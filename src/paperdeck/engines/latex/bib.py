"""Tolerant bibliography readers for compiled LaTeX and BibTeX sources."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from paperdeck.engines.latex.project import LatexProject
from paperdeck.ir.anchors import AnchorAllocator
from paperdeck.ir.model import BibEntry, BibUrl, Emph, ExtLink, Inline, Math, Strong, Text, Warning


@dataclass(frozen=True)
class BibRef:
    anchor_id: str
    number: str | None
    label: str | None


def _strip_commands(text: str) -> str:
    text = re.sub(r"\\(?:text(?:it|bf|rm)|emph)\s*\{([^{}]*)\}", r"\1", text)
    text = text.replace("~", " ").replace(r"\&", "&").replace(r"\%", "%")
    text = text.replace("--", "–")
    text = re.sub(r"\\[A-Za-z]+\s*", "", text)
    return text.replace("{", "").replace("}", "").strip()


def _entry_inlines(text: str, warnings: list[Warning]) -> tuple[list[Inline], list[BibUrl]]:
    urls: list[BibUrl] = []
    result: list[Inline] = []
    cursor = 0
    pattern = re.compile(r"\\(url|href)\s*\{([^{}]*)\}(?:\{([^{}]*)\})?")
    for match in pattern.finditer(text):
        plain = text[cursor : match.start()]
        if plain:
            result.extend(_plain_inlines(plain))
        url, label = match.group(2), match.group(3) or match.group(2)
        if re.match(r"^(?:https?|mailto):", url, re.I):
            result.append(ExtLink(url=url, content=[Text(text=_strip_commands(label))]))
            urls.append(BibUrl(url=url, kind="generic"))
        else:
            result.append(Text(text=_strip_commands(label)))
            warnings.append(
                Warning(code="bib-tex-dropped", message="invalid bibliography link scheme")
            )
        cursor = match.end()
    if cursor < len(text):
        result.extend(_plain_inlines(text[cursor:]))
    return result, urls


def _plain_inlines(text: str) -> list[Inline]:
    result: list[Inline] = []
    cursor = 0
    pattern = re.compile(r"\$([^$]+)\$|\\(emph|textit|textbf)\s*\{([^{}]*)\}")
    for match in pattern.finditer(text):
        if match.start() > cursor:
            result.append(Text(text=_strip_commands(text[cursor : match.start()])))
        if match.group(1) is not None:
            result.append(Math(latex=match.group(1)))
        elif match.group(2) in {"emph", "textit"}:
            result.append(Emph(content=[Text(text=_strip_commands(match.group(3) or ""))]))
        else:
            result.append(Strong(content=[Text(text=_strip_commands(match.group(3) or ""))]))
        cursor = match.end()
    if cursor < len(text):
        result.append(Text(text=_strip_commands(text[cursor:])))
    return [item for item in result if not isinstance(item, Text) or item.text]


def _parse_bbl(
    text: str, alloc: AnchorAllocator
) -> tuple[list[BibEntry], dict[str, BibRef], list[Warning]]:
    entries: list[BibEntry] = []
    index: dict[str, BibRef] = {}
    warnings: list[Warning] = []
    matches = list(re.finditer(r"\\bibitem(?:\[([^]]*)\])?\s*\{([^}]+)\}", text))
    for position, match in enumerate(matches, 1):
        key = match.group(2).strip()
        if key in index:
            warnings.append(
                Warning(code=f"bib-key-duplicate:{key}", message="duplicate bibliography key")
            )
            continue
        end = matches[position].start() if position < len(matches) else len(text)
        body = text[match.end() : end]
        label = _strip_commands(match.group(1)) if match.group(1) else None
        number = None if label else str(position)
        anchor = alloc.next("bib")
        entry_warnings: list[Warning] = []
        content, urls = _entry_inlines(body, entry_warnings)
        entries.append(
            BibEntry(id=anchor, number=number, label=label, key=key, content=content, urls=urls)
        )
        index[key] = BibRef(anchor, number, label)
        if entry_warnings:
            warnings.append(entry_warnings[0])
    return entries, index, warnings


def _parse_bibtex(
    text: str, alloc: AnchorAllocator
) -> tuple[list[BibEntry], dict[str, BibRef], list[Warning]]:
    entries: list[BibEntry] = []
    index: dict[str, BibRef] = {}
    warnings: list[Warning] = []
    starts = list(re.finditer(r"@\w+\s*\{\s*([^,]+),", text))
    for position, match in enumerate(starts, 1):
        key = match.group(1).strip()
        end = starts[position].start() if position < len(starts) else len(text)
        fields_text = text[match.end() : end]
        fields: dict[str, str] = {}
        for field_match in re.finditer(r"(\w+)\s*=\s*(?:\{([^{}]*)\}|\"([^\"]*)\")", fields_text):
            fields[field_match.group(1).lower()] = (
                field_match.group(2) or field_match.group(3) or ""
            ).strip()
        if not key or key in index:
            warnings.append(
                Warning(code=f"bib-key-duplicate:{key}", message="duplicate bibliography key")
            )
            continue
        author = _strip_commands(fields.get("author", ""))
        title = _strip_commands(fields.get("title", ""))
        venue = _strip_commands(fields.get("journal", fields.get("booktitle", "")))
        year = _strip_commands(fields.get("year", ""))
        text_value = ". ".join(item for item in [author, title] if item)
        if venue:
            text_value += f". {venue}"
        if year:
            text_value += f", {year}"
        if not text_value:
            warnings.append(
                Warning(
                    code=f"bib-entry-skipped:{key}",
                    message="bibliography entry has no readable fields",
                )
            )
            continue
        entry_id = alloc.next("bib")
        content, urls = _entry_inlines(text_value, warnings)
        for field, kind, prefix in (
            ("doi", "doi", "https://doi.org/"),
            ("eprint", "arxiv", "https://arxiv.org/abs/"),
            ("url", "generic", ""),
        ):
            value = fields.get(field)
            if value:
                target = prefix + value
                if re.match(r"^https?://", target):
                    urls.append(
                        BibUrl(
                            url=target,
                            kind=cast(Literal["doi", "arxiv", "generic"], kind),
                        )
                    )
        number = str(position)
        entries.append(BibEntry(id=entry_id, number=number, key=key, content=content, urls=urls))
        index[key] = BibRef(entry_id, number, None)
    return entries, index, warnings


def parse_bibliography(
    project: LatexProject, alloc: AnchorAllocator
) -> tuple[list[BibEntry], dict[str, BibRef], list[Warning]]:
    """Select .bbl, inline thebibliography, or .bib in that priority order."""
    warnings: list[Warning] = []

    def capped(
        entries: list[BibEntry], index: dict[str, BibRef], stage_warnings: list[Warning]
    ) -> tuple[list[BibEntry], dict[str, BibRef], list[Warning]]:
        if len(entries) > 2000:
            stage_warnings.append(
                Warning(code="bib-cap", message="bibliography truncated at 2000 entries")
            )
            entries = entries[:2000]
            index = {entry.key: index[entry.key] for entry in entries if entry.key in index}
        return entries, index, stage_warnings

    bbls = sorted(project.root.glob("*.bbl"))
    if bbls:
        preferred = next((path for path in bbls if path.stem == project.main.stem), None)
        if preferred is None and len(bbls) > 1:
            warnings.append(
                Warning(
                    code="bib-bbl-multiple",
                    message="multiple .bbl files concatenated in name order",
                )
            )
        bbl_text = (
            _read_text(preferred) if preferred else "\n".join(_read_text(path) for path in bbls)
        )
        entries, index, parsed_warnings = _parse_bbl(bbl_text, alloc)
        if entries:
            warnings.append(Warning(code="bib-source:bbl", message="bibliography read from .bbl"))
            return capped(entries, index, warnings + parsed_warnings)
    inline = re.search(
        r"\\begin\{thebibliography\}.*?(.+?)\\end\{thebibliography\}",
        _read_text(project.flattened),
        re.S,
    )
    if inline:
        entries, index, parsed_warnings = _parse_bbl(inline.group(1), alloc)
        if entries:
            warnings.append(
                Warning(code="bib-source:thebibliography", message="bibliography read from source")
            )
            return capped(entries, index, warnings + parsed_warnings)
    bibs = sorted(project.root.glob("*.bib"))
    if bibs:
        entries, index, parsed_warnings = _parse_bibtex(
            "\n".join(_read_text(path) for path in bibs), alloc
        )
        warnings.append(Warning(code="bib-source:bib", message="bibliography read from .bib"))
        return capped(entries, index, warnings + parsed_warnings)
    return [], {}, warnings


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")
