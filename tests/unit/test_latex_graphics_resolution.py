from pathlib import Path

import pytest

from paperdeck.config import LimitsSettings
from paperdeck.engines.latex.ast_map import MappedDoc
from paperdeck.engines.latex.graphics import jpeg_dimensions, png_dimensions, resolve_graphics
from paperdeck.engines.latex.project import LatexProject
from paperdeck.errors import SecurityError
from paperdeck.ir.model import Figure, Quote


def _mapped(target: str) -> MappedDoc:
    figure = Figure(id="fig-1", caption=[])
    return MappedDoc([figure], [], [], None, [], [], {}, {"fig-1": target}, {}, set())


def _project(root: Path, preamble: str = "") -> LatexProject:
    main = root / "main.tex"
    main.write_text("", encoding="utf-8")
    return LatexProject(root, main, main, preamble, [])


def test_graphics_resolves_graphicspath_and_rejects_bad_magic(tmp_path: Path) -> None:
    (tmp_path / "figures").mkdir()
    (tmp_path / "figures" / "plot.png").write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        + (2).to_bytes(4, "big")
        + (3).to_bytes(4, "big")
        + b"\x08\x02\x00\x00\x00"
    )
    mapped = _mapped("plot")
    assets, warnings = resolve_graphics(
        mapped, _project(tmp_path, r"\graphicspath{{figures/}}"), LimitsSettings()
    )
    assert assets["asset-1"].width_px == 2
    assert mapped.body[0].asset_id == "asset-1"
    assert not warnings

    (tmp_path / "figures" / "bad.png").write_bytes(b"not png")
    with pytest.raises(SecurityError, match="magic"):
        resolve_graphics(_mapped("figures/bad.png"), _project(tmp_path), LimitsSettings())


def test_graphics_missing_and_unsupported_are_placeholders(tmp_path: Path) -> None:
    for target, code in (
        ("missing", "figure-format-unsupported"),
        ("plot.svg", "figure-format-unsupported"),
    ):
        if target.endswith(".svg"):
            (tmp_path / target).write_text("<svg/>", encoding="utf-8")
        mapped = _mapped(target)
        _, warnings = resolve_graphics(mapped, _project(tmp_path), LimitsSettings())
        assert warnings[0].code == code
        assert mapped.body[0].alt_text and "unavailable" in mapped.body[0].alt_text


def test_graphics_escape_is_security_error(tmp_path: Path) -> None:
    mapped = _mapped("../secret.png")
    with pytest.raises(SecurityError, match="escapes"):
        resolve_graphics(mapped, _project(tmp_path), LimitsSettings())


def test_graphics_dimension_parsers_reject_truncated_data() -> None:
    assert png_dimensions(b"\x89PNG\r\n\x1a\n") is None
    assert jpeg_dimensions(b"\xff\xd8\xff\xc0\x00") is None
    assert jpeg_dimensions(b"not jpeg") is None
    jpeg = b"\xff\xd8\xff\xc0\x00\x0b\x08\x00\x02\x00\x03\x00\x00\x00\x00"
    assert jpeg_dimensions(jpeg) == (3, 2)


def test_graphics_replaces_oversized_and_eps_figures(tmp_path: Path) -> None:
    oversized = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        + (5000).to_bytes(4, "big")
        + (2).to_bytes(4, "big")
        + b"\x08\x02\x00\x00\x00"
    )
    (tmp_path / "large.png").write_bytes(oversized)
    mapped = _mapped("large.png")
    _, warnings = resolve_graphics(mapped, _project(tmp_path), LimitsSettings())
    assert warnings[0].code == "figure-too-large"
    assert mapped.body[0].asset_id is None

    (tmp_path / "plot.eps").write_text("%!PS-Adobe-3.0", encoding="ascii")
    mapped = _mapped("plot.eps")
    _, warnings = resolve_graphics(mapped, _project(tmp_path), LimitsSettings())
    assert warnings[0].code == "figure-eps-unsupported"
    assert mapped.body[0].asset_id is None


def test_graphics_bad_pdf_is_reported_without_crashing(tmp_path: Path) -> None:
    (tmp_path / "plot.pdf").write_bytes(b"%PDF-1.7\nnot a real document")
    mapped = _mapped("plot.pdf")
    _, warnings = resolve_graphics(mapped, _project(tmp_path), LimitsSettings())
    assert warnings[0].code == "figure-pdf-failed"


def test_graphics_replaces_figures_inside_quotes(tmp_path: Path) -> None:
    quote = Quote(id="quote-1", content=[Figure(id="fig-1", caption=[])])
    mapped = MappedDoc([quote], [], [], None, [], [], {}, {"fig-1": "missing"}, {}, set())
    _, warnings = resolve_graphics(mapped, _project(tmp_path), LimitsSettings())
    assert warnings[0].code == "figure-format-unsupported"
    assert mapped.body[0].content[0].alt_text is not None
