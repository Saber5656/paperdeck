"""Quality checks for official LaTeXML HTML."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from bs4 import BeautifulSoup

_LOG = logging.getLogger(__name__)
STUB_PATTERNS = (
    "HTML is not available for this paper",
    "conversion is pending",
    "conversion pending",
)


@dataclass(frozen=True)
class GateResult:
    ok: bool
    reason: str | None
    error_marker_count: int
    text_kb: int


def assess(html_text: str) -> GateResult:
    """Assess a raw page without fetching anything."""
    soup = BeautifulSoup(html_text, "html.parser")
    visible = soup.get_text(" ", strip=True)
    text_kb = len(visible) // 1024
    lowered = visible.lower()
    if any(pattern.lower() in lowered for pattern in STUB_PATTERNS):
        result = GateResult(False, "html-stub", 0, text_kb)
    elif not soup.select(".ltx_section") and not soup.select(".ltx_para"):
        result = GateResult(False, "html-no-content", 0, text_kb)
    elif not any(item.get_text(strip=True) for item in soup.select("title")):
        result = GateResult(False, "html-missing-title", 0, text_kb)
    else:
        markers = 0
        for item in soup.find_all(class_=True):
            classes = item.get("class")
            if isinstance(classes, (list, tuple)) and any(
                "ltx_ERROR" in str(cls) or "ltx_missing" in str(cls) for cls in classes
            ):
                markers += 1
        threshold = max(20, text_kb / 2)
        result = GateResult(
            markers <= threshold,
            None if markers <= threshold else "html-low-quality",
            markers,
            text_kb,
        )
    _LOG.info(
        "arxiv-html gate: ok=%s markers=%d size=%dKB",
        result.ok,
        result.error_marker_count,
        result.text_kb,
    )
    return result
