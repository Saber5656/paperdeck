"""Convert the structural part of LaTeXML HTML into IR blocks."""

from __future__ import annotations

import base64
import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, cast

from bs4 import BeautifulSoup, Tag
from bs4.element import NavigableString

from paperdeck.input.arxiv import HtmlArtifact
from paperdeck.ir.anchors import AnchorAllocator
from paperdeck.ir.model import (
    Asset,
    AssetOrigin,
    Cell,
    CodeBlock,
    Figure,
    ListBlock,
    Paragraph,
    Quote,
    Section,
    Table,
    Text,
    Unhandled,
    Warning,
)


@dataclass
class StructureResult:
    meta_title: list[Any]
    authors: list[str]
    abstract: list[Any]
    body: list[Any]
    bibliography: list[Any]
    footnotes: list[Any]
    assets: dict[str, Asset]
    source_id_map: dict[str, str]
    labels: dict[str, str]
    warnings: list[Warning]
    elements: dict[str, Tag] = field(default_factory=dict)
    soup: BeautifulSoup | None = None
    artifact: HtmlArtifact | None = None


def _classes(tag: Tag) -> set[str]:
    value = tag.get("class")
    return {str(item) for item in value} if isinstance(value, (list, tuple)) else set()


def _text(tag: Tag | None) -> str:
    return " ".join(tag.get_text("", strip=False).split()) if tag else ""


def _text_without(tag: Tag, excluded_classes: set[str]) -> str:
    """Flatten text while omitting LaTeXML metadata descendants."""

    parts: list[str] = []

    def visit(node: Tag | NavigableString) -> None:
        if isinstance(node, NavigableString):
            parts.append(str(node))
            return
        if _classes(node) & excluded_classes:
            return
        for child in node.children:
            if isinstance(child, (Tag, NavigableString)):
                visit(child)

    visit(tag)
    return " ".join("".join(parts).split())


def _tag_number(tag: Tag) -> str | None:
    number_tag = tag.select_one(".ltx_tag")
    value = _text(number_tag)
    value = value.strip("()[]")
    if number_tag is not None:
        classes = _classes(number_tag)
        if "ltx_tag_figure" in classes or "ltx_tag_table" in classes:
            value = re.sub(r"^(?:Figure|Table)\s+", "", value, flags=re.IGNORECASE)
            value = value.rstrip(":").strip()
    return value or None


def _block_id(tag: Tag, kind: str, alloc: AnchorAllocator, result: StructureResult) -> str:
    anchor = alloc.next(kind)
    raw_id = tag.get("id")
    html_id = str(raw_id) if isinstance(raw_id, str) else ""
    if html_id:
        if html_id in result.source_id_map:
            result.warnings.append(
                Warning(code="html-id-duplicate", message="duplicate HTML id", where=html_id)
            )
        else:
            result.source_id_map[html_id] = anchor
            result.labels[html_id] = anchor
    result.elements[anchor] = tag
    return anchor


def _asset(tag: Tag, artifact: HtmlArtifact, result: StructureResult) -> str | None:
    image = tag.find("img")
    source = str(image.get("src") or "") if image else ""
    stored = artifact.asset_map.get(source)
    if not stored:
        result.warnings.append(
            Warning(
                code="figure-image-missing",
                message="figure image was not fetched",
                where=source or None,
            )
        )
        return None
    path = artifact.page_path.parent / "assets" / stored
    try:
        data = path.read_bytes()
    except OSError:
        result.warnings.append(
            Warning(
                code="figure-image-missing", message="cached figure image is missing", where=source
            )
        )
        return None
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        mime = cast(Any, "image/png")
    elif data.startswith(b"\xff\xd8\xff"):
        mime = cast(Any, "image/jpeg")
    elif data.lstrip().startswith(b"<svg") or b"<svg" in data[:4096]:
        mime = cast(Any, "image/svg+xml")
        cleaned = re.sub(rb"<script\b[^>]*>.*?</script\s*>", b"", data, flags=re.I | re.S)
        if cleaned != data:
            result.warnings.append(
                Warning(
                    code="svg-script-stripped",
                    message="SVG script content was removed",
                    where=source,
                )
            )
            data = cleaned
    else:
        result.warnings.append(
            Warning(
                code="figure-image-missing", message="cached asset is not an image", where=source
            )
        )
        return None
    asset_id = "asset-" + hashlib.sha1(stored.encode(), usedforsecurity=False).hexdigest()
    result.assets[asset_id] = Asset(
        id=asset_id,
        mime=mime,
        data_b64=base64.b64encode(data).decode("ascii"),
        origin=AssetOrigin(engine="arxiv-html", source_path=stored),
    )
    return asset_id


def _table(tag: Tag, alloc: AnchorAllocator, result: StructureResult) -> Table:
    anchor = _block_id(tag, "tab", alloc, result)
    rows: list[list[Cell]] = []
    table = tag.select_one("table") or tag
    for tr in table.find_all("tr"):
        cells: list[Cell] = []
        for cell in tr.find_all(["th", "td"], recursive=False):
            cells.append(
                Cell(
                    content=[Text(text=_text(cell))],
                    header=cell.name == "th",
                    colspan=int(str(cell.get("colspan") or 1)),
                    rowspan=int(str(cell.get("rowspan") or 1)),
                )
            )
        if cells:
            rows.append(cells)
    return Table(
        id=anchor,
        number=_tag_number(tag),
        caption=[Text(text=_text(tag.select_one(".ltx_caption")))],
        content_kind="grid",
        rows=rows,
    )


def _children(
    container: Tag, alloc: AnchorAllocator, result: StructureResult, limits: Any
) -> list[Any]:
    blocks: list[Any] = []
    document_container = "ltx_document" in _classes(container)
    after_title = not document_container
    for child in container.find_all(recursive=False):
        classes = _classes(child)
        if document_container and "ltx_title_document" in classes:
            after_title = True
            continue
        if document_container and not after_title:
            continue
        if classes & {
            "ltx_align_bottom",
            "ltx_TOC",
            "ltx_list_toc",
            "ltx_toc_toc",
            "ltx_logical-block",
            "ltx_pagination",
        }:
            continue
        if "ltx_title" in classes or "ltx_tag" in classes:
            continue
        if child.name == "section" and classes & {
            "ltx_section",
            "ltx_subsection",
            "ltx_subsubsection",
            "ltx_appendix",
        }:
            blocks.append(_section(child, alloc, result, limits))
        elif "ltx_para" in classes:
            para = child.select_one(":scope > .ltx_p") or child.select_one(".ltx_p") or child
            if not _text(para):
                continue
            anchor = _block_id(child, "para", alloc, result)
            result.elements[anchor] = para
            blocks.append(Paragraph(id=anchor, content=[Text(text=_text(para))]))
        elif "ltx_p" in classes:
            anchor = _block_id(child, "para", alloc, result)
            blocks.append(Paragraph(id=anchor, content=[Text(text=_text(child))]))
        elif child.name == "figure" and "ltx_figure" in classes:
            anchor = _block_id(child, "fig", alloc, result)
            aid = _asset(child, result.artifact, result) if result.artifact else None
            image = child.find("img")
            alt = str(image.get("alt")) if image is not None and image.get("alt") else ""
            blocks.append(
                Figure(
                    id=anchor,
                    number=_tag_number(child),
                    asset_id=aid,
                    caption=[Text(text=_text(child.select_one(".ltx_caption")))],
                    alt_text=alt or None,
                )
            )
        elif (child.name == "figure" and "ltx_table" in classes) or (
            child.name == "table" and "ltx_tabular" in classes
        ):
            table = child.select_one("table") or child
            if table.select_one("table table"):
                anchor = _block_id(child, "tab", alloc, result)
                result.warnings.append(
                    Warning(
                        code="nested-tabular-unhandled",
                        message="nested tabular content was not represented as a grid",
                        where=anchor,
                    )
                )
                blocks.append(Unhandled(id=anchor, text=_text(child)))
            else:
                blocks.append(_table(child, alloc, result))
        elif "ltx_itemize" in classes or "ltx_enumerate" in classes:
            anchor = _block_id(child, "para", alloc, result)
            items: list[list[Any]] = [
                [Paragraph(id=alloc.next("para"), content=[Text(text=_text(item))])]
                for item in child.select(":scope > .ltx_item")
            ]
            blocks.append(ListBlock(id=anchor, ordered="ltx_enumerate" in classes, items=items))
        elif "ltx_quote" in classes:
            anchor = _block_id(child, "para", alloc, result)
            blocks.append(
                Quote(
                    id=anchor,
                    content=[Paragraph(id=alloc.next("para"), content=[Text(text=_text(child))])],
                )
            )
        elif "ltx_verbatim" in classes:
            anchor = _block_id(child, "para", alloc, result)
            blocks.append(CodeBlock(id=anchor, text=child.get_text("", strip=False)))
        elif any(cls.startswith("ltx_equation") for cls in classes):
            rows = child.select(".ltx_equation") if "ltx_equationgroup" in classes else [child]
            for row in rows:
                anchor = _block_id(row, "eq", alloc, result)
                blocks.append(Unhandled(id=anchor, text=_text(row)))
        elif classes & {
            "ltx_page_content",
            "ltx_page_column",
            "ltx_document",
            "ltx_document_body",
            "ltx_body",
            "ltx_float",
            "ltx_keywords",
        }:
            blocks.extend(_children(child, alloc, result, limits))
        elif classes & {
            "ltx_authors",
            "ltx_abstract",
            "ltx_bibliography",
            "ltx_title_document",
            "ltx_creator",
            "ltx_author_before",
            "ltx_author_notes",
            "ltx_contact",
        }:
            continue
        elif any(cls.startswith("ltx_") for cls in classes) and child.name not in {
            "header",
            "footer",
        }:
            anchor = _block_id(child, "para", alloc, result)
            warning_code = "ltx-class-unhandled:" + ",".join(sorted(classes))
            if not any(item.code == warning_code for item in result.warnings):
                result.warnings.append(
                    Warning(
                        code=warning_code,
                        message="unknown LaTeXML class",
                        where=anchor,
                    )
                )
            blocks.append(Unhandled(id=anchor, text=_text(child)))
        elif child.find(["section", "figure", "table"], recursive=False):
            blocks.extend(_children(child, alloc, result, limits))
    return blocks


def _section(tag: Tag, alloc: AnchorAllocator, result: StructureResult, limits: Any) -> Section:
    classes = _classes(tag)
    level = 3 if "ltx_subsubsection" in classes else 2 if "ltx_subsection" in classes else 1
    anchor = _block_id(tag, "sec", alloc, result)
    title = tag.select_one(":scope > .ltx_title") or tag.select_one(".ltx_title")
    title_parts: list[str] = []
    if title:
        for item in title.contents:
            if isinstance(item, Tag):
                if "ltx_tag" not in _classes(item):
                    title_parts.append(item.get_text(" ", strip=True))
            else:
                title_parts.append(str(item).strip())
    title_text = " ".join(item for item in title_parts if item)
    number = _tag_number(title) if title else None
    children = _children(tag, alloc, result, limits)
    return Section(
        id=anchor, level=level, number=number, title=[Text(text=title_text)], children=children
    )


def parse_structure(
    soup: BeautifulSoup, artifact: HtmlArtifact, alloc: AnchorAllocator, limits: Any
) -> StructureResult:
    result = StructureResult([], [], [], [], [], [], {}, {}, {}, [], soup=soup, artifact=artifact)
    title = soup.select_one(".ltx_title_document")
    result.meta_title = [Text(text=_text(title))] if title else []
    result.authors = [
        _text_without(item, {"ltx_note", "ltx_author_notes"})
        for item in soup.select(".ltx_creator .ltx_personname")
    ]
    abstract = soup.select_one(".ltx_abstract")
    if abstract:
        paragraphs = abstract.select(".ltx_p")
        abstract_text = (
            " ".join(_text(item) for item in paragraphs) if paragraphs else _text(abstract)
        )
        result.abstract = [Paragraph(id=alloc.next("para"), content=[Text(text=abstract_text)])]
    root = soup.select_one(".ltx_page_main") or soup.body or soup
    result.body = _children(root, alloc, result, limits)
    for item in soup.select(".ltx_bibliography .ltx_bibitem"):
        anchor = _block_id(item, "bib", alloc, result)
        result.bibliography.append((anchor, item))
    for item in soup.select(".ltx_note:not(.ltx_note_frontmatter):not(.ltx_role_footnotemark)"):
        anchor = _block_id(item, "fn", alloc, result)
        result.footnotes.append((anchor, item))
    return result
