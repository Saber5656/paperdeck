"""Total raw-TeX micro-parser and reference resolution helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal, cast


@dataclass(frozen=True)
class TexDirective:
    span: tuple[int, int]


@dataclass(frozen=True)
class LabelDef(TexDirective):
    name: str


@dataclass(frozen=True)
class RefUse(TexDirective):
    style: str
    names: list[str]


@dataclass(frozen=True)
class CiteUse(TexDirective):
    style: str
    keys: list[str]
    prenote: str | None = None
    postnote: str | None = None


@dataclass(frozen=True)
class FootnoteInline(TexDirective):
    tex_body: str
    truncated: bool = False


@dataclass(frozen=True)
class OtherTex(TexDirective):
    tex: str


def _safe_fragment(text: str) -> str:
    return "".join(char for char in text if char >= " " or char in "\n\t")[:30]


_NAME = re.compile(r"^[A-Za-z0-9_:.+/-]+$")
_START = "\ue000"
_END = "\ue001"
_REFS = {"ref", "eqref", "cref", "Cref", "autoref"}
_CITES = {"cite", "citep", "citet", "citealp", "citealt", "citeauthor", "citeyear"}
_STRUCTURAL_TEX = re.compile(
    r"^\s*\\(?:maketitle\b|appendix\b|bibliographystyle(?:\[[^]]*\])?\s*\{[^{}]*\}|"
    r"begin\s*\{thebibliography\}\s*\{[^{}]*\}|end\s*\{thebibliography\})\s*$",
    re.DOTALL,
)


def read_group(text: str, index: int) -> tuple[str | None, int]:
    """Read a balanced group beginning at ``index``; never raises."""
    if index >= len(text) or text[index] != "{":
        return None, index
    depth = 1
    escaped = False
    for cursor in range(index + 1, len(text)):
        char = text[cursor]
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[index + 1 : cursor], cursor + 1
    return None, len(text)


def _read_bracket(text: str, index: int) -> tuple[str | None, int]:
    if index >= len(text) or text[index] != "[":
        return None, index
    depth = 1
    for cursor in range(index + 1, len(text)):
        if text[cursor] == "[":
            depth += 1
        elif text[cursor] == "]":
            depth -= 1
            if depth == 0:
                return text[index + 1 : cursor], cursor + 1
    return None, len(text)


def _valid_names(content: str) -> list[str] | None:
    names = [item.strip() for item in content.split(",")]
    return names if names and all(_NAME.fullmatch(item) for item in names) else None


def _other(text: str, start: int, end: int) -> OtherTex:
    return OtherTex(span=(start, end), tex=text[start:end])


def parse_raw_tex(text: str) -> list[TexDirective]:
    """Parse supported directives and return positional fragments covering ``text``."""
    result: list[TexDirective] = []
    cursor = 0
    loose_start = 0

    def flush(end: int) -> None:
        nonlocal loose_start
        if end > loose_start:
            result.append(_other(text, loose_start, end))

    while cursor < len(text):
        if text[cursor] != "\\":
            cursor += 1
            continue
        match = re.match(r"\\([A-Za-z]+)", text[cursor:])
        if match is None:
            cursor += 1
            continue
        command = match.group(1)
        index = cursor + len(match.group(0))
        while index < len(text) and text[index].isspace():
            index += 1
        directive: TexDirective | None = None
        end = index
        if command == "footnote":
            body, end = read_group(text, index)
            if body is not None:
                truncated = len(body) > 10000
                directive = FootnoteInline((cursor, end), body[:10000], truncated)
        elif command == "label" or command in _REFS:
            first, end = read_group(text, index)
            if first is not None:
                names = _valid_names(first)
                if names is not None:
                    if command == "label" and len(names) == 1:
                        directive = LabelDef((cursor, end), names[0])
                    elif command in _REFS:
                        directive = RefUse((cursor, end), command, names)
        elif command in _CITES:
            pre, post = None, None
            index = cursor + len(match.group(0))
            optional: list[str] = []
            while index < len(text) and text[index].isspace():
                index += 1
            while index < len(text) and text[index] == "[":
                note, next_index = _read_bracket(text, index)
                if note is None:
                    break
                optional.append(note)
                index = next_index
                while index < len(text) and text[index].isspace():
                    index += 1
            actual_keys, end = read_group(text, index)
            keys = _valid_names(actual_keys) if actual_keys is not None else None
            if keys is not None:
                if len(optional) == 1:
                    post = optional[0]
                elif len(optional) >= 2:
                    pre, post = optional[0], optional[1]
                directive = CiteUse((cursor, end), command, keys, pre, post)
        if directive is None:
            # Consume a balanced argument for unknown commands so the fragment is useful.
            unknown_end = index
            if unknown_end < len(text) and text[unknown_end] == "{":
                _, unknown_end = read_group(text, unknown_end)
            cursor = max(cursor + 1, unknown_end)
            continue
        flush(cursor)
        result.append(directive)
        cursor = end
        loose_start = end
    flush(len(text))
    return result


def _ref_kind(target: Any, bib_index: dict[str, Any]) -> str:
    name = target.__class__.__name__
    return {
        "Equation": "eq",
        "Figure": "fig",
        "Table": "tab",
        "Section": "sec",
        "FootnoteDef": "fn",
        "BibRef": "bib",
    }.get(name, "sec")


def _footnote_inlines(text: str) -> list[Any]:
    from paperdeck.ir.model import Math, Text

    result: list[Any] = []
    cursor = 0
    for match in re.finditer(r"\$([^$]+)\$", text):
        if match.start() > cursor:
            result.append(Text(text=text[cursor : match.start()]))
        result.append(Math(latex=match.group(1)))
        cursor = match.end()
    if cursor < len(text):
        result.append(Text(text=text[cursor:]))
    return result


def _directive_inlines(
    span: Any,
    labels: dict[str, str],
    targets: dict[str, Any],
    bib_index: dict[str, Any],
    footnotes: list[Any],
    warnings: list[Any],
) -> list[Any]:
    from paperdeck.ir.model import Cite, FootnoteDef, FootnoteRef, Paragraph, RefLink, Text, Warning

    result: list[Any] = []
    for directive in parse_raw_tex(span.tex):
        if isinstance(directive, LabelDef):
            warnings.append(
                Warning(
                    code="label-loose",
                    message="label was not bound to a numberable node",
                    where=directive.name,
                )
            )
        elif isinstance(directive, RefUse):
            unresolved_kind = "eq" if directive.style == "eqref" else "sec"
            resolved: list[tuple[str, str, str]] = []
            for name in directive.names:
                target_id = labels.get(name, "")
                target = targets.get(target_id)
                if target_id and target is not None:
                    kind = _ref_kind(target, bib_index)
                    display = str(getattr(target, "number", None) or "??")
                    if directive.style == "eqref":
                        display = f"({display})"
                    elif directive.style in {"cref", "Cref", "autoref"}:
                        words = {
                            "eq": "Eq.",
                            "fig": "Fig.",
                            "tab": "Table",
                            "sec": "Section",
                            "fn": "Footnote",
                        }
                        word = words.get(kind, "Section")
                        if directive.style == "Cref":
                            word = word.capitalize()
                        display = f"{word} {display}"
                    resolved.append((target_id, kind, display))
                else:
                    warnings.append(
                        Warning(
                            code="unresolved-ref",
                            message="reference target is unresolved",
                            where=name,
                        )
                    )
                    resolved.append(("", unresolved_kind, "??"))
            if directive.style in {"cref", "Cref", "autoref"} and len(resolved) > 1:
                grouped: list[Any] = []
                for index, (target_id, kind, display) in enumerate(resolved):
                    word, _, number = display.partition(" ")
                    if index == 0:
                        if directive.style == "Cref":
                            word = word.capitalize()
                        word = word.rstrip(".") + "s."
                        display = f"{word} {number}"
                    else:
                        display = number
                    grouped.append(
                        RefLink(
                            target_id=target_id,
                            kind=cast(Literal["eq", "fig", "tab", "sec", "bib", "fn"], kind),
                            text=display,
                        )
                    )
                    if index + 1 < len(resolved):
                        grouped.append(Text(text=", "))
                result.extend(grouped)
            else:
                result.extend(
                    RefLink(
                        target_id=item[0],
                        kind=cast(Literal["eq", "fig", "tab", "sec", "bib", "fn"], item[1]),
                        text=item[2],
                    )
                    for item in resolved
                )
        elif isinstance(directive, CiteUse):
            ids: list[str] = []
            parts: list[str] = []
            labels_mode = False
            for key in directive.keys:
                ref = bib_index.get(key)
                if ref is None:
                    warnings.append(
                        Warning(
                            code=f"cite-unresolved:{key}",
                            message="citation key is unresolved",
                            where=key,
                        )
                    )
                    parts.append("?")
                    continue
                ids.append(ref.anchor_id)
                if ref.label:
                    labels_mode = True
                    parts.append(ref.label)
                else:
                    parts.append(ref.number or "?")
            separator = "; " if labels_mode else ", "
            note = ", ".join(item for item in [directive.prenote, directive.postnote] if item)
            text_value = separator.join(parts)
            if labels_mode:
                text_value = f"({text_value}{', ' + note if note else ''})"
            else:
                text_value = f"[{text_value}{', ' + note if note else ''}]"
            result.append(Cite(bib_ids=ids, text=text_value))
        elif isinstance(directive, FootnoteInline):
            foot_id = f"fn-{len(footnotes) + 1}"
            number = str(len(footnotes) + 1)
            footnotes.append(
                FootnoteDef(
                    id=foot_id,
                    number=number,
                    content=[
                        Paragraph(
                            id=f"para-{foot_id}",
                            content=_footnote_inlines(directive.tex_body),
                        )
                    ],
                )
            )
            result.append(FootnoteRef(target_id=foot_id, number=number))
        elif isinstance(directive, OtherTex):
            if _STRUCTURAL_TEX.fullmatch(directive.tex):
                continue
            warnings.append(
                Warning(
                    code=f"raw-tex-dropped:{_safe_fragment(directive.tex)}",
                    message="unsupported raw TeX dropped",
                )
            )
    return result


def resolve_references(doc: Any, labels: dict[str, str], bib_index: dict[str, Any]) -> Any:
    """Resolve raw placeholders in a mapped document and return it."""
    from paperdeck.errors import ConversionError
    from paperdeck.ir.model import (
        Cite,
        Emph,
        ExtLink,
        Figure,
        Paragraph,
        Section,
        Table,
        Text,
        Warning,
    )

    targets: dict[str, Any] = {}

    def collect(blocks: list[Any]) -> None:
        for block in blocks:
            targets[block.id] = block
            if isinstance(block, Section):
                collect(block.children)
            elif block.__class__.__name__ == "Quote":
                collect(block.content)
            elif block.__class__.__name__ == "ListBlock":
                for item in block.items:
                    collect(item)

    collect(doc.body)
    targets.update({ref.anchor_id: ref for ref in bib_index.values()})
    span_map = {span.placeholder_id: span for span in doc.raw_spans}
    warnings = list(doc.warnings)

    def inline_list(values: list[Any]) -> list[Any]:
        output: list[Any] = []
        for value in values:
            if isinstance(value, Text) and value.text in span_map:
                output.extend(
                    _directive_inlines(
                        span_map[value.text], labels, targets, bib_index, doc.footnotes, warnings
                    )
                )
            elif isinstance(value, (Emph, ExtLink)):
                output.append(value.model_copy(update={"content": inline_list(value.content)}))
            elif isinstance(value, Cite):
                ids: list[str] = []
                parts: list[str] = []
                labels_mode = False
                for key in value.bib_ids:
                    ref = bib_index.get(key)
                    if ref is None:
                        warnings.append(
                            Warning(
                                code=f"cite-unresolved:{key}",
                                message="citation key is unresolved",
                                where=key,
                            )
                        )
                        parts.append("?")
                    else:
                        ids.append(ref.anchor_id)
                        if ref.label:
                            labels_mode = True
                            parts.append(ref.label)
                        else:
                            parts.append(ref.number or "?")
                separator = "; " if labels_mode else ", "
                display = separator.join(parts)
                display = f"({display})" if labels_mode else f"[{display}]"
                output.append(value.model_copy(update={"bib_ids": ids, "text": display}))
            else:
                output.append(value)
        return output

    def replace_block(block: Any) -> Any:
        if isinstance(block, Section):
            return block.model_copy(
                update={
                    "title": inline_list(block.title),
                    "children": [replace_block(item) for item in block.children],
                }
            )
        if isinstance(block, Paragraph):
            return block.model_copy(update={"content": inline_list(block.content)})
        if isinstance(block, Figure):
            return block.model_copy(update={"caption": inline_list(block.caption)})
        if isinstance(block, Table):
            rows = [
                [cell.model_copy(update={"content": inline_list(cell.content)}) for cell in row]
                for row in block.rows or []
            ]
            return block.model_copy(update={"caption": inline_list(block.caption), "rows": rows})
        if hasattr(block, "content") and block.__class__.__name__ == "Quote":
            return block.model_copy(
                update={"content": [replace_block(item) for item in block.content]}
            )
        if hasattr(block, "items"):
            return block.model_copy(
                update={"items": [[replace_block(item) for item in group] for group in block.items]}
            )
        return block

    doc.body = [replace_block(block) for block in doc.body]
    doc.meta_title = inline_list(doc.meta_title)
    if doc.meta_abstract:
        doc.meta_abstract = [replace_block(block) for block in doc.meta_abstract]
    doc.labels = dict(labels)
    doc.warnings = warnings

    def contains(value: Any) -> bool:
        if isinstance(value, str):
            return _START in value or _END in value
        if isinstance(value, dict):
            return any(contains(item) for item in value.values())
        if isinstance(value, (list, tuple, set)):
            return any(contains(item) for item in value)
        return False

    if contains([block.model_dump() for block in doc.body]):
        raise ConversionError(
            "raw-TeX sentinel leaked into IR",
            hint="Inspect raw reference resolution.",
            code="sentinel-leak",
        )
    return doc
