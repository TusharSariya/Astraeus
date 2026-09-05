# Named Open-Meteo pressure-profile evidence

Research note, 2026-09-05. This is non-normative evidence for issue 98 and the
unregistered `experimental-openmeteo-brightsky` change only.

## Official declarations

The official [JMA API](https://open-meteo.com/en/docs/jma-api),
[Meteo-France API](https://open-meteo.com/en/docs/meteofrance-api), and
[UKMO API](https://open-meteo.com/en/docs/ukmo-api) pages expose eight
pressure-level response families: temperature, relative humidity, dew point,
cloud cover, wind speed, wind direction, vertical velocity and geopotential
height. Their native-variable tables distinguish producer fields from
Open-Meteo transformations:

- JMA and ARPEGE publish temperature, RH, U/V wind, geopotential and vertical
  velocity. Open-Meteo computes dew point and pressure-level cloud from RH and
  speed/direction from U/V.
- UKMO publishes temperature, RH, wind speed/direction, geopotential and
  vertical velocity. Open-Meteo computes dew point and pressure-level cloud
  from RH.

No page states whether producer RH is relative to liquid, ice, or a mixed
phase. It is retained as raw `%` response data with `raw_phase_unknown`, never
published under Astraeus's phase-required canonical RH key. Dew point and
pressure cloud are retained as explicitly `intermediary_derived`. Open-Meteo's
geometric vertical speed in `m/s` is not renamed to Astraeus omega (`Pa/s`),
and its height in `m` is not renamed to the catalogue's GRIB `gpm` field.

## Bounded live inventory

Three calls, one per exact `models=` selector, requested one forecast hour at
47.5615 N, 52.7126 W. All returned HTTP 200 for 2026-09-05T15:00Z. A level
listed as missing was present as an array of JSON nulls; it was not absent from
the response. No interpolation or replacement was applied.

| Model | Official pressure surfaces | Live field/level result |
|---|---|---|
| JMA GSM | 1000, 975, 950, 925, 900, 850, 800, 700, 600, 500, 400, 300, 250, 200, 150, 100 hPa | Temperature, wind speed/direction, vertical velocity and geopotential retrieved at 1000, 925, 850, 700, 600, 500, 400, 300, 250, 200, 150, 100; 975, 950, 900 and 800 were null. RH, dew point and cloud retrieved at 1000, 925, 850, 700, 600, 500, 400 and 300; those same four intermediate levels plus 250, 200, 150 and 100 were null. |
| ARPEGE World 0.25° | 1000, 950, 925, 900, 850, 800, 750, 700, 650, 600, 550, 500, 450, 400, 350, 300, 275, 250, 225, 200, 175, 150, 125, 100, 70, 50, 30, 20, 10 hPa | Temperature, RH, cloud, wind speed/direction and geopotential retrieved at all 29. Dew point retrieved from 1000 through 125 and was null at 100, 70, 50, 30, 20 and 10. Vertical velocity was null at all 29 and its unit was the literal `undefined`, despite the official native-variable table listing the field. |
| UKMO Global 10 km | 1000, 975, 950, 925, 900, 850, 800, 750, 700, 650, 600, 550, 500, 450, 400, 375, 350, 325, 300, 275, 250, 225, 200, 175, 150, 125, 100, 70, 50, 40, 30, 20, 10 hPa | Temperature, RH, cloud, wind speed/direction, vertical velocity and geopotential retrieved at all 33. Dew point retrieved from 1000 through 125 and was null at 100, 70, 50, 40, 30, 20 and 10. |

The retained bundle is under
[`evidence/openmeteo-profiles-20260905`](evidence/openmeteo-profiles-20260905/summary.json).
It contains the three response bodies, deterministic zipped-Zarr profile
artifacts, provenance, and real `LiveStore` `/profile` readbacks at all 16 JMA,
29 ARPEGE and 33 UKMO advertised levels. The corrected artifacts were derived
from the retained response bodies with zero new provider requests; the original
capture time and response hashes remain unchanged, while regenerated artifact
hashes and the reprocessing time are explicit in `summary.json`.

Canonical completeness is assessed for temperature, wind speed and wind
direction at every advertised level and retained valid time. JMA's canonical
arrays are null at 975, 950, 900 and 800 hPa, so its corrected result is
`complete=false`, `qc_passed=true` and cannot advance the prior visible
revision. ARPEGE and UKMO are complete for their canonical arrays. Raw/deferred
fields remain available for inspection even when null; each provenance entry
keeps its own values, missing mask, literal response unit, delivery class,
pressure and valid times. The Zarr pressure coordinate itself carries `hPa`,
`positive=down` and `standard_name=air_pressure`, verified after reopening the
stored artifact. These artifacts remain experimental and do not register or
schedule any source.
