# Title

[W1] 09 Implement the cache manager (XDG layout, atomic writes)

## Summary

Implement `src/paperdeck/input/cache.py`: the `CacheManager` owning the on-disk cache tree
of DESIGN §8.5 with atomic writes and the operations needed by `cache ls/clear/path`.

## Context

All fetched artifacts and LLM responses persist here; correctness (atomicity, stable
pathing) enables offline mode and free re-runs.

## Scope

- `CacheManager(root: Path)` (root from `platformdirs.user_cache_path("paperdeck")`).
- Path builders: `arxiv_dir(id, version) -> Path` (old-style `/`→`--`),
  `llm_dir(model) -> Path` (model name sanitized here: `[^A-Za-z0-9._-]` → `_`; issue 28
  reuses this builder and must not re-implement sanitization).
- `put(path_key: str, source: Path | bytes) -> Path` atomic (tmp+rename, fsync dir on
  POSIX), `get(path_key) -> Path | None`, `exists`, `entries() -> list[CacheEntry]`
  (id, version, kinds present, total bytes), `clear(arxiv_id: str | None)`.
- `path_key` grammar (validated on every call): a relative POSIX path under the cache
  root, matching `^[A-Za-z0-9._/-]+$`, no `..` segment, no leading `/`; violation →
  `SecurityError("cache-key-invalid")`.

## Detailed Requirements

1. Layout exactly DESIGN §8.5 (file names `meta.xml`, `source.tar.gz|source.tex|
   source.pdf`, `paper.pdf`, `html/index.html`, `html/assets/<name>` — asset basenames
   are chosen by the caller (issue 12 uses `<sha1-of-src><ext>`); the cache only enforces
   the `path_key` grammar).
2. Version handling: `version=None` maps to directory `latest-unknown` only transiently —
   callers must re-home entries once metadata reveals the version; provide
   `promote(id, resolved_version)` doing the atomic directory rename.
3. `clear` refuses to operate when `root` does not end with `/paperdeck` (paranoia guard
   against misconfigured root), and uses `shutil.rmtree` on validated subdirs only.
4. Permissions: dirs 0755 except `llm/` 0700; files 0644 (llm files 0600).
5. No locking in v1; concurrent-run caveat documented in module docstring (DESIGN §8.5).
6. `CacheEntry.total_bytes` computed lazily; `ls` output formatting stays in the CLI
   (issue 49), not here.

## Acceptance Criteria

- Unit tests (tmp_path): atomicity (crash-sim: tmp file left behind is ignored and
  cleaned); old-style id mapping `hep-th/9901001` → `hep-th--9901001`; promote() moves
  content and is idempotent; clear(None) empties only the paperdeck root; permission bits
  asserted on POSIX.
- SEC-AC: `clear` with a doctored root (`/tmp`) raises `SecurityError` and deletes nothing.
- SEC-AC: `put("../escape.bin", …)`, `put("/abs.bin", …)`, and a `path_key` with a NUL
  byte each raise `SecurityError("cache-key-invalid")` and write nothing (path
  confinement proven).
- mypy strict.

## Validation

`uv run pytest tests/unit/test_cache.py -q`

## Dependencies

01, 02, 04.

## Non-goals

What gets cached when (11–12, 28); CLI presentation (49).

## Design References

DESIGN §8.5, §17; ADR-007 §7.
