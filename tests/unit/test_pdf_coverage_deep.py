"""Meaningful branch coverage for the PDF pipeline and its local LLM boundary."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from paperdeck.config import load_settings
from paperdeck.engines.pdf.assemble import assemble_pdf
from paperdeck.engines.pdf.blocks import RawBlock, _Line, build_blocks, detect_columns
from paperdeck.engines.pdf.citations import (
    BibEntryDraft,
    extract_bibliography,
    link_citations,
    link_structural_refs,
)
from paperdeck.engines.pdf.equations import EquationDraft, EquationsResult, process_equations
from paperdeck.engines.pdf.extract import PageBitmap, encode_png_rgb, open_pdf
from paperdeck.engines.pdf.segment import RoleInfo, SegmentResult, segment
from paperdeck.errors import InputError, LlmError
from paperdeck.ir.model import BibEntry, Text
from paperdeck.llm.schemas import PdfBibV1, PdfEquationLatexV1, PdfSegmentV1


class _Bitmap:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.closed = False

    def crop_png(self, _bbox, pad_pt=6) -> bytes:
        if self.fail:
            raise ValueError("crop")
        return encode_png_rgb(2, 2, b"\xff" * 12)

    def close(self) -> None:
        self.closed = True


class _Pdf:
    path = Path("paper.pdf")
    metadata_title = ""

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    def page_size(self, _page: int) -> tuple[float, float]:
        return 600.0, 800.0

    def bitmap(self, _page: int, _scale: float = 2.0) -> _Bitmap:
        return _Bitmap(self.fail)


class _Llm:
    settings = SimpleNamespace(llm=SimpleNamespace(vlm_model="local"))

    def __init__(self, response=None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls = 0

    def complete(self, *_args, **_kwargs):
        self.calls += 1
        if self.error:
            raise self.error
        return self.response


class _Ledger:
    def __init__(self, allowed: bool = True) -> None:
        self.allowed = allowed

    def remaining_allows(self, _estimate: float) -> bool:
        return self.allowed

    def call_estimate(self, _purpose: str) -> float:
        return 0.01


class _Alloc:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    def next(self, kind: str) -> str:
        self.counts[kind] = self.counts.get(kind, 0) + 1
        return f"{kind}-{self.counts[kind]}"


def _raw(block_id: str, text: str, page: int = 0) -> RawBlock:
    return RawBlock(block_id, page, (40.0, 400.0, 560.0, 430.0), text, 10.0, 1, 0, 30.0)


def test_columns_and_block_flush_paths() -> None:
    assert detect_columns([], 600) == ([[]], None)
    assert detect_columns([SimpleNamespace(bbox=(0, 0, 10, 10))], 0) == (
        [[SimpleNamespace(bbox=(0, 0, 10, 10))]],
        None,
    )
    lines = [_Line([], (20, 20 + i * 20, 160, 30 + i * 20)) for i in range(20)] + [
        _Line([], (440, 20 + i * 20, 580, 30 + i * 20)) for i in range(20)
    ]
    columns, warning = detect_columns(lines, 600)
    assert warning is None and len(columns) == 2 and len(columns[0]) == len(columns[1]) == 20
    chars = [
        SimpleNamespace(text="a", bbox=(10, 100, 20, 110), font_size=10),
        SimpleNamespace(text="b", bbox=(30, 100, 40, 110), font_size=10),
        SimpleNamespace(text="c", bbox=(10, 40, 20, 50), font_size=20),
    ]
    blocks = build_blocks([SimpleNamespace(page=0, width=600, chars=chars)])
    assert len(blocks) == 2 and blocks[0].text == "a b"


def test_citation_extraction_and_all_link_forms() -> None:
    assert extract_bibliography([], _Llm())[-1] == ["pdf-bib-empty"]
    response = SimpleNamespace(
        entries=[SimpleNamespace(number="[1]", text="A", urls=["javascript:x"])]
    )
    entries, numeric, ids, warnings = extract_bibliography(
        [_raw("b", "[1] A")], _Llm(response), alloc=_Alloc()
    )
    assert entries and numeric == {"1": "bib-1"} and ids == ["bib-1"]
    assert warnings == ["bib-url-rejected:bib-1"]
    bib = [SimpleNamespace(number="1", id="bib-1", text="Smith 2020")]

    class CiteLlm:
        def complete(self, *_args, **_kwargs):
            return SimpleNamespace(
                mappings=[
                    SimpleNamespace(marker="(Smith 2020)", entry_indices=[0, 9]),
                    SimpleNamespace(marker="(missing 2021)", entry_indices=[]),
                ]
            )

    rows = link_citations(["See [1]; (Smith 2020) and (missing 2021)."], bib, CiteLlm())
    assert len(rows[0]) == 2 and rows[0][0].node.bib_ids == ["bib-1"]
    refs = link_structural_refs(
        ["Equation 1 Fig. 2 Table 3 Section 4 §5"],
        {("eq", "1"): "eq-1", ("fig", "2"): "fig-2", ("tab", "3"): "tab-3", ("sec", "4"): "sec-4"},
    )
    assert {item.node.target_id for item in refs[0]} == {"eq-1", "fig-2", "tab-3", "sec-4"}


def test_citation_chunking_and_fallback_drafts() -> None:
    class BibLlm:
        def __init__(self) -> None:
            self.calls = 0

        def complete(self, *_args, **_kwargs):
            self.calls += 1
            return PdfBibV1(entries=[{"number": None, "text": "entry", "urls": []}])

    llm = BibLlm()
    entries, *_ = extract_bibliography([_raw("b", "x" * 30001)], llm)
    assert llm.calls == 2 and len(entries) == 2
    assert isinstance(BibEntryDraft("x", None, "text"), BibEntryDraft)
    assert link_citations(["[1,99] [2-70]"], [SimpleNamespace(number="1", id="b1")])[0] == []


def test_equation_success_duplicates_crop_failure_and_vlm_failure() -> None:
    blocks = [_raw("e1", "x = y"), _raw("e2", "z = q")]
    seg = SegmentResult(
        {
            "e1": RoleInfo("display_equation", number_text="(1)"),
            "e2": RoleInfo("display_equation", number_text="(1)"),
        },
        [],
        ["e1", "e2"],
    )
    llm = _Llm(PdfEquationLatexV1(latex="x", confidence=0.9))
    result = process_equations(seg, blocks, _Pdf(), llm, _Ledger(), _Alloc())
    assert result.equations["e1"].latex == "x"
    assert "pdf-eq-number-duplicate:e2" in result.warnings
    failed = process_equations(seg, blocks, _Pdf(True), llm, _Ledger(), _Alloc())
    assert not failed.equations and len(failed.warnings) == 2
    errored = process_equations(
        SegmentResult({"e1": RoleInfo("display_equation")}, [], ["e1"]),
        blocks[:1],
        _Pdf(),
        _Llm(error=RuntimeError("network")),
        _Ledger(),
        _Alloc(),
    )
    assert "vlm-failed:e1" in errored.warnings and errored.equations["e1"].latex is None


def test_equation_budget_stops_vlm_but_crops_remaining() -> None:
    blocks = [_raw("e1", "x = y"), _raw("e2", "z = q")]
    seg = SegmentResult(
        {"e1": RoleInfo("display_equation"), "e2": RoleInfo("display_equation")}, [], ["e1", "e2"]
    )
    result = process_equations(seg, blocks, _Pdf(), _Llm(), _Ledger(False), _Alloc())
    assert set(result.equations) == {"e1", "e2"} and len(result.assets) == 2
    assert result.warnings == ["vlm-budget-exhausted"]


def test_assembly_covers_sections_assets_tables_and_unhandled() -> None:
    blocks = [
        _raw("title", "A title"),
        _raw("author", "Alice Example"),
        _raw("h1", "Introduction"),
        _raw("h2", "Details"),
        _raw("p1", "See Eq. (1) Fig. 1 Table 1 Sec. 1 [1]."),
        _raw("eq", "x = y"),
        _raw("fig", "Figure 1 caption"),
        _raw("tab", "Table 1 caption"),
        _raw("unknown", "unsupported equation"),
        _raw("bib", "[1] source"),
        _raw("abstract", "Abstract words"),
        _raw("noise", "footer"),
    ]
    roles = {
        "title": RoleInfo("title"),
        "author": RoleInfo("author_line"),
        "h1": RoleInfo("heading", 1),
        "h2": RoleInfo("heading", 2),
        "p1": RoleInfo("paragraph"),
        "eq": RoleInfo("display_equation", number_text="1"),
        "fig": RoleInfo("figure_caption", number_text="1"),
        "tab": RoleInfo("table_caption", number_text="1"),
        "unknown": RoleInfo("display_equation"),
        "bib": RoleInfo("bib_entry", number_text="1"),
        "abstract": RoleInfo("abstract"),
        "noise": RoleInfo("noise"),
    }
    seg = SegmentResult(roles, [], [item.id for item in blocks])
    eq = EquationsResult(
        equations={"eq": EquationDraft("eq-1", "1", "asset-eq-1")},
        assets={},
    )
    bib = [BibEntry(id="bib-1", number="1", content=[Text(text="source")], urls=[])]
    settings = load_settings(None, {"llm.base_url": "http://localhost:11434/v1"})
    doc = assemble_pdf(
        seg,
        blocks,
        eq,
        (bib, {"1": "bib-1"}, ["bib-1"], []),
        _Pdf(),
        settings,
    )
    assert len(doc.body) == 1 and doc.body[0].children
    assert doc.meta.authors == ["Alice Example"] and doc.meta.abstract

    def walk(nodes):
        for node in nodes:
            yield node
            yield from walk(getattr(node, "children", []))

    all_nodes = list(walk(doc.body))
    assert any(getattr(item, "type", "") == "equation" for item in all_nodes)
    assert any(item.type == "figure" for item in all_nodes)
    assert any(item.type == "table" for item in all_nodes)
    assert any(item.type == "unhandled" for item in all_nodes)


def test_segment_batches_merges_and_repairs_coverage() -> None:
    blocks = [_raw(f"b{i}", "part-" if i == 0 else "word", i) for i in range(10)]

    class SegmentLlm:
        def __init__(self) -> None:
            self.calls = 0

        def complete(self, _purpose, messages, _schema, **_kwargs):
            self.calls += 1
            text = str(messages[-1]["content"])
            ids = [json.loads(line)["id"] for line in text.splitlines() if line.startswith("{")]
            ids = [item for item in ids if not item.startswith("ctx-")]
            return PdfSegmentV1(
                blocks=[
                    {"id": item, "role": "title" if item == "b0" else "paragraph"} for item in ids
                ],
                section_order=ids,
            )

    llm = SegmentLlm()
    result = segment(blocks, llm)
    assert llm.calls == 2 and result.roles["b0"].role == "title"
    assert result.paragraphs
    assert segment([], llm).roles == {}


def test_segment_invalid_coverage_retries_then_fails() -> None:
    block = _raw("b1", "text")

    class Bad:
        def complete(self, *_args, **_kwargs):
            return PdfSegmentV1(blocks=[], section_order=[])

    with pytest.raises(LlmError, match="coverage"):
        segment([block], Bad())


def test_extract_png_bitmap_and_limits(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        encode_png_rgb(0, 1, b"")
    raw = bytes([1, 2, 3, 4] * 4)
    bitmap = PageBitmap(SimpleNamespace(buffer=raw, n_channels=4), 2, 2, 1.0)
    assert len(bitmap._rgb()) == 12
    assert bitmap.crop_png((0, 0, 2, 2)).startswith(b"\x89PNG")
    bitmap.close()
    with pytest.raises(InputError, match="cannot be read"):
        open_pdf(tmp_path / "missing.pdf", load_settings(None, {}).limits)
    too_large = tmp_path / "large.pdf"
    too_large.write_bytes(b"x")
    limits = load_settings(None, {}).limits.model_copy(update={"max_input_mb": 0})
    with pytest.raises(InputError, match="exceeds"):
        open_pdf(too_large, limits)
