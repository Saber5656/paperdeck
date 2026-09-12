from pathlib import Path

from paperdeck.config import load_settings
from paperdeck.engines.pdf.extract import open_pdf


def make_fixture(directory: Path) -> Path:
    from reportlab.pdfgen import canvas

    path = directory / "two-page.pdf"
    doc = canvas.Canvas(str(path), pagesize=(612, 792))
    for page in range(2):
        doc.drawString(72, 720, f"Fixture page {page + 1}")
        doc.showPage()
    doc.save()
    return path


def test_reportlab_fixture_extracts_chars_and_png(tmp_path: Path) -> None:
    path = make_fixture(tmp_path)
    settings = load_settings(None, {})
    with open_pdf(path, settings.limits) as doc:
        assert doc.page_count == 2
        assert doc.chars(0)
        png = doc.bitmap(0).crop_png((65, 680, 300, 735))
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
