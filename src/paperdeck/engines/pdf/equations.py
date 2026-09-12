"""Image-primary equation crops with explicitly unverified VLM transcription."""
from __future__ import annotations

import base64
import re
from dataclasses import dataclass, field
from typing import Any

from ...llm.prompts import load_prompt
from ...llm.schemas import PdfEquationLatexV1


@dataclass(frozen=True)
class EquationDraft:
    anchor_id: str
    number: str
    asset_id: str
    content_kind: str = "image"
    latex: str | None = None
    latex_verified: bool = False
    confidence: float | None = None


@dataclass(frozen=True)
class AssetDraft:
    id: str
    mime: str
    data_b64: str
    origin: dict[str, Any]


@dataclass
class EquationsResult:
    equations: dict[str, EquationDraft] = field(default_factory=dict)
    assets: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def _number(raw: str | None, fallback: int) -> str:
    if not raw:
        return f"E{fallback}"
    value = raw.strip()
    value = value[1:-1].strip() if value.startswith("(") and value.endswith(")") else value
    return value or f"E{fallback}"


def _asset(asset_id: str, data: bytes, page: int) -> Any:
    encoded = base64.b64encode(data).decode("ascii")
    try:
        from ...ir.model import Asset
        return Asset(id=asset_id, mime="image/png", data_b64=encoded, origin={"engine": "pdf", "page": page})
    except (ImportError, TypeError):
        return AssetDraft(asset_id, "image/png", encoded, {"engine": "pdf", "page": page})


def process_equations(seg: Any, blocks: list[Any], pdfdoc: Any, llm: Any, ledger: Any, alloc: Any) -> EquationsResult:
    by_id = {block.id: block for block in blocks}
    result = EquationsResult()
    used_numbers: set[str] = set()
    sequence = 0
    for block_id in seg.order:
        info = seg.roles.get(block_id)
        if info is None or info.role != "display_equation":
            continue
        sequence += 1
        block = by_id[block_id]
        try:
            image = pdfdoc.bitmap(block.page, 2.0).crop_png(block.bbox, pad_pt=6)
        except Exception:
            result.warnings.append(f"pdf-eq-crop-failed:{block_id}")
            continue
        asset_id = alloc.next("asset") if hasattr(alloc, "next") else f"asset-eq-{sequence}"
        anchor_id = alloc.next("eq") if hasattr(alloc, "next") else f"eq-{sequence}"
        result.assets[asset_id] = _asset(asset_id, image, block.page)
        number = _number(info.number_text, sequence)
        if number in used_numbers:
            result.warnings.append(f"pdf-eq-number-duplicate:{block_id}")
        used_numbers.add(number)
        draft = EquationDraft(anchor_id, number, asset_id)
        try:
            if not ledger.remaining_allows(1024):
                result.warnings.append("vlm-budget-exhausted")
                result.equations[block_id] = draft
                # Stop all subsequent VLM calls while still retaining crops.
                for rest_id in seg.order[seg.order.index(block_id) + 1 :]:
                    rest = seg.roles.get(rest_id)
                    if rest and rest.role == "display_equation":
                        sequence += 1
                        rest_block = by_id[rest_id]
                        try:
                            rest_image = pdfdoc.bitmap(rest_block.page, 2.0).crop_png(rest_block.bbox, pad_pt=6)
                            rid = alloc.next("asset") if hasattr(alloc, "next") else f"asset-eq-{sequence}"
                            ra = alloc.next("eq") if hasattr(alloc, "next") else f"eq-{sequence}"
                            result.assets[rid] = _asset(rid, rest_image, rest_block.page)
                            result.equations[rest_id] = EquationDraft(ra, _number(rest.number_text, sequence), rid)
                        except Exception:
                            result.warnings.append(f"pdf-eq-crop-failed:{rest_id}")
                break
            messages = [{"role": "system", "content": load_prompt("equation_latex", context="The image is the source of truth.")}, {"role": "user", "content": "Transcribe this equation image."}]
            response = llm.complete("equation", messages, PdfEquationLatexV1, model=getattr(llm.settings.llm, "vlm_model", None), images=[image], max_tokens=1024)
            latex = str(response.latex)
            if not latex or len(latex) > 4000 or re.search(r"\\(?:input|include|write|csname|href|url)\b", latex):
                result.warnings.append(f"vlm-latex-rejected:{block_id}")
            else:
                draft = EquationDraft(anchor_id, number, asset_id, latex=latex, confidence=float(response.confidence))
        except Exception:
            result.warnings.append(f"vlm-failed:{block_id}")
        result.equations[block_id] = draft
    return result


__all__ = ["AssetDraft", "EquationDraft", "EquationsResult", "process_equations"]
