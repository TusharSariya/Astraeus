## Why

`ensemble-members-and-source-plurality` established that this stack can hold a
member at all: the decoder keeps `number`, an artifact carries its members and
reports completeness, a provider's own reduction is stored as retrieved, the
sampler refuses a member dimension nobody addressed, and the registry declares
whether a provider publishes members or only a reduction. It deliberately
stopped there. It admitted no family, it fixed no ingest order, and it
forbade every statistic outright: "a mean, median or spread SHALL be served
only where the provider itself published it as a field". That prohibition was
the honest reading of the governing rule at the time, and it is the thing the
owner has now decided differently.

Wayfinder ticket
[#22](https://github.com/TusharSariya/Astraeus/issues/22) resolved on
2026-09-02: all six ensemble families are admitted, in the order REPS,
AIFS-ENS, IFS ENS, GEFS, GEPS reductions, ICON-EPS; a control member is a
member with a flag rather than a separate source; and statistics over members
ARE computed here, as `derived_here` values through registered derivation
methods, always within one family and one run, never across families, never
combined with a provider reduction, and always served beside the raw
per-member values they summarise. That is not consensus returning under
another name. Consensus averaged the same field across centres, which
`evidence-truth-boundary` still forbids and which this change does not touch.
A mean over the members of one run of one model is that model's own spread of
outcomes, computed by a cited method from inputs that are all one family's
retrieved values, which is exactly what `evidence-classes-and-derived-here`
admits on data paths.

The measurements behind the family order are in
`docs/research/wayfinder/ensemble-access.md` (branch
`research/ensemble-access`), one HTTP call each on 2026-09-02 against the
`20260901` `00z` run. REPS is first because GeoMet subsets server side and one
member field for one lead is 40 224 bytes already cut to the evidence box, the
cheapest per-member cloud field of any family by two orders of magnitude.
AIFS-ENS is next because it is the only family publishing per-member low,
middle and high cloud, against the finding that no ECCC model on GeoMet
publishes layered cloud at all. IFS ENS follows with instantaneous `tcc` at
PDT 4.1 and, unlike REPS, member `u` and `v`. GEFS is fourth and costs about
7.7 MB per field per lead across 31 members to store about 1.2 KB, and its
column total cloud is a 3 h or 6 h average at every lead in `pgrb2a` and
averaged again in `pgrb2b`, so it contributes a time-averaged cloud field and
no instantaneous column at all. GEPS is fifth and reduction-only, because it
publishes zero members anywhere reachable. ICON-EPS is last, natively,
because nothing about it was measured on that ticket.

What remained unverified when this change was written, and was not assumed
away: where the IFS ENS control member's file lives in the `ifs/0p25/enfo` layout;
whether ECMWF `06z` and `18z` carry the full ENS; the REPS run cycles and lead
set, which are documentation and were not enumerated; whether REPS `ETA_NT` is
genuinely instantaneous, since GeoTIFF carries no product definition template;
the PDT of the AIFS-ENS layered cloud fields; and every figure for ICON-EPS.
Issue 82 rechecked the live Open Data listing and f024 index on 2026-09-05:
only `enfo-ef` exists and it contains `pf` 1..50 with no `cf`. The experiment
keeps control 0 missing and does not borrow deterministic `oper` output. No
statistic in this change may be computed from a family whose member count
is unverified, which is the fail-closed reading of all of the above.

Classification: Experiment, Spec-Impact: none. `docs/specv1` is untouched.

## What Changes

- **Six families are admitted in a fixed order**, with the ingest order itself
  specified so that a partial build is a prefix of the list rather than an
  arbitrary subset: REPS, AIFS-ENS, IFS ENS, GEFS, GEPS reductions, ICON-EPS.
- **Storage scope per family follows ticket 20.** REPS and GEPS arrive over
  GeoMet, which subsets server side, so every published field is stored. AIFS-ENS,
  IFS ENS, GEFS and ICON-EPS cannot subset server side, so only the fields the
  catalogue's families use are stored and the rest are catalogued
  `available-not-stored`.
- **The control is a member with a `control` flag**, in the same member axis
  as the perturbed members, never a separate source and never a separate
  field. A family that publishes its control in its own file (AIFS-ENS `cf`)
  still lands as a flagged member of the one family.
- **Statistics are computed here through the derivation method registry.**
  Mean, spread, quantiles, threshold probabilities and member counts become
  registered entries, each `derived_here`, each within one family and one run.
- **The three refusals are specified, not implied**: never across families,
  never combined with a provider reduction, and never over a member set the
  artifact reports as partial without saying so on the value.
- **Raw members are always served beside the statistics.** A statistic that
  cannot be shown beside the members it summarises is not served.
- **GEFS six-hour-mean total cloud is its own catalogue key**, admitted with a
  comparability note, never drawn beside an instantaneous cloud field on one
  ramp or one axis, and never an input to a statistic over instantaneous
  cloud.
- **REPS wind direction stays null.** REPS publishes speed with no u or v on
  any member, so direction is absent, is not derived, and the catalogue
  records the gap rather than filling it.
- **The reader contract is fixed**: per-member values on demand, statistics as
  labelled derived-here fields naming their method and member set, a member
  selector plus statistic layers on the map, and never an unnamed "ensemble"
  number anywhere in the interface or its text alternative.

## Capabilities

### New Capabilities

None. `derivation-method-registry` is introduced by
`evidence-classes-and-derived-here` and is extended here.

### Modified Capabilities

- `source-registry-catalogue`: the six families are declared with their
  admission order, their subsettability and therefore their storage scope,
  their expected member count, how the control is identified, and the fields
  they do not publish (REPS direction), on top of the shape declaration that
  `ensemble-members-and-source-plurality` already requires.
- `artifact-ingestion`: the control lands as a flagged member; the storage
  scope per family is applied at ingest; a time-averaged member field is
  stored under its own key with its averaging window recorded.
- `derivation-method-registry`: the five ensemble statistics are registered
  entries with their inputs, ranges and refusals, extending the entry list
  that `evidence-classes-and-derived-here` opens.
- `point-evidence-sampling`: a statistic is served as a labelled derived-here
  field beside the members, with the member set named; a cross-family request,
  a provider-reduction mix and a partial or stale member set each fail closed.
- `web-evidence-interface`: a member selector and statistic layers, every
  ensemble number named, and the expert control block modified so that member
  stops being a read-only readout and becomes a real request parameter.

## Impact

- Affected specs: `source-registry-catalogue` (ADDED),
  `artifact-ingestion` (ADDED), `derivation-method-registry` (ADDED),
  `point-evidence-sampling` (ADDED), `web-evidence-interface` (ADDED and
  MODIFIED). Every ADDED heading was cross-checked by hand against
  `openspec/specs/` and against the open changes, because `openspec validate`
  resolves neither: an ADDED heading that already exists in an accepted spec
  collides at archive, and one that duplicates another open change's ADDED
  heading collides with it.
- The one MODIFIED block is `web-evidence-interface`'s "A control that cannot
  change the request is disabled and says why". Its `Run, member and level`
  scenario asserts that member is a read-only readout because the point
  request has no parameter for it, which ticket 22's reader contract reverses.
  All four of its scenario titles are carried over verbatim.
- Dependency, blocking: this change sits behind
  `ensemble-members-and-source-plurality` (member storage, completeness,
  decoder, registry shape), `evidence-classes-and-derived-here` (the class
  field and the derivation method registry the statistics go through) and
  `field-catalogue-and-families` (the keys the statistics name, including the
  six-hour-mean cloud key). It contradicts none of them and re-states none of
  their requirements.
- One sentence of `ensemble-members-and-source-plurality` is superseded by the
  owner's resolution and is not silently overwritten here. Its requirement "A
  sampled member is a value with an identity" states that a mean, median or
  spread is served only where the provider published it. Ticket 22 reverses
  that. This change adds no requirement that edits another open change's
  delta; the correction belongs in that change, and task 6.2 puts the choice
  of which change carries it to the owner before either is archived.
- Affected code, when the implementation pass runs and NOT in this change:
  `registry/source_data.py` and `registry/audit.py` (family declarations),
  `registry/fields.py` (the averaged-cloud key and the REPS direction gap),
  `ingest/adapters/` (four new ensemble adapters, one per access shape),
  `api/weather_api/derivations.py` (the five statistic entries),
  `api/weather_api/store.py` and `models.py` (member selection and statistic
  fields), `web/src/` (member selector, statistic layers).
- Upstream cost, which is the binding constraint and not storage: the S3 and
  ECMWF families fetch a whole global record per member to keep a few KB, so
  admitting AIFS-ENS, IFS ENS and GEFS is a bandwidth decision the
  `geomet-wms-access` budget does not cover. No family is scheduled by this
  change.
- Rollback: nothing ships here, so there is nothing to roll back. The
  implementation pass is gated on the owner accepting the per-family upstream
  cost, which is task 6.1.
