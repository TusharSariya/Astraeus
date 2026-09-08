# GDPS-GEML 25 km disposition: all 54 accounting IDs

Non-normative research for [#194](https://github.com/TusharSariya/Astraeus/issues/194),
2026-09-08. Base `538a363`. **No acquisition/exclusion status is owner-approved
by this note; #194 remains open.** No grids were fetched, no source was admitted,
and `operational: false` remains unchanged.

## Product conclusion

GEML remains a separately published AI forecast product. ECCC's
[current GDPS description](https://eccc-msc.github.io/open-data/msc-data/nwp_gdps/readme_gdps_en/)
distinguishes the coupled 15 km physics-based GDPS from its GEML guidance.
The [May 26, 2026 implementation notice](https://dd.weather.gc.ca/doc/genots/2026/05/25/NOCN03_CWAO_251940___18749)
upgrades GDPS 9.1 to GDPS 10.0 using spectral nudging toward GEML. It does not
announce retirement of the standalone GEML product. Current metadata below
confirms continued publication; folding these IDs into GDPS would erase their
producer-product identity.

The [official GDPS chronology](https://eccc-msc.github.io/open-data/msc-data/nwp_gdps/changelog_gdps_en/)
separately records the July 3, 2019 change of the physics-based GDPS grid from
25 km to 15 km. That older GDPS 25 km product is not the currently advertised
`GDPS-GEML_25km` family. A matching resolution label does not establish a
replacement relationship.

The [GEML documentation](https://eccc-msc.github.io/open-data/msc-data/nwp_gdps/readme_gdps-geml-datamart_en/)
defines Global Environmental eMuLator, an ECCC-trained GraphCast-compatible
model, 1440 by 721 global 0.25-degree cells, 13 pressure levels, 00/12 UTC
runs and six-hour forecasts through 240 hours. It is not “Global Ensemble
Machine Learning,” as an earlier local marine research table expanded the name.
GEML is potentially useful as separate large-scale guidance, but its role in
nudging GDPS means independence cannot be assumed. This is an inference from
the documented model relationship, not measured incremental forecast skill.

## Geography, access and native identity

Every scoped WMS response advertises the same global cell-edge extent:
west -180.125, east 179.875, south -90.125, north 90.125 degrees. Avalon
45–50.5 N / 58–46 W is inside it. These cell-edge bounds do not authorize
out-of-range latitude sampling. Geographic exclusion is unsupported.
The provider identifier remains `urn:x-msc-smc:md:weather-meteo::nwep.gdps.geml`.

The current [GEML Datamart product root](https://dd.weather.gc.ca/today/model_gdps-geml/)
was an empty directory at the captured instant. Its documented `25km/` child
returned 404. This is an observed current-directory gap, not retirement.
The [2026-09-07 12 UTC, lead 006 directory](https://dd.weather.gc.ca/20260907/WXO-DD/model_gdps-geml/25km/12/006/)
listed 82 GRIB2 files, including **all 54** exact variable/level matches below.
The other 28 files are outside this ticket's historical ID set. No payload was
requested. The observed path lacks the `grib2/lat_lon/` components appearing in
the English documentation template; implementations must follow validated
published listings and fail closed on absent run directories.

Filename date/hour is forecast reference time; `PT006H` identifies the lead,
so this listing's valid time is 2026-09-07 18 UTC. Current WMS metadata advertises
reference times `2026-09-06T00:00:00Z/2026-09-07T12:00:00Z/PT12H`, default
2026-09-07 12 UTC. Valid times end at 2026-09-17 12 UTC with PT6H spacing,
default 2026-09-08 00 UTC; each row records its actual starting hour below.
A capabilities range is not proof that every cross-product of run/time exists.

The units below are **WMS title units**, unchanged from the retained September 6
inventory, not decoded GRIB units. In particular temperature °C is not a promise
of native GRIB °C, and geopotential `[gpm]` must not be silently mapped to energy
per mass. Preserve separate GeoMet server-rectified coverage versus native GRIB
geometry and units. The [retained accounting](geomet-field-accounting-2026-09-06.md)
records WCS numeric access, server resampling and the ECCC licence; this pass
does not re-fetch those full catalogues or reinterpret permission/admission.

## Exact dispositions and closure

**D1 for every row:** `distinct_current_product_candidate_deferred_owner_contract`.
All 54 are geographically eligible, currently advertised and present in a native
file listing. None is acquired, retired, replaced-by-GDPS, geographically excluded
or approved as an independent forecast vote. Proposed next action is one bounded
GEML source contract covering this exact set, rather than 54 ad hoc acquisitions.
All levels, units and time starts remain individually accounted below.

The specific remaining owner action is to select acquisition of these 54 IDs as
separate GEML evidence, or explicitly exclude/defer their incremental product
value. If acquisition is chosen, [#141](https://github.com/TusharSariya/Astraeus/issues/141)
must settle source/access identity, selected field/lead scope, native GRIB units,
missing values and geometry before implementation; [#97](https://github.com/TusharSariya/Astraeus/issues/97)
retains integrated evidence obligations. Current metadata resolves identity and
geography but cannot supply an owner-approved disposition or live numeric proof.
Do not close #194 on this research alone.

## Exhaustive reconciliation

Native variable/level is the exact filename middle token between
`20260907T12Z_MSC_GDPS-GEML_` and `_LatLon0.25_PT006H.grib2`.
Time start is on 2026-09-07 UTC. Each row links its scoped official metadata.

| Coverage ID | WMS unit | Native variable/level | Time start | Disposition |
|---|---|---|---|---|
| [GDPS-GEML_25km_AirTemp_1000mb](https://geo.weather.gc.ca/geomet?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities&LAYERS=GDPS-GEML_25km_AirTemp_1000mb) | °C | `AirTemp_IsbL-1000` | 18:00 | D1 |
| [GDPS-GEML_25km_AirTemp_100mb](https://geo.weather.gc.ca/geomet?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities&LAYERS=GDPS-GEML_25km_AirTemp_100mb) | °C | `AirTemp_IsbL-0100` | 18:00 | D1 |
| [GDPS-GEML_25km_AirTemp_150mb](https://geo.weather.gc.ca/geomet?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities&LAYERS=GDPS-GEML_25km_AirTemp_150mb) | °C | `AirTemp_IsbL-0150` | 18:00 | D1 |
| [GDPS-GEML_25km_AirTemp_200mb](https://geo.weather.gc.ca/geomet?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities&LAYERS=GDPS-GEML_25km_AirTemp_200mb) | °C | `AirTemp_IsbL-0200` | 18:00 | D1 |
| [GDPS-GEML_25km_AirTemp_250mb](https://geo.weather.gc.ca/geomet?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities&LAYERS=GDPS-GEML_25km_AirTemp_250mb) | °C | `AirTemp_IsbL-0250` | 18:00 | D1 |
| [GDPS-GEML_25km_AirTemp_2m](https://geo.weather.gc.ca/geomet?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities&LAYERS=GDPS-GEML_25km_AirTemp_2m) | °C | `AirTemp_AGL-2m` | 18:00 | D1 |
| [GDPS-GEML_25km_AirTemp_300mb](https://geo.weather.gc.ca/geomet?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities&LAYERS=GDPS-GEML_25km_AirTemp_300mb) | °C | `AirTemp_IsbL-0300` | 18:00 | D1 |
| [GDPS-GEML_25km_AirTemp_400mb](https://geo.weather.gc.ca/geomet?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities&LAYERS=GDPS-GEML_25km_AirTemp_400mb) | °C | `AirTemp_IsbL-0400` | 18:00 | D1 |
| [GDPS-GEML_25km_AirTemp_500mb](https://geo.weather.gc.ca/geomet?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities&LAYERS=GDPS-GEML_25km_AirTemp_500mb) | °C | `AirTemp_IsbL-0500` | 18:00 | D1 |
| [GDPS-GEML_25km_AirTemp_50mb](https://geo.weather.gc.ca/geomet?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities&LAYERS=GDPS-GEML_25km_AirTemp_50mb) | °C | `AirTemp_IsbL-0050` | 18:00 | D1 |
| [GDPS-GEML_25km_AirTemp_600mb](https://geo.weather.gc.ca/geomet?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities&LAYERS=GDPS-GEML_25km_AirTemp_600mb) | °C | `AirTemp_IsbL-0600` | 18:00 | D1 |
| [GDPS-GEML_25km_AirTemp_700mb](https://geo.weather.gc.ca/geomet?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities&LAYERS=GDPS-GEML_25km_AirTemp_700mb) | °C | `AirTemp_IsbL-0700` | 18:00 | D1 |
| [GDPS-GEML_25km_AirTemp_850mb](https://geo.weather.gc.ca/geomet?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities&LAYERS=GDPS-GEML_25km_AirTemp_850mb) | °C | `AirTemp_IsbL-0850` | 18:00 | D1 |
| [GDPS-GEML_25km_AirTemp_925mb](https://geo.weather.gc.ca/geomet?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities&LAYERS=GDPS-GEML_25km_AirTemp_925mb) | °C | `AirTemp_IsbL-0925` | 18:00 | D1 |
| [GDPS-GEML_25km_Geopotential_1000mb](https://geo.weather.gc.ca/geomet?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities&LAYERS=GDPS-GEML_25km_Geopotential_1000mb) | gpm | `Geopotential_IsbL-1000` | 18:00 | D1 |
| [GDPS-GEML_25km_Geopotential_100mb](https://geo.weather.gc.ca/geomet?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities&LAYERS=GDPS-GEML_25km_Geopotential_100mb) | gpm | `Geopotential_IsbL-0100` | 18:00 | D1 |
| [GDPS-GEML_25km_Geopotential_150mb](https://geo.weather.gc.ca/geomet?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities&LAYERS=GDPS-GEML_25km_Geopotential_150mb) | gpm | `Geopotential_IsbL-0150` | 18:00 | D1 |
| [GDPS-GEML_25km_Geopotential_200mb](https://geo.weather.gc.ca/geomet?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities&LAYERS=GDPS-GEML_25km_Geopotential_200mb) | gpm | `Geopotential_IsbL-0200` | 18:00 | D1 |
| [GDPS-GEML_25km_Geopotential_250mb](https://geo.weather.gc.ca/geomet?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities&LAYERS=GDPS-GEML_25km_Geopotential_250mb) | gpm | `Geopotential_IsbL-0250` | 18:00 | D1 |
| [GDPS-GEML_25km_Geopotential_300mb](https://geo.weather.gc.ca/geomet?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities&LAYERS=GDPS-GEML_25km_Geopotential_300mb) | gpm | `Geopotential_IsbL-0300` | 18:00 | D1 |
| [GDPS-GEML_25km_Geopotential_400mb](https://geo.weather.gc.ca/geomet?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities&LAYERS=GDPS-GEML_25km_Geopotential_400mb) | gpm | `Geopotential_IsbL-0400` | 18:00 | D1 |
| [GDPS-GEML_25km_Geopotential_500mb](https://geo.weather.gc.ca/geomet?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities&LAYERS=GDPS-GEML_25km_Geopotential_500mb) | gpm | `Geopotential_IsbL-0500` | 18:00 | D1 |
| [GDPS-GEML_25km_Geopotential_50mb](https://geo.weather.gc.ca/geomet?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities&LAYERS=GDPS-GEML_25km_Geopotential_50mb) | gpm | `Geopotential_IsbL-0050` | 18:00 | D1 |
| [GDPS-GEML_25km_Geopotential_600mb](https://geo.weather.gc.ca/geomet?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities&LAYERS=GDPS-GEML_25km_Geopotential_600mb) | gpm | `Geopotential_IsbL-0600` | 18:00 | D1 |
| [GDPS-GEML_25km_Geopotential_700mb](https://geo.weather.gc.ca/geomet?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities&LAYERS=GDPS-GEML_25km_Geopotential_700mb) | gpm | `Geopotential_IsbL-0700` | 18:00 | D1 |
| [GDPS-GEML_25km_Geopotential_850mb](https://geo.weather.gc.ca/geomet?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities&LAYERS=GDPS-GEML_25km_Geopotential_850mb) | gpm | `Geopotential_IsbL-0850` | 18:00 | D1 |
| [GDPS-GEML_25km_Geopotential_925mb](https://geo.weather.gc.ca/geomet?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities&LAYERS=GDPS-GEML_25km_Geopotential_925mb) | gpm | `Geopotential_IsbL-0925` | 18:00 | D1 |
| [GDPS-GEML_25km_Pressure_MSL](https://geo.weather.gc.ca/geomet?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities&LAYERS=GDPS-GEML_25km_Pressure_MSL) | Pa | `Pressure_MSL` | 12:00 | D1 |
| [GDPS-GEML_25km_SpecificHumidity_1000mb](https://geo.weather.gc.ca/geomet?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities&LAYERS=GDPS-GEML_25km_SpecificHumidity_1000mb) | kg/kg | `SpecificHumidity_IsbL-1000` | 12:00 | D1 |
| [GDPS-GEML_25km_SpecificHumidity_100mb](https://geo.weather.gc.ca/geomet?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities&LAYERS=GDPS-GEML_25km_SpecificHumidity_100mb) | kg/kg | `SpecificHumidity_IsbL-0100` | 12:00 | D1 |
| [GDPS-GEML_25km_SpecificHumidity_150mb](https://geo.weather.gc.ca/geomet?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities&LAYERS=GDPS-GEML_25km_SpecificHumidity_150mb) | kg/kg | `SpecificHumidity_IsbL-0150` | 12:00 | D1 |
| [GDPS-GEML_25km_SpecificHumidity_200mb](https://geo.weather.gc.ca/geomet?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities&LAYERS=GDPS-GEML_25km_SpecificHumidity_200mb) | kg/kg | `SpecificHumidity_IsbL-0200` | 12:00 | D1 |
| [GDPS-GEML_25km_SpecificHumidity_250mb](https://geo.weather.gc.ca/geomet?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities&LAYERS=GDPS-GEML_25km_SpecificHumidity_250mb) | kg/kg | `SpecificHumidity_IsbL-0250` | 12:00 | D1 |
| [GDPS-GEML_25km_SpecificHumidity_300mb](https://geo.weather.gc.ca/geomet?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities&LAYERS=GDPS-GEML_25km_SpecificHumidity_300mb) | kg/kg | `SpecificHumidity_IsbL-0300` | 12:00 | D1 |
| [GDPS-GEML_25km_SpecificHumidity_400mb](https://geo.weather.gc.ca/geomet?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities&LAYERS=GDPS-GEML_25km_SpecificHumidity_400mb) | kg/kg | `SpecificHumidity_IsbL-0400` | 12:00 | D1 |
| [GDPS-GEML_25km_SpecificHumidity_500mb](https://geo.weather.gc.ca/geomet?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities&LAYERS=GDPS-GEML_25km_SpecificHumidity_500mb) | kg/kg | `SpecificHumidity_IsbL-0500` | 12:00 | D1 |
| [GDPS-GEML_25km_SpecificHumidity_50mb](https://geo.weather.gc.ca/geomet?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities&LAYERS=GDPS-GEML_25km_SpecificHumidity_50mb) | kg/kg | `SpecificHumidity_IsbL-0050` | 12:00 | D1 |
| [GDPS-GEML_25km_SpecificHumidity_600mb](https://geo.weather.gc.ca/geomet?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities&LAYERS=GDPS-GEML_25km_SpecificHumidity_600mb) | kg/kg | `SpecificHumidity_IsbL-0600` | 12:00 | D1 |
| [GDPS-GEML_25km_SpecificHumidity_700mb](https://geo.weather.gc.ca/geomet?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities&LAYERS=GDPS-GEML_25km_SpecificHumidity_700mb) | kg/kg | `SpecificHumidity_IsbL-0700` | 12:00 | D1 |
| [GDPS-GEML_25km_SpecificHumidity_850mb](https://geo.weather.gc.ca/geomet?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities&LAYERS=GDPS-GEML_25km_SpecificHumidity_850mb) | kg/kg | `SpecificHumidity_IsbL-0850` | 12:00 | D1 |
| [GDPS-GEML_25km_SpecificHumidity_925mb](https://geo.weather.gc.ca/geomet?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities&LAYERS=GDPS-GEML_25km_SpecificHumidity_925mb) | kg/kg | `SpecificHumidity_IsbL-0925` | 12:00 | D1 |
| [GDPS-GEML_25km_VerticalVelocity_1000mb](https://geo.weather.gc.ca/geomet?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities&LAYERS=GDPS-GEML_25km_VerticalVelocity_1000mb) | Pa/s | `VerticalVelocity_IsbL-1000` | 12:00 | D1 |
| [GDPS-GEML_25km_VerticalVelocity_100mb](https://geo.weather.gc.ca/geomet?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities&LAYERS=GDPS-GEML_25km_VerticalVelocity_100mb) | Pa/s | `VerticalVelocity_IsbL-0100` | 12:00 | D1 |
| [GDPS-GEML_25km_VerticalVelocity_150mb](https://geo.weather.gc.ca/geomet?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities&LAYERS=GDPS-GEML_25km_VerticalVelocity_150mb) | Pa/s | `VerticalVelocity_IsbL-0150` | 12:00 | D1 |
| [GDPS-GEML_25km_VerticalVelocity_200mb](https://geo.weather.gc.ca/geomet?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities&LAYERS=GDPS-GEML_25km_VerticalVelocity_200mb) | Pa/s | `VerticalVelocity_IsbL-0200` | 12:00 | D1 |
| [GDPS-GEML_25km_VerticalVelocity_250mb](https://geo.weather.gc.ca/geomet?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities&LAYERS=GDPS-GEML_25km_VerticalVelocity_250mb) | Pa/s | `VerticalVelocity_IsbL-0250` | 12:00 | D1 |
| [GDPS-GEML_25km_VerticalVelocity_300mb](https://geo.weather.gc.ca/geomet?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities&LAYERS=GDPS-GEML_25km_VerticalVelocity_300mb) | Pa/s | `VerticalVelocity_IsbL-0300` | 12:00 | D1 |
| [GDPS-GEML_25km_VerticalVelocity_400mb](https://geo.weather.gc.ca/geomet?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities&LAYERS=GDPS-GEML_25km_VerticalVelocity_400mb) | Pa/s | `VerticalVelocity_IsbL-0400` | 12:00 | D1 |
| [GDPS-GEML_25km_VerticalVelocity_500mb](https://geo.weather.gc.ca/geomet?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities&LAYERS=GDPS-GEML_25km_VerticalVelocity_500mb) | Pa/s | `VerticalVelocity_IsbL-0500` | 12:00 | D1 |
| [GDPS-GEML_25km_VerticalVelocity_50mb](https://geo.weather.gc.ca/geomet?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities&LAYERS=GDPS-GEML_25km_VerticalVelocity_50mb) | Pa/s | `VerticalVelocity_IsbL-0050` | 12:00 | D1 |
| [GDPS-GEML_25km_VerticalVelocity_600mb](https://geo.weather.gc.ca/geomet?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities&LAYERS=GDPS-GEML_25km_VerticalVelocity_600mb) | Pa/s | `VerticalVelocity_IsbL-0600` | 12:00 | D1 |
| [GDPS-GEML_25km_VerticalVelocity_700mb](https://geo.weather.gc.ca/geomet?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities&LAYERS=GDPS-GEML_25km_VerticalVelocity_700mb) | Pa/s | `VerticalVelocity_IsbL-0700` | 12:00 | D1 |
| [GDPS-GEML_25km_VerticalVelocity_850mb](https://geo.weather.gc.ca/geomet?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities&LAYERS=GDPS-GEML_25km_VerticalVelocity_850mb) | Pa/s | `VerticalVelocity_IsbL-0850` | 12:00 | D1 |
| [GDPS-GEML_25km_VerticalVelocity_925mb](https://geo.weather.gc.ca/geomet?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities&LAYERS=GDPS-GEML_25km_VerticalVelocity_925mb) | Pa/s | `VerticalVelocity_IsbL-0925` | 12:00 | D1 |

## Bounded metadata receipts and verification

All 54 scoped WMS responses returned the requested exact layer, unchanged title
and global extent. They total **835,304 bytes**, under a 128 KiB ceiling per
request. Raw metadata stays outside Git at `/private/tmp/geml194-metadata`.
The exact-ID reconciliation and native-filename membership assertions passed
54/54. This verifies metadata, not forecast retrieval, decoded units or API values.
A multi-layer capabilities attempt returned a 604-byte service exception:
GeoMet supports only a single layer filter. No unbounded full WMS response was
requested. The per-layer follow-up was sequential and rate-spaced.

Compact per-request digests allow the retained files to be checked without
committing provider response bodies. Final-byte times are client UTC times.

| Request | Bytes | Completed UTC | SHA-256 |
|---|---:|---|---|
| `GDPS-GEML_25km_AirTemp_1000mb` | 17839 | 2026-09-08T02:14:48.129946+00:00 | `f0f73626c7e4f284cda9e4c53b168f74050bdf99b4f66023310a5b0f93b4819d` |
| `GDPS-GEML_25km_AirTemp_100mb` | 16123 | 2026-09-08T02:14:48.453429+00:00 | `515021163caf59d07dc0d5ecefb9f14032e3ec15234ed30d45b00f2c2cb6c19d` |
| `GDPS-GEML_25km_AirTemp_150mb` | 16123 | 2026-09-08T02:14:48.789021+00:00 | `acc355d366e3d24338bd0d91195ff22c4e0ab394f16c5505ca4085d750616380` |
| `GDPS-GEML_25km_AirTemp_200mb` | 16123 | 2026-09-08T02:14:49.125804+00:00 | `23ab0a35e08e10ee6546667d601aea23d765fd539c84c422400d686751c39ac4` |
| `GDPS-GEML_25km_AirTemp_250mb` | 16123 | 2026-09-08T02:14:49.451894+00:00 | `dd9925ee08d1d6397b1299fa50d83ca2708a611f06447efd3ac5837c130494dc` |
| `GDPS-GEML_25km_AirTemp_2m` | 18683 | 2026-09-08T02:14:49.820806+00:00 | `ee44194477fa82a9ca4450b73e822f943ce13387fdb25e7f19d470903152c309` |
| `GDPS-GEML_25km_AirTemp_300mb` | 17259 | 2026-09-08T02:14:50.156469+00:00 | `94407978f34e88f8952881218d9d279a251ebdd80a1302d9fb0ce75cb3465909` |
| `GDPS-GEML_25km_AirTemp_400mb` | 17259 | 2026-09-08T02:14:50.496941+00:00 | `aaf584ee3ee1c76a87521b0e9bd08344b850d47f190f95d0db3051b5a14f7af8` |
| `GDPS-GEML_25km_AirTemp_500mb` | 17259 | 2026-09-08T02:14:50.952271+00:00 | `cc6e10c28add3752597d677777ad26a2a8ac5dd0dd11557cb6c9c956f492f7e2` |
| `GDPS-GEML_25km_AirTemp_50mb` | 16114 | 2026-09-08T02:14:51.282084+00:00 | `7960e0c6fd559763c7c139d1e2c14130bdd94730d31da8aac426814755d6b6a9` |
| `GDPS-GEML_25km_AirTemp_600mb` | 17827 | 2026-09-08T02:14:51.601788+00:00 | `07833f73d4157f3037998ec36f47272437610f7b9225f8b8f8c1a75f08dda9ea` |
| `GDPS-GEML_25km_AirTemp_700mb` | 17827 | 2026-09-08T02:14:51.935519+00:00 | `99e8f5824e190d4912b9d165e67b10a15866e33eddb9f03b0cf75cc574b3fee7` |
| `GDPS-GEML_25km_AirTemp_850mb` | 17827 | 2026-09-08T02:14:52.272989+00:00 | `0034052cd226b800eed2e4dafa52ed291aa40cc4771d1793b36908121e75da92` |
| `GDPS-GEML_25km_AirTemp_925mb` | 17827 | 2026-09-08T02:14:52.633473+00:00 | `dcedc40f65db9713e798c2d33b39617d8045ba7db3b43e2852d69c8690205a19` |
| `GDPS-GEML_25km_Geopotential_1000mb` | 14685 | 2026-09-08T02:14:52.977174+00:00 | `3a59c259305438e34b6db84b49e7dc5308f85fc65cf6e95c9876b589339bb05a` |
| `GDPS-GEML_25km_Geopotential_100mb` | 14688 | 2026-09-08T02:14:53.319177+00:00 | `56f97d74065786d69d627a318835105ec36a3c68e9781277e7adca3c57b2c4e8` |
| `GDPS-GEML_25km_Geopotential_150mb` | 14691 | 2026-09-08T02:14:53.657338+00:00 | `3e473fd165d810ada2f63790ac89d087d8c162817d206f98aa74da3cd7151ff8` |
| `GDPS-GEML_25km_Geopotential_200mb` | 14691 | 2026-09-08T02:14:53.985524+00:00 | `749c0b18bf80d17ef6b17413bd50515eeb5459286b07a679d91bc217b2de048e` |
| `GDPS-GEML_25km_Geopotential_250mb` | 14691 | 2026-09-08T02:14:54.328323+00:00 | `be8a97adfcdc1de8a3dedc4d5345a94d2f13a93ccbbaaf2f1ca4b39b141ecb09` |
| `GDPS-GEML_25km_Geopotential_300mb` | 14679 | 2026-09-08T02:14:54.650901+00:00 | `02879aaaaed304aca47e846305daadaab15b98148ddea932f125102ec1e296a6` |
| `GDPS-GEML_25km_Geopotential_400mb` | 14679 | 2026-09-08T02:14:54.989817+00:00 | `25c2a33a10f14730af3d033b43852160ca773599c86781f817daa28498f2e04f` |
| `GDPS-GEML_25km_Geopotential_500mb` | 14679 | 2026-09-08T02:14:55.325950+00:00 | `e9ea030ba35c867cb2d88def5f5970da20cd29988192a74780302f6808c6183f` |
| `GDPS-GEML_25km_Geopotential_50mb` | 14686 | 2026-09-08T02:14:55.658247+00:00 | `c5ae5a60c869f1b6fbd0e74863247d255364ebfba35e6f66a11ef0cab7582cc0` |
| `GDPS-GEML_25km_Geopotential_600mb` | 14679 | 2026-09-08T02:14:56.001269+00:00 | `85cbe484dc1f21002c8825e7911814c60473797bf8a2d4f61e910d777d57c8c3` |
| `GDPS-GEML_25km_Geopotential_700mb` | 14679 | 2026-09-08T02:14:56.339753+00:00 | `a1881b24105ce990b21a86e98e47d607085afffe864aa58b749a8d93f9e9f4a1` |
| `GDPS-GEML_25km_Geopotential_850mb` | 14682 | 2026-09-08T02:14:56.674203+00:00 | `d6d49178e414cc9dec0229d7f98150293a571920ca2e7b5307148630457e3d24` |
| `GDPS-GEML_25km_Geopotential_925mb` | 14665 | 2026-09-08T02:14:57.017736+00:00 | `5360b4356edc09aab158ade0a73577ae8087c1db66db328f7f6ccc3c3310decd` |
| `GDPS-GEML_25km_Pressure_MSL` | 16543 | 2026-09-08T02:14:57.364260+00:00 | `7c2f176701343ebd1b833b2dbc6b4c1500d013515557fd8007b2f96209914ed0` |
| `GDPS-GEML_25km_SpecificHumidity_1000mb` | 14597 | 2026-09-08T02:14:57.693876+00:00 | `2c2e8477b6d106b7576326f88395c17b81a26912d789f5b33898250326465478` |
| `GDPS-GEML_25km_SpecificHumidity_100mb` | 14635 | 2026-09-08T02:14:58.020689+00:00 | `883bd0f054dc0defa88449da86bd0631874962d1528a0d824da2f66ff952a57d` |
| `GDPS-GEML_25km_SpecificHumidity_150mb` | 14635 | 2026-09-08T02:14:58.348921+00:00 | `663a6ac7d121b4f33659cd2adffdbb3ede951683192f946f196e6d1676652883` |
| `GDPS-GEML_25km_SpecificHumidity_200mb` | 14641 | 2026-09-08T02:14:58.677152+00:00 | `5031a84bd364708bf2d00a94f12ec2429fc0f2320583be36a7bd4b2487986199` |
| `GDPS-GEML_25km_SpecificHumidity_250mb` | 14641 | 2026-09-08T02:14:59.013587+00:00 | `4a7193d69fc22c1c18889ac30d68061a7c8e05e1f7c5ce3e14e796d3721a89ef` |
| `GDPS-GEML_25km_SpecificHumidity_300mb` | 14641 | 2026-09-08T02:14:59.342656+00:00 | `c204dfed26cd1f6eaa3de6bf10217cb271e23473787f5d99b56e53c6c0d5d447` |
| `GDPS-GEML_25km_SpecificHumidity_400mb` | 14641 | 2026-09-08T02:14:59.675626+00:00 | `af8c152ec1a85177654742b784d77bc0649aa13699c1a2f395fe1a776b58cc0e` |
| `GDPS-GEML_25km_SpecificHumidity_500mb` | 14641 | 2026-09-08T02:15:00.010354+00:00 | `64c1d6f118dab472492e6f9a0191030c6dea49eb1c5ab75e6fdcd2119b11a87b` |
| `GDPS-GEML_25km_SpecificHumidity_50mb` | 14629 | 2026-09-08T02:15:00.339322+00:00 | `f7afe57510c1e5340d4a770de14e953bb93d804940c8ce041f766bdea49640d8` |
| `GDPS-GEML_25km_SpecificHumidity_600mb` | 14641 | 2026-09-08T02:15:00.679582+00:00 | `e322711498eb500f3bdc306094ab2e66a6b3f65e52c0fc63af058bfe4265232b` |
| `GDPS-GEML_25km_SpecificHumidity_700mb` | 14641 | 2026-09-08T02:15:01.109164+00:00 | `cf7954d5807c5412fb29686ef5a7ede714d95fee1bb77d25a2448ef0937d64cd` |
| `GDPS-GEML_25km_SpecificHumidity_850mb` | 14591 | 2026-09-08T02:15:01.446623+00:00 | `18a18b8c2a340dd70eb0cf0107f9e0a5efbac24a1fb02c4c622eb7d5dcc5093a` |
| `GDPS-GEML_25km_SpecificHumidity_925mb` | 14591 | 2026-09-08T02:15:01.779032+00:00 | `e6c5edcc94cf385cf73386e85550b0f68509db8b4478f6ff50498fed2df8c424` |
| `GDPS-GEML_25km_VerticalVelocity_1000mb` | 15200 | 2026-09-08T02:15:02.124116+00:00 | `2ef5a614cde3df071b60c084c5e436566ca2229590c1b973e502ac0b74eeecf7` |
| `GDPS-GEML_25km_VerticalVelocity_100mb` | 15193 | 2026-09-08T02:15:02.461727+00:00 | `4a745eeaf084a84e83489e2848f68eae7d26cde6f4766019167ba37a7c8585a6` |
| `GDPS-GEML_25km_VerticalVelocity_150mb` | 15193 | 2026-09-08T02:15:02.790421+00:00 | `eb3a5d4b050a817129750999a91d8852863d9771fcfa25798b43491441f38d90` |
| `GDPS-GEML_25km_VerticalVelocity_200mb` | 15193 | 2026-09-08T02:15:03.130675+00:00 | `9b3a98323981614f02192db44c03e6953b74ac19240fadfc24b0a8fce24d655c` |
| `GDPS-GEML_25km_VerticalVelocity_250mb` | 15193 | 2026-09-08T02:15:03.454677+00:00 | `d897275bb35aeaf22e74f7079f1b1bce29fd502b710b6eef011605f88372e9e7` |
| `GDPS-GEML_25km_VerticalVelocity_300mb` | 15193 | 2026-09-08T02:15:03.783559+00:00 | `abb2b466b8b60789a1dea4d179d66526db4214b4aabd433d53991b33cd83b1db` |
| `GDPS-GEML_25km_VerticalVelocity_400mb` | 15193 | 2026-09-08T02:15:04.118066+00:00 | `6eb8ff0fe072a3a460d058882ef2c10ec602417632305515d2b1d839fa93b3c9` |
| `GDPS-GEML_25km_VerticalVelocity_500mb` | 15193 | 2026-09-08T02:15:04.455324+00:00 | `a4e7b1606e335faa4ffc3852a07cb7c1cde70b126eb06d3d5385fd5814dc07a6` |
| `GDPS-GEML_25km_VerticalVelocity_50mb` | 15186 | 2026-09-08T02:15:04.797257+00:00 | `84861ffce3bfe2b91042159c23ae73e804947a57588a9c334cc3649cb7596cca` |
| `GDPS-GEML_25km_VerticalVelocity_600mb` | 15193 | 2026-09-08T02:15:05.151389+00:00 | `aee6bb5c93facf219727a3c420d9245185a041920175b90b484711cc5c15eed2` |
| `GDPS-GEML_25km_VerticalVelocity_700mb` | 15193 | 2026-09-08T02:15:05.485279+00:00 | `217dd8021d819c4293f136d4e503ab53f80a2a521d1211ed0f6978c2d94c7a2c` |
| `GDPS-GEML_25km_VerticalVelocity_850mb` | 15193 | 2026-09-08T02:15:05.814430+00:00 | `8afebf65645c21fcc73a7d899dc440733cc4677df465d0f9ec083315438d9ebc` |
| `GDPS-GEML_25km_VerticalVelocity_925mb` | 15193 | 2026-09-08T02:15:06.156191+00:00 | `b0ab86b5e2f87268bb93afbaff0191b2690398251345860c8410a4aea7743ac5` |
| [directory](https://dd.weather.gc.ca/today/model_gdps-geml/) | 524 | 2026-09-08T02:15:06.430745+00:00 | `a3f22308009ee40f03ff07c06233b59281ac85b46356724a0f3a2343ac62e227` |
| [directory](https://dd.weather.gc.ca/20260907/WXO-DD/model_gdps-geml/25km/) | 838 | 2026-09-08T02:15:06.627421+00:00 | `96be3c3dc18a0c6bf043877b13be307634e0110aa95c552127847a46ff0d0437` |
| [directory](https://dd.weather.gc.ca/20260907/WXO-DD/model_gdps-geml/25km/12/) | 5746 | 2026-09-08T02:15:06.904180+00:00 | `0e76903b42006b337f639f4a79ef731fe4b1729bb2ebfc8ffecdf98cb9e4702f` |
| [directory](https://dd.weather.gc.ca/20260907/WXO-DD/model_gdps-geml/25km/12/006/) | 19719 | 2026-09-08T02:15:07.152776+00:00 | `1bd18063e7bc5597688878983f75fa7983e39ec57aa569f09fee59a82b0b1c3d` |

Spec-Impact: none; research/accounting only, no behavior or normative status change.
Verification: exact 54-ID/title/native-filename reconciliation passed; specctl: 0 errors, 0 warnings.
