from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright

pytestmark = pytest.mark.playwright
ASSETS = Path(__file__).resolve().parents[2] / "src/paperdeck/render/assets"


@pytest.fixture(params=["chromium", "webkit"])
def page(request, tmp_path):
    body = """<header id="pd-header">
<button id="pd-toc-toggle">Contents</button>
<button id="pd-theme-toggle">Theme</button>
<button id="pd-help-toggle">Help</button>
</header>
<nav id="pd-toc" aria-label="Table of contents">
<ol>
<li data-level="1">
<a class="pd-ref pd-toc-link" href="#sec-1">Introduction</a>
<ol></ol>
</li>
<li data-level="1">
<a class="pd-ref pd-toc-link" href="#sec-2">Method</a>
<ol><li data-level="2"><a href="#sec-2">A subsection</a></li></ol>
</li>
</ol>
</nav>
<main id="pd-content">
<section id="sec-1">
<h2>Introduction</h2>
<p id="para-1">See <a class="pd-ref" data-kind="eq" href="#eq-2">equation (2)</a>.</p>
<div class="pd-eq" id="eq-1" data-latex="x^2">
<span class="pd-eq-number">(1)</span>
</div>"""
    body += "".join(
        f'<p id="para-{i}">A research paragraph with enough content to exercise scrolling. '
        + "The model preserves evidence and reference context. " * 12
        + "</p>"
        for i in range(2, 20)
    )
    body += """</section>
<section id="sec-2">
<h2>Method</h2>
<div class="pd-eq" id="eq-2" data-latex="\\R^2">
<span class="pd-eq-number">(2)</span>
</div>
<p id="para-21">End of paper.</p>
</section>
</main>"""
    scripts = (
        '<script id="pd-data" type="application/json">'
        '{"docId":"test-document","macros":{"\\\\R":"\\\\mathbb{R}"}}</script>'
    )
    for file in ("theme_bootstrap.js", "vendor/katex/katex.min.js", "viewer.js"):
        scripts += "<script>" + (ASSETS / file).read_text() + "</script>"
    file = tmp_path / "viewer.html"
    file.write_text(
        "<!doctype html><html><head><style>"
        + (ASSETS / "viewer.css").read_text()
        + (ASSETS / "vendor/katex/katex.min.css").read_text()
        + "</style></head><body>"
        + body
        + scripts
        + "</body></html>"
    )
    with sync_playwright() as p:
        browser = getattr(p, request.param).launch()
        tab = browser.new_page(viewport={"width": 1440, "height": 1024}, reduced_motion="reduce")
        errors = []
        tab.on("pageerror", lambda err: errors.append(str(err)))
        tab.goto(file.as_uri())
        yield tab
        assert errors == []
        browser.close()


def test_math_popup_jump_back(page):
    assert page.locator("#eq-1 .katex").count() == 1
    assert page.locator("#eq-1 .pd-eq-number").inner_text() == "(1)"
    link = page.locator("#para-1 .pd-ref")
    link.focus()
    expect(page.locator("#pd-popup .katex")).to_have_count(1)
    assert link.get_attribute("aria-describedby") == "pd-popup"
    assert page.locator("#pd-popup [id]").count() == 0
    page.keyboard.press("Escape")
    assert not page.locator("#pd-popup").is_visible()
    start = page.evaluate("scrollY")
    link.click()
    page.wait_for_function("scrollY > 1000")
    assert page.locator("#pd-back").is_visible()
    assert page.locator("#eq-2 .katex").count() == 1
    page.locator("#pd-back").click()
    page.wait_for_function(f"Math.abs(scrollY - {start}) < 2")
    assert not page.locator("#pd-back").is_visible()


def test_theme_keyboard_help_responsive_print(page):
    assert page.locator("#pd-toc .pd-disclosure").count() == 1
    disclosure = page.locator("#pd-toc .pd-disclosure")
    assert disclosure.get_attribute("aria-expanded") == "true"
    disclosure.click()
    assert not page.get_by_text("A subsection", exact=True).is_visible()
    disclosure.click()
    assert page.get_by_text("A subsection", exact=True).is_visible()
    page.locator("#pd-theme-toggle").click()
    assert page.locator("html").get_attribute("data-theme-mode") == "light"
    page.keyboard.press("d")
    assert page.locator("html").get_attribute("data-theme") == "dark"
    page.keyboard.press("?")
    assert page.locator("#pd-help").is_visible()
    mode = page.locator("html").get_attribute("data-theme-mode")
    page.keyboard.press("d")
    assert page.locator("html").get_attribute("data-theme-mode") == mode
    page.keyboard.press("Escape")
    assert not page.locator("#pd-help").is_visible()
    page.set_viewport_size({"width": 800, "height": 700})
    page.wait_for_function("!document.body.classList.contains('pd-toc-open')")
    page.locator("#pd-toc-toggle").click()
    page.locator('#pd-toc a.pd-toc-link[href="#sec-2"]').click()
    assert not page.locator("#pd-toc").is_visible()
    page.emulate_media(media="print")
    assert not page.locator("#pd-header").is_visible()


def test_position_restore_and_top(page):
    page.evaluate("window.scrollTo(0, 2600)")
    page.wait_for_timeout(650)
    saved = page.evaluate("scrollY")
    page.reload()
    page.wait_for_function("scrollY > 1500")
    assert abs(page.evaluate("scrollY") - saved) < 350
    assert page.locator("#pd-toast").is_visible()
    page.keyboard.press("T")
    page.wait_for_function("scrollY === 0")
    page.reload()
    assert page.evaluate("scrollY") == 0


def test_keyboard_sections_guards_and_duplicate_registry(page):
    page.keyboard.press("j")
    assert page.locator("#sec-1 h2").bounding_box()["y"] >= 53
    page.keyboard.press("j")
    # The final heading is clamped by the document bottom and lazy equation layout.
    expect(page.locator("#sec-2 h2")).to_be_in_viewport(ratio=1)
    page.keyboard.press("k")
    page.wait_for_function(
        "Math.abs(document.querySelector('#sec-1 h2').getBoundingClientRect().top - 72) < 2"
    )
    before = page.locator("html").get_attribute("data-theme-mode")
    page.keyboard.press("Meta+d")
    assert page.locator("html").get_attribute("data-theme-mode") == before
    assert page.evaluate("""() => {
      try { pd.keys.register('j', 'duplicate', () => {}); return false; }
      catch (error) { return error.message.includes('Duplicate shortcut'); }
    }""")


def test_storage_denial_does_not_break_reader(page):
    page.add_init_script("""Object.defineProperty(window, 'localStorage', {
      get() { throw new DOMException('Blocked', 'SecurityError'); }
    });""")
    page.reload()
    page.locator("#pd-theme-toggle").click()
    assert page.locator("html").get_attribute("data-theme-mode") == "light"
    page.keyboard.press("?")
    expect(page.locator("#pd-help")).to_be_visible()


def test_automatic_theme_tracks_os_but_explicit_theme_does_not(page):
    page.emulate_media(color_scheme="dark")
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")
    page.locator("#pd-theme-toggle").click()
    expect(page.locator("html")).to_have_attribute("data-theme-mode", "light")
    page.emulate_media(color_scheme="light")
    page.emulate_media(color_scheme="dark")
    expect(page.locator("html")).to_have_attribute("data-theme", "light")


def test_editable_and_composition_keyboard_events_are_ignored(page):
    before = page.locator("html").get_attribute("data-theme-mode")
    page.evaluate("""() => {
      for (const name of ['input', 'textarea', 'select', 'div']) {
        const el = document.createElement(name);
        if (name === 'div') el.contentEditable = 'true';
        document.body.append(el); el.focus();
        el.dispatchEvent(new KeyboardEvent('keydown', {key: 'd', bubbles: true}));
        el.remove();
      }
      document.body.dispatchEvent(new KeyboardEvent('keydown', {
        key: 'd', bubbles: true, isComposing: true
      }));
    }""")
    for modifier in ("Control", "Meta", "Alt"):
        page.keyboard.press(modifier + "+d")
    assert page.locator("html").get_attribute("data-theme-mode") == before


def test_long_math_does_not_expand_page_before_or_after_rendering(page):
    page.evaluate(r"""() => {
      const p = document.createElement('p');
      p.style.marginTop = '10000px';
      p.id = 'long-math-regression';
      const math = document.createElement('span');
      math.className = 'pd-math';
      math.dataset.latex = '\\frac{' + Array(80).fill('\\mathbf{x}_{i}').join('') + '}{y}';
      math.textContent = math.dataset.latex;
      p.append(math); document.querySelector('main').append(p);
    }""")
    for width in (1440, 320):
        page.set_viewport_size({"width": width, "height": 1024})
        assert page.evaluate("() => document.documentElement.scrollWidth <= innerWidth")
    page.locator("#long-math-regression").scroll_into_view_if_needed()
    page.evaluate("() => pd.math.renderInto(document.querySelector('#long-math-regression'))")
    expect(page.locator("#long-math-regression .katex")).to_have_count(1)
    for width in (1440, 320):
        page.set_viewport_size({"width": width, "height": 1024})
        assert page.evaluate("() => document.documentElement.scrollWidth <= innerWidth")
    assert page.locator("#long-math-regression .pd-math").evaluate(
        "el => el.scrollWidth > el.clientWidth"
    )
