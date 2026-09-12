"""LLM role classification over deterministic PDF blocks."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, replace
from typing import Any

from ...errors import LlmError
from ...llm.prompts import load_prompt
from ...llm.schemas import PdfSegmentV1
from .blocks import RawBlock


@dataclass(frozen=True)
class RoleInfo:
    role: str
    level: int | None = None
    number_text: str | None = None
    links_to_block: str | None = None


@dataclass(frozen=True)
class HeadingNode:
    block_id: str
    level: int
    children: list[HeadingNode] = field(default_factory=list)


@dataclass
class SegmentResult:
    roles: dict[str, RoleInfo]
    section_tree: list[HeadingNode]
    order: list[str]
    warnings: list[str] = field(default_factory=list)
    paragraphs: list[tuple[str, str, list[str]]] = field(default_factory=list)
    links_to_block: dict[str, str] = field(default_factory=dict)


def _serialize(blocks: list[RawBlock]) -> str:
    rows = []
    for block in blocks:
        text = block.text[:600] + ("…" if len(block.text) > 600 else "")
        rows.append(
            json.dumps(
                {
                    "id": block.id,
                    "page": block.page,
                    "bbox": [round(x) for x in block.bbox],
                    "font_size_median": round(block.font_size_median),
                    "text": text,
                },
                ensure_ascii=False,
            )
        )
    return "\n".join(rows)


def _tree(headings: list[tuple[str, int]]) -> list[HeadingNode]:
    roots: list[HeadingNode] = []
    stack: list[tuple[int, HeadingNode]] = []
    for block_id, level in headings:
        node = HeadingNode(block_id, level)
        while stack and stack[-1][0] >= level:
            stack.pop()
        if stack:
            parent = stack[-1][1]
            parent.children.append(node)
        else:
            roots.append(node)
        stack.append((level, node))
    return roots


def _merge_paragraphs(
    blocks: list[RawBlock], roles: dict[str, RoleInfo]
) -> list[tuple[str, str, list[str]]]:
    result: list[tuple[str, str, list[str]]] = []
    for block in blocks:
        if roles.get(block.id, RoleInfo("noise")).role != "paragraph":
            continue
        if not result:
            result.append((block.id, block.text, [block.id]))
            continue
        previous_id, previous_text, ids = result[-1]
        previous = next(item for item in blocks if item.id == previous_id)
        same_page = previous.page == block.page
        gap = previous.bbox[1] - block.bbox[3]
        threshold = 2.5 * max(previous.line_height_median, block.line_height_median, 1.0)
        final = previous_text.rstrip().endswith((".", "!", "?", '."', ".'", ")."))
        join = (same_page and gap < threshold) or (not same_page and not final)
        if join:
            if re.search(r"[a-z]-$", previous_text) and re.match(r"^[a-z]", block.text):
                text = previous_text[:-1] + block.text
            else:
                text = previous_text.rstrip() + " " + block.text.lstrip()
            result[-1] = (previous_id, text, ids + [block.id])
        else:
            result.append((block.id, block.text, [block.id]))
    return result


def segment(blocks: list[RawBlock], llm: Any) -> SegmentResult:
    if not blocks:
        return SegmentResult({}, [], [], [])
    pages = sorted({block.page for block in blocks})
    batches: list[list[RawBlock]] = []
    for start in range(0, len(pages), 8):
        page_set = set(pages[start : start + 8])
        batch = [block for block in blocks if block.page in page_set]
        if start:
            prev = [block for block in blocks if block.page == pages[start - 1]]
            if prev:
                batch.insert(0, replace(prev[-1], id="ctx-" + prev[-1].id))
        batches.append(batch)
    roles: dict[str, RoleInfo] = {}
    order: list[str] = []
    warnings: list[str] = []
    links: dict[str, str] = {}
    heading_ids: list[tuple[str, int]] = []
    for batch in batches:
        input_ids = [block.id for block in batch if not block.id.startswith("ctx-")]
        serialized = _serialize(batch)
        messages = [
            {"role": "system", "content": "You are a document structure classifier."},
            {"role": "user", "content": load_prompt("segment", blocks=serialized)},
        ]
        response = llm.complete("segment", messages, PdfSegmentV1, max_tokens=8192)
        for attempt in range(2):
            returned = [entry.id for entry in response.blocks]
            missing = sorted(set(input_ids) - set(returned))
            unknown = sorted(set(returned) - set(input_ids))
            duplicate = sorted({item for item in returned if returned.count(item) > 1})
            if not missing and not unknown and not duplicate:
                break
            if attempt:
                raise LlmError(
                    "segment block coverage failed",
                    "Retry the conversion with a more reliable model.",
                    "segment-coverage",
                )
            feedback = (
                f"Coverage error. Missing={missing}; unknown={unknown}; "
                f"duplicated={duplicate}. Classify every input id exactly once."
            )
            messages.append({"role": "user", "content": feedback})
            response = llm.complete("segment", messages, PdfSegmentV1, max_tokens=8192)
        for entry in response.blocks:
            if entry.id not in input_ids:
                continue
            roles[entry.id] = RoleInfo(
                entry.role, entry.level, entry.number_text, entry.links_to_block
            )
            if entry.links_to_block:
                links[entry.id] = entry.links_to_block
            if entry.role == "heading":
                heading_ids.append((entry.id, entry.level or 1))
        order.extend([entry for entry in response.section_order if entry in input_ids])
    # Canonical deterministic reading order wins if a model omits section_order.
    order = [block.id for block in blocks if block.id in roles]
    seen_title = 0
    seen_abstract = 0
    for block in blocks:
        info = roles.get(block.id)
        if info is None:
            continue
        if info.role == "title" and block.page > 2:
            roles[block.id] = RoleInfo("heading", 1, info.number_text, info.links_to_block)
            heading_ids.append((block.id, 1))
            warnings.append(f"late-title-demoted:{block.id}")
        elif info.role == "title":
            seen_title += 1
        if info.role == "abstract":
            seen_abstract += 1
            if seen_abstract > 1:
                roles[block.id] = RoleInfo("paragraph")
                warnings.append(f"duplicate-abstract:{block.id}")
    noise_ids = {
        block.id for block in blocks if roles.get(block.id, RoleInfo("noise")).role == "noise"
    }
    order = [block_id for block_id in order if block_id not in noise_ids]
    return SegmentResult(
        roles, _tree(heading_ids), order, warnings, _merge_paragraphs(blocks, roles), links
    )


__all__ = ["HeadingNode", "RoleInfo", "SegmentResult", "segment"]
