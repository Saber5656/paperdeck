# MVP implementation review disposition

All 18 findings in the initial automated Codex review of PR #57 were adopted. The
changes below are verified by focused regressions and the subsequent integrated suite.
CodeRabbit reported a successful status but skipped review because the repository had
fewer than ten stars; its status is not counted as independent review evidence.

The primary agent also reviewed the integrated changes for the product goal,
regressions, escaping/transport/budget boundaries, test validity, and accidental local
paths or secrets. The self-review found and fixed unknown-cost footer formatting,
long-math/raw-text overflow, lazy-layout fragment movement, and print ToC specificity.
Each repair has a failing observation followed by a passing regression. Additional
acceptance work found and fixed PDF column flattening and compressed archive limits.

| Review finding | Adopted resolution | Fix | Regression |
| --- | --- | --- | --- |
| [r3996671100](https://github.com/Saber5656/paperdeck/pull/57#discussion_r3996671100) | Use PDF coordinates for above/beside figure regions and explicit table-body links | [630940d](https://github.com/Saber5656/paperdeck/commit/630940d) | [test_pdf_geometry_acceptance.py](../tests/unit/test_pdf_geometry_acceptance.py) |
| [r3996671103](https://github.com/Saber5656/paperdeck/pull/57#discussion_r3996671103) | Resolve references nested in Strong, Sub, and Sup nodes | [d1d1daa](https://github.com/Saber5656/paperdeck/commit/d1d1daa) | [test_latex_refs_resolution.py](../tests/unit/test_latex_refs_resolution.py) |
| [r3996671106](https://github.com/Saber5656/paperdeck/pull/57#discussion_r3996671106) | Preserve direct sibling paragraphs, figures, and sections from arXiv HTML | [a119020](https://github.com/Saber5656/paperdeck/commit/a119020) | [test_html_structure.py](../tests/unit/test_html_structure.py) |
| [r3996671107](https://github.com/Saber5656/paperdeck/pull/57#discussion_r3996671107) | Create unique temporary files for concurrent cache writes | [8e70acb](https://github.com/Saber5656/paperdeck/commit/8e70acb) | [test_ir_cache_acceptance.py](../tests/unit/test_ir_cache_acceptance.py) |
| [r3996671111](https://github.com/Saber5656/paperdeck/pull/57#discussion_r3996671111) | Replay appendix transitions from source where Pandoc drops the marker | [f52222b](https://github.com/Saber5656/paperdeck/commit/f52222b) | [test_latex_engine.py](../tests/unit/test_latex_engine.py) |
| [r3996671113](https://github.com/Saber5656/paperdeck/pull/57#discussion_r3996671113) | Honor validated PDF segment section order in assembly | [630940d](https://github.com/Saber5656/paperdeck/commit/630940d) | [test_pdf_geometry_acceptance.py](../tests/unit/test_pdf_geometry_acceptance.py) |
| [r3996671115](https://github.com/Saber5656/paperdeck/pull/57#discussion_r3996671115) | Use merged PDF paragraphs and repaired hyphenation in assembly and citations | [630940d](https://github.com/Saber5656/paperdeck/commit/630940d) | [test_pdf_geometry_acceptance.py](../tests/unit/test_pdf_geometry_acceptance.py) |
| [r3996671121](https://github.com/Saber5656/paperdeck/pull/57#discussion_r3996671121) | Translate terminal HTTP status failures into the declared LLM error taxonomy | [b408733](https://github.com/Saber5656/paperdeck/commit/b408733) | [test_llm_terminal_errors.py](../tests/unit/test_llm_terminal_errors.py) |
| [r3996671126](https://github.com/Saber5656/paperdeck/pull/57#discussion_r3996671126) | Enforce unknown-price token reservations and preserve unavailable dollar cost | [d1fd9c0](https://github.com/Saber5656/paperdeck/commit/d1fd9c0) | [test_llm_token_budget.py](../tests/unit/test_llm_token_budget.py) |
| [r3996671128](https://github.com/Saber5656/paperdeck/pull/57#discussion_r3996671128) | Apply the VLM model price to image requests | [45d1080](https://github.com/Saber5656/paperdeck/commit/45d1080) | [test_llm_contract_acceptance.py](../tests/unit/test_llm_contract_acceptance.py) |
| [r3996671133](https://github.com/Saber5656/paperdeck/pull/57#discussion_r3996671133) | Keep literal input commands inside verbatim, listings, and filecontents untouched | [d1d1daa](https://github.com/Saber5656/paperdeck/commit/d1d1daa) | [test_latex_project.py](../tests/unit/test_latex_project.py) |
| [r3996671134](https://github.com/Saber5656/paperdeck/pull/57#discussion_r3996671134) | Read actual PDF metadata title and use a warned filename fallback | [630940d](https://github.com/Saber5656/paperdeck/commit/630940d) | [test_pdf_geometry_acceptance.py](../tests/unit/test_pdf_geometry_acceptance.py) |
| [r3996671137](https://github.com/Saber5656/paperdeck/pull/57#discussion_r3996671137) | Preserve immutable ancestors when assembling nested sections | [d1d1daa](https://github.com/Saber5656/paperdeck/commit/d1d1daa) | [test_ast_map.py](../tests/unit/test_ast_map.py) |
| [r3996671138](https://github.com/Saber5656/paperdeck/pull/57#discussion_r3996671138) | Retain table labels carried by Pandoc container attributes | [d1d1daa](https://github.com/Saber5656/paperdeck/commit/d1d1daa) | [test_ast_map.py](../tests/unit/test_ast_map.py) |
| [r3996671141](https://github.com/Saber5656/paperdeck/pull/57#discussion_r3996671141) | Include normalized provider identity in LLM cache keys | [97bfbaa](https://github.com/Saber5656/paperdeck/commit/97bfbaa) | [test_llm_provider_cache.py](../tests/unit/test_llm_provider_cache.py) |
| [r3996671145](https://github.com/Saber5656/paperdeck/pull/57#discussion_r3996671145) | Exclude volatile provenance and warnings from reader identity | [37a7328](https://github.com/Saber5656/paperdeck/commit/37a7328) | [test_reader_identity.py](../tests/unit/test_reader_identity.py) |
| [r3996671148](https://github.com/Saber5656/paperdeck/pull/57#discussion_r3996671148) | Mark context-only segmentation blocks read-only and omit them from classification | [630940d](https://github.com/Saber5656/paperdeck/commit/630940d) | [test_pdf_geometry_acceptance.py](../tests/unit/test_pdf_geometry_acceptance.py) |
| [r3996671150](https://github.com/Saber5656/paperdeck/pull/57#discussion_r3996671150) | Serialize bibliography inline content for author-year mapping | [630940d](https://github.com/Saber5656/paperdeck/commit/630940d) | [test_pdf_geometry_acceptance.py](../tests/unit/test_pdf_geometry_acceptance.py) |

Later acceptance additions are linked in [MVP acceptance](MVP_ACCEPTANCE.md). Raw
red/green logs, complete available public tool records, and the detailed per-criterion
ledger are retained in the local Agents Vault. No paid API review or model-quality
assessment is claimed. Review threads are resolved only after their focused fixes are
present in the PR; current-head checks and native merge rules remain separate gates.
