Non-normative research, dated 2026-09-02. Findings only; no admission decision, no
registry state, no spec impact. Wayfinder ticket
[#8](https://github.com/TusharSariya/Astraeus/issues/8).

# Space-weather source inventory beyond SWPC

Scope: space-weather observations and forecasts usable for aurora visibility over
the Avalon Peninsula, beyond the three SWPC sources already catalogued
(`noaa-swpc-kp`, `noaa-swpc-rtsw`, `noaa-swpc-ovation` in
`experiments/st-johns-weather-map/registry/source_data.py`).

Every endpoint marked verified was fetched anonymously over HTTPS on 2026-09-02
between roughly 05:30 and 06:10 UTC. Sizes and timestamps are what came back on
that fetch.

## The one thing that changed under the existing catalogue

`noaa-swpc-rtsw` is pinned to `https://services.swpc.noaa.gov/json/rtsw/rtsw_mag_1m.json`
with a comment that "the feed's own source field names the measuring spacecraft".
On 2026-09-02 that field carried **three** values across the 24-hour window, and
**DSCOVR was not one of them**:

| `source` value | records in `rtsw_mag_1m.json` | records in `rtsw_wind_1m.json` |
| --- | --- | --- |
| `SOLAR1` | 1436 | 1390 |
| `ACE` | 1322 | 1312 |
| `IMAP` | 871 | 861 |

`SOLAR1` is SWFO-L1, renamed SOLAR-1 (Space weather Observations at L1 to Advance
Readiness - 1) on arrival at L1 in January 2026; its SWiPS/SWIS suite is NOAA's
stated replacement for the ACE and DSCOVR solar-wind monitoring, and its CCOR
coronagraph is the stated replacement for SOHO LASCO
([NESDIS](https://www.nesdis.noaa.gov/news/swfo-l1-renamed-solar-1-reaches-final-destination-one-million-miles-earth)).
`IMAP` is the Interstellar Mapping and Acceleration Probe, also at L1. Records are
interleaved by instant with an `active` flag; none of the last 24 h of records had
`active: true`, so the consumer must pick a source itself rather than trust a
single primary. `rtsw_wind_1m.json` additionally carries `overall_quality` and
seven `max_*_flag` quality fields the current record does not list.

Consequence for the registry, not decided here: `noaa-swpc-rtsw` stores `bz_gsm`
and `bt` on a bare time axis with no spacecraft identity, while the prior research
in `docs/research/data-sources.md` explicitly calls for storing
"spacecraft/source identity". With three spacecraft now interleaved in one feed
and a per-record quality flag set, that omission is now load-bearing.

## Source table

Cadence and latency are the producer's, or measured where the producer does not
publish one. "New" means not currently in `source_data.py`.

| Source | Producer | Quantity | Endpoint | Format | Cadence | Latency | Licence and redistribution | Verified live | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SWPC RTSW magnetic field | NOAA SWPC (from SOLAR-1, ACE, IMAP) | IMF Bt, Bx/By/Bz GSE and GSM at L1 | `https://services.swpc.noaa.gov/json/rtsw/rtsw_mag_1m.json` | JSON, 1.5 MB / 24 h | 1 min | latest record 1-3 min old | US Government work, public domain, no restriction | yes | catalogued as `noaa-swpc-rtsw`; spacecraft identity and quality flags not stored |
| SWPC RTSW plasma | NOAA SWPC (same three) | proton speed, density, temperature, quality flags | `https://services.swpc.noaa.gov/json/rtsw/rtsw_wind_1m.json` | JSON, 2.6 MB / 24 h | 1 min | latest record 1-3 min old | US Government work, public domain | yes | **new**; the speed/density half of the coupling picture, currently absent |
| SWPC RTSW ephemerides | NOAA SWPC | spacecraft GCI/GSE position | `https://services.swpc.noaa.gov/json/rtsw/rtsw_ephemerides_1h.json` | JSON | 1 h | 1 h | US Government work, public domain | yes | **new**; needed only if propagation delay is computed here |
| SWPC propagated solar wind | NOAA SWPC Geospace | L1 wind propagated to the bow shock, with `propagated_time_tag` | `https://services.swpc.noaa.gov/products/geospace/propagated-solar-wind-1-hour.json` | JSON array-of-arrays | 1 min | ~5 min | US Government work, public domain | yes | **new**; removes the need to derive-here a propagation lag |
| SWPC Geospace Dst | NOAA SWPC (Geospace model) | modelled Dst | `https://services.swpc.noaa.gov/json/geospace/geospace_dst_1_hour.json` | JSON | 1 min | ~5 min | US Government work, public domain | yes | **new**; model output, not an observed index |
| SWPC Geospace predicted Kp | NOAA SWPC | model-predicted K | `https://services.swpc.noaa.gov/json/geospace/geospace_pred_est_kp_1_hour.json` | JSON | nominally 1 min | **stale**: every record timestamped 2024-06-18 | US Government work, public domain | endpoint 200, content stale | **new**; do not admit without re-probing |
| SWPC 1-minute planetary K | NOAA SWPC | `kp_index`, `estimated_kp`, `kp` string | `https://services.swpc.noaa.gov/json/planetary_k_index_1m.json` | JSON, 28 KB | 1 min | ~1 min | US Government work, public domain | yes | **new**; a minute-cadence estimated Kp the catalogued 3-hourly `noaa-swpc-kp` does not carry |
| SWPC 3-day forecast | NOAA SWPC | Kp table, storm probabilities, radio flux, prose | `https://services.swpc.noaa.gov/text/3-day-forecast.txt` | fixed-width text | 3 / day | issued 2026-09-02 00:30 UTC | US Government work, public domain | yes | **new**; the machine-readable Kp part duplicates the catalogued forecast JSON |
| SWPC 27-day outlook | NOAA SWPC | daily Ap, F10.7, largest Kp for 27 days | `https://services.swpc.noaa.gov/text/27-day-outlook.txt` | fixed-width text | weekly (Mon) | issued 2026-08-31 01:55 UTC | US Government work, public domain | yes | **new**; well outside the 14-day planning window, context only |
| SWPC alerts, watches, warnings | NOAA SWPC | issued space-weather messages with product codes | `https://services.swpc.noaa.gov/products/alerts.json` | JSON, 41 KB | event-driven | minutes | US Government work, public domain | yes | **new**; the "watches and warnings" tier of the existing evidence hierarchy |
| SWPC NOAA scales | NOAA SWPC | current and forecast G/S/R scale values | `https://services.swpc.noaa.gov/products/noaa-scales.json` | JSON, 1.1 KB | ~1 h | stamped 2026-09-02 05:41 UTC at fetch | US Government work, public domain | yes | **new**; keyed `"0"`-`"4"` for current plus a forecast day set, all G/S/R "none" at fetch |
| Kyoto Dst via SWPC | Kyoto WDC, redistributed by NOAA SWPC | quicklook Dst, hourly | `https://services.swpc.noaa.gov/products/kyoto-dst.json` | JSON, 7 KB / 7 d | 1 h | ~1-2 h | Kyoto data under NOAA redistribution; acknowledge Kyoto WDC | yes | **new**; **reprocessed** evidence, not retrieved (see below) |
| Kyoto Dst realtime, direct | Kyoto WDC for Geomagnetism | quicklook Dst | `https://wdc.kugi.kyoto-u.ac.jp/dst_realtime/presentmonth/index.html` | HTML page wrapping a fixed-width IAGA-style block, EUC-JP | 1 h | ~1-2 h | no machine-readable licence found; the WDC asks for acknowledgement of Kyoto and the contributing observatories, and publishes no redistribution grant | yes (HTTP 200, 5.7 KB) | **new**; licence unresolved, scraping required |
| Kyoto AE realtime, direct | Kyoto WDC | quicklook AE/AU/AL/AO | `https://wdc.kugi.kyoto-u.ac.jp/ae_realtime/presentmonth/index.html` | HTML wrapping fixed-width, Shift-JIS | 1 h (1-min values in the plot service) | quicklook; provisional AE lags **years** (provisional AE for 2020 released 2025-07-30) | as above | yes (HTTP 200, 3.0 KB) | **new**; quicklook only is usable, definitive is unusable for operations |
| GFZ Kp | GFZ Helmholtz Centre Potsdam | Kp, nowcast and definitive | `https://kp.gfz.de/app/json/?start=…&end=…&index=Kp` | JSON | 3 h | nowcast within the hour | **CC BY 4.0**, cite GFZ, DOI 10.5880/Kp.0001 | yes | **new**; the only openly licensed Kp with an explicit grant |
| GFZ Hp30 | GFZ | Hp30 half-hourly geomagnetic index | `https://kp.gfz.de/app/json/?…&index=Hp30` | JSON | 30 min | ~1 h | CC BY 4.0 | yes | **new**; the highest-cadence planetary index available |
| GFZ Hp60 | GFZ | Hp60 hourly index | `https://kp.gfz.de/app/json/?…&index=Hp60` | JSON | 1 h | ~1 h | CC BY 4.0 | yes | **new** |
| NRCan STJ magnetometer | Natural Resources Canada / Geological Survey of Canada, CANMOS | X, Y, Z, F at 1 s (`LF*`) and 1 min (`UF*`), station 47.595 N 52.677 W | `https://www.earthquakescanada.nrcan.gc.ca/fdsnws/dataselect/1/query?network=C2&station=STJ&location=R0&channel=UFX&starttime=…&endtime=…` | miniSEED (FDSN dataselect); metadata as text via `fdsnws/station/1` | 1 s and 1 min | near real time (`R0` = internet, `R1`/`R2` = GOES relay) | **restrictive**: "not for sale or distribution by you to third parties, without the express written permission of Natural Resources Canada"; non-commercial; acknowledgement and a copy of any publication requested | yes, channel metadata and a 10-minute miniSEED window both returned | **new**; **redistribution-blocked as written** |
| Space Weather Canada regional forecast, STJ | Natural Resources Canada | hourly range of magnetic field variation, 48 h review plus 24 h forecast, classified Quiet / Unsettled / Active / Stormy / Major Storm at St. John's thresholds 0-27, 28-50, 51-89, 90-262, 263+ nT | `https://www.spaceweather.gc.ca/forecast-prevision/short-court/sfst-6-en.php?obs=STJ` (index at `sfst-5-en.php`) | HTML page; the values load client-side, no JSON endpoint found | hourly values, forecast to +24 h | page served, values not in the HTML | NRCan; same geomagnetic conditions of use as above | page yes (HTTP 200); data payload **not** located | **new**; the single most Avalon-specific space-weather forecast found, and the hardest to retrieve |
| Space Weather Canada Atom feed | NRCan | space-weather bulletins | `https://www.spaceweather.gc.ca/atom/feed-en.xml` | Atom XML, 25 KB | event-driven | minutes | NRCan | yes | **new** |
| GOES magnetometer | NOAA SWPC / GOES-19 primary | He, Hp, Hn field components at geosynchronous orbit | `https://services.swpc.noaa.gov/json/goes/primary/magnetometers-1-day.json` | JSON, 261 KB | 1 min | ~1-2 min | US Government work, public domain | yes | **new**; geosynchronous, not local, and only weakly indicative for the Avalon |
| GOES XRS | NOAA SWPC / GOES-18 and 19 | 0.1-0.8 nm and 0.05-0.4 nm X-ray flux | `https://services.swpc.noaa.gov/json/goes/primary/xrays-1-day.json` | JSON, 654 KB | 1 min | ~1-2 min | US Government work, public domain | yes | **new**; flare context, ~2-3 days upstream of any aurora |
| GOES instrument sources | NOAA SWPC | which GOES is primary for electrons, protons, alphas | `https://services.swpc.noaa.gov/json/goes/instrument-sources.json` | JSON | on change | last change 2026-07-29 | US Government work, public domain | yes | **new**; provenance metadata for the two rows above |
| GOES SUVI imagery | NOAA SWPC | EUV solar disc, 6 channels (94, 131, 171, 195, 284, 304) | `https://services.swpc.noaa.gov/images/animations/suvi/primary/195/latest.png` | PNG | ~4 min | minutes | US Government work, public domain | yes (195 and 304) | **new**; imagery, no numeric evidence value |
| CCOR-1 coronagraph | NOAA SWPC / GOES-19 | white-light coronagraph, CME detection | `https://services.swpc.noaa.gov/products/ccor1/jpegs.json` (index), `.../images/animations/ccor1/latest.jpg` | JSON index of JPEG and FITS | ~15 min | index entries were dated 2026-08-09 at fetch | US Government work, public domain | index yes, `latest.jpg` yes | **new**; operational successor to LASCO |
| SOHO LASCO C2/C3 | ESA/NASA SOHO, LASCO consortium | white-light coronagraph | `https://soho.nascom.nasa.gov/data/realtime/c2/1024/latest.jpg` and `.../c3/...` | JPEG (realtime), FITS in the archive | ~12 min for C2, ~30 min for C3 | ~30-60 min for realtime frames | NASA/ESA imagery, free use with acknowledgement; LASCO consortium citation requested for science use | yes | **new**; being superseded by CCOR, keep as a cross-check only |
| SDO imagery | NASA SDO | AIA EUV and HMI magnetogram browse images | `https://sdo.gsfc.nasa.gov/assets/img/latest/latest_1024_0193.jpg` | JPEG | ~15 min for browse images | ~15-30 min | NASA imagery, free use with acknowledgement | yes | **new**; imagery only |
| STEREO-A beacon via SWPC | NASA STEREO, relayed by SWPC | density, speed, temperature, HGRTN magnetic field | `https://services.swpc.noaa.gov/json/stereo/stereo_a_1m.json` | JSON, **656 bytes** | nominally beacon-rate | **stale**: newest record `2026-07-27T12:29:00Z`, about 5 weeks old at fetch | US Government work, public domain (relay); NASA STEREO open data | endpoint yes, content stale | **new**; do not admit on this evidence |
| AuroraWatch UK status | Lancaster University | UK geomagnetic alert level | `https://aurorawatch-api.lancs.ac.uk/0.2.5/status/current-status.xml` | XML, 462 B | ~1-3 min | minutes | Lancaster University terms; UK-specific | yes | **new**; wrong hemisphere-sector, listed only as a nowcast-alternative datapoint |
| Aurorasaurus reports | Aurorasaurus (NCAR/NASA) | crowdsourced aurora sightings | `https://api.aurorasaurus.org/aurora/report/latest` | JSON | event-driven | minutes | project terms | **no**, connection failed (HTTP 000) | **new**; and citizen reports would be **uncalibrated observation** class in any case |

Endpoints probed and found **absent** (recorded so they are not probed again):
`services.swpc.noaa.gov/products/solar-wind/mag-1-day.json` and `plasma-1-day.json`
(404; the `products/solar-wind/` directory listing is empty), and
`json/ace/mag/ace_mag_1m.json` / `json/ace/swepam/ace_swepam_1m.json` (404). ACE
survives at 1-hour cadence only, at `json/ace/mag/ace_mag_1h.json` and
`json/ace/swepam/ace_swepam_1h.json`, both verified 200 with current timestamps;
ACE's 1-minute contribution now reaches consumers through the RTSW feeds instead.
The legacy `www.spaceweather.gc.ca/data-donnee/sm-mag/rt-tr/...` paths cited in
`docs/research/data-sources.md` return 404 and are superseded by the FDSN service.

## What SpaceWeatherLive displays, and what it draws on

SpaceWeatherLive is an aggregator, not a producer. Its live pages load from four
external hosts only: `services.swpc.noaa.gov`, `sdo.gsfc.nasa.gov`,
`sohowww.nascom.nasa.gov` and `stereo-ssc.nascom.nasa.gov`, plus
`www.sws.bom.gov.au` for the Australian magnetometer panels. Its navigation names
the imagery sources it carries as SDO, STEREO, PROBA-2, SOHO, GOES and **SOLAR-1**,
and its coronagraph section offers CCOR-1, CCOR-2 and LASCO side by side. Its
magnetometer section credits the Geological Survey of Canada for the CANMOS
panels, the Finnish Meteorological Institute for the Kiruna panel, and Geoscience
Australia, the University of Newcastle Space Physics Group and the Australian
Antarctic Division for the southern panels. Its index pages cite NOAA SWPC for the planetary K nowcast and
the alerts feed, GFZ Potsdam for definitive Kp/ap, and Kyoto for quicklook Dst.

The practical conclusion: **SpaceWeatherLive reveals no upstream that is not
already reachable directly.** Every feed behind it is on the table above. It is
useful as a cross-check on presentation, not as a source, and its own displays
would be reprocessed evidence at best.

## STEREO status

STEREO-A is operating nominally and taking science data on a regular basis.
STEREO-B lost contact on 2014-10-01 after a spacecraft reset during a solar
conjunction test; communications were briefly re-established on 2016-08-21, no
further signal was received after 2016-09-23, and NASA directed that periodic
recovery operations cease with the last support pass on 2018-10-17. Source:
[STEREO Mission Status, NASA STEREO Science Center](https://stereo-ssc.nascom.nasa.gov/status.shtml).

STEREO-A is therefore the only STEREO asset, and for this experiment it is a
weak one twice over: it is off the Sun-Earth line, so it images the Sun from an
angle rather than measuring the wind that will reach Newfoundland, and the SWPC
relay of its beacon was five weeks stale at the time of fetch.

## What matters for Avalon aurora visibility specifically

The Avalon sits at about 47.6 N geographic, roughly 53 N geomagnetic. Aurora is
visible there only when the oval is pushed well equatorward, which makes two
things decisive and most of the table above merely contextual.

**The local magnetometer (STJ) is the only true ground truth in the box.** It sits
inside the Avalon detail box at 47.595 N, 52.677 W, a few kilometres from the
St. John's city centre; it measures the actual local
disturbance rather than a planetary average, and the local rate of change of the
horizontal component responds to a substorm onset in minutes, where the
3-hourly planetary Kp already catalogued cannot resolve a substorm at all. GFZ
Hp30 narrows the planetary index to 30 minutes but is still planetary. Nothing
else in the inventory can distinguish "the oval reached Newfoundland" from
"the oval reached somewhere at this L-shell". Two caveats sit on top of that
value: the FDSN service delivers miniSEED, which is a seismological waveform
container needing a decoder rather than a JSON parse, and NRCan's stated
conditions of use forbid onward distribution to third parties without written
permission and ask that the data not be used commercially. A map that serves STJ
traces to the public would be redistributing them.

**The Space Weather Canada regional forecast for STJ is the only forecast product
that is about Newfoundland rather than about the planet.** It gives 48 hours of
reviewed hourly range plus 24 hours of forecast hourly range, classified against
thresholds calibrated for St. John's specifically (Quiet 0-27 nT through Major
Storm at 263+ nT). That is a forward-looking local statement of exactly the
quantity the STJ magnetometer measures, from the agency that runs the
magnetometer. Its problem is retrieval: the page is served fine, but the values
are loaded client-side and no JSON or text endpoint behind it was located within
this ticket's probe budget. Finding that endpoint, or deciding the product is
link-only, is the obvious follow-on question.

Ranked for this location, on top of the existing hierarchy in
`docs/research/data-sources.md`:

1. STJ magnetometer local disturbance, if the licence can be resolved.
2. Space Weather Canada STJ regional forecast, if the payload can be retrieved.
3. RTSW plasma (speed, density) alongside the already-catalogued Bz and Bt, with
   spacecraft identity and quality flags stored, and SWPC's own propagated
   solar wind in place of a derived-here propagation lag.
4. GFZ Hp30 as the highest-cadence planetary index that is openly licensed.
5. OVATION (already catalogued) for oval geometry and viewline.
6. Quicklook Dst for storm-phase context; SWPC alerts for the warning tier.

Everything solar - XRS, SUVI, LASCO, CCOR, SDO, STEREO-A - is two to three days
upstream of any Avalon aurora. It belongs to a "something may be coming" band, not
to a visibility decision on a given night, and none of it is imagery a numeric
evidence path can consume without a model in between.

## Evidence class per CONTEXT.md

Applying the classes in `CONTEXT.md`:

- **Retrieved.** Anything fetched from the producer as the producer issued it:
  all `services.swpc.noaa.gov` feeds fetched from NOAA SWPC, GFZ Kp/Hp30/Hp60
  fetched from `kp.gfz.de`, STJ miniSEED fetched from the NRCan FDSN service,
  the Space Weather Canada Atom feed, SOHO and SDO imagery from their own hosts.

- **Reprocessed** (producer and intermediary both named). `products/kyoto-dst.json`
  is Kyoto WDC's index delivered by NOAA SWPC, so it must be declared as producer
  Kyoto WDC for Geomagnetism, intermediary NOAA SWPC. The same applies to
  `json/stereo/stereo_a_1m.json`: producer NASA STEREO, intermediary NOAA SWPC.
  Under the 2026-09-02 source-delivery-kind rule these are admissible **only if
  the reprocessing is declared**; fetching Kyoto Dst from SWPC and calling it
  retrieved would be a misdeclaration. Fetching the same index directly from
  `wdc.kugi.kyoto-u.ac.jp` would make it retrieved, at the cost of scraping an
  EUC-JP HTML page and an unresolved licence.

- **Derived-here** (allowed on data paths, inputs and cited method required). Any
  rolling Bz summary over 5/15/30/60 minutes, any dH/dt computed from STJ X and Y,
  any local K-index computed from STJ, and any solar-wind-to-magnetosphere
  coupling function. Note that SWPC's propagated solar wind and Geospace Dst are
  **not** derived-here: they are retrieved model output from NOAA, and the
  distinction matters for who is accountable for the method.

- **Generated-display.** Interpolating the OVATION 10-minute grid or an STJ trace
  between retrieved frames for smooth animation. Display only, never on a data
  path, and subject to the existing three-level kill switch.

- **Uncalibrated observation.** Aurorasaurus crowdsourced sightings, and any
  hobbyist magnetometer feed. Never usable for verification. (Aurorasaurus was
  unreachable at fetch time in any case.)

A licence note that cuts across the classes: the NRCan geomagnetic conditions of
use are the only genuinely restrictive terms in this inventory. Everything from
NOAA SWPC is a US Government work in the public domain, GFZ is explicit CC BY 4.0,
NASA and ESA imagery is free use with acknowledgement, and Kyoto is merely
unstated rather than restrictive. NRCan alone says, in terms, that the data are
not for distribution to third parties without written permission and asks that
they not be used commercially - and NRCan happens to hold the two sources that
matter most for the Avalon. Resolving that, by written permission or by a
link-only registry state, is the gating question for local aurora evidence.
