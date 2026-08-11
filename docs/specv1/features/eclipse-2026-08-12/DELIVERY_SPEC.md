---
id: ECL26-DELIVERY
title: Eclipse Planner Delivery and Rollout
type: delivery-spec
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
  - RFC-003
  - ECL26-VERIFICATION
supersedes: []
---

# Eclipse planner delivery and rollout

## ECL26-REL-001 — Limit the immediate preview honestly

The one-day controlled preview is a fixed St. John's origin, small approved
site catalogue, pinned geometry, precomputed traffic-blind routes, one manually
verified forecast snapshot, timestamped GOES IR/cloud and surface observations,
categorical cloud evidence, simple documented ranking, static map/timeline/
cards, safety, provenance, and no-reliable-recommendation state.

It has no dynamic origin, public task queue, live Valhalla dependency,
unvalidated optical-flow nowcast, ensemble probability claim, or production
reliability claim. It requires signed-snapshot verification, CDN availability,
offline-open, and rollback rehearsals.

## ECL26-REL-002 — Build the reusable web product by dependency order

```text
contracts and fixtures
  -> geometry, providers, site/routing, layer runtime
  -> accepted score/safety rules and golden recommendation
  -> fixture-backed API and evidence viewer
  -> live provider/candidate integration
  -> staging security, recovery, load, and cost gates
  -> v1_web release
```

Do not start with photorealistic 3-D or volumetric cloud presentation. The first
viewer milestone proves correct value, place, time, masks, quality, and
provenance in 2-D.

## ECL26-REL-003 — Defer optional capabilities without weakening contracts

Perturbed nowcast trajectories, full quantitative ray profile, universal
building/canopy coverage, Cesium inspection, VTK volume laboratory, 511, phone
horizon scans, aerosols, native public release, background sessions, and AR may
follow only through their accepted requirements and gates.

## ECL26-REL-004 — Gate public native release

Before release, freeze and verify true-terrain requirement/renderer, OS and
device support, performance/memory/battery/thermal/storage budgets, basemap and
offline rights, retention/account identity, background-location scope,
build/sign/update ownership, privacy manifests, store disclosures, notification
behavior, and physical-device acceptance.

## ECL26-REL-005 — Assign work only after contract predecessors pass

Every delegated work item records predecessor, consumed schema/fixture version,
produced artifact, acceptance command, contract owner, and integration owner.
Agents may implement against committed fixtures but cannot invent schemas.
Scoring waits for accepted rules and numeric fixtures. Native product work
waits for the native risk spike.
