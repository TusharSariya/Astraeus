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

## Web contract

The spec deltas pin the class name and that a derived value exposes its inputs
and method. They do not pin the JSON, so the client reads the simplest shape
that carries them, and the API owner should match it:

- `provenance.evidence_class`: one of the six strings, required. Absent, empty,
  non-string or outside the six all resolve to one client state,
  `unrecognised`, which renders as unavailable with the reason and never as
  `retrieved`. The two failures are distinguished only in the reason text.
- `provenance.quality`: `{ status, flags }`, with `derived` appearing in
  `flags`. Absent means "not named", never a status this client invented.
- `provenance.derivation_inputs`: a list of
  `{ field, source_id, product, valid_time, quality, evidence_class }`.
  `quality` is accepted as a bare status string or as the same
  `{ status, flags }` object. Read only when the value's own class is
  `derived_here`.
- The method: `provenance.derivation_method` as `{ name, version, citation }`
  is preferred; the flat `derivation` / `derivation_version` /
  `derivation_citation` fields the API publishes today are the fallback, so a
  response that predates the object form still names its method. Also read
  only for `derived_here`: a reprocessed value's `derivation` is the
  intermediary's sentence, not a registered method this deployment can cite.
- `/layers` items carry `evidence_class` as the same six-value string. The
  class is never inferred from `evidence_basis` or the group: a published
  artifact can hold values of any class, and inferring is what the field
  replaces.

Two client decisions the spec left open, recorded here because they are
visible behaviour:

- **A missing class suppresses the value.** The spec's scenario names an
  unrecognised class; the field is required with no default, so a value
  carrying none has no honest class either and is treated identically.
- **An unrecognised class on a LAYER does not withhold the imagery.** The
  drawer shows the unrecognised badge and the reason sentence beside the row.
  Withholding a whole layer's pixels is a fallback-rules decision
  (`frame-fallback-and-viewport-layout`), not this change's, and is left to
  the owner.

## Open questions carried into implementation

- Whether existing derived artifacts (cloud motion, the WEonG repair) are
  re-classed in place or republished; the manifest gains `evidence_classes`
  either way.
- The exact validation tolerance for a method's physical range clamp and how
  a clamped value is flagged.
