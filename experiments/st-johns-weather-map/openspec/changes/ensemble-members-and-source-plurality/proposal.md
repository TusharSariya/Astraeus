## Why

The map has reported `HRDPS primary - consensus unavailable` for as long as
anyone has looked at it, and the reason is not a missing feed. It is a
contradiction between two accepted requirements that no data can resolve.
`point-evidence-sampling` requires an ensemble among the candidates before a
consensus value is produced. `source-registry-catalogue` reads eligibility
from the registry, and `registry/audit.py:68-69` refuses eligibility to any
record that is not `deterministic_forecast`, while
`api/weather_api/store.py:1173` derives `is_ensemble` from that same category.
A candidate must be eligible to be counted, deterministic to be eligible, and
an ensemble to satisfy the gate. There is no common solution, so the branch
that produces a consensus value has never once been taken.

The owner's decision on 2026-09-02 was to remove consensus rather than repair
it. The repair argument is weak on its own terms: an ensemble mean is a
smoothed field that no centre issued, averaging it into a 2.5 km regional
model damps the gradients that model exists to resolve, and hard-won facts 7
and 9 already record that the cloud fields being compared across centres are
not the same quantity. Under the governing rule a blend is a value that was
not retrieved, and it never earned a carve-out. Every source that published
will be shown side by side instead, with HRDPS named as the headline by an
explicit ordering.

Separately, the owner asked to add ensemble ingestion, and measurement showed
that "an ensemble" is not one thing. Three of the five registered ensembles
were probed live on 2026-09-02. GEFS publishes 31 members as per-member GRIB2
on S3. REPS publishes 21 members as 1239 individual GeoMet coverages. GEPS
publishes no members at all, only its own mean, spread, percentiles and
threshold probabilities, and both ECCC ensembles are now 404 on every open
ECCC HTTP path including the one the registry declares. Two ingest shapes are
therefore required, not one. Meanwhile nothing in this stack understands a
member: the decoder deletes the `number` coordinate at
`ingest/grib.py:328`, and a member array reaches `float()` in
`_sample_dataset` and is caught into a `None`, losing evidence silently.

A third strand arrived with the same measurement pass. The foreign global
models that would add genuine diversity here - UK Met Office Global 10 km, JMA
GSM, ARPEGE-world, CMA GRAPES - are reachable at this location only through an
aggregator, and that aggregator does not return a published cell. It selects a
cell by a policy that defaults to nearby land at similar elevation, downscales
against a 90 m elevation model, and interpolates the native step up to hourly.
`point-evidence-sampling` forbade that outright. The owner's decision on
2026-09-02 was to loosen the rule rather than lose the sources, on the grounds
that such a value is still retrieved rather than invented here, and that the
honest fix is to declare what kind of source it came from. The same
declaration covers a real gap that predates the question: nothing in the
registry currently distinguishes a producer's own feed from a third party's
rendering of it.

Evidence and measurements are recorded in
`docs/research/ensembles-and-source-plurality.md`, and the source
re-verification behind the third strand in
`docs/research/01-atmospheric-nwp-satellite.md` sections R1 to R5. That pass
also found that three ECCC Datamart feeds this project had catalogued died
within three days, including the forecast sounding ranked first in
`04-gap-analysis.md`. What remains unverified:
whether GeoMet WCS returns a usable Avalon subset per REPS member and at what
cost; whether GEFS publishes any instantaneous total cloud, since `pgrb2a`
carries only a six-hour average; whether ECMWF open-data discovery can be
fixed; and whether GEPS is reachable over MetPX Sarracenia, the one open ECCC
route not probed.

Classification: Experiment, Spec-Impact: none. `docs/specv1` is untouched.

## What Changes

- **Consensus is removed, not repaired.** The requirement that produces a
  blended value is deleted along with the three-state fallback ladder and the
  `consensus unavailable` badge. No response field is a mean over sources.
- **Every source that published is shown.** A field carries one entry per
  contributing source, each with its own provenance, and no source's value is
  merged into another's. The headline names one declared primary by an
  explicit ordering, HRDPS first, and says so.
- **Two ensemble ingest shapes are specified.** Where a provider publishes
  members, every member is stored and carries its member id. Where a provider
  publishes only its own reduction, that reduction is stored as retrieved,
  never recomputed here, and never combined with a statistic over a different
  member set.
- **Member completeness is reported, never assumed.** A run that retrieved
  some members publishes as partial with the missing members named, rather
  than presenting a thin ensemble as a whole one.
- **The decoder keeps the member coordinate.** `number` stops being dropped
  as an anonymous scalar, and a decode that would lose it fails instead.
- **The sampler refuses a member dimension it was not asked about**, on the
  precedent already set for an unrequested pressure dimension, rather than
  returning null.
- **The registry declares which shape applies** per ensemble record, so an
  adapter is not left to infer it, and the consensus block is retired.
- **The published-cell rule is loosened, and made explicit instead.** Every
  record declares how its values reach this deployment: `published_cell`, or
  `reprocessed` when an intermediary transformed the producer's field first. A
  reprocessed value may be served, but it names both the producer and the
  intermediary and every documented transformation, it can never be the
  display primary, and no derivation may read it.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `point-evidence-sampling`: both consensus requirements are removed; display
  selection is restated without the consensus rung; the published-cell rule is
  restated to admit a declared reprocessed source under strict conditions;
  every contributing source is shown side by side; a sampled member is a value
  with an identity, and an unhandled member dimension is refused rather than
  nulled.
- `source-registry-catalogue`: consensus eligibility is removed and restated
  as display ordering; an ensemble record declares whether the provider
  publishes members or only its own reduction; every record declares whether
  its values arrive as published cells or reprocessed by an intermediary; and
  the catalogue requirement is restated so its per-record field list drops
  consensus eligibility and gains the delivery kind.
- `artifact-ingestion`: an ensemble artifact carries its members and reports
  member completeness; a provider's own ensemble statistic is stored as
  retrieved.
- `grib-decoding`: the member coordinate is preserved rather than stripped.
- `web-evidence-interface`: every contributing source is listed for a field
  and no consensus wording appears anywhere, including the text alternative; a
  reprocessed value names its producer and its intermediary wherever it is
  shown.

Four requirements are removed and restated rather than modified in place.
`openspec validate` refuses a MODIFIED block that drops a scenario the
accepted spec still carries, and in both cases the dropped scenario is exactly
the consensus behaviour being retired. Each REMOVED block records the reason
and names its replacement.

## Impact

- Affected specs: `point-evidence-sampling` (REMOVED, ADDED),
  `source-registry-catalogue` (REMOVED, ADDED), `artifact-ingestion` (ADDED),
  `grib-decoding` (ADDED), `web-evidence-interface` (ADDED). Every REMOVED and
  ADDED heading was cross-checked against `openspec/specs/` by hand, because
  `openspec validate` does not resolve a heading against the base spec.
- Affected code, when the implementation pass runs and NOT in this change:
  `api/weather_api/science.py` (consensus removal), `api/weather_api/store.py`
  (`_consensus_candidates`, `_sample_dataset`, `live_point_fields`),
  `api/weather_api/models.py`, `ingest/grib.py`, `ingest/manifest.py`,
  `registry/source_data.py`, `registry/audit.py`, `ingest/adapters/` (new
  ensemble adapters), `web/src/App.tsx` and the point panel.
- Registry corrections carried by this change's tasks:
  `google-weathernext-2` licence split into its Creative Commons historic
  tier and its restricted real-time tier; `eccc-geps` and `eccc-reps`
  endpoints corrected to GeoMet with the 404 evidence recorded.
- Data: no artifact format changes here. When ensembles land they introduce a
  member dimension, which is a new axis the store, sampler and renderer have
  never carried.
- Archive order, blocking: this change modifies requirements that
  `generated-cloud-development` does not touch, so the two are independent,
  but both sit behind `interpolation-method-bench` in the archive queue for
  the reasons recorded in that change's proposal. No status transition is
  taken here: only @TusharSariya authorizes an accepted, verified or
  superseded status.
- Rollback: nothing ships in this change, so there is nothing to roll back.
  The implementation pass that follows is gated on the owner accepting the
  removal of consensus, which is a behaviour change readers will see.
