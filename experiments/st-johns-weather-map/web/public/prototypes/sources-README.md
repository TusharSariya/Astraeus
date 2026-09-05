# Sources view design study

**Experiment. Combined direction selected by the owner.** Keep all three
perspectives inside Sources in the settled Bench shell for
[Design the Sources view](https://github.com/TusharSariya/Astraeus/issues/52).
Source ledger is the default; Family finder and Coverage lanes answer
complementary questions over the same data. Switching perspectives preserves
filters, shared Focus and the open inspector.

This records the owner’s design selection, not prototype promotion. No production
route or normative specification is changed by this study annotation.

From this directory:

```sh
PORT=5202 python3 serve.py
```

Open <http://localhost:5202/sources.html?variant=A>. The inherited server prints
an older provenance URL; use the Sources URL above. Its read-only `/api` proxy
connects to localhost:8000.

- **A / Source ledger:** source-first directory. Registry state/reason, retrieval
  freshness, run assessment, temporal evidence and licence sit in parallel columns.
- **B / Family finder:** family-first directory leading to a field-by-source
  matrix of declared storage mappings. Source temporal status remains in each
  column header; it never becomes a claim of field availability.
- **C / Coverage lanes:** exact returned retained-run samples, layer frames and
  aged-out declarations on separate tracks. The complete matching catalogue stays
  beside the lanes, including sources with no temporal marks.

Use the bottom arrows or left/right keys outside native controls to switch.
Variant, location and instant live in the URL. Filters, theme, vision simulation,
inspector selection and response objects remain in memory. Switching perspectives
preserves them. The A/B/C controls remain the study navigation; the selected
product direction is a perspective switcher within Sources. Other Bench view labels provide shell context only.

## Review interactions

- Search by source ID, product or producer; filter by declared field family,
  registry state, stale retrieval, retained run or aged-out declaration at Focus.
  Clear filters returns to the whole catalogue.
- In B, choose a family to see its matrix. A family groups related quantities,
  not interchangeable values. “Stored” comes from a registry mapping, not a
  successful retrieval at the selected field, coordinate or time.
- Click a source or matrix cell for the docked inspector: class availability,
  delivery kind, registry reason, retrieval and run freshness, licence/attribution,
  fields and mapping notes, layers with verified join basis, exact timeline item,
  API notices, full records and request provenance.
- Change the shared instant through the selector or bottom rail. “Set Focus to
  now” uses the wall-clock instant; the timeline has discrete samples, so this
  usually reports no exact item. It does not round or substitute an earlier item.
- Change location between registered Signal Hill and arbitrary St. John's.
  These endpoints are global/temporal and do not sample coordinates: the location
  remains shared context, and local coverage stays explicitly unestablished.
- Historical API capture is the default. “Read API now” independently reads all
  four endpoints. It clears the previous live response while reading. Failures
  remain unavailable without capture fallback. Capture restoration is explicit.
  The unavailable-state control supplies no source records or numerical fixtures.
- Light, dark and red night use unchanged C Hyperlegible tokens. Grayscale and
  deuteranopia are display simulations. Provider slots follow the existing source
  lists; unknown sources use the existing Other slot. Colour carries no unique
  evidence meaning. The unknown-class symbol is not a new evidence class.

## Evidence boundaries

Four requests captured September 5, 2026 UTC: `/catalog`, `/sources/status`,
`/timeline`, `/layers`. Full request/response records are in
[sources-captures.json](sources-captures.json); schema and join findings are in
[sources-data-notes.md](sources-data-notes.md).

This capture contains 118 catalogue sources, 19 declared family names, 118 status
records, 361 timeline instants and 35 layers. Every timeline retained-coverage
array is empty. All 35 layer run-stale assessments are null. No aged-out source
is declared. These absent states are real capture facts, not invented fixtures.

21 layers have verified source joins from unique catalogue products or explicit
backend aliases/adapter pairs. 14 remain unmapped and inspectable under API
notices. A missing join does not establish that a source has no layers. GFS is
listed as an available product at some instants while retained-run coverage is
empty; both facts remain visible without resolving the discrepancy in the client.

Evidence class is not served on catalogue records. It is not inferred from
registry state, product name or delivery kind. Per-reading method/inputs, quality,
sample geometry and comparability are not supplied by these four endpoints;
registry mapping notes are shown verbatim without upgrading them to per-value
provenance. API additions remain owned by
[Settle the API contract additions the prototypes proved](https://github.com/TusharSariya/Astraeus/issues/54).

C uses exact temporal marks, without continuous fills, interpolated coverage,
nearest-frame selection or client freshness calculations. All layer-frame marks
are separate from retained-run marks. The layer inspector discloses stored versus
live-proxy basis. Freshness age is the API's age at its own read, not a ticking
client estimate. The four requests may read different store states.

## Governance and verification

Classification: **Experiment**. `Spec-Refs: GOV-SPEC-001, GOV-SPEC-002,
GOV-SPEC-004, GOV-SPEC-005`. These constrain the workflow; they do not accept
Sources UI behavior. Only the owner selects the design and authorizes normative
status changes. The prototype remains outside production, pending the map's API
and specification handoff gates.

Checks are manual/ad hoc, not an added prototype test suite:

```sh
node --check sources.js
node --check sources-data.js
```

From the worktree root:

```sh
uv run --project tools/specs python tools/specs/specctl.py validate
git diff --check
```

Browser checks cover all three alternatives, search and filters, matrix navigation,
Focus and inspector continuity, immediate selected-row highlighting, canonical
URL time deduplication, arbitrary point disclosure, theme/vision controls,
390px page-overflow checks, capture/outage restoration, live reads and simulated
HTTP 502 responses with no capture fallback. A real capture has no positive
retained-run or aged-out examples, so those positive visual states are unverified.
Full keyboard/screen-reader and outdoor night checks are not claimed; the phone
brief remains a separate design decision.

The owner selected the combined direction in the design review: all three are
useful ways to see the same data. The [issue resolution](https://github.com/TusharSariya/Astraeus/issues/52#issuecomment-5548442947)
and map pointer carry this decision forward to the API and specification handoff gates. This selection
does not establish per-field availability or local coverage beyond the evidence
boundaries above.


## Keyboard repair study — September 5, 2026

The owner approved the shared interaction contract after Wayfinder69's browser
audit. This branch repairs that contract in the isolated Sources experiment;
no production behavior, source data, or normative status changes.

Explicit Inspect now focuses the docked inspector heading. Close or Escape
within the inspector restores the actual source/field opener, including after
rerender; a filtered-out opener falls back to the visible view heading. The
inspector remains nonmodal. Native control and horizontal-scroll arrows retain
their behavior; prototype variants use the explicit previous/next buttons.
Actions expose source identity, evidence class and expanded state. A single
250ms-debounced status reports the view/result count and API completion or
unavailability, without announcing the full catalogue. Refresh retains focus
while busy and ignores duplicate button activation. Reader announcement quality
still requires an actual reader session.

Run the repaired study with `PORT=5210 python3 serve.py` from this directory.
A bounded browser regression script covers the original defects and related
controls. With Playwright installed in the web project, run from this directory:

```sh
node sources-a11y-check.cjs
node --check sources.js
```

For a shared dependency installation, set `PLAYWRIGHT_MODULE` to its absolute
Playwright module directory; `PROTOTYPE_URL` defaults to `http://localhost:5210`.
The September 5 run used the workspace web project's Playwright installation.
The script stubs HTTP 502 in its own browser for failure verification and writes
its final accessibility snapshot to `/tmp/sources-a11y-repaired-ax.txt`.

Passed: ledger ArrowRight scrolls without switching variant; Enter/Space inspect
focuses the heading, with one Shift+Tab to Close instead of 238 Tabs; Close/Escape
restore visible source and exact matrix-cell openers; filtered-out opener uses
heading fallback; Coverage window rerender preserves its select focus; Escape
outside inspector is untouched; outage clears source rows and supplies concise
status; no browser page errors. Chromium keyboard/accessibility-tree evidence
only, not VoiceOver/NVDA/JAWS verification. Positive per-value generated evidence,
physical-device/outdoor use, and full contrast coverage remain unverified.

Classification: Experiment. Spec-Refs: GOV-SPEC-001, GOV-SPEC-002,
GOV-SPEC-004, GOV-SPEC-005. Root specctl validation and diff whitespace checks
passed; these are governance checks, not UI conformance certification.
