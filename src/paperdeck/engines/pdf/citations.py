"""PDF bibliography normalization and conservative citation linking."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ...llm.prompts import load_prompt
from ...llm.schemas import PdfBibV1, PdfCiteMapV1


@dataclass(frozen=True)
class Splice:
    start: int
    end: int
    node: Any


@dataclass(frozen=True)
class CiteNode:
    bib_ids: list[str]
    text: str


@dataclass(frozen=True)
class RefNode:
    target_id: str
    kind: str
    text: str


@dataclass(frozen=True)
class BibEntryDraft:
    id: str
    number: str | None
    text: str
    urls: list[dict[str, str]] = field(default_factory=list)


def _anchor(alloc: Any, kind: str, index: int) -> str:
    return alloc.next(kind) if hasattr(alloc, "next") else f"{kind}-{index}"


def _safe_urls(urls: list[str], warnings: list[str], where: str) -> list[dict[str, str]]:
    safe: list[dict[str, str]] = []
    for url in urls:
        if url.startswith(("http://", "https://")):
            safe.append({"url": url, "kind": "generic"})
        else:
            warnings.append(f"bib-url-rejected:{where}")
    return safe


def extract_bibliography(
    bib_blocks: list[Any], llm: Any, ledger: Any = None, alloc: Any = None
) -> tuple[list[Any], dict[str, str], list[str], list[str]]:
    warnings: list[str] = []
    text = "\n".join(str(getattr(block, "text", block)) for block in bib_blocks)
    if not text.strip():
        return [], {}, [], ["pdf-bib-empty"]
    entries: list[Any] = []
    chunks = [text[i : i + 30000] for i in range(0, len(text), 30000)]
    for _chunk_idx, chunk in enumerate(chunks):
        response = llm.complete(
            "bib",
            [{"role": "system", "content": load_prompt("bib", text=chunk)}],
            PdfBibV1,
            max_tokens=8192,
            ledger=ledger,
        )
        for _item_idx, item in enumerate(response.entries):
            number = str(item.number).strip("[]") if item.number else None
            entry_id = (
                _anchor(alloc, "bib", len(entries) + 1)
                if alloc is not None
                else f"bib-{len(entries) + 1}"
            )
            urls = _safe_urls(list(item.urls), warnings, entry_id)
            try:
                from ...ir.model import BibEntry, BibUrl, Text

                content: list[Any] = [Text(text=item.text)]
                entries.append(
                    BibEntry(
                        id=entry_id,
                        number=number,
                        content=content,
                        urls=[BibUrl(url=url["url"], kind="generic") for url in urls],
                    )
                )
            except (ImportError, TypeError):
                entries.append(BibEntryDraft(entry_id, number, item.text, urls))
    numeric: dict[str, str] = {}
    for entry in entries:
        number = getattr(entry, "number", None)
        if number:
            numeric[str(number)] = str(entry.id)
    return entries, numeric, [str(getattr(entry, "id", "")) for entry in entries], warnings


_NUMERIC_RE = re.compile(r"\[(\d{1,3}(?:\s*[,;]\s*\d{1,3})*(?:\s*[-–]\s*\d{1,3})?)\]")


def _expand_numbers(raw: str) -> list[int]:
    output: list[int] = []
    for part in re.split(r"[,;]", raw):
        part = part.strip()
        match = re.fullmatch(r"(\d+)\s*[-–]\s*(\d+)", part)
        if match:
            start, end = map(int, match.groups())
            output.extend(range(start, min(end, start + 49) + 1))
        elif part.isdigit():
            output.append(int(part))
    return output[:50]


def _non_overlapping(items: list[Splice]) -> list[Splice]:
    return sorted(
        (item for item in items if item.end > item.start),
        key=lambda item: (item.start, -(item.end - item.start)),
    )


def link_citations(
    paragraph_texts: list[str], bib: list[Any], llm: Any = None, ledger: Any = None
) -> list[list[Splice]]:
    numeric = {
        str(getattr(entry, "number", "")): str(getattr(entry, "id", ""))
        for entry in bib
        if getattr(entry, "number", None)
    }
    result: list[list[Splice]] = []
    author_candidates: list[tuple[int, int, str]] = []
    for para_idx, text in enumerate(paragraph_texts):
        splices: list[Splice] = []
        for match in _NUMERIC_RE.finditer(text):
            ids: list[str] = []
            unknown: list[int] = []
            for number in _expand_numbers(match.group(1)):
                if str(number) in numeric:
                    ids.append(numeric[str(number)])
                else:
                    unknown.append(number)
            if not unknown and ids:
                splices.append(Splice(match.start(), match.end(), CiteNode(ids, match.group(0))))
        for match in re.finditer(
            r"\((?:[A-Z][A-Za-z'’-]+[^()]{0,60}?\d{4}[a-z]?(?:;[^()]{0,80})*)\)", text
        ):
            author_candidates.append((para_idx, match.start(), match.group(0)))
        result.append(splices)
    if author_candidates and llm is not None:
        markers = "\n".join(f"{i}: {candidate[2]}" for i, candidate in enumerate(author_candidates))

        def entry_text(item: Any) -> str:
            text = getattr(item, "text", None)
            if text:
                return str(text)
            return "".join(str(getattr(part, "text", "")) for part in getattr(item, "content", []))

        entries = "\n".join(f"{i}: {entry_text(item)}" for i, item in enumerate(bib))
        response = llm.complete(
            "cite-map",
            [
                {
                    "role": "system",
                    "content": load_prompt("cite_map", markers=markers, entries=entries),
                }
            ],
            PdfCiteMapV1,
            max_tokens=4096,
            ledger=ledger,
        )
        for mapping in response.mappings:
            try:
                marker_idx = next(
                    i for i, item in enumerate(author_candidates) if item[2] == mapping.marker
                )
            except StopIteration:
                continue
            valid = [bib[i].id for i in mapping.entry_indices if 0 <= i < len(bib)]
            if not valid:
                continue
            para_idx, start, marker = author_candidates[marker_idx]
            result[para_idx].append(Splice(start, start + len(marker), CiteNode(valid, marker)))
    return [_non_overlapping(items) for items in result]


def link_structural_refs(
    paragraph_texts: list[str], numbers_map: dict[tuple[str, str], str]
) -> list[list[Splice]]:
    patterns = (
        ("eq", re.compile(r"\b(?:Eq\.?|Equation)\s*\(?([0-9]+[a-z]?)\)?", re.I)),
        ("fig", re.compile(r"\b(?:Fig\.?|Figure)\s*([0-9]+[a-z]?)", re.I)),
        ("tab", re.compile(r"\b(?:Table|Tab\.?)\s*([0-9]+)", re.I)),
        ("sec", re.compile(r"(?:\b(?:Sec\.?|Section)\s*|§\s*)([0-9]+(?:\.[0-9]+)*)", re.I)),
    )
    output: list[list[Splice]] = []
    for text in paragraph_texts:
        row: list[Splice] = []
        for kind, pattern in patterns:
            for match in pattern.finditer(text):
                target = numbers_map.get((kind, match.group(1)))
                if target:
                    row.append(
                        Splice(match.start(), match.end(), RefNode(target, kind, match.group(0)))
                    )
        output.append(_non_overlapping(row))
    return output


__all__ = [
    "BibEntryDraft",
    "CiteNode",
    "RefNode",
    "Splice",
    "extract_bibliography",
    "link_citations",
    "link_structural_refs",
]
