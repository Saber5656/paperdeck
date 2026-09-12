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


def test_bibtex_supports_common_entry_types_and_all_external_links(tmp_path: Path) -> None:
    main = tmp_path / "main.tex"
    main.write_text("", encoding="utf-8")
    (tmp_path / "refs.bib").write_text(
        "@article{article, author={A}, title={Article}, journal={J}, year={2020}, "
        "url={https://example.org/a}}\n"
        "@inproceedings{talk, author={B}, title={Talk}, booktitle={Proceedings}, year={2021}, "
        "eprint={2101.12345}}\n"
        "@book{book, author={C}, title={Book}, year={2022}, doi={10.1000/book}}\n"
        "@misc{misc, title={Misc}, url={https://example.org/m}}\n",
        encoding="utf-8",
    )
    project = LatexProject(tmp_path, main, main, "", [])
    entries, index, warnings = parse_bibliography(project, AnchorAllocator())
    assert set(index) == {"article", "talk", "book", "misc"}
    assert [entry.number for entry in entries] == ["1", "2", "3", "4"]
    assert {url.kind for entry in entries for url in entry.urls} == {"doi", "arxiv", "generic"}
    assert {url.url for entry in entries for url in entry.urls} >= {
        "https://doi.org/10.1000/book",
        "https://arxiv.org/abs/2101.12345",
        "https://example.org/a",
    }
    assert [warning.code for warning in warnings] == ["bib-source:bib"]


def test_bbl_wins_over_bib_even_when_bib_is_more_complete(tmp_path: Path) -> None:
    main = tmp_path / "main.tex"
    main.write_text("", encoding="utf-8")
    (tmp_path / "main.bbl").write_text(r"\bibitem{compiled} Compiled.", encoding="utf-8")
    (tmp_path / "refs.bib").write_text(
        "@article{source, title={Source}, year={2024}}", encoding="utf-8"
    )
    project = LatexProject(tmp_path, main, main, "", [])
    entries, index, warnings = parse_bibliography(project, AnchorAllocator())
    assert [entry.key for entry in entries] == ["compiled"]
    assert set(index) == {"compiled"}
    assert [warning.code for warning in warnings] == ["bib-source:bbl"]


def test_inline_thebibliography_preserves_label_and_rejects_unsafe_href(tmp_path: Path) -> None:
    main = tmp_path / "main.tex"
    source = (
        r"\begin{thebibliography}{9}"
        r"\bibitem[Doe (2024)]{x} A \href{javascript:alert(1)}{bad}."
        r"\end{thebibliography}"
    )
    main.write_text(source, encoding="utf-8")
    project = LatexProject(tmp_path, main, main, source, [])
    entries, index, warnings = parse_bibliography(project, AnchorAllocator())
    assert entries[0].number is None
    assert entries[0].label == "Doe (2024)"
    assert index["x"].label == "Doe (2024)"
    assert any(item.code == "bib-tex-dropped" for item in warnings)
    assert not entries[0].urls


def test_thebibliography_is_used_when_no_bbl(tmp_path: Path) -> None:
    main = tmp_path / "main.tex"
    main.write_text(
        r"\begin{thebibliography}{9}\bibitem{x} X.\end{thebibliography}", encoding="utf-8"
    )
    project = LatexProject(tmp_path, main, main, main.read_text(), [])
    entries, _, warnings = parse_bibliography(project, AnchorAllocator())
    assert entries[0].key == "x"
    assert warnings[0].code == "bib-source:thebibliography"
