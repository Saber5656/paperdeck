"""Machine-readable conversion report, separate from the document IR.

A success always has input/engine/fallbacks/timings_ms/warnings/llm/output/versions.
Failures additionally carry error {code, exit}. Reports contain no request bodies or keys.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from paperdeck.errors import OutputExistsError
from paperdeck.logsetup import redact


def _empty_usage() -> dict[str, int | float | None]:
    return dict(calls=0, cache_hits=0, tokens_in=0, tokens_out=0, estimated_usd=0, actual_usd=0)


class RunReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input: str
    engine: str | None = None
    fallbacks: list[dict[str, str]] = Field(default_factory=list)
    timings_ms: dict[str, float] = Field(default_factory=dict)
    warnings: list[dict[str, str]] = Field(default_factory=list)
    llm: dict[str, int | float | None] = Field(default_factory=_empty_usage)
    output: dict[str, object] = Field(default_factory=dict)
    versions: dict[str, str] = Field(default_factory=dict)
    error: dict[str, str | int] | None = None


def atomic_write(path: Path, text: str, *, overwrite: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(prefix="." + path.name + ".", suffix=".tmp", dir=path.parent)
    temporary = Path(raw)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        if overwrite:
            os.replace(temporary, path)
        else:
            try:
                os.link(temporary, path)
            except FileExistsError as exc:
                raise OutputExistsError(
                    "Output already exists.", "Use --force to replace it.", "output-exists"
                ) from exc
    finally:
        temporary.unlink(missing_ok=True)


def write_report(path: Path, report: RunReport) -> None:
    atomic_write(path, redact(report.model_dump_json(indent=2, exclude_none=True)) + "\n")
