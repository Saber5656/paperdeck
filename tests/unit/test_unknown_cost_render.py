from bs4 import BeautifulSoup

from paperdeck.config import load_settings
from paperdeck.ir.model import LlmProvenance
from paperdeck.render.html import render
from paperdeck.render.validate import validate_html
from tests.fixtures.reader import document


def test_unknown_model_cost_renders_as_unknown():
    doc = document()
    doc = doc.model_copy(
        update={
            "provenance": doc.provenance.model_copy(
                update={
                    "llm": LlmProvenance(model="unpriced-model", cost_usd=None),
                }
            )
        }
    )
    html = render(doc, load_settings(None, {}))
    assert (
        "cost unavailable" in BeautifulSoup(html, "html.parser").select_one(".pd-provenance").text
    )
    assert validate_html(html) == []
