from __future__ import annotations

import ast
from pathlib import Path

# Bump this floor in the same change that adds or moves SEC-AC coverage.
SEC_AC_TEST_FLOOR = 30


def test_security_suite_has_pinned_minimum() -> None:
    root = Path(__file__).parent
    count = 0
    for path in root.glob("test_*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        count += sum(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test_")
            for node in ast.walk(tree)
        )
        count += sum(
            isinstance(node, (ast.Import, ast.ImportFrom))
            for node in ast.walk(tree)
            for alias in getattr(node, "names", ())
            if alias.name.startswith("test_")
        )
    assert count >= SEC_AC_TEST_FLOOR
