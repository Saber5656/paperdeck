# Security policy

Please report vulnerabilities through [GitHub Security Advisories](https://github.com/Saber5656/paperdeck/security/advisories) so that a private report can be created. Include the affected version, a reproducible description, and the smallest safe proof. Do not include credentials or private papers in a report.

We target an acknowledgement and an initial response within 14 days. The latest released version is supported; please retest fixes against the latest release before reporting a duplicate.

## Self-containment guarantee

The generated HTML reader is self-contained: its JavaScript, CSS, fonts, KaTeX assets, and paper data are embedded or bundled, and the viewer makes zero external requests. To verify an output locally, run:

```sh
python -m paperdeck.render.validate out.html
```

The validator rejects external viewer requests and missing bundled assets. This guarantee covers the generated reader and does not prevent the conversion process from fetching arXiv material or sending PDF text/images to a configured LLM provider.

## Residual risk

PDF parsing runs in process and remains a T3 residual risk. Convert untrusted PDFs cautiously, keep dependencies current, and use a separate low-privilege environment when handling documents from unknown sources. Report parser crashes or unexpected file access through the private advisory channel.
