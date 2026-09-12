"""Enforce the zero-resource-request and hashed-script output contract.

JSON script islands are hashed too: the invariant covers every script body, including
non-executable data, so adding or changing an island also changes the CSP.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from bs4 import BeautifulSoup


@dataclass(frozen=True)
class Violation:
    code: str
    detail: str
    element_excerpt: str = ""


def csp_for_scripts(scripts: list[str]) -> str:
    hashes = " ".join(
        "'sha256-" + base64.b64encode(hashlib.sha256(s.encode()).digest()).decode() + "'"
        for s in scripts
    )
    return (
        "default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src "
        + hashes
        + "; font-src data:; connect-src 'none'; form-action 'none'; "
        "base-uri 'none'; frame-ancestors 'none'"
    )


def _css_has_request(css: str) -> bool:
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    css = re.sub(
        r"\\([0-9a-fA-F]{1,6})\s?",
        lambda m: chr(int(m[1], 16)) if int(m[1], 16) <= 0x10FFFF else "\ufffd",
        css,
    )
    css = re.sub(r"\\(.)", r"\1", css)
    if re.search(r"@import\b", css, re.I):
        return True
    return any(
        not value.strip().strip("'\"").lower().startswith("data:")
        for value in re.findall(r"url\s*\((.*?)\)", css, re.I | re.S)
    )


def validate_html(html_text: str) -> list[Violation]:
    soup = BeautifulSoup(html_text, "html.parser")
    violations: list[Violation] = []

    def flag(code: str, detail: str, element: object) -> None:
        excerpt = re.sub(r"[\x00-\x1f\x7f]", "", str(element))[:120]
        violations.append(Violation(code, detail, excerpt))

    forbidden = {
        "link",
        "iframe",
        "frame",
        "object",
        "embed",
        "form",
        "base",
        "video",
        "audio",
        "source",
        "track",
    }
    for tag in soup.find_all(True):
        if tag.name in forbidden or (
            tag.name == "meta" and str(tag.get("http-equiv", "")).lower() == "refresh"
        ):
            flag("forbidden-element", f"{tag.name} is not permitted", tag)
        if tag.name == "svg":
            flag("svg-inline", "SVG must be embedded as an image", tag)
        if tag.name == "script":
            if tag.has_attr("src"):
                flag("script-external", "External scripts are forbidden", tag)
            if tag.get("type") not in (None, "application/json"):
                flag("script-type", "Unexpected script type", tag)
        for name, raw in tag.attrs.items():
            value = " ".join(raw) if isinstance(raw, list) else str(raw)
            if re.match(r"^on[a-z]+", name, re.I):
                flag("inline-handler", "Inline handlers are forbidden", tag)
            if name == "style" and _css_has_request(value):
                flag("style-url", "CSS resource URL must be data:", tag)
            if name in {"src", "srcset", "poster", "data", "ping", "background"}:
                if name in {"srcset", "ping"} or not value.lower().startswith("data:"):
                    flag("external-resource", f"{name} must be a single data: URL", tag)
            if name == "href":
                scheme = urlsplit(value).scheme.lower()
                allowed = tag.name == "a" and (
                    value.startswith("#") or scheme in {"https", "http", "mailto"}
                )
                if scheme in {"https", "http"} and "noopener" not in tag.get_attribute_list("rel"):
                    allowed = False
                if not allowed:
                    flag("external-resource", "Unexpected navigation or resource href", tag)
        if tag.name == "style" and _css_has_request(tag.get_text()):
            flag("style-url", "CSS resource URL must be data:", tag)
    metas = [
        m
        for m in soup.find_all("meta")
        if str(m.get("http-equiv", "")).lower() == "content-security-policy"
    ]
    if not metas:
        flag("csp-missing", "CSP is required", "")
    else:
        expected = csp_for_scripts([str(s.string or "") for s in soup.find_all("script")])
        if len(metas) != 1 or metas[0].get("content") != expected:
            flag("csp-mismatch", "CSP does not match the inline script hashes", metas[0])
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    args = parser.parse_args()
    violations = validate_html(args.file.read_text(encoding="utf-8"))
    for violation in violations:
        print(f"{violation.code}: {violation.detail}")
    return 9 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
