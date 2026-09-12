# Viewer visual design

Selected before implementation, 2026-09-12, using Product Design `user-context`,
`get-context`, `ideate`, and `image-to-code`. The installed plugin updated from 0.1.54
(preflight/ideation) to 0.1.55 (implementation skill resolved after stale path search).

## Brief and selection

A researcher opens an offline HTML paper, reads long passages, previews references,
and returns from jumps. Three independently generated visual alternatives were
compared: Quiet Folio (ivory/teal, floating previews), Modern Monograph (white/indigo,
permanent preview margin), Night Study (dark, spacious reading). The main agent selected
Quiet Folio under the user's autonomous implementation instruction. The selection adds
no new product scope. Source images and exact mapping are stored in Agents Vault.

Quiet Folio leaves space for a comfortable single column and temporary previews without
sacrificing reading width. Modern Monograph's permanent right rail reduces article width;
Night Study is useful as the required dark theme, rather than the default.

## Visual and interaction contract

- 1440 × 1024 desktop target; 230 px contents rail, 52 px utility header, 46 rem maximum
  reading width. Generous outer margins; no card container around the article.
- Ivory `#faf9f5`, ink `#202621`, links `#236759`, subtle separators `#d9dfd9`.
  Dark theme uses `#171b21`, `#e1e4e7`, and `#8ac8b6` with comparable contrast.
- Georgia/system serif article, 18 px/1.7 body; system sans UI, 14 px. No downloaded
  fonts except bundled KaTeX equation fonts. Title 2.5 rem, section headings 1.7 rem.
- Contents, theme, help and Back are labelled native buttons. Text labels provide clear
  accessible controls with no extra icon dependency or handcrafted pictograms.
- Below 900 px: contents closed initially, toggle opens an overlay. Article padding
  20 px; long equations/tables scroll horizontally. Popups remain within viewport.
- Reference delay 150 ms, grace 300 ms, focus equivalent, Escape dismissal, inert nested
  links, bounded back stack. No browser-history changes for internal jumps.
- Auto/light/dark theme, saved position and reduced-motion behavior per DESIGN §16.
  Print hides controls and displays the full text. Storage denial degrades silently.
- Unknown constructs, unresolved references, dropped figures and math failures remain
  legible with explicit text. Raw PDF math crops are retained; copied transcription
  is explicitly unverified. No photos, decorative raster assets or unrelated features.

Implementation remains the specified Python/Jinja/static JS/CSS product. A prototype
starter and Node build system would conflict with the canonical runtime and are not used.
Design QA compares the generated source and rendered reader at matching viewport/state,
then verifies small screens, keyboard controls, dark mode and offline behavior.
