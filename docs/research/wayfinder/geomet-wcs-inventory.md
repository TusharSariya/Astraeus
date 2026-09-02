# GeoMet WCS inventory and cost for the evidence box

**Non-normative research, dated 2026-09-02.** Nothing here is a specification, an
admission decision or a registry change. It records what
`https://geo.weather.gc.ca/geomet` answered to live requests on 2026-09-02 and
what was read from the service's own capabilities documents. No source was
promoted, no artifact was published, no registry state was touched.

Resolves wayfinder research ticket
[#6](https://github.com/TusharSariya/Astraeus/issues/6). Evidence box: 45.0 to
50.5 N, 58.0 to 46.0 W. Service version at probe time: GeoMet-Weather 2.40.3.

## 1. Working request shapes

All shapes below were executed live and returned the stated status.

### GetCapabilities (WCS)

```
https://geo.weather.gc.ca/geomet?SERVICE=WCS&VERSION=2.0.1&REQUEST=GetCapabilities
```

200, `1 190 020` bytes, 7.27 s. It advertises **6123 coverages**. It carries
`wcs:CoverageId` and `wcs:CoverageSubtype` and **nothing else** — no title, no
abstract, no unit, no time extent. A coverage's meaning cannot be read from the
WCS capabilities document at all.

### Reading what a coverage means

The WCS document has no titles, so the human-readable quantity and the time and
reference-time extents must come from the **WMS** capabilities with the
single-leaf `LAYERS` filter the ingest adapter already uses:

```
https://geo.weather.gc.ca/geomet?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities&LAYERS=<coverage id>
```

200, ~18 KB. The leaf `<Title>` sits on the line immediately after
`<Name><coverage id></Name>`; the `<Dimension name="time">` and
`<Dimension name="reference_time">` elements on the same leaf give the extents.
WCS coverage ids and WMS layer names are the same strings, so one WMS fetch
documents one WCS coverage. This costs one upstream call per coverage.

### DescribeCoverage

```
https://geo.weather.gc.ca/geomet?SERVICE=WCS&VERSION=2.0.1&REQUEST=DescribeCoverage&COVERAGEID=<id>
```

200, ~2.5 KB, ~0.2 s. What it actually says, verified on
`HRDPS.CONTINENTAL_N4`, `HRDPS.CONTINENTAL.PRES_HR.850`,
`RDPS_10km_AirTemp_2m`, `GDPS_15km_AirTemp_2m` and `REPS.MEM.ETA_TT.01`:

- `gml:Envelope` carries `axisLabels="lat long"`, but the `gml:RectifiedGrid`
  inside carries `gml:axisLabels` **`long lat`**. The two disagree by design;
  the grid's order is the one the subset parameters follow.
- The grid is a plain `RectifiedGridCoverage` in **EPSG:4326 with a constant
  degree offset vector** — GeoMet has already reprojected off the model's native
  grid. This is why the rotated-lat/lon 2-D-coordinate problem that GRIB2 ingest
  hits (hard-won fact in `openspec/config.yaml`) does **not** appear in WCS
  output: `image/netcdf` comes back with 1-D `lon` and `lat`.
- **There is no time axis in the domain set.** The coverage is described as 2-D
  even though the layer is a time series. Time is not discoverable from
  `DescribeCoverage`; it must come from the WMS `time` dimension.
- The `swe:uom` in `gmlcov:rangeType` is not trustworthy.
  `HRDPS.CONTINENTAL_N4` is described as `W.m-2.Sr-1` while the WMS title for
  the same layer says `[J/m²]`. Take units from the WMS title, not the WCS
  range type.
- `REPS.MEM.ETA_TT.01` reports its offset vectors with
  `srsName=".../EPSG/0/102990"` while the envelope is EPSG:4326. Mixed CRS
  labelling within one description; the returned GeoTIFF is nonetheless
  georeferenced in 4326.

### GetCoverage — the shape that works

```
https://geo.weather.gc.ca/geomet
  ?SERVICE=WCS&VERSION=2.0.1&REQUEST=GetCoverage
  &COVERAGEID=HRDPS.CONTINENTAL_TT
  &FORMAT=image/tiff
  &SUBSET=long(-58,-46)
  &SUBSET=lat(45,50.5)
  &SCALESIZE=long(534),lat(245)
  &TIME=2026-09-02T18:00:00Z
  &DIM_REFERENCE_TIME=2026-09-01T12:00:00Z
```

200, `image/tiff`, 524 230 bytes, 0.66 s. Float32 GeoTIFF, tie point
`(-58.0, 50.5)`, pixel scale 0.0225 deg.

Rules established live:

1. **`FORMAT` is mandatory and its absence is not an OWS error.** Omitting it
   returns **HTTP 500 with an Apache `text/html` error page**, not an exception
   report. This is the most likely explanation of the 2026-08-30 "naive
   GetCoverage faults" note in `docs/geomet-layers.md`. `image/tiff` and
   `image/netcdf` both work (netCDF classic, 531 328 bytes for the same subset).
2. **`BBOX` is silently ignored.** `&BBOX=45,-58,50.5,-46` with no `SUBSET`
   returns **HTTP 200 and the entire continental grid** — 2540 x 1290 px,
   **13 114 558 bytes, 4.67 s**. A wrong subsetting parameter costs 13 MB and
   looks like success. This is the WCS sibling of the transposed-BBOX 96-byte
   PNG trap already recorded for WMS.
3. **Axis labels.** `long`/`lat` work; `Long`/`Lat` work; `x`/`y` work and
   return a byte-identical result. An unknown label returns **HTTP 200 with
   `text/xml`** carrying `ows:ExceptionReport` /
   `exceptionCode="InvalidAxisLabel"`, 529 bytes. Status code alone does not
   distinguish success from failure.
4. **`SCALESIZE` is required to get native resolution.** Without it the service
   returns its own default output size, which is *not* native and is not even
   isotropic. Measured defaults for the same box: HRDPS 272 x 164 px
   (0.0441 x 0.0335 deg, against a 0.0225 deg native grid); REPS 30 x 60 px
   (0.400 x 0.0917 deg, against 0.09 deg native). A caller that omits
   `SCALESIZE` gets a resampled field and no warning. GEPS is the exception —
   its default came back at its native 0.5 deg.
5. **`TIME` works on WCS and fails the same way as on WMS.** A valid instant is
   honoured. An unadvertised instant (`TIME=1999-01-01T00:00:00Z`) returns
   **HTTP 200 with `text/xml`** carrying
   `ogc:ServiceException code="NoMatch"`, 477 bytes — byte-for-byte the trap
   already recorded for WMS `GetMap`. `DIM_REFERENCE_TIME` is accepted on WCS
   as well.

**Native `SCALESIZE` for the evidence box** (12.0 deg longitude by 5.5 deg
latitude), from each model's `DescribeCoverage` offset vector:

| Model | Offset (deg) | `SCALESIZE` | Pixels | Float32 bytes |
|---|---|---|---|---|
| HRDPS 2.5 km | 0.022500 | `long(534),lat(245)` | 130 830 | ~524 KB |
| RDPS 10 km | 0.090298 | `long(133),lat(61)` | 8 113 | ~33 KB |
| GDPS 15 km | 0.150000 | `long(80),lat(37)` | 2 960 | ~12 KB |
| REPS | 0.090000 | `long(133),lat(61)` | 8 113 | ~33 KB |
| GEPS | 0.500000 | `long(24),lat(11)` | 264 | ~1.5 KB |

## 2. Coverage findings

`yes` = the coverage id exists and a `GetCoverage` subset to the box returned a
valid GeoTIFF today. `no` = no coverage of that quantity exists in the WCS
capabilities for that model. `unverified` = the id exists but the quantity was
not confirmed against a WMS title, or the semantics are open.

Naming differs by model and this matters: HRDPS uses RPN codes
(`HRDPS.CONTINENTAL_<CODE>[_<level>]` and `HRDPS.CONTINENTAL.PRES_<CODE>.<hPa>`)
while RDPS and GDPS use plain-English ids (`RDPS_10km_<Quantity>_<level>`).

| Field asked for | HRDPS (377 cov.) | RDPS (404 cov.) | GDPS (386 cov.) |
|---|---|---|---|
| Temperature at 40 / 80 / 120 m | **yes** — `_TT_40m/_80m/_120m` | **yes** — `AirTemp_40m/80m/120m` | **yes** — `AirTemp_40m/80m/120m` |
| Dew point at 40 / 80 / 120 m | **yes** — `_TD_40m/_80m/_120m` (title verified: "Dew point temperature at 80m above ground [°C]") | **no** — `DewPoint_2m` only | **no** — `DewPoint_2m` only |
| Relative humidity at 40 / 80 / 120 m | **yes** — `_HR_40m/_80m/_120m` (title verified, `[%]`) | **no** — only `SpecificHumidity_40m/80m/120m` | **no** — only `SpecificHumidity_40m/80m/120m` |
| Specific humidity at 40 / 80 / 120 m | **yes** — `_HU_40m/_80m/_120m` | **yes** | **yes** |
| Wind at 40 / 80 / 120 m | **yes, as speed and direction** — `_WSPD_*`, `_WD_*`. No u/v components published | **yes, as speed and direction** — `WindSpeed_*`, `WindDir_*`. No u/v | **yes, as speed and direction**. No u/v |
| Relative humidity on all pressure levels | **yes — 28 levels**: 50, 100, 150, 175, 200, 225, 250, 275, 300, 350, 400, 450, 500, 550, 600, 650, 700, 750, 800, 850, 875, 900, 925, 950, 970, 985, 1000, 1015 hPa (`.PRES_HR.<hPa>`) | **yes — 31 levels + 2 m**: adds 10, 20, 30 mb below HRDPS's set (`RelativeHumidity_<n>mb`) | **yes — 31 levels + 2 m**, same set as RDPS |
| Boundary-layer height | **yes** — `_HPBL`, title "Planetary boundary layer height [m]" | **yes** — `PlanetaryBoundaryLayerHeight` | **yes** — `PlanetaryBoundaryLayerHeight` |
| Skin temperature | **yes** — `_SKINT`, title "Aggregate land surface skin temperature [°C]" | **not the same quantity** — no `SKINT`; `RadiativeTemp` = "Aggregate surface radiative temperature [°C]" | **not the same quantity** — `RadiativeTemp` only |
| Ice cover | **yes, but analysis-only** — `_ICEC`, "[Proportion]"; WMS time extent is a single instant `2026-09-02T00:00:00Z/2026-09-02T00:00:00Z/PT0H`, not a forecast series | **yes** — `SeaIceFraction` | **yes** — `SeaIceFraction` |
| Low cloud | **no** | **no** | **no** |
| Mid cloud | **no** | **no** | **no** |
| High cloud | **no** | **no** | **no** |
| Cloud base / ceiling | **no** | **no** | **no** |
| Total cloud (for reference) | **yes** — `_NT`, "Total cloud cover [%]" (the opacity-weighted quantity of the existing hard-won fact) | **yes** — `TotalCloudCover` | **yes** — `TotalCloudCover` |
| Global radiation | **accumulated only** — `_N4` is "Downward shortwave **accumulated** radiation flux at the surface [J/m²]". No instantaneous W/m² coverage exists | **accumulated only** — `DownwardShortwaveRadiationFlux-Accum [J/m²]`, plus Net/Upward shortwave and downward longwave | **accumulated only**, same set (no `UpwardShortwaveRadiationFlux_NTAtm`) |

Grep of the whole 6123-coverage id list for `cloud`, `ceil`, `base` and the RPN
low/mid/high codes returns only `TotalCloudCover`, `CloudWater_EAtm`,
`HRDPS.CONTINENTAL_NT` and `HRDPS.CONTINENTAL_N4` across every model, plus
`CAPS_3km_*` equivalents. **Cloud by layer and cloud base are not on GeoMet WCS
at all**, for any ECCC model. The `HRDPS-WEonG_2.5km_SkyState` post-processed
layer is the nearest thing and is a categorical sky state, not a layered
fraction.

Two RDPS-only coverages found incidentally and directly relevant to the
astronomy activity profile, not asked for by the ticket and **not verified
beyond the id existing**: `RDPS_10km_SeeingIndex` and
`RDPS_10km_SkyTransparencyIndex`. GDPS and HRDPS publish neither.

## 3. Size and latency per coverage subset

Every row is one live `GetCoverage` on 2026-09-02, subset to the evidence box,
`FORMAT=image/tiff`, with the native `SCALESIZE` from section 1. Single
sequential requests from one client; no concurrency was attempted.

| Coverage | Bytes | Seconds |
|---|---|---|
| `HRDPS.CONTINENTAL_TT` | 524 230 | 0.61 |
| `HRDPS.CONTINENTAL_HR_40m` | 524 230 | 0.75 |
| `HRDPS.CONTINENTAL_TD_120m` | 524 230 | 0.64 |
| `HRDPS.CONTINENTAL_HPBL` | 524 230 | 0.60 |
| `HRDPS.CONTINENTAL_SKINT` | 524 230 | 0.64 |
| `HRDPS.CONTINENTAL_ICEC` | 526 366 | 0.99 |
| `HRDPS.CONTINENTAL_NT` | 524 230 | 0.59 |
| `HRDPS.CONTINENTAL_N4` | 524 230 | 0.61 |
| `HRDPS.CONTINENTAL.PRES_HR.850` | 524 230 | 0.73 |
| `RDPS_10km_AirTemp_40m` | 32 900 | 0.30 |
| `RDPS_10km_PlanetaryBoundaryLayerHeight` | 32 900 | 0.34 |
| `RDPS_10km_SeaIceFraction` | 40 348 | 0.32 |
| `RDPS_10km_RelativeHumidity_850mb` | 32 900 | 0.34 |
| `GDPS_15km_AirTemp_80m` | 12 266 | 0.40 |
| `GDPS_15km_TotalCloudCover` | 12 266 | 0.48 |
| `HRDPS.CONTINENTAL_TT`, **`BBOX` instead of `SUBSET`** (full grid) | 13 114 558 | 4.67 |
| `HRDPS.CONTINENTAL_TT`, `image/netcdf` | 531 328 | 0.81 |

Cost is essentially a function of pixel count, not of the variable. The planning
number is therefore simple and stable:

- **HRDPS: ~0.52 MB and ~0.65 s per field per time step.**
- **RDPS: ~0.033 MB and ~0.32 s** per field per time step.
- **GDPS: ~0.012 MB and ~0.45 s** per field per time step.
- **REPS: ~0.033 MB** per member per field per time step (at native
  `SCALESIZE`; measured at the service default it was 7 494 B).
- **GEPS: ~0.0015 MB** per reduction per field per time step.

What that implies for the 28-hour window, at hourly steps, one run, before any
compression: one HRDPS field is 29 steps x 0.52 MB = **~15 MB**. The 28 HRDPS
pressure-level RH coverages alone are **~424 MB** per run. The near-surface fog
set actually asked for (TT, TD, HR, WSPD, WD at each of 40, 80 and 120 m — 15
coverages) is **~226 MB** per run and **~10 upstream call-seconds per time
step**. Retrieval is cheap in time and expensive in bytes against a stated
three-hours-of-history storage constraint; a subset of levels or a coarser
`SCALESIZE` is the lever, and `SCALESIZE` is a documented, disclosed
resampling rather than a silent one.

`MAX_UPSTREAM_CALLS_PER_REQUEST` is 32 for the API. One WCS field at one time
costs one call, so any per-request WCS use is call-bound long before it is
byte-bound.

## 4. REPS and GEPS status

**Both answer on GeoMet WCS today, and both are still dead on Datamart.** The
hard-won fact that GEPS and REPS are 404 on every open ECCC HTTP path is about
`dd.weather.gc.ca` and the hpfx mirror; it is not true of GeoMet. GeoMet is
where they went.

**REPS — 1773 coverages, answers.**
`REPS.MEM.ETA_TT.01` subset to the box: 200, `image/tiff`, 7 494 B at the
service default size, 0.22 s. Member ids run `.01` through `.21` — **21
members**, confirmed by enumerating the capabilities — across **1239
`REPS.MEM.*` coverages**. Per member the published variables are 22 `ETA_*`
surface fields (`TT`, `HR`, `HU`, `WSPD`, `NT`, `N4`, `PN-SLP`, precipitation
types, …), `NTAT_EI`, and a `PRES_*` set: `GZ`, `HR` and `TT` on 9 pressure
levels (50, 100, 200, 250, 500, 700, 850, 925, 1000 hPa) plus `TT`, `HU` and
`WSPD` at 40 m, 80 m and 120 m. **Wind speed only — no u/v components on any
member**, so member wind direction is not retrievable, exactly as the
2026-09-02 measurement in `openspec/config.yaml` records. The remaining ~534
`REPS.DIAG.*` coverages are the provider's own reductions
(`ERC0`…`ERC100` percentiles, threshold probabilities).

**GEPS — 532 coverages, answers, still no members.**
`GEPS.DIAG.3_TT.ERC50` subset to the box: 200, `image/tiff`, 1 474 B, 0.22 s
(24 x 11 px at native 0.5 deg). **Zero `GEPS.MEM.*` coverages exist.**
Everything published is a provider reduction: `ERMEAN`, `ERSSTD`, percentiles
`ERC0`/`ERC10`/`ERC25`/`ERC50`/`ERC75`/`ERC90`/`ERC100`, and threshold
probabilities (`ERGE*`, `PROB`). This confirms, on a second endpoint and a
second protocol, the shape already recorded: GEPS gives its own statistic and
nothing else, which is retrieved evidence to be stored as issued and never
recombined.

## 5. Open questions

1. **Cloud by layer and cloud base do not exist on GeoMet.** If the field
   catalogue wants low/mid/high cloud or a ceiling, it must come from another
   producer, from `HRDPS-WEonG_2.5km_SkyState` as a categorical proxy, or from
   a declared derived-here closure. Which is a decision, not a lookup.
2. **`RadiativeTemp` versus `SKINT`.** Whether RDPS/GDPS "aggregate surface
   radiative temperature" is the same physical quantity as HRDPS "aggregate
   land surface skin temperature" is unverified. The air-sea difference that
   drives Grand Banks advection fog needs this settled before the two are put
   on one axis.
3. **Accumulated versus instantaneous shortwave.** Every ECCC global-radiation
   coverage is an accumulation in J/m². The accumulation window is not stated
   in the WMS title and was not verified. Differencing consecutive steps to get
   a mean flux would be derived-here, and repeats the GFS PDT 4.0/4.8 trap in a
   new place.
4. **HRDPS ice cover is analysis-only.** `_ICEC` advertised a single instant
   with `PT0H`. Whether that is permanent or an artefact of today's run is
   unverified; `RDPS_10km_SeaIceFraction`'s extent was not checked.
5. **No u/v anywhere.** Neither the deterministic models nor REPS publish wind
   components on WCS, only speed and direction. Any steering-wind use under the
   display carve-outs, which is stated in terms of a vector field, would have to
   reconstruct u/v from speed and direction — a derivation, with its own
   accuracy question at 40 to 120 m.
6. **Does WCS honour `reference_time` or only accept it?** `DIM_REFERENCE_TIME`
   returned 200 with a plausible payload, but the returned field was not
   compared against the same instant from a different run, so "accepted" is all
   that was verified.
7. **The 272 x 164 default.** Where the non-native default output size comes
   from, and whether it is stable, is unknown. Treat `SCALESIZE` as mandatory
   rather than relying on the default ever being native.
8. **Concurrency and rate limits.** All measurements are sequential and
   single-client. Nothing is known about GeoMet's behaviour under the parallel
   fetches a 29-step, 15-field pull would want.
9. **`RDPS_10km_SeeingIndex` / `SkyTransparencyIndex`.** Ids exist; quantity,
   units, method and provenance class unverified.

## 6. Verified live versus read from documentation

**Verified live on 2026-09-02** (curl against `geo.weather.gc.ca/geomet`;
roughly 50 upstream calls total):

- The full WCS `GetCapabilities` document and the 6123 coverage ids in it,
  including every per-model count, every level list, and the absence of
  low/mid/high cloud and cloud base. These come from grepping the saved
  document, not from memory.
- Every request shape, failure mode and status code in section 1: the ignored
  `BBOX`, the `InvalidAxisLabel` 200/XML, the missing-`FORMAT` HTTP 500 HTML,
  the `NoMatch` 200/XML on an unadvertised `TIME`, the accepted `x`/`y` and
  `Long`/`Lat` aliases, and `image/netcdf`.
- Grid geometry, offset vectors, axis-label disagreement, the absent time axis
  and the `EPSG:102990` oddity, from `DescribeCoverage` on five coverages.
- Every byte count and elapsed time in section 3, and the GeoTIFF dimensions
  and georeferencing behind them (read out of the returned TIFF tags).
- The WMS titles, units and time/reference-time extents quoted for
  `HRDPS.CONTINENTAL_TD`, `_HR`, `_HR_40m`, `_TD_80m`, `_HPBL`, `_SKINT`,
  `_ICEC`, `_NT`, `_N4`, `_WSPD_120m`, `RDPS_10km_RadiativeTemp` and
  `RDPS_10km_DownwardShortwaveRadiationFlux-Accum`.
- That REPS and GEPS coverages answer `GetCoverage` for the box, the 21 REPS
  members, and the absence of any `GEPS.MEM.*`.

**Read from documentation or inherited, not re-derived here:**

- The hard-won facts in `experiments/st-johns-weather-map/openspec/config.yaml`
  — HRDPS/RDPS liquid-water RH phase, HRDPS opacity-weighted `NT` versus GFS
  overlap cloud, the WEonG temporal smoothing kernel, the WMS
  `GetFeatureInfo`/axis-order/`NoMatch` traps, the ensemble shapes, the Datamart
  withdrawals.
- That GEPS and REPS are 404 on `dd.weather.gc.ca` and hpfx. Not re-probed for
  this ticket; only the GeoMet side was tested.
- `MAX_UPSTREAM_CALLS_PER_REQUEST = 32` and the single-leaf `LAYERS`
  capabilities filter, from `docs/geomet-layers.md` and
  `ingest/adapters/eccc_geomet.py`.

**Inferred, marked as such:** the per-run byte projections in section 3 are
arithmetic on one measured field size times 29 hourly steps. No multi-step pull
was actually executed.
