---
id: RFC-002
title: Client Rendering and Offline Products
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
  - RFC-001
supersedes: []
---

# RFC-002 — Client rendering and offline products

## MAP-BASE-001 — Use an open operational renderer baseline

The web operational map MUST use MapLibre GL JS with deck.gl for owned raster,
vector, trajectory, and scenario-spread overlays. The native operational map
MUST use MapLibre React Native for 2-D/2.5-D behavior. Mapbox, ArcGIS, Cesium
ion, and other paid renderers remain optional adapters.

CesiumJS MAY provide a lazy-loaded web inspection view. VTK.js MAY provide a
bounded diagnostic volume laboratory. Neither is required for operational
planning or allowed to alter analytic results.

## MAP-ADAPT-001 — Conform to one map-surface contract

Web and native adapters implement:

```text
loadManifest(manifest)
setEvaluationRevision(revision)
setFrame(frameKey)
setSelection(selection)
setLayerVisibility(layerId, visible)
queryPoint(screenPoint)
getCapabilities()
onCameraChange(listener)
onError(listener)
cancelPendingLoads()
dispose()
```

Adapters discard obsolete revision/frame responses, support cancellation, and
degrade unsupported capabilities explicitly. `queryPoint` resolves analytic
features or numeric probes; it MUST NOT sample rendered pixels.

## MAP-TIME-001 — Synchronize one decision timeline

One timeline controls the map, module-supplied subject direction or sky region,
recommendation cards, atmospheric evidence, observations, route deadlines, and
horizon profile. Tracks separate subject geometry/signal, obstruction,
supported quantitative or categorical environmental evidence, observation
markers, critical windows, and travel cutoffs.

## MAP-SEM-001 — Preserve evidence semantics in presentation

Every layer displays source, valid/run/scan/retrieval time, resolution, units,
legend, masks, and freshness. Forecast and observations use distinct palettes.
Interpolation MUST NOT imply finer precision than the native evidence. A
client may change visual opacity or palette but MUST NOT change analytic masks,
thresholds, intersections, or score inputs.

## MAP-OFF-001 — Keep offline products distinct

- `PlanSnapshot` is a small signed renderer-neutral plan and fallback.
- `WebOfflineBundle` is constrained by browser quota, service workers,
  IndexedDB/Cache API, and licence terms.
- `NativeAreaPack` is a resumable, verified, atomic package using SQLite,
  app-private files, and native map resources.

No client may claim parity between these products.

## MAP-OFF-002 — Verify native area packs atomically

An area-pack manifest records schema/runtime version, bounds, zoom, observation
time range, base/evaluation/forecast revisions, issue/stale/expiry times,
artifact media type/size/SHA-256/role, and licence attribution.

```text
queued -> downloading -> verifying -> ready
                     \-> partial | corrupt
ready -> updating -> ready
```

Downloads support ranges and resume. A pack activates only after every managed
artifact and native SDK resource verifies. The prior complete revision remains
active until replacement succeeds. Mixed, expired, partial, corrupt, or
incompatible data MUST NOT appear current.

Exact offline probes use numeric grids or point datasets plus masks and
provenance, never reverse-engineered tile colors.

## MAP-NATIVE-001 — Gate native release on physical evidence

The native risk spike MUST prove web/native/backend probe parity, interrupted
250–500 MB pack recovery, airplane-mode cold launch, manual fallback, and
measured map, memory, storage, battery, and thermal behavior on representative
iPhone, Pixel, and Samsung devices. Simulator results alone cannot pass.

True native terrain, minimum OS/device classes, basemap rights, pack budgets,
account/installation identity, build/update ownership, and background location
must be frozen before public native release.
