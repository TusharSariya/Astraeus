## ADDED Requirements

### Requirement: A scrub never blanks the map and never wastes retrieved work
While a newly selected frame is being retrieved, the interface SHALL keep
the previously drawn frame on screen at its own disclosed timestamp
(`refreshing`), and SHALL replace it only when the new frame arrives or the
retrieval fails - a failure still clears to the unavailable state with its
reason, because stale pixels under a new timestamp remain forbidden.
Requests SHALL be deduplicated per (layer, frame, extent) across concurrent
wants; a frame change SHALL NOT abort an in-flight raster request (its
result is cached for reuse) - only a viewport change or unmount aborts.
MapLibre image sources SHALL be updated in place for an unchanged layer
stack rather than removed and re-added per frame.

#### Scenario: Scrubbing to an uncached frame
- **WHEN** the selected instant moves to a frame not yet retrieved
- **THEN** the previous frame stays drawn, the text alternative says the
  last retrieved frame is shown at its own instant while the new one loads,
  and the swap happens only on arrival

#### Scenario: A failed frame clears
- **WHEN** the retrieval for the new frame fails
- **THEN** the imagery clears to the unavailable state with the reason -
  the held previous frame is not silently kept under the new selection

### Requirement: Budget-free frames are prefetched; proxied frames never are
The interface SHALL prefetch, at idle priority, the full published frame
axis (and, when interpolation is on, the adjacent-pair motion textures) of
every ACTIVE layer whose raster this experiment renders itself from stored
artifacts - these cost no upstream provider calls. Layers whose imagery is
live-proxied SHALL NOT be prefetched: their upstream budget is spent only
on what is actually shown.

#### Scenario: A rendered-grid layer warms its axis
- **WHEN** a rendered-grid layer is visible and the viewport settles
- **THEN** its remaining frames are fetched at idle priority so a scrub
  across the window paints from cache

#### Scenario: The proxy budget is untouched
- **WHEN** only live-proxied layers are visible
- **THEN** no speculative raster request is issued for them

### Requirement: Rendered rasters are right-sized and GPU-scaled nearest
Rasters of locally rendered layers MAY be requested at a bounded pixel size
smaller than the canvas and SHALL then be scaled on the GPU with
nearest-neighbor resampling, so the stored cells stay block-uniform and are
never smoothed by display scaling. Server-side, identical renders SHALL be
answered from a bounded cache keyed by everything that determines the bytes
(layer, frame, artifact revision and dataset identity, bounds, size, CRS),
and the expensive pixel-to-cell lookup of a curvilinear grid SHALL be
memoised per revision and extent - cached index arithmetic only; sampled
values are always read from the requested frame.

#### Scenario: The same frame twice
- **WHEN** the same (layer, frame, bounds, size, CRS) is requested again
  under the same published revision
- **THEN** the served bytes are identical and no re-render occurs

#### Scenario: A republished revision never inherits pixels
- **WHEN** the artifact moves to a new revision
- **THEN** its renders are computed afresh; no cache entry keyed to the old
  revision or dataset answers for it
