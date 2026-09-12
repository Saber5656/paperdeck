"""Render validated IR to the pd-* DOM contract used by the offline viewer.

Every text/attribute remains autoescaped. Only package-owned scripts/styles and the
JSON island escaped by build_bundle are trusted markup; no IR text enters these sinks.
"""

from __future__ import annotations

from importlib.resources import files

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from markupsafe import Markup

from paperdeck.config import Settings
from paperdeck.ir.model import Document, Inline, Section, Text
from paperdeck.ir.validate import iter_blocks, validate_document
from paperdeck.render.assets import AssetsBundle, build_bundle


def plain_text(nodes: list[Inline]) -> str:
    parts = []
    for node in nodes:
        if isinstance(node, Text) or hasattr(node, "text"):
            parts.append(str(getattr(node, "text", "")))
        elif hasattr(node, "content"):
            parts.append(plain_text(node.content))
        elif hasattr(node, "latex"):
            parts.append(str(node.latex))
    return "".join(parts)


def render_document(doc: Document, assets_bundle: AssetsBundle, settings: Settings) -> str:
    validate_document(doc, settings.limits)
    env = Environment(
        loader=FileSystemLoader(str(files("paperdeck.render").joinpath("templates"))),
        autoescape=True,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    return env.get_template("document.html.j2").render(
        doc=doc.model_dump(mode="json"),
        bundle=assets_bundle,
        title=plain_text(doc.meta.title),
        section_titles={
            b.id: plain_text(b.title) for b in iter_blocks(doc) if isinstance(b, Section)
        },
        footnote_counts={},
        # Audited sinks: immutable bundled text and JSON with script delimiters escaped.
        style_text=Markup(assets_bundle.style_text),  # noqa: S704
        script_texts=[Markup(s.text) for s in assets_bundle.scripts],  # noqa: S704
        data_json=Markup(assets_bundle.data_json),  # noqa: S704
    )


def render(doc: Document, settings: Settings) -> str:
    return render_document(doc, build_bundle(doc, settings), settings)
