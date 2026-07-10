# Title

[W7] 55 Implement packaging polish and the release workflow

## Summary

Finalize distribution: sdist/wheel completeness checks, `pipx`/`uv tool` smoke test, the
tag-driven release workflow publishing to PyPI via Trusted Publishing (OIDC), GitHub
Release notes, and CHANGELOG bootstrap, per DESIGN §22.

## Context

Last mile of v1: everything green must become an installable artifact through a
supply-chain-sane pipeline (no long-lived PyPI tokens).

## Scope

- `.github/workflows/release.yml` (tag `v*` trigger).
- Wheel-content test; install smoke test; `CHANGELOG.md`; version-bump procedure.

## Detailed Requirements

1. Wheel content test (`tests/unit/test_wheel_contents.py`, runs in CI `gates` job from
   54 — this issue adds it): build via `uv build` in a temp dir, open the wheel, assert
   presence of: templates, `viewer.js/css`, `vendor/katex/**` + `MANIFEST.json` +
   KaTeX `LICENSE`, `ir-v1.json`, prompts, schemas; assert absence of `tests/**`,
   fixtures, `.pyc`.
2. Install smoke (CI job in release workflow, also runnable locally): the job installs
   pandoc, then `pipx install dist/*.whl` in a clean venv → `paperdeck --version`;
   `paperdeck doctor --json` (all required checks pass; `pandoc` check is `ok` since the
   job installed it; `api-key` warn is expected); the job writes a minimal `.tex` via
   here-doc, runs `paperdeck convert` on it, and validates the output with
   `python -m paperdeck.render.validate`.
3. `release.yml`: trigger on tag `v*`; a regex gate step classifies the tag —
   `^v\d+\.\d+\.\d+$` = stable (full pipeline incl. publish), anything else (e.g.
   `v0.1.0-rc1`) = dry-run (all jobs except publish; publish step skipped with a notice).
   Jobs: (a) verify tag version == `paperdeck.__version__` (script; runs for both
   classes, comparing the `v`-stripped, pre-release-suffix-stripped form), (b) full CI
   reuse (workflow_call to ci.yml), (c) build, (d) smoke, (e) publish via
   `pypa/gh-action-pypi-publish` pinned by SHA using **Trusted Publishing**
   (`id-token: write` permission on the publish job ONLY; environment `pypi` with manual
   approval enabled noted for repo settings; runs only for stable tags), (f) GitHub
   Release with generated notes + CHANGELOG excerpt. PyPI project-side Trusted Publisher
   registration is a manual maintainer step — documented in the workflow header comment
   and RELEASING section.
4. `CHANGELOG.md`: Keep-a-Changelog format, `## [Unreleased]` seeded with a v1 summary
   line; release procedure appends.
5. `RELEASING.md` section inside CONTRIBUTING (edit): bump version → update CHANGELOG →
   tag → push tag → verify environment approval → post-release manual sweep record link.
6. merge ≠ release rule (user's global policy) encoded: release requires the manual
   environment approval gate even after merge.

## Acceptance Criteria

- Wheel content test green; a deliberately broken package-data glob fails it (proven in
  PR description with a local run).
- Release workflow dry-run: an `-rc` tag runs all jobs with publish skipped (the regex
  gate proven); version-mismatch tag fails job (a).
- SEC-AC: `id-token: write` appears only in the publish job and the publish step is
  reachable only via the stable-tag regex gate + the `pypi` environment approval
  (asserted by extending `tests/unit/test_workflow_hygiene.py` to release.yml); all
  actions SHA-pinned.
- CHANGELOG + RELEASING sections exist and match the actual workflow steps.

## Validation

`uv run pytest tests/unit/test_wheel_contents.py tests/unit/test_workflow_hygiene.py -q`
+ release workflow dry-run evidence in the PR.

## Dependencies

54.

## Non-goals

Homebrew formula, conda, Docker images (v2); signing/SLSA provenance (v2 idea, noted in
SECURITY.md later).

## Design References

DESIGN §22; ADR-005 §4 (license files in artifacts), ADR-007 (supply chain);
user policy: merge ≠ release.
