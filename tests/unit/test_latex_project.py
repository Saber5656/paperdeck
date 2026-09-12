from pathlib import Path

import pytest

from paperdeck.engines.latex.project import prepare, strip_comments
from paperdeck.errors import ConversionError, SecurityError


def _main(text: str, root: Path) -> Path:
    path = root / "main.tex"
    path.write_text(text, encoding="utf-8")
    return path


def test_prepare_flattens_nested_inputs_and_preserves_verbatim(tmp_path: Path) -> None:
    main = _main(
        "\\documentclass{article}\n\\begin{document}\n\\input{a}\n\\include{b}\n\\end{document}\n",
        tmp_path,
    )
    (tmp_path / "a.tex").write_text("A % comment\n\\input{nested}\n", encoding="utf-8")
    (tmp_path / "nested.tex").write_text("N\n", encoding="utf-8")
    (tmp_path / "b.tex").write_text("B\n", encoding="utf-8")
    project = prepare(main)
    flattened = project.flattened.read_text(encoding="utf-8")
    assert "comment" not in flattened and "% >>> a" in flattened and flattened.count("\n\n") >= 1


def test_comments_keep_verbatim_and_escaped_percent() -> None:
    text = "x % gone\n\\% kept\n\\begin{verbatim}\na % kept\n\\end{verbatim}\n"
    result = strip_comments(text)
    assert "gone" not in result and "\\% kept" in result and "a % kept" in result


def test_include_escape_and_cycle_fail(tmp_path: Path) -> None:
    main = _main(
        "\\documentclass{x}\n\\begin{document}\n\\input{../../etc/passwd}\n\\end{document}",
        tmp_path,
    )
    with pytest.raises(SecurityError) as exc:
        prepare(main)
    assert exc.value.code == "include-escape"
    main.write_text(
        "\\documentclass{x}\n\\begin{document}\n\\input{a}\n\\end{document}", encoding="utf-8"
    )
    (tmp_path / "a.tex").write_text("\\input{main}\n", encoding="utf-8")
    with pytest.raises(ConversionError, match="cycle"):
        prepare(main)
