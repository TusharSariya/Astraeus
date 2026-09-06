# Open-Meteo GFS-Wave bounded-demand DQC (#99)

Status: non-normative implementation evidence. It does not admit the source,
change a specification status, or make the experiment operational.

## DQC-99-001: Free-access and request contract

The official [Marine Weather API](https://open-meteo.com/en/docs/marine-weather-api)
documents `https://marine-api.open-meteo.com/v1/marine`, the explicit
`ncep_gfswave016` GFS-Wave model, `cell_selection=sea`, and hourly
`wave_*`, `swell_wave_*`, and `wind_wave_*` height, period, and direction
variables. The listed values are instantaneous: heights are metres, periods
seconds, and directions are wave-*from* directions (`0°` from north and `90°`
from east). The service returns the selected grid-cell latitude and longitude.

The same documentation identifies the model as NOAA/NCEP GFS Wave 0.16 degree,
hourly with a 16-day reach and a six-hour update cadence. It does not document
or return a GFS-Wave producer-run identifier in the Marine point response. This
integration therefore leaves `run_time` unknown and names that limitation in
provenance; it does not read atmospheric-model `meta.json` as a substitute.

Open-Meteo's [terms](https://open-meteo.com/en/terms) allow the free endpoint
only for non-commercial use, up to 10,000 calls/day, 5,000/hour, and 600/minute,
with CC-BY 4.0 attribution and no availability guarantee. This local,
experimental, non-deployed request path has no API key and does not claim a
commercial-use right or any provider uptime.

## DQC-99-002: Bounded live receipt

At `2026-09-06T22:56:29Z`, a direct anonymous request for
`47.561500,-52.712600`, model `ncep_gfswave016`, `cell_selection=sea`, and
the nine declared fields for only `2026-09-06T20:00Z` returned HTTP 200.
The body was 675 bytes, SHA-256
`f4b8396d548c71981e8fed5321d98d32a97c28551b3c55bae05f5568412e88b4`.
The response selected the sea grid cell `47.666668,-52.666664`, returned the
one requested hourly timestamp, declared `m`, `s`, and `°` units, and carried a
finite value for every one of the nine fields. No raw provider body is stored
in Git.

## DQC-99-003: Implemented demand boundary

`openmeteo_gfs_wave_query.py` sends exactly one selected UTC hour and the nine
declared native fields. It validates the response time, units, finite values,
returned cell coordinate, and a 2 KiB received-body maximum. Its fixed
top-level/hourly structure makes the parse bounded to one timestamp and nine
fields; only compact normalized values and selected freshness headers remain in
the 256 KiB aggregate source-local cache.
It holds at most 32 canonical coordinate/time/field/model/sea-selection entries
for at most five minutes, shortened by a valid provider `Cache-Control: max-age`
directive when present. Identical misses coalesce. An expired cache entry is
never served on fetch failure; no neighbouring hour is substituted.

One missing or malformed native field becomes an explicitly unavailable field
with `native_field_unavailable`, while valid siblings remain available. A wholly
null sea-cell response is unavailable, never calm. The nine returned values map
to registered canonical keys, including the wind-wave and swell partition
period/direction keys. Values are `reprocessed` by Open-Meteo, name NOAA/NCEP
and Open-Meteo in provenance, remain non-primary but readable as evidence-only
alternatives, and keep `operational: false`.

Spec-Refs: GOV-SPEC-004; `evidence-truth-boundary` (retrieved-only,
unavailable-on-failure); `source-registry-catalogue` (registry state ceiling);
`point-evidence-sampling` (native point/provenance semantics).
