from paperdeck.engines.latex.ast_map import MappedDoc
from paperdeck.engines.latex.counters import assign_numbers
from paperdeck.ir.model import Cell, Equation, Figure, Section, Table, Text


def _mapped(
    body: list[Section | Equation | Figure | Table], *, env_map: dict[str, str] | None = None
) -> MappedDoc:
    return MappedDoc(
        body,
        [],
        [],
        None,
        [],
        [],
        env_map or {},
        {},
        {},
        set(),
    )


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


def test_row_split_preserves_nested_cases_and_wraps_only_top_level_alignment() -> None:
    equation = Equation(
        id="eq-rows",
        content_kind="latex",
        latex=(
            r"\begin{align}"
            r"f(x)&=\begin{cases}x&x>0\\-x&x\leq0\end{cases}\\"
            r"g(x)=x^2\\"
            r"h(x)&=x+1\end{align}"
        ),
        latex_verified=True,
    )
    result = assign_numbers(_mapped([equation], env_map={"eq-rows": "align"}), "")
    rows = [item for item in result.body if isinstance(item, Equation)]
    assert [row.number for row in rows] == ["1", "2", "3"]
    assert len(rows) == 3
    assert rows[0].latex is not None and rows[0].latex.startswith(r"\begin{aligned}")
    assert r"\begin{cases}x&x>0\\-x&x\leq0\end{cases}" in (rows[0].latex or "")
    assert rows[1].latex == r"g(x)=x^2"
    assert rows[2].latex == r"\begin{aligned}h(x)&=x+1\end{aligned}"


def test_starred_and_display_math_are_unnumbered() -> None:
    starred = Equation(
        id="eq-star",
        content_kind="latex",
        latex=r"\begin{gather*}a\\b\end{gather*}",
        latex_verified=True,
    )
    display = Equation(
        id="eq-display",
        content_kind="latex",
        latex=r"x+y",
        latex_verified=True,
    )
    result = assign_numbers(
        _mapped([starred, display], env_map={"eq-star": "gather*", "eq-display": "display"}),
        "",
    )
    assert [item.number for item in result.body if isinstance(item, Equation)] == [None, None, None]


def test_captionless_media_does_not_advance_captioned_counters() -> None:
    body = [
        Figure(id="fig-empty", caption=[]),
        Figure(id="fig-one", caption=[Text(text="First")]),
        Table(id="tab-empty", caption=[], content_kind="grid", rows=[[Cell(content=[])]]),
        Table(
            id="tab-one",
            caption=[Text(text="First")],
            content_kind="grid",
            rows=[[Cell(content=[])]],
        ),
        Figure(id="fig-two", caption=[Text(text="Second")]),
    ]
    result = assign_numbers(_mapped(body), "")
    assert [item.number for item in result.body if isinstance(item, Figure)] == [None, "1", "2"]
    assert [item.number for item in result.body if isinstance(item, Table)] == [None, "1"]


def test_numbering_ids_and_values_are_stable_across_replays() -> None:
    source = Equation(
        id="eq-stable",
        content_kind="latex",
        latex=r"\begin{align}a&=1\\b&=2\nonumber\\c&=3\end{align}",
        latex_verified=True,
    )
    first = assign_numbers(_mapped([source], env_map={"eq-stable": "align"}), "")
    second = assign_numbers(_mapped([source], env_map={"eq-stable": "align"}), "")
    first_rows = [(item.id, item.number) for item in first.body if isinstance(item, Equation)]
    second_rows = [(item.id, item.number) for item in second.body if isinstance(item, Equation)]
    assert (
        first_rows
        == second_rows
        == [("eq-stable", "1"), ("eq-stable-2", None), ("eq-stable-3", "2")]
    )
    assert sum(number is not None for _, number in first_rows) == 2
