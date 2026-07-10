# ADR-005: MIT license with a permissive-only runtime dependency policy

- Status: Accepted
- Date: 2026-07-08
- Deciders: user (round 3 + explicit confirmation), Fable (dependency policy)

## Context

The repository is public and will be released as OSS. The user's existing projects are MIT
and the product domain (document conversion/reading UI) carries negligible patent risk, so
Apache-2.0's patent clause buys little. The real licensing risk is **dependencies**: the
strongest Python PDF library (PyMuPDF) is AGPL-3.0.

## Decision

1. Project license: **MIT** (LICENSE file at repo root, standard text).
2. Runtime Python dependencies must be MIT/BSD/Apache-2.0/ISC/PSF-class permissive.
   Copyleft (GPL/LGPL/AGPL/SSPL) Python dependencies are forbidden. Concretely: PyMuPDF is
   banned; pypdfium2 (Apache-2.0/BSD-3) is the PDF library.
3. External **subprocess tools** may be GPL (pandoc): separate-process invocation of an
   unmodified, user-installed binary is not derivation and does not affect MIT licensing.
   paperdeck never bundles or redistributes such tools.
4. Vendored frontend assets must be permissive (KaTeX: MIT) and carry their license text in
   the vendored directory and in generated HTML (comment header attribution).
5. CI enforces the policy: a dependency-license check (e.g. `pip-licenses`) fails the build
   on non-permissive runtime deps (dedicated issue; dev-only tools are exempt but recorded).

## Consequences

- Positive: consistent with the user's OSS portfolio; downstream embedding is frictionless;
  the dependency rule is mechanical and CI-enforceable.
- Negative: no patent-retaliation protection (accepted: negligible domain risk); losing
  PyMuPDF's conveniences (accepted: pypdfium2 covers v1 needs — research/03).
