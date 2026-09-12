"""Shared deterministic reader IR fixture."""

from paperdeck.ir.model import Document


def document():
    return Document.model_validate(
        {
            "schema_version": "1",
            "source": {"kind": "local", "original": "example.tex"},
            "provenance": {
                "engine": "latex",
                "engine_versions": {"paperdeck": "0.1.0.dev0", "katex": "0.18.7"},
                "created_at": "2026-09-12T00:00:00Z",
                "fallbacks": [],
            },
            "meta": {
                "title": [{"type": "text", "text": "A <script>alert(1)</script> paper"}],
                "authors": ["Example Author"],
                "links": [],
            },
            "body": [
                {
                    "type": "section",
                    "id": "sec-1",
                    "level": 1,
                    "number": "1",
                    "title": [{"type": "text", "text": "Introduction"}],
                    "children": [
                        {
                            "type": "paragraph",
                            "id": "para-1",
                            "content": [
                                {"type": "text", "text": "See "},
                                {
                                    "type": "ref_link",
                                    "target_id": "eq-1",
                                    "kind": "eq",
                                    "text": "(1)",
                                },
                                {
                                    "type": "ext_link",
                                    "url": "https://example.com",
                                    "content": [{"type": "text", "text": "source"}],
                                },
                            ],
                        },
                        {
                            "type": "equation",
                            "id": "eq-1",
                            "number": "1",
                            "content_kind": "latex",
                            "latex": "x < y",
                            "latex_verified": True,
                        },
                    ],
                }
            ],
            "macros": {"\\bad": "</script><img onerror=alert(1)>"},
        }
    )


def kitchen_sink_document():
    value = document().model_dump(mode="json")
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
    return Document.model_validate(value)
