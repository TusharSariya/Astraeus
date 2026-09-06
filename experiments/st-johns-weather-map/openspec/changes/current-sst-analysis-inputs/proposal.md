# Current OSTIA and NOAA OISST SST analysis inputs

## Why

Coastal-condition analysis needs source-identifiable SST evidence. The current
experiment has no adapter for the Met Office OSTIA or NOAA OISST Level-4
analysis products, even though both have anonymous current access paths.

## What changes

- Add separate catalogued, unschedulable sources plus isolated capture adapters for current OSTIA foundation SST and
  NOAA OISST v2.1 daily SST.
- Preserve native grid, analysis time, preliminary/final identity, uncertainty,
  native missingness and OSTIA's surface mask over the evidence box.
- Apply bounded anonymous retrieval and the shared artifact/API proof gate.

No fog formula, fog verdict, score, archive acquisition, sea-ice evidence or
production admission or scheduler registration is introduced.

Spec-Impact: none; isolated experiment implementation under the shared source
integration contract. Production authority remains unresolved there.
