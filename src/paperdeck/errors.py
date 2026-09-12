"""Stable exception taxonomy and user-facing error presentation."""

from __future__ import annotations

import re
import traceback as traceback_module
from dataclasses import dataclass
from typing import TypeVar

import click


@dataclass(frozen=True)
class FallbackNote:
    """Record why one conversion engine was skipped or failed."""

    engine: str
    reason_code: str
    detail: str


class PaperdeckError(Exception):
    """Base for expected failures that can be presented to a CLI user."""

    default_code = "paperdeck-error"

    def __init__(self, user_message: str, hint: str, code: str | None = None) -> None:
        if not hint:
            raise ValueError("hint is required and must be non-empty")
        self.user_message = user_message
        self.hint = hint
        self.code = code or self.default_code
        super().__init__(user_message)


class InputError(PaperdeckError):
    default_code = "input-error"


class FetchError(PaperdeckError):
    default_code = "fetch-error"


class ConversionError(PaperdeckError):
    """Recoverable failure from an individual conversion engine or IR gate."""

    default_code = "conversion-error"


class AllEnginesFailedError(PaperdeckError):
    default_code = "all-engines-failed"

    def __init__(
        self,
        user_message: str,
        hint: str,
        attempts: list[FallbackNote],
        code: str | None = None,
    ) -> None:
        self.attempts = list(attempts)
        super().__init__(user_message, hint, code)


class LlmError(PaperdeckError):
    default_code = "llm-error"


class CostLimitError(PaperdeckError):
    default_code = "cost-limit"

    def __init__(
        self,
        user_message: str,
        hint: str,
        estimate_usd: float,
        limit_usd: float,
        code: str | None = None,
    ) -> None:
        self.estimate_usd = estimate_usd
        self.limit_usd = limit_usd
        super().__init__(user_message, hint, code)


class ConfigError(PaperdeckError):
    default_code = "config-error"


_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


class SecurityError(PaperdeckError):
    default_code = "security-error"

    def __init__(self, user_message: str, hint: str, code: str | None = None) -> None:
        safe = _CONTROL_RE.sub("", user_message)[:120]
        super().__init__(safe, hint, code)


class OutputExistsError(PaperdeckError):
    default_code = "output-exists"


EXIT_CODES: dict[type[BaseException], int] = {
    InputError: 3,
    FetchError: 4,
    ConversionError: 5,
    AllEnginesFailedError: 5,
    LlmError: 6,
    CostLimitError: 7,
    ConfigError: 8,
    SecurityError: 9,
    OutputExistsError: 10,
}

_BUG_HINT = "Please report: https://github.com/Saber5656/paperdeck/issues"
_E = TypeVar("_E", bound=BaseException)


def _exit_code(exc: BaseException) -> int:
    if isinstance(exc, click.UsageError):
        return 2
    for exception_type, code in EXIT_CODES.items():
        if isinstance(exc, exception_type):
            return code
    return 1


def _render_table(attempts: list[FallbackNote]) -> str:
    headers = ("ENGINE", "REASON", "DETAIL")
    rows = [(item.engine, item.reason_code, item.detail) for item in attempts]
    widths = [
        max([len(headers[idx]), *(len(row[idx]) for row in rows)] or [len(headers[idx])])
        for idx in range(3)
    ]
    lines = [" | ".join(value.ljust(widths[idx]) for idx, value in enumerate(headers))]
    lines.append("-+-".join("-" * width for width in widths))
    lines.extend(
        " | ".join(value.ljust(widths[idx]) for idx, value in enumerate(row)) for row in rows
    )
    return "\n".join(lines)


def present_error(exc: BaseException, verbose: int = 0) -> tuple[str, int]:
    """Render an exception and return ``(stderr_text, process_exit_code)``."""
    if isinstance(exc, PaperdeckError):
        message, hint = exc.user_message, exc.hint
        extra = f"\n{_render_table(exc.attempts)}" if isinstance(exc, AllEnginesFailedError) else ""
    elif isinstance(exc, click.UsageError):
        message, hint, extra = str(exc), "Use --help to see valid options.", ""
    else:
        message, hint, extra = str(exc) or exc.__class__.__name__, _BUG_HINT, ""
    rendered = f"error: {message}\nhint: {hint}{extra}"
    if verbose >= 2:
        rendered += "\n" + "".join(traceback_module.format_exception(exc)).rstrip()
    return rendered, _exit_code(exc)
