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
