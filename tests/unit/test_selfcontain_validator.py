import base64
import hashlib

import pytest

from paperdeck.render.validate import csp_for_scripts, validate_html


def page(fragment="", script="const x = 1;"):
    return (
        '<html><head><meta http-equiv="Content-Security-Policy" content="'
        + csp_for_scripts([script])
        + '"></head><body>'
        + fragment
        + "<script>"
        + script
        + "</script></body></html>"
    )


@pytest.mark.parametrize(
    ("fragment", "code"),
    [
        ('<img src="https://tracker.example/a">', "external-resource"),
        ('<img src="//cdn.example/a">', "external-resource"),
        ('<img src="relative.png">', "external-resource"),
        ('<a href="javascript:alert(1)">x</a>', "external-resource"),
        ('<a href="https://example.com">x</a>', "external-resource"),
        ('<link href="x">', "forbidden-element"),
        ('<meta http-equiv="refresh" content="0; url=https://evil.com">', "forbidden-element"),
        ("<form></form>", "forbidden-element"),
        ('<div onclick="alert(1)">x</div>', "inline-handler"),
        ("<style>div {background:url( 'evil.png' )}</style>", "style-url"),
        ('<style>@import "https://example.com/a.css";</style>', "style-url"),
        ('<script src="https://example.com/a.js"></script>', "script-external"),
        ('<script type="module">1</script>', "script-type"),
        ("<svg></svg>", "svg-inline"),
        ('<img srcset="data:image/png;base64,abc 1x, https://evil.com/a 2x">', "external-resource"),
    ],
)
def test_reject_active_content(fragment, code):
    assert code in {v.code for v in validate_html(page(fragment))}


def test_green_and_tamper():
    html = page(
        '<a rel="noopener noreferrer" href="https://example.com">link</a>'
        '<a href="#eq-1">ref</a>'
        '<img src="data:image/png;base64,eA==">'
    )
    assert validate_html(html) == []
    assert "csp-mismatch" in {
        v.code for v in validate_html(html.replace("const x = 1;", "const x = 2;"))
    }
    assert "csp-missing" in {v.code for v in validate_html("<html/>")}
    digest = base64.b64encode(hashlib.sha256(b"const x = 1;").digest()).decode()
    assert "'sha256-" + digest + "'" in html
