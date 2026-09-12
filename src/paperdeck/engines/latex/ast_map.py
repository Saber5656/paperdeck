"""Map Pandoc JSON AST nodes to the paperdeck IR skeleton."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from paperdeck.ir.anchors import AnchorAllocator
from paperdeck.ir.model import (
    Block,
    Cell,
    Cite,
    Code,
    CodeBlock,
    Emph,
    Equation,
    ExtLink,
    Figure,
    FootnoteDef,
    FootnoteRef,
    Inline,
    LineBreak,
    ListBlock,
    Math,
    Paragraph,
    Quote,
    Section,
    Strong,
    Sub,
    Sup,
    Table,
    Text,
    Unhandled,
    Warning,
)

_START = "\ue000"
_END = "\ue001"


@dataclass(frozen=True)
class RawSpan:
    placeholder_id: str
    tex: str
    context: str


@dataclass
class MappedDoc:
    body: list[Block]
    meta_title: list[Inline]
    meta_authors: list[str]
    meta_abstract: list[Block] | None
    footnotes: list[FootnoteDef]
    raw_spans: list[RawSpan]
    env_map: dict[str, str]
    image_targets: dict[str, str]
    source_ids: dict[str, str]
    unnumbered_sections: set[str]
    warnings: list[Warning] = field(default_factory=list)
    labels: dict[str, str] = field(default_factory=dict)
    source_labels: set[str] = field(default_factory=set)


def _plain(node: Any) -> str:
    result: list[str] = []
    stack: list[Any] = [node]
    while stack:
        current = stack.pop()
        if isinstance(current, str):
            result.append(current)
        elif isinstance(current, list):
            stack.extend(reversed(current))
        elif isinstance(current, dict):
            typ, content = current.get("t"), current.get("c")
            if typ in {"Space", "SoftBreak", "LineBreak"}:
                result.append(" ")
            elif typ in {"Str", "Code"} or isinstance(content, list):
                stack.append(content)
    return "".join(result)


def _meta_inlines(value: Any, alloc: AnchorAllocator) -> list[Inline]:
    if isinstance(value, dict) and value.get("t") == "MetaInlines":
        return _inlines(value.get("c", []), alloc, [], [], "inline")
    if isinstance(value, dict) and value.get("t") == "MetaString":
        return [Text(text=str(value.get("c", "")))]
    return []


def _inlines(
    nodes: list[Any],
    alloc: AnchorAllocator,
    raw_spans: list[RawSpan],
    warnings: list[Warning],
    context: str,
    depth: int = 0,
    mapped: MappedDoc | None = None,
) -> list[Inline]:
    result: list[Inline] = []
    for node in nodes:
        if not isinstance(node, dict):
            result.append(Text(text=str(node)))
            continue
        typ, content = node.get("t"), node.get("c")
        nested = content if isinstance(content, list) else []
        if depth >= 200 and nested:
            warnings.append(
                Warning(code="inline-depth-cap", message="nested inline content flattened")
            )
            result.append(Text(text=_plain(nested)))
        elif typ == "Str":
            result.append(Text(text=str(content or "")))
        elif typ == "Space" or typ == "SoftBreak":
            result.append(Text(text=" "))
        elif typ == "LineBreak":
            result.append(LineBreak())
        elif typ == "Emph":
            result.append(
                Emph(
                    content=_inlines(nested, alloc, raw_spans, warnings, context, depth + 1, mapped)
                )
            )
        elif typ == "Strong":
            result.append(
                Strong(
                    content=_inlines(nested, alloc, raw_spans, warnings, context, depth + 1, mapped)
                )
            )
        elif typ == "Superscript":
            result.append(
                Sup(
                    content=_inlines(nested, alloc, raw_spans, warnings, context, depth + 1, mapped)
                )
            )
        elif typ == "Subscript":
            result.append(
                Sub(
                    content=_inlines(nested, alloc, raw_spans, warnings, context, depth + 1, mapped)
                )
            )
        elif typ == "Code":
            result.append(
                Code(
                    text=str(
                        content[1]
                        if isinstance(content, list) and len(content) > 1
                        else content or ""
                    )
                )
            )
        elif typ == "Math":
            if isinstance(content, list) and len(content) > 1:
                result.append(Math(latex=str(content[1])))
            else:
                result.append(Text(text=_plain(node)))
        elif typ == "Link":
            attributes = content[0] if isinstance(content, list) and content else []
            target = (
                content[2][0]
                if isinstance(content, list) and len(content) > 2 and content[2]
                else ""
            )
            reference = ""
            if isinstance(attributes, list) and len(attributes) > 2:
                key_values = attributes[2]
                if isinstance(key_values, list):
                    for pair in key_values:
                        if isinstance(pair, list) and len(pair) > 1 and pair[0] == "reference":
                            reference = str(pair[1])
                            break
            if str(target).startswith("#") and reference:
                placeholder = f"{_START}{len(raw_spans)}{_END}"
                raw_spans.append(RawSpan(placeholder, rf"\ref{{{reference}}}", context))
                result.append(Text(text=placeholder))
                continue
            child = _inlines(
                content[1] if isinstance(content, list) and len(content) > 1 else [],
                alloc,
                raw_spans,
                warnings,
                context,
                depth + 1,
                mapped,
            )
            if urlparse(str(target)).scheme.lower() not in {"https", "http", "mailto"}:
                warnings.append(
                    Warning(
                        code="invalid-link-scheme",
                        message="external link dropped",
                        where=str(target),
                    )
                )
                result.extend(child)
            else:
                result.append(ExtLink(url=str(target), content=child))
        elif typ == "Cite":
            citations = content[0] if isinstance(content, list) and content else []
            keys = [str(item.get("citationId", "")) for item in citations if isinstance(item, dict)]
            shown = _plain(content[1] if isinstance(content, list) and len(content) > 1 else [])
            result.append(Cite(bib_ids=keys, text=shown))
        elif typ == "Note":
            if mapped is None:
                result.append(Text(text=_plain(content)))
            else:
                foot_id = alloc.next("fn")
                number = str(len(mapped.footnotes) + 1)
                body = content if isinstance(content, list) else []
                mapped.footnotes.append(
                    FootnoteDef(id=foot_id, number=number, content=_map_blocks(body, alloc, mapped))
                )
                result.append(FootnoteRef(target_id=foot_id, number=number))
        elif (
            typ == "RawInline"
            and isinstance(content, list)
            and len(content) > 1
            and content[0] in {"tex", "latex"}
        ):
            placeholder = f"{_START}{len(raw_spans)}{_END}"
            raw_spans.append(RawSpan(placeholder, str(content[1]), context))
            result.append(Text(text=placeholder))
        elif typ == "RawInline":
            warnings.append(
                Warning(code="raw-inline-dropped", message="non-LaTeX raw inline dropped")
            )
        elif typ == "Image":
            target = (
                content[2][0]
                if isinstance(content, list) and len(content) > 2 and content[2]
                else ""
            )
            result.append(
                Text(
                    text=_plain(
                        content[1] if isinstance(content, list) and len(content) > 1 else []
                    )
                )
            )
            warnings.append(
                Warning(code="inline-image-deferred", message=f"image target deferred: {target}")
            )
        elif typ in {"Span", "Div"}:
            result.extend(
                _inlines(
                    nested[1] if typ == "Span" and len(nested) > 1 else nested,
                    alloc,
                    raw_spans,
                    warnings,
                    context,
                    depth + 1,
                    mapped,
                )
            )
        else:
            warnings.append(
                Warning(
                    code=f"pandoc-node-unhandled:{typ}", message=f"unhandled inline node: {typ}"
                )
            )
            result.append(Text(text=_plain(node)))
    return result


def _map_blocks(
    nodes: list[Any],
    alloc: AnchorAllocator,
    mapped: MappedDoc,
    display_envs: list[str] | None = None,
) -> list[Block]:
    result: list[Block] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        typ, content = node.get("t"), node.get("c")
        if typ == "Header" and isinstance(content, list) and len(content) >= 3:
            try:
                level = int(content[0])
            except (TypeError, ValueError):
                mapped.warnings.append(
                    Warning(code="pandoc-node-malformed:Header", message="invalid header level")
                )
                continue
            attr = content[1] if isinstance(content[1], list) else []
            source_id = str(attr[0]) if attr else ""
            block_id = alloc.next("sec")
            title = _inlines(
                content[2], alloc, mapped.raw_spans, mapped.warnings, "inline", mapped=mapped
            )
            section = Section(id=block_id, level=level, title=title, children=[])
            if source_id:
                mapped.source_ids[source_id] = block_id
            classes = attr[1] if len(attr) > 1 and isinstance(attr[1], list) else []
            if "unnumbered" in classes or "unnumbered" in source_id:
                mapped.unnumbered_sections.add(block_id)
            result.append(section)
        elif typ in {"Para", "Plain"}:
            inlines = content if isinstance(content, list) else []
            pending: list[Any] = []
            for inline in inlines:
                if isinstance(inline, dict) and inline.get("t") == "Image":
                    if pending:
                        result.append(
                            Paragraph(
                                id=alloc.next("para"),
                                content=_inlines(
                                    pending,
                                    alloc,
                                    mapped.raw_spans,
                                    mapped.warnings,
                                    "inline",
                                    mapped=mapped,
                                ),
                            )
                        )
                        pending = []
                    image_content = inline.get("c", [])
                    target = (
                        image_content[2][0]
                        if isinstance(image_content, list)
                        and len(image_content) > 2
                        and image_content[2]
                        else ""
                    )
                    figure_id = alloc.next("fig")
                    mapped.image_targets[figure_id] = str(target)
                    caption = (
                        image_content[1]
                        if isinstance(image_content, list) and len(image_content) > 1
                        else []
                    )
                    result.append(
                        Figure(
                            id=figure_id,
                            caption=_inlines(
                                caption,
                                alloc,
                                mapped.raw_spans,
                                mapped.warnings,
                                "inline",
                                mapped=mapped,
                            ),
                        )
                    )
                elif (
                    isinstance(inline, dict)
                    and inline.get("t") == "Math"
                    and isinstance(inline.get("c"), list)
                    and isinstance(inline["c"][0], dict)
                    and inline["c"][0].get("t") == "DisplayMath"
                ):
                    if pending:
                        result.append(
                            Paragraph(
                                id=alloc.next("para"),
                                content=_inlines(
                                    pending,
                                    alloc,
                                    mapped.raw_spans,
                                    mapped.warnings,
                                    "inline",
                                    mapped=mapped,
                                ),
                            )
                        )
                        pending = []
                    eq_id = alloc.next("eq")
                    latex = str(inline["c"][1])
                    env_match = re.search(r"\\begin\{([^}]+)\}", latex)
                    source_env = display_envs.pop(0) if display_envs else None
                    env = env_match.group(1) if env_match else (source_env or "display")
                    if env == "aligned" and source_env and source_env != "display":
                        env = source_env
                    mapped.env_map[eq_id] = env
                    result.append(
                        Equation(id=eq_id, content_kind="latex", latex=latex, latex_verified=True)
                    )
                else:
                    pending.append(inline)
            if pending:
                result.append(
                    Paragraph(
                        id=alloc.next("para"),
                        content=_inlines(
                            pending,
                            alloc,
                            mapped.raw_spans,
                            mapped.warnings,
                            "inline",
                            mapped=mapped,
                        ),
                    )
                )
        elif typ == "CodeBlock":
            text = content[1] if isinstance(content, list) and len(content) > 1 else ""
            lang = (
                content[0][1][0]
                if isinstance(content, list)
                and content
                and isinstance(content[0], list)
                and len(content[0]) > 1
                and content[0][1]
                else None
            )
            result.append(CodeBlock(id=alloc.next("para"), text=str(text), language=lang))
        elif typ == "BlockQuote":
            result.append(
                Quote(
                    id=alloc.next("para"),
                    content=_map_blocks(content or [], alloc, mapped, display_envs),
                )
            )
        elif typ in {"BulletList", "OrderedList"}:
            items = (
                content[1]
                if typ == "OrderedList" and isinstance(content, list) and len(content) > 1
                else content
            )
            result.append(
                ListBlock(
                    id=alloc.next("para"),
                    ordered=typ == "OrderedList",
                    items=[
                        _map_blocks(item, alloc, mapped, display_envs) for item in (items or [])
                    ],
                )
            )
        elif typ == "Table":
            result.append(_table(content, alloc, mapped))
        elif typ == "Figure":
            result.append(_figure(content, alloc, mapped))
        elif (
            typ == "RawBlock"
            and isinstance(content, list)
            and len(content) > 1
            and content[0] in {"tex", "latex"}
        ):
            raw = str(content[1])
            environment = re.match(r"\s*\\begin\{([A-Za-z]+)(\*)?\}", raw)
            environment_name = (
                environment.group(1) + (environment.group(2) or "") if environment else ""
            )
            if environment and environment_name.rstrip("*") in {
                "equation",
                "align",
                "gather",
                "eqnarray",
                "multline",
                "flalign",
                "alignat",
            }:
                equation_id = alloc.next("eq")
                mapped.env_map[equation_id] = environment_name
                result.append(
                    Equation(
                        id=equation_id,
                        content_kind="latex",
                        latex=raw,
                        latex_verified=True,
                    )
                )
                continue
            placeholder = f"{_START}{len(mapped.raw_spans)}{_END}"
            mapped.raw_spans.append(RawSpan(placeholder, raw, "block"))
            result.append(Paragraph(id=alloc.next("para"), content=[Text(text=placeholder)]))
        elif typ == "RawBlock":
            mapped.warnings.append(
                Warning(code="raw-block-dropped", message="non-LaTeX raw block dropped")
            )
            result.append(Unhandled(id=alloc.next("para"), text="unsupported raw block"))
        elif typ == "Div":
            attr = content[0] if isinstance(content, list) and content else []
            classes = attr[1] if isinstance(attr, list) and len(attr) > 1 else []
            children = _map_blocks(
                content[1] if isinstance(content, list) and len(content) > 1 else [],
                alloc,
                mapped,
                display_envs,
            )
            if isinstance(attr, list) and attr and attr[0] and len(children) == 1:
                child = children[0]
                if isinstance(child, Table):
                    mapped.source_ids[str(attr[0])] = child.id
            if "abstract" in classes:
                mapped.meta_abstract = children
            else:
                result.extend(children)
        else:
            mapped.warnings.append(
                Warning(code=f"pandoc-node-unhandled:{typ}", message=f"unhandled block node: {typ}")
            )
            result.append(Unhandled(id=alloc.next("para"), text=_plain(node)))
    return result


def _figure(content: Any, alloc: AnchorAllocator, mapped: MappedDoc) -> Figure:
    attr = content[0] if isinstance(content, list) and content else []
    caption_value = content[1] if isinstance(content, list) and len(content) > 1 else []
    caption_nodes = (
        caption_value[1] if isinstance(caption_value, list) and len(caption_value) > 1 else []
    )
    caption_nodes = _caption_nodes(caption_nodes)
    target = ""
    image_nodes = content[2] if isinstance(content, list) and len(content) > 2 else []
    for image_node in image_nodes if isinstance(image_nodes, list) else []:
        if isinstance(image_node, dict) and image_node.get("t") == "Plain":
            for inline in image_node.get("c", []):
                if isinstance(inline, dict) and inline.get("t") == "Image":
                    image_content = inline.get("c", [])
                    if (
                        isinstance(image_content, list)
                        and len(image_content) > 2
                        and image_content[2]
                    ):
                        target = str(image_content[2][0])
    block_id = alloc.next("fig")
    if isinstance(attr, list) and attr and attr[0]:
        mapped.source_ids[str(attr[0])] = block_id
    mapped.image_targets[block_id] = str(target)
    return Figure(
        id=block_id,
        caption=_inlines(
            caption_nodes,
            alloc,
            mapped.raw_spans,
            mapped.warnings,
            "inline",
            mapped=mapped,
        ),
    )


def _table(content: Any, alloc: AnchorAllocator, mapped: MappedDoc) -> Table:
    attr = content[0] if isinstance(content, list) and content else []
    caption = content[1] if isinstance(content, list) and len(content) > 1 else []
    caption = _caption_nodes(
        caption[1] if isinstance(caption, list) and len(caption) > 1 else caption
    )
    rows: list[list[Cell]] = []
    # Pandoc 1.23 table shape: attr, caption, colspecs, head, bodies, foot.
    head = content[3] if isinstance(content, list) and len(content) > 3 else []
    if isinstance(head, list) and len(head) > 1:
        rows.extend(_table_rows(head[1], alloc, mapped, True))
    bodies = content[4] if isinstance(content, list) and len(content) > 4 else []
    if isinstance(bodies, list):
        for body in bodies:
            if isinstance(body, list) and len(body) > 3:
                body_rows = body[3]
                if (
                    isinstance(body_rows, list)
                    and body_rows
                    and isinstance(body_rows[0], list)
                    and body_rows[0]
                    and isinstance(body_rows[0][0], list)
                    and body_rows[0][0]
                    and isinstance(body_rows[0][0][0], list)
                    and len(body_rows[0][0][0]) >= 5
                ):
                    body_rows = body_rows[0]
                rows.extend(_table_rows(body_rows, alloc, mapped, False))
    block_id = alloc.next("tab")
    if isinstance(attr, list) and attr and attr[0]:
        mapped.source_ids[str(attr[0])] = block_id
    return Table(
        id=block_id,
        caption=_inlines(
            caption, alloc, mapped.raw_spans, mapped.warnings, "inline", mapped=mapped
        ),
        content_kind="grid",
        rows=rows,
    )


def _table_rows(
    value: Any, alloc: AnchorAllocator, mapped: MappedDoc, header: bool
) -> list[list[Cell]]:
    rows: list[list[Cell]] = []
    for row in value if isinstance(value, list) else []:
        if (
            isinstance(row, list)
            and len(row) > 1
            and isinstance(row[1], list)
            and row[1]
            and isinstance(row[1][0], list)
            and len(row[1][0]) >= 5
        ):
            row = row[1]
        cells: list[Cell] = []
        for cell in row if isinstance(row, list) else []:
            if not isinstance(cell, list) or len(cell) < 5:
                continue
            blocks = cell[4]
            inlines: list[Inline] = []
            for block in blocks if isinstance(blocks, list) else []:
                if isinstance(block, dict) and block.get("t") in {"Plain", "Para"}:
                    inlines.extend(
                        _inlines(
                            block.get("c", []),
                            alloc,
                            mapped.raw_spans,
                            mapped.warnings,
                            "inline",
                            mapped=mapped,
                        )
                    )
            try:
                colspan, rowspan = int(cell[2]), int(cell[3])
            except (TypeError, ValueError):
                mapped.warnings.append(
                    Warning(code="pandoc-node-malformed:Cell", message="invalid table span")
                )
                continue
            cells.append(Cell(content=inlines, header=header, colspan=colspan, rowspan=rowspan))
        if cells:
            rows.append(cells)
    return rows


def _caption_nodes(value: Any) -> list[Any]:
    if not isinstance(value, list):
        return []
    nodes: list[Any] = []
    for item in value:
        if isinstance(item, dict) and item.get("t") in {"Plain", "Para"}:
            nodes.extend(item.get("c", []))
        else:
            nodes.append(item)
    return nodes


def _display_envs(source_text: str) -> list[str]:
    """Classify display math that Pandoc 3.1.x emits without its environment."""
    pattern = re.compile(
        r"\\begin\{(equation|align|gather|eqnarray|multline|flalign|alignat)(\*)?\}"
        r"|\\\[|\$\$"
    )
    result: list[str] = []
    for match in pattern.finditer(source_text):
        if match.group(1):
            result.append(match.group(1) + (match.group(2) or ""))
        else:
            result.append("display")
    return result


def map_ast(
    ast: dict[str, Any], alloc: AnchorAllocator, source_text: str | None = None
) -> MappedDoc:
    """Map a Pandoc AST while retaining raw-TeX and source side maps."""
    mapped = MappedDoc([], [], [], None, [], [], {}, {}, {}, set())
    blocks = ast.get("blocks", [])
    display_envs = _display_envs(source_text) if source_text is not None else []
    mapped.body = _nest_sections(
        _map_blocks(blocks if isinstance(blocks, list) else [], alloc, mapped, display_envs)
    )
    meta = ast.get("meta", {})
    if isinstance(meta, dict):
        mapped.meta_title = _meta_inlines(meta.get("title"), alloc)
        authors = meta.get("author", {})
        if isinstance(authors, dict) and authors.get("t") == "MetaList":
            mapped.meta_authors = [_plain(item) for item in authors.get("c", [])]
        abstract = meta.get("abstract")
        if isinstance(abstract, dict) and abstract.get("t") == "MetaBlocks":
            abstract_blocks = abstract.get("c", [])
            mapped.meta_abstract = _map_blocks(
                abstract_blocks if isinstance(abstract_blocks, list) else [], alloc, mapped
            )
    return mapped


def _nest_sections(blocks: list[Block]) -> list[Block]:
    """Build section hierarchy from Pandoc's flat header stream."""
    result: list[Block] = []
    stack: list[Section] = []
    children: dict[str, list[Block]] = {}
    for block in blocks:
        if isinstance(block, Section):
            while stack and stack[-1].level >= block.level:
                stack.pop()
            children[block.id] = list(block.children)
            if stack:
                children[stack[-1].id].append(block)
            else:
                result.append(block)
            stack.append(block)
        elif stack:
            children[stack[-1].id].append(block)
        else:
            result.append(block)

    def materialize(block: Block) -> Block:
        if not isinstance(block, Section):
            return block
        return block.model_copy(
            update={"children": [materialize(child) for child in children[block.id]]}
        )

    return [materialize(block) for block in result]


def _replace_by_id(blocks: list[Block], block_id: str, replacement: Block) -> bool:
    for index, block in enumerate(blocks):
        if block.id == block_id:
            blocks[index] = replacement
            return True
        if isinstance(block, Section) and _replace_by_id(block.children, block_id, replacement):
            return True
    return False


def assert_no_sentinels(doc: Any) -> None:
    """Reject unresolved raw-TeX placeholders anywhere in an IR model."""

    def contains(value: Any) -> bool:
        if isinstance(value, str):
            return _START in value or _END in value
        if isinstance(value, dict):
            return any(contains(item) for item in value.values())
        if isinstance(value, (list, tuple, set)):
            return any(contains(item) for item in value)
        return False

    if contains(doc.model_dump()):
        from paperdeck.errors import ConversionError

        raise ConversionError(
            "raw-TeX sentinel leaked into IR",
            hint="Inspect the reference resolution stage.",
            code="sentinel-leak",
        )
