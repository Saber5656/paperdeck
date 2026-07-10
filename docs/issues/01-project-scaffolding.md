# Title

[W0] 01 Set up project scaffolding, package skeleton, and dev tooling

## Summary

Create the Python project skeleton exactly as specified in DESIGN §5.1: `pyproject.toml`
(hatchling), `src/paperdeck/` package tree with empty module stubs, the `Engine` protocol,
dev tooling configuration (ruff, mypy strict, pytest), and a working `paperdeck --version`
entry point.

## Context

Every other issue adds code into this skeleton. Getting layout, tooling, and the engine
protocol right first means later issues are purely additive and mechanical.

## Scope

- `pyproject.toml`, `.gitignore` (Python), `uv.lock` committed.
- `src/paperdeck/__init__.py` with `__version__ = "0.1.0.dev0"` (single source).
- Empty **Python module** stubs for every `.py` file listed in DESIGN §5.1 (functions
  raise `NotImplementedError` where a body is required by imports). Non-Python content
  owned by later issues (templates 38, viewer assets 41/47, KaTeX vendor 37, schemas
  06/30, prompts 30) is NOT authored here — create the directories with a `.gitkeep`
  placeholder each so the package-data globs resolve.
- `src/paperdeck/engines/__init__.py`: `Engine` protocol and `EngineContext` dataclass
  (the engine registry is added by issue 26; DESIGN §5.1 note).
- `src/paperdeck/cli.py`: click group with only `--version` working.
- `tests/` with one smoke test importing every module.

## Detailed Requirements

1. `pyproject.toml`:
   - `[project]` name `paperdeck`, `requires-python = ">=3.11"`, license `MIT`,
     dependencies exactly: `click`, `httpx`, `pydantic>=2`, `jinja2`, `pypdfium2`,
     `beautifulsoup4`, `platformdirs` (no version pins beyond pydantic major; lockfile pins).
   - `[project.scripts] paperdeck = "paperdeck.cli:main"`.
   - `[dependency-groups] dev = ["pytest", "pytest-cov", "ruff", "mypy", "playwright",
     "reportlab", "pip-licenses"]`.
   - hatchling build backend; package data globs for `render/templates/**`,
     `render/assets/**`, `llm/schemas/**`, `llm/prompts/**`, `ir/schema/**`.
2. Tool config (in `pyproject.toml`): ruff (line length 100, `select = ["E","F","I","B","S","UP"]`
   — `S` enables bandit-style security lints), mypy `strict = true` for `src/paperdeck`.
3. `engines/__init__.py`:
   ```python
   @dataclass(frozen=True)
   class EngineContext:
       spec: "InputSpec"; settings: "Settings"; cache: "CacheManager"
       workdir: Path; confirm_cost: Callable[[CostEstimate], bool]
   class Engine(Protocol):
       name: ClassVar[str]
       def available(self, ctx: EngineContext) -> tuple[bool, str]: ...
       def convert(self, ctx: EngineContext) -> "Document": ...
   ```
   (Forward references as strings; concrete types arrive in later issues.)
4. `cli.py`: `@click.group()` `main` with `--version` (reads `__version__`), `--config`,
   `-v/--verbose` count, `-q/--quiet` — options parsed and stored in a `click.Context.obj`
   dict; subcommands land in later issues.
5. Directory stubs must match DESIGN §5.1 exactly (paths are load-bearing for other issues).

## Acceptance Criteria

- `uv sync` succeeds on macOS and Linux; `uv run paperdeck --version` prints
  `paperdeck, version 0.1.0.dev0`.
- `uv run ruff check .`, `uv run mypy src/paperdeck`, `uv run pytest` all pass.
- Smoke test imports every `paperdeck.*` module without side effects (no network, no file
  writes at import time — asserted by the test).
- Package builds: `uv build` produces sdist+wheel; wheel contains the package-data dirs
  (placeholder-populated at this stage).
- SEC-AC: `uv.lock` is committed and `uv sync --locked` succeeds (pinned dependency tree —
  DESIGN §20.2 T10 substrate; the CI license/audit gates land in issue 54).

## Validation

`uv sync && uv run pytest tests/test_smoke.py && uv run ruff check . && uv run mypy src/paperdeck && uv build`

## Dependencies

None (first issue).

## Non-goals

No functional logic; no CI workflow (issue 54); no README content (issue 53); no KaTeX
assets (issue 37).

## Design References

DESIGN §5.1 (layout, dependency list), §22 (packaging), ADR-005 (dependency policy),
ADR-008 (no Node toolchain).
