from pydantic import ValidationError
import pytest

from paperdeck.llm.schemas import (
    PdfBibV1,
    PdfCiteMapV1,
    PdfEquationLatexV1,
    PdfSegmentV1,
    get,
)


def test_registry_and_valid_payloads() -> None:
    assert get("pdf_segment.v1")[1] == "v1"
    PdfSegmentV1(blocks=[{"id": "b1", "role": "heading", "level": 1}], section_order=["b1"])
    PdfEquationLatexV1(latex=r"x^2", confidence=0.8)
    PdfBibV1(entries=[{"text": "A", "urls": ["https://example.test/a"]}])
    PdfCiteMapV1(mappings=[{"marker": "(Smith, 2020)", "entry_indices": [0]}])


@pytest.mark.parametrize(
    "payload",
    [
        {"blocks": [{"id": "b1", "role": "heading"}], "section_order": []},
        {"blocks": [{"id": "b1", "role": "paragraph", "extra": 1}], "section_order": []},
    ],
)
def test_segment_is_bounded_and_strict(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        PdfSegmentV1.model_validate(payload)


def test_bib_rejects_unsafe_url() -> None:
    with pytest.raises(ValidationError):
        PdfBibV1(entries=[{"text": "bad", "urls": ["javascript:alert(1)"]}])
