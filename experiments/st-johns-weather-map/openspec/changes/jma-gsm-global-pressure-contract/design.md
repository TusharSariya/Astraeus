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

| hPa | Producer T | Producer RH | Producer U/V | Producer omega | Producer geopotential | Open-Meteo dew/cloud | Contract disposition |
|---:|---|---|---|---|---|---|---|
| 1000 | yes | yes | yes | yes | yes | derived from T/RH | required |
| 975 | no | no | no | no | no | unavailable | producer-unsupported |
| 950 | no | no | no | no | no | unavailable | producer-unsupported |
| 925 | yes | yes | yes | yes | yes | derived from T/RH | required |
| 900 | no | no | no | no | no | unavailable | producer-unsupported |
| 850 | yes | yes | yes | yes | yes | derived from T/RH | required |
| 800 | no | no | no | no | no | unavailable | producer-unsupported |
| 700 | yes | yes | yes | yes | yes | derived from T/RH | required |
| 600 | yes | yes | yes | yes | yes | derived from T/RH | required |
| 500 | yes | yes | yes | yes | yes | derived from T/RH | required |
| 400 | yes | yes | yes | yes | yes | derived from T/RH | required |
| 300 | yes | yes | yes | yes | yes | derived from T/RH | required |
| 250 | yes | no | yes | yes | yes | unavailable | required except RH/dew/cloud |
| 200 | yes | no | yes | yes | yes | unavailable | required except RH/dew/cloud |
| 150 | yes | no | yes | yes | yes | unavailable | required except RH/dew/cloud |
| 100 | yes | no | yes | yes | yes | unavailable | required except RH/dew/cloud |

JMA global also publishes temperature, U/V, omega and geopotential at 70, 50,
30, 20 and 10 hPa. Open-Meteo's JMA endpoint does not expose those levels in
the documented pressure selection. They are recorded as
`intermediary_unexposed`, outside the required access-path inventory.

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

JMA publishes omega on pressure surfaces. Open-Meteo returns geometric
vertical velocity in `m/s`; it remains raw and incompatible with the existing
canonical omega key. Geopotential/height response semantics remain raw until
their unit mapping is accepted. Neither is silently relabelled.

The pressure coordinate remains hPa with `positive=down` and no vertical
interpolation. Open-Meteo's hourly interpolation from the native six-hourly
global forecast is declared as intermediary temporal processing. Rolling
responses keep run identity unknown unless a value-level run reference is
available.

## Completeness and failure behavior

Source completeness requires every value/time cell for:

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

