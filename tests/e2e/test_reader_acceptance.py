"""Reader acceptance using a production-rendered, nested document."""

import json

import pytest
from playwright.sync_api import expect, sync_playwright

from paperdeck.config import load_settings
from paperdeck.ir.model import Document
from paperdeck.render.html import render
from tests.fixtures.reader import kitchen_sink_document

pytestmark = pytest.mark.playwright


@pytest.fixture(scope="module")
def reader_file(tmp_path_factory):
    value = kitchen_sink_document().model_dump(mode="json")
    value["meta"]["title"] = [{"type": "text", "text": "Reader acceptance document"}]
    value["macros"] = {"\\R": "\\mathbb{R}"}

    def section(number, level=1, children=None):
        paragraphs = [
            {
                "type": "paragraph",
                "id": f"para-{number * 100 + i}",
                "content": [
                    {"type": "text", "text": ("Readable evidence and source context. " * 35)}
                ],
            }
            for i in range(7)
        ]
        return {
            "type": "section",
            "id": f"sec-{number}",
            "level": level,
            "number": str(number),
            "title": [{"type": "text", "text": f"Section {number}"}],
            "children": paragraphs + (children or []),
        }

    value["body"] += [section(2, children=[section(3, 2, [section(4, 3)])]), section(5), section(6)]
    value["body"][-1]["children"].append(
        {
            "type": "equation",
            "id": "eq-9",
            "number": "9",
            "content_kind": "latex",
            "latex": "\\R^2",
            "latex_verified": True,
        }
    )
    path = tmp_path_factory.mktemp("reader-acceptance") / "reader.html"
    path.write_text(render(Document.model_validate(value), load_settings(None, {})))
    return path


@pytest.fixture(params=["chromium", "webkit"])
def reader_page(request, reader_file):
    with sync_playwright() as p:
        browser = getattr(p, request.param).launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900}, reduced_motion="reduce")
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(reader_file.as_uri())
        yield page
        assert errors == []
        browser.close()


def test_lazy_math_hostile_fallback_and_file_storage(reader_page):
    page = reader_page
    expect(page.locator("#eq-1 .katex")).to_have_count(1)
    assert page.locator("#eq-9 .katex").count() == 0
    page.locator("#eq-9").scroll_into_view_if_needed()
    expect(page.locator("#eq-9 .katex")).to_have_count(1)
    page.locator("#eq-9").evaluate(r"""el => {
      delete el.dataset.pdRendered; el.replaceChildren();
      el.dataset.latex = '\\frac{<img onerror=alert(1)>';
      pd.math.renderInto(el);
    }""")
    expect(page.locator("#eq-9")).to_have_class("pd-eq pd-math-error")
    assert "<img onerror=alert(1)>" in page.locator("#eq-9 code").inner_text()
    assert page.locator("#eq-9 img").count() == 0
    assert (
        page.evaluate("() => { pd.store.set('probe', 'stored'); return pd.store.get('probe'); }")
        == "stored"
    )


def test_jump_stack_hover_grace_and_bottom_popup(reader_page):
    page = reader_page
    positions = []
    for section in (2, 5, 6):
        positions.append(page.evaluate("() => scrollY"))
        page.locator(f'#pd-toc a[href="#sec-{section}"]').click()
        expect(page.locator("#pd-back")).to_have_text(f"Back ({len(positions)})")
    for expected_y in reversed(positions):
        page.keyboard.press("Backspace")
        assert abs(page.evaluate("() => scrollY") - expected_y) < 3
    expect(page.locator("#pd-back")).not_to_be_visible()
    link = page.locator('main a[href="#eq-1"]').first
    link.evaluate(
        "el => {el.style.position='fixed';el.style.bottom='15px';"
        "el.style.left='400px';el.style.zIndex=50;}"
    )
    link.hover()
    popup = page.locator("#pd-popup")
    expect(popup).to_be_visible()
    assert (
        popup.bounding_box()["y"] + popup.bounding_box()["height"] <= link.bounding_box()["y"] + 1
    )
    popup.hover()
    page.wait_for_timeout(230)
    expect(popup).to_be_visible()
    page.mouse.move(1300, 300)
    expect(popup).not_to_be_visible()


def test_toc_nested_reveal_spy_persistence_and_overlay(reader_page):
    page = reader_page
    deep = page.locator('#pd-toc a[href="#sec-4"]')
    expect(deep).not_to_be_visible()
    assert page.locator("#pd-toc").get_attribute("aria-label") == "Table of contents"
    for number in (2, 5, 6):
        page.locator(f"#sec-{number} > h2").evaluate(
            "el => scrollTo(0, el.getBoundingClientRect().top + scrollY - 80)"
        )
        expect(page.locator(f'#pd-toc a[href="#sec-{number}"]')).to_have_attribute(
            "aria-current", "location"
        )
    page.locator("#sec-4 > h4").evaluate(
        "el => scrollTo(0, el.getBoundingClientRect().top + scrollY - 80)"
    )
    expect(deep).to_be_visible()
    page.locator("#pd-toc-toggle").click()
    page.reload()
    expect(page.locator("#pd-toc")).not_to_be_visible()
    page.set_viewport_size({"width": 800, "height": 900})
    page.locator("#pd-toc-toggle").click()
    expect(page.locator("#pd-toc-backdrop")).to_be_visible()
    page.locator('#pd-toc a[href="#sec-5"]').click()
    expect(page.locator("#pd-toc")).not_to_be_visible()
    expect(page.locator("#pd-back")).to_be_visible()


def test_theme_at_domcontentloaded_all_labels_and_persistence(reader_page):
    page = reader_page
    page.emulate_media(color_scheme="dark")
    page.add_init_script(
        "document.addEventListener('DOMContentLoaded', () => {"
        "window.themeAtReady=document.documentElement.dataset.theme;});"
    )
    page.reload()
    assert page.evaluate("() => window.themeAtReady") == "dark"
    for label in ("light", "dark", "auto"):
        page.locator("#pd-theme-toggle").click()
        expect(page.locator("#pd-theme-toggle")).to_have_text("Theme: " + label)
    page.locator("#pd-theme-toggle").click()
    page.reload()
    expect(page.locator("#pd-theme-toggle")).to_have_text("Theme: light")


def test_position_garbage_flush_debounce_and_hash_precedence(reader_page, reader_file):
    page = reader_page
    key = page.evaluate('() => "pd-pos:"+pd.docId')
    for garbage in ("not JSON", json.dumps({"anchor": "sec-9999", "offset": 0, "at": 1})):
        page.evaluate("([key,value]) => localStorage.setItem(key,value)", [key, garbage])
        page.reload()
        expect(page.locator("#pd-toast")).not_to_be_visible()
    page.evaluate("""() => {
      window.positionWrites=0; const original=pd.store.set;
      pd.store.set=(key,value) => {
        if(key.startsWith('pd-pos:'))window.positionWrites++; original(key,value);
      };
    }""")
    for i in range(20):
        page.evaluate("y => scrollTo(0,y)", 6000 + i * 10)
        page.wait_for_timeout(75)
    page.wait_for_timeout(550)
    assert page.evaluate("() => positionWrites") <= 3
    assert page.evaluate("key => JSON.parse(localStorage.getItem(key)).anchor", key) != "sec-9999"
    page.evaluate("() => scrollTo(0, 7300)")
    saved = page.evaluate("() => scrollY")
    page.reload()
    expect(page.locator("#pd-toast")).to_be_visible()
    expect(page.locator("#pd-toast")).not_to_be_visible(timeout=5000)
    assert abs(page.evaluate("() => scrollY") - saved) < 300
    page.goto("about:blank")
    page.goto(reader_file.as_uri() + "#eq-9")
    expect(page.locator("#eq-9")).to_have_class("pd-eq pd-flash")
    expect(page.locator("#pd-toast")).not_to_be_visible()
    expect(page.locator("#eq-9")).to_be_in_viewport()


def test_keyboard_registry_exact_focus_and_section_offsets(reader_page):
    page = reader_page
    for key, selector in [("j", "#sec-1 h2"), ("j", "#sec-2 h2"), ("k", "#sec-1 h2")]:
        page.keyboard.press(key)
        assert abs(page.locator(selector).bounding_box()["y"] - 72) < 3
    page.locator("#pd-help-toggle").click()
    assert page.locator("#pd-help tr").count() == page.evaluate("() => pd.keys.registry.size")
    position = page.evaluate("() => scrollY")
    page.keyboard.press("j")
    assert page.evaluate("() => scrollY") == position
    for _ in range(12):
        page.keyboard.press("Tab")
        assert page.evaluate(
            "() => document.querySelector('#pd-help').contains(document.activeElement)"
        )
    page.keyboard.press("Escape")
    expect(page.locator("#pd-help-toggle")).to_be_focused()


def test_computed_layout_filters_print_and_reduced_motion(reader_page):
    page = reader_page
    assert page.locator("#pd-content").bounding_box()["width"] <= 46 * 16
    assert page.locator("#pd-header").evaluate("el=>getComputedStyle(el).position") == "fixed"
    light = page.locator("body").evaluate("el=>getComputedStyle(el).backgroundColor")
    page.keyboard.press("d")
    page.keyboard.press("d")
    assert page.locator("body").evaluate("el=>getComputedStyle(el).backgroundColor") != light
    page.evaluate("""() => {
      for (const cls of ['pd-img-crop','ordinary-figure']) {
        const img=document.createElement('img'); img.className=cls;
        document.querySelector('figure').append(img);
      }
    }""")
    assert page.locator(".pd-img-crop").evaluate("el=>getComputedStyle(el).filter") != "none"
    assert page.locator(".ordinary-figure").evaluate("el=>getComputedStyle(el).filter") == "none"
    page.keyboard.press("d")
    page.keyboard.press("d")
    assert page.locator(".pd-img-crop").evaluate("el=>getComputedStyle(el).filter") == "none"
    page.locator('main a[href="#eq-1"]').first.focus()
    expect(page.locator("#pd-popup")).to_be_visible()
    assert page.locator("#pd-popup").bounding_box()["height"] <= 900 * 0.45 + 1
    assert page.locator("#pd-popup").evaluate("el=>getComputedStyle(el).animationName") == "none"
    page.emulate_media(media="print")
    expect(page.locator("#pd-header")).not_to_be_visible()
    expect(page.locator("#pd-toc")).not_to_be_visible()


def test_scroll_spy_updates_once_per_frame(reader_page):
    page = reader_page
    counts = page.evaluate("""async () => {
      const first = document.querySelector('#pd-toc a.pd-toc-link');
      const frames = {}, originalFrame = requestAnimationFrame;
      let stamp = 0;
      window.requestAnimationFrame = callback => originalFrame(time => {
        stamp = time; callback(time);
      });
      const toggle = DOMTokenList.prototype.toggle;
      DOMTokenList.prototype.toggle = function(name, force) {
        if (name === 'pd-current' && this === first.classList) {
          frames[stamp] = (frames[stamp] || 0) + 1;
        }
        return toggle.call(this, name, force);
      };
      const headings = [...document.querySelectorAll('main section > h2')];
      for (let index = 0; index < 25; index++) {
        const heading = headings[index % headings.length];
        scrollTo(0, heading.getBoundingClientRect().top + scrollY - 80);
        await new Promise(resolve => requestAnimationFrame(resolve));
      }
      await new Promise(resolve => requestAnimationFrame(resolve));
      await new Promise(resolve => requestAnimationFrame(resolve));
      DOMTokenList.prototype.toggle = toggle;
      window.requestAnimationFrame = originalFrame;
      return Object.values(frames);
    }""")
    assert counts and max(counts) <= 1
