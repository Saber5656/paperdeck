# ruff: noqa: E501
from paperdeck.engines.arxiv_html.quality import assess


def test_quality_gate_accepts_healthy_page() -> None:
    result = assess(
        '<html><head><title>T</title></head><body><section class="ltx_section"><p class="ltx_para">x</p></section></body></html>'
    )
    assert result.ok is True
    assert result.reason is None


def test_quality_gate_rejects_stub_empty_and_missing_title() -> None:
    assert assess("<title>T</title>HTML is not available for this paper").reason == "html-stub"
    assert (
        assess("<html><head><title>T</title></head><body>empty</body></html>").reason
        == "html-no-content"
    )
    assert assess('<section class="ltx_section">x</section>').reason == "html-missing-title"


def test_quality_gate_threshold_counts_markers_and_text_kb() -> None:
    low = (
        " ".join('<span class="ltx_ERROR">bad</span>' for _ in range(60)) + " " + ("x" * 40 * 1024)
    )
    high = (
        " ".join('<span class="ltx_missing">bad</span>' for _ in range(5))
        + " "
        + ("x" * 200 * 1024)
    )
    assert (
        assess('<title>T</title><section class="ltx_section ltx_para">' + low + "</section>").reason
        == "html-low-quality"
    )
    result = assess('<title>T</title><section class="ltx_section ltx_para">' + high + "</section>")
    assert result.ok is True and result.error_marker_count == 5
