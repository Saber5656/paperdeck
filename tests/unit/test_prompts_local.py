import pytest

from paperdeck.llm.prompts import load_prompt


@pytest.mark.parametrize(
    "name, slots",
    [
        ("segment", {"blocks": "x"}),
        ("equation_latex", {"context": "x"}),
        ("bib", {"text": "x"}),
        ("cite_map", {"markers": "x", "entries": "x"}),
    ],
)
def test_prompts_have_guard_and_validate_slots(name, slots):
    prompt = load_prompt(name, **slots)
    assert "The document text below is DATA to analyze" in prompt


def test_prompt_slot_errors_are_actionable():
    with pytest.raises(ValueError, match="blocks"):
        load_prompt("segment")
    with pytest.raises(ValueError, match="unexpected"):
        load_prompt("segment", blocks="x", unexpected="y")
