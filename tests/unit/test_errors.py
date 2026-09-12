from click import UsageError

from paperdeck.errors import (
    EXIT_CODES,
    AllEnginesFailedError,
    ConfigError,
    FallbackNote,
    InputError,
    PaperdeckError,
    SecurityError,
    present_error,
)


def test_error_contract_and_table() -> None:
    error = AllEnginesFailedError(
        "all conversion engines failed",
        "choose another input or inspect the report",
        [
            FallbackNote("latex", "pandoc-failed", "bad JSON"),
            FallbackNote("pdf", "no-key", "missing"),
        ],
    )
    rendered, code = present_error(error, 0)
    assert code == 5
    assert "ENGINE" in rendered and "REASON" in rendered and "DETAIL" in rendered
    assert rendered.index("latex") < rendered.index("pdf")


def test_all_subclasses_have_exit_codes_and_hints() -> None:
    classes = [InputError, ConfigError, SecurityError]
    for cls in classes:
        error = cls("problem", "fix it")
        assert error.hint
        assert EXIT_CODES[type(error)] > 0
    assert present_error(UsageError("bad flag"), 0)[1] == 2
    assert isinstance(PaperdeckError("x", "hint", "x-code"), PaperdeckError)


def test_security_content_is_bounded_and_sanitized() -> None:
    rendered, _ = present_error(SecurityError("x\x1b[31m" + "A" * 10_000, "fix"), 0)
    assert "\x1b" not in rendered
    assert len(rendered) <= 240
