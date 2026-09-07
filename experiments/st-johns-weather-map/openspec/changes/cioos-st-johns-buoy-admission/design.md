# Design: CIOOS Atlantic St. John's buoy candidate

## Evidence boundary

The proposed source is CIOOS Atlantic ERDDAP dataset `SMA_st_johns`, not the
SmartAtlantic ERDDAP delivery that the existing `smartatlantic-st-johns`
registry record names. Both reference a Marine Institute buoy, but endpoint
hostname is not source identity. The record therefore names:

- distributor: CIOOS Atlantic ERDDAP;
- producer/station operator: Marine Institute, exactly as metadata states;
- dataset id: `SMA_st_johns`;
- dataset UUID: `92fdac9b-91b7-48f0-8afd-5d9d1b24db90`;
- canonical metadata:
  `https://cioosatlantic.ca/erddap/info/SMA_st_johns/index.html`;
- canonical data endpoint:
  `https://cioosatlantic.ca/erddap/tabledap/SMA_st_johns.csv`.

On 2026-09-07 the canonical metadata declared TimeSeries identity through
`station_name,longitude,latitude`, CC BY 4.0 and
`time_coverage_end: 2026-04-13T18:30:01Z`. The catalogue independently lists
CC BY 4.0. The record must preserve those citations and retrieval dates. A
future implementation re-reads bounded metadata before responding; it does
not assume that the historical coverage observation means the feed is current.
This proposal makes no latest-data request, so the displayed metadata end is a
stale-coverage signal rather than a claim about a current native sample.

## Native schema boundary

The first slice is deliberately small. It may request only these provider
variables plus station/time/coordinate identity:

| Provider variable | Published standard name | Literal published unit | Proposed field role |
| --- | --- | --- | --- |
| `air_temp_avg` | `air_temperature` | `degree_C` | air temperature |
| `air_dewpoint_avg` | `dew_point_temperature` | `degree_C` | dew point |
| `air_humidity_avg` | `relative_humidity` | `1` | relative humidity, no percent conversion |
| `air_pressure_avg` | `air_pressure` | `mbar` | air pressure, no hPa relabeling |
| `wind_spd_avg` | `wind_speed` | `m s-1` | wind speed |
| `wind_dir_avg` | `wind_from_direction` | `degree` | wind direction, from |
| `surface_temp_avg` | `sea_surface_temperature` | `degree_C` | sea-surface temperature |
| `wave_ht_sig` | `sea_surface_wave_significant_height` | `m` | significant wave height |
| `wave_period_max` | `sea_surface_wave_maximum_period` | `s` | maximum wave period |
| `wave_dir_avg` | `sea_surface_wave_from_direction` | `degree` | wave direction, from |

The decoder validates every requested variable's exact identifier, literal
unit and standard name against metadata before accepting a row. It preserves
zero values. A missing cell is null independently. The published metadata has
no `qa`, `quality`, or `data_flag` variable; the candidate cannot locally
invent one. No ADCP profile, derived comfort value, current direction/speed,
spectral array, conversion, or numerical quality check belongs in this slice.

`station_name` is the report's station identity. `platform_id`, when present in
metadata, is a platform attribute and not a substitute for a row's station
identity. The response carries a finite `precise_lat`/`precise_lon` row pair
when both are finite; otherwise it carries the finite `latitude`/`longitude`
pair. A mixed pair, a missing station name, or coordinates outside the metadata
station identity fails the record rather than creating a location.

## Proposed query and selection boundary

The future reader first fetches a bounded metadata document and validates the
identity/schema/coverage above. It then makes one canonical ERDDAP tabledap
CSV request containing only the identity columns and the ten fields above,
constrained to the proposed native selection interval. The canonical key
includes dataset id, endpoint, sorted variables, selected instant, selection
rule and the fixed station identity; it has no latitude search or model run.

The proposed current-context selection is the newest native record at or
before the aware selected timestamp with an age strictly less than one hour.
It is not a claim that ERDDAP guarantees a cadence. A future record, an exact
one-hour-old record, a station-name/coordinate mismatch, duplicate selected
identity, or a coverage end more than two hours before acquisition completion
returns unavailable. There is no interpolation, fallback station, older sample
or prior cache value. The report's coordinate is returned as a native station
report with a station-specific sampling method, not a rectilinear or
curvilinear grid cell.

These proposed intervals require owner acceptance. Until then this design does
not authorize a reader, API response, layer or UI claim.

## Receipt, cache and failure boundary

A future source-local cache follows the accepted demand-cache shape: a
canonical request is coalesced, fresh hits issue no provider payload request,
and the entry contains native report time, source/station identity, literal
units, missingness, metadata/data request identities, safe headers, byte
counts, body digests and final-byte receipt times. Limits, TTL and body/decode
budgets must be chosen from one measured fixture/body before implementation;
this proposal deliberately does not fabricate numeric limits.

After a finite expiry, a failed refresh exposes only bounded typed metadata and
`values_withheld: true`; it does not serve rows, raw bodies, exception traces,
stale samples, a stored artifact or another source. No scheduled ingestion or
archive is added. The default unselected point composition, cache-only layer
metadata and client card are implementation tasks only after acceptance.

## Required acceptance evidence

Before code, record one official metadata receipt and one bounded data receipt
outside Git, with hashes and final-byte completion. The data receipt must show
the exact selected variables, station identity, native time, units and
missingness. If current metadata still fails the adopted coverage rule, the
result is an explicit unavailable source, not a simulated live fixture.
