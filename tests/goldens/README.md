# LaTeX corpus goldens

`minimal.html` and `equations.html` are byte-comparable HTML snapshots from the
subprocess LaTeX corpus run. The comparison normalizes the Pandoc version in the
footer (`pandoc VERSION`) because the CI matrix intentionally runs Pandoc 3.1 and
3.11. It also normalizes the reader `docId` and recomputes only the matching CSP hash:
local source provenance contains an absolute checkout path, and that path intentionally
changes the document identity. Product code still keeps the real `docId`; only the
portable golden comparison replaces it. Provenance timestamps are kept in the report,
and generated asset bytes remain covered by the self-containment validator.

The JSON files record stable semantic facts for all eight corpus projects, including
the six extended projects.

To regenerate a golden after an intentional IR or renderer change, run the marked
pipeline test with `PAPERDECK_FAKE_NOW` set to a fixed ISO timestamp and the explicit
update flag, inspect the rendered HTML and validator report, then review the diff:

```sh
PAPERDECK_FAKE_NOW=2000-01-01T00:00:00+00:00 uv run pytest tests/e2e/test_pipeline_latex.py::test_latex_corpus_cli_and_standalone_validator --update-goldens -q
```

CI never regenerates these files; without `--update-goldens`, changed or missing HTML
goldens fail the test.
# Rendered reader

`reading-demo.html` is actual offline CLI output from `examples/reading-demo.tex`.
CI validates this committed document and fails if the HTML golden set is empty.
Regenerate after reviewed reader changes with:

```sh
uv run paperdeck -q convert examples/reading-demo.tex --offline --output tests/goldens/reading-demo.html --force
uv run python -m paperdeck.render.validate tests/goldens/reading-demo.html
```
