"""Content pass and engine assembly for the arXiv HTML engine."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any, Literal

from bs4 import BeautifulSoup, Tag
from bs4.element import NavigableString

from paperdeck import __version__
from paperdeck.engines import EngineContext
from paperdeck.errors import ConversionError
from paperdeck.input.arxiv import ArxivClient
from paperdeck.ir.anchors import AnchorAllocator
from paperdeck.ir.model import (
    BibEntry,
    Cite,
    Code,
    Document,
    Emph,
    Equation,
    ExtLink,
    Figure,
    FootnoteDef,
    FootnoteRef,
    Inline,
    LineBreak,
    Math,
    Meta,
    MetaLink,
    Paragraph,
    Provenance,
    RefLink,
    Section,
    Source,
    Strong,
    Sub,
    Sup,
    Table,
    Text,
    Unhandled,
    Warning,
)
from paperdeck.ir.validate import validate_document
from paperdeck.netgate import NetGate

from .fetch import fetch_html
from .parse_structure import StructureResult, parse_structure
from .quality import assess


def _classes(tag: Tag) -> set[str]:
    value = tag.get("class")
    return {str(item) for item in value} if isinstance(value, (list, tuple)) else set()


def _clean(tag: Tag | None) -> str:
    return tag.get_text(" ", strip=True) if tag else ""


def _number(tag: Tag) -> str | None:
    value = _clean(tag.select_one(".ltx_tag")) if tag.select_one(".ltx_tag") else ""
    value = value.strip("()[]")
    return value or None


def _kind(
    target: str, structure: StructureResult
) -> Literal["eq", "fig", "tab", "sec", "bib", "fn"]:
    tag = structure.elements.get(target)
    if tag is None:
        return "sec"
    classes = _classes(tag)
    if any(item.startswith("ltx_equation") for item in classes):
        return "eq"
    if "ltx_figure" in classes:
        return "fig"
    if "ltx_table" in classes or "ltx_tabular" in classes:
        return "tab"
    if "ltx_note" in classes:
        return "fn"
    if "ltx_bibitem" in classes:
        return "bib"
    if tag.name == "section":
        return "sec"
    return "sec"


def _inlines(node: Tag, structure: StructureResult) -> list[Inline]:
    result: list[Inline] = []
    for child in node.children:
        if isinstance(child, NavigableString):
            if str(child):
                result.append(Text(text=str(child)))
            continue
        if not isinstance(child, Tag):
            continue
        classes = _classes(child)
        if "ltx_tag" in classes:
            continue
        if child.name == "math":
            alt = child.get("alttext")
            if alt is None:
                structure.warnings.append(
                    Warning(code="math-alttext-missing", message="MathML has no alttext")
                )
                result.append(Text(text=_clean(child)))
            else:
                result.append(Math(latex=str(alt)))
        elif child.name == "br":
            result.append(LineBreak())
        elif (
            child.name == "a"
            and "ltx_ref" in classes
            and str(child.get("href", "")).startswith("#")
        ):
            fragment = str(child.get("href"))[1:]
            target = structure.source_id_map.get(fragment, "")
            if not target:
                structure.warnings.append(
                    Warning(
                        code="unresolved-ref",
                        message="reference target is unresolved",
                        where=fragment,
                    )
                )
            result.append(
                RefLink(
                    target_id=target,
                    kind=_kind(target, structure),
                    text=child.get_text(" ", strip=True),
                )
            )
        elif "ltx_cite" in classes:
            bib_ids: list[str] = []
            text = child.get_text(" ", strip=True)
            for link in child.select("a[href^='#bib']"):
                fragment = str(link.get("href") or "")[1:]
                bib_target = structure.source_id_map.get(fragment)
                if bib_target:
                    bib_ids.append(bib_target)
                else:
                    structure.warnings.append(
                        Warning(
                            code="cite-unresolved:" + fragment,
                            message="citation target is unresolved",
                            where=fragment,
                        )
                    )
            result.append(Cite(bib_ids=bib_ids, text=text if bib_ids else "?"))
        elif child.name == "a" and child.get("href"):
            url = str(child.get("href"))
            if re.match(r"^(?:https?|mailto):", url, re.I):
                result.append(ExtLink(url=url, content=_inlines(child, structure)))
            else:
                result.append(Text(text=child.get_text(" ", strip=True)))
        elif child.name in {"em", "i"} or "ltx_text_emph" in classes:
            result.append(Emph(content=_inlines(child, structure)))
        elif child.name in {"strong", "b"} or "ltx_text_bold" in classes:
            result.append(Strong(content=_inlines(child, structure)))
        elif child.name == "sub":
            result.append(Sub(content=_inlines(child, structure)))
        elif child.name == "sup":
            result.append(Sup(content=_inlines(child, structure)))
        elif "ltx_note" in classes:
            fragment = str(child.get("id") or "")
            target = structure.source_id_map.get(fragment, "")
            result.append(FootnoteRef(target_id=target, number=_number(child) or ""))
        elif child.name == "code":
            result.append(Code(text=child.get_text("", strip=False)))
        else:
            result.extend(_inlines(child, structure))
    return result


def _block(block: Any, structure: StructureResult) -> Any:
    tag = structure.elements.get(block.id)
    if tag is None:
        return block
    if isinstance(block, Section):
        title = tag.select_one(":scope > .ltx_title") or tag.select_one(".ltx_title")
        return block.model_copy(
            update={
                "title": _inlines(title, structure) if title else block.title,
                "children": [_block(child, structure) for child in block.children],
            }
        )
    if isinstance(block, Paragraph):
        return block.model_copy(update={"content": _inlines(tag, structure)})
    if isinstance(block, Figure):
        caption = tag.select_one(".ltx_caption")
        return block.model_copy(
            update={"caption": _inlines(caption, structure) if caption else block.caption}
        )
    if isinstance(block, Table):
        rows: list[list[Any]] = []
        table = tag.select_one("table") or tag
        for tr in table.find_all("tr"):
            cells = []
            for cell in tr.find_all(["th", "td"], recursive=False):
                current = next(
                    (
                        item
                        for row in block.rows or []
                        for item in row
                        if isinstance(item.content[0], Text)
                        and item.content[0].text == _clean(cell)
                    ),
                    None,
                )
                if current:
                    cells.append(current.model_copy(update={"content": _inlines(cell, structure)}))
            if cells:
                rows.append(cells)
        return block.model_copy(update={"rows": rows or block.rows})
    if isinstance(block, Unhandled) and any(
        cls.startswith("ltx_equation") for cls in _classes(tag)
    ):
        math = tag.select_one("math")
        alt = math.get("alttext") if math else None
        if alt is None:
            structure.warnings.append(
                Warning(
                    code="math-alttext-missing", message="equation has no alttext", where=block.id
                )
            )
            return Unhandled(id=block.id, text=_clean(tag))
        return Equation(
            id=block.id,
            number=_number(tag),
            content_kind="latex",
            latex=str(alt),
            latex_verified=True,
        )
    return block


def parse_content(
    structure: StructureResult,
) -> tuple[list[Any], list[BibEntry], list[FootnoteDef]]:
    body = [_block(block, structure) for block in structure.body]
    bibliography: list[BibEntry] = []
    for anchor, tag in structure.bibliography:
        number = _number(tag)
        content = _inlines(tag, structure)
        bibliography.append(BibEntry(id=anchor, number=number, content=content, urls=[]))
    footnotes: list[FootnoteDef] = []
    for anchor, tag in structure.footnotes:
        footnotes.append(
            FootnoteDef(
                id=anchor,
                number=_number(tag) or "",
                content=[Paragraph(id=anchor + "-para", content=_inlines(tag, structure))],
            )
        )
    return body, bibliography, footnotes


class ArxivHtmlEngine:
    name = "arxiv-html"

    def available(self, ctx: EngineContext) -> tuple[bool, str]:
        if ctx.spec.kind != "arxiv" or not ctx.spec.arxiv_id:
            return False, "html-unavailable"
        if ctx.settings.offline:
            version = ctx.spec.version
            if version is None:
                for candidate in reversed(ctx.cache.versions(ctx.spec.arxiv_id)):
                    key = (
                        f"arxiv/{ctx.spec.arxiv_id.replace('/', '--')}/{candidate}/html/index.html"
                    )
                    if ctx.cache.exists(key):
                        return True, ""
                return False, "offline-uncached"
            key = f"arxiv/{ctx.spec.arxiv_id.replace('/', '--')}/{version}/html/index.html"
            return ctx.cache.exists(key), "" if ctx.cache.exists(key) else "offline-uncached"
        return True, ""

    def convert(self, ctx: EngineContext) -> Document:
        client = ArxivClient(NetGate(ctx.settings), ctx.cache)
        meta = client.metadata(ctx.spec.arxiv_id or "", ctx.spec.version)
        artifact = fetch_html(ctx, meta)
        if artifact is None:
            raise ConversionError(
                "arXiv HTML is unavailable", "fall back to another engine", "html-unavailable"
            )
        gate = assess(artifact.page_path.read_text(encoding="utf-8", errors="replace"))
        if not gate.ok:
            raise ConversionError(
                "arXiv HTML quality gate failed",
                "fall back to another engine",
                gate.reason or "html-low-quality",
            )
        soup = BeautifulSoup(
            artifact.page_path.read_text(encoding="utf-8", errors="replace"), "html.parser"
        )
        structure = parse_structure(soup, artifact, AnchorAllocator(), ctx.settings.limits)
        body, bibliography, footnotes = parse_content(structure)
        doc = Document(
            source=Source(
                kind="arxiv",
                arxiv_id=meta.id,
                version=str(meta.resolved_version),
                original=ctx.spec.original,
            ),
            provenance=Provenance(
                engine=self.name,
                engine_versions={"paperdeck": __version__, "katex": "alttext"},
                created_at=datetime.now(UTC).isoformat(),
                fallbacks=[],
            ),
            meta=Meta(
                title=structure.meta_title,
                authors=structure.authors or meta.authors,
                abstract=structure.abstract or None,
                links=[MetaLink(url=meta.abs_url, kind="arxiv")]
                + ([MetaLink(url=f"https://doi.org/{meta.doi}", kind="doi")] if meta.doi else []),
            ),
            body=body,
            bibliography=bibliography,
            footnotes=footnotes,
            assets=structure.assets,
            labels=structure.labels,
            warnings=structure.warnings,
        )
        validate_document(doc, ctx.settings.limits)
        return doc
