"""Export the reviewed LLM pydantic schemas for inspection and wire drift checks."""

from __future__ import annotations

import json
from pathlib import Path

from paperdeck.llm.schemas import get


def main() -> None:
    destination = Path("src/paperdeck/llm/schemas")
    for name in ("pdf_segment.v1", "pdf_equation_latex.v1", "pdf_bib.v1", "pdf_cite_map.v1"):
        model, version = get(name)
        path = destination / f"{name}.json"
        serialized = json.dumps(model.model_json_schema(), indent=2, ensure_ascii=False) + "\n"
        path.write_text(serialized, encoding="utf-8")


if __name__ == "__main__":
    main()
