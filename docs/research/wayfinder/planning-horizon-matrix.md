Non-normative research, 2026-09-02. Not a spec, not an admission decision.

# Planning-window source matrix for the 14-day horizon

Answers wayfinder ticket
[#15](https://github.com/TusharSariya/Astraeus/issues/15): for every
deterministic and ensemble product that reaches beyond 48 hours, its reach in
hours per run cycle, run cadence, publication latency, grid resolution over the
evidence box (45.0 to 50.5 N, 58.0 to 46.0 W), whether total cloud, cloud by
layer, relative humidity, precipitable water and 10 m wind are published, and
the licence that governs forward-looking data.

Written so the horizon-tier decision (`CONTEXT.md`: core window 3 h back to
24 h ahead at full fidelity, planning window to 14 days ahead from global
products) can assign feeders without re-checking.

Reuses rather than repeats:

- `docs/research/wayfinder/geomet-wcs-inventory.md` (branch
  `research/geomet-wcs-inventory`) for the GeoMet WCS request shape, the
  absence of layered cloud and cloud base anywhere on GeoMet, and the GEPS
  reduction inventory.
- `docs/research/wayfinder/ensemble-access.md` (branch
  `research/ensemble-access`) for GEFS, IFS ENS, AIFS-ENS, REPS and GEPS
  member counts, access paths, cloud records and wire sizes. This file adds
  only the cadence and latency those entries lacked.
- `experiments/st-johns-weather-map/openspec/config.yaml` for the GFS
  instantaneous-versus-average duplicate trap, the GFS mixed-phase versus ECCC
  liquid-water RH difference, the HRDPS/GFS total-cloud incomparability, the
  GEFS averaged cloud column and the WeatherNext 2 licence split.
- `experiments/st-johns-weather-map/registry/source_data.py` for each record's
  declared state, endpoints and policy block.

Every cell marked **verified live** rests on an HTTP call made on 2026-09-02
between 05:15 and 05:35 UTC against the `20260901` or `20260902` runs.
**Documentation** means a producer's own statement, not a call made here.
**Unverified** means neither. No statistics were computed, nothing was
published to the store, no registry state changed.

---

## 1. Matrix

Products are grouped deterministic first, then ensemble. Reach is per run
cycle; where cycles differ, both are given.

| Product | Reach | Cadence | Latency | Resolution over the box | Total cloud | Cloud by layer | Relative humidity | Precipitable water | 10 m wind | Licence (forward-looking) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **NOAA GFS** `noaa-gfs` | **384 h**, hourly to f120 then 3-hourly (f121 and f241 are 404, f387 is 404) — *verified live* | 00/06/12/18 UTC — *verified live* (`gfs.20260902/00` present at 05:21 UTC) | 00z `f000` **T+3 h 35 m**, `f024` T+3 h 44 m, `f120` T+4 h 12 m, `f240` T+4 h 39 m, `f384` **T+5 h 18 m** — *verified live* (S3 `Last-Modified`) | 0.25 deg global, **49 x 23 = 1 127 cells** in the box — *verified live* | **yes**, `TCDC:entire atmosphere`, instantaneous *and* a trailing average at every lead — *verified live* | **yes**, `LCDC`/`MCDC`/`HCDC`, again instantaneous plus a trailing average — *verified live* | **yes**, `RH:2 m` and 30+ isobaric levels; **mixed phase** — *verified live* (phase from `config.yaml`) | **yes**, `PWAT:entire atmosphere` — *verified live* | **yes**, `UGRD`/`VGRD:10 m` — *verified live* | NOAA Open Data, US Government work, no restriction, attribution requested — *documentation* |
| **ECCC GDPS** `eccc-gdps` (GeoMet) | **240 h**, 137 steps: hourly to +84 h then 3-hourly — *verified live* (WMS `GetCapabilities` time dimension) | 2 runs/day, 00/12 UTC — *documentation*, corroborated live (00z cloud beside a 12z humidity layer) | **not uniform across layers.** At 05:21 UTC `TotalCloudCover` and `WindSpeed_10m` were already on the 2026-09-02 00z run (**< T+5 h 21 m**) while `RelativeHumidity_2m` and `RelativeHumidity_850mb` were still on the 2026-09-01 12z run — *verified live* | 15 km GeoMet grid; one `GetCoverage` for the box returned **12 266 B** GeoTIFF in 0.30 s at server default scaling (native needs `SCALESIZE`, per `geomet-wcs-inventory`) — *verified live* | **yes**, `GDPS_15km_TotalCloudCover` — *verified live* | **no.** No `GDPS_*Cloud*` layer coverage of any kind; only `CloudWater_EAtm`. Confirms the `geomet-wcs-inventory` finding for the global model too — *verified live* | **yes**, `RelativeHumidity` on isobaric levels and `RelativeHumidity_2m`. Phase **unverified** for GDPS (`config.yaml` establishes liquid-water phase for HRDPS/RDPS only) | **no.** No precipitable-water or total-column-water-vapour coverage exists under `GDPS_*` — *verified live* | **yes**, but as `WindSpeed_10m` + `WindDir_10m`; **no u/v component coverage**, same shape as REPS — *verified live* | Open Government Licence - Canada 2.0, attribution to ECCC — *documentation* |
| **ECMWF IFS deterministic** `ecmwf-ifs` | **360 h** at 00z/12z (85 files, 3-hourly to 144 h then 6-hourly; 361 h and 366 h are 404); **144 h** at 06z/18z (49 files) — *verified live* | 00/06/12/18 UTC — *verified live* | 01-09-2026 12z `360h` index published **19:34 UTC = T+7 h 34 m**; the 2026-09-02 00z run was still absent at 05:21 UTC (T+5 h 21 m) — *verified live* | 0.25 deg global, **49 x 23 cells** — *verified live* | **yes**, `tcc` — *verified live* | **no.** No `lcc`/`mcc`/`hcc` in the open-data `oper` set — *verified live* | **yes**, `r` on 14 isobaric levels (10 to 1000 hPa). **No 2 m RH**; `2d` dewpoint instead — *verified live* | **yes**, `tcwv` (and `tcw`) — *verified live* | **yes**, `10u`/`10v` (plus `100u`/`100v`) — *verified live* | ECMWF real-time open data, CC BY 4.0 plus ECMWF Terms of Use — *documentation* |
| **ECMWF AIFS single** `ecmwf-aifs-single` | **360 h** at every cycle, 61 files, **6-hourly throughout** — *verified live* (00z and 06z both enumerated) | 00/06/12/18 UTC, all four to full reach — *verified live* | same dissemination slot as IFS; 12z final leads at T+7 h 30 m to T+7 h 40 m — *verified live* | 0.25 deg global, **49 x 23 cells** — *verified live* | **yes**, `tcc` — *verified live* | **yes**, `lcc`/`mcc`/`hcc` — *verified live*. With AIFS-ENS this is the only ECMWF open-data family carrying layered cloud | **no relative humidity at all.** Only `q` on levels; `2d` at the surface — *verified live* | **partial.** `tcw` (total column water, hydrometeors included) but **no `tcwv`** — not the same quantity as GFS `PWAT` or ICON `tqv` — *verified live* | **yes**, `10u`/`10v`, `100u`/`100v` — *verified live* | CC BY 4.0 plus ECMWF Terms of Use; ECMWF labels AIFS experimental. Still **retrieved** evidence — the producer issued it — *documentation* |
| **DWD ICON global** `dwd-icon-global` | **180 h** at 00z/12z (113 steps, hourly to +78 h then 3-hourly); **120 h** at 06z/18z (93 steps) — *verified live*. **Does not reach 14 days** | 00/06/12/18 UTC — *verified live* | **the fastest here.** 00z `CLCT` `000` published **02:43:59 UTC = T+2 h 44 m**, `180` at **03:31:55 = T+3 h 32 m** — *verified live* | **icosahedral R03B07 (~13 km) native, not lat/lon.** No regular-lat-lon variant is published for the global model; regridding needs DWD's own `ICON_GLOBAL2WORLD_0125_EASY` / `_025_EASY` weight archives, which exist — *verified live*. At 0.125 deg the box is 97 x 45 cells | **yes**, `clct` (and `clct_mod`) — *verified live* | **yes**, `clcl`/`clcm`/`clch`, plus `clc` on model levels and `hbas_con`/`htop_con`/`hzerocl` — *verified live* | **yes**, `relhum` on **18 isobaric levels** (30 to 1000 hPa) and `relhum_2m` — *verified live*. Phase **unverified** | **yes**, `tqv` (total column water vapour); `tqc`/`tqi`/`tqr`/`tqs` also published — *verified live* | **yes**, `u_10m`/`v_10m`, plus `vmax_10m` gust — *verified live* | DWD open data / GeoNutzV, free use with attribution to Deutscher Wetterdienst and preserved product metadata — *documentation* (registry policy block, `review_state: verified`) |
| **Google WeatherNext 2** `google-weathernext-2` | **15 days**, 6-hourly — *documentation* (registry, Earth Engine catalogue read 2026-09-02) | **unverified.** Registry records "official dataset-dependent" | **unverified.** Registry: "to be established by live latency audit". Not probed here: the record is `credential_required` and access needs a reviewed Google data request | 0.25 deg global, **49 x 23 cells** — *documentation* | **no. Publishes no cloud variable of any kind** — *documentation* (`config.yaml`, verified band list 2026-09-02). Any "cloud cover" a reseller offers for it is that reseller's humidity closure, a **generated** value under carve-out (d) | **no** — *documentation* | **no relative humidity.** Specific humidity on 50-1000 hPa only — *documentation* | **no** — *documentation* | **yes**, 10 m and 100 m winds — *documentation* | **restricted for every forward-looking value.** The licence splits on **valid time**: only data relating to a time more than 48 h in the past is CC BY 4.0; a forecast for a future instant is never in that tier, so all planning-window data sits under the revocable GDM Real-Time Experimental Data Terms, which restrict redistribution and proxying — *documentation* (`config.yaml`, registry `review_state: restricted`) |
| **NOAA GEFS** `noaa-gefs` (31 members) | **384 h**, 3-hourly to f240 then 6-hourly — *verified live in `ensemble-access`* | **00/06/12/18 UTC** — *verified live (this ticket)*, all four prefixes present | 00z `gep01` `f024` **T+3 h 57 m**; `f384` still absent at 05:21 UTC (**> T+5 h 21 m**) — *verified live (this ticket)* | 0.5 deg `pgrb2a`/`pgrb2b` (**25 x 12 = 300 cells**); 0.25 deg `pgrb2s` (49 x 23) — *from `ensemble-access`* | **no instantaneous column.** `TCDC:entire atmosphere` is a 3 h / 6 h **average** at every lead — *verified live in `ensemble-access`, re-confirmed here at f240* | **no** usable one: `LCDC`/`MCDC`/`HCDC` are averages too. Instantaneous cloud proxies are `HGT:cloud ceiling`, `CWAT`, `TCDC:475 mb` — *from `ensemble-access`* | **yes**, `RH:2 m` and 10 isobaric levels in `pgrb2a`, 21 more plus hybrid levels in `pgrb2b`; **mixed phase** like GFS — *verified live* | **yes**, `PWAT:entire atmosphere` in `pgrb2a` — *verified live (this ticket)* | **yes**, `UGRD`/`VGRD:10 m` in `pgrb2a` — *verified live (this ticket)* | NOAA Open Data, US Government work — *documentation* |
| **ECMWF IFS ENS** `ecmwf-ens` (51 members) | **360 h** at 00z/12z (85 lead files, 3-hourly to 144 h then 6-hourly); **144 h** at 06z/18z (49 files) — *verified live (this ticket; `ensemble-access` left the off-cycles unverified)* | 00/06/12/18 UTC, full reach only at 00z/12z — *verified live (this ticket)* | 01-09-2026 12z `360h` index published **19:40 UTC = T+7 h 40 m** — *verified live (this ticket)* | 0.25 deg, **49 x 23 cells** stored per member; ~29 MB on the wire per lead for one field across 51 members — *from `ensemble-access`* | **yes**, instantaneous `tcc`, PDT 4.1 — *verified live in `ensemble-access`* | **no** — *from `ensemble-access`* | **yes**, `r` on 14 levels — *from `ensemble-access`* | **yes**, `tcwv` and `tcw` — *from `ensemble-access`* | **yes**, `10u`/`10v` — member wind **direction** available, unlike REPS — *from `ensemble-access`* | CC BY 4.0 plus ECMWF Terms of Use — *documentation* |
| **ECMWF AIFS-ENS** `ecmwf-aifs-ens` (51 members) | **360 h**, 61 lead files, 6-hourly — *verified live in `ensemble-access`* | 00/06/12/18 UTC, full reach at every cycle (06z enumerated here: 61 files) — *verified live (this ticket)* | 01-09-2026 12z `360h` `pf` index published **19:40 UTC = T+7 h 40 m** — *verified live (this ticket)* | 0.25 deg, **49 x 23 cells** stored; ~72 MB on the wire per lead per field across 51 members — *from `ensemble-access`* | **yes**, instantaneous `tcc`, PDT 4.1 — *verified live in `ensemble-access`* | **yes**, `lcc`/`mcc`/`hcc` — **the only ensemble family with per-member layered cloud** — *verified live in `ensemble-access`* (their PDT unverified) | **no.** `q` only — *from `ensemble-access`* | **partial**, `tcw` only, no `tcwv` — *from `ensemble-access`* | **yes**, `10u`/`10v` — *from `ensemble-access`* | CC BY 4.0 plus ECMWF Terms of Use; experimental label — *documentation* |
| **ECCC GEPS** `eccc-geps` (0 members) | **384 h** (`2026-09-01T15Z/2026-09-17T12Z/PT3H` on the 12z run), 3-hourly — *verified live* | 2 runs/day, 00/12 UTC — *documentation*; at 05:21 UTC the newest GEPS on GeoMet was still the previous 12z run | **bounded from below only.** At 05:21 UTC GeoMet still advertised the **2026-09-01 12z** run, so the 2026-09-02 00z GEPS was not published at **T+5 h 21 m** — *verified live*; the publication instant itself was not measured | 0.5 deg; box is `SCALESIZE=long(24),lat(11)` = **24 x 11 cells**, ~1.5 KB per reduction — *from `geomet-wcs-inventory`* | **yes, as reductions only**: `GEPS.DIAG.3_NT.{ERMEAN,ERSSTD,ERC0..ERC100}` — *verified live* | **no** — *verified live* | **no relative humidity in any reduction.** The humidity-adjacent field is `3_HMX`/`24_HMXX` (humidex) — *verified live (this ticket)* | **no** — *verified live* | **yes, as reductions only**: `3_WSPD.*` speed and gust probabilities; **no direction, no u/v** — *verified live* | Open Government Licence - Canada 2.0 — *documentation* |
| **ECCC REPS** `eccc-reps` (21 members) | **72 h — below this ticket's 48 h+ planning threshold and well short of 14 days.** Listed for completeness — *documentation* | 4 runs/day — *documentation*, lead set not enumerated | **unverified** | 10 km; `SCALESIZE=long(133),lat(61)`, **40 224 B per member per field per lead already subset server side** — *from `ensemble-access`* | **yes**, `ETA_NT` per member; instantaneous per docs, unconfirmed at GRIB level (GeoTIFF carries no PDT) — *from `ensemble-access`* | **no** — *from `geomet-wcs-inventory`* | **yes**, `ETA_HR` and `PRES_HR` on 9 levels — *from `geomet-wcs-inventory`* | **no** — *from `geomet-wcs-inventory`* | **speed only**, `ETA_WSPD`; **no u/v, so no member wind direction** — *from `geomet-wcs-inventory`* | Open Government Licence - Canada 2.0 — *documentation* |

---

## 2. Notes

**Only five products actually reach 14 days.** GFS (384 h), GEFS (384 h), GEPS
(384 h), IFS ENS and AIFS-ENS (360 h each), plus IFS deterministic and AIFS
single at 360 h on their 00z/12z cycles. **GDPS stops at 240 h** and **ICON
global stops at 180 h**, so neither can feed the far end of the planning window
however good they are nearer in. WeatherNext 2 claims 15 days but is
credential-blocked and licence-restricted for every forward-looking value.

**Latency splits the field into two clear bands.** ICON is out first (final
lead **T+3 h 32 m**), then GFS (**T+5 h 18 m**) and GEFS; ECMWF's whole
dissemination lands together around **T+7 h 30 m to T+7 h 40 m** for IFS, ENS
and AIFS-ENS alike. Anything scheduled against ECMWF must tolerate a run
roughly four hours older than the ICON run beside it — at day 10 that is
negligible, at hour 24 it is not.

**GDPS layer availability is not atomic.** Total cloud and 10 m wind were on
the newer run while 2 m and 850 hPa relative humidity were a cycle behind, in
one and the same capabilities document. A GDPS fetch that assumes all its
layers share a run reference time will silently mix two runs. Read each
layer's own time dimension.

**Cloud by layer is scarce and asymmetric.** ECCC publishes none anywhere —
not on GDPS, not on GEPS, not on REPS, confirming `geomet-wcs-inventory` for
the global models too. IFS deterministic and IFS ENS publish none. The
products that do are GFS, ICON, **AIFS single** and **AIFS-ENS** — that is, the
machine-learning family and the two American/German deterministic feeds.

**Relative humidity is missing from both AIFS products and from GEPS.** AIFS
carries `q` only, so any RH shown for it would be a **derived-here** value
requiring inputs, method and citation, not a retrieved one. GEPS offers
humidex, which is not humidity.

**Precipitable water has three different quantities hiding under one heading.**
GFS `PWAT` and ICON `tqv` are water vapour. ECMWF `tcwv` is water vapour but
`tcw` is total column water including hydrometeors, and the AIFS products
publish **only `tcw`**. GDPS and the ECCC ensembles publish neither. Do not put
AIFS `tcw` in the same field-catalogue slot as GFS `PWAT`.

**Two cloud-comparability traps already in `config.yaml` reach into this
window.** GFS publishes total and layered cloud **twice per lead** —
instantaneous (PDT 4.0) and a trailing average (PDT 4.8) — and both were
present at f240 here; only the instantaneous record is the declared quantity.
GEFS has no instantaneous column at all. And HRDPS/ECCC opacity-weighted cloud
is not the same quantity as GFS overlap-fraction cloud, so a planning-window
value must not be scored against a core-window one.

**Wind direction is unavailable from every ECCC ensemble product.** GEPS
reductions and REPS members both carry speed without u/v. If the planning
window needs direction from a Canadian ensemble, it does not exist openly.

**The member-identity blocker still governs every ensemble row.** Independent
of any source, `ingest/grib.py` drops `number` at decode and
`Provenance.member` has never been set by any adapter (`config.yaml`,
2026-09-02). Every ensemble access path in this table is unusable until that is
fixed.

**GEPS and REPS remain reachable only through GeoMet**; the Datamart paths are
still 404 and MSC's readme still documents them. Re-probe before relying on any
`dd.weather.gc.ca` path.

---

## 3. A suggested split for the horizon-tier decision

Offered as a starting point for the owner to react to, not a decision.

**Core window (3 h back to 24 h ahead, full fidelity).** Keep it ECCC-led and
fast: HRDPS via GeoMet as primary, RDPS second, REPS for regional spread out to
72 h. From this ticket's set, the only useful additions inside 24 h are **ICON
global** — it is the earliest-published global model here by roughly ninety
minutes over GFS and two and a half hours over ECMWF, and it is the only global
feed carrying layered cloud, 18-level RH and `tqv` together — and **GFS**,
already implemented in `noaa_s3.py`, for its instantaneous total and layered
cloud. Both carry a regridding or duplicate-record cost that the adapter
already knows about (icosahedral weights for ICON, `_INSTANTANEOUS_FORECAST`
for GFS).

**Planning window (to 14 days).** Reach forces the roster:

- **Days 0-7.5 (to 180 h):** ICON global stays available, so the core-window
  feeders can simply keep running. GDPS covers to 240 h with total cloud and
  RH but no layered cloud and no precipitable water.
- **Days 7.5-10 (180-240 h):** ICON is gone. GFS, GDPS, IFS deterministic,
  AIFS single and the ensembles remain.
- **Days 10-15 (240-384 h):** GDPS is gone too. What survives is **GFS**
  (deterministic, layered cloud, PWAT, RH), **IFS deterministic** and **AIFS
  single** to 360 h on 00z/12z only, and the ensembles **GEFS**, **IFS ENS**,
  **AIFS-ENS** to 360-384 h, plus **GEPS** reductions to 384 h.

**Two shapes of evidence in the far tier.** A single deterministic value at day
12 is close to meaningless; the honest planning-window products are the
ensemble distributions and the provider's own reductions. If only one ensemble
family can be afforded, **AIFS-ENS** is the strongest candidate on content — it
is the only family with per-member instantaneous total *and* layered cloud —
and the weakest on bandwidth (~72 MB per field per lead for 51 members, versus
REPS's 40 KB server-side subset). **GEPS reductions are by far the cheapest
14-day cloud evidence available** (~1.5 KB per reduction, 384 h, `3_NT`
percentiles) and are retrieved evidence to be stored as issued, never
recombined.

**A cadence note for the tier boundary.** IFS deterministic, IFS ENS, AIFS
single and AIFS-ENS do not all behave alike across cycles: IFS and IFS ENS give
full reach only at 00z and 12z (144 h at 06z/18z), while both AIFS products
give 360 h at all four. A planning-window refresh keyed to every six hours will
see the ECMWF physical models drop to six days twice a day and the ML models
not.

**What this leaves for the field catalogue.** Three fields in this table are
named alike and are not alike: total cloud (opacity-weighted ECCC versus
overlap-fraction GFS/ICON), relative humidity (GFS/GEFS mixed-phase versus ECCC
liquid-water; GDPS and ICON phase unverified), and precipitable water (`tqv`
and `tcwv` vapour versus AIFS `tcw` total column water). The open question in
issue #5 about a per-field comparability rule beyond phase and unit is answered
here with three concrete cases.

---

## 4. What this leaves open

- **GDPS and ICON relative-humidity phase.** Neither was measured from the
  model's own specific humidity the way `config.yaml` records for HRDPS, RDPS
  and GFS. Until measured, a GDPS or ICON humidity threshold is not
  transferable to or from either.
- **GDPS per-layer run skew.** Observed once, at one instant. Whether it is
  routine, and how large the skew gets, is unmeasured.
- **GEPS and WeatherNext 2 publication latency.** GEPS was only bounded from
  below (00z not present at T+5 h 21 m). WeatherNext 2 was not probed at all;
  it is `credential_required` and the registry still calls for a live latency
  audit.
- **WeatherNext 2 run cadence.** Registry says "official dataset-dependent";
  nothing here narrowed it.
- **GDPS native `SCALESIZE` for the box.** One `GetCoverage` was made at server
  default scaling (12 266 B); the native cell count was not established, unlike
  REPS `long(133),lat(61)` and GEPS `long(24),lat(11)`.
- **AIFS `lcc`/`mcc`/`hcc` product definition template**, deterministic as well
  as ensemble. Present, not decoded.
- **ICON regridding cost.** The weight archives exist; neither their size nor
  the per-field cost of applying them to the box was measured.
- **Whether GFS layered cloud at long leads is worth drawing.** Present at
  f240, quantity unexamined.
- Nothing was computed, published or promoted. Registry states are unchanged.
