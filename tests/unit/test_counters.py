from paperdeck.engines.latex.ast_map import MappedDoc
from paperdeck.engines.latex.counters import assign_numbers
from paperdeck.ir.model import Equation, Section


def test_align_rows_and_numberwithin() -> None:
    equation = Equation(
        id="eq-1",
        content_kind="latex",
        latex=r"\begin{align}a&=b\\c&=d\nonumber\\e&=f\end{align}",
        latex_verified=True,
    )
    mapped = MappedDoc(
        [Section(id="sec-1", level=1, title=[], children=[equation])],
        [],
        [],
        None,
        [],
        [],
        {"eq-1": "align"},
        {},
        {},
        set(),
    )
    result = assign_numbers(mapped, r"\numberwithin{equation}{section}")
    section = result.body[0]
    assert isinstance(section, Section)
    equations = [item for item in section.children if isinstance(item, Equation)]
    assert [item.number for item in equations] == ["1.1", None, "1.2"]
    assert all("&" in item.latex for item in equations)


def test_unnumbered_section_does_not_advance_parent_counter() -> None:
    mapped = MappedDoc(
        [
            Section(id="sec-1", level=1, title=[], children=[]),
            Section(id="sec-2", level=1, title=[], children=[]),
        ],
        [],
        [],
        None,
        [],
        [],
        {},
        {},
        {},
        {"sec-1"},
    )
    result = assign_numbers(mapped, "")
    assert isinstance(result.body[0], Section)
    assert isinstance(result.body[1], Section)
    assert result.body[0].number is None
    assert result.body[1].number == "1"
