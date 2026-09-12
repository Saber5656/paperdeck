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


def test_include_commands_inside_literal_environments_are_not_expanded(tmp_path: Path) -> None:
    main = _main(
        "\\documentclass{x}\n\\begin{document}\n"
        "\\begin{verbatim}\n\\input{literal}\n\\end{verbatim}\n"
        "\\input{real}\n\\end{document}",
        tmp_path,
    )
    (tmp_path / "literal.tex").write_text("MUST NOT APPEAR", encoding="utf-8")
    (tmp_path / "real.tex").write_text("REAL CONTENT", encoding="utf-8")
    project = prepare(main)
    flattened = project.flattened.read_text(encoding="utf-8")
    assert "\\input{literal}" in flattened
    assert "MUST NOT APPEAR" not in flattened
    assert "REAL CONTENT" in flattened


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


def test_prepare_selection_missing_include_and_latin1_fallback(tmp_path: Path) -> None:
    (tmp_path / "paper.tex").write_text(
        "\\documentclass{x}\n\\begin{document}\n\\input{missing}\n\\end{document}",
        encoding="utf-8",
    )
    (tmp_path / "other.tex").write_text("not a main", encoding="utf-8")
    project = prepare(tmp_path)
    assert project.main.name == "paper.tex"
    assert "missing" in project.flattened.read_text()
    assert any(item.code == "missing-include" for item in project.warnings)

    latin = tmp_path / "latin.tex"
    latin.write_bytes(b"\\documentclass{x}\n\\begin{document}\n\x96\n\\end{document}")
    latin_project = prepare(latin)
    assert any(item.code == "source-encoding-fallback" for item in latin_project.warnings)


def test_prepare_ambiguous_main_warns_and_missing_document_fails(tmp_path: Path) -> None:
    for name in ("one.tex", "two.tex"):
        (tmp_path / name).write_text(
            "\\documentclass{x}\n\\begin{document}\nX\n\\end{document}", encoding="utf-8"
        )
    project = prepare(tmp_path)
    assert project.main.name in {"one.tex", "two.tex"}
    assert any(item.code == "main-tex-ambiguous" for item in project.warnings)
    bad = tmp_path / "bad.tex"
    bad.write_text("\\documentclass{x}", encoding="utf-8")
    with pytest.raises(ConversionError) as error:
        prepare(bad)
    assert error.value.code == "no-begin-document"
