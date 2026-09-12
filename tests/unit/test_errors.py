import pytest
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
from paperdeck.logsetup import redact


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
    assert "[31m" not in rendered
    assert len(rendered) <= 200


def test_security_content_stays_bounded_with_verbose_traceback() -> None:
    rendered, _ = present_error(SecurityError("A" * 10_000, "B" * 10_000), 2)
    assert len(rendered) <= 200


@pytest.mark.parametrize("verbose", [0, 1, 2])
def test_presented_exception_redacts_tokens_at_every_verbosity(verbose: int) -> None:
    try:
        raise RuntimeError("sk-test1234567890 Authorization: Bearer xyz-secret")
    except RuntimeError as exc:
        rendered, _ = present_error(exc, verbose)
    safe = redact(rendered)
    assert "sk-test1234567890" not in safe
    assert "Bearer xyz-secret" not in safe
    assert "***" in safe
