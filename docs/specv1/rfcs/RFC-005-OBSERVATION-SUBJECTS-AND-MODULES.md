---
id: RFC-005
title: Observation Subjects and Modules
type: rfc
status: proposed
owners:
  - "@TusharSariya"
profiles:
  - event_day_preview
  - v1_web
  - v1_native
created: 2026-08-11
updated: 2026-08-11
depends_on:
  - RFC-000
  - RFC-001
supersedes: []
---

# RFC-005 — Observation subjects and modules

## Summary

Astraeus plans an optical observation of a selected `ObservationSubject`. A
subject may be a persistent target, scheduled occurrence, forecast phenomenon,
or discovered transient. A versioned observation module owns the physics,
evidence needs, detectability model, safety policy, scoring rule, and typed
request/result extension for each supported family.

The August 12, 2026 eclipse remains the first complete release slice. The
profiles below describe extensibility; they do not claim that non-eclipse
science, providers, scores, or geographic coverage are implemented.

## SYS-SUBJ-001 — Model targets and occurrences explicitly

`ObservationSubject` is the public umbrella concept. It MUST distinguish:

- `persistent_target`: a target such as Jupiter, an asteroid, star, or galaxy;
- `scheduled_occurrence`: an eclipse, occultation, conjunction, transit, or
  meteor-shower interval;
- `forecast_phenomenon`: aurora, airglow, or another forecast optical state;
- `discovered_transient`: a nova, supernova, new comet, or alert-discovered
  target.

Every request identifies `module_id` and `subject_id`. An occurrence-bound
subject also supplies `occurrence_id`; a persistent target MUST NOT be forced to
invent one. Subject identity is distinct from the user's observation objective
and equipment profile.

## SYS-MOD-001 — Give every supported subject one versioned module owner

Each supported subject family MUST resolve to exactly one active observation
module for a given module major version. The module declares:

```text
identity and semantic version
subject and occurrence classes
resolve subject or occurrence
validate observation profile
temporal and spatial validity
direction, angular extent, or sky region over time
critical subwindows and duration rules
required and optional evidence classes
physical signal and detectability evaluation
module-specific safety gates
applicable score components and scoring rule
typed request and result schemas
provenance and mapped verification
```

Provider formats still terminate at adapters. A module consumes normalized
evidence and MUST NOT make clients or renderers authoritative scientific
pipelines.

## SYS-MOD-002 — Declare capabilities instead of assuming common physics

The schema-validated observation-module registry is the machine-readable source
of module identity and capability declarations. It records subject classes,
occurrence semantics, geometry types, supported optical modes/objectives,
required evidence, contract references, rules, limitations, and verification.

Direction geometry is one of `point`, `disc`, `track`, `sky_region`,
`extended_field`, `full_sky`, or `volume`. Modules MUST evaluate the changing
geometry throughout each useful window. A point-target assumption cannot be
silently applied to an auroral volume, meteor radiant, eclipse track, comet
tail, or full-sky observation.

## SYS-MOD-003 — Keep subject-specific physics outside the common optimizer

The common optimizer owns candidate iteration, time framing, eligibility,
route/access/site gates, revision freezing, window aggregation, and ranked
decision output. A module owns occurrence resolution, physical opportunity,
geometry, brightness or signal semantics, background contrast, equipment
detectability, critical intervals, and subject-specific safety.

Modules compose common atmosphere, obstruction, darkness, Moon, light-
pollution, seeing, wind, dew, and operational evidence only when applicable.
They MUST NOT add an irrelevant factor merely to conform to a universal score.

## SYS-MOD-004 — Fail closed for unsupported or incomplete modules

Only a registry entry with `status: active`, owner approval, accepted owning
specifications/contracts/rules, and passing mapped verification may execute in
a production profile. Unknown, planned, proposed, version-incompatible,
geographically unsupported, or contract-mismatched modules return a typed
unsupported-module error and no recommendation.

No generic catch-all payload, arbitrary module JSON, default science model, or
closest-looking module substitution is permitted.

## SYS-SCORE-001 — Preserve applicability and comparison boundaries

Every common score component declares `applicable` or `not_applicable`. An
applicable component has a value only when its accepted rule has sufficient
evidence. Missing, stale, outside-coverage, or failed-QC evidence remains
missing and MUST NOT become zero, perfect, clear, safe, or not applicable.

Planning scores may be compared only when `module_id`, module major version,
`subject_id`, occurrence where applicable, objective, observation profile, and
scoring version match. Cross-subject discovery or ranking requires a separate
accepted calibration and utility specification.

The backend derives `comparison_key` as `cmp_` plus the unpadded base64url
SHA-256 digest of RFC 8785 canonical JSON containing exactly those comparison
fields. Clients compare the opaque key and MUST NOT independently recreate a
more permissive equivalence relation.

The shared component vocabulary is:

- physical signal potential;
- geometric visibility;
- atmospheric transmission;
- background contrast;
- observer/equipment detectability;
- usable duration;
- operational feasibility;
- travel-adjusted utility.

## SYS-SAFE-001 — Keep module safety outside score tradeoffs

Each module declares its subject-specific safety policy. Safety gates are
evaluated independently of viewing utility and cannot be offset by score. Solar
modules preserve certified-viewer and objective-filter rules; other modules do
not inherit a meaningless solar acknowledgement. Common access, route, weather,
coastal, driver, and site-safety gates continue to apply where relevant.

Missing, stale, or contradictory required safety policy or evidence blocks
module activation or returns `no_reliable_recommendation`.

## SYS-EXT-001 — Add modules through reviewed contracts

Adding a production module requires an accepted module/feature specification,
registry entry, typed request and result discriminator variants, science/data/
safety ownership, versioned scoring rules, provenance behavior, and mapped
verification. Capability-table membership alone does not authorize execution.

The public API remains stable while its closed request/result unions gain
reviewed module variants. Removing or incompatibly changing a variant requires
a major contract version or an explicit migration specification.

## Planned capability profiles

| Family | Examples | Geometry | Dominant module uncertainty |
|---|---|---|---|
| Solar | eclipses, transits, solar features | disc/track | clouds, safety, activity |
| Lunar | phases, lunar eclipses, occultations | disc/track | clouds, horizon, convention |
| Solar-system target | planets, dwarf planets, asteroids, NEOs | moving point/disc | brightness, ephemeris |
| Comet | periodic and newly discovered comets | point/extended field | brightness, morphology |
| Stellar/deep sky | stars, variables, clusters, nebulae, galaxies | point/extended field | transparency, seeing, background |
| Meteor activity | annual showers and outbursts | sky region/full sky | rate profile, cloud, Moon |
| Aurora | oval, arcs, diffuse emission | sky region/volume | space weather, motion, contrast |
| Transient | nova, supernova, transient alert | point/extended field | discovery state, brightness |
| Multi-body occurrence | conjunctions, occultations, transits | point/track | timing, path, orbit |
| Atmospheric astronomical scene | sunrise, sunset, twilight, zodiacal light, airglow | sky region | 3-D cloud, aerosol, illumination |
| Orbital pass | ISS and artificial satellites | moving track | orbit, illumination, manoeuvre |

These planned profiles cover human-visible optical observation: naked eye,
binoculars, telescopes, fixed cameras, and tracking cameras. Radio, infrared
beyond ordinary optical-camera response, ultraviolet, X-ray, neutrino,
cosmic-ray, and gravitational-wave facilities are outside V1.

## Compatibility and migration

The draft API has no production consumers. Replace `/v1/eclipse/plans` with
generic `/v1/plans` and make the solar-eclipse request the first typed union
variant. Preserve all `ECL26-*` requirements and regression controls in the
eclipse feature; it composes this RFC rather than becoming generic physics.

## Verification

The module registry, OpenAPI union, evaluation revision, and eclipse regression
suite jointly verify this RFC. An unsupported module fixture must fail before
provider access, scoring, route generation, or recommendation creation.
