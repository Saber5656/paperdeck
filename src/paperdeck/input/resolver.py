"""Classify command line input without performing network or write operations."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import unquote, urlparse

from ..errors import InputError

Kind = Literal["arxiv", "latex-local", "pdf-local"]

_NEW_ID = re.compile(r"^\d{4}\.\d{4,5}(?:v(\d+))?$")
_OLD_ID = re.compile(r"^[a-z][a-z-]*(?:\.[A-Z]{2})?/\d{7}(?:v(\d+))?$")
_SAFE_SLUG = re.compile(r"[^A-Za-z0-9._-]")
_ARXIV_HOSTS = {"arxiv.org", "www.arxiv.org", "export.arxiv.org"}
_ACCEPTED = (
    "Examples: 2401.12345, arXiv:hep-th/9901001v2, or "
    "https://arxiv.org/abs/2401.12345; local files: paper.tex, "
    "paper.tar.gz, or paper.pdf."
)


@dataclass(frozen=True)
class InputSpec:
    """The normalized input accepted by the conversion pipeline."""

    kind: Kind
    arxiv_id: str | None = None
    version: int | None = None
    path: Path | None = None
    archive: bool = False
    original: str = ""


def _invalid(raw: str) -> InputError:
    return InputError(f"Unrecognized input: {raw[:120]}", _ACCEPTED, "input-unrecognized")


def _parse_id(value: str) -> tuple[str, int | None] | None:
    value = re.sub(r"^arxiv:", "", value, flags=re.IGNORECASE)
    match = _NEW_ID.fullmatch(value) or _OLD_ID.fullmatch(value)
    if match is None:
        return None
    version = int(match.group(1)) if match.group(1) else None
    return value[: -len(match.group(1)) - 1] if match.group(1) else value, version


def resolve(raw: str) -> InputSpec:
    """Resolve *raw*; an existing path wins over ID parsing.

    In particular, a regular file literally named ``2401.12345`` is treated as a
    local file candidate and subsequently rejected for its suffix, rather than as
    an arXiv ID.  This preserves the documented local-path-first grammar.
    """

    candidate = Path(raw)
    try:
        if candidate.exists():
            resolved = candidate.resolve(strict=True)
            if not resolved.is_file():
                raise InputError("Input path is not a regular file", _ACCEPTED, "input-not-file")
            lower = resolved.name.lower()
            if lower.endswith(".pdf"):
                return InputSpec("pdf-local", path=resolved, original=raw)
            if lower.endswith(".tex"):
                return InputSpec("latex-local", path=resolved, archive=False, original=raw)
            if lower.endswith((".tar", ".tar.gz", ".tgz", ".gz")):
                return InputSpec("latex-local", path=resolved, archive=True, original=raw)
            raise InputError(
                f"Unsupported local file suffix: {resolved.suffix}", _ACCEPTED, "input-suffix"
            )
    except OSError:
        raise InputError("Input path could not be read", _ACCEPTED, "input-missing") from None

    parsed = urlparse(raw)
    if (
        parsed.scheme.lower() in {"http", "https"}
        and parsed.hostname
        and parsed.hostname.lower() in _ARXIV_HOSTS
    ):
        path = unquote(parsed.path)
        for prefix in ("/abs/", "/pdf/", "/html/"):
            if path.startswith(prefix):
                value = path[len(prefix) :]
                if prefix == "/pdf/" and value.lower().endswith(".pdf"):
                    value = value[:-4]
                parsed_id = _parse_id(value)
                if parsed_id:
                    arxiv_id, version = parsed_id
                    return InputSpec("arxiv", arxiv_id=arxiv_id, version=version, original=raw)
                break
        raise _invalid(raw)

    parsed_id = _parse_id(raw)
    if parsed_id:
        arxiv_id, version = parsed_id
        return InputSpec("arxiv", arxiv_id=arxiv_id, version=version, original=raw)
    raise _invalid(raw)


def output_slug(spec: InputSpec) -> str:
    """Return a deterministic, filesystem-safe output slug for *spec*."""

    if spec.kind == "arxiv":
        ident = spec.arxiv_id or "unknown"
        suffix = f"v{spec.version}" if spec.version is not None else ""
        raw = "arxiv-" + ident.replace("/", "-") + suffix
    else:
        raw = spec.path.stem if spec.path else "paper"
        if spec.path and spec.path.name.lower().endswith(".tar.gz"):
            raw = spec.path.name[:-7]
        elif spec.path and spec.path.name.lower().endswith(".tgz"):
            raw = spec.path.name[:-4]
    safe = _SAFE_SLUG.sub("-", raw)
    return safe or "paper"
