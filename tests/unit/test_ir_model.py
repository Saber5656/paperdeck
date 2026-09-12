import pytest
from pydantic import ValidationError

from paperdeck.ir.model import (
    Asset,
    AssetOrigin,
    BibUrl,
    Cell,
    Equation,
    ExtLink,
    Paragraph,
    Table,
    Text,
)


def test_discriminated_inline_parses() -> None:
    node = Paragraph.model_validate(
        {
            "type": "paragraph",
            "id": "para-1",
            "content": [{"type": "text", "text": "x"}],
        }
    )
    assert isinstance(node.content[0], Text)


def test_equation_invariants() -> None:
    with pytest.raises(ValidationError, match="latex"):
        Equation(id="eq-1", content_kind="latex", latex="", latex_verified=False)


def test_extlink_and_extra_are_rejected() -> None:
    with pytest.raises(ValidationError):
        ExtLink(url="javascript:alert(1)", content=[])
    with pytest.raises(ValidationError):
        Text(text="x", extra="bad")


@pytest.mark.parametrize("scheme", ["javascript", "data", "file", "vbscript"])
def test_unsafe_url_schemes_are_rejected_by_both_link_models(scheme: str) -> None:
    with pytest.raises(ValidationError):
        ExtLink(url=f"{scheme}:payload", content=[])
    with pytest.raises(ValidationError):
        BibUrl(url=f"{scheme}:payload", kind="generic")


@pytest.mark.parametrize(
    ("factory", "field"),
    [
        (
            lambda: Equation(id="eq", content_kind="latex", latex="x", latex_verified=False),
            "latex_verified",
        ),
        (
            lambda: Equation(id="eq", content_kind="image", asset_id=None),
            "asset_id",
        ),
        (
            lambda: Equation(
                id="eq", content_kind="latex", latex="x", latex_verified=True, confidence=2
            ),
            "confidence",
        ),
        (
            lambda: Table(id="tab", content_kind="grid", rows=None, caption=[]),
            "rows",
        ),
        (
            lambda: Table(id="tab", content_kind="image", asset_id=None, caption=[]),
            "asset_id",
        ),
        (lambda: Cell(content=[], colspan=0), "colspan"),
        (lambda: Cell(content=[], rowspan=0), "rowspan"),
        (
            lambda: Asset(
                id="asset",
                mime="text/plain",
                data_b64="aGk=",
                origin=AssetOrigin(engine="test"),
            ),
            "mime",
        ),
    ],
)
def test_model_invariant_errors_name_the_rejected_field(factory, field: str) -> None:
    with pytest.raises(ValidationError, match=field):
        factory()
