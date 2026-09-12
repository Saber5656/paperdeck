"""Export the committed IR JSON Schema."""

from __future__ import annotations

from pathlib import Path

from paperdeck.ir.schema_export import schema_text


def main() -> None:
    destination = Path(__file__).resolve().parents[1] / "src/paperdeck/ir/schema/ir-v1.json"
    destination.write_text(schema_text(), encoding="utf-8")


if __name__ == "__main__":
    main()
