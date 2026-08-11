---
id: PRD-001
title: Astraeus V1 Product Requirements
type: prd
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
  - GOV-001
supersedes: []
---

# Astraeus V1 product requirements

## Summary

Astraeus answers a decision, not merely a forecast:

> Given where I am, how far I can travel, and when I am available, where should
> I go, when should I be there, where should I look, and how good is the
> opportunity?

The first reusable vertical slice plans observation of the August 12, 2026
solar eclipse from the Avalon Peninsula. The architecture must remain capable
of adding aurora, deep-sky, meteor, comet, sunrise, and sunset event modules
without pretending their physics or success criteria are interchangeable.

## Users

- A general observer using certified solar viewers.
- A photographer using a correctly front-mounted solar filter.
- A user deciding whether travel offers enough robust benefit over staying.

## PRD-OUT-001 — Return a decision-oriented recommendation

The product MUST answer stay or go, destination, departure and arrival time,
viewing direction, opportunity quality, dominant risk, and fallback. It MUST
include the current location as a distinct stay option.

## PRD-OUT-002 — Optimize within real constraints

The result MUST honor availability, full round-trip travel, setup and teardown,
walking, access, environmental safety, and observation interval constraints.

## PRD-OUT-003 — Explain evidence and uncertainty honestly

The product MUST separate deterministic event geometry, issued forecasts,
current observations, evidence quality, scenario spread, source disagreement,
and access/safety assertions. It MUST call the result a planning score until a
success probability is empirically calibrated.

## PRD-OUT-004 — Fail closed

The product MUST return `no reliable recommendation` when critical geometry,
cloud evidence, access, route, or site-safety evidence is unavailable or stale.
It MUST NOT silently substitute climatology, a consumer forecast, or an
unverified site.

## PRD-OUT-005 — Preserve reproducibility

Every recommendation MUST be reproducible from immutable inputs, provider/run
metadata, retrieval times, checksums, ephemeris and Earth-orientation inputs,
rules, algorithms, routing graph, site catalogue, and client-visible revision.

## PRD-SAFE-001 — Solar safety cannot be optimized away

For a partial eclipse, the product MUST never show a glasses-off state. Weather,
cloud, score, or apparent darkness MUST NOT relax certified viewer and
front-mounted optical-filter requirements. Users without valid viewers receive
authoritative indirect-viewing guidance only.

## PRD-ACC-001 — Recommended destinations require current evidence

A destination MUST NOT receive a score, go state, deadline, or navigation link
unless lawful access/stopping, opening hours, and critical site safety are
approved and current. Unknown sites MAY appear only in an exploratory view.

## Release profiles

### `event_day_preview`

A controlled, accountless PWA serving a fixed-origin, signed, precomputed plan
snapshot. It collects no GPS and makes no live-planner reliability claim.

### `v1_web`

A dynamic-origin web planner with live providers, asynchronous evaluation,
evidence viewer, provenance, and explicit degradation.

### `v1_native`

An Expo/React Native companion that shares contracts and domain semantics,
supports verified offline products, and ships only after physical-device,
privacy, permission, and store gates pass.

## Success criteria

- A user can decide whether and where to travel without combining separate
  astronomy, weather, map, access, and routing apps.
- A recommendation states why it won and what could invalidate it.
- Stale, missing, and conflicting evidence is visible and affects eligibility.
- The same evaluation revision has identical meaning across clients.
- The system can honestly recommend staying or making no recommendation.

## Non-goals

- Numerical weather prediction or foundational weather-model training.
- Calibrated visibility probability before outcome data exists.
- Global coverage, all astronomical events, radiative-transfer perfection,
  native immersive AR, or photorealistic 3-D obstruction inference in V1.
