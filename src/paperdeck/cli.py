"""Command-line entry point for paperdeck."""

from __future__ import annotations

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


def run_cli() -> None:
    """Invoke the CLI and present unexpected command errors consistently."""
    try:
        main(standalone_mode=False)
    except click.exceptions.Exit:
        raise
    except Exception as exc:  # pragma: no cover - exercised through CliRunner
        verbosity = int(getattr(getattr(exc, "ctx", None), "obj", {}).get("verbose", 0))
        rendered, code = present_error(exc, verbosity)
        click.echo(redact(rendered), err=True)
        raise click.exceptions.Exit(code) from exc


if __name__ == "__main__":  # pragma: no cover
    run_cli()
