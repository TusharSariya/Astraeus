# ADR 0001: Five evidence classes, with derived-here allowed on data paths

Date: 2026-09-02
Status: accepted (experiment scope, Spec-Impact: none)

## Context

The governing rule of the St. John's weather-map experiment is that nothing is
displayed or returned that was not retrieved. That rule left only two ways for
a value to exist on a data path: retrieved as the producer issued it, or
reprocessed by a declared intermediary. Everything else was pushed into
display-only carve-outs. Consensus was removed on 2026-09-02 because a blended
value is one no centre issued.

The four activities this foundation serves (running, astronomy, aurora,
landscape photography) need quantities no producer publishes for this
peninsula: air-sea temperature difference for Grand Banks fog, seeing from
model levels, dew point depression against a cooled optic, wet-bulb globe
temperature. Each is a physical construction over retrieved inputs, not a
blend. Under the old two-class rule they were either forbidden or smuggled
in, and every attempt collided with the guardrails.

## Decision

Every value carries one of exactly five evidence classes: retrieved,
reprocessed, derived-here, generated-display, uncalibrated observation.

Derived-here is allowed on every data path and on the map when it reads only
retrieved inputs (from any number of sources), names every input with its own
provenance, uses a method admitted through an owner-approved derivation method
registry (name, version, citation, inputs, physical range, enabled flag), and
carries a quality no better than the worst of its inputs. Combining the same
field across centres remains blending and remains forbidden. Reprocessed and
uncalibrated values are never the display primary and never derivation inputs.
Generated-display stays display-only. Every value shows its class to the
reader.

## Amendment (2026-09-02, same day)

A sixth class, **intermediary-derived**, was added when the owner chose to
admit Open-Meteo's cloud cover for Google WeatherNext 2, a value Open-Meteo
computes from the model's humidity profile for a model that publishes no
cloud. It is neither reprocessed (nothing was transformed) nor derived-here
(this deployment did not compute it). The class names producer, intermediary
and the intermediary's method where documented, and carries the reprocessed
limits: never the display primary, never a derivation input. The title of
this record is kept for stability; the class count is six.

## Consequences

- The provenance schema gains a required class field, artifacts record the
  classes they contain, and provenance failures are isolated per artifact.
- The decision layer's outputs are derived-here values and cannot masquerade
  as producer output.
- Adding a derivation is a registry entry and an owner approval, not a spec
  fight.
- Reversing this means removing a field every artifact carries and every
  client reads; that cost is why it is recorded here.
