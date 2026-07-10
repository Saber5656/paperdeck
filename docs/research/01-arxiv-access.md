# Research: arXiv programmatic access

Date: 2026-07-08 (verified via web on this date)
Status: informs ADR-001 (converter strategy), DESIGN.md §8 (input acquisition), §20 (security model)

## Facts

### Endpoints

| Purpose | Endpoint | Notes |
|---|---|---|
| Metadata query | `https://export.arxiv.org/api/query?id_list=<id>` | Atom XML; title, authors, abstract, categories, version info |
| LaTeX source (e-print) | `https://export.arxiv.org/e-print/<id>` | gzipped tar (most common), single gzipped `.tex`, or raw PDF for PDF-only submissions |
| PDF | `https://export.arxiv.org/pdf/<id>` | May redirect; serves the compiled PDF |
| Official HTML | `https://arxiv.org/html/<id>v<N>` | LaTeXML-generated HTML; see coverage below |

`export.arxiv.org` is the mirror arXiv designates for programmatic access; interactive
`arxiv.org` should not be hit by automated tools except where a resource only exists there
(the `/html/` route). Implementation must verify at build time whether `/html/` is served on
`export.arxiv.org` and prefer it if so.

### Rate limits and Terms of Use

- Legacy APIs (arXiv API, OAI-PMH, RSS): **no more than 1 request every 3 seconds, single
  connection at a time** (source: arXiv API ToU).
- ToU permits retrieving, storing, and using e-print content for personal use or research
  purposes, and building discovery tools; it requires respecting rate limits and not
  circumventing them.
- Bulk harvesting is out of scope for paperdeck; no bulk pipelines (S3 requester-pays, OAI-PMH
  harvesting) are needed for v1.
- A descriptive `User-Agent` (e.g. `paperdeck/<version> (+repo URL)`) is good citizenship and
  helps arXiv contact tool authors instead of blocking them.

### Official HTML coverage (LaTeXML)

- arXiv generates HTML for **every new TeX/LaTeX submission since 2023-12**; older papers
  generally have no official HTML.
- ~97% of submissions produce *some* HTML (availability ceiling); the share converting without
  LaTeXML errors was ~75% as of the cited report, targeting 90%.
- HTML pages embed conversion-error report markers when LaTeXML encountered problems; these
  markers can be used as a machine-readable quality gate.
- LaTeXML implements special support for 400+ common LaTeX packages; unrecognized packages
  degrade output.

### arXiv ID forms the resolver must accept

| Form | Example |
|---|---|
| New-style ID | `2401.12345`, `2401.12345v2` |
| Old-style ID | `hep-th/9901001`, `math.GT/0309136` |
| abs URL | `https://arxiv.org/abs/2401.12345` |
| pdf URL | `https://arxiv.org/pdf/2401.12345` (with or without `.pdf`) |
| html URL | `https://arxiv.org/html/2401.12345v1` |
| DOI form | `arXiv:2401.12345` prefix string |

## Impact on paperdeck design

1. A single `ArxivClient` must own **all** arXiv traffic and enforce a process-wide rate
   limiter (min interval 3s between requests, one connection).
2. The official HTML route makes a **deterministic high-fidelity converter** possible for
   papers from 2023-12 onward with no heavy local toolchain. It becomes the preferred engine
   when available and healthy (quality gate on LaTeXML error markers).
3. Older arXiv papers (pre-2023-12) must flow through the LaTeX-source engine (pandoc) or the
   PDF engine.
4. Network allowlist for the fetch phase is exactly: `export.arxiv.org`, `arxiv.org`.
5. Every downloaded artifact is cached (XDG cache dir) so repeat conversions make zero network
   requests.

## Sources

- [Terms of Use for arXiv APIs](https://info.arxiv.org/help/api/tou.html)
- [arXiv API Access](https://info.arxiv.org/help/api/index.html)
- [arXiv Bulk Data Access](https://info.arxiv.org/help/bulk_data.html)
- [Accessibility update: arXiv now offers papers in HTML format](https://blog.arxiv.org/2023/12/21/accessibility-update-arxiv-now-offers-papers-in-html-format/)
- [HTML as an accessible format for papers](https://info.arxiv.org/about/accessible_HTML.html)
- [Scaling Accessible Mathematics on arXiv: HTML Conversion and MathML 4](https://arxiv.org/abs/2605.16562)
- [HTML papers on arXiv — why it is important, and how we made it happen](https://arxiv.org/abs/2402.08954)
