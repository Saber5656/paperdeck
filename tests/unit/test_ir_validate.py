import pytest

from paperdeck.config import LimitsSettings
from paperdeck.errors import ConversionError
from paperdeck.ir.model import Document, Paragraph, RefLink, Text
from paperdeck.ir.validate import iter_blocks, validate_document


def make_doc() -> Document:
    return Document(
        source={"kind": "local", "original": "x.pdf"},
        provenance={
            "engine": "pdf",
            "engine_versions": {},
            "created_at": "2026-01-01T00:00:00Z",
            "fallbacks": [],
        },
        meta={"title": [Text(text="Title")], "authors": [], "links": []},
        body=[Paragraph(id="para-1", content=[RefLink(target_id="", kind="sec", text="?")])],
    )


def test_allocator_and_walker_and_unresolved_warning() -> None:
    doc = make_doc()
    assert [block.id for block in iter_blocks(doc)] == ["para-1"]
    warnings = validate_document(doc, LimitsSettings())
    assert any(item.code == "unresolved-ref" for item in warnings)


def test_unknown_reference_and_asset_fail() -> None:
    doc = Document.model_validate(
        make_doc().model_dump()
        | {
            "body": [
                {
                    "type": "paragraph",
                    "id": "para-1",
                    "content": [
                        {
                            "type": "ref_link",
                            "target_id": "missing",
                            "kind": "sec",
                            "text": "x",
                        }
                    ],
                }
            ]
        }
    )
    with pytest.raises(ConversionError, match="missing"):
        validate_document(doc, LimitsSettings())
