import base64
from copy import deepcopy

import pytest
from bs4 import BeautifulSoup

from paperdeck.config import load_settings
from paperdeck.errors import ConversionError
from paperdeck.ir.model import Asset, AssetOrigin, Equation, Figure, Table
from paperdeck.render.assets import build_bundle
from paperdeck.render.html import render
from paperdeck.render.validate import validate_html
from tests.fixtures.reader import document


def test_budget_drops_figures_before_tables_and_preserves_equations():
    settings = load_settings(None, {})
    settings = settings.model_copy(
        update={
            "limits": settings.limits.model_copy(
                update={"embed_warn_mb": 2, "embed_hard_max_mb": 3}
            )
        }
    )
    assets = {
        key: Asset(
            id=key,
            mime="image/png",
            data_b64=base64.b64encode(b"x" * amount).decode(),
            origin=AssetOrigin(engine="pdf"),
        )
        for key, amount in [
            ("fig-large", 1_500_000),
            ("fig-small", 800_000),
            ("table", 1_000_000),
            ("equation", 800_000),
        ]
    }
    doc = document().model_copy(
        update={
            "assets": assets,
            "body": [
                Figure(id="fig-1", asset_id="fig-large", caption=[]),
                Figure(id="fig-2", asset_id="fig-small", caption=[]),
                Table(id="tab-1", content_kind="image", asset_id="table", caption=[]),
                Equation(
                    id="eq-1", content_kind="image", asset_id="equation", latex_verified=False
                ),
            ],
        }
    )
    bundle = build_bundle(doc, settings)
    assert bundle.dropped[0].id == "fig-large"
    assert "equation" in bundle.image_srcs
    assert bundle.total_embedded_bytes <= 3 * 1024 * 1024
    assert [d.id for d in bundle.dropped][:2] == ["fig-large", "fig-small"]
    huge = assets["equation"].model_copy(
        update={"data_b64": base64.b64encode(b"x" * 5_000_000).decode()}
    )
    with pytest.raises(ConversionError, match="size limit"):
        build_bundle(doc.model_copy(update={"assets": {**assets, "equation": huge}}), settings)


def test_kitchen_sink_nested_nodes_and_repeated_footnotes():
    value = deepcopy(document().model_dump(mode="json"))
    value["body"][0]["children"].extend(
        [
            {
                "type": "paragraph",
                "id": "para-2",
                "content": [
                    {
                        "type": "emph",
                        "content": [
                            {"type": "strong", "content": [{"type": "text", "text": "nested"}]}
                        ],
                    },
                    {"type": "sup", "content": [{"type": "text", "text": "2"}]},
                    {"type": "sub", "content": [{"type": "text", "text": "i"}]},
                    {"type": "code", "text": "<test>"},
                    {"type": "math", "latex": "x^2"},
                    {"type": "line_break"},
                    {"type": "cite", "bib_ids": ["bib-1", "bib-2"], "text": "[1,2]"},
                    {"type": "footnote_ref", "target_id": "fn-1", "number": "1"},
                    {"type": "footnote_ref", "target_id": "fn-1", "number": "1"},
                ],
            },
            {
                "type": "list",
                "id": "para-3",
                "ordered": True,
                "items": [
                    [
                        {
                            "type": "paragraph",
                            "id": "para-4",
                            "content": [{"type": "text", "text": "item"}],
                        }
                    ]
                ],
            },
            {
                "type": "quote",
                "id": "para-5",
                "content": [
                    {
                        "type": "paragraph",
                        "id": "para-6",
                        "content": [{"type": "text", "text": "quote"}],
                    }
                ],
            },
            {
                "type": "code_block",
                "id": "para-7",
                "text": "<script>x</script>",
                "language": "python",
            },
            {"type": "unhandled", "id": "para-8", "text": "<unknown>"},
            {"type": "figure", "id": "fig-1", "caption": [{"type": "text", "text": "caption"}]},
            {
                "type": "table",
                "id": "tab-1",
                "caption": [],
                "content_kind": "grid",
                "rows": [
                    [
                        {
                            "content": [{"type": "text", "text": "heading"}],
                            "header": True,
                            "colspan": 2,
                        }
                    ]
                ],
            },
        ]
    )
    value["bibliography"] = [
        {
            "id": f"bib-{i}",
            "number": str(i),
            "content": [{"type": "text", "text": f"Source {i}"}],
            "urls": [],
        }
        for i in (1, 2)
    ]
    value["footnotes"] = [
        {
            "type": "footnote_def",
            "id": "fn-1",
            "number": "1",
            "content": [
                {"type": "paragraph", "id": "para-9", "content": [{"type": "text", "text": "Note"}]}
            ],
        }
    ]
    from paperdeck.ir.model import Document

    html = render(Document.model_validate(value), load_settings(None, {}))
    soup = BeautifulSoup(html, "html.parser")
    ids = [el["id"] for el in soup.select("[id]")]
    assert len(ids) == len(set(ids))
    assert validate_html(html) == []
    assert soup.select_one('th[scope="col"][colspan="2"]')
    assert all(soup.select_one(a["href"]) for a in soup.select('a[href^="#"]'))
