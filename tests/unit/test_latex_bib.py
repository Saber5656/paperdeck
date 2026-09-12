from pathlib import Path

from paperdeck.engines.latex.bib import parse_bibliography
from paperdeck.engines.latex.project import LatexProject
from paperdeck.ir.anchors import AnchorAllocator


def test_bbl_priority_and_natbib_labels(tmp_path: Path) -> None:
    main = tmp_path / "main.tex"
    main.write_text("", encoding="utf-8")
    (tmp_path / "main.bbl").write_text(
        r"\bibitem{a} A. \emph{Title}.\bibitem[Smith et al.(2020)]{b} B.", encoding="utf-8"
    )
    project = LatexProject(tmp_path, main, main, "", [])
    entries, index, warnings = parse_bibliography(project, AnchorAllocator())
    assert [entry.number for entry in entries] == ["1", None]
    assert index["b"].label == "Smith et al.(2020)"
    assert warnings[0].code == "bib-source:bbl"


def test_bbl_cleaner_handles_links_math_and_duplicate_keys(tmp_path: Path) -> None:
    main = tmp_path / "main.tex"
    main.write_text("", encoding="utf-8")
    (tmp_path / "main.bbl").write_text(
        r"\bibitem{k} A~\textbf{bold} $x^2$ \url{https://example.org} "
        r"\href{javascript:bad}{bad}.\bibitem{k} duplicate",
        encoding="utf-8",
    )
    project = LatexProject(tmp_path, main, main, "", [])
    entries, index, warnings = parse_bibliography(project, AnchorAllocator())
    assert len(entries) == 1 and index["k"].number == "1"
    assert any(item.type == "math" for item in entries[0].content)
    assert any(item.type == "ext_link" for item in entries[0].content)
    assert any(item.code == "bib-key-duplicate:k" for item in warnings)


def test_bibtex_fallback_formats_fields_and_urls(tmp_path: Path) -> None:
    main = tmp_path / "main.tex"
    main.write_text("", encoding="utf-8")
    (tmp_path / "refs.bib").write_text(
        "@article{a, author={Doe}, title={Title}, journal={Journal}, year={2024}, doi={10.1/x}}\n"
        "@misc{b, title={Only title}}\n"
        "@misc{broken, note={no readable fields}}",
        encoding="utf-8",
    )
    project = LatexProject(tmp_path, main, main, "", [])
    entries, index, warnings = parse_bibliography(project, AnchorAllocator())
    assert {entry.key for entry in entries} == {"a", "b"}
    assert index["a"].number == "1"
    assert entries[0].urls[0].kind == "doi"
    assert any(item.code == "bib-entry-skipped:broken" for item in warnings)


def test_thebibliography_is_used_when_no_bbl(tmp_path: Path) -> None:
    main = tmp_path / "main.tex"
    main.write_text(
        r"\begin{thebibliography}{9}\bibitem{x} X.\end{thebibliography}", encoding="utf-8"
    )
    project = LatexProject(tmp_path, main, main, main.read_text(), [])
    entries, _, warnings = parse_bibliography(project, AnchorAllocator())
    assert entries[0].key == "x"
    assert warnings[0].code == "bib-source:thebibliography"
