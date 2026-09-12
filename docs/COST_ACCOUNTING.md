# Model cost accounting

The estimate uses each configured model's own input and output price, including a
separate vision model. Cached responses contribute zero billable tokens and cost.
Every physical HTTP attempt reserves its estimated input and bounded output cost;
retries reserve again. Observed usage replaces the reservation after the response.

If a model has no configured price, the estimate and reported actual dollar cost
are unknown (`null` in the report and IR provenance). The ledger still reserves
conservative planning amounts at $10/$30 per million input/output tokens and warns
at two million tokens. These fallback amounts are not provider prices or a reported
bill. Configure the model's actual rates to apply the monetary budget at those rates;
configure explicit zero prices for a local model with no per-call charge.

This clarifies DESIGN §14.6: the two-million-token warning is retained, and unknown
pricing does not silently disable an explicit monetary budget. The IR cost field
also permits `null` so unknown cost is never represented as zero or as an invented
actual charge. Known-price and zero-call documents retain numeric cost values.
