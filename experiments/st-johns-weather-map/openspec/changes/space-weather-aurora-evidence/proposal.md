## Why

St. John's sits near 53-54 degrees geomagnetic latitude: aurora is genuinely
photographable there from roughly Kp 4-5 (NOAA's own viewline guidance), and
the map's night-sky audience currently has no evidence for it. NOAA SWPC
publishes the needed feeds keyless and JSON over HTTPS - verified live
2026-08-30/31: the OVATION aurora nowcast grid (`json/ovation_aurora_latest`,
with its own Observation Time and Forecast Time), the planetary K index
observed series and 3-day forecast (`products/noaa-planetary-k-index*.json`,
the forecast carrying per-value `observed|estimated|predicted` status), and
the real-time solar wind magnetometer series (`json/rtsw/rtsw_mag_1m.json`,
1-minute `bz_gsm`). The RTSW feed's own `source` field currently names
"SOLAR1"/ACE - not DSCOVR - so nothing here ever names a spacecraft the feed
does not declare.

What is verified: feed URLs, shapes and cadences, checked live. What is not:
long-run schema stability (a live smoke test pins the shapes) and OVATION's
skill (it is a model nowcast; the layer says so).

Classification: Experiment, Spec-Impact: none. `docs/specv1` is untouched.

## What Changes

- **`ingest/adapters/swpc.py`** (new, awc.py pattern): three registered
  adapters over PoliteClient JSON. `noaa-swpc-kp` publishes `kp_observed`
  and `kp_forecast` artifacts (the forecast keeps the provider's own
  per-value status as a flag-coded variable; no lead_hours are synthesized).
  `noaa-swpc-rtsw` publishes `solar_wind` (`bz_gsm`, `bt`) on a time axis
  with deliberately no latitude/longitude, so a planetary quantity can never
  reach `/point` with a fake sample distance. `noaa-swpc-ovation` publishes
  `aurora_grid`, the OVATION probabilities cropped to the Atlantic context
  box, valid at the file's own Forecast Time; a file without its timestamps
  is refused.
- **Registry**: three sources under a new `space_weather` category (kept out
  of the forecast/observation category lists), with parseable cadences
  (10 minutes / 1 minute / 3 hours) and freshness thresholds, plus
  `VARIABLE_OVERRIDES` entries so run metadata never claims the surface
  default variables.
- **`GET /space-weather`** (new): latest Bz with its age, the Kp observed
  series, and the Kp forecast series with per-value status, each with
  per-feed freshness against the registry thresholds; fixture mode fails
  closed (no fixture space weather is invented).
- **`/point`**: `aurora_probability` becomes a sampled field - a real
  gridded value at the requested coordinate.
- **Aurora map layer** `noaa-swpc-aurora-oval` (satellite.py pattern):
  rendered from the stored OVATION grid with `X-Weather-Image-Basis:
  rendered_grid`, transparent below a disclosed threshold, legend stating
  model, horizon and the Kp 4-5 St. John's guidance.
- **Web**: Kp and Bz metric cards, the aurora layer toggle in the existing
  rendered-grid group, and an `aurora_probability` evidence row.

## Capabilities

### New Capabilities

- `space-weather-evidence`: honesty rules for planetary space-weather
  evidence - observed vs forecast Kp separation, no fake localization, no
  undeclared spacecraft naming, staleness fail-closed.

### Modified Capabilities

- `artifact-ingestion`: three SWPC JSON adapters and their artifact shapes.
- `map-layers`: the rendered aurora layer beside the other rendered grids.
- `ingestion-worker-scheduling`: the three cadence/freshness proses parse.
