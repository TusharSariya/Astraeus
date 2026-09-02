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

## What the registry entries look like, and why two start disabled

Decided while implementing tasks 3 and 4, and recorded here rather than left
to the reader of the code:

- **An entry may produce more than one field.** The spec names "wind speed and
  direction" and "the Sun and Moon geometry fields" as single constructions, so
  an entry carries `outputs`, each with its own field, units, physical range
  and range rule. A one-output entry is the common case, not the only one.
- **Ensemble statistics and sector sampling are registered `enabled: false`.**
  Both are required entries and neither has an implementation yet: member
  retrieval arrives with `ensemble-members-and-source-plurality` and the sector
  sampler with the point work. Registering them enabled would declare a
  construction this deployment cannot perform. They are entries, approved, and
  switched off at the first of the three levels until their code exists.
- **The no-blend rule reads the field family, not the field name.** The spec's
  own blending scenario combines `total_cloud_opacity_weighted` from HRDPS with
  `total_cloud_geometric` from GFS - two different catalogue names for one
  family. So each input declares its family and its source, and two members of
  one family from two sources are refused as blending, as is the same field
  from two sources and a provider reduction mixed with another member set.
- **`delivery_kind` is required on every record, and this change is where it
  landed.** The obligation belongs to `ensemble-members-and-source-plurality`,
  which specified the field and did not implement it, so task 4.0 carries it
  here rather than leaving 4.1 extending a field that does not exist. All 64
  records declare a kind: 60 `published_cell`, 3 `reprocessed` (MADIS, OpenAQ
  and the CWOP route through findu.com - the three places where a third party
  stands between the producer and this deployment and transforms what it
  passes on), and 1 `intermediary_derived`. `_source` takes it keyword-only
  with no default, so the next aggregator record cannot inherit
  `published_cell` in silence.
- **Display-primary eligibility is a field the audit enforces, not prose.**
  Every record carries `display_primary`, which follows from its kind unless
  the record overrides it, and the audit refuses any record that claims the
  primary while its values are not the producer's own cell. The spec says the
  audit enforces this "rather than leaving it to the display layer", which
  needs something in the record for the display layer to read.
- **The producer-direct kind is `published_cell`, not `retrieved`.** Both spec
  deltas name it that way, and the two axes are separate on purpose: a
  delivery kind says whose cell a value is, an evidence class says how the
  value came to exist. An `intermediary_derived` value is still retrieved by
  this deployment, so reusing `retrieved` for the delivery kind would make one
  word mean two things.

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

## Web contract

The shape below is the API's, as `api/weather_api/models.py` publishes it
(merged 2026-09-02). Provenance is FLAT: there is no nested method object and
no nested delivery object. The client reads the flat fields as its contract.

- `provenance.evidence_class`: one of the six strings, required, no default.
  Absent, empty, non-string or outside the six all resolve to one client
  state, `unrecognised`, which renders as unavailable with the reason and
  never as `retrieved`. The two failures are distinguished only in the reason
  text.
- `provenance.quality`: `{ status, flags }`. `flags` carries `derived` for a
  derived value, and the two refusal flags below. Absent means "not named",
  never a status this client invented.
- **The method, flat**: `derivation` (the registry entry name),
  `derivation_version`, `derivation_citation`. A nested
  `derivation_method: { name, version, citation }` is still read first because
  it costs three lines, but nothing produces it; the flat fields are the
  contract. Read only when the value's own class is `derived_here`: a
  reprocessed value's `derivation` is the intermediary's sentence, not a
  registered method this deployment can cite.
- `provenance.derivation_inputs`: a list of
  `{ field, source_id, product, valid_time, run_time, units, evidence_class,
  quality }`, `quality` being the same `{ status, flags }` object (a bare
  status string is also accepted, for a hand-written response).
- **Delivery, flat**: `delivery_kind` (`published_cell` | `reprocessed` |
  `intermediary_derived`), `intermediary`, `intermediary_method`. The label
  beside the class badge is "producer's own cell", "reprocessed by
  <intermediary>", "computed by <intermediary>". A kind the client does not
  know, or none at all, renders NO label — see the decisions below.
- `provenance.display_primary_eligible`: the API computes it from the class.
  When it is absent the client reads the class directly and refuses
  `reprocessed`, `intermediary_derived` and `uncalibrated_observation`, so a
  missing field can never promote one of the three into a reading.
- **Refusals**: `quality.flags` carries `derivation_refused` (the registry
  conditions refused a derived value) or `provenance_unmodelled` (an
  artifact's provenance could not be modelled). The reason lives only in the
  response's `notices`, as
  `artifact from <source> (revision <id>) was skipped: <reason>`. The client
  matches a notice to the field by the field name, falling back to the source
  id — an unmodelled artifact's notice names the artifact, not each field.
- `/catalog` source records carry `delivery_kind`, `intermediary` and
  `display_primary`. All three are optional on the client until every record
  declares them.
- `/layers` items carry `evidence_class` as the same six-value string. The
  class is never inferred from `evidence_basis` or the group: a published
  artifact can hold values of any class, and inferring is what the field
  replaces.

Client decisions the spec left open, recorded here because they are visible
behaviour:

- **A missing class suppresses the value.** The spec's scenario names an
  unrecognised class; the field is required with no default, so a value
  carrying none has no honest class either and is treated identically.
- **A missing delivery kind is silent.** The opposite decision, and
  deliberately so: the kind is a registry attribute, so an undeclared one is a
  gap in the registry rather than a failure of the evidence, and a "delivery
  unknown" chip beside a good retrieved value would read as a doubt about the
  value. An undeclared CLASS is a doubt about the value; an undeclared KIND is
  not.
- **An unrecognised class still occupies the reading's slot.** It is refused
  as a value but not demoted to an alternative: the fault must be visible
  where the number would have been, not tucked inside a disclosure panel. Only
  the three declared non-primary classes, and a source the catalogue refuses,
  become alternatives.
- **Non-primary values are shown, never hidden.** They are collected under
  "Retrieved, but never the reading", driven by the whole alternatives record
  rather than wired metric by metric, so a field with no metric of its own
  cannot be silently dropped. A field whose ONLY value is non-primary reads as
  Unknown with that value beside it.
- **Alternatives are not unit-converted.** The metrics convert; an alternative
  prints the value in the unit its own response declared, because it exists to
  be compared with the source it names.
- **Alerts ignore the primary rule.** An alert is a published hazard text, not
  a reading to be outranked, so `warnings` reads from every field. Withholding
  a warning to satisfy a rule about numbers would be the worse error.
- **An unrecognised class on a LAYER does not withhold the imagery.** The
  drawer shows the unrecognised badge and the reason sentence beside the row.
  Withholding a whole layer's pixels is a fallback-rules decision
  (`frame-fallback-and-viewport-layout`), not this change's, and is left to
  the owner.

## Open questions carried into implementation

- Whether existing derived artifacts (cloud motion, the WEonG repair) are
  re-classed in place or republished; the manifest gains `evidence_classes`
  either way.
- ~~The exact validation tolerance for a method's physical range clamp and how
  a clamped value is flagged.~~ **Answered.** There is no tolerance, because a
  tolerance is a second bound nobody declared. Each output declares one of four
  range rules: `clamp` bounds the value and flags it `range_clamped`; `wrap`
  folds a circular quantity such as a bearing into its interval and flags it
  `range_wrapped`; `null` refuses the value and flags it `range_refused`; and
  `inherit_input_range` says the bound is the input field's own published
  range, which is the honest answer for a statistic over an arbitrary field.
