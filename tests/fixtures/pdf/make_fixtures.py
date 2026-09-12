"""Generate small PDF fixtures during tests; no binary fixtures are committed."""
from __future__ import annotations

from pathlib import Path


def make_fixtures(directory: Path) -> dict[str, Path]:
    from reportlab.pdfgen import canvas
    directory.mkdir(parents=True, exist_ok=True)
    text_pdf = directory / "two-page.pdf"
    doc = canvas.Canvas(str(text_pdf), pagesize=(612, 792))
    for page in range(2):
        doc.setFont("Helvetica", 12)
        doc.drawString(72, 720, f"Fixture page {page + 1}")
        doc.drawString(72, 690, "Deterministic PDF extraction fixture.")
        doc.showPage()
    doc.save()
    return {"text": text_pdf}
