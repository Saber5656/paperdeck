"""Deterministic JSON Schema serialization for the committed IR contract."""

from __future__ import annotations

import json

from .model import Document


def schema_text() -> str:
    schema = Document.model_json_schema()
    schema["$id"] = "https://github.com/Saber5656/paperdeck/schema/ir-v1.json"
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"
