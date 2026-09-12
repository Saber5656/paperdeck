"""Acceptance tests for PDF extraction limits and assembly geometry gaps."""

from __future__ import annotations

import struct
from pathlib import Path
from types import SimpleNamespace

import pytest
from reportlab.pdfgen import canvas

from paperdeck.config import load_settings
from paperdeck.engines.pdf.assemble import assemble_pdf
from paperdeck.engines.pdf.blocks import RawBlock, _Line, build_blocks, detect_columns
from paperdeck.engines.pdf.citations import link_citations
from paperdeck.engines.pdf.extract import encode_png_rgb, open_pdf
from paperdeck.engines.pdf.segment import RoleInfo, SegmentResult, segment
from paperdeck.errors import ConversionError, InputError
from paperdeck.ir.model import BibEntry, Text
from paperdeck.llm.schemas import PdfSegmentV1


def _pdf(path: Path, pages: int = 1, *, encrypted: bool = False) -> Path:
    document = canvas.Canvas(
        str(path), pagesize=(612, 792), encrypt="password" if encrypted else None
    )
    for index in range(pages):
        document.drawString(72, 720, f"fixture page {index}")
        document.showPage()
    document.save()
    return path


def _png_dimensions_and_pixels(data: bytes) -> tuple[int, int, bytes]:
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    width, height = struct.unpack(">II", data[16:24])
    offset = 8
    compressed = bytearray()
    while offset < len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        kind = data[offset + 4 : offset + 8]
        payload = data[offset + 8 : offset + 8 + length]
        offset += 12 + length
        if kind == b"IDAT":
            compressed.extend(payload)
        if kind == b"IEND":
            break
    import zlib

    rows = zlib.decompress(bytes(compressed))
    stride = width * 3
    assert len(rows) == (stride + 1) * height
    return width, height, b"".join(
        rows[row * (stride + 1) + 1 : (row + 1) * (stride + 1)] for row in range(height)
    )


def test_pdf_load_limits_and_failure_taxonomy(tmp_path: Path) -> None:
    settings = load_settings(None, {})
    with pytest.raises(InputError, match="Unable to open PDF") as encrypted:
        open_pdf(_pdf(tmp_path / "encrypted.pdf", encrypted=True), settings.limits)
    assert encrypted.value.code == "pdf-encrypted"

    with pytest.raises(InputError) as unreadable:
        path = tmp_path / "garbage.pdf"
        path.write_bytes(b"%PDF-1.7\ntruncated")
        open_pdf(path, settings.limits)
    assert unreadable.value.code == "pdf-unreadable"

    with pytest.raises(InputError) as too_many:
        open_pdf(_pdf(tmp_path / "many.pdf", pages=501), settings.limits)
    assert too_many.value.code == "pdf-too-many-pages"


def test_pdf_page_failure_threshold_warns_then_stops(tmp_path: Path) -> None:
    settings = load_settings(None, {})
    with open_pdf(_pdf(tmp_path / "pages.pdf", pages=20), settings.limits) as document:
        original = document._document.get_page

        def fail_first(index: int):
            if index == 0:
                raise RuntimeError("corrupt page")
            return original(index)

        document._document.get_page = fail_first
        assert document.chars(0) == []
        assert document.warnings == ["pdf-page-failed:0"]

    with open_pdf(_pdf(tmp_path / "broken.pdf", pages=3), settings.limits) as document:
        original = document._document.get_page

        def fail_first_page(index: int):
            if index == 0:
                raise RuntimeError("corrupt page")
            return original(index)

        document._document.get_page = fail_first_page
        with pytest.raises(ConversionError, match="too many unreadable") as broken:
            document.chars(0)
        assert broken.value.code == "pdf-too-broken"


def test_png_encoder_and_crop_prove_dimensions_and_y_flip(tmp_path: Path) -> None:
    for width, height in ((1, 1), (100, 50)):
        raw = bytes(index % 256 for index in range(width * height * 3))
        actual_width, actual_height, pixels = _png_dimensions_and_pixels(
            encode_png_rgb(width, height, raw)
        )
        assert (actual_width, actual_height, pixels) == (width, height, raw)

    path = tmp_path / "rectangle.pdf"
    document = canvas.Canvas(str(path), pagesize=(612, 792))
    document.setFillColorRGB(0, 0, 0)
    document.rect(100, 500, 200, 50, fill=1, stroke=0)
    document.showPage()
    document.save()
    settings = load_settings(None, {})
    with open_pdf(path, settings.limits) as pdfdoc:
        pixels = _png_dimensions_and_pixels(
            pdfdoc.bitmap(0, 1.0).crop_png((100, 500, 300, 550), 0)
        )[2]
    dark_ratio = sum(
        sum(pixels[index : index + 3]) < 90 for index in range(0, len(pixels), 3)
    ) / (len(pixels) / 3)
    assert dark_ratio > 0.95


class _CropPdf:
    path = Path("fixture.pdf")
    metadata_title = ""

    def __init__(self) -> None:
        self.crops: list[tuple[float, float, float, float]] = []

    def page_size(self, _page: int) -> tuple[float, float]:
        return 600.0, 800.0

    def bitmap(self, _page: int, _scale: float = 2.0) -> _CropPdf:
        return self

    def crop_png(self, bbox: tuple[float, float, float, float], pad_pt: float = 0) -> bytes:
        del pad_pt
        self.crops.append(bbox)
        return encode_png_rgb(1, 1, b"\xff\xff\xff")


def _raw(block_id: str, bbox: tuple[float, float, float, float], text: str = "x") -> RawBlock:
    return RawBlock(block_id, 0, bbox, text, 10.0, 1, 0, 10.0)


def _empty_result() -> SimpleNamespace:
    return SimpleNamespace(equations={}, assets={}, warnings=[])


def test_assembly_pairs_beside_figure_and_linked_table_body() -> None:
    pdf = _CropPdf()
    figure_body = _raw("figure-body", (40.0, 100.0, 250.0, 300.0), "art")
    figure_caption = _raw("figure-caption", (300.0, 160.0, 390.0, 190.0), "Figure 1")
    figure_seg = SegmentResult(
        {
            "figure-body": RoleInfo("figure_body"),
            "figure-caption": RoleInfo("figure_caption", number_text="1"),
        },
        [],
        ["figure-body", "figure-caption"],
    )
    assemble_pdf(
        figure_seg,
        [figure_body, figure_caption],
        _empty_result(),
        ([], {}, [], []),
        pdf,
        load_settings(None, {}),
    )
    assert pdf.crops == [(40.0, 100.0, 250.0, 300.0)]

    pdf.crops.clear()
    table_body = _raw("table-body", (100.0, 300.0, 500.0, 500.0), "cells")
    table_caption = _raw("table-caption", (100.0, 240.0, 500.0, 270.0), "Table 1")
    table_seg = SegmentResult(
        {
            "table-body": RoleInfo("table_body"),
            "table-caption": RoleInfo(
                "table_caption", number_text="1", links_to_block="table-body"
            ),
        },
        [],
        ["table-body", "table-caption"],
    )
    assemble_pdf(
        table_seg,
        [table_body, table_caption],
        _empty_result(),
        ([], {}, [], []),
        pdf,
        load_settings(None, {}),
    )
    assert pdf.crops == [(100.0, 300.0, 500.0, 500.0)]

    no_region = _CropPdf()
    no_region_seg = SegmentResult(
        {"caption": RoleInfo("figure_caption", number_text="2")}, [], ["caption"]
    )
    no_region_document = assemble_pdf(
        no_region_seg,
        [_raw("caption", (100.0, 240.0, 500.0, 270.0), "Figure 2")],
        _empty_result(),
        ([], {}, [], []),
        no_region,
        load_settings(None, {}),
    )
    assert no_region.crops == []
    assert any(item.code == "pdf-figure-region-missing" for item in no_region_document.warnings)


def test_three_column_detection_returns_unhandled_warning() -> None:
    lines: list[_Line] = []
    for x0 in (0.0, 400.0, 760.0):
        for index in range(20):
            y = 20.0 + index * 20.0
            lines.append(_Line([], (x0, y, x0 + 200.0, y + 10.0)))
    columns, warning = detect_columns(lines, 1000.0)
    assert len(columns) == 1 and warning == "layout-columns-unhandled"
    chars = [
        SimpleNamespace(
            text="x",
            bbox=(x0, 20.0 + index * 30.0 + offset, x0 + 200.0, 30.0 + index * 30.0 + offset),
            font_size=10.0,
        )
        for x0, offset in ((0.0, 0.0), (400.0, 8.0), (760.0, 16.0))
        for index in range(20)
    ]
    built = build_blocks([SimpleNamespace(page=0, width=1000.0, chars=chars)])
    assert built[0].warnings == ("layout-columns-unhandled",)


def test_segment_keeps_validated_model_reading_order_and_ctx_is_omitted() -> None:
    blocks = [
        _raw("b1", (40.0, 500.0, 540.0, 520.0), "first"),
        _raw("b2", (40.0, 450.0, 540.0, 470.0), "second"),
    ]

    class Ordered:
        settings = SimpleNamespace()

        def complete(self, _purpose, messages, _schema, **_kwargs):
            assert "read-only" in messages[-1]["content"]
            return PdfSegmentV1(
                blocks=[
                    {"id": "b1", "role": "paragraph"},
                    {"id": "b2", "role": "paragraph"},
                ],
                section_order=["b2", "b1"],
            )

    # The prompt contract itself must tell the model that context is read-only.
    from paperdeck.llm.prompts import load_prompt

    prompt = load_prompt("segment", blocks="ctx-b0")
    assert "ctx-" in prompt and "read-only" in prompt and "section_order" in prompt
    result = segment(blocks, Ordered())
    assert result.order == ["b2", "b1"]


def test_assembly_uses_segment_paragraph_merge_and_real_pdf_metadata(tmp_path: Path) -> None:
    path = _pdf(tmp_path / "metadata.pdf")
    # Recreate with a title because _pdf intentionally has no metadata title.
    document = canvas.Canvas(str(path), pagesize=(612, 792))
    document.setTitle("Metadata Title")
    document.showPage()
    document.save()
    settings = load_settings(None, {})
    with open_pdf(path, settings.limits) as pdfdoc:
        assert pdfdoc.metadata_title == "Metadata Title"

    first = _raw("b1", (40.0, 500.0, 540.0, 520.0), "analy-")
    second = _raw("b2", (40.0, 470.0, 540.0, 490.0), "sis")
    seg = SegmentResult(
        {"b1": RoleInfo("paragraph"), "b2": RoleInfo("paragraph")},
        [],
        ["b1", "b2"],
        paragraphs=[("b1", "analysis", ["b1", "b2"])],
    )
    result = assemble_pdf(
        seg,
        [first, second],
        _empty_result(),
        ([], {}, [], []),
        SimpleNamespace(path=path, metadata_title="Metadata Title"),
        settings,
    )
    assert len(result.body) == 1
    assert result.body[0].content[0].text == "analysis"


def test_citation_mapper_receives_normalized_bibliography_text() -> None:
    seen: list[str] = []

    class Mapper:
        def complete(self, _purpose, messages, _schema, **_kwargs):
            seen.append(str(messages[-1]["content"]))
            return SimpleNamespace(mappings=[])

    bib = [BibEntry(id="bib-1", content=[Text(text="Smith, A. 2020. Paper")], urls=[])]
    link_citations(["(Smith 2020)"], bib, Mapper())
    assert "Smith, A. 2020. Paper" in seen[0]
