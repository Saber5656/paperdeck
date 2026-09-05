# paperdeck — v1 Design Specification

Status: Draft for review (canonical source of truth for v1)
Date: 2026-07-08
Language note: repository docs are English; user-facing README may be bilingual.

This document is the single canonical specification. Issues in `docs/issues/` reference
sections here by number (e.g. `DESIGN §12.5`). If an issue and this document disagree, this
document wins and the issue must be updated.

---

## 1. Product overview

**paperdeck** converts an academic paper (arXiv ID/URL, LaTeX source, or PDF) into a single
self-contained HTML file that provides a modern reading experience:

- **Reference jumps**: in-text references (`Eq. (3)`, `Fig. 2`, `[12]`, `§4.1`) become links
  that jump to their target, with a floating **Back** control returning to the reading
  position.
- **Hover previews**: hovering (or focusing) a reference shows the target — the rendered
  equation, figure thumbnail + caption, bibliography entry, or section heading — in a popup
  without losing reading position.
- **Beautiful math**: LaTeX math re-rendered with KaTeX; PDF-derived math shown as
  high-resolution image crops with clearly-marked unverified LaTeX copy text.
- **Reading comfort**: table of contents sidebar, light/dark theme, reading-position
  restore, keyboard navigation — all offline, in one portable file.

One CLI command in, one `.html` file out. No server, no account, no telemetry.

## 2. Confirmed requirements (user decisions, 2026-07-08)

| # | Decision | Value |
|---|---|---|
| R1 | Form factor | CLI producing static HTML; no resident server |
| R2 | Input scope | Hybrid: arXiv (high quality) + arbitrary PDFs (best effort) + local files |
| R3 | arXiv path | Deterministic (no LLM): official arXiv HTML or LaTeX source via pandoc |
| R4 | PDF path | LLM-required: structure via LLM, math via VLM |
| R5 | PDF math | Cropped image is ground truth; VLM LaTeX attached as **unverified** copy text |
| R6 | Math hover | v1 = reference preview popups; symbol-definition hover is v2 |
| R7 | LLM access | OpenAI-compatible API; default OpenAI; `base_url`/`model` configurable |
| R8 | Stack | Python (≥3.11); viewer in framework-free vanilla JS/CSS |
| R9 | Output | Single self-contained HTML; zero external requests |
| R10 | Viewer v1 | ToC sidebar, light/dark theme, position save/restore, keyboard nav (+ core: jumps, previews, back) |
| R11 | License | MIT; permissive-only runtime dependencies (no AGPL/GPL Python deps) |
| R12 | arXiv fetch | By ID/URL with rate-limited allowlisted network; local files also accepted |

Related ADRs: 001 (engines), 002 (pandoc), 003 (KaTeX), 004 (LLM), 005 (license),
006 (single-file + CSP), 007 (security), 008 (viewer).

## 3. Goals and non-goals

### 3.1 v1 goals

1. `paperdeck convert 2401.12345` produces a correct, pleasant, offline-readable HTML for a
   typical recent arXiv paper in under ~60 s (network permitting), with working reference
   jumps, previews, ToC, themes, position restore, and keyboard navigation.
2. `paperdeck convert paper.pdf` produces a best-effort reading experience for any academic
   PDF using the configured LLM, with explicit cost display and guardrails.
3. All outputs pass the machine-checked self-containment invariant (ADR-006).
4. A contributor can install and run everything with `uv sync` + `pandoc` present; CI is
   green with lint, types, tests, license gate, and asset checksums.

### 3.2 v1 non-goals

- No library/collection management, no search across papers, no annotations/highlights.
- No symbol-definition hover (v2), no summarization, no translation.
- No inline-math extraction on the PDF path (display equations only).
- No mobile-specific app; the HTML must merely remain usable on mobile browsers.
- No Windows CI in v1 (macOS + Linux); Windows likely works but is untested.
- No `--dir` output mode; no PDF re-export.
- No sandboxed PDF parsing (documented residual risk, ADR-007 §8).

### 3.3 v2 deferred ideas

Symbol-definition hover (LLM), LaTeXML-local backend, MathJax fallback, GROBID/local-ML
offline PDF path, citation resolution via Crossref/Semantic Scholar, `--dir` output,
annotation layer, library index page, PDF-parse sandboxing, EPS figure support via
ghostscript, Windows CI.

## 4. Glossary

| Term | Meaning |
|---|---|
| IR | Intermediate Representation — engine-independent document model (§10) |
| Engine | A converter producing IR: `arxiv-html`, `latex`, `pdf` (§9, §11–13) |
| Anchor | Stable element id in the output HTML (`eq-12`, `bib-3`, …) (§10.4) |
| RefLink | IR inline node linking to an anchor with a kind (`eq`, `fig`, `tab`, `sec`, `bib`, `fn`) |
| Preview | Popup rendering of an anchor's target shown on hover/focus |
| Self-containment | The zero-external-request invariant (ADR-006) |
| Run report | Machine-readable JSON summary of a conversion (§19.3) |

## 5. Architecture overview

```
             ┌────────────────────────────────────────────────────────────┐
 INPUT ──▶   │ resolver (§8.1)                                            │
 (id/url/    │   └─ InputSpec{kind: arxiv|latex-local|pdf-local, …}       │
  path)      └──────────────┬─────────────────────────────────────────────┘
                            ▼
             ┌────────────────────────────────────────────────────────────┐
             │ acquisition (§8.2–8.5)                                     │
             │   ArxivClient ──▶ CacheManager (XDG)   [netgate allowlist] │
             └──────────────┬─────────────────────────────────────────────┘
                            ▼
             ┌────────────────────────────────────────────────────────────┐
             │ engine selection state machine (§9)                        │
             │   arxiv-html (§11)   latex/pandoc (§12)   pdf/LLM (§13)    │
             └──────────────┬─────────────────────────────────────────────┘
                            ▼
                    IR document (§10)  ──▶ ir.validate (JSON Schema)
                            ▼
             ┌────────────────────────────────────────────────────────────┐
             │ renderer (§15): jinja2 → HTML + inlined assets + CSP       │
             │   └─ self-containment validator (§15.6)                    │
             └──────────────┬─────────────────────────────────────────────┘
                            ▼
                  single .html  (viewer runtime §16 runs in browser)
```

### 5.1 Package layout (normative)

```
pyproject.toml
scripts/vendor_katex.py
src/paperdeck/
    __init__.py            # __version__ single source
    cli.py                 # click command group (§6)
    config.py              # §7
    errors.py              # §18
    logsetup.py            # §19 (named to avoid stdlib-logging shadowing)
    report.py              # §19.3
    netgate.py             # §8.4 network gate: allowlist, offline, rate limiter
    input/
        resolver.py        # §8.1
        arxiv.py           # §8.3
        cache.py           # §8.5
        tarsafe.py         # §8.6
    ir/
        model.py           # §10 (pydantic)
        anchors.py         # §10.4
        validate.py        # §10.6
        schema/ir-v1.json  # generated, committed
    engines/
        __init__.py        # Engine protocol + EngineContext (registry added with §9)
        select.py          # §9
        arxiv_html/ fetch.py, quality.py, parse_structure.py, parse_content.py
        latex/      project.py, pandoc.py, ast_map.py, counters.py, refs.py,
                    bib.py, macros.py, graphics.py, engine.py
        pdf/        extract.py, blocks.py, segment.py, equations.py,
                    citations.py, assemble.py, engine.py
    llm/
        client.py          # §14
        cache.py           # §14.5
        cost.py            # §14.6
        schemas/*.json     # LLM response schemas (versioned)
        prompts/*.md       # prompt templates
    render/
        html.py            # §15
        assets.py          # §15.4–15.5
        validate.py        # §15.6
        templates/document.html.j2 (+ partials)
        assets/viewer.js, viewer.css, vendor/katex/** (+ MANIFEST.json)
tests/  (unit/, fixtures/, e2e/)
```

Runtime dependencies (complete list; additions need ADR): `click`, `httpx`, `pydantic`,
`jinja2`, `pypdfium2`, `beautifulsoup4`, `platformdirs`.
External tool: `pandoc` ≥ 3.0 (checked by `doctor`, needed only for the `latex` engine).
Dev-only: `pytest`, `pytest-cov`, `ruff`, `mypy`, `playwright`, `reportlab`, `pip-licenses`.

## 6. CLI specification

Entry point: `paperdeck` (console script). Global flags: `--config PATH`, `-v/--verbose`,
`-q/--quiet`, `--version`.

### 6.1 `paperdeck convert INPUT [options]`

| Option | Default | Meaning |
|---|---|---|
| `INPUT` | — | arXiv ID (`2401.12345`, `2401.12345v2`, `hep-th/9901001`, `arXiv:…`), arXiv abs/pdf/html URL, or local path (`.pdf`, `.tex`, `.tar.gz`, `.tgz`, `.tar`, `.gz` single-file) |
| `-o, --output PATH` | `./<slug>.html` (§6.4) | Output file path |
| `--engine {auto,arxiv-html,latex,pdf}` | `auto` | Engine override (§9) |
| `--offline` | off | Forbid all network (fetch + LLM). Cached artifacts allowed |
| `--force` | off | Overwrite existing output file |
| `--max-cost USD` | config `llm.max_cost_usd` | LLM budget for this run |
| `--yes` | off | Skip interactive cost confirmation (§14.6) |
| `--no-llm-cache` | off | Bypass LLM disk cache (still writes it) |

Behavior contract:
1. Resolve input → acquire artifacts → select engine (§9) → convert → validate IR → render →
   validate self-containment → write output atomically (temp file + rename).
2. stderr shows progress lines; stdout stays clean except the final absolute output path
   (machine-friendly). `--quiet` silences progress, not errors.
3. On engine fallback, print one line: `engine: arxiv-html failed (reason) -> falling back to latex`.
4. Before any LLM spending: print estimate and ask `Proceed? [y/N]` unless `--yes` (§14.6).
5. Exit codes per §18. A run report JSON is always written next to the output as
   `<output>.report.json` (disable with `--quiet`? no — always; small).

### 6.2 `paperdeck fetch ARXIV_ID [--kind source|pdf|html|all]`

Downloads into cache only (no conversion), prints cache paths. Default kind: `all`
(best-effort; missing HTML is not an error).

### 6.3 `paperdeck cache {path|ls|clear}` / `paperdeck doctor`

- `cache path`: print cache root. `cache ls`: table of cached papers + sizes.
  `cache clear [ARXIV_ID]`: delete all or one entry (confirmation unless `--yes`).
- `doctor`: checks and reports — Python version; pandoc presence/version; KaTeX vendored
  checksum match; config file validity; API key env presence (name only, never value);
  network reachability of `export.arxiv.org` and LLM `base_url` (skipped with `--offline`);
  cache dir writability. Exit 0 only if all required checks pass (network checks are
  warnings, not failures).

### 6.4 Output naming (slug)

arXiv inputs: `arxiv-<id>[v<N>].html` with `/` → `-` for old-style IDs
(`arxiv-hep-th-9901001.html`). Local inputs: `<input-basename>.html`. Existing file without
`--force` → exit 10.

## 7. Configuration

File: `<XDG_CONFIG_HOME>/paperdeck/config.toml` (via `platformdirs`; macOS:
`~/Library/Application Support/paperdeck/config.toml` — platformdirs default). Missing file
= all defaults. Unknown keys → error (typo safety). `paperdeck doctor` validates.

Precedence (high→low): CLI flag > environment variable > config file > built-in default.

```toml
schema_version = 1

[llm]
base_url    = "https://api.openai.com/v1"
model       = "gpt-5.6-terra"
vlm_model   = "gpt-5.6-terra"
api_key_env = "OPENAI_API_KEY"   # NAME of the env var holding the key
timeout_s   = 120
max_retries = 3
max_cost_usd = 1.50
cache       = true

[llm.pricing."gpt-5.6-terra"]
input_per_mtok  = 2.50
output_per_mtok = 15.00
[llm.pricing."gpt-5.6-luna"]
input_per_mtok  = 1.00
output_per_mtok = 6.00
# image inputs approximated as flat tokens per image for estimation:
[llm.estimate]
image_tokens_flat = 1100
chars_per_token   = 4.0

[fetch]
timeout_s       = 60
max_download_mb = 200

[limits]
max_pdf_pages        = 500
max_input_mb         = 200
max_archive_members  = 2000
max_archive_total_mb = 500
embed_warn_mb        = 25
embed_hard_max_mb    = 50

[output]
default_dir = "."
```

Environment variables (flat, fixed set): `PAPERDECK_CONFIG`, `PAPERDECK_OFFLINE=1`,
`PAPERDECK_LLM_BASE_URL`, `PAPERDECK_LLM_MODEL`, `PAPERDECK_LLM_VLM_MODEL`,
`PAPERDECK_MAX_COST_USD`. The API key itself is read from the env var named by
`api_key_env` — paperdeck never persists key material (ADR-007 §5).

`config.py` exposes one frozen `Settings` pydantic model; construction performs full
validation with actionable messages (bad key path, expected type, allowed range).

## 8. Input resolution and acquisition

### 8.1 Resolver (`input/resolver.py`)

`resolve(raw: str) -> InputSpec`. Classification order:

1. Existing local path → by suffix: `.pdf` → `pdf-local`; `.tex` → `latex-local(single)`;
   `.tar|.tar.gz|.tgz|.gz` → `latex-local(archive)`; else → `InputError`.
2. arXiv URL forms (host in `arxiv.org`, `www.arxiv.org`, `export.arxiv.org`; path
   `/abs/<id>`, `/pdf/<id>[.pdf]`, `/html/<id>`) → `arxiv` with extracted id + version.
3. Bare arXiv IDs: new-style `^\d{4}\.\d{4,5}(v\d+)?$`; old-style
   `^[a-z-]+(\.[A-Z]{2})?/\d{7}(v\d+)?$`; `arXiv:` prefix stripped. → `arxiv`.
4. Anything else → `InputError` with examples of accepted forms.

`InputSpec` fields: `kind`, `arxiv_id?`, `version?`, `path?`, `original: str`.

### 8.2 Acquisition flow (arXiv inputs)

Metadata (Atom) is fetched first (cache-first) to learn title/authors/abstract and the
latest version when the input omitted `v<N>`. Then artifacts are fetched lazily — only what
the selected engine needs (§9): HTML page (+ its referenced images), or e-print, or PDF.

### 8.3 `ArxivClient` (`input/arxiv.py`)

- Endpoints per research/01: metadata `GET https://export.arxiv.org/api/query?id_list=<id>`;
  e-print `GET https://export.arxiv.org/e-print/<idv>`; pdf `GET
  https://export.arxiv.org/pdf/<idv>`; html `GET https://arxiv.org/html/<idv>` (try
  `export.arxiv.org` first; on 404/redirect-loop use `arxiv.org`).
- All requests go through `netgate` (§8.4). `User-Agent:
  paperdeck/<version> (+https://github.com/Saber5656/paperdeck)`.
- e-print content sniffing: gzip-tar vs gzip-single-tex vs raw PDF (magic bytes, not
  Content-Type alone). Streams to cache with size cap `fetch.max_download_mb`.
- Atom parsing uses `defusedxml`-style hardening: stdlib `xml.etree` with entity resolution
  disabled (no DTD/external entities).

### 8.4 `netgate` (single network gate)

Every HTTP request in the whole codebase is created through
`netgate.client(purpose: "arxiv"|"llm")`, which enforces:

| Rule | arxiv | llm |
|---|---|---|
| Host allowlist | `export.arxiv.org`, `arxiv.org`, `www.arxiv.org` | host of configured `base_url` only |
| Rate limit | ≥ 3.0 s between requests, process-wide, single connection | provider-side; no local limit |
| TLS verify | always | always |
| Redirects | only within arxiv allowlist | not followed |
| Offline mode | request → `FetchError(code="offline")` | request → `FetchError(code="offline")` |
| Response cap | `fetch.max_download_mb` streamed | 20 MB |

No other module may construct an HTTP client (enforced by a grep-based CI check for
`httpx.` outside `netgate.py` — see issue on CI).

### 8.5 Cache layout (`input/cache.py`)

Root: `<XDG_CACHE_HOME>/paperdeck/` (platformdirs). Layout:

```
cache/
  arxiv/<id-with-slashes-as-->/<version>/
      meta.xml            # raw Atom entry
      source.tar.gz | source.tex | source.pdf   # e-print (as sniffed)
      paper.pdf
      html/index.html + html/assets/<fetched images>
  llm/<model>/<sha256-of-request>.json          # §14.5
```

Writes are atomic (temp + rename). `cache ls/clear` operate on this tree. No locks in v1
(single-user CLI; concurrent runs may re-download — acceptable, documented).

### 8.6 Safe archive extraction (`input/tarsafe.py`)

`extract_tar(src: Path, dest: Path, limits) -> list[Path]` — mandatory for every tar/gzip
input (ADR-007 §2): rejects absolute member names, `..` segments, symlink/hardlink members
whose target escapes `dest`, device/FIFO members; enforces `limits.max_archive_members`,
per-member and `max_archive_total_mb` caps (checked while streaming, not from headers);
normalizes permissions (0644/0755); returns extracted file list. Gzip-single-file inputs are
size-capped during decompression (bomb defense).

## 9. Engine selection state machine (`engines/select.py`)

Inputs: `InputSpec`, `--engine`, `--offline`, cache state, config. Output: ordered engine
attempt plan; execution stops at first success. All transitions logged + recorded in
provenance (`fallbacks: [{engine, reason_code, detail}]`).

States and transitions (`auto` mode):

| # | Condition | Plan |
|---|---|---|
| A1 | `arxiv` input | try `arxiv-html` → `latex` → `pdf` |
| A2 | `arxiv` + `--offline` | same plan, but each engine only if its artifact is already cached; else skip with reason `offline-uncached` |
| L1 | `latex-local` | `latex` only |
| P1 | `pdf-local` | `pdf` only |
| F1 | `--engine X` | `X` only (invalid combination — e.g. `arxiv-html` for a local pdf — is exit 2 with explanation) |

Per-engine gate before attempt (a gate needing fetched artifacts may run at the start of
`convert()`; a `ConversionError` whose `code` is in the reason vocabulary below is
recorded by selection as that reason verbatim, any other code as `convert-failed:<code>`):

- `arxiv-html`: artifact fetchable (HTTP 200) AND quality gate passes (§11.2), else one of
  the reasons `html-unavailable`, `html-stub`, `html-no-content`, `html-missing-title`,
  `html-low-quality` (gate emits the specific code; selection records it verbatim).
- `latex`: e-print is tex/tar (not PDF-only submission), pandoc present (else reason
  `pandoc-missing` with install hint), main tex found.
- `pdf`: PDF artifact exists (fetch if arXiv), LLM configured (API key present or
  `base_url` local), cost confirmation passed. `pdf` never runs implicitly without the §14.6
  confirmation (interactive or `--yes`).

If the plan is exhausted: exit 5 with a table of engines and reasons.

## 10. Intermediate Representation (IR)

The IR is the contract between engines and the renderer. It is defined as pydantic models
(`ir/model.py`) mirrored 1:1 by a committed JSON Schema (`ir/schema/ir-v1.json`, generated
by a script and checked in CI for drift). `schema_version: "1"`.

### 10.1 Document

| Field | Type | Notes |
|---|---|---|
| `schema_version` | `"1"` | literal |
| `source` | Source | `{kind: "arxiv"\|"local", arxiv_id?, version?, original: str}` |
| `provenance` | Provenance | `{engine, engine_versions: {paperdeck, pandoc?, katex}, created_at: ISO8601, fallbacks: [FallbackNote], llm?: {model, vlm_model, calls, tokens_in, tokens_out, cost_usd}}` |
| `meta` | Meta | `{title: [Inline], authors: [str], abstract?: [Block], links: [{url, kind: "arxiv"\|"doi"\|"generic"}]}` |
| `macros` | `dict[str,str]` | LaTeX macro name → definition, for KaTeX (§12.7) |
| `body` | `[Block]` | document order |
| `bibliography` | `[BibEntry]` | may be empty |
| `footnotes` | `[FootnoteDef]` | may be empty |
| `assets` | `dict[str, Asset]` | id → asset |
| `labels` | `dict[str,str]` | original label (`\label` value or source id) → anchor id |
| `warnings` | `[Warning]` | `{code, message, where?}` |

### 10.2 Block nodes

All blocks have `id` (anchor, §10.4). `number` fields are display strings (`"3"`, `"4.2"`).

| Node | Fields |
|---|---|
| `Section` | `level: 1..6`, `number?`, `title: [Inline]`, `children: [Block]` |
| `Paragraph` | `content: [Inline]` |
| `Equation` | `number?`, `label?`, `content_kind: "latex"\|"image"`, `latex?`, `asset_id?`, `latex_verified: bool`, `confidence?: 0..1` — invariants: `content_kind=latex ⇒ latex set ∧ latex_verified=true`; `content_kind=image ⇒ asset_id set ∧ latex_verified=false` |
| `Figure` | `number?`, `label?`, `asset_id?`, `caption: [Inline]`, `alt_text?` (missing asset ⇒ placeholder rendering + warning) |
| `Table` | `number?`, `label?`, `caption: [Inline]`, `content_kind: "grid"\|"image"`, `rows?: [[Cell]]` (`Cell = {content:[Inline], header: bool, colspan: int=1, rowspan: int=1}`), `asset_id?` |
| `ListBlock` | `ordered: bool`, `items: [[Block]]` |
| `Quote` | `content: [Block]` |
| `CodeBlock` | `text: str`, `language?` |
| `FootnoteDef` | `number`, `content: [Block]` |
| `Unhandled` | `text: str` (plain-text degradation of unsupported constructs; always paired with a Warning) |
| `BibEntry` | `id`, `number?: str` (display number, e.g. `"12"`), `label?: str` (natbib author-year display label, e.g. `"Smith et al., 2020"`), `key?: str` (source citation key), `content: [Inline]`, `urls: [{url, kind: "doi"\|"arxiv"\|"generic"}]` (bibliography list item; lives in `Document.bibliography`) |

### 10.3 Inline nodes

| Node | Fields |
|---|---|
| `Text` | `text` |
| `Emph` / `Strong` / `Sub` / `Sup` | `content: [Inline]` |
| `Code` | `text` |
| `Math` | `latex` (inline math; LaTeX/arXiv engines only) |
| `RefLink` | `target_id`, `kind: "eq"\|"fig"\|"tab"\|"sec"\|"bib"\|"fn"`, `text: str` (display text as authored, e.g. `(3)`, `Fig. 2`, `[12]`) |
| `Cite` | `bib_ids: [str]`, `text: str` (rendered as one or more RefLink-equivalent anchors at render time) |
| `ExtLink` | `url`, `content: [Inline]` — URL scheme must be `https`/`http`/`mailto`; others dropped to Text + warning |
| `FootnoteRef` | `target_id`, `number` |
| `LineBreak` | — |

### 10.4 Anchor id scheme (`ir/anchors.py`)

Sequential per type in document order: `sec-1…`, `eq-1…`, `fig-…`, `tab-…`, `bib-…`,
`fn-…`, `para-…`. Ids are assigned by a single `AnchorAllocator` used by every engine
(stable for identical input). `labels` maps source labels → these ids. `RefLink.target_id`
must exist in the document (validator-enforced); unresolvable references degrade to
`RefLink` with `kind` kept and `target_id=""` plus a warning — the renderer styles these as
inert (no link), never broken links.

### 10.5 Asset

`{id, mime: "image/png"|"image/jpeg"|"image/svg+xml", data_b64, width_px?, height_px?,
origin: {engine, source_path?|page?}}`. SVG policy: embedded only via `<img src="data:">`
(never inline SVG), `<script>` elements stripped defensively at ingest (§11.4, ADR-007).

### 10.6 Validation (`ir/validate.py`)

Checks beyond pydantic: every `RefLink.target_id`/`Cite.bib_ids`/`FootnoteRef.target_id`
either resolves to an existing id or is `""`; every `asset_id` exists; anchor ids unique;
equation invariants (§10.2); every `labels` value is an existing anchor id (violation =
hard failure naming the label). Total decoded asset size is measured here and emitted as
warning `assets-over-budget` when above `limits.embed_hard_max_mb` — enforcement (dropping
to fit) is the renderer's job (§15.5), never a validation failure. Runs after every
engine, before rendering. Failure = engine failure (feeds §9 fallback).

## 11. Engine A: `arxiv-html`

### 11.1 Fetch (`engines/arxiv_html/fetch.py`)

Fetch `html/<idv>` page via ArxivClient into cache; then fetch every `<img>`-referenced
same-host relative asset (rate-limited, size-capped, count-capped at 200) into
`html/assets/`. Cross-host or absolute-URL images are **not** fetched (recorded as warnings;
figure placeholder used).

### 11.2 Quality gate (`engines/arxiv_html/quality.py`)

Reject (reason `html-low-quality`) if any of: `<title>` missing/empty; no
`.ltx_section`/`.ltx_para` content at all; count of elements with class matching
`ltx_ERROR|ltx_missing` exceeds `max(20, 1 per 2KB of text)`; page is a stub ("HTML is not
available for this paper" pattern). Thresholds are constants with rationale comments;
tunable only via code.

### 11.3 Structure mapping (`parse_structure.py`)

BeautifulSoup (builtin `html.parser`). Mapping table (normative; unknown `ltx_*` classes →
`Unhandled` + warning). Split of work: the structure pass implements the
section/paragraph/figure/table/list rows and collects math, cross-ref, citation,
bibliography, and footnote elements as opaque placeholders; the content pass (§11.4)
converts those placeholder rows:

| LaTeXML construct | IR |
|---|---|
| `.ltx_title_document` | `meta.title` |
| `.ltx_creator .ltx_personname` | `meta.authors[]` |
| `.ltx_abstract` | `meta.abstract` |
| `section.ltx_section/.ltx_subsection/.ltx_subsubsection` + `.ltx_title` (leading tag text → `number`) | `Section` (level from class) |
| `.ltx_para > .ltx_p` | `Paragraph` |
| `figure.ltx_figure` + `.ltx_caption` + `img` | `Figure` |
| `figure.ltx_table` / `table.ltx_tabular` | `Table(grid)` (colspan/rowspan honored) |
| `.ltx_equation` / `.ltx_equationgroup` (+`.ltx_tags` → `number`) | `Equation(latex)` per numbered row |
| `.ltx_bibliography .ltx_bibitem` | `BibEntry` (tag text → `number`) |
| `.ltx_note` (footnotes) | `FootnoteDef` + `FootnoteRef` |
| lists/quotes/verbatim (`.ltx_itemize/.ltx_enumerate/.ltx_quote/.ltx_verbatim`) | `ListBlock`/`Quote`/`CodeBlock` |

### 11.4 Content mapping (`parse_content.py`)

- Math: `<math>` elements → `Equation.latex` / `Math.latex` from `alttext` attribute
  (LaTeXML preserves source LaTeX there). Missing `alttext` → `Unhandled` + warning.
- Cross-refs: `a.ltx_ref[href^="#"]` → `RefLink` (kind inferred from target element type;
  target ids re-mapped through AnchorAllocator via `labels`).
- Citations: `.ltx_cite a[href^="#bib"]` → `Cite`.
- External links → `ExtLink` (scheme-filtered). Images → assets (§10.5; sniff mime by magic
  bytes, not extension; non-image content rejected).

## 12. Engine B: `latex`

### 12.1 Source project handling (`engines/latex/project.py`)

Input: extracted source dir (from tarsafe) or a single `.tex`. Main-file detection order:
(1) exactly one `.tex` containing `\documentclass`; (2) if several: prefer basenames
`main|paper|ms|arxiv` (that order); (3) else the candidate with the largest transitive
count of `\input`/`\include`-reachable `.tex` files; (4) tie → largest file size +
warning `main-tex-ambiguous`. Single-file input: that file is the main and the source
root is its parent directory. Flattening: textual replacement of `\input{x}`/`\include{x}` with file
contents (path confinement to source root; missing file → keep command + warning; cycle
detection with max depth 20; comments stripped of `%`-to-EOL outside verbatim first).
Output: one flattened `main.flat.tex` + the preamble slice (before `\begin{document}`).

### 12.2 pandoc invocation (`engines/latex/pandoc.py`)

`pandoc -f latex+raw_tex -t json --quiet main.flat.tex`, run with: argv list (no shell),
cwd = source root, env = minimal (`PATH` only), wall timeout 120 s, stdout cap 200 MB,
stderr captured for warnings. Version check `pandoc --version` ≥ 3.0 once per run.
Nonzero exit / timeout / unparseable JSON → `ConversionError("pandoc-failed")`.

### 12.3 AST mapping (`engines/latex/ast_map.py`)

pandoc-AST → IR skeleton. Handled pandoc nodes: `Header`(→Section tree by level),
`Para/Plain`, `Math(InlineMath|DisplayMath)`, `Figure/Image`, `Table`, `BulletList/
OrderedList`, `BlockQuote`, `CodeBlock`, `Note`(→footnotes), `Cite`, `Link`, `Str/Space/
Emph/Strong/Code/Superscript/Subscript/LineBreak`, `RawInline/RawBlock (format=="tex")` →
handed to §12.4–12.5 resolvers; anything else → `Unhandled` + warning. This module does NOT
assign numbers or resolve refs.

### 12.4 Raw-TeX micro-parser (`engines/latex/refs.py`, part 1)

Regex-grade parser over `RawInline` tex for exactly: `\label{…}`, `\ref{…}`, `\eqref{…}`,
`\cref{…}/\Cref{…}` (single + comma lists), `\cite…{…}` variants (natbib `\citep/\citet`
included), `\autoref{…}`, `\footnote{…}` (balanced-brace scan). Unknown raw tex → dropped
with warning (never rendered raw).

### 12.5 Numbering replay (`engines/latex/counters.py`) — normative algorithm

Walk final block sequence in document order, replaying LaTeX counters:

1. Section counters: `section.subsection.subsubsection` dotted numbers; reset children on
   parent increment; `\appendix` (raw block) switches section numbering to `A, B, …`.
2. Equation counter: incremented for every **numbered display row**: environment `equation`
   → 1 number; `align/gather/eqnarray/multline` → 1 per row (split rows on top-level `\\`)
   except rows containing `\nonumber`/`\notag`; starred environments (`equation*` etc.) and
   bare `\[…\]`/`$$…$$` → unnumbered. `\numberwithin{equation}{section}` in preamble ⇒
   format `<sec>.<n>` with reset per section. Multi-row environments become one `Equation`
   per row; each row's `latex` is the row body without the environment wrapper and without
   `\label{}`; rows containing top-level alignment `&` are wrapped in
   `\begin{aligned}…\end{aligned}` (alignment preserved), rows without `&` are kept
   verbatim. `\label` inside a row attaches to that row's Equation.
3. Figure/Table counters: increment per `Figure`/`Table` block containing a caption.
4. Result: `number` strings on nodes + `labels: {latex_label → anchor_id}`.

Known-divergence caveat (documented to users): exotic counter manipulation
(`\setcounter`, `\addtocounter`, custom theorem counters) is not replayed; theorem-like
environments are v2. A validation warning fires when any `\eqref` target resolves to an
unnumbered equation (signals drift).

### 12.6 Reference + citation resolution (`refs.py`, part 2)

`\ref/\eqref/\cref/\autoref` → `RefLink{kind from target node type, text}`: `\eqref` text =
`(<number>)`; `\ref` text = `<number>`; `\cref` text = `<Type>~<number>` with type word from
target kind (`Eq.`, `Fig.`, `Table`, `Section`). Unresolved label → inert RefLink + warning.
`\cite*` → `Cite{bib_ids}` matched against bibliography keys (§12.8); unresolved keys keep
`text=[?]` + warning.

### 12.7 Macro extraction (`engines/latex/macros.py`)

From the preamble slice: `\newcommand{\x}[n]?{body}`, `\renewcommand`, `\def\x{body}`,
`\DeclareMathOperator{\x}{body}` (→ `\operatorname{body}`), `\providecommand`. Emit
`Document.macros` (name → KaTeX-compatible definition string, arg count encoded as KaTeX
`#1…#9` usage — passed through verbatim). Skip (with warning) definitions using TeX
conditionals/expansion primitives. Cap: 500 macros.

### 12.8 Bibliography (`engines/latex/bib.py`)

Priority 1: `.bbl` file (or `thebibliography` env in source): parse
`\bibitem[opt]{key}` entries; entry text = LaTeX-to-text via small inline converter (reuse
ast_map on a per-entry pandoc run is overkill: strip commands, keep text + `\emph` →
Emph + URLs via `\url{}`/`\href{}`). Without `[opt]`: `BibEntry.number` = 1-based
position, `label=None`. With `[opt]` (natbib author-year): `BibEntry.label` = cleaned
label, `number=None`. Priority 2: `.bib` files: tolerant field parser (`author`, `title`, `year`,
`journal|booktitle`, `doi`, `url`, `eprint`) → formatted entry `Author(s). Title. Venue,
Year.` DOI/arXiv eprint → `urls[]`. 

### 12.9 Graphics (`engines/latex/graphics.py`)

`\includegraphics{name}` resolution: try extensions in order `.pdf,.png,.jpg,.jpeg` under
declared `\graphicspath` dirs then source root (path-confined). `.pdf` figure → render page
1 via pypdfium2 at scale such that long side ≤ 2000 px → PNG asset. `.png/.jpg` → validate
magic bytes, cap dimensions (downscale > 4096 px via pypdfium2? no — use PIL? **Pillow is
NOT a dependency**; use pypdfium2 only for PDF rendering. For raster downscaling v1: accept
as-is if ≤ limits, else placeholder + warning — no re-encoder dependency. Revisit v2). `.eps`
→ placeholder + warning (v2: ghostscript). Every asset counted against embed budgets (§15.5).

### 12.10 Assembly (`engines/latex/engine.py`)

Pipeline: project → pandoc → ast_map → macros → counters → refs → bib → graphics →
`ir.validate`. Emits provenance (pandoc version, flatten stats) + all warnings.

## 13. Engine C: `pdf`

### 13.1 Extraction (`engines/pdf/extract.py`)

pypdfium2: enforce `limits.max_pdf_pages` / `max_input_mb` up front; per page: all chars
with boxes (`get_charbox`), page size, and a 2× (144 dpi-equivalent) bitmap rendered lazily
only for pages containing equation/figure/table candidates (memory control).
Encrypted/broken PDFs → `InputError` with clear message.

### 13.2 Deterministic pre-clustering (`engines/pdf/blocks.py`)

Chars → lines (y-overlap ≥ 50% and same baseline cluster) → blocks (vertical gap >
1.8 × median line height splits; column detection via x-histogram valley for 2-column
layouts). Repetition-based header/footer removal: identical normalized text at same y-band
on ≥ 60% of pages → dropped. Output: ordered `RawBlock{page, bbox, text, font_size_median}`
list. Pure function, heavily unit-tested; no LLM here.

### 13.3 LLM segmentation (`engines/pdf/segment.py`)

Batched calls (default 8 pages of blocks per call, 1-block overlap context). Input: numbered
block list (id, page, bbox, font size, text ≤ 600 chars each). Output (schema
`llm/schemas/pdf_segment.v1.json`): per block id, a role from
`{title, author_line, abstract, heading{level}, paragraph, display_equation{number_text?},
figure_caption{number_text?}, table_caption{number_text?}, table_body, bib_entry,
noise}` + a section tree (heading block ids in order with levels). Reading order is NOT an
LLM output: the deterministic order from §13.2 is canonical (the LLM only classifies).
Merging rule: contiguous `paragraph` blocks in reading order with same role merge into IR
Paragraphs (hyphenation repaired: trailing `-` + lowercase joins). Every response
schema-validated + block-id-coverage checked (every input id classified exactly once;
missing/unknown ids → one retry with error feedback → hard fail).

### 13.4 Equations (`engines/pdf/equations.py`)

For `display_equation` blocks: crop bbox + 6 pt padding from the 2× bitmap → PNG asset;
`Equation{content_kind=image, number}` (number from `number_text`, else sequential
`E<n>` display without parentheses). VLM call per equation image (schema
`pdf_equation_latex.v1.json` → `{latex, confidence}`): store as `latex` with
`latex_verified=false`, `confidence`. Skip VLM (config `llm.cache`-independent flag not
needed; controlled by budget §14.6 — when remaining budget insufficient, stop VLM calls,
keep images, warn `vlm-budget-exhausted`).

### 13.5 Citations and bibliography (`engines/pdf/citations.py`)

- Bib entries: `bib_entry` blocks → LLM splits/normalizes into entries (schema
  `pdf_bib.v1.json`: `{entries: [{number?, text, urls: []}]}`; urls must satisfy renderer
  scheme rules).
- In-text markers, deterministic first: regex for `[12]`, `[3,5]`, `[7-9]` (also en-dash) →
  `Cite` to numeric entries. Author-year style `(Kumar et al., 2019; Li & Ma, 2020)`
  detected by regex, mapped to entries by one LLM call (schema `pdf_cite_map.v1.json`).
  Unmapped markers stay plain text + warning (never guessed links).
- Structural refs (`Eq. (3)`, `Fig. 2`, `Section 4.1`, `Table 2`) matched by regex over
  paragraph text → `RefLink` to nodes whose `number` matches; no matching number → the
  text is left untouched (no link, no warning — prose mentions of other papers' figures
  are common and warnings would be noise).

### 13.6 Assembly (`engines/pdf/assemble.py`)

Build IR in reading order with `confidence` and per-node `provenance.page`; abstract/title
from roles (fallback: PDF metadata title); validate; record LLM usage into provenance.
Figures: `figure_caption` blocks pair with the largest non-text raster region above/beside
them (deterministic geometric pairing); the region is cropped as the figure image. Tables:
`content_kind=image` in v1 (crop spanning `table_body` blocks + caption as `Table.caption`).

## 14. LLM client (`llm/`)

### 14.1 Request shape

`POST {base_url}/chat/completions`, JSON: `{model, messages, response_format:
{type:"json_schema", json_schema:{name, schema, strict:true}}, temperature: 0,
max_tokens: <per-call cap>}`. Auth: `Authorization: Bearer <key>` where key =
`os.environ[settings.llm.api_key_env]`; absent key → `ConfigError` **before** any pipeline
work (fail fast), except fully-local base_url without key requirement (allow empty when
host is localhost — documented). VLM calls embed images as
`{"type":"image_url","image_url":{"url":"data:image/png;base64,…"}}` content parts.

### 14.2 Compatibility fallback

On HTTP 400 mentioning `response_format`/`json_schema`: retry the call once with
`response_format:{type:"json_object"}` and the schema embedded in the system prompt; mark
`compat_mode=true` for the session (skip strict attempts thereafter).

### 14.3 Validation and retries

Every response: extract `choices[0].message.content` → `json.loads` → validate against the
schema (local validation always, `jsonschema`-free: pydantic models generated per schema —
implementation detail: schemas authored as pydantic models, JSON Schema exported for the
wire). Invalid → up to `max_retries` re-asks appending a short error description. Transport
errors/429/5xx → exponential backoff (1s/4s/9s + jitter), honoring `Retry-After`. Then
`LlmError`.

### 14.4 Redaction and logging

Request logging at `-v` prints: model, purpose, token estimate, cache hit/miss — never
message content at default verbosity; `-vv` prints prompts with the redaction filter (§19.2)
applied. API key never appears in any log/error/report (assert via tests).

### 14.5 Disk cache (`llm/cache.py`)

Key: `sha256(canonical_json({model, messages, schema_name, schema_version}))`. Value file:
`{schema_name, schema_version, created_at, response_content, usage}` (never request
messages or headers — prompts contain paper text and stay out of the value file; the key
alone links request to response). Hit → zero-cost replay
(usage counted as cached, cost $0 in report). `--no-llm-cache` bypasses reads (still
writes). Cache never stores auth headers.

### 14.6 Cost accounting and guard (`llm/cost.py`)

- Estimator (pre-flight, printed before confirmation): text tokens ≈ chars /
  `llm.estimate.chars_per_token`; images ≈ `image_tokens_flat` each; output tokens assumed =
  min(input, 4096) per call class. Estimate formula documented as ±50% rough.
- Runtime ledger: sums actual `usage.prompt_tokens/completion_tokens` × configured pricing;
  unknown model in pricing table → cost shown as `unknown (no pricing configured)` and
  budget enforcement switches to token count (warn at 2M tokens).
- Guard: before first paid call, show estimate + ask unless `--yes`. Two distinct outcomes:
  the user **declining** the confirmation is an engine-availability outcome
  (`ConversionError("cost-declined")` → selection reason `cost-declined`, exit 5 when the
  plan exhausts); the ledger **exceeding** `--max-cost`/config mid-run raises
  `CostLimitError` (exit 7). VLM degradation per §13.4.

## 15. Renderer (`render/`)

### 15.1 Template contract

`document.html.j2` (+ `_block.j2`, `_inline.j2`, `_head.j2` partials). Autoescape ON;
`|safe` forbidden except the two audited sinks: inlined asset text (viewer.js/css, KaTeX)
and pre-serialized `data:` URIs (both produced by `render/assets.py`, never from IR text).
The renderer is a pure function `render(ir: Document, settings) -> str`.

### 15.2 Block/inline rendering rules

- Sections → `<section id><h2..h6>` with number span; Paragraph → `<p id>`.
- Equation(latex) → `<div class="pd-eq" id data-latex="…" data-number="(3)">` (KaTeX fills
  at load); Equation(image) → same wrapper containing `<img src="data:…" alt="equation
  (unverified LaTeX attached)">` + copy button when `latex` present, labeled
  `Copy LaTeX (unverified)`.
- Inline Math → `<span class="pd-math" data-latex="…">`.
- RefLink → `<a class="pd-ref" href="#eq-12" data-kind="eq">(3)</a>`; inert form (empty
  target) → `<span class="pd-ref-dead" title="unresolved reference">`.
- Cite → `<a class="pd-ref" data-kind="bib" href="#bib-7">[7]</a>` (grouped brackets for
  multi-cite).
- Figure/Table per §10.2; tables get `<th scope>` from header cells.
- Bibliography → `<ol class="pd-bib">` with `<li id="bib-n">`; entry URLs → `ExtLink`
  rendering `<a rel="noopener noreferrer" target="_blank">` (the ONLY external-navigation
  elements; scheme-validated https/http/mailto).
- Footnotes → end-of-document list with backlinks.
- Metadata header: title, authors, arXiv/DOI links, collapsible abstract; provenance footer:
  engine, versions, warning count (details in a collapsible list), LLM cost when applicable.

### 15.3 Preview data

No duplicate content is emitted for previews: the viewer clones the live target element by
id into the popup (single source of truth). Renderer must therefore keep each target
self-sufficient (equation wrapper includes its number span; bib `<li>` readable standalone).

### 15.4 Asset inlining (`render/assets.py`)

Inline order: `<style>` = viewer.css + katex.css (fonts rewritten to data-URI woff2, only
woff2 kept); `<script>` = katex.js + viewer.js, each as separate `<script>` elements with
recorded sha256; images/fonts → `data:` URIs. Everything read from package data
(`importlib.resources`), KaTeX checksums re-verified against `MANIFEST.json` at render time
(tamper detection → hard error).

### 15.5 Size budgets

Sum of embedded assets tracked during render: > `embed_warn_mb` → stderr warning; >
`embed_hard_max_mb` → drop assets with warnings until under cap, in order: figure images
largest-first, then table images; equation images are **never** dropped (they are the
pdf-engine ground truth), and viewer/KaTeX assets are never dropped. Still over the cap
after all droppable assets → `ConversionError("output-too-large")`. Report lists dropped
assets.

### 15.6 CSP + self-containment validator (`render/validate.py`)

CSP meta (exact, single line): `default-src 'none'; img-src data:; style-src
'unsafe-inline'; script-src 'sha256-<h1>' 'sha256-<h2>' …; font-src data:; connect-src
'none'; form-action 'none'; base-uri 'none'; frame-ancestors 'none'`.
Validator parses the final HTML and fails on: any `src/href/srcset/poster/data` attribute
with `http(s):` scheme except `a[href]` with `rel~=noopener`; any `url(` in style text not
`data:`; any `<link rel=stylesheet>`, `<iframe>`, `<object>`, `<embed>`, `<form>`; missing
or non-matching CSP script hashes; inline event handlers (`on*` attributes). Runs on every
conversion; also exposed as `python -m paperdeck.render.validate <file>` for CI/tests.

## 16. Viewer runtime (`render/assets/viewer.js`, `viewer.css`)

Structure: tiny core (`pd.qs`, `pd.on`, `pd.store` try/catch localStorage wrapper,
`pd.docId` = content-hash injected by renderer) + independent IIFE features. Budget ≤ ~600
lines total. No dependencies besides KaTeX.

| Feature | Spec |
|---|---|
| `math` | On DOMContentLoaded: render `.pd-math/.pd-eq[data-latex]` in viewport immediately; rest via IntersectionObserver (rootMargin 200%). KaTeX options: `throwOnError:false`, `macros` from injected JSON, `displayMode` per class. Failed render → `.pd-math-error` showing raw latex in `<code>` |
| `popup` | mouseenter on `.pd-ref` (delay 150 ms) → popup near cursor with **clone** of target element (math already rendered; re-render clone if pending); mouseleave 300 ms grace; focus/blur equivalents for keyboard; Escape closes; popup max 45vh, scrollable; nested refs inside popup are inert |
| `jump/back` | click `.pd-ref` → record `{scrollY}` on back-stack (max 50) → smooth-scroll to target + flash highlight; floating Back chip (visible when stack non-empty, shows depth); `Backspace`/chip click pops. Browser history untouched; `location.hash` targets honored on load |
| `toc` | Sidebar from `<section>` tree (renderer emits `<nav id="pd-toc">` server-side; JS only wires behavior); scroll-spy via IntersectionObserver highlights current; collapsible ≥ level 3; `t` toggles sidebar; hidden by default < 900 px viewport (slide-over) |
| `theme` | `data-theme` on `<html>` carries the **resolved** value `light\|dark` (CSS keys off it); `data-theme-mode` carries the raw mode `auto\|light\|dark`; auto = `prefers-color-scheme` (live listener); toggle button cycles modes; persisted via `pd.store` docId-independent key `pd-theme` |
| `position` | Save `{anchor: id of topmost visible block, offset: elementTop − scrollY (elementTop = getBoundingClientRect().top + scrollY at save time), at: epoch ms}` (debounced 500 ms) under key `pd-pos:<docId>`; on load (no location.hash): restore via `scrollTo(0, currentElementTop − offset)` + toast `Resumed — press T to go to top` (auto-hide 4 s) |
| `keys` | `j/k` next/prev section top; `t` ToC; `d` theme; `Backspace` back; `?` help overlay (lists shortcuts, Esc closes). Never intercept with modifiers or inside inputs |
| a11y | popups: `role="tooltip"`, refs get `aria-describedby` while open; Back chip and toggles are real `<button>`; focus outline preserved; ToC is `<nav><ol>`; prefers-reduced-motion disables smooth scroll |

CSS: custom properties for both themes on `:root[data-theme=…]`; print stylesheet (hide
chrome, expand content); content column max-width 46rem, KaTeX display scroll-x when
overflowing.

## 17. Storage layout summary

| Path (platformdirs) | Contents | Perms |
|---|---|---|
| config dir `/paperdeck/config.toml` | user config (never written by paperdeck) | user-created |
| cache dir `/paperdeck/arxiv/**` | fetched artifacts (§8.5) | 0755/0644 |
| cache dir `/paperdeck/llm/**` | LLM response cache (§14.5) | 0700 dir |
| tempfile 0700 dirs | extraction, page bitmaps | auto-cleaned (context managers) |

## 18. Error taxonomy and exit codes (`errors.py`)

`PaperdeckError(code, user_message, hint?)` hierarchy:

| Exception | Exit | Typical cause |
|---|---|---|
| `UsageError` (click) | 2 | bad flags/combination |
| `InputError` | 3 | unrecognized input, broken/encrypted PDF, missing file |
| `FetchError` | 4 | network failure, HTTP error, size cap exceeded |
| `AllEnginesFailedError` | 5 | plan exhausted (§9) — message tabulates reasons |
| `LlmError` | 6 | transport/validation failure after retries |
| `CostLimitError` | 7 | budget guard (§14.6) |
| `ConfigError` | 8 | invalid config, missing API key |
| `SecurityError` | 9 | tar traversal, allowlist violation, checksum mismatch, validator failure |
| `OutputExistsError` | 10 | output exists without `--force` |
| unexpected | 1 | bug — prints issue-reporting hint |

Every error prints: one-line cause + one-line actionable hint. Stack traces only at `-vv`.

## 19. Logging, progress, run report

1. `logsetup.py`: stderr handler, levels WARNING (default) / INFO (`-v`) / DEBUG (`-vv`).
2. Redaction filter on the root handler: masks values of env var named by `api_key_env`,
   any `sk-[A-Za-z0-9_-]{8,}`-shaped token, and `Authorization` header values.
3. Run report `<output>.report.json` (normative field set): `{input, engine, fallbacks,
   timings_ms: {stage: ms}, warnings: [{code, message}], llm: {calls, cache_hits,
   tokens_in, tokens_out, estimated_usd, actual_usd}, output: {path, bytes, asset_count,
   dropped_assets}, versions: {paperdeck, pandoc?, katex}}`. On failure the report is
   written best-effort with `error: {code, exit}` added. Schema documented in
   `report.py`; consumed by tests.

## 20. Security model

### 20.1 Trust boundaries

```
[untrusted internet: arXiv artifacts] ──▶ netgate ──▶ cache ──▶ parsers (tarsafe→pandoc/pdfium/bs4)
[untrusted paper content] ──▶ LLM prompts ──▶ [untrusted LLM output] ──▶ schema validation ──▶ IR
[IR = semi-trusted data] ──▶ renderer (escaping) ──▶ HTML + CSP ──▶ validator ──▶ user's browser
[secrets: API key env] ──▶ llm client only (redacted everywhere else)
```

### 20.2 Threats and controls

| # | Threat | Control (design ref) |
|---|---|---|
| T1 | Malicious tarball (traversal/symlink/bomb) | tarsafe rules §8.6; tests with attack fixtures |
| T2 | TeX code execution | no TeX engine ever invoked (ADR-007 §1); pandoc parses only, hardened subprocess §12.2 |
| T3 | Malicious PDF exploiting parser | pypdfium2 (fuzzed engine) + input/page caps §13.1; residual risk documented in SECURITY.md; Dependabot updates |
| T4 | Prompt injection via paper text steering LLM output | strict schemas + local validation §14.3; output treated as data; renderer escapes; URLs from LLM restricted to https/http + only in bib `urls` §13.5; self-containment validator backstop §15.6 |
| T5 | XSS into generated HTML (any engine) | autoescape §15.1; no inline SVG §10.5; no inline event handlers; CSP script hashes §15.6 |
| T6 | Exfiltration/tracking from output file | CSP `connect-src 'none'` + validator: zero fetchable external refs §15.6 |
| T7 | SSRF / unexpected hosts | netgate single gate + allowlists §8.4; LLM base_url host pinned; no redirects off-list |
| T8 | Secret leakage (logs/cache/output/report) | key from env only; redaction filter §19.2; cache stores no auth §14.5; tests assert absence |
| T9 | Supply chain (frontend) | vendored pinned KaTeX + SHA-256 manifest, CI re-verify §15.4, ADR-008 |
| T10 | Supply chain (Python) | permissive-only policy + `pip-licenses` CI gate (ADR-005); lockfile (`uv.lock`) committed; Dependabot |
| T11 | Cost abuse (huge paper → runaway spend) | pre-flight estimate + confirmation + hard budget §14.6; page/size caps §13.1 |
| T12 | Cache poisoning (local) | cache is user-local; artifacts re-validated by magic bytes at use; LLM cache keyed by full request hash |

### 20.3 Security acceptance criteria convention

Issues carry `SEC-AC:` prefixed acceptance criteria (grep-able). CI must include the
security test suite (attack fixtures for T1/T4/T5/T6) — a release is blocked if any SEC-AC
test is missing or failing (see CI issue).

### 20.4 Disclosure

`SECURITY.md`: private reporting via GitHub Security Advisories; supported-version =
latest minor; response-time statement; residual-risk statement (T3).

## 21. Testing and QA strategy

| Layer | What | Tooling |
|---|---|---|
| Unit | resolver grammar, tarsafe attacks, counters replay, refs resolution, bib parsers, blocks clustering, cost math, CSP builder, redaction | pytest (no network, no pandoc needed except marked) |
| Contract | IR pydantic ⟷ committed JSON Schema drift check; LLM schemas versioned | pytest + generation script |
| Engine golden | fixture corpora → IR JSON snapshots (`tests/fixtures/{latex,arxiv_html,pdf}/…`); pandoc-marked tests skip when absent locally, mandatory in CI | pytest golden files |
| LLM | `FakeLLM` httpx MockTransport returning canned schema-valid (and deliberately invalid) responses; no real API in CI ever | pytest |
| Render/e2e | fixture IR → HTML → self-containment validator → Playwright (chromium + webkit): popup shows correct target, back returns, ToC highlights, theme persists, position restores, keys work | Playwright (separate CI job) |
| Security | T1 tar fixtures, T4 injection strings (`<script>`, `](javascript:…)`, prompt-injection phrases) must appear escaped/ignored in output, T6 validator red/green fixtures, T8 log scan | pytest |
| Quality sweep (manual, pre-release) | 10-paper arXiv sample sheet (mixed years/fields) with checklist: title/sections/eq numbers/refs/bib correct | documented procedure in CONTRIBUTING |

Coverage floor: 85% lines on `src/paperdeck` (CI-enforced), excluding templates/assets.

## 22. Packaging and distribution

- `pyproject.toml` (hatchling), `requires-python = ">=3.11"`, console script `paperdeck`;
  package data includes templates/assets/schemas/prompts; version single-sourced in
  `paperdeck.__init__.__version__`.
- Install story: `uv tool install paperdeck` / `pipx install paperdeck`; `pandoc` via OS
  package manager (doctor prints per-OS hint).
- Release: tag `vX.Y.Z` → CI builds sdist+wheel → **Trusted Publishing (OIDC) to PyPI**
  (no long-lived tokens, ADR-007-consistent); GitHub Release with changelog; `main` is
  protected, PRs only (repo rules already active).

## 23. Performance and size budgets

| Metric | Budget |
|---|---|
| arXiv-html engine, typical paper | ≤ 30 s wall (network-bound; rate limiter dominates when many figures) |
| latex engine, typical paper | ≤ 20 s wall |
| pdf engine, 30-page paper | ≤ 3 min wall, ≤ $0.50 at default models (estimate; verify in beta) |
| Output size, no figures | ≤ 2.5 MB (KaTeX + viewer + text) |
| Output size, typical figures | ≤ 15 MB; warn 25 MB; hard cap 50 MB (§15.5) |
| Viewer first paint on 50-eq paper | ≤ 1.5 s on M1-class laptop (lazy math §16) |

## 24. Known unknowns (may spawn issues during implementation)

1. Real-world pandoc failure rate on old arXiv sources — may need preamble-sanitizing
   pre-pass (strip unknown packages) as a new issue.
2. LaTeXML HTML variance across arXiv conversion versions — mapping table may need
   extension; quality-gate thresholds may need tuning against a sample set.
3. VLM equation-LaTeX quality at default models — copy-text UX may need a confidence
   threshold below which LaTeX is withheld.
4. `file://` localStorage behavior differences (Safari) — position/theme persistence may
   silently degrade; acceptable, but verify and document actual matrix.
5. KaTeX coverage gaps on macro-heavy papers — may motivate MathJax fallback (v2 trigger).
6. Chat Completions `json_schema` support variance across local servers (Ollama/vLLM
   versions) — compat fallback §14.2 may need per-server quirks.
7. Column detection on exotic layouts (3-column, landscape) — clustering heuristics §13.2
   may need iteration; failure mode is degraded reading order, caught by golden fixtures.
8. Exact token/image pricing drift — pricing config defaults will need refresh at release
   time.

## 25. Traceability

Requirement → design: R1→§5,6; R2→§8,9; R3→§11,12; R4→§13,14; R5→§13.4,15.2; R6→§15.3,16;
R7→§14; R8→§5.1,16; R9→§15.4–15.6; R10→§16; R11→ADR-005,§22; R12→§8.3–8.4.
Design → issues: see coverage table in `docs/ISSUE_PLAN.md`.
