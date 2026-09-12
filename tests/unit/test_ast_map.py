from paperdeck.engines.latex.ast_map import map_ast
from paperdeck.engines.latex.counters import assign_numbers
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


def test_ast_map_handles_supported_inline_and_block_nodes() -> None:
    inline = [
        {"t": "Str", "c": "text"},
        {"t": "Space"},
        {"t": "Emph", "c": [{"t": "Str", "c": "e"}]},
        {"t": "Strong", "c": [{"t": "Str", "c": "s"}]},
        {"t": "Subscript", "c": [{"t": "Str", "c": "sub"}]},
        {"t": "Superscript", "c": [{"t": "Str", "c": "sup"}]},
        {"t": "Code", "c": [["", [], []], "code"]},
        {"t": "Math", "c": [{"t": "InlineMath"}, "x"]},
        {"t": "LineBreak"},
        {"t": "Link", "c": [["", [], []], [{"t": "Str", "c": "link"}], ["https://x", ""]]},
        {"t": "Link", "c": [["", [], []], [{"t": "Str", "c": "bad"}], ["javascript:x", ""]]},
        {"t": "Cite", "c": [[{"citationId": "k"}], [{"t": "Str", "c": "cite"}]]},
        {"t": "RawInline", "c": ["latex", r"\ref{x}"]},
        {"t": "RawInline", "c": ["html", "<i>x</i>"]},
    ]
    ast = {
        "blocks": [
            {"t": "Header", "c": [1, ["", [], []], [{"t": "Str", "c": "H"}]]},
            {"t": "Para", "c": inline},
            {"t": "CodeBlock", "c": [["", ["python"], []], "print(1)"]},
            {"t": "BlockQuote", "c": [{"t": "Plain", "c": [{"t": "Str", "c": "q"}]}]},
            {"t": "BulletList", "c": [[{"t": "Plain", "c": [{"t": "Str", "c": "b"}]}]]},
            {
                "t": "OrderedList",
                "c": [
                    [1, {"t": "Decimal"}, {"t": "Period"}],
                    [{"t": "Plain", "c": [{"t": "Str", "c": "o"}]}],
                ],
            },
            {
                "t": "Div",
                "c": [
                    ["", ["abstract"], []],
                    [{"t": "Plain", "c": [{"t": "Str", "c": "abstract"}]}],
                ],
            },
            {
                "t": "Div",
                "c": [["", ["box"], []], [{"t": "Plain", "c": [{"t": "Str", "c": "div"}]}]],
            },
            {"t": "RawBlock", "c": ["latex", r"\appendix"]},
            {"t": "RawBlock", "c": ["html", "<script>x</script>"]},
            {"t": "SmallCaps", "c": [{"t": "Str", "c": "unknown"}]},
        ],
        "meta": {},
    }
    mapped = map_ast(ast, AnchorAllocator())
    assert mapped.meta_abstract and mapped.raw_spans
    section = mapped.body[0]
    assert section.type == "section"
    paragraph = section.children[0]
    assert paragraph.type == "paragraph"
    assert any(item.type == "ext_link" for item in paragraph.content)
    assert any(item.code == "invalid-link-scheme" for item in mapped.warnings)


def test_ast_map_recovers_raw_display_math_block() -> None:
    mapped = map_ast(
        {
            "blocks": [
                {
                    "t": "RawBlock",
                    "c": [
                        "latex",
                        r"\begin{align}x &= 1\label{eq:x}\\ y &= 2\nonumber\\ z &= 3\end{align}",
                    ],
                }
            ],
            "meta": {},
        },
        AnchorAllocator(),
    )
    assert mapped.body[0].type == "equation"
    assert mapped.env_map[mapped.body[0].id] == "align"
    numbered = assign_numbers(mapped, "")
    assert [item.number for item in numbered.body if item.type == "equation"] == ["1", None, "2"]

    starred = map_ast(
        {
            "blocks": [{"t": "RawBlock", "c": ["latex", r"\begin{align*}x &= 1\end{align*}"]}],
            "meta": {},
        },
        AnchorAllocator(),
    )
    assert starred.env_map[starred.body[0].id] == "align*"
    assert assign_numbers(starred, "").body[0].number is None
