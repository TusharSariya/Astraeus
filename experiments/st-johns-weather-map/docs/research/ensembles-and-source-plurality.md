# Ensembles and source plurality: what an ensemble can actually give this map

Research pass of 2026-09-02, commissioned after the owner asked to add Google
WeatherNext 2 forecasting and an ensemble source (GEPS or GEFS), and observed
that the map has been reporting `HRDPS primary - consensus unavailable` for as
long as anyone has looked at it.

Three questions were open: whether the ensembles the registry already declares
are reachable at all; what shape their data actually takes; and why the
consensus that was specified to need one has never once produced a value. The
answer to the third is not a data gap. It is a contradiction between two
accepted specifications, and it is unsatisfiable by construction.

**Every claim below carries a tag.** VERIFIED means a live request was issued
from this machine on the stated date and the quoted bytes came back, or the
line was read in this repository's own source. REPORTED means the claim comes
from provider documentation or secondary knowledge without a primary read.
UNREAD means a source was identified and not opened, and no number from it may
be attributed. GAP is a negative result of the search, recorded so nobody
repeats it. Nothing tagged REPORTED has been promoted.

Companion to `01-atmospheric-nwp-satellite.md`, which catalogues source
availability; this document is about what the ensembles mean and how they
would have to be stored.

---

## 0. The headline, before the detail

1. **Consensus cannot ever fire, and never could.**
   `openspec/specs/point-evidence-sampling/spec.md:58` requires an ensemble
   before a consensus value is produced. `registry/audit.py:68-69` forbids any
   record that is not `deterministic_forecast` from being consensus-eligible.
   `api/weather_api/store.py:1173` derives `is_ensemble` from that same
   category. So the one class of evidence the gate demands is the one class
   the registry may never admit. The badge on the map is not reporting a
   missing feed. It is reporting an unsatisfiable requirement. **VERIFIED** in
   all three files.
2. **ECCC's ensembles have left the open HTTP feed.** GEPS and REPS are 404 at
   every path on `dd.weather.gc.ca` and its mirror, including the endpoint the
   registry declares. They survive only through GeoMet. **VERIFIED**, §2.
3. **The two ECCC ensembles are not the same kind of thing.** REPS publishes
   1239 individual member coverages in WCS, 1260 layers in WMS. GEPS
   publishes no members at all in either service, only
   its own mean, spread, percentiles and threshold probabilities. Any design
   that assumes "an ensemble means members" is wrong for half of them.
   **VERIFIED**, §3.
4. **WeatherNext 2 has no cloud variable.** Not total, not layered, not
   fractional. For a map whose subject is cloud, DeepMind's model contributes
   temperature, wind, pressure, humidity and omega, and nothing at all about
   the thing being drawn. **VERIFIED**, §7.
5. **GEFS total cloud is a six-hour average.** The same trap as hard-won fact
   7, one product further along. It is not comparable with the instantaneous
   HRDPS or GFS field and must not be drawn beside them as though it were.
   **VERIFIED**, §6.

---

## 1. What the registry already declares

Five records carry `category: "ensemble"`, every one at status
`implementing`, and not one of them has an adapter: `eccc-geps`, `eccc-reps`,
`ecmwf-ens`, `ecmwf-aifs-ens`, `noaa-gefs` (`registry/source_data.py`,
inventory in `00-current-inventory.md:34-40`). **VERIFIED.**

They are already wired for scheduling in everything except retrieval.
`ingest/registry.py:165` puts `ensemble` in `FORECAST_CATEGORIES`, so each one
already receives lead hours 0 through 24; `ingest/registry.py:152-155` already
lists `noaa-gefs`, `eccc-geps` and `ecmwf-ens` in `CONTEXT_BOX_SOURCES`, so
each would be stored on the wider Atlantic context bounds rather than cropped
to the Avalon. Cadence and freshness already parse: "2 runs/day" for GEPS
gives 43200 s, "00/06/12/18 UTC" for GEFS gives 21600 s. **VERIFIED** in
source.

What is missing is exactly one thing per source: a registered adapter
(`ingest/registry.py:350-355`). The scheduler needs no edit at all; that is
the design point of its module docstring.

---

## 2. Reachability, measured 2026-09-02

All requests issued from this machine on 2026-09-02, anonymous, no
credentials.

| Source | Route probed | Result |
| --- | --- | --- |
| `noaa-gefs` | `https://noaa-gefs-pds.s3.amazonaws.com/?list-type=2&prefix=gefs.20260901/12/atmos/pgrb2ap5/` | **200**, 31 members across 7 listing pages |
| `eccc-reps` | `https://geo.weather.gc.ca/geomet?service=WCS&version=2.0.1&request=GetCapabilities` | **200**, 1239 `REPS.MEM.*` coverages; WMS carries 1260 of the same layers |
| `eccc-geps` | same WCS capabilities | **200**, 532 `GEPS.*` coverages, none of them members |
| `eccc-geps` | `https://dd.weather.gc.ca/today/model_geps/` | **404** |
| `eccc-reps` | `https://dd.weather.gc.ca/today/model_reps/` | **404** |
| `eccc-geps` | `https://dd.weather.gc.ca/today/ensemble/geps/grib2/raw/00/003/` | **404** |
| `eccc-geps` | `https://hpfx.collab.science.gc.ca/20260902/WXO-DD/ensemble/geps/grib2/raw/00/003/` | **404** |
| `ecmwf-ens` | `https://data.ecmwf.int/forecasts/` | **200**, but an ECPDS portal shell, not the dated cycle tree the adapter assumes |

**VERIFIED.** Three findings worth keeping.

**The registry's declared GEPS endpoint is dead.** `registry/source_data.py`
gives `https://dd.weather.gc.ca/today/model_geps/` through the `_eccc_model`
helper. That path 404s. So does `model_reps`. Directory listings confirm it is
absence rather than a permissions answer: `https://dd.weather.gc.ca/today/`
lists 24 `model_*` directories, and neither `model_geps/` nor `model_reps/`
appears between `model_gdwps/` and `model_gewps/` where they would sort. The
`ensemble/` tree on both `dd.weather.gc.ca` and the
`hpfx.collab.science.gc.ca` mirror contains only `cansips/` and `doc/`.

**MSC's own product documentation still describes the dead path.** The GEPS
Datamart readme documents
`https://dd.weather.gc.ca/today/ensemble/geps/grib2/{TYPE}/{HH}/{hhh}/` with
filenames `CMC_geps-raw_..._allmbrs.grib2`. **REPORTED**, from the readme.
That URL 404s today. Either the product moved without the documentation
following, or it was withdrawn. Do not build against the documented path
without re-probing.

**GAP:** no route to raw GEPS or REPS GRIB2 was found on any open ECCC HTTP
host. The AMQP feed (MetPX Sarracenia) was not tried and remains the one
unexplored option; the registry's own `integration.client` string already
names it.

---

## 3. What each provider actually publishes

This is the finding that decides the storage design, and the two ECCC
ensembles fall on opposite sides of it.

### 3.1 REPS publishes members, as real coverages

GeoMet exposes member layers under the pattern `REPS.MEM.<VARIABLE>.<NN>` for
`NN` in 01 through 21: **1260 in the WMS capabilities and 1239 in the WCS
capabilities**, counted separately. Appearing in both matters, and the WCS
count is the one that counts: WMS would give
only pictures and single-pixel `GetFeatureInfo` answers (hard-won fact 1),
whereas a WCS coverage is a gridded field that can be subset and decoded.
**VERIFIED** by capabilities read.

Member variables include `ETA_TT` (temperature), `ETA_HR` (relative
humidity), `ETA_NT` (total cloud), `ETA_PN` and `ETA_PN-SLP` (pressure),
`ETA_WSPD` (wind speed), `ETA_PR`/`ETA_RN`/`ETA_SN` (precipitation, rain,
snow), plus pressure-level `PRES_TT`, `PRES_HR` and `PRES_GZ` at 50 through
1000 hPa and near-surface `PRES_TT`/`PRES_HU`/`PRES_WSPD` at 40, 80 and 120 m.
**VERIFIED.**

**Note the absence:** there is no `ETA_UU`/`ETA_VV` in the member set, only
`ETA_WSPD`. REPS members give wind speed without direction. A wind vector
cannot be reconstructed from them, and this project refuses to invent one.

### 3.2 GEPS publishes only its own reduction

Zero `GEPS.MEM.*` layers exist in either WMS or WCS capabilities.
**VERIFIED** by direct grep of both documents. What GEPS does publish is a
`GEPS.DIAG.*` family in five shapes:

| suffix | meaning |
| --- | --- |
| `ERMEAN` | ensemble mean |
| `ERSSTD` | ensemble standard deviation, the spread |
| `ERC0` … `ERC100` | percentiles, including `ERC50` as the median |
| `PROB` | probability of crossing a named threshold |
| `ERGE`, `ERLE` | probability at or above, at or below a threshold |

Total cloud is present as percentiles: `GEPS.DIAG.3_NT.ERC0` through
`ERC100`. Temperature likewise as `GEPS.DIAG.3_TT.*`, plus `GEPS.DIAG_TT_850`
on pressure levels. **VERIFIED.**

These are the provider's own statistics over the provider's own member set.
They are retrieved evidence in exactly the sense this project means, and they
must be stored as retrieved. What they must never become is a number this
stack recomputes, nor a statistic mixed with one computed from a different
member set. A mean of 21 ECCC members and a mean of 31 NOAA members are not
the same quantity and do not average.

### 3.3 GEFS publishes members as GRIB2, one file per member

Bucket `noaa-gefs-pds`, layout
`gefs.YYYYMMDD/HH/atmos/{pgrb2ap5,pgrb2bp5,pgrb2sp25}/`, cycles 00, 06, 12 and
18. **VERIFIED** by listing.

**31 members, verified live** rather than taken from documentation: paging the
full listing for `gefs.20260901/12/atmos/pgrb2ap5/` across seven pages yields
exactly `gec00` plus `gep01` through `gep30`. The AWS Open Data registry page
still says 21 members, which was true of GEFS v11; do not trust it.
**VERIFIED**, and it closes open question 1 below.

The `.idx` sidecar for `gec00.t12z.pgrb2a.0p50.f006` decodes to 5717 bytes and
carries what this project needs at the surface. Quoted verbatim:

```
63:63:11990018:d=2026090112:TMP:2 m above ground:6 hour fcst:ENS=low-res ctl
64:64:12131911:d=2026090112:RH:2 m above ground:6 hour fcst:ENS=low-res ctl
67:67:12628544:d=2026090112:UGRD:10 m above ground:6 hour fcst:ENS=low-res ctl
68:68:12892346:d=2026090112:VGRD:10 m above ground:6 hour fcst:ENS=low-res ctl
69:69:13152372:d=2026090112:APCP:surface:0-6 hour acc fcst:ENS=low-res ctl
77:77:13943824:d=2026090112:TCDC:entire atmosphere:0-6 hour ave fcst:ENS=low-res ctl
85:85:15306657:d=2026090112:PRMSL:mean sea level:6 hour fcst:ENS=low-res ctl
```

**VERIFIED.** Two things to read off it. The control member is self-labelling,
`ENS=low-res ctl`, so the control need not be inferred from the filename. And
there is no `DPT` at 2 m: GEFS gives relative humidity directly, which this
stack prefers anyway, since `resolve_relative_humidity` exists precisely to
avoid deriving it when a provider published it.

The cost shape differs sharply from GEPS. GEFS is one file per member per
lead, so a 24-hour window at 31 members is roughly 775 range-requested
downloads per run, comparable with the HRDPS profile ingest that already
lengthened the cycle past the GOES freshness threshold. The documented GEPS
GRIB2 layout, by contrast, packs every member into one `_allmbrs.grib2` file
per variable per lead. **REPORTED** for GEPS, since that path is 404.

---

## 4. The member problem in this codebase

Nothing in the stack understands an ensemble member. Three places would lose
or corrupt one, and only the third is loud about it.

**The decoder deletes the member id.** `ingest/grib.py:328` lists `number` in
`_MESSAGE_SCALAR_COORDS`, and `strip_message_scalars` drops every scalar
coordinate; at line 356 the four names in that tuple are dropped *without*
being recorded into attributes, unlike other scalar coordinates which survive
as `level_type` and `level_value`. cfgrib exposes the GEFS and GEPS member as
exactly that `number` coordinate. So today a member id is discarded at decode
and cannot be recovered downstream. **VERIFIED** in source.

**The sampler turns a member array into null.** `_sample_dataset`
(`api/weather_api/store.py:628-720`) recognises latitude, longitude, time and
an optional pressure coordinate, and nothing else. A variable carrying a
member dimension reaches line 687, `raw = located[name].values`, as a
31-element array; `float(raw)` at 690 raises; the exception is caught at
691-692 and the value becomes `None`. That is a silent loss, not an error.
**VERIFIED** in source.

There is a precedent for the right behaviour four lines earlier. Line 638
refuses a dataset outright when it carries an unrequested `pressure`
*dimension* rather than guessing which level to take. An unhandled member
dimension deserves the same refusal, and currently gets a null instead.

**The manifest cannot express member completeness.** `validate_run` checks a
time axis and per-field presence and units (`ingest/manifest.py:231-244`).
There is no way to say that 27 of 31 members arrived. The registry record for
`noaa-gefs` already names this gap in its own status reason: "member inventory
and completeness fixtures remain". **VERIFIED.**

**The renderer has no member concept.** `RenderedGridSpec` maps one 2-D field
per source, logical name and variable (`api/weather_api/grids.py:151-192`).
Drawing a member, or a spread, needs a decision that does not exist yet.

**Provenance has a member field that nothing fills.** `Provenance.member`
exists (`api/weather_api/models.py:85`), is read from the artifact provenance
dict rather than the dataset (`api/weather_api/store.py:1133`), and is set by
no adapter anywhere. The only non-null value in the repository is
`member: 'control'` in a web fixture. The interface currently asserts the
opposite of a member selector: `web/src/App.test.tsx:229-267` pins that the UI
renders "No ensemble member in returned provenance" and never sends a
`member=` query parameter. Exposing members is a product change, not only a
storage one. **VERIFIED.**

---

## 5. Why consensus is being removed

### 5.1 The contradiction

Three files, read 2026-09-02, all **VERIFIED**:

- `openspec/specs/point-evidence-sampling/spec.md:58` — "A consensus value
  SHALL be produced only when the eligible, fresh, QC-passing candidates
  include ECCC regional evidence, at least one independent deterministic
  centre, and at least one applicable ensemble family."
- `api/weather_api/science.py:68` — `if not (has_eccc and has_independent and
  has_ensemble): return ConsensusResult(False, ..., "minimum evidence not
  met")`, where `has_ensemble` needs a candidate whose category is `ensemble`.
- `registry/audit.py:68-69` — a record with `consensus.eligible` true must
  have `category == "deterministic_forecast"`, enforced by
  `registry/tests/test_audit.py`.

`_consensus_candidates` (`api/weather_api/store.py:1156-1176`) admits a sample
only when `config.may_enter_consensus`, which is the registry's
`consensus.eligible`. So a candidate must be eligible to be counted, must be
deterministic to be eligible, and must be an ensemble to satisfy the gate.
The three conditions have no common solution. The seven eligible records today
are `eccc-hrdps`, `eccc-rdps`, `eccc-gdps`, `ecmwf-ifs`, `ecmwf-aifs-single`,
`noaa-gfs` and `dwd-icon-global`, and every one is deterministic by
construction of the rule.

Two independent bugs would have masked each other even if the gate could pass.
`fresh` and `quality_passed` are left at their `True` defaults in
`_consensus_candidates`, so freshness is never actually evaluated on the live
path despite the requirement naming it. And of the seven eligible records only
three have working adapters; `ecmwf_opendata.py` and `dwd_icon.py` both raise
`AdapterUnavailable` unconditionally. **VERIFIED.**

### 5.2 The substantive argument, not just the bug

A bug is a reason to fix, not to remove. The reason to remove is separate and
holds even with the gate repaired.

An ensemble mean is a smoothed field. Averaging members damps exactly the
sharp gradients and small features that a 2.5 km regional model exists to
resolve, so a blend of HRDPS with a coarse global mean is smoother than
HRDPS alone while carrying HRDPS's name in its provenance. The verification
literature is consistent that an ensemble's contribution is its distribution,
and that collapsing it to a single deterministic number discards the spread
that is the actual product; treating the mean as a deterministic forecast is
the specific thing that literature warns against, because the spread-error
relationship is nonlinear and the probability of large error grows with
spread. **REPORTED** — the spread-skill papers were identified through search
and their abstracts summarised, not read in primary form. No number is
attributed to them here.

The project-internal argument is stronger and is **VERIFIED** by this stack's
own rules. Hard-won fact 9 already records that HRDPS `TCDC` and GFS `TCDC`
are not the same quantity: one is opacity-weighted, the other a geometric
overlap fraction. Section 6 below adds that GEFS `TCDC` is a six-hour average.
A mean over quantities that are not the same quantity is not a better estimate
of anything. Consensus was averaging temperature only, where the comparison is
more defensible, but the machinery invited extension to fields where it is
not.

And the governing rule points the same way. "Nothing is displayed or returned
that was not actually retrieved." A blended mean is a value no centre issued.
It survives only as an explicitly carved-out exception, and the owner's
judgment on 2026-09-02 was that it never earned one.

### 5.3 What replaces it

Every source that published for the coordinate and time is shown, side by
side, each with its own provenance. The headline slot names one declared
primary, HRDPS, by an explicit ordering rather than a blend. No value is
merged into another's. The three-state fallback ladder and the
`consensus unavailable` badge go away, because there is no longer a higher
option that failed.

This is close to what the response already does. `/point` today already
returns per-source fields for `eccc-hrdps`, `eccc-rdps`, `noaa-gfs`,
`awc-metar-speci` and `noaa-swpc-ovation` and only substitutes a single
consensus temperature in the case that has never occurred. Removing consensus
mostly deletes a branch that has never been taken in production.

---

## 6. Quantity traps

**GEFS total cloud is a six-hour average.** The inventory line reads
`TCDC:entire atmosphere:0-6 hour ave fcst`. This is hard-won fact 7 one
product further along: GFS publishes total cloud twice per lead,
instantaneous under PDT 4.0 and a trailing average under PDT 4.8, and this
stack's adapter deliberately selects the instantaneous record through
`_INSTANTANEOUS_FORECAST`. In the GEFS `pgrb2a` inventory only the averaged
record appears. **VERIFIED** for `pgrb2a` at f006; whether an instantaneous
field exists in `pgrb2b` is open question 3. Until that is settled, GEFS
cloud must not be drawn beside HRDPS or GFS cloud as though it were the same
quantity, and probably must not be drawn at all.

**A provider's ensemble statistic is that provider's own reduction.** GEPS
`ERMEAN` is a mean over ECCC's 21 members computed by ECCC. It is retrieved
evidence. It is not interchangeable with a mean this stack would compute over
GEFS's 31 members, it must never be recomputed here from members, and two
such statistics from different providers must never be combined.

**REPS members carry speed without direction.** `ETA_WSPD` exists,
`ETA_UU`/`ETA_VV` do not. Wind direction is simply absent from the REPS
member set and must be reported absent rather than derived.

**GEPS and GEFS are both 0.5°.** Roughly 37 km at this latitude, against
HRDPS at 2.5 km. An ensemble here is evidence about synoptic uncertainty, not
about the Avalon's fog. **REPORTED** for GEPS resolution, from the MSC readme;
**VERIFIED** for GEFS from the `pgrb2a.0p50` product name.

---

## 7. WeatherNext 2

Availability and access were already catalogued in
`01-atmospheric-nwp-satellite.md` §2 and are not repeated. Three things are
added here, all measured 2026-09-02.

**The complete band list, and the absence in it.** Surface and single-level:
`2m_temperature`, `10m_u_component_of_wind`, `10m_v_component_of_wind`,
`100m_u_component_of_wind`, `100m_v_component_of_wind`,
`mean_sea_level_pressure`, `sea_surface_temperature`,
`total_precipitation_6hr`. On pressure levels from 50 to 1000 hPa:
geopotential, specific humidity, temperature, u and v components, and vertical
velocity. 0.25°, six-hourly initialisations and six-hourly lead steps, 64
members, 15 days. **VERIFIED** from the Earth Engine catalogue entry.

**There is no cloud variable of any kind.** Not total cloud, not layered, not
a fraction. For a map whose subject is cloud this is decisive: WeatherNext
contributes temperature, wind, pressure, humidity and omega, and says nothing
about the field being drawn. It follows that any "cloud cover" an aggregator
advertises for WeatherNext is computed downstream from specific humidity and
temperature by that aggregator's own closure. Such a value would be a
generated field wearing DeepMind's name, and under carve-out (d) it could only
be displayed with a cited construction and a GENERATED disclosure, never
served as provider output.

**The licence splits on valid time, not on run age.** Quoted verbatim from the
Earth Engine terms: Historic Experimental Data is "any data that relates to a
time that is more than 48 hours ago"; Real-Time Experimental Data is "any data
that relates to a time that is no more than 48 hours in the past". Because a
forecast for tomorrow relates to a time that is not in the past at all, **every
forward-looking value falls in the Real-Time tier**, under the DeepMind
Real-Time Weather Forecasting Experimental Data Terms, which are separate,
revocable and restrict redistribution and proxying. Only Historic data is CC
BY 4.0. **VERIFIED** for the definitions.

A caution on that reading. Google's own pages carry a second, looser gloss
describing the split as forecasts "generated within past 48 hours", which is
run-age language and would classify an old run's future portion differently.
The two readings disagree on that one case. The authoritative text is the
terms PDF, which was not retrieved. **UNREAD.** Under either reading the
freshest forecast is restricted, so the conclusion for a live map is
unaffected.

Required citation for the Historic tier, verbatim: "© 2025 DeepMind
Technologies Limited's machine learning models used to create the experimental
data made available at [dataset URL] under CC BY 4.0 licence terms. This data
is intended for experimental modelling only and is not intended, validated, or
approved for real world use."

**What the Historic tier is good for.** The interpolation harness already
works by holding out real frames and scoring reconstructions against them.
Past-valid data under a clear Creative Commons licence is exactly the
substrate for an independent yardstick, and it never touches the live map. The
64-member ensemble is genuinely strong; it is simply strong at a scale, a
cadence and a variable set that this particular map does not draw.

---

## 8. Open questions

1. ~~How many members does GEFS actually publish?~~ **CLOSED 2026-09-02,
   verified live.** 31: `gec00` plus `gep01` through `gep30`, counted by
   paging the full S3 listing for one cycle. The AWS Open Data registry page
   saying 21 is stale and describes GEFS v11.
2. Does GeoMet WCS return a usable Avalon subset per REPS member, at what byte
   cost and at what latency? 1239 member coverages exist; none has been
   fetched. A 21-member ingest through 21 separate WCS requests per variable
   per lead may be prohibitive, and `geomet-wms-access` already budgets
   upstream calls per request and per process.
3. Is there an instantaneous total cloud field in GEFS `pgrb2b`, or is the
   six-hour average the only one GEFS publishes? Decides whether GEFS cloud
   is drawable at all.
4. Can ECMWF open-data discovery be fixed? `data.ecmwf.int/forecasts/` answers
   200 with an ECPDS portal rather than the dated cycle tree the adapter
   assumes, and both ECMWF adapters currently refuse unconditionally. Two of
   the five registered ensembles are behind this.
5. Is GEPS retrievable over MetPX Sarracenia (AMQP), the one open ECCC route
   not probed? The registry's own integration string already names it.
6. Once members are stored, what does a member-aware render mean? Spaghetti,
   spread shading and a member selector are three different products, and the
   interface currently asserts it offers none of them.

---

## 9. What this implies for the spec

Recorded here so the openspec change has its evidence, not as a requirement
itself. The normative text lives in
`openspec/changes/ensemble-members-and-source-plurality/`.

- Consensus is removed rather than repaired. Every source that published is
  shown side by side; the headline is a declared ordering with HRDPS first.
- Two ingest shapes are needed, not one, because the providers differ: store
  every member where the provider publishes members (GEFS, REPS); store the
  provider's own statistics as retrieved where it does not (GEPS).
- The decoder must stop deleting `number`, and the sampler must refuse a
  member dimension it was not asked about rather than returning null.
- Member completeness must be reported, not assumed. A partial ensemble is
  published as partial with the missing members named.
- The registry must declare, per ensemble record, which of the two shapes
  applies, so the adapter is not left to guess.
