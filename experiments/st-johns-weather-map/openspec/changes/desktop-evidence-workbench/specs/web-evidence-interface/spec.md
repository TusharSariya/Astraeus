## MODIFIED Requirements

### Requirement: Layers are an additive stack with per-layer opacity and published draw order
The map SHALL support several layers drawn at once, each toggleable and each with its own opacity control. The reader SHALL be able to reorder the stack, and the current order, opacity, and visibility SHALL be represented in the URL. A reader with no saved or linked stack SHALL receive the five-layer Nowcast built-in with the roles selected in Wayfinder #46 and current delivery identities (GOES natural colour `geomet-live-goes-east-naturalcolor`, HRDPS cloud `geomet-live-hrdps-nt`, selected-time CAP `eccc-cap-alerts-current`, radar `eccc-radar-radar`, lightning `eccc-lightning-lightning`); a Saved stack loaded from the browser or URL SHALL replace the current stack explicitly. Every requested layer SHALL still resolve and fail independently, so an unavailable default member never becomes a substitute value or removes the remaining stack.

#### Scenario: Radar over a field
- **WHEN** two layers are enabled
- **THEN** both draw in the reader's current order, each at its own opacity

#### Scenario: A first visit
- **WHEN** no saved or linked stack exists
- **THEN** the Nowcast built-in requests its five declared layers and reports every unavailable member instead of filling it from another source or instant

#### Scenario: A linked stack is opened
- **WHEN** the URL names an ordered stack
- **THEN** it replaces the current stack without merging hidden defaults into it

#### Scenario: No layer selected
- **WHEN** the reader explicitly removes every layer from the stack
- **THEN** the text alternative states "Basemap only. No meteorological layer is requested." and the empty stack persists for that link

#### Scenario: No layer published
- **WHEN** `/layers` returns nothing or could not be read
- **THEN** the selector shows a status message naming the reason, the map remains a basemap, and no layer is invented

#### Scenario: Retired linked or saved layer
- **WHEN** an explicit stack names a retired delivery identity
- **THEN** the selection is preserved, its absence is explained, and a known replacement is offered only if it is published in the current catalogue and not already selected
- **AND** accepting replacement preserves drawing position, visibility and opacity, focuses the replacement's visibility control, and changes the URL through the existing stack update
- **AND** saving/loading a stack retains exactly its requested identities

#### Scenario: Distinguishing catalogue and draw failures
- **WHEN** a selected layer cannot draw
- **THEN** the row distinguishes catalogue loading, catalogue request failure, successful catalogue absence, draw loading and unavailable imagery
- **AND** details expose the returned draw reason and catalogue notices without asserting a provider HTTP failure, empty dataset or cache hit that the response does not establish

Verification: `web/src/workbench/MapStack.test.tsx` exercises default identities,
explicit replacement, preserved selection settings and focus, duplicate refusal,
loading/failure/absence states and retained saved selections. Browser verification
checks replacement and URL restoration using constructed responses, plus a bounded
live catalogue/raster check recorded separately from fixture evidence.

The feature loader also conforms to the accepted `evidence-truth-boundary`
requirements “The browser trusts the declared mode, not the status code” and
“An empty retrieved answer is distinct from no retrieval”. Mapped regressions in
`web/src/api.test.ts` reject unavailable/missing/unknown modes even on HTTP 200
and retain provider notices. `web/src/MapPanel.test.tsx` and
`web/src/workbench/MapStack.test.tsx` verify that a successful empty collection
emits an empty receipt and a “No features returned” row rather than an outage.

#### Scenario: Stored sample and provider image inventories differ
- **WHEN** a retained WMS sample predates the serving window but its recorded provider binding advertises current images
- **THEN** the layer keeps its identity and exposes current image times separately from an empty in-window sample axis
- **AND** the map requests images at image timestamps, never features at those image-only timestamps
- **AND** the native timeline includes the declared image timestamps

#### Scenario: Catalogue frames cannot pass serving validation
- **WHEN** any layer producer returns sample times, frame records or image times outside the current serving window
- **THEN** the catalogue removes those times from its requestable axes and explains the excluded extent
- **AND** frame resolution also refuses out-of-window frames from an older catalogue without issuing malformed requests

Verification: catalogue endpoint regressions cover every producer through the
shared response boundary, including boundary instants and rolled windows. Map
request regressions distinguish sample and image axes, provider failure and stale
older API responses. Bounded live checks audit every advertised frame axis and
request the current radar/lightning imagery independently.
