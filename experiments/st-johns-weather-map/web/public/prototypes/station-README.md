# Station and point layers on the Map

Experimental artifact for [Design station and point layers on the Map](https://github.com/TusharSariya/Astraeus/issues/58). The owner selected **A — Layer-led**. [Canonical resolution](https://github.com/TusharSariya/Astraeus/issues/58#issuecomment-5548645284). B and C remain comparison artifacts, not selected product modes. This does not change accepted product behavior or specification status.

Run from the repository root:

```sh
PORT=5203 python3 experiments/st-johns-weather-map/web/public/prototypes/serve.py
```

Open <http://localhost:5203/map.html?stationStudy=1&variant=A>. Bottom arrows compare three alternatives while preserving Focus, time, layer order/toggles, selection, and inspector state:

- **A — Layer-led:** choose the layer; inspect its readings and absence reasons below the map.
- **B — Place roster:** enter through CYYT, the shared Focus, or evidence without a usable location. The roster filters the displayed stack without changing enabled layers.
- **C — Field lens:** choose a model field at Focus and keep its value, source, time, freshness, and sampled grid cell beside the map.

This study isolates the non-raster stack. The original raster prototype remains at `map.html?mv=A`; the study does not verify combined raster/station rendering or swipe. It reuses the selected Hyperlegible tokens, Sources evidence glyphs, and Map reference styling. On narrow screens, disclosures flow below the map to avoid covering one another. This is responsive access to the study, not the deferred phone brief.

## Evidence and limits

`station-captures.json` contains 24 timestamped HTTP responses: catalogue, timeline, six point requests, and sixteen feature requests. See `station-data-notes.md` for the audit. Historical mode uses exact captured coordinates and instants; another map location does not borrow a nearby capture. Live mode requests fresh responses and never falls back to the capture after failure. The unavailable-state control exercises absence explicitly.

No usable station report geometry was available in these responses. CYYT is an **airport reference** from adapter coordinates, not an observation. The shared Focus is also a reference. Both are excluded from weather-marker counts. AQHI and CAP are not assigned invented locations; absence of CAP geometry is not an all-clear. TAF is a forecast and remains unreadable without its valid interval and admitted report evidence.

The earlier captured instant exposes stale GFS model values for surface/column and upper-air fields. They retain their actual per-field retrieved or derived evidence classes. Values belong to the sampled model cell, not an airport station or the exact requested coordinate. The inspector preserves query/sample coordinates, distance, units, levels, valid/run/retrieval times, freshness contradictions, method, quality, attribution, and complete raw responses. Display rounding is at most two decimal places; raw precision is retained. A genuine numeric zero remains visible.

Admission requires finite numeric data, matching live point and provenance modes, source identity, provider/product/unit metadata, admitted evidence class, passed quality, and matching Focus time and returned query coordinates. Blocked and absent evidence remains unreadable. Stale model values remain explicitly stale. Future nonempty feature geometry is disclosed as unadmitted: this study deliberately does not invent a positive station eligibility contract. Positive station-marker rendering and TAF interval handling therefore remain **unverified**, not implemented capabilities.

The external reference basemap can fail independently of weather requests; a visible map error is shown. There is no generated weather display. Current-hour live reads are explicit; a saved historical instant is never labelled moving “now.”

## Verification and handoff

Browser checks cover all three alternatives, state continuity, reference-pin selection without moving Focus, zero versus absence, arbitrary uncaptured coordinates, layer controls, field selection, outage/HTTP 502 with no fallback, themes and vision simulations, and 390px document width. A real live read completed all eleven requested routes with HTTP 200. Syntax checks cover the new modules and guarded original map script. The spec validator is required before handoff.

No physical-device, screen-reader, outdoor red-night, positive station geometry, or combined raster/station composition claim is made. API follow-up needs report-to-station association, report validity (including TAF intervals), coverage semantics, and consistent freshness provenance before positive station rendering can be judged.

Classification: Experiment. Spec-Refs: GOV-SPEC-001, GOV-SPEC-002, GOV-SPEC-004, GOV-SPEC-005. No normative specification status changed; owner feedback on this artifact feeds the later API and implementation proposals.


## Keyboard accessibility repair study

The owner selected the shared interaction contract from the evidence-accessibility audit. This isolated repair branch implements explicit nonmodal inspector entry, actual-opener restoration on Close/scoped Escape, visible heading fallback if the opener disappears, and retained logical focus after layer selection, toggle and reorder (including the disabled edge action). Repeated Inspect names identify their layer; selected layers expose pressed state. Arrow navigation uses native controls rather than global prototype shortcuts.

A labelled coordinate form provides a keyboard counterpart to choosing a map point. It preserves entered query precision and uses the existing prototype input bounds; the documented API coverage mismatch is not repaired by this form. Exact uncaptured points still show absence. Existing semantic reading buttons provide model values, class/source, units, time and freshness without relying on the map canvas. Status updates are concise and identical banner text is not replaced on unrelated rerenders.

Run the repair server with `PORT=5213 python3 experiments/st-johns-weather-map/web/public/prototypes/serve.py`, then open <http://localhost:5213/map.html?stationStudy=1&variant=A>.

With Playwright installed/resolvable, run `node experiments/st-johns-weather-map/web/public/prototypes/check-station-accessibility.cjs`; `PLAYWRIGHT_MODULE` can point to another installed Playwright module. Checks exercise Enter/Space, opener/fallback focus, reorder edge, zero/absence, keyboard point entry, native arrow/Escape scope and night/narrow layout. Syntax, specctl and diff checks passed.

Experiment only. Spec-Refs: GOV-SPEC-001, GOV-SPEC-002, GOV-SPEC-004, GOV-SPEC-005. Actual screen-reader speech, full sequential navigation, contrast/zoom, physical-device and assembled raster/Activity coverage remain unverified. This is not an accessibility-conformance claim.
