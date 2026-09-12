import os

import pytest
from playwright.sync_api import expect, sync_playwright

from tests.e2e.test_pipeline_pdf import _config, _paper, _run
from tests.security.fake_llm import FakeLLM

pytestmark = pytest.mark.playwright


def test_converted_pdf_crop_citation_and_offline_browser(tmp_path):
    pdf, output, config = (tmp_path / name for name in ("paper.pdf", "paper.html", "config.toml"))
    with FakeLLM() as server:
        _paper(pdf, "A paragraph cites [1]. <script>alert(1)</script>")
        _config(config, server.base_url)
        result = _run(
            ["--config", str(config), "-q", "convert", str(pdf), "--yes", "-o", str(output)],
            env={**os.environ, "FAKE_API_KEY": "dummy-key"},
        )
        assert result.returncode == 0, result.stderr
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(offline=True)
        page = context.new_page()
        requests, errors = [], []
        page.on(
            "request", lambda req: requests.append(req.url) if req.url.startswith("http") else None
        )
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(output.as_uri())
        assert page.locator(".pd-eq img").count() >= 1
        assert page.locator(".pd-copy-latex").count() >= 1
        assert "unverified" in page.locator(".pd-copy-latex").first.inner_text().lower()
        citation = page.locator('main a[data-kind="bib"]').first
        citation.scroll_into_view_if_needed()
        citation.focus()
        expect(page.locator("#pd-popup")).to_be_visible()
        expect(page.locator("#pd-popup")).to_contain_text("Example reference")
        assert requests == [] and errors == []
        browser.close()
