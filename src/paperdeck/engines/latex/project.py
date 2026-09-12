"""LaTeX source selection, safe include flattening, and preamble extraction."""

from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from paperdeck.errors import ConversionError, SecurityError
from paperdeck.ir.model import Warning

_COMMENT_ENV = re.compile(r"\\begin\{(verbatim|lstlisting|filecontents)(?:\*?)\}", re.I)
_END_COMMENT_ENV = re.compile(r"\\end\{(verbatim|lstlisting|filecontents)(?:\*?)\}", re.I)
_INCLUDE = re.compile(r"\\(input|include)\s*\{([^{}]*)\}")


@dataclass
class LatexProject:
    root: Path
    main: Path
    flattened: Path
    preamble: str
    warnings: list[Warning] = field(default_factory=list)
    tempdir: Path | None = None


def _read(path: Path, warnings: list[Warning]) -> str:
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        warnings.append(
            Warning(code="source-encoding-fallback", message=f"latin-1 fallback: {path.name}")
        )
        return raw.decode("latin-1")


def strip_comments(text: str) -> str:
    """Remove unescaped percent comments while preserving literal-code environments."""
    out: list[str] = []
    env: str | None = None
    for line in text.splitlines(keepends=True):
        if env is not None:
            out.append(line)
            if _END_COMMENT_ENV.search(line):
                env = None
            continue
        opening = _COMMENT_ENV.search(line)
        if opening:
            env = opening.group(1).lower()
            out.append(line)
            if _END_COMMENT_ENV.search(line):
                env = None
            continue
        cut: int | None = None
        for index, char in enumerate(line):
            if char != "%":
                continue
            backslashes = 0
            cursor = index - 1
            while cursor >= 0 and line[cursor] == "\\":
                backslashes += 1
                cursor -= 1
            if backslashes % 2 == 0:
                cut = index
                break
        out.append(line if cut is None else line[:cut] + ("\n" if line.endswith("\n") else ""))
    return "".join(out)


def _candidate_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.tex") if path.is_file())


def _reachable(path: Path, root: Path, seen: set[Path] | None = None) -> set[Path]:
    seen = set() if seen is None else seen
    if path in seen:
        return seen
    seen.add(path)
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return seen
    for match in _INCLUDE.finditer(text):
        target = match.group(2)
        candidate = root / target
        if candidate.suffix.lower() != ".tex":
            candidate = candidate.with_suffix(".tex")
        if candidate.exists() and candidate.resolve().is_relative_to(root.resolve()):
            _reachable(candidate.resolve(), root, seen)
    return seen


def _select_main(root: Path, warnings: list[Warning]) -> Path:
    candidates = _candidate_files(root)
    if not candidates:
        raise ConversionError(
            "no .tex main file found",
            hint="Provide a LaTeX source file or archive.",
            code="no-main-tex",
        )
    documentclass = [
        path
        for path in candidates
        if re.search(r"\\documentclass(?:\s*\[[^]]*\])?\s*\{", path.read_text(errors="replace"))
    ]
    if len(documentclass) == 1:
        return documentclass[0]
    preferred = {"main": 0, "paper": 1, "ms": 2, "arxiv": 3}
    preferred_candidates = [path for path in candidates if path.stem.lower() in preferred]
    if preferred_candidates:
        return sorted(preferred_candidates, key=lambda path: preferred[path.stem.lower()])[0]
    ranked = sorted(
        candidates,
        key=lambda path: (len(_reachable(path, root)), path.stat().st_size),
        reverse=True,
    )
    if len(ranked) > 1 and (
        len(_reachable(ranked[0], root)) == len(_reachable(ranked[1], root))
        and ranked[0].stat().st_size == ranked[1].stat().st_size
    ):
        warnings.append(
            Warning(code="main-tex-ambiguous", message="multiple equally suitable main files")
        )
    return ranked[0]


def _confined(root: Path, relative: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute():
        raise SecurityError(
            "include path escapes source root",
            hint="Remove absolute include paths.",
            code="include-escape",
        )
    target = root / candidate
    if target.suffix.lower() != ".tex":
        target = target.with_suffix(".tex")
    resolved = target.resolve(strict=False)
    if not resolved.is_relative_to(root.resolve()):
        raise SecurityError(
            "include path escapes source root",
            hint="Keep includes inside the source tree.",
            code="include-escape",
        )
    return resolved


def prepare(source: Path) -> LatexProject:
    """Prepare a source directory or single file for the Pandoc stage."""
    warnings: list[Warning] = []
    source = source.resolve()
    if source.is_file():
        root, main = source.parent, source
    elif source.is_dir():
        root = source
        main = _select_main(root, warnings)
    else:
        raise ConversionError(
            f"source does not exist: {source}", hint="Check the input path.", code="no-main-tex"
        )
    active: set[Path] = set()

    def flatten(path: Path, depth: int = 0) -> str:
        if depth > 20:
            raise ConversionError(
                "include nesting exceeds depth 20",
                hint="Reduce include nesting.",
                code="include-cycle",
            )
        resolved = path.resolve()
        if resolved in active:
            raise ConversionError(
                "include cycle detected", hint="Break the include cycle.", code="include-cycle"
            )
        active.add(resolved)
        text = strip_comments(_read(resolved, warnings))
        cursor = 0
        pieces: list[str] = []
        for match in _INCLUDE.finditer(text):
            pieces.append(text[cursor : match.start()])
            kind, name = match.groups()
            try:
                target = _confined(root, name.strip())
            except SecurityError:
                raise
            if not target.exists():
                warnings.append(Warning(code="missing-include", message=f"missing include: {name}"))
                pieces.append(match.group(0))
            else:
                pieces.append(f"% >>> {name}\n")
                pieces.append(flatten(target, depth + 1))
                pieces.append(f"\n% <<< {name}\n")
                if kind == "include":
                    pieces.append("\n")
            cursor = match.end()
        pieces.append(text[cursor:])
        active.remove(resolved)
        return "".join(pieces)

    flattened_text = flatten(main)
    marker = re.search(r"\\begin\s*\{document\}", flattened_text)
    if marker is None:
        raise ConversionError(
            "missing \\begin{document}",
            hint="Add a document environment.",
            code="no-begin-document",
        )
    tempdir = Path(tempfile.mkdtemp(prefix="paperdeck-latex-"))
    flattened = tempdir / "main.flat.tex"
    flattened.write_text(flattened_text, encoding="utf-8")
    return LatexProject(root, main, flattened, flattened_text[: marker.start()], warnings, tempdir)
