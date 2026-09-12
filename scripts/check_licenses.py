#!/usr/bin/env python3
"""Fail when runtime dependencies contain a non-permissive license.

Input is the JSON emitted by ``pip-licenses --format=json``. A requirements
file from ``uv export --no-dev`` narrows enforcement to runtime packages;
dev-only findings are printed as notices for maintainers.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

ALLOWLIST = frozenset(
    {"MIT", "BSD-2-Clause", "BSD-3-Clause", "Apache-2.0", "ISC", "Python-2.0", "PSF-2.0"}
)
# Existing httpx CA-data dependency; unmodified, separately installed distribution.
# Scope and upstream source are documented in docs/DEPENDENCY_LICENSES.md.
PACKAGE_EXCEPTIONS = {
    "certifi": {"MPL-2.0", "Mozilla Public License 2.0 (MPL 2.0)"},
}
REVIEWED_BINARY_LICENSES = {
    ("pypdfium2", "5.13.0"): "BSD-3-Clause, Apache-2.0, dependency licenses",
}


def _name(row: Mapping[str, Any]) -> str:
    return str(row.get("Name", row.get("name", ""))).strip()


def _license(row: Mapping[str, Any]) -> str:
    return str(row.get("License", row.get("license", "UNKNOWN"))).strip()


def _allowed_parts(value: str) -> set[str]:
    parts = re.split(r"\s+(?:OR|AND)\s+|[,;|/]", value, flags=re.IGNORECASE)
    found: set[str] = set()
    for part in parts:
        compact = re.sub(r"[^a-z0-9]+", "", part.lower())
        if compact == "mit" or compact == "mitlicense":
            found.add("MIT")
        elif compact in {"bsd2clause", "bsdlicense2clause"}:
            found.add("BSD-2-Clause")
        elif compact in {"bsd3clause", "bsdlicense3clause", "bsdlicense"}:
            found.add("BSD-3-Clause")
        elif compact in {"apache2", "apache20", "apachelicense20", "apachesoftwarelicense"}:
            found.add("Apache-2.0")
        elif compact == "isc":
            found.add("ISC")
        elif compact in {"python2", "python20", "pythonsoftwarefoundationlicense"}:
            found.add("Python-2.0")
        elif compact in {"psf2", "psf20", "psflicense"}:
            found.add("PSF-2.0")
    return found


def check_licenses(
    rows: Iterable[Mapping[str, Any]], runtime_packages: set[str] | None = None
) -> tuple[list[Mapping[str, Any]], list[Mapping[str, Any]]]:
    """Return ``(runtime_violations, dev_only_notices)`` for license rows."""
    violations: list[Mapping[str, Any]] = []
    notices: list[Mapping[str, Any]] = []
    for row in rows:
        package = _name(row)
        value = _license(row)
        if value in PACKAGE_EXCEPTIONS.get(package.lower(), set()):
            continue
        if REVIEWED_BINARY_LICENSES.get((package.lower(), str(row.get("Version", "")))) == value:
            continue
        # Every conjunct must be permitted; an OR offers an independent choice.
        # Nested SPDX expressions require review rather than permissive guessing.
        nested = ("(" in value or ")" in value) and re.search(r"\b(?:AND|OR)\b", value)
        allowed = not nested and any(
            all(
                _allowed_parts(part) & ALLOWLIST
                for part in re.split(r"\s+AND\s+|[,;|/]", alternative, flags=re.IGNORECASE)
            )
            for alternative in re.split(r"\s+OR\s+", value, flags=re.IGNORECASE)
        )
        if allowed:
            continue
        runtime_names = {item.lower() for item in runtime_packages} if runtime_packages else set()
        if runtime_packages is None or package.lower() in runtime_names:
            violations.append(row)
        else:
            notices.append(row)
    return violations, notices


def _runtime_names(path: Path) -> set[str]:
    names: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        match = re.match(r"([A-Za-z0-9][A-Za-z0-9_.-]*)", line)
        if match:
            names.add(match.group(1))
    return names


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "json_file", nargs="?", type=Path, help="pip-licenses JSON; stdin by default"
    )
    parser.add_argument("--runtime-file", type=Path)
    args = parser.parse_args(argv)
    raw = args.json_file.read_text(encoding="utf-8") if args.json_file else sys.stdin.read()
    rows = json.loads(raw)
    if not isinstance(rows, list):
        raise SystemExit("pip-licenses JSON must be an array")
    runtime = _runtime_names(args.runtime_file) if args.runtime_file else None
    violations, notices = check_licenses(rows, runtime)
    for row in notices:
        print(f"notice: dev-only {_name(row)} has {_license(row)}")
    if violations:
        print("Runtime license violations:")
        for row in violations:
            print(f"  {_name(row)}: {_license(row)} (allow: {', '.join(sorted(ALLOWLIST))})")
        return 1
    print("Runtime license gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
