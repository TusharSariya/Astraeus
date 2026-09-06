# Design: optional North Atlantic forecast centres

## Evidence box and probe

The coverage gate uses the experiment's declared box, not a successful request
at St. John's alone:

```text
north 50.5 N
south 45.0 N
west  58.0 W
east  46.0 W
```

On 2026-09-03, NOAA NOMADS returned GRIB2 (`GRIB` magic and HTTP 200) for
total-cloud subsets over all four bounds:

| Product | Probed file | Result |
|---|---|---|
| RAP full-domain grid | `rap.t00z.awp130pgrbf00.grib2` | 133,177-byte GRIB2 subset |
| NAM parent grid | `nam.t00z.awphys00.tm00.grib2` | 1,790-byte GRIB2 subset |

The associated `.idx` inventories exposed `VIS`, `GUST`, pressure-level `TMP`,
`RH`, `UGRD` and `VGRD`; the subset request selected `TCDC`. These are one-run
access and inventory observations, not performance claims.

Primary references:

- NOAA RAP/RRFS fields: <https://rapidrefresh.noaa.gov/RAP/>
- NOAA NAM product inventory: <https://www.nco.ncep.noaa.gov/pmb/products/nam/>
- NOAA NOMADS production data: <https://nomads.ncep.noaa.gov/pub/data/nccf/com/>
- ECMWF open data: <https://www.ecmwf.int/en/forecasts/datasets/open-data>
- DWD open data: <https://www.dwd.de/EN/ourservices/opendata/opendata.html>

Full research notes:

- `docs/research/north-atlantic-forecast-model-viability.md`
- `docs/research/nvidia-earth2-cpu-feasibility.md`
- `docs/research/google-weathernext-3-validation.md`

## Admission matrix

| Family | Tier | Centre | Permitted role | Unresolved gate |
|---|---|---|---|---|
| HRDPS/RDPS/REPS | primary/fallback/ensemble | ECCC | Existing declared roles | Existing gates unchanged |
| IFS | optional native | ECMWF | Independent deterministic comparison | Adapter live smoke and skill |
| IFS ENS | optional native | ECMWF | Labelled member distribution | Bounded member/field storage and skill |
| AIFS Single/ENS | optional native | ECMWF | Same-centre scenario families | Cloud-field usefulness and skill |
| ICON Global | optional native | DWD | Independent deterministic comparison | Native-mesh live smoke and skill |
| GFS/GEFS | optional native | NOAA | NOAA representative/scenario family | Existing gates |
| RAP | optional candidate | NOAA | Event-day short-range scenario | Edge quality, cadence, latency, fixtures and skill |
| NAM parent | optional candidate | NOAA | Short-range diagnostic scenario | Edge quality, cadence, latency, fixtures and skill |
| RRFS-NA | conditional | NOAA | None until admitted | Stable operational feed, box coverage, inventory and skill |
| ARPEGE World | research only | Meteo-France | Labelled disagreement | Native official feed or accepted intermediary path |
| UKMO Global | research only | UK Met Office | Owner-only labelled disagreement | Native feed and redistribution-compatible terms |
| HRRR | excluded | NOAA | None | Domain does not cover the box |
| Icelandic/Nordic/Greenland/Iberian regional models | excluded | Various | None | No documented full-box coverage |
| Russian products | unvalidated | Various | None | Product identity, access, licence, coverage and reliability |
| Earth2Studio | framework | NVIDIA | Runs declared models; no evidence by itself | Per-asset licences and runtime verification |
| FourCastNet 1 | generated research | NVIDIA model initialized from a named source | CPU feasibility baseline and synoptic scenario | One-step CPU measurement; no direct cloud fields |
| FourCastNet 3 | generated conditional | NVIDIA model initialized from a named source | Probabilistic moisture/synoptic family | Full CPU/GPU inference, provenance and skill; no direct cloud fields |
| ForecastNet | excluded | Local training would own the output | None as supplied | Generic architecture; no atmospheric checkpoint or analysis |
| WeatherNext 3 | conditional restricted | Google; initialized partly from ECMWF HRES | High-priority global AI cloud ensemble | Allowlist, terms, live schema/cost/latency and Avalon skill |

## Independence and comparability

Centre diversity and product diversity are different axes. GFS, GEFS, RAP,
NAM and RRFS share the NOAA/NCEP centre label. IFS, IFS ENS and AIFS share the
ECMWF centre label. Only one deterministic representative per centre may enter
a centre-level comparison at an instant. Other deterministic runs remain
named scenarios, and ensemble members remain a within-family distribution.

Cloud fields are compared only when the field catalogue says their physical
definitions and temporal semantics are comparable. HRDPS opacity-weighted
cloud and GFS geometric-overlap cloud, for example, can be displayed together
as disagreement but cannot be averaged into a synthetic consensus.

## Promotion sequence

An optional candidate moves through these gates without skipping one:

1. Official product, access path, licence and redistribution terms recorded.
2. Full evidence-box subset succeeds at every corner and along an eastward
   upstream transect for at least three runs from different cycles.
3. Exact GRIB messages, levels, units, accumulation/instant semantics, grid and
   missing-value behavior are pinned in a fixture.
4. Publication cadence, latency, completeness and failure behavior are measured
   across at least seven days.
5. Retrospective evaluation covers coastal fog/stratus, frontal cloud and clear
   controls, with GOES and surface observations as verification rather than
   another model as truth.
6. Adapter fixture, live smoke, artifact validation, API readback and provenance
   checks pass.
7. The owner approves any registry promotion or V1 provider-contract change.

## Generated Earth-2 evidence

Earth2Studio is not a producer and receives no centre vote. Every generated
forecast names its initializer, exact checkpoint digest, framework version,
precision, device, seed/member and transformations. FourCastNet 1 and 3 do not
publish direct cloud, fog, ceiling or visibility fields, so neither satisfies
critical cloud evidence. A humidity-to-cloud diagnostic is a separate
construction requiring its own accepted method and verification.

The catalogue GPU badges are recommendations, not hard minima. CPU capability
is established only by full-checkpoint inference, not by loading a model or
running a dummy wrapper. Until measured, FCN3 CPU inference is `unverified`,
not `unsupported` and not `viable`.

## WeatherNext 3

WeatherNext 3 is a delivered Google forecast product, not an Earth2Studio-like
framework. Google publishes 64 members, hourly surface steps, 15-day main-cycle
forecasts, 48-hour interim forecasts, 0.1-degree gridded surface output and
direct total/high/medium/low cloud fractions. It does not publish direct fog,
visibility, ceiling or cloud-base fields.

Its hourly initialization cadence does not imply one-hour availability.
Published dissemination targets are about 7 hours 10 minutes to 7 hours 45
minutes after initialization for Google Cloud Storage and later for BigQuery
or Earth Engine, with documented variation. Initialization, publication and
retrieval times therefore remain distinct.

Access is allowlisted. Full ensemble access uses Requester Pays Google Cloud
Storage, and the real-time terms distinguish restricted future/recent data from
data at least one hour old under CC BY 4.0. The adapter must preserve access
surface, product version, terms class, member/statistic identity and Google's
documented ECMWF HRES analysis input dependency. The 64 members are one Google
family, not independent votes. No WeatherNext cloud value may be numerically
combined with HRDPS or GFS until field-catalogue comparability is verified.
