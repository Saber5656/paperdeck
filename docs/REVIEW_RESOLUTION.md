# Review resolution record

- Repository: `Saber5656/paperdeck`
- Pull request: #23
- Parent head observed before this addendum: `ac6341a94e26f6d0550b6f6ed125238bc2d0e33a`
- Scope: existing review threads only; no new Bot review is requested.
- This document records design-level resolutions and focused verification gates. It does not claim implementation or test completion.

## Thread `PRRT_kwDOTNkEMM6QAWyq`

### Include the provider in the LLM cache key

- Finding: The existing review thread `PRRT_kwDOTNkEMM6QAWyq` identifies this contract gap.
- Normative resolution: Define the cache request identity as normalized provider/base-url origin plus model and request parameters, while keeping provider details out of the value file and excluding credentials.
- Focused verification before resolving this thread: Run the same model request against two provider origins and assert distinct cache entries; repeat the same origin and assert a hit.
- Resolution record status: addressed in this design addendum; implementation/test completion is not claimed here.

## Thread `PRRT_kwDOTNkEMM6QAWyu`

### Reorder latex-bib before latex-refs

- Finding: The existing review thread `PRRT_kwDOTNkEMM6QAWyu` identifies this contract gap.
- Normative resolution: Correct the W2 dependency table and execution order so `latex-bib` produces `BibRef`/`bib_index` before `latex-refs` consumes it; all wave order and references must agree.
- Focused verification before resolving this thread: Run the dependency-table consistency check and assert a topological sort places latex-bib before latex-refs with no contradictory edge.
- Resolution record status: addressed in this design addendum; implementation/test completion is not claimed here.

## Thread `PRRT_kwDOTNkEMM6QAWyx`

### Hash the JSON data island in the CSP

- Finding: The existing review thread `PRRT_kwDOTNkEMM6QAWyx` identifies this contract gap.
- Normative resolution: Treat the `script[type=application/json]` data island as an inline CSP body: serialize it deterministically and include its hash in the generated CSP, or use an explicitly equivalent non-script carrier.
- Focused verification before resolving this thread: Render a document containing `#pd-data`, recompute the CSP over every inline body, and assert the validator reports no CSP mismatch.
- Resolution record status: addressed in this design addendum; implementation/test completion is not claimed here.

## Thread `PRRT_kwDOTNkEMM6QAWy7`

### Render placeholders for assets dropped by the bundle

- Finding: The existing review thread `PRRT_kwDOTNkEMM6QAWy7` identifies this contract gap.
- Normative resolution: When an IR asset id has no bundle entry because it was dropped by a budget decision, render the specified unavailable-asset placeholder with stable metadata instead of a broken URL; `asset_id is None` remains a separate case.
- Focused verification before resolving this thread: Convert an oversized figure/table that is omitted from the bundle and assert the HTML contains the placeholder and no broken asset reference.
- Resolution record status: addressed in this design addendum; implementation/test completion is not claimed here.

## Thread `PRRT_kwDOTNkEMM6QAWzB`

### Add workflow_call to the CI triggers

- Finding: The existing review thread `PRRT_kwDOTNkEMM6QAWzB` identifies this contract gap.
- Normative resolution: Declare `workflow_call` on `ci.yml` with the inputs and secrets used by the release workflow, keeping normal push and pull-request triggers intact.
- Focused verification before resolving this thread: Parse the workflows and verify the release reusable-workflow reference resolves to a CI workflow that declares `workflow_call`.
- Resolution record status: addressed in this design addendum; implementation/test completion is not claimed here.

## Thread `PRRT_kwDOTNkEMM6QAWzK`

### Define ConversionError in the base taxonomy

- Finding: The existing review thread `PRRT_kwDOTNkEMM6QAWzK` identifies this contract gap.
- Normative resolution: Add `ConversionError` to the base error taxonomy as the normal recoverable engine/fallback signal and map pandoc, HTML-gate, cost, and equivalent failures to it without conflating programmer or security errors.
- Focused verification before resolving this thread: Exercise each fallback failure and assert its class, stable reason code, and fallback decision match the taxonomy.
- Resolution record status: addressed in this design addendum; implementation/test completion is not claimed here.

## Thread `PRRT_kwDOTNkEMM6QAWzO`

### Build PDF structural links after numbers exist

- Finding: The existing review thread `PRRT_kwDOTNkEMM6QAWzO` identifies this contract gap.
- Normative resolution: Split assembly into numbering and linking phases: assign equation/figure/table/section numbers first, then resolve structural references using the resulting `numbers_map` before final serialization.
- Focused verification before resolving this thread: Render a PDF-path document with cross-references and assert every generated link points to the assigned number and target anchor.
- Resolution record status: addressed in this design addendum; implementation/test completion is not claimed here.

## Thread `PRRT_kwDOTNkEMM6QAWzQ`

### Avoid conflicting T shortcut while the resume toast is visible

- Finding: The existing review thread `PRRT_kwDOTNkEMM6QAWzQ` identifies this contract gap.
- Normative resolution: Give the resume toast an explicit, time-bounded shortcut context in which `T` scrolls to the top; suppress the global ToC binding in that context and only restore it after the toast is dismissed or expires.
- Focused verification before resolving this thread: Load a saved position, press `T` while the toast is visible and after it is gone, and assert the first action scrolls while the second toggles the ToC.
- Resolution record status: addressed in this design addendum; implementation/test completion is not claimed here.

## Thread `PRRT_kwDOTNkEMM6QAWzW`

### Align tarfile filter use with Python 3.11 support

- Finding: The existing review thread `PRRT_kwDOTNkEMM6QAWzW` identifies this contract gap.
- Normative resolution: Gate use of `TarFile.extract*`'s `filter` parameter on the actual Python patch version; for Python 3.11.0–3.11.3 use the documented manual safe-extraction path with identical traversal/link checks.
- Focused verification before resolving this thread: Run the extraction safety matrix on Python 3.11.0–3.11.3 and 3.11.4+ (or equivalent compatibility fixtures) and assert no early `TypeError` bypasses the checks.
- Resolution record status: addressed in this design addendum; implementation/test completion is not claimed here.

## Thread `PRRT_kwDOTNkEMM6QAWzb`

### Exclude volatile provenance from the document id hash

- Finding: The existing review thread `PRRT_kwDOTNkEMM6QAWzb` identifies this contract gap.
- Normative resolution: Define the content hash input as canonical semantic IR and explicitly exclude volatile provenance such as `created_at`; preserve source/provenance separately for display and audit.
- Focused verification before resolving this thread: Convert identical semantic content with different creation timestamps and assert equal `docId` and reading-position keys.
- Resolution record status: addressed in this design addendum; implementation/test completion is not claimed here.

## Bot review policy

The existing Bot review is not re-triggered for this PR. Replies and thread resolution are performed only after the focused verification conditions above are recorded.