# Title

[W7] 53 Write OSS meta documents (README, LICENSE, SECURITY, CONTRIBUTING)

## Summary

Author the repository's public face: `README.md` (bilingual EN primary / JA section),
`LICENSE` (MIT), `SECURITY.md`, and `CONTRIBUTING.md` including the golden-fixture and
manual-sweep procedures, per DESIGN §20.4/§21/§22 and ADR-005.

## Context

The repo is already public; these files define expectations for users, contributors, and
security reporters before the first release.

## Scope

Four files at repo root. No code changes.

## Detailed Requirements

1. `README.md` (English first, `## 日本語` summary section after):
   - one-paragraph pitch + animated-gif placeholder slot (media added post-v1);
   - install (`uv tool install paperdeck` / `pipx`), pandoc prerequisite + per-OS
     commands, LLM setup (`OPENAI_API_KEY`, config file example pointing at
     OpenAI-compatible servers incl. a localhost Ollama example);
   - quickstart: the three canonical invocations (arXiv id / local tex / local pdf) with
     expected outputs;
   - feature tour table (jumps, previews, math, ToC, themes, position, keys — with the
     key list);
   - engine explanation table (which engine when, fidelity expectations, cost notes,
     `--engine`/`--offline`);
   - honest limitations section (from DESIGN §3.2 + §12.5 caveat + pdf-engine
     best-effort framing + R5 unverified-LaTeX explanation);
   - privacy/security promises: zero external requests in outputs (link SECURITY.md),
     what is sent to the LLM provider (paper text/images) and when (pdf engine only).
2. `LICENSE`: MIT, copyright `2026 Saber5656` (user's GitHub account name).
3. `SECURITY.md` per DESIGN §20.4: report via GitHub Security Advisories (private),
   response target 14 days, supported = latest release, residual-risk statement (T3
   in-process PDF parsing; recommendation to convert untrusted PDFs cautiously),
   the self-containment guarantee definition and how to verify it
   (`python -m paperdeck.render.validate out.html`).
4. `CONTRIBUTING.md`: dev setup (`uv sync`, `pandoc`, `uv run playwright install`),
   test invocations per marker, golden-update procedure (`--update-goldens` + review
   rules), the 10-paper manual sweep checklist (DESIGN §21) as a copyable template,
   dependency policy summary (ADR-005: permissive-only, no AGPL/Pillow note), commit/PR
   conventions (one issue per PR, `[W<n>] <NN>` title prefix), ADR process for new deps.
5. Cross-references to docs/DESIGN.md and docs/decisions/ for depth (docs stay canonical).
6. No badges that imply unbuilt infrastructure (add CI badge only in issue 54's PR).

## Acceptance Criteria

- All four files present; README renders on GitHub without broken links/anchors
  (relative links resolve in the repo tree).
- README quickstart commands and the config example are written against DESIGN §6/§7
  verbatim (documentation-only check at this stage; a follow-up line item in issue 50's
  Validation runs `paperdeck doctor` against the README config example once the CLI
  exists).
- SEC-AC: SECURITY.md contains the exact verification command string
  `python -m paperdeck.render.validate` and states the zero-external-request guarantee
  and the T3 residual risk (grep-able assertions in `tests/unit/test_docs_links.py`).
- LICENSE year/holder correct.
- Language rule respected: English canonical, Japanese section is a faithful summary
  (not a divergent spec).

## Validation

Documentation-only: `tests/unit/test_docs_links.py` (relative links resolve; SECURITY.md
grep assertions) + manual review. No product-code execution is required by this issue.

## Dependencies

— (content is written against DESIGN §6/§7; if later CLI issues change flags, updating
the README is part of *those* issues' scope).

## Non-goals

Docs website (v2); demo media capture (post-v1); CHANGELOG (starts at release, issue 55).

## Design References

DESIGN §20.4, §21, §22, §3.2; ADR-005, ADR-006; R11.
