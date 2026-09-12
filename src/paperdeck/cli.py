"""Command-line entry point for paperdeck."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import click

from . import __version__
from .errors import present_error
from .logsetup import configure_logging, redact


class _HandlingGroup(click.Group):
    """Present expected paperdeck failures at the command boundary."""

    def invoke(self, ctx: click.Context) -> Any:
        try:
            return super().invoke(ctx)
        except click.exceptions.Exit:
            raise
        except KeyboardInterrupt:
            click.echo("Interrupted.", err=True)
            raise click.exceptions.Exit(130) from None
        except Exception as exc:
            verbosity = int((ctx.obj or {}).get("verbose", 0))
            rendered, code = present_error(exc, verbosity)
            click.echo(redact(rendered), err=True)
            raise click.exceptions.Exit(code) from exc


@click.group(cls=_HandlingGroup, invoke_without_command=True)
@click.version_option(__version__, prog_name="paperdeck")
@click.option("--config", type=click.Path(path_type=None), default=None)
@click.option("-v", "--verbose", count=True)
@click.option("-q", "--quiet", is_flag=True)
@click.pass_context
def main(ctx: click.Context, config: str | None, verbose: int, quiet: bool) -> None:
    """Convert papers into self-contained HTML reading decks."""
    ctx.ensure_object(dict)
    ctx.obj.update(config=config, verbose=verbose, quiet=quiet)
    configure_logging(verbose, quiet=quiet)


def _settings(ctx: click.Context, overrides: dict[str, object] | None = None) -> Any:
    from .config import load_settings

    obj = ctx.find_root().obj
    path = Path(obj["config"]) if obj.get("config") else None
    settings = load_settings(path, overrides or {})
    configure_logging(
        obj.get("verbose", 0), api_key_env=settings.llm.api_key_env, quiet=obj.get("quiet", False)
    )
    return settings


def _cache() -> Any:
    from platformdirs import user_cache_path

    from .input.cache import CacheManager

    return CacheManager(user_cache_path("paperdeck"))


@main.command()
@click.argument("input_value", metavar="INPUT")
@click.option("-o", "--output", type=click.Path(path_type=Path))
@click.option("--engine", type=click.Choice(["auto", "arxiv-html", "latex", "pdf"]), default="auto")
@click.option("--offline", is_flag=True, default=None)
@click.option("--force", is_flag=True)
@click.option("--max-cost", type=click.FloatRange(min=0))
@click.option("--yes", is_flag=True)
@click.option("--no-llm-cache", is_flag=True)
@click.pass_context
def convert(
    ctx: click.Context,
    input_value: str,
    output: Path | None,
    engine: str,
    offline: bool | None,
    force: bool,
    max_cost: float | None,
    yes: bool,
    no_llm_cache: bool,
) -> None:
    """Convert INPUT and write one portable HTML file and a JSON run report."""
    import dataclasses
    import sys
    import tempfile
    import time

    from . import __version__
    from .engines import EngineContext
    from .errors import OutputExistsError, PaperdeckError, SecurityError
    from .input.resolver import output_slug, resolve
    from .logsetup import progress
    from .report import RunReport, atomic_write, write_report

    started = time.monotonic()
    overrides: dict[str, object] = {}
    if offline is not None:
        overrides["offline"] = offline
    if max_cost is not None:
        overrides["llm.max_cost_usd"] = max_cost
    if no_llm_cache:
        overrides["llm.cache"] = False
    settings = _settings(ctx, overrides)
    progress("resolving…")
    spec = resolve(input_value)
    output = (
        (output or Path(settings.output.default_dir) / (output_slug(spec) + ".html"))
        .expanduser()
        .absolute()
    )
    if output.exists() and not force:
        raise OutputExistsError(
            "Output already exists.", "Use --force to replace it.", "output-exists"
        )
    if spec.path and output == spec.path:
        raise click.UsageError("Output must differ from the input file.")
    report_path = Path(str(output) + ".report.json")
    report = RunReport(input=input_value, versions={"paperdeck": __version__})
    report.timings_ms["resolve"] = (time.monotonic() - started) * 1000

    def confirm_cost(estimate: Any) -> bool:
        from .llm.cost import format_estimate

        click.echo(redact(format_estimate(estimate)), err=True)
        report.llm["estimated_usd"] = estimate.usd
        if yes:
            return True
        if not sys.stdin.isatty():
            click.echo(
                "Cost declined: non-interactive input. Add --yes to approve this estimate.",
                err=True,
            )
            return False
        return click.confirm("Proceed?", default=False, err=True)

    try:
        from .engines.select import plan, run_plan
        from .render.assets import build_bundle
        from .render.html import render_document
        from .render.validate import validate_html

        with tempfile.TemporaryDirectory(prefix="paperdeck-") as temporary:
            context = EngineContext(
                spec, settings, _cache(), Path(temporary), confirm_cost, run_metrics=report.llm
            )
            stage = time.monotonic()
            selected_plan = plan(spec, engine, settings, context.cache)
            doc = run_plan(selected_plan, context)
            report.timings_ms["convert"] = (time.monotonic() - stage) * 1000
            report.engine = doc.provenance.engine
            report.fallbacks = [dataclasses.asdict(note) for note in doc.provenance.fallbacks]
            report.warnings = [dict(code=w.code, message=w.message) for w in doc.warnings]
            report.versions.update(doc.provenance.engine_versions)
            if doc.provenance.llm:
                llm = doc.provenance.llm
                report.llm.update(
                    calls=llm.calls,
                    tokens_in=llm.tokens_in,
                    tokens_out=llm.tokens_out,
                    actual_usd=llm.cost_usd,
                )
            progress("rendering…")
            stage = time.monotonic()
            bundle = build_bundle(doc, settings)
            html = render_document(doc, bundle, settings)
            report.timings_ms["render"] = (time.monotonic() - stage) * 1000
            progress("validating…")
            stage = time.monotonic()
            violations = validate_html(html)
            if violations:
                raise SecurityError(
                    "Generated HTML failed the offline safety check.",
                    "Report this paperdeck bug with the violation codes: "
                    + ", ".join(v.code for v in violations),
                    "output-validation",
                )
            report.timings_ms["validate"] = (time.monotonic() - stage) * 1000
            stage = time.monotonic()
            atomic_write(output, html, overwrite=force)
            report.timings_ms["write"] = (time.monotonic() - stage) * 1000
            report.output = dict(
                path=str(output),
                bytes=len(html.encode()),
                asset_count=len(bundle.image_srcs),
                dropped_assets=[dataclasses.asdict(d) for d in bundle.dropped],
            )
            write_report(report_path, report)
            progress(
                f"done in {time.monotonic() - started:.1f}s "
                f"(engine={report.engine}, warnings={len(report.warnings)}, "
                f"cost=${report.llm['actual_usd']})"
            )
            click.echo(str(output))
    except (Exception, KeyboardInterrupt) as exc:
        if hasattr(exc, "attempts"):
            report.fallbacks = [dataclasses.asdict(note) for note in exc.attempts]
        _, exit_code = present_error(exc, 0)
        report.error = dict(
            code=exc.code
            if isinstance(exc, PaperdeckError)
            else "interrupted"
            if isinstance(exc, KeyboardInterrupt)
            else "unexpected",
            exit=130 if isinstance(exc, KeyboardInterrupt) else exit_code,
        )
        try:
            write_report(report_path, report)
        except OSError:
            pass
        raise


@main.command()
@click.argument("arxiv_id")
@click.option("--kind", type=click.Choice(["source", "pdf", "html", "all"]), default="all")
@click.option("--offline", is_flag=True, default=None)
@click.pass_context
def fetch(ctx: click.Context, arxiv_id: str, kind: str, offline: bool | None) -> None:
    """Download an arXiv paper into the cache for later reading."""
    from .errors import FetchError
    from .input.arxiv import ArxivClient
    from .input.resolver import resolve
    from .netgate import NetGate

    settings = _settings(ctx, {"offline": offline} if offline is not None else {})
    spec = resolve(arxiv_id)
    if spec.kind != "arxiv" or not spec.arxiv_id:
        raise click.UsageError("fetch accepts an arXiv ID or arXiv URL.")
    client = ArxivClient(NetGate(settings), _cache())
    meta = client.metadata(spec.arxiv_id, spec.version)
    kinds = ["source", "pdf", "html"] if kind == "all" else [kind]
    succeeded = False
    for item in kinds:
        try:
            result: Path | None
            if item == "source":
                artifact = client.eprint(spec.arxiv_id, meta.resolved_version)
                result = artifact.path
            elif item == "pdf":
                result = client.pdf(spec.arxiv_id, meta.resolved_version)
            else:
                html_artifact = client.html_page(spec.arxiv_id, meta.resolved_version)
                result = html_artifact.page_path if html_artifact else None
            if result:
                succeeded = True
                click.echo(f"{item}: {result}")
            else:
                click.echo(f"{item}: not available")
                if kind != "all":
                    raise FetchError(
                        "arXiv HTML is unavailable.",
                        "Try --kind source or pdf.",
                        "html-unavailable",
                    )
        except FetchError as exc:
            if kind != "all":
                raise
            click.echo(redact(f"{item}: {exc.code}"), err=True)
    if not succeeded:
        raise FetchError(
            "No artifacts were available.",
            "Check the arXiv ID and connection.",
            "artifacts-unavailable",
        )


@main.group("cache")
def cache_command() -> None:
    """Inspect or remove the local download and model-response cache."""


@cache_command.command("path")
def cache_path() -> None:
    click.echo(str(_cache().root))


@cache_command.command("ls")
def cache_list() -> None:
    cache = _cache()
    click.echo("ID                      VERSION   KINDS             SIZE")
    for entry in cache.entries():
        size = (
            f"{entry.total_bytes / 1048576:.1f} MiB"
            if entry.total_bytes >= 1048576
            else f"{entry.total_bytes / 1024:.1f} KiB"
        )
        click.echo(f"{entry.id:24}{str(entry.version or '-'):10}{','.join(entry.kinds):18}{size}")
    files = list((cache.root / "llm").rglob("*.json")) if (cache.root / "llm").exists() else []
    total = sum(p.stat().st_size for p in files if p.is_file())
    click.echo(
        f"llm-cache               -         {len(files)} entries         {total / 1024:.1f} KiB"
    )


@cache_command.command("clear")
@click.argument("arxiv_id", required=False)
@click.option("--yes", is_flag=True)
def cache_clear(arxiv_id: str | None, yes: bool) -> None:
    import sys

    from .input.resolver import resolve

    if arxiv_id:
        spec = resolve(arxiv_id)
        if spec.kind != "arxiv":
            raise click.UsageError("Use an arXiv ID to select a cache entry.")
        arxiv_id = spec.arxiv_id
    if not yes:
        if not sys.stdin.isatty():
            raise click.UsageError(
                "Cache clear requires confirmation. Add --yes to approve deletion."
            )
        if not click.confirm("Delete the selected cached data?", default=False, err=True):
            raise click.UsageError("Cache clear cancelled.")
    cache = _cache()

    def size() -> int:
        return (
            sum(p.stat().st_size for p in cache.root.rglob("*") if p.is_file())
            if cache.root.exists()
            else 0
        )

    before = size()
    cache.clear(arxiv_id)
    click.echo(f"Freed {before - size()} bytes")


@main.command()
@click.option("--json", "as_json", is_flag=True)
@click.option("--offline", is_flag=True, default=None)
@click.pass_context
def doctor(ctx: click.Context, as_json: bool, offline: bool | None) -> None:
    """Check the environment; exit 1 only when a required check fails."""
    import json
    import shutil
    import subprocess
    import sys
    import tempfile
    from importlib.resources import files

    from .netgate import NetGate
    from .render.vendor import verify_vendored

    checks: list[dict[str, str]] = []

    def check(name: str, status: str, detail: str) -> None:
        checks.append(dict(name=name, status=status, detail=redact(detail)))

    check("python", "ok" if sys.version_info >= (3, 11) else "fail", sys.version.split()[0])
    settings = None
    try:
        settings = _settings(ctx, {"offline": offline} if offline is not None else {})
        check("config", "ok", "Configuration is valid")
    except Exception as exc:
        check("config", "fail", str(exc))
    pandoc = shutil.which("pandoc")
    if pandoc:
        try:
            result = subprocess.run(  # noqa: S603 -- resolved trusted executable
                [pandoc, "--version"], capture_output=True, text=True, timeout=10, check=True
            )
            version = result.stdout.splitlines()[0]
            check("pandoc", "ok" if int(version.split()[1].split(".")[0]) >= 3 else "warn", version)
        except Exception:
            check("pandoc", "warn", "Could not inspect pandoc; latex engine unavailable")
    else:
        hint = "brew install pandoc" if sys.platform == "darwin" else "apt install pandoc"
        check("pandoc", "warn", f"latex engine unavailable; install with {hint}")
    mismatches = verify_vendored(
        Path(str(files("paperdeck.render").joinpath("assets/vendor/katex")))
    )
    check(
        "katex-assets",
        "fail" if mismatches else "ok",
        ", ".join(mismatches) if mismatches else "Checksums verified",
    )
    if settings:
        check(
            "api-key",
            "ok" if settings.resolve_api_key() else "warn",
            settings.llm.api_key_env
            + (
                ": set (masked)"
                if settings.resolve_api_key()
                else ": not set; remote PDF engine unavailable"
            ),
        )
    else:
        check("api-key", "warn", "Not checked because configuration is invalid")
    try:
        root = _cache().root
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=root) as probe:
            probe.write(b"paperdeck")
        check("cache-writable", "ok", "Cache is writable")
    except OSError:
        check("cache-writable", "fail", "Cache cannot be written; check directory permissions")
    if not settings or settings.offline:
        check("network", "warn", "Skipped in offline mode or because configuration is invalid")
    else:
        try:
            gate = NetGate(settings)
            responses = [
                gate.client("arxiv").head("https://export.arxiv.org"),
                gate.client("llm").get(settings.llm.base_url),
            ]
            check(
                "network",
                "ok",
                "Endpoints reachable: " + ", ".join(str(r.status_code) for r in responses),
            )
        except Exception as exc:
            check("network", "warn", "Reachability check failed: " + type(exc).__name__)
    if as_json:
        click.echo(json.dumps({"checks": checks}, indent=2))
    else:
        for item in checks:
            click.echo(f"[{item['status']}] {item['name']}: {item['detail']}")
    ctx.exit(1 if any(c["status"] == "fail" for c in checks) else 0)


if __name__ == "__main__":
    main()
