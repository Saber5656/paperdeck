from types import SimpleNamespace

from paperdeck.engines.pdf.citations import link_citations, link_structural_refs


def test_numeric_and_structural_links_are_conservative() -> None:
    bib = [SimpleNamespace(number="1", id="bib-1"), SimpleNamespace(number="3", id="bib-3")]
    rows = link_citations(["See [1,3] and [99]."], bib)
    assert len(rows[0]) == 1
    assert rows[0][0].node.bib_ids == ["bib-1", "bib-3"]
    refs = link_structural_refs(["Eq. (3) and Fig. 2"], {("eq", "3"): "eq-1"})
    assert len(refs[0]) == 1
    assert refs[0][0].node.target_id == "eq-1"


def test_ranges_are_capped() -> None:
    bib = [SimpleNamespace(number=str(i), id=f"bib-{i}") for i in range(1, 80)]
    rows = link_citations(["[1-79]"], bib)
    assert len(rows[0][0].node.bib_ids) == 50
