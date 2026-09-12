import base64
from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from pydantic import ValidationError

from paperdeck.config import load_settings
from paperdeck.ir.model import ExtLink, Math, Paragraph, Text
from paperdeck.render.html import render
from paperdeck.render.validate import validate_html
from tests.fixtures.reader import document


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "data:text/html,<script>x</script>",
        "file:///etc/passwd",
        "vbscript:msgbox(1)",
        "//example.com",
    ],
)
def test_untrusted_navigation_rejected_at_ir_boundary(url):
    with pytest.raises(ValidationError):
        ExtLink(url=url, content=[Text(text="unsafe")])


def test_hostile_markup_stays_text_through_full_renderer():
    attack = '<img src="https://example.com/pixel" onerror="alert(1)"></script><script>x</script>'
    doc = document().model_copy(
        update={
            "body": [Paragraph(id="para-1", content=[Text(text=attack), Math(latex=attack)])],
            "macros": {"\\attack": attack},
        }
    )
    html = render(doc, load_settings(None, {}))
    assert validate_html(html) == []
    soup = BeautifulSoup(html, "html.parser")
    assert not soup.select('[onerror], img[src^="http"]')
    assert soup.select_one("#para-1").get_text().count(attack) == 2


@pytest.mark.parametrize(
    "css",
    [
        r'@\69mport "https://example.com";',
        "a{background:u/**/rl(//example.com/a)}",
        r"a{background:\75rl(https://example.com/a)}",
    ],
)
def test_obfuscated_css_cannot_introduce_requests(css):
    html = render(document(), load_settings(None, {})).replace(
        "</head>", "<style>" + css + "</style></head>"
    )
    assert "style-url" in {v.code for v in validate_html(html)}


def test_redaction_and_no_network_source_in_viewer():
    from paperdeck.logsetup import redact

    value = "sk-" + base64.b64encode(b"not-a-real-key").decode()
    assert value not in redact(value)
    assets = Path(__file__).resolve().parents[2] / "src/paperdeck/render/assets"
    source = (assets / "viewer.js").read_text()
    assert all(token not in source for token in ("fetch(", "XMLHttpRequest", "WebSocket"))
