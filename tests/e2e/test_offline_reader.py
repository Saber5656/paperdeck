import re

import pytest
from playwright.sync_api import sync_playwright

from paperdeck.config import load_settings
from paperdeck.ir.model import Equation, Math, Paragraph, Text
from paperdeck.render.html import render
from tests.fixtures.reader import document

pytestmark = pytest.mark.playwright


@pytest.mark.parametrize("browser_name", ["chromium", "webkit"])
def test_production_html_opens_offline_without_requests(browser_name, tmp_path):
    doc = document().model_copy(
        update={
            "macros": {"\\R": "\\mathbb{R}"},
            "body": [
                Paragraph(
                    id="para-1",
                    content=[Text(text="An offline mathematical paper "), Math(latex=r"\R^2")],
                ),
                Equation(
                    id="eq-1",
                    content_kind="latex",
                    latex=r"\href{javascript:alert(1)}{x}",
                    latex_verified=True,
                ),
            ],
        }
    )
    path = tmp_path / "reader.html"
    path.write_text(render(doc, load_settings(None, {})))
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        # WebKit's offline emulation rejects file navigation itself. Block all HTTP
        # transports there; Chromium supports offline file navigation directly.
        context = browser.new_context(
            offline=browser_name == "chromium", viewport={"width": 1440, "height": 1024}
        )
        context.route(re.compile(r"^https?://"), lambda route: route.abort())
        page = context.new_page()
        requests = []
        errors = []
        page.on(
            "request",
            lambda request: (
                requests.append(request.url)
                if request.url.startswith(("http:", "https:"))
                else None
            ),
        )
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(path.as_uri())
        assert page.locator(".pd-math .katex").count() == 1
        assert page.locator("#eq-1 a").count() == 0
        assert requests == []
        assert errors == []
        assert page.locator("html").get_attribute("data-theme") in {"light", "dark"}
        page.set_viewport_size({"width": 320, "height": 640})
        assert (
            page.locator("#pd-help-toggle").bounding_box()["x"]
            + page.locator("#pd-help-toggle").bounding_box()["width"]
            <= 320
        )
        context.close()
        browser.close()
