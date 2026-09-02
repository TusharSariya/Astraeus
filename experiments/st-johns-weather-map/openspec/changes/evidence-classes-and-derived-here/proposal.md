## Why

The governing rule says nothing is displayed or returned that was not
retrieved. It gave a value two honest origins: retrieved as the producer
issued it, or reprocessed by a declared intermediary. Everything else was
pushed into display-only carve-outs, and every attempt to serve a quantity
the producers do not publish for this peninsula collided with the rule. The
four activities this foundation serves need exactly such quantities:
air-sea temperature difference for Grand Banks fog, seeing from model levels,
dew point depression against a cooled optic, wet-bulb globe temperature, cloud
in the sunrise sector along a bearing. Each is a physical construction over
retrieved inputs, not a blend, and one of them, relative humidity from
temperature and dew point, is already served under
`point-evidence-sampling` without a class to call its own.

The code confirms the gap. `Provenance` in `api/weather_api/models.py` has
no class field, so a value's origin is inferred today from three unrelated
signals: a `derivation` name, an `evidence_basis` of `live_proxy`, or a
generated flag. `Quality.status` allows only `passed`, `suspect`, `failed`
and `unknown`, which is why a derived artifact whose QC status was `derived`
failed a whole `/point` response on 2026-09-01 (hard-won fact, last entry in
`openspec/config.yaml`). The registry's `delivery_kind` from
`ensemble-members-and-source-plurality` says how a source's values arrive,
but says nothing about a value this deployment computed.

The owner decided on 2026-09-02 (wayfinder tickets 17 and 25, ADR 0001 at
`docs/adr/0001-five-evidence-classes.md`, glossary at `CONTEXT.md`) that
every value carries one of six evidence classes, and that a class called
derived-here is allowed on every data path under conditions strict enough
that the governing rule still holds. This change writes that decision into
the specification. It changes no adapter and promotes no source.

## What Changes

- **Six evidence classes, one required field.** Every provenance record
  carries `evidence_class`, one of `retrieved`, `reprocessed`,
  `derived_here`, `intermediary_derived`, `generated_display`,
  `uncalibrated_observation`, with no default. The class is never inferred
  from a derivation name, a basis flag or a generated flag.
- **Per value, recorded per artifact.** The class rides on each value; an
  artifact records the set of classes it contains so storage and QC gates can
  act on it.
- **Derived-here is admitted on data paths** (`/point`, `/profile`,
  `/timeline`, `/features` and the map) only when all four hold: every input
  is a retrieved value, from any number of sources, each listed with its own
  provenance; the method is an enabled entry in an owner-approved derivation
  method registry (name, version, citation, inputs, physical range); the
  result is bounded to the method's declared physical range; and the result's
  quality is no better than the worst input's.
- **The no-blend rule is restated, not relaxed.** Combining different fields
  is derivation. Combining the same field across centres is blending and stays
  forbidden. Combining a provider's reduction with a statistic over a different
  member set stays forbidden.
- **A source's published field is never replaced** by a derivation for that
  source. The existing relative-humidity rule becomes the general case.
- **Reprocessed, intermediary-derived and uncalibrated values** are never the
  display primary and never a derivation input. Intermediary-derived is new:
  an intermediary computed the value from a producer's retrieved fields by the
  intermediary's own method; producer, intermediary and method (where
  documented) are named. First member: Open-Meteo's cloud cover for Google
  WeatherNext 2, a model that publishes no cloud.
- **Generated-display is unchanged** under its new name: every carve-out in
  `openspec/config.yaml` and the three-level kill switch stand, and it never
  reaches a data path.
- **Provenance failures are isolated per artifact.** An artifact whose
  provenance cannot be modelled yields `null` with a notice for its own
  fields and never fails the response. `Quality` gains a `derived` flag
  rather than a fifth status, so the four-status contract holds.
- **Every value shows its class** to the reader, retrieved included, with a
  legend, so the absence of a badge never carries meaning.

## Capabilities

### New Capabilities

- `derivation-method-registry`: the owner-approved registry that gates every
  derived-here value; its shape, approval, enabling levels and the rule that a
  method is never fitted to the pictures it produces.

### Modified Capabilities

- `evidence-truth-boundary`: adds the six-class declaration, the derived-here
  admission conditions, the limits on reprocessed, intermediary-derived and
  uncalibrated values, the derived-quality rule and per-artifact isolation of
  provenance failures.
- `point-evidence-sampling`: generalises "relative humidity is derived only
  when not published" to every field, and requires the derivation registry
  for any derived value it serves.
- `source-registry-catalogue`: adds `intermediary_derived` beside
  `published_cell` and `reprocessed` as a delivery kind a record may declare,
  with the producer, intermediary and method fields it must carry.
- `web-evidence-interface`: every value and layer carries a class badge and
  the legend names all six.

## Impact

- `api/weather_api/models.py`: `Provenance.evidence_class` (required, no
  default), `Quality.flags` gains `derived`, artifact manifests gain
  `evidence_classes`.
- `api/weather_api/store.py`: `LiveStore.sample_point` and `_sample_dataset`
  isolate provenance failures per artifact; derived artifacts are admitted
  by class, never by name match.
- `ingest/manifest.py`: `RequiredField.evidence_class` and
  `RunManifest.evidence_classes`, and the manifest block each artifact records
  in its own provenance for the store to admit it by.
- `ingest/derive/`: a `registry.py` for derivation methods mirroring the
  interpolation method registry; existing methods (relative humidity, wind,
  fog state, the WEonG repair, cloud motion) are registered or re-classed.
- `registry/schema.json`, `registry/source_data.py`: delivery kind
  `intermediary_derived`; the Open-Meteo WeatherNext 2 cloud record.
- `web/src/`: class badge and legend; the data-mode banner is unchanged.
- No adapter is changed, no registry status is promoted, `operational` stays
  `false`. Spec-Impact: none outside this experiment.
