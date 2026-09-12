from pathlib import Path

from reportlab.pdfgen import canvas

from paperdeck.config import load_settings
from paperdeck.engines.pdf.blocks import build_blocks
from paperdeck.engines.pdf.equations import process_equations
from paperdeck.engines.pdf.extract import open_pdf
from paperdeck.engines.pdf.segment import RoleInfo, SegmentResult
from paperdeck.ir.anchors import AnchorAllocator
from paperdeck.llm.schemas import PdfEquationLatexV1


class FakeLlm:
    def __init__(self, latex: str):
        self.latex = latex
        self.calls = 0

    def complete(self, *_args, **_kwargs):
        self.calls += 1
        return PdfEquationLatexV1(latex=self.latex, confidence=0.4)


class Ledger:
    def __init__(self, allowed=True):
        self.allowed = allowed

    def remaining_allows(self, _estimate):
        return self.allowed


def test_equation_crop_and_unverified_transcription(tmp_path: Path) -> None:
    path = tmp_path / "equation.pdf"
    doc = canvas.Canvas(str(path), pagesize=(612, 792))
    doc.rect(100, 500, 200, 50, fill=1)
    doc.setFillColorRGB(1, 1, 1)
    doc.drawString(120, 520, "x = y")
    doc.showPage()
    doc.save()
    settings = load_settings(None, {"llm.base_url": "http://localhost:11434/v1"})
    llm = FakeLlm(r"\href{javascript:x}{y}")
    with open_pdf(path, settings.limits) as pdfdoc:
        blocks = build_blocks([pdfdoc.page_chars(0)])
        block = blocks[0]
        seg = SegmentResult({block.id: RoleInfo("display_equation")}, [], [block.id])
        result = process_equations(seg, blocks, pdfdoc, llm, Ledger(), AnchorAllocator())
    assert result.assets and result.equations[block.id].latex is None
    assert any(item.startswith("vlm-latex-rejected") for item in result.warnings)
    assert llm.calls == 1


def test_budget_degradation_keeps_image_asset(tmp_path: Path) -> None:
    path = tmp_path / "equation.pdf"
    doc = canvas.Canvas(str(path), pagesize=(612, 792))
    doc.drawString(100, 500, "x = y")
    doc.showPage()
    doc.save()
    settings = load_settings(None, {"llm.base_url": "http://localhost:11434/v1"})
    llm = FakeLlm("x")
    with open_pdf(path, settings.limits) as pdfdoc:
        blocks = build_blocks([pdfdoc.page_chars(0)])
        block = blocks[0]
        seg = SegmentResult({block.id: RoleInfo("display_equation")}, [], [block.id])
        result = process_equations(seg, blocks, pdfdoc, llm, Ledger(False), AnchorAllocator())
    assert result.assets and result.equations[block.id].latex is None
    assert "vlm-budget-exhausted" in result.warnings
    assert llm.calls == 0
