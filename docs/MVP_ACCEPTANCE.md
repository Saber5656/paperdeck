# MVP acceptance and delivery evidence

The MVP converts arXiv papers, local LaTeX, and local PDFs to self-contained HTML.
This index connects every original implementation issue to executable acceptance
coverage. The implementation and local tests are complete; the current-head CI and
release dry run are checked separately in the pull request before merge.

## Individual issue evidence

Issue draft numbers 23–55 map to GitHub 24–56 because #23 was a design pull request.
Test files contain additional boundary cases beyond this compact index. Detailed
per-criterion results and raw execution logs are retained in the local Agents Vault.

| GitHub issue | Scope | Executable evidence |
| --- | --- | --- |
| [#1](https://github.com/Saber5656/paperdeck/issues/1) | [project scaffolding](issues/01-project-scaffolding.md) | [smoke](../tests/test_smoke.py), [wheel_contents](../tests/unit/test_wheel_contents.py) |
| [#2](https://github.com/Saber5656/paperdeck/issues/2) | [error taxonomy](issues/02-error-taxonomy.md) | [errors](../tests/unit/test_errors.py), [CLI redaction](../tests/e2e/test_error_acceptance.py) |
| [#3](https://github.com/Saber5656/paperdeck/issues/3) | [logging redaction](issues/03-logging-redaction.md) | [logsetup](../tests/unit/test_logsetup.py) |
| [#4](https://github.com/Saber5656/paperdeck/issues/4) | [config loading](issues/04-config-loading.md) | [config](../tests/unit/test_config.py) |
| [#5](https://github.com/Saber5656/paperdeck/issues/5) | [ir model](issues/05-ir-model.md) | [ir_model](../tests/unit/test_ir_model.py), [ir_edge_cases](../tests/unit/test_ir_edge_cases.py) |
| [#6](https://github.com/Saber5656/paperdeck/issues/6) | [ir anchors validation schema](issues/06-ir-anchors-validation-schema.md) | [ir_validate](../tests/unit/test_ir_validate.py), [ir_schema_drift](../tests/unit/test_ir_schema_drift.py) |
| [#7](https://github.com/Saber5656/paperdeck/issues/7) | [input resolver](issues/07-input-resolver.md) | [resolver](../tests/unit/test_resolver.py), [input_security_acceptance](../tests/unit/test_input_security_acceptance.py) |
| [#8](https://github.com/Saber5656/paperdeck/issues/8) | [netgate](issues/08-netgate.md) | [netgate](../tests/unit/test_netgate.py), [input_security_acceptance](../tests/unit/test_input_security_acceptance.py) |
| [#9](https://github.com/Saber5656/paperdeck/issues/9) | [cache manager](issues/09-cache-manager.md) | [cache](../tests/unit/test_cache.py), [ir_cache_acceptance](../tests/unit/test_ir_cache_acceptance.py) |
| [#10](https://github.com/Saber5656/paperdeck/issues/10) | [tarsafe extraction](issues/10-tarsafe-extraction.md) | [tarsafe](../tests/unit/test_tarsafe.py) |
| [#11](https://github.com/Saber5656/paperdeck/issues/11) | [arxiv metadata client](issues/11-arxiv-metadata-client.md) | [arxiv_metadata](../tests/unit/test_arxiv_metadata.py) |
| [#12](https://github.com/Saber5656/paperdeck/issues/12) | [arxiv artifact downloads](issues/12-arxiv-artifact-downloads.md) | [arxiv_metadata](../tests/unit/test_arxiv_metadata.py) |
| [#13](https://github.com/Saber5656/paperdeck/issues/13) | [latex project handling](issues/13-latex-project-handling.md) | [latex_project](../tests/unit/test_latex_project.py) |
| [#14](https://github.com/Saber5656/paperdeck/issues/14) | [pandoc runner](issues/14-pandoc-runner.md) | [latex_pandoc_runner](../tests/unit/test_latex_pandoc_runner.py) |
| [#15](https://github.com/Saber5656/paperdeck/issues/15) | [pandoc ast mapping](issues/15-pandoc-ast-mapping.md) | [ast_map](../tests/unit/test_ast_map.py) |
| [#16](https://github.com/Saber5656/paperdeck/issues/16) | [rawtex micro parser](issues/16-rawtex-micro-parser.md) | [rawtex_parser](../tests/unit/test_rawtex_parser.py) |
| [#17](https://github.com/Saber5656/paperdeck/issues/17) | [numbering replay](issues/17-numbering-replay.md) | [counters](../tests/unit/test_counters.py) |
| [#18](https://github.com/Saber5656/paperdeck/issues/18) | [latex reference resolution](issues/18-latex-reference-resolution.md) | [latex_refs_resolution](../tests/unit/test_latex_refs_resolution.py) |
| [#19](https://github.com/Saber5656/paperdeck/issues/19) | [preamble macro extraction](issues/19-preamble-macro-extraction.md) | [latex_macros](../tests/unit/test_latex_macros.py) |
| [#20](https://github.com/Saber5656/paperdeck/issues/20) | [latex bibliography](issues/20-latex-bibliography.md) | [latex_bib](../tests/unit/test_latex_bib.py) |
| [#21](https://github.com/Saber5656/paperdeck/issues/21) | [latex graphics](issues/21-latex-graphics.md) | [latex_graphics](../tests/unit/test_latex_graphics.py), [latex_graphics_resolution](../tests/unit/test_latex_graphics_resolution.py) |
| [#22](https://github.com/Saber5656/paperdeck/issues/22) | [latex engine assembly](issues/22-latex-engine-assembly.md) | [latex_engine](../tests/unit/test_latex_engine.py), [pipeline_latex](../tests/e2e/test_pipeline_latex.py) |
| [#24](https://github.com/Saber5656/paperdeck/issues/24) | [arxiv html fetch quality gate](issues/23-arxiv-html-fetch-quality-gate.md) | [html_quality](../tests/unit/test_html_quality.py), [arxiv_html_engine](../tests/engine/test_arxiv_html_engine.py) |
| [#25](https://github.com/Saber5656/paperdeck/issues/25) | [arxiv html structure parsing](issues/24-arxiv-html-structure-parsing.md) | [html_structure](../tests/unit/test_html_structure.py), [arxiv_html_golden](../tests/engine/test_arxiv_html_golden.py) |
| [#26](https://github.com/Saber5656/paperdeck/issues/26) | [arxiv html content parsing](issues/25-arxiv-html-content-parsing.md) | [html_content](../tests/unit/test_html_content.py), [arxiv_html_golden](../tests/engine/test_arxiv_html_golden.py) |
| [#27](https://github.com/Saber5656/paperdeck/issues/27) | [engine selection](issues/26-engine-selection.md) | [select](../tests/unit/test_select.py), [pipeline_pdf](../tests/e2e/test_pipeline_pdf.py) |
| [#28](https://github.com/Saber5656/paperdeck/issues/28) | [llm client](issues/27-llm-client.md) | [llm_remaining_acceptance](../tests/unit/test_llm_remaining_acceptance.py), [llm_terminal_errors](../tests/unit/test_llm_terminal_errors.py) |
| [#29](https://github.com/Saber5656/paperdeck/issues/29) | [llm disk cache](issues/28-llm-disk-cache.md) | [llm_cache_local](../tests/unit/test_llm_cache_local.py), [llm_provider_cache](../tests/unit/test_llm_provider_cache.py) |
| [#30](https://github.com/Saber5656/paperdeck/issues/30) | [llm cost guard](issues/29-llm-cost-guard.md) | [llm_contract_acceptance](../tests/unit/test_llm_contract_acceptance.py), [llm_remaining_acceptance](../tests/unit/test_llm_remaining_acceptance.py), [llm_token_budget](../tests/unit/test_llm_token_budget.py) |
| [#31](https://github.com/Saber5656/paperdeck/issues/31) | [llm schemas prompts](issues/30-llm-schemas-prompts.md) | [llm_schema_acceptance](../tests/unit/test_llm_schema_acceptance.py), [llm_remaining_acceptance](../tests/unit/test_llm_remaining_acceptance.py) |
| [#32](https://github.com/Saber5656/paperdeck/issues/32) | [pdf extraction](issues/31-pdf-extraction.md) | [pdf_geometry_acceptance](../tests/unit/test_pdf_geometry_acceptance.py), [pdf_llm_remaining_acceptance](../tests/unit/test_pdf_llm_remaining_acceptance.py) |
| [#33](https://github.com/Saber5656/paperdeck/issues/33) | [pdf block clustering](issues/32-pdf-block-clustering.md) | [pdf_blocks_local](../tests/unit/test_pdf_blocks_local.py), [pdf_llm_remaining_acceptance](../tests/unit/test_pdf_llm_remaining_acceptance.py) |
| [#34](https://github.com/Saber5656/paperdeck/issues/34) | [pdf llm segmentation](issues/33-pdf-llm-segmentation.md) | [pdf_llm_remaining_acceptance](../tests/unit/test_pdf_llm_remaining_acceptance.py) |
| [#35](https://github.com/Saber5656/paperdeck/issues/35) | [pdf equations vlm](issues/34-pdf-equations-vlm.md) | [pdf_equations_local](../tests/unit/test_pdf_equations_local.py), [pdf_llm_remaining_acceptance](../tests/unit/test_pdf_llm_remaining_acceptance.py) |
| [#36](https://github.com/Saber5656/paperdeck/issues/36) | [pdf citations bibliography](issues/35-pdf-citations-bibliography.md) | [pdf_citations_local](../tests/unit/test_pdf_citations_local.py), [pdf_llm_remaining_acceptance](../tests/unit/test_pdf_llm_remaining_acceptance.py) |
| [#37](https://github.com/Saber5656/paperdeck/issues/37) | [pdf engine assembly](issues/36-pdf-engine-assembly.md) | [pdf_geometry_acceptance](../tests/unit/test_pdf_geometry_acceptance.py), [pdf_llm_remaining_acceptance](../tests/unit/test_pdf_llm_remaining_acceptance.py), [pipeline_pdf](../tests/e2e/test_pipeline_pdf.py) |
| [#38](https://github.com/Saber5656/paperdeck/issues/38) | [katex vendoring](issues/37-katex-vendoring.md) | [vendor_manifest](../tests/unit/test_vendor_manifest.py) |
| [#39](https://github.com/Saber5656/paperdeck/issues/39) | [renderer core](issues/38-renderer-core.md) | [renderer_acceptance](../tests/unit/test_renderer_acceptance.py), [unknown_cost_render](../tests/unit/test_unknown_cost_render.py) |
| [#40](https://github.com/Saber5656/paperdeck/issues/40) | [asset inlining budgets](issues/39-asset-inlining-budgets.md) | [render_assets](../tests/unit/test_render_assets.py), [renderer_acceptance](../tests/unit/test_renderer_acceptance.py) |
| [#41](https://github.com/Saber5656/paperdeck/issues/41) | [self containment validator](issues/40-self-containment-validator.md) | [selfcontain_validator](../tests/unit/test_selfcontain_validator.py), [render_boundary](../tests/security/test_render_boundary.py) |
| [#42](https://github.com/Saber5656/paperdeck/issues/42) | [viewer core math](issues/41-viewer-core-math.md) | [reader_acceptance](../tests/e2e/test_reader_acceptance.py), [pipeline_pdf_viewer](../tests/e2e/test_pipeline_pdf_viewer.py) |
| [#43](https://github.com/Saber5656/paperdeck/issues/43) | [viewer popup back](issues/42-viewer-popup-back.md) | [reader_acceptance](../tests/e2e/test_reader_acceptance.py), [pipeline_viewer](../tests/e2e/test_pipeline_viewer.py) |
| [#44](https://github.com/Saber5656/paperdeck/issues/44) | [viewer toc](issues/43-viewer-toc.md) | [reader_acceptance](../tests/e2e/test_reader_acceptance.py) |
| [#45](https://github.com/Saber5656/paperdeck/issues/45) | [viewer theme](issues/44-viewer-theme.md) | [reader_acceptance](../tests/e2e/test_reader_acceptance.py), [viewer](../tests/e2e/test_viewer.py) |
| [#46](https://github.com/Saber5656/paperdeck/issues/46) | [viewer reading position](issues/45-viewer-reading-position.md) | [reader_acceptance](../tests/e2e/test_reader_acceptance.py), [reader_identity](../tests/unit/test_reader_identity.py) |
| [#47](https://github.com/Saber5656/paperdeck/issues/47) | [viewer keyboard](issues/46-viewer-keyboard.md) | [reader_acceptance](../tests/e2e/test_reader_acceptance.py), [viewer](../tests/e2e/test_viewer.py) |
| [#48](https://github.com/Saber5656/paperdeck/issues/48) | [viewer css](issues/47-viewer-css.md) | [reader_acceptance](../tests/e2e/test_reader_acceptance.py), [renderer_acceptance](../tests/unit/test_renderer_acceptance.py) |
| [#49](https://github.com/Saber5656/paperdeck/issues/49) | [convert command](issues/48-convert-command.md) | [cli_acceptance_remaining](../tests/e2e/test_cli_acceptance_remaining.py), [cli_boundaries](../tests/e2e/test_cli_boundaries.py) |
| [#50](https://github.com/Saber5656/paperdeck/issues/50) | [fetch cache commands](issues/49-fetch-cache-commands.md) | [cli_acceptance_remaining](../tests/e2e/test_cli_acceptance_remaining.py), [fetch_cache_commands](../tests/e2e/test_fetch_cache_commands.py) |
| [#51](https://github.com/Saber5656/paperdeck/issues/51) | [doctor command](issues/50-doctor-command.md) | [cli_acceptance_remaining](../tests/e2e/test_cli_acceptance_remaining.py), [doctor](../tests/e2e/test_doctor.py) |
| [#52](https://github.com/Saber5656/paperdeck/issues/52) | [e2e latex viewer](issues/51-e2e-latex-viewer.md) | [pipeline_latex](../tests/e2e/test_pipeline_latex.py), [pipeline_viewer](../tests/e2e/test_pipeline_viewer.py) |
| [#53](https://github.com/Saber5656/paperdeck/issues/53) | [e2e pdf security suite](issues/52-e2e-pdf-security-suite.md) | [pipeline_pdf](../tests/e2e/test_pipeline_pdf.py), [sec_ac_imports](../tests/security/test_sec_ac_imports.py) |
| [#54](https://github.com/Saber5656/paperdeck/issues/54) | [oss meta docs](issues/53-oss-meta-docs.md) | [docs_links](../tests/unit/test_docs_links.py) |
| [#55](https://github.com/Saber5656/paperdeck/issues/55) | [ci pipeline](issues/54-ci-pipeline.md) | [workflow_hygiene](../tests/unit/test_workflow_hygiene.py), [check_licenses](../tests/unit/test_check_licenses.py) |
| [#56](https://github.com/Saber5656/paperdeck/issues/56) | [packaging release](issues/55-packaging-release.md) | [wheel_contents](../tests/unit/test_wheel_contents.py), [workflow_hygiene](../tests/unit/test_workflow_hygiene.py) |

## Acceptance clarifications inherited from the reviewed design

- The CSP hashes four script bodies: theme bootstrap, JSON data island, KaTeX, and
  viewer. The older three-script count excludes the JSON island; the accepted design
  review requires it to be hashed too. The validator and browser tests enforce this.
- Templates use automatic escaping with no `|safe` filter. Package-owned CSS/scripts
  and escaped JSON are the audited `Markup` inputs; source or model text cannot enter
  those trusted inputs. Metadata and bibliography URLs use the same validated URL
  policy as explicit external links and carry `noopener noreferrer` and `_blank`.
- Portable LaTeX HTML snapshots normalize the installed Pandoc version and the
  path-derived document id with its matching CSP hash. Everything else is compared
  byte-for-byte, and corruption detection is tested. The production id is unchanged.
- Unknown model prices remain unavailable in reports and the reader; they are never
  presented as a measured zero charge. A conservative estimate and token ceiling still
  guard requests. See [cost accounting](COST_ACCOUNTING.md).
- Runtime license exceptions are package/version-specific and documented with their
  actual notices in [dependency licenses](DEPENDENCY_LICENSES.md). Development-only
  dependencies are reported separately by the license gate.

## Direct verification outside unit fixtures

- Eight LaTeX corpus projects run through the actual CLI and standalone validator.
  Pandoc 3.1.3 and 3.11 are checked; two committed full HTML snapshots and six semantic
  snapshots cover the results.
- Ten real arXiv HTML papers were downloaded through the production client, converted
  by the actual CLI, and opened offline in Chromium. Every final output made zero
  HTTP resource requests, emitted zero page errors, and had no horizontal page overflow.
  All ten title views were visually inspected. One paper (1609.04802v5) has a partial
  image cache after a stalled download; source HTML also omits some image nodes.
  This sweep does not claim perfect reconstruction of unsupported LaTeXML structures.
- Chromium and WebKit exercise the reader and actual LaTeX CLI output. Actual PDF CLI
  output uses the local FakeLLM and checks equation crops, unverified copy, citations,
  consent, cost limits, and hostile model output without paid API calls.
- A fresh destination reproduced all 24 vendored KaTeX files, including its manifest
  and license, byte-for-byte from the pinned official distributions.
- An isolated wheel build with deliberately excluded reader assets failed the wheel
  content test. The normal wheel and sdist are installed and smoke-tested separately.
- [Visual QA](../design-qa.md) includes the source design comparison and
  [light](qa/kitchen-light.jpg), [dark](qa/kitchen-dark.jpg),
  [320px](qa/kitchen-narrow.jpg), and [print](qa/kitchen-print.jpg) kitchen-sink views.
  The attack-like title is intentional test data and is displayed as literal text.

## Delivery boundaries

The prerelease tag workflow is an actual dry run: build, CI, and installation smoke
must succeed while PyPI publication and GitHub Release creation are skipped. The
negative version tag `v0.0.0-rc.acceptance` was rejected in
[run 34703647177](https://github.com/Saber5656/paperdeck/actions/runs/34703647177).
Stable PyPI publication and real paid-model quality evaluation are separate release
steps documented in [CONTRIBUTING](../CONTRIBUTING.md).

Maintainers should require `security`, `gates`, and the OS `test` checks in repository
settings. Native repository rules are respected at merge; check success is verified
for the current head even where a check is not configured as required.
