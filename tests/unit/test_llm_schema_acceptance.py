import json
from importlib.resources import files

import pytest
from pydantic import ValidationError

from paperdeck.llm.schemas import PdfBibV1, PdfCiteMapV1, PdfEquationLatexV1, PdfSegmentV1


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (PdfEquationLatexV1, {"latex": "x" * 4001, "confidence": 0.5}),
        (PdfEquationLatexV1, {"latex": "x", "confidence": -0.1}),
        (PdfEquationLatexV1, {"latex": "x", "confidence": 1.1}),
        (PdfEquationLatexV1, {"latex": "x", "confidence": 0.5, "execute": "untrusted"}),
        (
            PdfSegmentV1,
            {"blocks": [{"id": "b", "role": "paragraph", "level": 1}], "section_order": []},
        ),
        (PdfSegmentV1, {"blocks": [], "section_order": [], "notes": "x" * 501}),
        (PdfSegmentV1, {"blocks": [], "section_order": ["b"] * 10001}),
        (PdfBibV1, {"entries": [{"text": "x" * 2001}]}),
        (PdfBibV1, {"entries": [{"text": "x", "urls": ["https://example.com"] * 6}]}),
        (PdfBibV1, {"entries": [{"text": "x"}] * 501}),
        (PdfCiteMapV1, {"mappings": [{"marker": "x" * 121, "entry_indices": []}]}),
        (PdfCiteMapV1, {"mappings": [{"marker": "x", "entry_indices": [-1]}]}),
        (PdfCiteMapV1, {"mappings": [{"marker": "x", "entry_indices": list(range(21))}]}),
        (PdfCiteMapV1, {"mappings": [{"marker": "x", "entry_indices": []}] * 1001}),
    ],
)
def test_model_response_limits_reject_untrusted_oversized_or_invalid_data(model, payload):
    with pytest.raises(ValidationError):
        model.model_validate(payload)


@pytest.mark.parametrize(
    ("name", "model"),
    [
        ("pdf_segment.v1", PdfSegmentV1),
        ("pdf_equation_latex.v1", PdfEquationLatexV1),
        ("pdf_bib.v1", PdfBibV1),
        ("pdf_cite_map.v1", PdfCiteMapV1),
    ],
)
def test_all_response_schemas_match_the_packaged_contract(name, model):
    actual = files("paperdeck.llm.schemas").joinpath(name + ".json").read_text()
    expected = json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2) + "\n"
    assert actual == expected
