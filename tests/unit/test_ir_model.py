import pytest
from pydantic import ValidationError

from paperdeck.ir.model import Equation, ExtLink, Paragraph, Text


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
