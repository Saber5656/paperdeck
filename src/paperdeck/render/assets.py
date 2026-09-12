"""Audited trusted text and data-URI boundary for the offline renderer."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

from paperdeck.config import Settings
from paperdeck.errors import ConversionError, SecurityError
from paperdeck.ir.model import Document, Equation, Figure, Table
from paperdeck.ir.validate import iter_blocks
from paperdeck.render.validate import csp_for_scripts
from paperdeck.render.vendor import verify_vendored

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Script:
    text: str
    sha256_b64: str


@dataclass(frozen=True)
class DroppedAsset:
    id: str
    bytes: int
    reason: str


@dataclass(frozen=True)
class AssetsBundle:
    style_text: str
    scripts: list[Script]
    csp_value: str
    image_srcs: dict[str, str]
    dropped: list[DroppedAsset]
    total_embedded_bytes: int
    data_json: str
    katex_version: str


def build_bundle(doc: Document, settings: Settings) -> AssetsBundle:
    root = Path(str(files("paperdeck.render").joinpath("assets")))
    vendor = root / "vendor/katex"
    mismatches = verify_vendored(vendor)
    if mismatches:
        raise SecurityError(
            "Bundled math assets failed verification.",
            hint="Reinstall paperdeck from a trusted package.",
            code="vendor-checksum",
        )
    css = (vendor / "katex.min.css").read_text()

    # Keep only woff2 alternatives; rewrite each @font-face src as one data URL.
    def font_src(match: re.Match[str]) -> str:
        candidates = re.findall(r'url\([\'"]?(fonts/[^\)\'" ]+\.woff2)[\'"]?\)', match[0])
        if not candidates:
            raise SecurityError(
                "Bundled font source is unsupported.",
                hint="Reinstall paperdeck.",
                code="vendor-font",
            )
        name = candidates[0]
        payload = base64.b64encode((vendor / name).read_bytes()).decode()
        return "src:url(data:font/woff2;base64," + payload + ') format("woff2");'

    css = re.sub(r"src:[^;}]+;?", font_src, css)
    style_text = (root / "viewer.css").read_text() + "\n" + css
    scripts = []
    for file in (root / "theme_bootstrap.js", vendor / "katex.min.js", root / "viewer.js"):
        text = file.read_text()
        scripts.append(
            Script(text, base64.b64encode(hashlib.sha256(text.encode()).digest()).decode())
        )
    doc_id = hashlib.sha256(
        json.dumps(doc.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:16]
    data_json = (
        json.dumps(
            {"macros": doc.macros, "docId": doc_id, "warnings_count": len(doc.warnings)},
            sort_keys=True,
        )
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
    sizes = {
        key: len(base64.b64decode(asset.data_b64, validate=True))
        for key, asset in doc.assets.items()
    }
    total = (
        len(style_text.encode())
        + sum(len(script.text.encode()) for script in scripts)
        + len(data_json.encode())
        + sum(sizes.values())
    )
    if total > settings.limits.embed_warn_mb * 1024 * 1024:
        logger.warning("Embedded content exceeds the configured warning size.")
    asset_blocks = list(iter_blocks(doc))
    if doc.meta.abstract:
        asset_blocks.extend(
            iter_blocks(doc.model_copy(update={"body": doc.meta.abstract, "footnotes": []}))
        )
    protected = {
        block.asset_id for block in asset_blocks if isinstance(block, Equation) and block.asset_id
    }
    dropped: list[DroppedAsset] = []
    for kind in (Figure, Table):
        candidates = {
            block.asset_id
            for block in asset_blocks
            if isinstance(block, kind) and block.asset_id and block.asset_id not in protected
        }
        for asset_id in sorted(candidates, key=lambda key: (-sizes.get(key, 0), key)):
            if total <= settings.limits.embed_hard_max_mb * 1024 * 1024:
                break
            if any(d.id == asset_id for d in dropped):
                continue
            amount = sizes.get(asset_id, 0)
            dropped.append(DroppedAsset(asset_id, amount, "embed-hard-limit"))
            total -= amount
    if total > settings.limits.embed_hard_max_mb * 1024 * 1024:
        raise ConversionError(
            "Document exceeds the embedded size limit.",
            hint="Increase limits.embed_hard_max_mb or use a smaller input.",
            code="output-too-large",
        )
    excluded = {drop.id for drop in dropped}
    return AssetsBundle(
        style_text,
        scripts,
        csp_for_scripts([scripts[0].text, data_json] + [s.text for s in scripts[1:]]),
        {
            key: f"data:{asset.mime};base64,{asset.data_b64}"
            for key, asset in doc.assets.items()
            if key not in excluded
        },
        dropped,
        total,
        data_json,
        str(json.loads((vendor / "MANIFEST.json").read_text())["version"]),
    )
