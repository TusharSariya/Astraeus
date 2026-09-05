# Sources view design study

**Experiment. Decision pending.** Three alternatives inside the settled Bench
shell for [Design the Sources view](https://github.com/TusharSariya/Astraeus/issues/52).
No production route or normative specification is changed.

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
inspector selection and response objects remain in memory. Switching alternatives
preserves them. Other Bench view labels provide shell context only.

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

No variant has been selected. Keep this ticket open until the owner chooses a
structure or combination, then record the resolution and append one map pointer.
