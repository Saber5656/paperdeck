from pathlib import Path

from paperdeck.ir.schema_export import schema_text


def test_committed_schema_matches_models() -> None:
    path = Path(__file__).parents[2] / "src/paperdeck/ir/schema/ir-v1.json"
    assert path.read_text(encoding="utf-8") == schema_text()
