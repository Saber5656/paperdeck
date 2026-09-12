"""Central logging setup with lazy secret redaction."""

from __future__ import annotations

import logging
import os
import re
import sys
from typing import Any, cast

_TOKEN_RE = re.compile(r"sk-[A-Za-z0-9_-]{8,}")
_AUTH_RE = re.compile(r"(Authorization\s*:\s*Bearer\s+)\S+", re.IGNORECASE)
_quiet = False
_api_key_env = "OPENAI_API_KEY"


def _mask(text: str, api_key_env: str) -> str:
    value = os.environ.get(api_key_env)
    if value and len(value) >= 8:
        text = text.replace(value, "***")
    text = _TOKEN_RE.sub("***", text)
    return _AUTH_RE.sub(r"\1***", text)


def redact(text: str, api_key_env: str | None = None) -> str:
    """Apply the same masking policy as the configured logging filter."""
    return _mask(text, api_key_env or _api_key_env)


class RedactionFilter(logging.Filter):
    """Mask secrets in both the rendered record and its formatting arguments."""

    def __init__(self, api_key_env: str = "OPENAI_API_KEY") -> None:
        super().__init__()
        self.api_key_env = api_key_env

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _mask(str(record.msg), self.api_key_env)
        if isinstance(record.args, tuple):
            record.args = tuple(_mask(str(arg), self.api_key_env) for arg in record.args)
        elif isinstance(record.args, dict):
            record.args = {
                key: _mask(str(value), self.api_key_env) for key, value in record.args.items()
            }
        return True


def configure_logging(
    verbosity: int,
    api_key_env: str = "OPENAI_API_KEY",
    quiet: bool = False,
) -> None:
    """Configure one stderr handler; later calls update level, stream and env name."""
    global _api_key_env, _quiet
    _quiet = quiet
    _api_key_env = api_key_env
    root = logging.getLogger()
    level = (
        logging.ERROR
        if quiet
        else logging.DEBUG
        if verbosity >= 2
        else logging.INFO
        if verbosity
        else logging.WARNING
    )
    root.setLevel(level)
    existing = next(
        (item for item in root.handlers if getattr(item, "_paperdeck", False)),
        None,
    )
    handler = cast(logging.StreamHandler[Any] | None, existing)
    if handler is None:
        handler = logging.StreamHandler(sys.stderr)
        handler.__dict__["_paperdeck"] = True
        root.addHandler(handler)
    else:
        handler.setStream(sys.stderr)
    handler.setLevel(level)
    handler.filters.clear()
    handler.addFilter(RedactionFilter(api_key_env))
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s"
            if verbosity >= 2
            else "%(levelname)s %(name)s: %(message)s"
        )
    )


def progress(msg: str) -> None:
    """Write user-facing progress to stderr unless quiet mode is active."""
    if not _quiet:
        print(msg, file=sys.stderr)
