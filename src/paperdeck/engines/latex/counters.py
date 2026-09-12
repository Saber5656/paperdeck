"""Deterministic LaTeX section, equation, figure and table numbering replay."""

from __future__ import annotations

import re
from collections.abc import Iterator

from paperdeck.engines.latex.ast_map import MappedDoc
from paperdeck.engines.latex.refs import LabelDef, parse_raw_tex
from paperdeck.ir.model import Block, Equation, Figure, Section, Table, Warning


def _split_rows(text: str) -> list[str]:
    rows: list[str] = []
    start = 0
    braces = 0
    environments: list[str] = []
    cursor = 0
    while cursor < len(text):
        if text[cursor] == "{" and (cursor == 0 or text[cursor - 1] != "\\"):
            braces += 1
            cursor += 1
            continue
        if text[cursor] == "}" and (cursor == 0 or text[cursor - 1] != "\\"):
            braces = max(0, braces - 1)
            cursor += 1
            continue
        if text[cursor] == "\\" and cursor + 1 < len(text):
            if text.startswith("\\begin{", cursor):
                end = text.find("}", cursor + 7)
                if end >= 0:
                    environments.append(text[cursor + 7 : end])
                    cursor = end
            elif text.startswith("\\end{", cursor):
                end = text.find("}", cursor + 5)
                if end >= 0 and environments:
                    environments.pop()
                    cursor = end
            elif text.startswith("\\\\", cursor) and braces == 0 and not environments:
                rows.append(text[start:cursor])
                cursor += 1
                start = cursor + 1
        cursor += 1
    rows.append(text[start:])
    return rows


def _body(latex: str, env: str) -> str:
    value = re.sub(rf"^\s*\\begin\{{{re.escape(env)}\*?\}}", "", latex)
    value = re.sub(rf"\\end\{{{re.escape(env)}\*?\}}\s*$", "", value)
    return value.strip()


def _with_equation(eq: Equation, latex: str, number: str | None) -> Equation:
    if number is None:
        return eq.model_copy(update={"latex": latex, "number": None})
    return eq.model_copy(update={"latex": latex, "number": number})


def _contains(value: object, marker: str) -> bool:
    if isinstance(value, str):
        return marker in value
    if isinstance(value, dict):
        return any(_contains(item, marker) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(_contains(item, marker) for item in value)
    return False


def _walk_sections(
    blocks: list[Block],
    counters: list[int],
    appendix: list[bool],
    labels: dict[str, str],
    mapped: MappedDoc,
    warnings: list[Warning],
    eq_counter: list[int],
    number_within: bool,
    figure_counter: list[int],
    table_counter: list[int],
    appendix_counter: list[int],
) -> list[Block]:
    result: list[Block] = []
    for block in blocks:
        if isinstance(block, Section):
            unnumbered = block.id in mapped.unnumbered_sections
            if not unnumbered:
                counters[block.level - 1] += 1
                for index in range(block.level, 6):
                    counters[index] = 0
            if unnumbered:
                number = None
            elif appendix[0] and block.level == 1:
                appendix_counter[0] += 1
                number = chr(ord("A") + appendix_counter[0] - 1)
            elif appendix[0]:
                number = ".".join(str(value) for value in counters[: block.level] if value)
            else:
                number = ".".join(str(value) for value in counters[: block.level] if value)
            if block.level == 1 and number_within and not unnumbered:
                eq_counter[0] = 0
            children = _walk_sections(
                block.children,
                counters[:],
                appendix,
                labels,
                mapped,
                warnings,
                eq_counter,
                number_within,
                figure_counter,
                table_counter,
                appendix_counter,
            )
            result.append(block.model_copy(update={"number": number, "children": children}))
            continue
        if not appendix[0]:
            marker = any(
                span.tex.strip() == r"\appendix"
                and _contains(block.model_dump(), span.placeholder_id)
                for span in mapped.raw_spans
            )
            if marker:
                appendix[0] = True
                counters[:] = [0] * 6
        if isinstance(block, Figure) and block.caption:
            figure_counter[0] += 1
            result.append(block.model_copy(update={"number": str(figure_counter[0])}))
            continue
        if isinstance(block, Table) and block.caption:
            table_counter[0] += 1
            result.append(block.model_copy(update={"number": str(table_counter[0])}))
            continue
        if isinstance(block, Equation):
            env = mapped.env_map.get(block.id, "display")
            starred = env.endswith("*") or env in {"display", "math"}
            numbered_envs = {"align", "gather", "eqnarray", "multline", "flalign", "alignat"}
            if env.replace("*", "") in numbered_envs:
                rows = _split_rows(_body(block.latex or "", env.replace("*", "")))
            else:
                rows = [_body(block.latex or "", env.replace("*", ""))]
            split: list[Equation] = []
            for row in rows:
                row_labels = re.findall(r"\\label\{([^}]+)\}", row)
                row = re.sub(r"\\label\{[^}]+\}", "", row).strip()
                if "\\nonumber" in row or "\\notag" in row:
                    split_id = block.id if not split else f"{block.id}-{len(split) + 1}"
                    source_block = (
                        block if split_id == block.id else block.model_copy(update={"id": split_id})
                    )
                    split.append(_with_equation(source_block, row, None))
                    labels.update({label: split_id for label in row_labels})
                    continue
                number = None
                if not starred:
                    eq_counter[0] += 1
                    number = (
                        f"{counters[0]}.{eq_counter[0]}"
                        if number_within and counters[0]
                        else str(eq_counter[0])
                    )
                if "&" in row and env.replace("*", "") in numbered_envs:
                    row = f"\\begin{{aligned}}{row}\\end{{aligned}}"
                split_id = block.id if not split else f"{block.id}-{len(split) + 1}"
                source_block = (
                    block if split_id == block.id else block.model_copy(update={"id": split_id})
                )
                split.append(_with_equation(source_block, row, number))
                labels.update({label: split_id for label in row_labels})
            result.extend(split)
            continue
        result.append(block)
    return result


def assign_numbers(mapped: MappedDoc, preamble: str) -> MappedDoc:
    """Replay numbering and attach source labels to generated anchor ids."""
    warnings = list(mapped.warnings)
    appendix = [False]
    number_within = bool(
        re.search(r"\\numberwithin\s*\{\s*equation\s*\}\s*\{\s*section\s*\}", preamble)
    )
    if re.search(r"\\(?:setcounter|addtocounter|refstepcounter)", preamble):
        warnings.append(
            Warning(
                code="counter-manipulation-unsupported",
                message="custom counter manipulation was not replayed",
            )
        )
    if re.search(r"\\begin\{(?:theorem|lemma|proposition)", preamble):
        warnings.append(
            Warning(
                code="theorem-like-unsupported", message="theorem-like numbering is unsupported"
            )
        )
    labels: dict[str, str] = {}
    mapped.body = _walk_sections(
        mapped.body,
        [0] * 6,
        appendix,
        labels,
        mapped,
        warnings,
        [0],
        number_within,
        [0],
        [0],
        [0],
    )
    mapped.warnings = warnings
    source_ids = mapped.source_ids
    if mapped.source_labels:
        source_ids = {
            name: target for name, target in source_ids.items() if name in mapped.source_labels
        }
    labels.update(source_ids)
    ordered = list(_all_blocks(mapped.body))
    numberable = (Section, Equation, Figure, Table)
    for span in mapped.raw_spans:
        for directive in parse_raw_tex(span.tex):
            if isinstance(directive, LabelDef):
                owner_index = next(
                    (
                        index
                        for index, block in enumerate(ordered)
                        if span.placeholder_id in str(block.model_dump())
                    ),
                    len(ordered),
                )
                candidates = [
                    block for block in ordered[: owner_index + 1] if isinstance(block, numberable)
                ]
                if candidates:
                    if owner_index >= len(ordered) or not isinstance(
                        ordered[owner_index], numberable
                    ):
                        warnings.append(
                            Warning(
                                code="label-loose",
                                message="label bound to nearest preceding numberable node",
                                where=directive.name,
                            )
                        )
                    labels.setdefault(directive.name, candidates[-1].id)
                else:
                    warnings.append(
                        Warning(
                            code="label-loose",
                            message="label was not bound to a numberable node",
                            where=directive.name,
                        )
                    )
    label_for_id = {target: name for name, target in labels.items()}

    def attach(block: Block) -> Block:
        updates: dict[str, object] = {}
        if block.id in label_for_id and hasattr(block, "label"):
            updates["label"] = label_for_id[block.id]
        if isinstance(block, Section):
            updates["children"] = [attach(child) for child in block.children]
        if updates:
            return block.model_copy(update=updates)
        return block

    mapped.body = [attach(block) for block in mapped.body]
    mapped.labels = labels
    return mapped


def _all_blocks(blocks: list[Block]) -> Iterator[Block]:
    for block in blocks:
        yield block
        if isinstance(block, Section):
            yield from _all_blocks(block.children)
