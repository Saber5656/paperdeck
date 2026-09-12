# ruff: noqa: E501
from pathlib import Path

import click
import pytest

from paperdeck.config import load_settings
from paperdeck.engines import EngineContext
from paperdeck.engines.select import plan, run_plan
from paperdeck.errors import (
    AllEnginesFailedError,
    ConfigError,
    ConversionError,
    CostLimitError,
    FetchError,
    LlmError,
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
        self,
        name: str,
        available: tuple[bool, str] = (True, ""),
        error: Exception | None = None,
        available_error: Exception | None = None,
    ):
        self.name = name
        self._available = available
        self.error = error
        self.available_error = available_error
        self.calls = 0

    def available(self, ctx: EngineContext) -> tuple[bool, str]:
        if self.available_error:
            raise self.available_error
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


def test_pdf_cost_decline_is_recorded_by_pdf_engine(
    tmp_path: Path,
) -> None:
    pdf = Stub("pdf", error=ConversionError("cost confirmation declined", "retry", "cost-declined"))
    context = EngineContext(
        InputSpec("pdf-local", path=tmp_path / "x.pdf", original="x.pdf"),
        load_settings(None, {}),
        CacheManager(tmp_path / "cache"),
        tmp_path,
        lambda _: pytest.fail("selection must not confirm PDF cost"),
    )
    with pytest.raises(AllEnginesFailedError) as exc:
        run_plan(["pdf"], context, {"pdf": pdf})
    assert exc.value.attempts[0].reason_code == "cost-declined"
    assert pdf.calls == 1


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


def test_fetch_and_llm_errors_from_availability_fall_back(tmp_path: Path) -> None:
    first = Stub("arxiv-html", available_error=FetchError("down", "retry", "network-error"))
    second = Stub("latex")
    result = run_plan(
        ["arxiv-html", "latex"],
        _ctx(tmp_path),
        {"arxiv-html": first, "latex": second},
    )
    assert result.provenance.fallbacks[0].reason_code == "html-unavailable"

    llm = Stub("pdf", available_error=LlmError("no llm", "configure it", "missing-key"))
    context = EngineContext(
        InputSpec("pdf-local", path=tmp_path / "x.pdf", original="x.pdf"),
        load_settings(None, {}),
        CacheManager(tmp_path / "cache2"),
        tmp_path,
        lambda _: True,
    )
    with pytest.raises(AllEnginesFailedError) as exc:
        run_plan(["pdf"], context, {"pdf": llm})
    assert exc.value.attempts[0].reason_code == "llm-not-configured"


@pytest.mark.parametrize(
    "error, expected",
    [
        (FetchError("down", "retry", "network-error"), "convert-failed:network-error"),
        (LlmError("failed", "retry", "timeout"), "llm-not-configured"),
        (ConfigError("missing", "configure", "config-error"), "llm-not-configured"),
    ],
)
def test_runtime_fetch_llm_and_config_errors_fall_back(
    tmp_path: Path, error: Exception, expected: str
) -> None:
    name = "pdf" if isinstance(error, (LlmError, ConfigError)) else "latex"
    engine = Stub(name, error=error)
    context = _ctx(tmp_path, kind="pdf-local" if name == "pdf" else "latex-local")
    with pytest.raises(AllEnginesFailedError) as exc:
        run_plan([name], context, {name: engine})
    assert exc.value.attempts[0].reason_code == expected


def test_offline_pdf_is_skipped_before_engine_calls(tmp_path: Path) -> None:
    pdf = Stub("pdf")
    with pytest.raises(AllEnginesFailedError) as exc:
        run_plan(["pdf"], _ctx(tmp_path, offline=True, kind="pdf-local"), {"pdf": pdf})
    assert exc.value.attempts[0].reason_code == "offline-uncached"
    assert pdf.calls == 0


def test_missing_registry_engine_is_recorded(tmp_path: Path) -> None:
    with pytest.raises(AllEnginesFailedError) as exc:
        run_plan(["latex"], _ctx(tmp_path), {})
    assert exc.value.attempts[0].reason_code == "convert-failed:unknown-engine"


def test_default_registry_is_lazy(monkeypatch: pytest.MonkeyPatch) -> None:
    class Dummy:
        def __init__(self) -> None:
            self.name = "dummy"

    modules = {
        name: type("Module", (), {cls: Dummy})
        for name, cls in (
            ("paperdeck.engines.arxiv_html.parse_content", "ArxivHtmlEngine"),
            ("paperdeck.engines.latex.engine", "LatexEngine"),
            ("paperdeck.engines.pdf.engine", "PdfEngine"),
        )
    }
    monkeypatch.setattr("paperdeck.engines.select.import_module", modules.__getitem__)
    from paperdeck.engines.select import _registry

    result = _registry(None)
    assert set(result) == {"arxiv-html", "latex", "pdf"}
