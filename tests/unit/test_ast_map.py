from paperdeck.engines.latex.ast_map import map_ast
from paperdeck.ir.anchors import AnchorAllocator


def test_ast_map_figure_table_and_raw_html_are_safe() -> None:
    ast = {
        "blocks": [
            {"t": "Header", "c": [1, ["h", [], []], [{"t": "Str", "c": "Title"}]]},
            {"t": "RawBlock", "c": ["html", "<script>alert(1)</script>"]},
            {
                "t": "Figure",
                "c": [
                    ["", [], []],
                    [None, [{"t": "Plain", "c": [{"t": "Str", "c": "Cap"}]}]],
                    [
                        {
                            "t": "Plain",
                            "c": [{"t": "Image", "c": [["", [], []], [], ["plot.png", ""]]}],
                        }
                    ],
                ],
            },
        ],
        "meta": {},
    }
    mapped = map_ast(ast, AnchorAllocator())
    assert mapped.image_targets == {"fig-1": "plot.png"}
    raw = mapped.body[0].children[0]
    assert raw.text == "unsupported raw block"
    assert "script" not in raw.text


def test_ast_map_note_and_malformed_nodes_degrade_without_crashing() -> None:
    mapped = map_ast(
        {
            "blocks": [
                {"t": "Header", "c": ["bad", ["id", [], []], []]},
                {
                    "t": "Para",
                    "c": [
                        {"t": "Str", "c": "Body"},
                        {"t": "Note", "c": [{"t": "Para", "c": [{"t": "Str", "c": "N"}]}]},
                    ],
                },
            ],
            "meta": {},
        },
        AnchorAllocator(),
    )
    assert mapped.footnotes and mapped.footnotes[0].number == "1"
    assert mapped.body[0].type == "paragraph"
    assert any(w.code == "pandoc-node-malformed:Header" for w in mapped.warnings)
