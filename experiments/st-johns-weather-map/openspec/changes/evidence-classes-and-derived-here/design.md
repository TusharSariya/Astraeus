# Design

## Why a class is a field and not an inference

Three signals stand in for a class today: `derivation` set, `evidence_basis`
of `live_proxy`, and the generated flag on motion artifacts. Each was added
for one feature and none knows about the others, which is how a generated
WEonG repair reached `/point` and `/profile` on 2026-09-01: the name match in
`LiveStore.sample_point` stopped matching when the artifact's name grew a
layer suffix. A required field with no default cannot be forgotten, and a
`StrictModel` refuses a provenance that lacks it, so the failure mode becomes
a validation error at publication rather than a silent promotion at read time.

## Why six, and what each answers

Each class answers one question, "how did this number come to exist", and the
six are disjoint:

| class | who computed it | what this deployment did |
| --- | --- | --- |
| `retrieved` | the producer | fetched it as issued |
| `reprocessed` | the producer | fetched it after an intermediary transformed it (regrid, downscale, interpolate); intermediary and every transformation named |
| `derived_here` | this deployment | computed it from retrieved inputs by a registered, cited method |
| `intermediary_derived` | an intermediary | fetched a value the intermediary computed from the producer's fields by its own method; nothing the producer issued |
| `generated_display` | this deployment | interpolated between retrieved frames for display only |
| `uncalibrated_observation` | a citizen or personal instrument | fetched it; never used for verification |

`intermediary_derived` exists because the owner chose to admit Open-Meteo's
cloud for WeatherNext 2. It is not reprocessed (nothing was transformed) and
not derived-here (this deployment did not compute it and cannot cite the
method). Naming it lets the value in with an honest label and the reprocessed
limits.

## Why derived-here is per value and reads across sources

Relative humidity derived beside a retrieved temperature from the same HRDPS
artifact makes the class per value; per artifact would force two artifacts
for one run. Air-sea difference needs CIOPS-East sea-surface temperature and
HRDPS dew point, so inputs come from any number of sources. What keeps this
from becoming consensus by another name is the field, not the source count:
inputs are different fields combined by a physical relation, never the same
field averaged across centres.

## Why quality is the worst input plus a flag

A fifth `Quality.status` would break every consumer that switches on the four
existing values. A `derived` flag on the existing status keeps the contract,
and "no better than the worst input" is the only rule that cannot launder a
suspect input into a passed output. A method may downgrade further (a fog
closure that saw no valid cloud top says `unknown`), never raise.

## Why failures are isolated per artifact

`open` already skips a corrupt artifact and keeps answering from the rest;
`live_provenance` did not, so one unmodelled field took down every source in
a response. The same per-artifact isolation applies to provenance modelling:
the offending artifact yields `null` and a notice naming it, the rest answer.

## What generated-display does not change

Every carve-out in `openspec/config.yaml` for interpolated and generated
display frames stands as written. This change gives that behaviour its class
name and reasserts that it never reaches a data path. The three-level kill
switch (registry `enabled`, `WEATHER_GENERATED_DISPLAY=off`, reader menu) is
the model for the derivation method registry's own enabling levels.

## The seam between the API and the derivation method registry

`weather_api.store` reads the registry through one function,
`ingest.derive.registry.get_entry(name)`, which returns the entry or `None`.
An entry carries `name`, `version`, `citation`, `inputs`, `output`,
`physical_range` (a low/high pair or `None`), `range_rule` (`clamp` or
`refuse`) and `enabled`; an entry with more than one output declares
`physical_range_by_output` keyed by served field name, because wind speed and
wind direction come from one entry and share no range. The API names three
entries: `relative_humidity_from_dew_point`,
`wind_speed_and_direction_from_components` and
`fog_state_from_present_weather`. A registry that cannot be imported, exposes
no `get_entry`, or knows the name but has it disabled all resolve the same
way: the method is not enabled, the value is `null` with a notice, and no
unregistered construction is substituted.

## What class an absent value carries

`evidence_class` is required on every provenance, including the placeholder a
response uses for a value that does not exist. The placeholder states the
class the absent value would have carried - `retrieved` for a field nothing
retrieved, `derived_here` for a derivation that was refused. What says the
value is absent is the null value beside it, the `unavailable` data mode and
the `no_retrieval` flag, never the class, so no reader can mistake a
placeholder for a reading.

## Open questions carried into implementation

- Whether existing derived artifacts (cloud motion, the WEonG repair) are
  re-classed in place or republished; the manifest gains `evidence_classes`
  either way.
- The exact validation tolerance for a method's physical range clamp and how
  a clamped value is flagged.
