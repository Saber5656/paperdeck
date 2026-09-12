# ruff: noqa: E501
from pathlib import Path

import click
import pytest

from paperdeck.config import load_settings
from paperdeck.engines import EngineContext
from paperdeck.engines.select import plan, run_plan
from paperdeck.errors import (
    AllEnginesFailedError,
    ConversionError,
    CostLimitError,
    SecurityError,
)
from paperdeck.input.cache import CacheManager
from paperdeck.input.resolver import InputSpec
from paperdeck.ir.model import Document, Meta, MetaLink, Paragraph, Provenance, Source, Text


def _doc() -> Document:
    return Document(
        source=Source(kind="local", original="fixture"),
        provenance=Provenance(engine="stub", engine_versions={}, created_at="now", fallbacks=[]),
        meta=Meta(
            title=[Text(text="T")],
            authors=[],
            links=[MetaLink(url="https://example.test", kind="generic")],
        ),
        body=[Paragraph(id="p-1", content=[Text(text="body")])],
    )


class Stub:
    def __init__(
        self, name: str, available: tuple[bool, str] = (True, ""), error: Exception | None = None
    ):
        self.name = name
        self._available = available
        self.error = error
        self.calls = 0

    def available(self, ctx: EngineContext) -> tuple[bool, str]:
        return self._available

    def convert(self, ctx: EngineContext) -> Document:
        self.calls += 1
        if self.error:
            error, self.error = self.error, None
            raise error
        return _doc()


def _ctx(
    tmp_path: Path,
    *,
    offline: bool = False,
    key: bool = False,
    kind: str = "latex-local",
) -> EngineContext:
    if key:
        import os

        os.environ["OPENAI_API_KEY"] = "test-key"
    settings = load_settings(None, {"offline": offline})
    return EngineContext(
        InputSpec(
            kind, path=tmp_path / ("x.pdf" if kind == "pdf-local" else "x.tex"), original="x"
        ),
        settings,
        CacheManager(tmp_path / "cache"),
        tmp_path,
        lambda _: True,
    )


def test_plan_matrix_and_invalid_forced_engine(tmp_path: Path) -> None:
    assert plan(InputSpec("arxiv", arxiv_id="2401.12345")) == ["arxiv-html", "latex", "pdf"]
    assert plan(InputSpec("latex-local", path=tmp_path / "x.tex")) == ["latex"]
    assert plan(InputSpec("pdf-local", path=tmp_path / "x.pdf")) == ["pdf"]
    with pytest.raises(click.UsageError):
        plan(InputSpec("pdf-local", path=tmp_path / "x.pdf"), "latex")


def test_run_plan_records_conversion_fallback_and_provenance(tmp_path: Path) -> None:
    first = Stub("latex", error=ConversionError("bad", "retry", "bad-parser"))
    result = run_plan(["latex", "latex"], _ctx(tmp_path), {"latex": first})
    assert result.provenance.fallbacks[0].reason_code == "convert-failed:bad-parser"
    assert first.calls == 2


def test_security_error_aborts_and_exhaustion_records_notes(tmp_path: Path) -> None:
    secure = Stub("latex", error=SecurityError("unsafe", "remove it", "unsafe"))
    with pytest.raises(SecurityError):
        run_plan(["latex"], _ctx(tmp_path), {"latex": secure})
    unavailable = Stub("latex", available=(False, "no-main-tex"))
    with pytest.raises(AllEnginesFailedError) as exc:
        run_plan(["latex"], _ctx(tmp_path), {"latex": unavailable})
    assert exc.value.attempts[0].reason_code == "no-main-tex"


def test_pdf_cost_decline_is_recorded_before_conversion(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    pdf = Stub("pdf")
    context = EngineContext(
        InputSpec("pdf-local", path=tmp_path / "x.pdf", original="x.pdf"),
        load_settings(None, {}),
        CacheManager(tmp_path / "cache"),
        tmp_path,
        lambda _: False,
    )
    with pytest.raises(AllEnginesFailedError) as exc:
        run_plan(["pdf"], context, {"pdf": pdf})
    assert exc.value.attempts[0].reason_code == "cost-declined"
    assert pdf.calls == 0


def test_cost_limit_error_is_terminal(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    pdf = Stub("pdf", error=CostLimitError("too costly", "lower limit", 2.0, 1.0))
    context = EngineContext(
        InputSpec("pdf-local", path=tmp_path / "x.pdf", original="x.pdf"),
        load_settings(None, {}),
        CacheManager(tmp_path / "cache"),
        tmp_path,
        lambda _: True,
    )
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with pytest.raises(CostLimitError):
        run_plan(["pdf"], context, {"pdf": pdf})
