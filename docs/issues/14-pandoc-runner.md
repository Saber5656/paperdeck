# Title

[W2] 14 Implement the hardened pandoc subprocess runner

## Summary

Implement `src/paperdeck/engines/latex/pandoc.py`: version-checked, hardened invocation of
`pandoc -f latex+raw_tex -t json` returning the parsed AST dict, per DESIGN §12.2.

## Context

pandoc is the only external tool in the product; it parses attacker-supplied input, so the
subprocess boundary must be strict, and its absence must degrade cleanly (selection reason
`pandoc-missing`).

## Scope

- `pandoc_version() -> tuple[int,int] | None` (None = not installed).
- `run_pandoc(flattened: Path, cwd: Path, timeout_s: int = 120) -> PandocResult` where
  `@dataclass(frozen=True) class PandocResult: ast: dict; warnings: list[str];
  version: tuple[int, int]`.
- `PandocNotFoundError(ConversionError)` with per-OS install hint text.

## Detailed Requirements

1. Discovery: `shutil.which("pandoc")`; version parsed from first line of
   `pandoc --version`; require ≥ (3,0) else treat as missing (with a message that names
   the found version).
2. Invocation via `subprocess.Popen([pandoc, "-f", "latex+raw_tex", "-t", "json",
   "--quiet", str(flattened)], cwd=cwd, env={"PATH": os.environ["PATH"]},
   stdin=subprocess.DEVNULL, stdout=PIPE, stderr=PIPE)` — argv list only (never
   `shell=True`), minimal env, stdin closed.
3. stdout read in 1 MiB chunks with a **real streaming cap**: past 200 MB, kill the
   process and raise `ConversionError("pandoc-output-cap")`. Wall timeout `timeout_s`
   enforced around the read loop; expiry kills the process →
   `ConversionError("pandoc-timeout")`.
4. Nonzero exit → `ConversionError("pandoc-failed")` including the last 2 KB of stderr
   (sanitized: control chars stripped).
5. JSON parse errors → `ConversionError("pandoc-bad-json")`. Validate top-level shape:
   `{"pandoc-api-version": [...], "blocks": [...], "meta": {...}}`.
   (Distinct codes `pandoc-failed` / `pandoc-timeout` / `pandoc-output-cap` /
   `pandoc-bad-json` are intentional refinements of DESIGN §12.2's failure clause; all
   are `ConversionError`s and feed §9 fallback identically.)
6. pandoc stderr warnings (when exit 0) → `PandocResult.warnings` for provenance.
7. `PandocResult.version` feeds `Document.provenance.engine_versions`.

## Acceptance Criteria

- Tests use a stub executable placed on PATH (shell script emitting canned JSON /
  sleeping / failing) — no real pandoc needed: version gate, timeout kill, nonzero exit,
  bad JSON, stderr capture, env minimalism (stub asserts `env` contains only PATH),
  argv shape (no shell interpolation: filename with spaces & `;rm` passes through as one
  arg).
- Integration test marked `@pytest.mark.pandoc` (skipped when absent, mandatory in CI):
  real pandoc converts a 5-line fixture; AST shape validated.
- SEC-AC: flattened path containing shell metacharacters is executed safely (stub echoes
  argv; test asserts single argument).

## Validation

`uv run pytest tests/unit/test_pandoc_runner.py -q`

## Dependencies

01, 02.

## Non-goals

AST semantics (15); doctor reporting (50 reuses `pandoc_version`).

## Design References

DESIGN §12.2; ADR-002; ADR-007 §1.
