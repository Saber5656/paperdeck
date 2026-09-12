"""Cross-node IR validation and shared traversal helpers."""

from __future__ import annotations

from collections.abc import Iterator
from typing import TypeVar

from paperdeck.config import LimitsSettings
from paperdeck.errors import ConversionError

from .model import (
    Block,
    Cite,
    Document,
    Emph,
    Equation,
    ExtLink,
    Figure,
    FootnoteDef,
    FootnoteRef,
    Inline,
    ListBlock,
    Paragraph,
    Quote,
    RefLink,
    Section,
    Strong,
    Sub,
    Sup,
    Table,
    Warning,
)

_B = TypeVar("_B", bound=Block)


def iter_blocks(doc: Document) -> Iterator[Block]:
    """Yield body blocks pre-order, followed by document footnotes."""

    def walk(block: Block) -> Iterator[Block]:
        yield block
        if isinstance(block, Section):
            for child in block.children:
                yield from walk(child)
        elif isinstance(block, ListBlock):
            for item in block.items:
                for child in item:
                    yield from walk(child)
        elif isinstance(block, FootnoteDef):
            for child in block.content:
                yield from walk(child)
        elif isinstance(block, Quote):
            for child in block.content:
                yield from walk(child)

    for block in doc.body:
        yield from walk(block)
    for footnote in doc.footnotes:
        yield from walk(footnote)


def _inline_children(inline: Inline) -> Iterator[Inline]:
    yield inline
    if isinstance(inline, (Emph, Strong, Sub, Sup, ExtLink)):
        for child in inline.content:
            yield from _inline_children(child)


def iter_inlines(block: Block) -> Iterator[Inline]:
    """Yield inline sequences owned by one block and recurse nested inline content."""
    sequences: list[list[Inline]] = []
    if isinstance(block, Section):
        sequences.append(block.title)
    elif isinstance(block, Paragraph):
        sequences.append(block.content)
    if isinstance(block, Figure):
        sequences.append(block.caption)
    elif isinstance(block, Table):
        sequences.append(block.caption)
        if block.rows:
            sequences.extend(cell.content for row in block.rows for cell in row)
    for sequence in sequences:
        for inline in sequence:
            yield from _inline_children(inline)


def _all_inlines(doc: Document) -> Iterator[Inline]:
    for block in iter_blocks(doc):
        yield from iter_inlines(block)
    for entry in doc.bibliography:
        for inline in entry.content:
            yield from _inline_children(inline)
    for inline in doc.meta.title:
        yield from _inline_children(inline)
    if doc.meta.abstract:
        for block in iter_blocks(
            doc.model_copy(update={"body": doc.meta.abstract, "footnotes": []})
        ):
            yield from iter_inlines(block)


def _fail(message: str) -> ConversionError:
    return ConversionError(
        message,
        "Choose another engine or inspect the input and conversion report.",
    )


def validate_document(doc: Document, limits: LimitsSettings) -> list[Warning]:
    """Validate references, assets and anchors, returning non-fatal warnings."""
    warnings: list[Warning] = []
    blocks = list(iter_blocks(doc))
    if doc.meta.abstract:
        blocks.extend(
            iter_blocks(doc.model_copy(update={"body": doc.meta.abstract, "footnotes": []}))
        )
    bib_entries = {entry.id for entry in doc.bibliography}
    anchor_ids: list[str] = [block.id for block in blocks]
    anchor_ids.extend(entry.id for entry in doc.bibliography)
    if len(anchor_ids) != len(set(anchor_ids)):
        duplicate = next(item for item in set(anchor_ids) if anchor_ids.count(item) > 1)
        raise _fail(f"duplicate anchor id: {duplicate}")
    known_assets = set(doc.assets)
    referenced_assets: set[str] = set()
    for block in blocks:
        asset_id = getattr(block, "asset_id", None)
        if asset_id is not None:
            if asset_id not in known_assets:
                raise _fail(f"unknown asset_id: {asset_id}")
            referenced_assets.add(asset_id)
        if isinstance(block, Equation):
            valid_latex = (
                block.content_kind == "latex"
                and bool(block.latex)
                and block.latex_verified
                and block.asset_id is None
            )
            valid_image = (
                block.content_kind == "image"
                and block.asset_id is not None
                and not block.latex_verified
            )
            if not (valid_latex or valid_image):
                raise _fail(f"invalid equation invariant: {block.id}")
        if isinstance(block, Table):
            if block.content_kind == "grid" and block.rows is None:
                raise _fail(f"grid table missing rows: {block.id}")
            if block.content_kind == "image" and block.asset_id is None:
                raise _fail(f"image table missing asset_id: {block.id}")
        if isinstance(block, Section) and not block.children:
            warnings.append(
                Warning(code="empty-section", message="section has no content", where=block.id)
            )
    for inline in _all_inlines(doc):
        if isinstance(inline, RefLink):
            if inline.target_id and inline.target_id not in anchor_ids:
                raise _fail(f"unresolvable RefLink target_id: {inline.target_id}")
            if not inline.target_id:
                warnings.append(
                    Warning(
                        code="unresolved-ref",
                        message="reference target is unresolved",
                        where=inline.text,
                    )
                )
            elif inline.kind == "eq" and any(item.id == inline.target_id for item in blocks):
                eq_target = next(item for item in blocks if item.id == inline.target_id)
                if isinstance(eq_target, Equation) and eq_target.number is None:
                    warnings.append(
                        Warning(
                            code="unnumbered-eqref-target",
                            message="equation has no number",
                            where=inline.target_id,
                        )
                    )
        elif isinstance(inline, FootnoteRef):
            if inline.target_id and inline.target_id not in anchor_ids:
                raise _fail(f"unresolvable FootnoteRef target_id: {inline.target_id}")
            if not inline.target_id:
                warnings.append(
                    Warning(
                        code="unresolved-ref",
                        message="footnote target is unresolved",
                        where=inline.number,
                    )
                )
        elif isinstance(inline, Cite):
            for bib_id in inline.bib_ids:
                if bib_id not in bib_entries:
                    raise _fail(f"unknown bibliography id: {bib_id}")
    for label, target in doc.labels.items():
        if target not in anchor_ids:
            raise _fail(f"label {label!r} points to unknown anchor id: {target}")
    for asset_id in known_assets - referenced_assets:
        warnings.append(
            Warning(code="orphan-asset", message="asset is not referenced", where=asset_id)
        )
    hard_bytes = limits.embed_hard_max_mb * 1024 * 1024
    estimated_bytes = sum(len(asset.data_b64) * 3 / 4 for asset in doc.assets.values())
    if estimated_bytes > hard_bytes:
        warnings.append(
            Warning(code="assets-over-budget", message="embedded assets exceed hard budget")
        )
    return warnings
