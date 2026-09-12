"""Browser acceptance against the actual CLI's converted LaTeX demonstration."""

import subprocess
import sys
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright

pytestmark = [pytest.mark.pandoc, pytest.mark.playwright]


@pytest.fixture(scope="module")
def converted_paper(tmp_path_factory):
    output = tmp_path_factory.mktemp("converted-viewer") / "paper.html"
    source = Path(__file__).resolve().parents[2] / "examples/reading-demo.tex"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "paperdeck.cli",
            "-q",
            "convert",
            str(source),
            "--offline",
            "-o",
            str(output),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(output)
    return output


@pytest.fixture(params=["chromium", "webkit"])
def converted_page(request, converted_paper):
    with sync_playwright() as p:
        browser = getattr(p, request.param).launch()
        page = browser.new_page(viewport={"width": 1440, "height": 800}, reduced_motion="reduce")
        errors, requests = [], []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on(
            "request", lambda req: requests.append(req.url) if req.url.startswith("http") else None
        )
        page.goto(converted_paper.as_uri())
        yield page
        assert errors == []
        assert requests == []
        browser.close()


def test_converted_references_theme_position_and_help(converted_page):
    page = converted_page
    reference = page.locator('main a[data-kind="eq"][href="#eq-1"]').last
    reference.scroll_into_view_if_needed()
    start = page.evaluate("scrollY")
    reference.focus()
    expect(page.locator("#pd-popup")).to_be_visible()
    assert page.locator("#pd-popup .pd-eq-number").inner_text() == "(1)"
    assert page.locator("#pd-popup .katex").count() == 1
    assert page.locator("#pd-popup [id]").count() == 0
    reference.click()
    page.keyboard.press("Backspace")
    page.wait_for_function(f"Math.abs(scrollY - {start}) < 3")
    page.locator('#pd-toc a[href="#sec-6"]').click()
    expect(page.locator('#pd-toc a[href="#sec-6"]')).to_have_attribute("aria-current", "location")
    page.keyboard.press("d")
    page.keyboard.press("d")
    assert page.locator("html").get_attribute("data-theme") == "dark"
    page.wait_for_timeout(650)
    saved = page.evaluate("scrollY")
    page.reload()
    assert page.locator("html").get_attribute("data-theme") == "dark"
    page.wait_for_function(f"Math.abs(scrollY - {saved}) < 350")
    page.locator("#pd-help-toggle").click()
    assert page.locator("#pd-help tr").count() == 7
    for _ in range(9):
        page.keyboard.press("Tab")
        assert page.evaluate("document.getElementById('pd-help').contains(document.activeElement)")
    page.keyboard.press("Escape")
    expect(page.locator("#pd-help-toggle")).to_be_focused()
    page.emulate_media(media="print")
    expect(page.locator("#pd-header")).not_to_be_visible()


def test_converted_deep_link_and_footnote(converted_page, converted_paper):
    page = converted_page
    page.goto(converted_paper.as_uri() + "#eq-2-2")
    assert page.locator("#eq-2-2 .pd-eq-number").inner_text() == "(3)"
    page.wait_for_function(
        "Math.abs(document.getElementById('eq-2-2').getBoundingClientRect().top - 72) < 5"
    )
    assert page.locator("#eq-2-2 .katex").count() == 1
    note = page.locator('a[data-kind="fn"]')
    note.scroll_into_view_if_needed()
    note.focus()
    expect(page.locator("#pd-popup")).to_contain_text("fictional demonstration")
