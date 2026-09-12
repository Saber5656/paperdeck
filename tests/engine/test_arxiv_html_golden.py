import json
from collections import Counter
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

from paperdeck.config import load_settings
from paperdeck.engines.arxiv_html.parse_content import parse_content
from paperdeck.engines.arxiv_html.parse_structure import parse_structure
from paperdeck.input.arxiv import HtmlArtifact
from paperdeck.ir.anchors import AnchorAllocator
from paperdeck.ir.model import Document, Meta, MetaLink, Provenance, Source
from paperdeck.ir.validate import validate_document
from paperdeck.render.html import render
from paperdeck.render.validate import validate_html

ROOT = Path(__file__).parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "arxiv_html" / "healthy.html"
GOLDEN = ROOT / "tests" / "goldens" / "arxiv_html" / "healthy.json"


def _snapshot(document: Document, source_ids: dict[str, str]) -> dict[str, object]:
    nodes = list(document.model_dump(mode="json")["body"])
    types: Counter[str] = Counter()

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            if value.get("type"):
                types[str(value["type"])] += 1
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(nodes)
    equations = [
        block
        for block in _blocks(document.body)
        if block.get("type") == "equation"
    ]
    figures = [block for block in _blocks(document.body) if block.get("type") == "figure"]
    tables = [block for block in _blocks(document.body) if block.get("type") == "table"]
    return {
        "title": document.meta.title[0].model_dump(mode="json")["text"],
        "authors": document.meta.authors,
        "body_types": dict(types),
        "source_ids": sorted(source_ids),
        "labels": sorted(document.labels),
        "equations": [[item["number"], item["latex"]] for item in equations],
        "figures": [[item["number"], item["asset_id"], item["caption"]] for item in figures],
        "tables": [
            [item["number"], item["rows"][0][0]["header"], item["rows"][0][0]["colspan"]]
            for item in tables
        ],
        "bibliography": len(document.bibliography),
        "footnotes": len(document.footnotes),
    }


def _blocks(nodes: list[Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for node in nodes:
        value = node.model_dump(mode="json")
        result.append(value)
        children = value.get("children")
        if isinstance(children, list):
            result.extend(_blocks_from_values(children))
    return result


def _blocks_from_values(nodes: list[Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        result.append(node)
        children = node.get("children")
        if isinstance(children, list):
            result.extend(_blocks_from_values(children))
    return result


def test_healthy_synthetic_fixture_matches_ir_golden_and_renders(tmp_path: Path) -> None:
    page = tmp_path / "index.html"
    page.write_bytes(FIXTURE.read_bytes())
    assets = page.parent / "assets"
    assets.mkdir()
    (assets / "plot.png").write_bytes(
        (FIXTURE.parent / "assets" / "plot.png").read_bytes()
    )
    artifact = HtmlArtifact(page, {"plot.png": "plot.png"}, [], "fixture")
    structure = parse_structure(
        BeautifulSoup(page.read_text(), "html.parser"), artifact, AnchorAllocator(), None
    )
    body, bibliography, footnotes = parse_content(structure)
    document = Document(
        source=Source(kind="arxiv", arxiv_id="2401.12345", version="1", original="fixture"),
        provenance=Provenance(
            engine="arxiv-html", engine_versions={}, created_at="now", fallbacks=[]
        ),
        meta=Meta(
            title=structure.meta_title,
            authors=structure.authors,
            abstract=structure.abstract,
            links=[MetaLink(url="https://arxiv.org/abs/2401.12345", kind="arxiv")],
        ),
        body=body,
        bibliography=bibliography,
        footnotes=footnotes,
        assets=structure.assets,
        labels=structure.labels,
        warnings=structure.warnings,
    )
    settings = load_settings(None, {})
    validate_document(document, settings.limits)
    rendered = render(document, settings)

    assert len(FIXTURE.read_bytes()) >= 150 * 1024
    assert validate_html(rendered) == []
    assert _snapshot(document, structure.source_id_map) == json.loads(GOLDEN.read_text())
