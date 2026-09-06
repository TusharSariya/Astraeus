# Design

## Contract boundary

The contract is for one producer product and access path: JMA global GSM
delivered through the exact Open-Meteo `jma_gsm` selector. JMA's Japan-area
GSM and MSM products are different products with different geography. Other
forecast models are different sources.

Source completeness answers whether the access path retrieved the fields
declared for global GSM. Consumer suitability answers whether an artifact
satisfies a downstream profile. These verdicts remain independent. A source
artifact may be complete at 12 levels and still be unusable by a consumer
whose contract requires all 16 old levels.

## Field inventory

The 16 old selection levels receive explicit dispositions:

| hPa | Temperature | RH | Dew point | Cloud | Wind speed | Wind direction | Vertical velocity | Geopotential height |
|---:|---|---|---|---|---|---|---|---|
| 1000 | producer-origin | producer-origin | derived T/RH | derived RH | derived U/V | derived U/V | converted omega/T | reprocessed producer field |
| 975 | unsupported | unsupported | unsupported | unsupported | unsupported | unsupported | unsupported | unsupported |
| 950 | unsupported | unsupported | unsupported | unsupported | unsupported | unsupported | unsupported | unsupported |
| 925 | producer-origin | producer-origin | derived T/RH | derived RH | derived U/V | derived U/V | converted omega/T | reprocessed producer field |
| 900 | unsupported | unsupported | unsupported | unsupported | unsupported | unsupported | unsupported | unsupported |
| 850 | producer-origin | producer-origin | derived T/RH | derived RH | derived U/V | derived U/V | converted omega/T | reprocessed producer field |
| 800 | unsupported | unsupported | unsupported | unsupported | unsupported | unsupported | unsupported | unsupported |
| 700 | producer-origin | producer-origin | derived T/RH | derived RH | derived U/V | derived U/V | converted omega/T | reprocessed producer field |
| 600 | producer-origin | producer-origin | derived T/RH | derived RH | derived U/V | derived U/V | converted omega/T | reprocessed producer field |
| 500 | producer-origin | producer-origin | derived T/RH | derived RH | derived U/V | derived U/V | converted omega/T | reprocessed producer field |
| 400 | producer-origin | producer-origin | derived T/RH | derived RH | derived U/V | derived U/V | converted omega/T | reprocessed producer field |
| 300 | producer-origin | producer-origin | derived T/RH | derived RH | derived U/V | derived U/V | converted omega/T | reprocessed producer field |
| 250 | producer-origin | unavailable | unavailable | unavailable | derived U/V | derived U/V | converted omega/T | reprocessed producer field |
| 200 | producer-origin | unavailable | unavailable | unavailable | derived U/V | derived U/V | converted omega/T | reprocessed producer field |
| 150 | producer-origin | unavailable | unavailable | unavailable | derived U/V | derived U/V | converted omega/T | reprocessed producer field |
| 100 | producer-origin | unavailable | unavailable | unavailable | derived U/V | derived U/V | converted omega/T | reprocessed producer field |

JMA global also publishes temperature, U/V, omega and geopotential at 70, 50,
30, 20 and 10 hPa. The pinned Open-Meteo ingest code explicitly drops those
messages because they use a different grid. They are recorded as
`intermediary_dropped`, outside the candidate access-path inventory.

## Representation and provenance

Temperature and U/V-derived wind speed/direction may remain canonical
reprocessed values at the 12 required levels. RH remains raw because JMA and
Open-Meteo do not declare a saturation-phase convention. Every RH entry names
JMA as producer and records `raw_phase_unknown`.

Dew point and pressure-level cloud are not producer fields. They name JMA
temperature/RH as inputs, Open-Meteo as deriving intermediary, the documented
derivation identity, response units, and missing masks. They are retained as
intermediary-derived evidence and are not promoted to canonical producer
observations.

JMA publishes omega on pressure surfaces. Open-Meteo converts omega with
temperature to geometric vertical velocity and formats it in the requested
wind-speed unit. It remains intermediary-derived and incompatible with the
existing canonical omega key. Open-Meteo also applies transformations to the
producer geopotential field. Geopotential-height semantics remain
intermediary-reprocessed until the conversion is accepted.

The pressure coordinate remains hPa with `positive=down` and no vertical
interpolation. Open-Meteo's hourly interpolation from the native six-hourly
global forecast is declared as intermediary temporal processing. Rolling
responses keep run identity unknown unless a value-level run reference is
available.

## Completeness and failure behavior

This is a candidate completeness inventory only. It cannot authorize a source
completeness verdict until model/run identity and the transformations above
have an owner-approved provenance rule. If that rule is later accepted,
completeness would require every value/time cell for:

- temperature, wind speed, and wind direction at 1000, 925, 850, 700, 600,
  500, 400, 300, 250, 200, 150, and 100 hPa;
- raw RH and intermediary-derived dew point/cloud at 1000, 925, 850, 700, 600,
  500, 400, and 300 hPa; and
- raw vertical velocity and geopotential height at the 12 required levels.

Null or omitted cells in that inventory make the source artifact incomplete.
Nulls at 975, 950, 900, and 800 hPa are preserved and reported as
producer-unsupported; they do not become zero, interpolated, or complete.

A consumer requiring the old 16 canonical levels receives an unsatisfied
profile verdict even if this source artifact is complete. The source artifact
must not be registered, scheduled, admitted, used for science, or treated as
operational solely because this draft exists or because a source-completeness
check passes.

## Rollback

Before acceptance there is no runtime change to roll back. If a later
implementation is withdrawn, restore the current 16-level partial verdict and
publication refusal; retained masks and provenance remain valid evidence.
