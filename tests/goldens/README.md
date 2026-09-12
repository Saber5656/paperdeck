# LaTeX semantic goldens

The files in `tests/goldens/latex/` record the stable, user-visible facts from the
subprocess LaTeX corpus run: title, section headings, equation numbering, and the
presence of the content-security policy. They intentionally omit provenance timestamps
and generated asset bytes, which are validated separately by the self-containment and
HTML tests.

To regenerate a golden after an intentional IR or renderer change, run the marked
pipeline test with `PAPERDECK_FAKE_NOW` set to a fixed ISO timestamp, inspect the
rendered HTML and validator report, then update the corresponding JSON by hand. CI
never regenerates these files; a changed golden must be reviewed with its fixture and
the semantic test.
