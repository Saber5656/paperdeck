"""Turn PDF segmentation results into the shared IR."""

from __future__ import annotations

import base64
import re
from datetime import UTC, datetime
from typing import Any

from .blocks import RawBlock
from .citations import Splice, link_citations, link_structural_refs


def _text(value: str) -> Any:
    from ...ir.model import Text

    return Text(text=value)


def apply_splices(text: str, splices: list[Splice]) -> list[Any]:
    """Convert non-overlapping character ranges into typed inline nodes."""
    ordered = sorted(splices, key=lambda item: (item.start, item.end))
    output: list[Any] = []
    cursor = 0
    for splice in ordered:
        if splice.start < cursor or splice.end < splice.start or splice.end > len(text):
            raise ValueError("overlapping or out-of-range citation splice")
        if splice.start > cursor:
            output.append(_text(text[cursor : splice.start]))
        node = splice.node
        try:
            from ...ir.model import Cite, RefLink

            if hasattr(node, "bib_ids"):
                output.append(Cite(bib_ids=list(node.bib_ids), text=node.text))
            elif hasattr(node, "target_id"):
                output.append(RefLink(target_id=node.target_id, kind=node.kind, text=node.text))
            else:
                output.append(node)
        except ImportError:
            output.append(node)
        cursor = splice.end
    if cursor < len(text):
        output.append(_text(text[cursor:]))
    return output


def _warning(code: str, where: str | None = None) -> Any:
    from ...ir.model import Warning

    return Warning(code=code.split(":", 1)[0], message=code, where=where)


def assemble_pdf(
    seg: Any,
    blocks: list[RawBlock],
    eq_result: Any,
    bib_result: tuple[list[Any], dict[str, str], list[str], list[str]],
    pdfdoc: Any,
    settings: Any,
    *,
    source: Any = None,
    llm_provenance: Any = None,
    llm: Any = None,
) -> Any:
    from ...ir.model import (
        Document,
        Figure,
        Meta,
        Paragraph,
        Provenance,
        Section,
        Source,
        Table,
        Unhandled,
    )

    bibliography, numeric_index, _, bib_warnings = bib_result
    paragraph_blocks = [
        block
        for block in blocks
        if seg.roles.get(block.id) and seg.roles[block.id].role == "paragraph"
    ]
    paragraph_texts = [block.text for block in paragraph_blocks]
    paragraph_sources = {block.id: block.text for block in paragraph_blocks}
    cite_splices = link_citations(paragraph_texts, bibliography, llm)
    numbers_map: dict[tuple[str, str], str] = {}
    for _block_id, draft in eq_result.equations.items():
        numbers_map[("eq", draft.number)] = draft.anchor_id
    all_splices: list[list[Splice]] = []
    for idx, text in enumerate(paragraph_texts):
        all_splices.append(link_structural_refs([text], numbers_map)[0] + cite_splices[idx])
    body: list[Any] = []
    section_stack: list[Any] = []
    section_counters: list[int] = []
    para_idx = 0
    section_idx = 0
    figure_idx = 0
    table_idx = 0

    def add_node(node: Any) -> None:
        if getattr(node, "type", None) == "section":
            while section_stack and section_stack[-1].level >= node.level:
                section_stack.pop()
            if section_stack:
                section_stack[-1].children.append(node)
            else:
                body.append(node)
            section_stack.append(node)
        elif section_stack:
            section_stack[-1].children.append(node)
        else:
            body.append(node)

    for block in blocks:
        info = seg.roles.get(block.id)
        if info is None or info.role in {"noise", "bib_entry", "author_line", "title", "abstract"}:
            continue
        if info.role == "heading":
            level = info.level or 1
            section_counters = section_counters[: level - 1]
            while len(section_counters) < level:
                section_counters.append(0)
            section_counters[-1] += 1
            number = ".".join(str(value) for value in section_counters)
            section_idx += 1
            sid = f"sec-{section_idx}"
            add_node(
                Section(
                    id=sid,
                    level=min(level, 6),
                    number=number,
                    title=[_text(block.text)],
                    children=[],
                )
            )
            numbers_map[("sec", number)] = sid
        elif info.role == "paragraph":
            pid = f"para-{para_idx + 1}"
            add_node(Paragraph(id=pid, content=apply_splices(block.text, all_splices[para_idx])))
            para_idx += 1
        elif info.role == "display_equation" and block.id in eq_result.equations:
            draft = eq_result.equations[block.id]
            from ...ir.model import Equation

            add_node(
                Equation(
                    id=draft.anchor_id,
                    number=draft.number,
                    content_kind="image",
                    latex=draft.latex,
                    asset_id=draft.asset_id,
                    latex_verified=False,
                    confidence=draft.confidence,
                )
            )
            numbers_map[("eq", draft.number)] = draft.anchor_id
        elif info.role == "display_equation":
            add_node(Unhandled(id=f"unhandled-{block.id}", text=block.text))
        elif info.role == "figure_caption":
            figure_idx += 1
            fid = f"fig-{figure_idx}"
            asset_id = _crop_region(pdfdoc, block, blocks, eq_result, settings, "figure", fid)
            caption = [_text(block.text)]
            add_node(Figure(id=fid, number=info.number_text, asset_id=asset_id, caption=caption))
            if info.number_text:
                numbers_map[("fig", info.number_text.strip("()"))] = fid
        elif info.role == "table_caption":
            table_idx += 1
            tid = f"tab-{table_idx}"
            asset_id = _crop_region(pdfdoc, block, blocks, eq_result, settings, "table", tid)
            add_node(
                Table(
                    id=tid,
                    number=info.number_text,
                    content_kind="image",
                    asset_id=asset_id,
                    caption=[_text(block.text)],
                )
            )
            if info.number_text:
                numbers_map[("tab", info.number_text.strip("()"))] = tid
    # Resolve structural references after node anchors are known.
    source_indices = {block.id: i for i, block in enumerate(paragraph_blocks)}

    def resolve_nodes(nodes: list[Any]) -> list[Any]:
        resolved: list[Any] = []
        for item in nodes:
            if getattr(item, "type", None) == "paragraph":
                raw = paragraph_sources.get(item.id, "")
                structural = link_structural_refs([raw], numbers_map)[0]
                source_index = source_indices.get(item.id, -1)
                cites = cite_splices[source_index] if source_index >= 0 else []
                resolved.append(
                    Paragraph(id=item.id, content=apply_splices(raw, structural + cites))
                )
            elif getattr(item, "type", None) == "section":
                resolved.append(
                    Section(
                        id=item.id,
                        level=item.level,
                        number=item.number,
                        title=item.title,
                        children=resolve_nodes(item.children),
                    )
                )
            else:
                resolved.append(item)
        return resolved

    body = resolve_nodes(body)
    titles = [
        block.text
        for block in blocks
        if seg.roles.get(block.id) and seg.roles[block.id].role == "title"
    ]
    title = titles[0] if titles else str(getattr(pdfdoc, "metadata_title", ""))
    if not title:
        title = "PDF document"
    authors: list[str] = []
    for block in blocks:
        if seg.roles.get(block.id) and seg.roles[block.id].role == "author_line":
            authors.extend(
                item.strip()
                for item in re.split(r",|;|\band\b", block.text, flags=re.I)
                if item.strip()
            )
    abstract_blocks: list[Any] = [
        Paragraph(id=f"para-abstract-{i}", content=[_text(block.text)])
        for i, block in enumerate(blocks)
        if seg.roles.get(block.id) and seg.roles[block.id].role == "abstract"
    ]
    source_obj = source or Source(kind="local", original=str(getattr(pdfdoc, "path", "paper.pdf")))
    prov = Provenance(
        engine="pdf",
        engine_versions={"paperdeck": "0.1.0"},
        created_at=datetime.now(UTC).isoformat(),
        fallbacks=[],
        llm=llm_provenance,
    )
    warnings = [
        _warning(item)
        for item in list(getattr(seg, "warnings", []))
        + list(getattr(eq_result, "warnings", []))
        + bib_warnings
    ]
    return Document(
        source=source_obj,
        provenance=prov,
        meta=Meta(
            title=[_text(title)], authors=authors, abstract=abstract_blocks or None, links=[]
        ),
        body=body,
        bibliography=bibliography,
        assets=eq_result.assets,
        warnings=warnings,
    )


def _walk(node: Any) -> list[Any]:
    result = [node]
    for child in getattr(node, "children", ()):
        result.extend(_walk(child))
    return result


def _crop_region(
    pdfdoc: Any,
    caption: RawBlock,
    blocks: list[RawBlock],
    result: Any,
    settings: Any,
    kind: str,
    anchor: str,
) -> str | None:
    page_blocks = [item for item in blocks if item.page == caption.page and item.id != caption.id]
    page_width, page_height = pdfdoc.page_size(caption.page)
    above = [item for item in page_blocks if item.bbox[3] <= caption.bbox[1]]
    bottom = max((item.bbox[3] for item in above), default=0.0)
    bbox = (0.0, bottom, page_width, caption.bbox[1])
    if bbox[2] - bbox[0] < 40 or bbox[3] - bbox[1] < 40:
        result.warnings.append(f"pdf-figure-region-missing:{caption.id}")
        asset_id = f"asset-{kind}-{anchor}"
        from .extract import encode_png_rgb

        result.assets[asset_id] = _asset(
            asset_id, encode_png_rgb(1, 1, b"\xff\xff\xff"), caption.page
        )
        return asset_id
    try:
        data = pdfdoc.bitmap(caption.page, 2.0).crop_png(bbox, pad_pt=0)
    except Exception:
        result.warnings.append(f"pdf-figure-region-missing:{caption.id}")
        asset_id = f"asset-{kind}-{anchor}"
        from .extract import encode_png_rgb

        result.assets[asset_id] = _asset(
            asset_id, encode_png_rgb(1, 1, b"\xff\xff\xff"), caption.page
        )
        return asset_id
    asset_id = f"asset-{kind}-{anchor}"
    result.assets[asset_id] = _asset(asset_id, data, caption.page)
    return asset_id


def _asset(asset_id: str, data: bytes, page: int) -> Any:
    from ...ir.model import Asset, AssetOrigin

    return Asset(
        id=asset_id,
        mime="image/png",
        data_b64=base64.b64encode(data).decode("ascii"),
        origin=AssetOrigin(engine="pdf", page=page),
    )


__all__ = ["apply_splices", "assemble_pdf"]
