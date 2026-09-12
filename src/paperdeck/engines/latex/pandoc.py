"""Hardened Pandoc JSON subprocess boundary."""

from __future__ import annotations

import json
import os
import re
import selectors
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from paperdeck.errors import ConversionError

_MAX_STDOUT = 200 * 1024 * 1024


@dataclass(frozen=True)
class PandocResult:
    ast: dict[str, object]
    warnings: list[str]
    version: tuple[int, int]


class PandocNotFoundError(ConversionError):
    default_code = "pandoc-missing"


def pandoc_version() -> tuple[int, int] | None:
    executable = shutil.which("pandoc")
    if executable is None:
        return None
    try:
        result = subprocess.run(  # noqa: S603
            [executable, "--version"],
            capture_output=True,
            stdin=subprocess.DEVNULL,
            env={"PATH": os.environ.get("PATH", os.defpath)},
            check=False,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    first_line = result.stdout.splitlines()[0] if result.stdout else ""
    match = re.search(r"(\d+)\.(\d+)", first_line)
    return (int(match.group(1)), int(match.group(2))) if match else None


def _failure(message: str, code: str) -> ConversionError:
    return ConversionError(
        message, hint="Install Pandoc >= 3.0 and retry the conversion.", code=code
    )


def _parse_result(stdout: bytes, stderr: bytes, version: tuple[int, int]) -> PandocResult:
    try:
        value = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise _failure("Pandoc returned invalid JSON", "pandoc-bad-json") from exc
    if (
        not isinstance(value, dict)
        or not isinstance(value.get("blocks"), list)
        or not isinstance(value.get("meta"), dict)
        or not isinstance(value.get("pandoc-api-version"), list)
    ):
        raise _failure("Pandoc returned an invalid AST shape", "pandoc-bad-json")
    warning_text = stderr.decode("utf-8", errors="replace")
    return PandocResult(value, [line for line in warning_text.splitlines() if line], version)


def run_pandoc(flattened: Path, cwd: Path, timeout_s: int = 120) -> PandocResult:
    """Run Pandoc without a shell, with minimal environment and bounded output."""
    executable = shutil.which("pandoc")
    version = pandoc_version()
    if executable is None or version is None or version < (3, 0):
        found = "not installed" if version is None else f"{version[0]}.{version[1]}"
        raise PandocNotFoundError(
            f"Pandoc >= 3.0 is required (found {found})",
            hint="Install Pandoc >= 3.0 using your OS package manager.",
            code="pandoc-missing",
        )
    try:
        process = subprocess.Popen(  # noqa: S603
            [executable, "-f", "latex+raw_tex", "-t", "json", "--quiet", str(flattened)],
            cwd=cwd,
            env={"PATH": os.environ.get("PATH", os.defpath)},
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
        )
    except OSError as exc:
        raise _failure(f"could not start Pandoc: {exc}", "pandoc-failed") from exc
    if process.stdout is None or process.stderr is None:
        process.kill()
        process.wait()
        raise _failure("Pandoc pipes could not be opened", "pandoc-failed")
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ, "stdout")
    selector.register(process.stderr, selectors.EVENT_READ, "stderr")
    stdout = bytearray()
    stderr = bytearray()
    deadline = time.monotonic() + timeout_s
    try:
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                process.kill()
                process.wait()
                raise _failure("Pandoc timed out", "pandoc-timeout")
            for key, _ in selector.select(min(remaining, 0.5)):
                chunk = os.read(key.fd, 1024 * 1024)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                if key.data == "stdout":
                    stdout.extend(chunk)
                    if len(stdout) > _MAX_STDOUT:
                        process.kill()
                        process.wait()
                        raise _failure("Pandoc output exceeded 200 MB", "pandoc-output-cap")
                else:
                    stderr.extend(chunk)
                    if len(stderr) > 8192:
                        del stderr[:-8192]
        return_code = process.wait(timeout=max(0.1, deadline - time.monotonic()))
    except subprocess.TimeoutExpired as exc:
        process.kill()
        process.wait()
        raise _failure("Pandoc timed out", "pandoc-timeout") from exc
    finally:
        selector.close()
    if return_code != 0:
        detail = bytes(stderr[-2048:]).decode("utf-8", errors="replace")
        detail = "".join(char for char in detail if char >= " " or char in "\n\t")
        raise _failure(f"Pandoc failed: {detail.strip()}", "pandoc-failed")
    return _parse_result(bytes(stdout), bytes(stderr), version)
