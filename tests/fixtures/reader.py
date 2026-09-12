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
