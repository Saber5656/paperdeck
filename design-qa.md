# Reader design QA

final result: passed

## Evidence and comparison conditions

- Source visual truth: `$AGENTS_VAULT_ROOT/01-Projects/paperdeck/mvp-20260912/design/selected-quiet-folio.png`.
- Source pixels: 1487 × 1058. The same aspect ratio was compared at a 1440 × 1024
  CSS viewport; source scale is approximately 0.968, not a device-density change.
- Implementation: `docs/qa/reader-light.jpg`, 1440 × 1024 pixels, 1× CSS density.
  This is actual CLI output from `examples/reading-demo.tex` using Pandoc 3.11.
- Additional captures: `docs/qa/reader-dark.jpg` (1440 × 1024) and
  `docs/qa/reader-narrow.jpg` (320 × 740), both at 1× density.
- Route/state: local reader, document top, contents open on desktop, light theme.
  Source and implementation images were supplied together in each comparison input.
  The source's open popup was assessed separately through real-document browser tests.
  Synthetic article prose, affiliations and section count differ; these are source
  document content differences, not layout evidence.
- Full-view composition plus the readable header, metadata, contents and first
  equation regions were inspected. Separate cropped inputs were unnecessary at this
  density because all controls and equation text were legible in the paired images.

## Findings and comparison history

1. Initial comparison was blocked: leaf contents entries exposed a useless Expand
   button; the desktop title wrapped onto two lines. Removed leaf disclosures and
   widened only the desktop title area while retaining the 46rem reading column.
2. The 320px test exposed a clipped Help button. Below 420px the visible label is
   shortened to Help, with its full accessible name retained and compact spacing.
3. Real converted content exposed inconsistent disclosure state. Branch controls
   now track visible child lists, expand the active path and match `aria-expanded`.
4. Cross-feature testing exposed a focus/scroll preview race, a scroll-spy offset
   mismatch, WebKit help-opener focus loss and headings hidden by the fixed header
   after keyboard navigation. Each was reproduced by a failing browser test and
   corrected. The updated converted-document scenarios passed in Chromium/WebKit.
5. Final paired capture confirms the title fits, leaf buttons are absent, populated
   branches have consistent controls, the reading column remains open and calm,
   and the narrow capture retains all persistent controls. No actionable P0/P1/P2
   visual findings remain.

## Required fidelity surfaces

- Typography: Georgia/system serif body and system UI text are deliberate offline
  choices. The source's slimmer serif is approximated by the platform font stack;
  the title, hierarchy and equation styling retain the selected direction.
- Spacing: fixed 53px header, 230px contents rail, centered 46rem body, expanded
  desktop masthead. Narrow layout uses 20px article margins and an overlay contents
  panel. The source has fewer sections; added subsection rows follow the same rhythm.
- Colors: ivory/teal and dark ink palette match the chosen direction. Computed body
  contrast is 14.65:1 light and 13.54:1 dark; muted text is 6.09:1 and 8.59:1.
- Image quality: actual bundled KaTeX typesetting remains crisp. No decorative
  imagery was required. Native labelled controls were selected before implementation
  instead of introducing a runtime icon/font dependency.
- Copy: product controls are concise, source prose is preserved, and the example is
  explicitly fictional. No prompt text or implementation workflow appears as reader UI.

## Interaction verification

Real LaTeX CLI output was tested for row-specific equation references, deep links,
preview rendering, Back/Backspace, contents highlighting, stored theme/position,
footnotes, help focus trapping/restoration, and print chrome removal. Chromium also
opened actual FakeLLM PDF output with its equation crop, unverified copy control and
citation preview. Produced HTML made zero HTTP requests and emitted no page errors.
Storage denial and a 320px viewport are covered. PDF model quality beyond the local
FakeLLM remains outside this visual QA evidence.

## Follow-up polish

The main title uses the system font available on each reader's device. Pixel-identical
font metrics across operating systems are not a v1 requirement. No blocking visual
work remains; rerun the browser matrix after interaction or layout changes.
