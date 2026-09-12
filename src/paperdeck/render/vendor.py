"""Verify the committed KaTeX manifest without importing conversion code."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath


def verify_vendored(root: Path) -> list[str]:
    try:
        manifest = json.loads((root / "MANIFEST.json").read_text())
        files = manifest["files"]
        if not isinstance(files, dict):
            return ["MANIFEST.json"]
        failures = []
        for name, checksum in files.items():
            parts = PurePosixPath(name).parts
            if not parts or ".." in parts or PurePosixPath(name).is_absolute() or "\\" in name:
                failures.append(name)
                continue
            path = root / name
            if (
                path.is_symlink()
                or not path.is_file()
                or hashlib.sha256(path.read_bytes()).hexdigest() != checksum
            ):
                failures.append(name)
        for required in ("katex.min.js", "katex.min.css", "LICENSE"):
            if required not in files:
                failures.append(required)
        if not any(name.startswith("fonts/") for name in files):
            failures.append("fonts")
        return sorted(set(failures))
    except (OSError, ValueError, KeyError, TypeError):
        return ["MANIFEST.json"]
