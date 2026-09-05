Non-normative research, 2026-09-02. Not a spec, not an admission decision.

# Ensemble member access, sizes and instantaneous cloud records

Answers wayfinder ticket
[#13](https://github.com/TusharSariya/Astraeus/issues/13): for each catalogued
ensemble family, how members are retrieved, what one lead time subset to the
evidence box (45.0 to 50.5 N, 58.0 to 46.0 W) weighs, and whether an
instantaneous total-cloud record exists.

Extends the ensemble facts already in
`experiments/st-johns-weather-map/openspec/config.yaml` (31 GEFS members, 21
REPS members, zero GEPS members, GEFS `pgrb2a` total cloud is a time average,
nothing in this stack understands a member) rather than re-deriving them.
Reuses the REPS and GEPS findings and the working WCS request shape from
`docs/research/wayfinder/geomet-wcs-inventory.md` on branch
`research/geomet-wcs-inventory`. No statistics were computed, nothing was
published to the store, no registry state changed.

Every "verified live" number below is one HTTP call made on 2026-09-02 against
the `20260901` `00z` run.

---

## 1. Summary

| Family | Members | Access | Instantaneous total cloud | Wire cost, one member, one field, one lead |
| --- | --- | --- | --- | --- |
| NOAA GEFS | 31 (`gec00` + `gep01`-`gep30`) | S3 GRIB2, `.idx` byte ranges | **no** (column TCDC is a 3 h / 6 h average) | 74 KB - 1.0 MB (whole global record) |
| ECMWF IFS ENS | 51 (50 `pf` + control) | data.ecmwf.int GRIB2, `.index` byte ranges | **yes** (`tcc`, PDT 4.1) | ~0.57 MB (whole global record) |
| ECMWF AIFS-ENS | 51 (50 `pf` + separate `cf` file) | data.ecmwf.int GRIB2, `.index` byte ranges | **yes** (`tcc` + `lcc`/`mcc`/`hcc`, PDT 4.1) | ~1.41 MB (whole global record) |
| ECCC REPS | 21 | GeoMet WCS `GetCoverage`, per member coverage | **yes** (`ETA_NT`), instantaneous per docs | **40 224 B, already subset to the box** |
| ECCC GEPS | **0** | GeoMet WCS, reductions only | n/a — no members exist | ~1.5 KB per reduction, subset to the box |

The one structural difference that matters for storage: **GeoMet WCS subsets
server side; S3 and data.ecmwf.int do not.** A byte range against GRIB2 buys a
whole global field and the box is cut locally afterwards. At 0.5 deg the box is
25 x 12 = 300 cells (~1.2 KB float32); at 0.25 deg it is 49 x 23 = 1 127 cells
(~4.5 KB float32). So for the S3 and ECMWF families the *stored* size is
negligible and the *retrieved* size is three orders of magnitude larger. Any
admission decision for these families is a bandwidth decision, not a disk one.

---

## 2. NOAA GEFS

**Access path.** `https://noaa-gefs-pds.s3.amazonaws.com/gefs.<YYYYMMDD>/<HH>/atmos/<set>/<member>.t<HH>z.<set>.<res>.f<LLL>`
with a `.idx` sidecar beside each file, in the same shape
`ingest/adapters/noaa_s3.py` already uses for deterministic GFS
(`select_gfs_ranges` over the `.idx`, then HTTP `Range`). Verified live: a
`Range` request for one record returned **206, 73 961 bytes, 0.42 s**, starting
with the `GRIB` magic. Three product sets exist and only three:
`pgrb2ap5` (0.5 deg, primary), `pgrb2bp5` (0.5 deg, secondary),
`pgrb2sp25` (0.25 deg, reduced field set). *Verified live.*

**Members.** 31: `gec00` (control) plus `gep01`-`gep30`; `gep30` f384 answers
200. Matches the config fact. *Verified live (spot checks); count from
config.yaml.*

**Cadence and reach.** Four cycles a day (`00`, `06`, `12`, `18` all present as
S3 prefixes). Leads are **3-hourly to f240, then 6-hourly to f384**: f003 and
f246 answer 200, f243 and f381 are 404. Reach **16 days**. *Verified live.*

**Fields.** `pgrb2a` f024 has 85 records per member, `pgrb2b` 505,
`pgrb2s` 38. RH is on 10 pressure levels plus 2 m in `pgrb2a`, on a further 21
levels plus 4 hybrid levels in `pgrb2b`. *Verified live.*

**Instantaneous total cloud: no.** This closes the "unverified" clause in
`config.yaml`.

- `pgrb2a`: `TCDC:entire atmosphere` is a time average at every lead —
  `0-3 hour ave fcst` at f003, `0-6` at f006, `6-12` at f012, `18-24` at f024,
  `234-240` at f240, `378-384` at f384. So the averaging window is 3 h for the
  first step of each 6 h block and 6 h thereafter; it is never instantaneous.
- `pgrb2b`: the layered cloud is *also* averaged —
  `TCDC:low cloud layer`, `middle`, `high` and `boundary layer cloud layer` are
  all `18-24 hour ave fcst` at f024, as are the low/middle/high cloud
  bottom/top pressures and top temperatures.
- The only instantaneous cloud records anywhere in GEFS are
  `TCDC:475 mb` (a single isobaric level, not a column),
  `TCDC:convective cloud layer`,
  `HGT:cloud ceiling`, `CWAT:entire atmosphere`, and the convective cloud
  bottom/top pressures. `HGT:cloud ceiling` is also in `pgrb2s` at 0.25 deg.
- Confirmed at the GRIB2 level, not only from the `.idx` label: the fetched
  `TCDC:475 mb` record decodes to **product definition template 4.1**
  ("individual ensemble forecast … at a point in time"), category 6 number 1.

*Verified live.* Practical consequence: GEFS gives no member-level
instantaneous cloud column to draw beside HRDPS or GFS. `HGT:cloud ceiling`
and `CWAT` are the instantaneous member-level cloud proxies it does offer.

**Sizes.** Whole files, member `gep01`, f024:

| Set | Resolution | Bytes | 
| --- | --- | --- |
| `pgrb2a` (`gec00`) | 0.5 deg | 15 239 806 |
| `pgrb2a` (`gep01`) | 0.5 deg | 15 443 130 |
| `pgrb2b` (`gep01`) | 0.5 deg | 102 271 296 |
| `pgrb2s` (`gep01`) | 0.25 deg | 17 766 559 |

Single-record byte ranges, from the f024 `.idx` (record start to next record
start), which is the realistic per-field wire cost:

| Record | Set | Bytes |
| --- | --- | --- |
| `RH:850 mb` | `pgrb2a` 0.5 deg | 247 106 |
| `TCDC:entire atmosphere` (18-24 h ave) | `pgrb2a` 0.5 deg | 174 309 |
| `TCDC:475 mb` (instantaneous) | `pgrb2b` 0.5 deg | **73 961, fetched** |
| `HGT:cloud ceiling` | `pgrb2s` 0.25 deg | 1 029 967 |

Across 31 members that is **~7.7 MB per field per lead** for a 0.5 deg
`pgrb2a` record, **~2.3 MB** for the instantaneous 475 mb cloud, and
**~32 MB** for the 0.25 deg cloud ceiling. Stored after subsetting: 300 cells
(~1.2 KB) or 1 127 cells (~4.5 KB) per member per field per lead. *Verified
live for the byte figures; the multiplication is arithmetic, not a measurement.*

**Licence.** NOAA Open Data Dissemination; US Government work, no
restrictions on use or redistribution, attribution requested. *Documentation.*

---

## 3. ECMWF IFS ENS (`enfo`)

**Access path.**
`https://data.ecmwf.int/forecasts/<YYYYMMDD>/<HH>z/ifs/0p25/enfo/<YYYYMMDDHHMMSS>-<L>h-enfo-ef.grib2`
with a `.index` sidecar of one JSON object per record carrying `_offset` and
`_length`, so byte-range access works exactly as in
`ingest/adapters/ecmwf_opendata.py` (`parse_ecmwf_index`) — that adapter
already targets `https://data.ecmwf.int/forecasts` and only needs the
`number` field added to its selector. Verified live: a `Range` fetch of one
`tcc` record returned the exact `_length` and the `GRIB` magic. *Verified
live.*

**Members: 51.** The `ef` file carries `type=pf` with `number` 1-50; the
control is not in this file as a separate `cf` type at this step. Treat the
family as 50 perturbed plus one control and confirm the control's location
before ingesting. Also published: `enfo-ep` probability files (4 per run) —
provider reductions, retrieved evidence, never to be recombined here.
*Verified live for the 50 `pf`; the control's file is **unverified**.*

**Resolution.** 0.25 deg regular lat/lon global (1440 x 721). *Verified live
(record sizes and index metadata).*

**Cadence and reach.** 85 distinct lead files per run, 3-hourly to 144 h then
6-hourly to **360 h = 15 days**. Run cycles `00z` and `12z` carry the full ENS;
`06z`/`18z` short cuts are **unverified**. *Verified live for the lead set.*

**Fields.** 48 parameters at f024, 8 500 records per lead file. Surface:
`2t`, `2d`, `10u`, `10v`, `100u`, `100v`, `10fg`, `msl`, `sp`, `skt`, `tp`,
`tprate`, `sf`, `ro`, `sd`, `asn`, `rsn`, `ptype`, `mucape`, `mn2t3`, `mx2t3`,
`tcw`, `tcwv`, **`tcc`**, `ssr`, `ssrd`, `str`, `strd`, `ttr`, `ewss`, `nsss`,
`lsm`, `sithick`, `zos`, `sot`, `vsw`, `sve`, `svn`, `fscov`. Pressure levels:
`t`, `u`, `v`, `w`, `q`, `r`, `gh`, `d`, `vo` on **14 levels** (10, 50, 100,
150, 200, 250, 300, 400, 500, 600, 700, 850, 925, 1000 hPa). Note **`u` and
`v` are present** — unlike REPS, ENS gives member wind direction. *Verified
live.*

**Instantaneous total cloud: yes.** `tcc` decodes to **product definition
template 4.1**, parameter category 6 number 192 (ECMWF local total cloud
cover), i.e. an individual ensemble member at a point in time. No layered
cloud (`lcc`/`mcc`/`hcc`) in the open-data ENS set. *Verified live.*

**Sizes.** The whole f024 `ef` file is **6 660 995 555 bytes** (6.2 GiB) — all
50 members, all 48 parameters. Per member per lead, `tcc` is
**562 984 to 576 855 bytes**; across 51 members ~29 MB per lead for one field.
Stored after subsetting to the box: 1 127 cells, ~4.5 KB per member per field
per lead. *Verified live.*

**Licence.** ECMWF real-time open data, CC BY 4.0, attribution to ECMWF.
*Documentation.*

---

## 4. ECMWF AIFS-ENS (`aifs-ens`)

**Access path.**
`https://data.ecmwf.int/forecasts/<YYYYMMDD>/<HH>z/aifs-ens/0p25/enfo/<stamp>-<L>h-enfo-{pf,cf}.grib2`
plus `.index` sidecars — same byte-range mechanics as ENS. Unlike IFS ENS the
control is a **separate `cf` file**. *Verified live.*

**Members: 51.** `pf` carries `number` 1-50 (5 400 records at f024); `cf` is
the control in its own file. *Verified live.*

**Resolution.** 0.25 deg global. **Cadence and reach:** 61 lead files,
6-hourly to **360 h = 15 days**. Also 4 `enfo-ep` probability files per run.
*Verified live.*

**Fields.** 29 parameters. Surface: `2t`, `2d`, `10u`, `10v`, `100u`, `100v`,
`msl`, `sp`, `skt`, `tp`, `cp`, `sf`, `ssrd`, `strd`, `tcw`, `rowe`, `fscov`,
`sot` (2 levels), `vsw` (2 levels), and cloud: **`tcc`, `lcc`, `mcc`, `hcc`**.
Pressure levels: `t`, `u`, `v`, `w`, `z` on 14 levels and `q` on 13.
*Verified live.*

**Instantaneous total cloud: yes, and layered cloud too.** `tcc` decodes to
**PDT 4.1**, category 6 number 1 (WMO total cloud cover). This is the only
catalogued family that publishes per-member **low, middle and high** cloud —
worth noting against the `geomet-wcs-inventory` finding that no ECCC model on
GeoMet publishes layered cloud or cloud base at all. *Verified live for `tcc`;
`lcc`/`mcc`/`hcc` presence is verified live, their PDT is **unverified**.*

**Sizes.** f024: `pf` **4 464 482 453 bytes** (4.16 GiB, 50 members),
`cf` **88 692 144 bytes**. Per member per lead, `tcc` is
**1 400 784 to 1 448 560 bytes** — about 2.5x the IFS ENS record, because the
AIFS field packs less compressibly. Across 51 members ~72 MB per lead for one
field. Stored after subsetting: ~4.5 KB per member per field per lead.
*Verified live.*

**Licence.** ECMWF real-time open data, CC BY 4.0. AIFS output is a machine
learning model's output and is labelled experimental by ECMWF; it is still
**retrieved** evidence in this deployment's terms — the producer issued it.
*Documentation.*

---

## 5. ECCC REPS

Cited from `docs/research/wayfinder/geomet-wcs-inventory.md` (branch
`research/geomet-wcs-inventory`) rather than repeated: 21 members `.01`-`.21`
across 1 239 `REPS.MEM.*` coverages plus ~534 `REPS.DIAG.*` provider
reductions; 22 `ETA_*` surface fields, `NTAT_EI`, and a `PRES_*` set of `GZ`,
`HR`, `TT` on 9 pressure levels plus `TT`, `HU`, `WSPD` at 40/80/120 m;
**wind speed only, no u/v on any member**, so member wind direction is not
retrievable. The 2026-09-02 probe requested `SCALESIZE=long(133),lat(61)`;
section 7 corrects the earlier native-resolution interpretation.

**Access path.** GeoMet WCS 2.0.1, the request shape established in that file
(`FORMAT` mandatory, `SUBSET` not `BBOX`), one coverage per member per field.
The corrected request declares the geographic subsetting CRS and treats
`SCALESIZE` as an output shape:

```
https://geo.weather.gc.ca/geomet
  ?SERVICE=WCS&VERSION=2.0.1&REQUEST=GetCoverage
  &COVERAGEID=REPS.MEM.ETA_NT.01
  &FORMAT=image/tiff
  &SUBSETTINGCRS=http://www.opengis.net/def/crs/EPSG/0/4326
  &SUBSET=long(-58,-46)
  &SUBSET=lat(45,50.5)
  &SCALESIZE=long(133),lat(61)
```

**One bounded call made for this ticket** (the only upstream call to GeoMet
here): **200, `image/tiff`, 40 224 bytes, 0.31 s**, little-endian TIFF magic.
*Verified live.*

**Instantaneous total cloud: yes.** `ETA_NT` is total cloud cover on the
member, and it is the field that answered above. GeoMet returns GeoTIFF, which
carries no GRIB product definition template, so the instantaneous quality is
**documentation, not verified live** — ECCC's `NT` diagnostic is a snapshot at
the valid time, unlike GEFS's averaged column. Confirm against the source GRIB
before drawing it beside HRDPS.

**Size in the box.** **40 224 bytes per member per field per lead**, already
subset server side — this is the true stored size, not a global field to be cut
down. Across 21 members: **~845 KB per field per lead**. That is the whole
retrieval cost, and it is the cheapest per-member cloud field of any family
here by two orders of magnitude. (The `geomet-wcs-inventory` figure of ~33 KB
is the same measurement at float32 without TIFF overhead; 40 224 B is what the
wire actually carried.) *Verified live.*

**Cadence and reach.** REPS runs 4 times a day out to 72 h, 3-hourly.
*Documentation — the run cycles and lead set were **not** enumerated here.*

**Licence.** Open Government Licence - Canada 2.0, attribution to Environment
and Climate Change Canada. *Documentation.*

**Still dead on Datamart.** The `config.yaml` fact that REPS is 404 on every
open ECCC HTTP path holds for `dd.weather.gc.ca` and hpfx; GeoMet is where it
moved. Not re-probed for this ticket.

---

## 6. ECCC GEPS

**No members exist.** Cited from `geomet-wcs-inventory.md`: 532 coverages,
**zero `GEPS.MEM.*`**, everything published is a provider reduction
(`ERMEAN`, `ERSSTD`, percentiles `ERC0`-`ERC100`, threshold probabilities).
`GEPS.DIAG.3_TT.ERC50` subset to the box is 1 474 bytes at native 0.5 deg
(`SCALESIZE=long(24),lat(11)`). Nothing about members changed on this ticket;
GEPS answers the "how are members retrieved" question with "they are not
published anywhere reachable".

Consequence for this ticket's scope: **GEPS cannot supply a member-level cloud
field.** Its reductions are retrieved evidence, stored as issued, never
recombined and never mixed with a statistic over a different member set.
*Cited, not re-verified.*

---

## 7. What this leaves open

- **The IFS ENS control member's file.** 50 `pf` members were enumerated; where
  the `cf` control lives in the `ifs/0p25/enfo` layout was not established.
  Unverified.
- **ECMWF `06z`/`18z` ENS coverage.** Only the `00z` run was listed.
  Unverified.
- **REPS run cycles and lead set.** Cited from documentation, not enumerated.
- **Whether `ETA_NT` is genuinely instantaneous.** GeoTIFF carries no PDT;
  needs the source GRIB or an ECCC field definition to confirm.
- **`lcc`/`mcc`/`hcc` PDT on AIFS-ENS.** Present, not decoded.
- **Member identity end to end.** Independent of any source: `ingest/grib.py`
  still drops `number` at decode and `Provenance.member` has never been set by
  any adapter (`config.yaml`, 2026-09-02). Every access path above is useless
  until that is fixed; this ticket does not fix it.
- **No statistics were computed, no artifact published, no registry state
  changed.**

---

## 7. 2026-09-05 live integration update

Issue 83 re-enumerated the live GeoMet WCS before acquisition. The service
still advertises 1,239 `REPS.*` coverages and 532 `GEPS.*` coverages. REPS has
21 coverages for each selected surface field and exact pressure identifiers at
50, 100, 200, 250, 500, 700, 850, 925 and 1000 hPa for HR and GZ (TT also has
40/80/120 m coverages). GEPS advertises zero `GEPS.MEM.*` coverages.

`DescribeCoverage` changes the geometry interpretation recorded earlier in
this document. REPS reports source CRS EPSG:102990 and 0.09 grid-axis offsets.
The 133 by 61 request over 45–50.5 N, 58–46 W is an explicitly requested
EPSG:4326 output grid, resampled by GeoMet with an undocumented method. Without
`SUBSETTINGCRS=EPSG:4326`, GeoMet returns plausible TIFFs containing zeros for
this geographic box because the subset coordinates are interpreted in the
rotated source CRS. With the subsetting CRS declared, all 21 members return
non-constant numeric cloud and wind grids. The retained artifact and exact
counts are in
`experiments/st-johns-weather-map/docs/evidence/eccc-ensemble-2026-09-05.json`.

The current WMS title labels `REPS.MEM.*.01` as `[control member]`. That is new
source evidence, but this experiment does not change the registry's unresolved
control identifier or flag member 01 as control. Owner/spec resolution remains
required before that behavior can enter an admitted path.

GEPS live capabilities advertise 00/12 UTC runs, three-hour instantaneous
steps through 384 hours, and coarser valid-time axes for windowed products. The
integration retained issued mean, standard deviation, percentile and threshold
probability coverages separately. It created no members and computed no
statistics. The documented Datamart paths remain dead and were not used.
