# Contributing to paperdeck

## Development setup

```sh
git clone https://github.com/Saber5656/paperdeck.git
cd paperdeck
uv sync
```

Install Pandoc using the commands in [`README.md`](README.md), then install browser test dependencies:

```sh
uv run playwright install --with-deps chromium webkit
```

Run the relevant tests with `uv run pytest -m "not playwright"`, `uv run pytest -m pandoc`, `uv run pytest -m security`, and `uv run pytest -m playwright`. The full non-browser suite must keep at least 85% line coverage.

## Golden fixtures and manual sweep

Update a golden only when the output change is intentional:

```sh
uv run pytest --update-goldens
git diff -- tests/goldens
```

Review the generated HTML, IR, warnings, citations, equation assets, and self-containment report before committing the fixture. Before a release, copy and complete this 10-paper sweep:

```text
[ ] 1. single-column text PDF
[ ] 2. two-column text PDF
[ ] 3. dense equations and figures
[ ] 4. bibliography with numeric citations
[ ] 5. author-year citations
[ ] 6. scanned or image-heavy PDF (expected warnings recorded)
[ ] 7. local LaTeX with custom macros
[ ] 8. LaTeX source archive with figures
[ ] 9. arXiv paper with HTML and PDF fallback
[ ] 10. offline conversion from a warmed cache
Notes, source versions, warnings, and output links:
```

## Dependencies and security

Runtime dependencies normally use permissive licenses: MIT, BSD-2-Clause, BSD-3-Clause, Apache-2.0, ISC, Python-2.0, or PSF-2.0. An OR expression permits choosing an allowed license; all AND terms must pass. Existing certifi and PDFium license decisions are recorded in [`docs/DEPENDENCY_LICENSES.md`](docs/DEPENDENCY_LICENSES.md). Do not add AGPL or unreviewed copyleft dependencies, and do not add Pillow at runtime; the PDF engine encodes PNG crops without it. New dependencies require an ADR under [`docs/decisions/`](docs/decisions/) describing license, runtime need, alternatives, and package-data impact.

## Commits and pull requests

Use focused commits with Conventional Commit prefixes. Group dependent issues into a reviewable feature when integration requires it, and retain individual issue acceptance evidence. Include tests, fixture review, security impact, and any manual-sweep evidence in the pull request. CI gates must be green before merge.

## Releasing

1. Bump `src/paperdeck/__init__.py`'s `__version__` (the single version source).
2. Move the release notes from `CHANGELOG.md`'s `Unreleased` section into a versioned section.
3. Run the full test, wheel-content, install-smoke, and manual-sweep checks; record the evidence link.
4. Create and push a stable tag such as `v0.1.0`.
5. Verify the `pypi` environment approval before Trusted Publishing runs. PyPI Trusted Publisher registration is a manual maintainer step.
6. Record the post-release manual sweep and advisory support status.

Merge does not publish a release. The release workflow requires the protected `pypi` environment approval and uses OIDC rather than a long-lived PyPI token. See [`docs/DESIGN.md`](docs/DESIGN.md) §22 for the canonical release design.
