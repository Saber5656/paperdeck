from paperdeck.engines.latex.macros import extract_macros


def test_macro_forms_and_redefinition_rules() -> None:
    macros, warnings = extract_macros(
        r"""
        \newcommand{\R}{\mathbb{R}}
        \newcommand{\f}[2]{#1+#2}
        \renewcommand{\R}{\mathbf{R}}
        \providecommand{\R}{ignored}
        \def\g#1#2{#1/#2}
        \DeclareMathOperator*{\argmax}{arg\,max}
        """
    )
    assert macros == {
        r"\R": r"\mathbf{R}",
        r"\f": "#1+#2",
        r"\g": "#1/#2",
        r"\argmax": r"\operatorname*{arg\,max}",
    }
    assert not any(item.code.startswith("macro-redefined") for item in warnings)


def test_macro_unsafe_optional_internal_and_size_limits() -> None:
    macros, warnings = extract_macros(
        " ".join(
            [
                r"\newcommand{\opt}[1][x]{#1}",
                r"\newcommand{\bad}{\ifx a b}",
                r"\newcommand{\nested}{\newcommand{\x}{y}}",
                r"\newcommand{\ok}{ok}",
                r"\newcommand{\foo@bar}{internal}",
                r"\newcommand{\huge}{" + "x" * 2001 + "}",
            ]
        )
    )
    assert macros == {r"\ok": "ok"}
    assert {item.code.split(":", 1)[0] for item in warnings} >= {
        "macro-optional-arg",
        "macro-unsafe",
        "macro-internal",
        "macro-too-large",
    }


def test_macro_cap_is_enforced() -> None:
    preamble = "".join(rf"\newcommand{{\m{i}}}{{x}}" for i in range(501))
    macros, warnings = extract_macros(preamble)
    assert len(macros) == 500
    assert any(item.code == "macro-cap" for item in warnings)


def test_macro_parser_skips_malformed_definitions() -> None:
    macros, warnings = extract_macros(
        r"\def nope{x}\def\bad#x{z}\newcommand{\broken"
        r"\newcommand{\missing-body}"
        r"\newcommand{\unclosed}[x"
        r"\newcommand{\again}{one}\newcommand{\again}{two}"
    )
    assert macros == {r"\again": "two"}
    assert any(item.code == r"macro-redefined:\again" for item in warnings)
