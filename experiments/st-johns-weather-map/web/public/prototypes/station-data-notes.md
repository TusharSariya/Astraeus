# Station and point study: captured evidence

Throwaway experiment for [Design station and point layers on the Map](https://github.com/TusharSariya/Astraeus/issues/58). This document is non-normative. No production
contracts, scientific rules, or provider behavior are changed.

## Capture and reproduction

`station-captures.json` contains 24 complete, timestamped, read-only responses from
`http://localhost:8000/api/experiments/weather/v0`. Every entry records its request
URL, request and completion times, HTTP status, headers, and complete JSON body.
The file was captured on 2026-09-05 UTC. It includes `/layers`, `/timeline`, six
`/point` combinations, and sixteen `/layers/{id}/features` responses. No values
were typed in, synthesized, or copied between locations.

The three Focus locations are Signal Hill (the existing map's 47.5704, -52.6816),
CYYT (47.6186, -52.7519), and a deliberately arbitrary query at 47.54, -52.8.
CYYT's coordinates come from the experiment's `ingest/adapters/awc.py`
`CYYT_LAT`/`CYYT_LON` constants. They establish an adapter station reference,
not a returned observation. An arbitrary query marker means only “sample here”.

The capture instants are 2026-09-04 01:00 UTC, the earliest permitted instant in
the captured timeline, and 2026-09-05 01:00 UTC, the then-current API hour. These
are fixed capture instants; the latter must not be presented as a moving “now”.
A subsequent live request may reject either instant when its rolling window
moves. The UI must show the request error, never silently use the capture.

## Findings

| Product | Advertised latest sample | Evidence available at capture Focus times |
| --- | --- | --- |
| CYYT METAR/SPECI | Sep 3 02:00 UTC | No point reading or feature geometry |
| CYYT TAF | Sep 1 10:00 UTC | No valid point reading or feature geometry |
| AQHI | Sep 3 02:00 UTC | No point reading or feature geometry |
| CAP alert points / features | Sep 3 01:45:01 UTC | No point reading or feature geometry |
| HRDPS and RDPS surface bundles | Sep 3 18:00 UTC | No point reading or feature geometry |
| GFS surface / column | Sep 4 01:00 UTC | 12 actual numeric fields at earlier Focus; none at later Focus |
| GFS upper air | Sep 4 01:00 UTC | Four actual wind fields at 200 and 300 hPa at earlier Focus; none later |

The historical METAR, TAF, AQHI, CAP, HRDPS and RDPS advertised frames each return
HTTP 422 from `/features`: their stored frame lies outside the API's current
permitted window. At the earliest permitted instant their feature collections
are empty. GFS surface and upper-air `/features` are also empty at that instant,
while `/point` can sample the underlying model fields. `/layers` presence is
therefore neither proof of a station observation nor proof of usable geometry.

At Sep 4 01:00 UTC, all three Focus queries return model samples with source
`noaa-gfs`, per-field evidence classes `retrieved` or `derived_here`, delivery
kind `published_cell`, source
resolution 0.25 degrees, and provenance freshness `stale`. The source run time
is Sep 2 18:00 UTC. The returned grid sample at 47.5, -52.75 is explicitly in
provenance, including distance from each Focus. It must not be moved to CYYT or
labelled an airport observation. Values remain inspectable as stale model
evidence; no station marker is created from them. Pressure-level fields are
kept in a separate upper-air record. Precipitable water remains explicitly an
entire-atmosphere column quantity within the labelled surface / column bundle.

The API's TAF notice says the retained artifact declares no `evidence_classes`
and was skipped because a value's class is required and never inferred. The
TAF layer's `group: observation` metadata must not cause a forecast to be called
an observation. The response also supplies no forecast-period end times.
Cadence and neighboring start times cannot establish a TAF validity interval.
No TAF reading or valid-period marker is shown.

No CAP geometry was established. An empty feature response is an absence of
retrieved evidence, not an “all clear”, and a CAP point would not establish an
alert coverage boundary. AQHI cannot be placed at a guessed monitoring site or
at the current Focus. Root `provenance-captures.json` was also inspected: it
contains GFS evidence and the same rejected-TAF notice, not a usable positive
station report.

## Module contract and rendering limits

`station-data.js` exports `FOCUSES`, `TIMES`,
`normalize(bundle, focusIdOrObject, validTime)`, and
`readLive(focusObject, validTime)`. `readLive` returns a new raw request bundle.
There is no captured-data fallback. `normalize` matches the exact route,
coordinate, and instant. A point with no matching capture is explicitly missing.

Records keep readings, units, classes, full provenance, raw responses,
Focus time, sample time, advertised time, absence reasons, source tolerance,
and raw error responses. Every record's `geometry` is null and `eligible` is
false in this evidence study. No usable station or alert geometry was returned
in the capture. Future live feature geometry remains unadmitted and is disclosed
as such until its report/source/time contract is established. `valueReadable` separately identifies returned numeric evidence.
`referenceGeometry` on the two CYYT records is only a location reference, with
an explicit basis; it never authorizes weather-marker styling. Missing values
are never zeroed. Forecast and observation times are not snapped or relabelled.

Manual verification: imported the module in Node and normalized all six captured
Focus/time combinations. The earlier instant produces exactly 12 GFS
surface/column and four GFS upper-air numeric readings for each Focus; the later
instant produces no numeric readings. No station/alert numeric reading or
weather marker is invented. The complete capture retains both HTTP 422 and
empty HTTP 200 outcomes for inspection. Browser integration and repository spec
validation are owned by the parent task.

The runtime enforces a 20-second timeout per live request. Non-JSON and HTTP
failures retain their response evidence and cannot fall back to saved values.
Numeric display requires matching live point and provenance times, passed quality,
source attribution, units and an admitted evidence class; blocked, absent or
unverified numeric payloads are suppressed with a reason and the raw body retained.
Stale genuine readings remain inspectable. Bundle glyphs use admitted readings
only, so null placeholder provenance cannot imply a retrieved observation.
