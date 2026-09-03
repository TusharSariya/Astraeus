# Design

## Why a statistic over members is not the consensus that was removed

Consensus was removed on 2026-09-02 because it averaged the same field across
centres: a mean of HRDPS opacity-weighted cloud and GFS geometric cloud is a
number no centre issued, over two quantities that are not the same quantity.
`evidence-truth-boundary` keeps that forbidden and this change does not touch
it.

A mean over the 21 members of one REPS run is a different object. Every input
is the same field, at the same level, in the same units, from one producer,
from one run, produced by one model whose members exist precisely so that the
spread between them can be read. The producer's own centre computes exactly
this statistic and publishes it for GEPS. What separates a legitimate member
statistic from a blend is therefore not "how many numbers went in" but
"whether the inputs are one field of one family and one run". That single test
is what every refusal below reduces to.

| construction | admitted | why |
| --- | --- | --- |
| mean over REPS members, one run | yes | one field, one family, one run |
| mean over GEFS and REPS members | no | two families, two grids, two model formulations |
| mean over two REPS runs | no | two initialisation times are not a member set |
| GEPS provider mean combined with a REPS mean | no | two member sets, and the provider's own statistic is retrieved evidence stored as issued |
| mean of HRDPS and GFS cloud | no | the removed consensus, unchanged |

## Why the statistics go through the derivation method registry

`evidence-classes-and-derived-here` already requires that no `derived_here`
value exists except from an enabled registry entry with a name, version,
citation, declared inputs, declared output, physical range and an
out-of-range rule, and it already refuses at registration any entry that
combines a provider reduction with a statistic over another member set. Making
the five statistics registry entries therefore buys the refusals for free,
as registration-time validation rather than as scattered runtime checks, and
it buys the three-level kill switch (per entry, per deployment, per reader)
that the same requirement defines. It also means an ensemble mean carries a
citation and a version like every other derived value, so a change to the
quantile convention is visible in provenance instead of silently changing a
displayed number.

The five entries and their shapes:

| entry | output | range rule |
| --- | --- | --- |
| `ensemble_mean` | the field's own unit | the field's own physical range |
| `ensemble_spread` | the field's own unit, non-negative | zero when every member agrees, which is a real answer and not a failure |
| `ensemble_quantile` | the field's own unit | the quantile convention and its interpolation rule are declared in the entry, because two conventions differ visibly on 21 members |
| `ensemble_threshold_probability` | fraction 0 to 1 | the threshold, its unit and its comparison sense are part of the request and are echoed on the value |
| `ensemble_member_count` | count | reports members used and members declared, never one number standing for both |

`ensemble_member_count` is an entry rather than a bare integer for one
reason: it is the field a reader needs in order to weigh every other
statistic, and routing it through the registry means it is produced by the
same code path over the same member set, so it can never disagree with the
mean beside it.

## Why the control is a flag and not a source

A control member is the unperturbed run of the same model at the same
resolution in the same family. Giving it its own registry record would make
member completeness uncheckable (21 members or 20 plus one source?), would
put it outside the member axis so no statistic could include or exclude it
deliberately, and would invite it onto the display-primary ordering as though
it were a deterministic model, which it is not. As a flagged member it is one
value on one axis: a statistic declares whether it included the control, a
reader can select it like any other member, and the count of declared members
is one number the registry states.

The awkward case is AIFS-ENS, whose control arrives in a separate `cf` file
while the 50 perturbed members arrive in a `pf` file. That is an access-shape
difference, not an identity difference. The adapter reads two files and
publishes one member axis of 51, and a run where `cf` is missing is a partial
run with the control named as missing, not a complete run of 50.

## Why absence has three distinct answers here

The stack already distinguishes null (published, no number in the cell) from
blocked (`activity-profiles`) and aged-out (ticket 20). Members add a fourth
distinction that has to be kept separate from all of them: a statistic over a
member set that is not the declared one. It is not null, because a number
exists; it is not blocked; the underlying members are present. The honest
answer is a value that carries its own member set on its face, plus a
refusal when the set is thin enough that the number would mislead.

The completeness threshold is deliberately not invented here. The rule is
comparative and fail-closed: a statistic over a partial member set is served
only when the artifact reports partial and the value names the members used
and the members declared; it is refused outright when the artifact would not
publish at all, which `ensemble-members-and-source-plurality` already defines
for a run where no member decodes. Where an owner-approved minimum member
count exists for an entry, the entry declares it; where none is declared, no
minimum is invented at runtime, and the shortfall is carried on the value
instead.

## Why the six-hour-mean cloud gets a key and a fence

GEFS `TCDC:entire atmosphere` is `0-3 hour ave fcst` at f003 and `18-24 hour
ave fcst` at f024. It is a real published field of a real admitted family and
it is not the same quantity as an instantaneous cloud fraction: a six-hour
mean of 50 percent is one sky at half cover or two skies, one clear and one
overcast. `field-catalogue-and-families` already splits it to its own key.
What this change adds is the two fences the key alone does not carry: it is
never drawn beside an instantaneous cloud field on one ramp or axis, and it
is never an input to a statistic whose other inputs are instantaneous. The
second fence matters because the first only guards the display, and a
threshold probability over a mixed set would be a data-path value with no
meaningful unit.

## Why REPS direction stays absent

REPS publishes `WSPD` on its members and no `u` or `v` on any of them, so
there is nothing to derive a direction from. Deriving one from another
family's wind would be cross-family blending; deriving one from the REPS
provider reductions would combine a reduction with a member; carrying a
direction from a neighbouring deterministic model would be borrowing another
source's value, which `point-evidence-sampling` forbids. The catalogue records
the gap and the field is null with a reason, which is the same answer the
governing rule gives everywhere else.

## Seam

Pinned by the change lead on 2026-09-02 before any task agent started, so
that ten agents in four waves build against one contract. Names prefer what
the spec deltas and the existing code already use. A task that must deviate
edits this section in the same commit and says so in its report.

### Seam A: the registry declaration (2.1 writes, 2.2 audits, 3.x and 4.2 read)

Every record with `category == "ensemble"` carries one object under the key
`ensemble`, validated by `registry/schema.json`:

```
"ensemble": {
  "family": "REPS" | "AIFS-ENS" | "IFS ENS" | "GEFS" | "GEPS reductions" | "ICON-EPS",
  "build_order": 1..6,
  "shape": "members" | "reduction",
  "subsetting": "server_side" | "none",
  "storage_scope": "every_published_field" | "family_fields_only",
  "member_count": <int> | null,
  "control": null | {"identifier": "<provider's own id>", "rule": "<prose>", "separate_retrieval": <bool>},
  "reductions": ["mean", "spread", "percentile", "threshold_probability"] | [],
  "gaps": [{"field": "<catalogue key>", "reason": "<prose>"}],
  "verification": {"member_count": "verified" | "unverified", "access_path": "verified" | "unverified",
                   "cadence": "verified" | "unverified", "evidence": "<research path>" | "none"},
  "schedulable": <bool>,
  "schedulable_reason": "<prose>"
}
```

Source ids and their families: `eccc-reps` REPS (1), `ecmwf-aifs-ens`
AIFS-ENS (2), `ecmwf-ens` IFS ENS (3), `noaa-gefs` GEFS (4), `eccc-geps` GEPS
reductions (5), `dwd-icon-eps` ICON-EPS (6, a new record). `subsetting` and
`storage_scope` reuse the exact values `registry/fields.py` `SOURCE_SCOPE`
already uses. `member_count` is null iff `shape == "reduction"`; `control` is
null iff the family publishes no control. Member identifiers are the
provider's own tokens: REPS `01`..`21`; GEFS `gec00` (control) and
`gep01`..`gep30`; ECMWF the GRIB `number` as a string, control `0` (the `cf`
type), perturbed `1`..`50`. `schedulable` is false on all six in this change:
a family with any `unverified` field is not schedulable by the spec, and the
non-subsettable families additionally wait on owner gate 6.1.

`registry/source_data.py` exports `ENSEMBLE_BUILD_ORDER: tuple[str, ...]` in
the owner's order and `ensemble_families() -> list[dict]` returning the six
records' `ensemble` blocks sorted by `build_order`. `ingest/registry.py`
parses the block into `IngestConfig.ensemble: EnsembleDeclaration | None`
(a frozen dataclass with the same field names) and `IngestConfig.ingestible`
is false for an ensemble record whose `ensemble` is absent or whose
`schedulable` is false, so registering an adapter never schedules a family.

### Seam B: the member coordinate in artifacts (3.3 provides, 3.1 uses, 3.2 records, 4.2 reads)

- The member axis is a dataset dimension and coordinate named `member`, of
  string dtype, holding the provider's own identifier. A boolean coordinate
  `control` runs along `member`. Both are written by
  `ingest.grib.stack_members(fields_by_member: Mapping[str, DataArray], *,
  control: str | None) -> DataArray`, which raises `GribError` naming the
  member values it saw when two would collapse onto one identifier.
- `ingest.grib.strip_message_scalars` keeps the GRIB `number` scalar as the
  attribute `grib_number` before dropping the coordinate, so a decoded
  message never loses its identity.
- A time-averaged field carries the attributes `cell_methods: "time: mean"`,
  `averaging_window_hours: <float>` and `averaging_window_basis: "<the
  producer's own record label, e.g. '18-24 hour ave fcst'>"`, stamped by
  `ingest.grib.declare_time_average(variable, *, window_label: str)`, which
  raises `GribError` when the label states no window (the field is then not
  stored).
- The artifact provenance dict carries `"members": {"declared": <int>,
  "present": [ids], "missing": [ids], "control": "<id>" | null,
  "control_retrieval": "same_file" | "separate_file" | "separate_coverage" |
  null}` and `"storage_scope": {"applied": "every_published_field" |
  "family_fields_only", "available_not_stored": [upstream names],
  "not_retrieved": [catalogue keys]}`. `ingest.manifest.RunManifest` gains
  `member_count: int | None` and `control: str | None`; `validate_run` fails
  a run `partial_members:<missing ids>` (complete=False) when fewer members
  than declared are present, fails `no_members` when none are, and fails QC
  `averaging_window_unstated:<field>` on a `cell_methods: "time: mean"`
  field with no `averaging_window_hours`. `ValidationResult.as_members()`
  returns the `members` block above. `validate_run` takes the keyword
  `control_retrieval` (`same_file`, `separate_file`, `separate_coverage`),
  raises `ManifestError` on any other value and nulls it where the family
  declares no control; an adapter passes it from the family's declaration
  (added by task 3.3 on 2026-09-02; 3.1 and 3.2 build to it).
- The store samples a member-bearing dataset only when the request named a
  member (`member=<id>` or `member=all`) or a statistic; otherwise the
  artifact yields no value and a skip notice
  `member_dimension_unaddressed:<revision>` (spec of step 1).

### Seam C: the derivation registry entries (4.1 writes, 4.2 calls)

The placeholder `ensemble_statistics_within_run` is NOT replaced. It is
enabled in this change (owner's standing rule: every member statistic goes
through that entry) and becomes the umbrella entry: the family-level switch
the spec's "the statistics are switched off" scenario names, resolved first
by `derive_ensemble_statistic`, so disabling it at any of the three levels
nulls all five statistics with a notice naming the level. Beside it the five
entries the spec requires are added: `ensemble_mean`, `ensemble_spread`,
`ensemble_quantile`, `ensemble_threshold_probability`,
`ensemble_member_count`, all version `within-run-v1`, all enabled, all citing
Wilks (2019) chapter 8; a value's `derivation` names the specific entry.
`ENSEMBLE_STATISTICS` stays the umbrella's name string;
`ENSEMBLE_STATISTIC_ENTRIES` is the tuple of the five names;
`ENSEMBLE_ENTRY_BY_STATISTIC: dict[str, str]` maps `"mean"`,
`"spread"`, `"quantile"`, `"threshold_probability"`, `"member_count"` to
them. Each entry's single input is
`Input(field="ensemble_member_field", family="ensemble_member_field",
kind="member_statistic")`, meaning one catalogue field over the member axis
of one source. Conventions: mean is arithmetic; spread is the sample standard
deviation with an n-1 denominator, zero when every member agrees; quantile is
Hyndman and Fan type 7 (linear interpolation on (n-1)q), the numpy default;
threshold probability is the fraction of members satisfying the comparison,
carrying `threshold`, `threshold_units` and `comparison` in `ge | gt | le |
lt`; member count reports used and declared as two numbers.
`DerivationMethod` gains `include_control: bool = True` and
`minimum_members: int | None = None` (none declared, owner gate 6.4).

Registration-time refusals added to `validation_errors`: a
`member_statistic` entry whose inputs name more than one source; one that
mixes a key in `TIME_AVERAGED_FIELDS = frozenset({"total_cloud_mean_6h"})`
with another key of the same family; the existing provider-reduction rule.

Derive-time API in `ingest/derive/registry.py`:

```
@dataclass(frozen=True) class MemberValue: member: str; control: bool; value: float | None; quality_status: str
@dataclass(frozen=True) class MemberSet: family: str; source_id: str; run_time: datetime | None; field: str;
    declared: int; members: tuple[MemberValue, ...]; time_averaged: bool = False
    # properties: used (members with a value), missing (declared ids absent), partial
@dataclass(frozen=True) class EnsembleStatistic: statistic: str; value: float | None;
    method: DerivationMethod | None; member_set: MemberSet | None; flags: tuple[str, ...];
    refusal: Refusal | None; condition_failed: str | None; members_used: int; members_declared: int;
    members_missing: tuple[str, ...]; control_included: bool | None; quantile: float | None = None;
    threshold: float | None = None; threshold_units: str | None = None; comparison: str | None = None
def derive_ensemble_statistic(statistic: str, member_sets: Sequence[MemberSet], *, quantile=None,
    threshold=None, threshold_units=None, comparison=None, reader_disabled=()) -> EnsembleStatistic
```

`condition_failed` codes: `one_family:<A>,<B>`, `one_run:<A>,<B>`,
`provider_reduction_mixed`, `averaged_with_instantaneous`,
`below_minimum:<used>/<minimum>`, `no_member_resolved`. A failed condition
yields `value=None` and never a value over the subset that passes. Quality
follows the worst member's `quality_status` plus the `derived` flag; a
partial set adds the flag `partial_member_set`.

### Seam D: the API request and response (4.3 models, 4.2 store and app, 4.4 web)

Request parameters on `/point`: `member: str | None` (a provider identifier
or `all`), `statistic: str | None` (one of the five statistic names),
`quantile: float | None`, `threshold: float | None`, `comparison: str | None`.
Fixture mode answers a `member` or `statistic` request with null fields and
the notice `fixture deployment carries no ensemble members`, never fabricated
members.

Response, on `Provenance`: the existing `member: str | None` names the
member of a per-member value; new `member_control: bool | None`; new
`ensemble: EnsembleProvenance | None`:

```
class EnsembleMemberSet(StrictModel):
    family: str; source_id: str; run_time: datetime | None; members_declared: int; members_used: int
    members_missing: list[str]; control_included: bool | None; partial: bool
class EnsembleProvenance(StrictModel):
    family: str; statistic: str | None; computed_here: bool; member_set: EnsembleMemberSet | None
    refusal: str | None = None; quantile: float | None = None; threshold: float | None = None
    threshold_units: str | None = None; comparison: str | None = None
    averaging_window_hours: float | None = None
```

A per-member value is its own `EvidenceField` (same `field` and `key`) with
`provenance.member` and `provenance.member_control` set and
`provenance.ensemble.statistic` null. A statistic is one `EvidenceField`
with `evidence_class = "derived_here"`, `derivation` = the entry name,
`provenance.ensemble.statistic` set, `computed_here = true`, and the members
it covered served beside it in the same response. A refused statistic is an
`EvidenceField` with `value = null`, `quality.flags` containing
`statistic_refused`, and `provenance.ensemble.refusal` naming the condition
code from Seam C; a null member value stays a plain absence. A provider
reduction is `retrieved` with `computed_here = false`. Quality flag names:
`statistic_refused`, `partial_member_set`, `derived` (existing). A value
whose family cannot be read from its registry record is not served and the
field is unavailable with `ensemble_family_unknown`.

Web: `loadPoint` gains `member` and `statistic` request options; the member
selector sends `member`; every ensemble row names family, run, statistic,
member set and computed-here or provider's-own, in the panel and in the text
alternative.

## Deviations recorded by the implementation pass (2026-09-02)

- The change's file plan named `api/weather_api/derivations.py`,
  `web/src/components/`, `tests/test_grib.py` and `tests/test_derivations.py`.
  None exists. The derivation method registry lives in
  `ingest/derive/registry.py`, web components sit flat under `web/src/`, and
  the tests are `tests/test_ingest_grib.py`, `tests/test_manifest.py` and
  `tests/test_derivation_registry.py`. `tasks.md` names the real files.
- The placeholder entry `ensemble_statistics_within_run`, which
  `ensemble-members-and-source-plurality` registered disabled, is enabled
  here as the umbrella entry, and the five per-statistic entries the spec
  requires are added beside it (Seam C). The first pin of this seam said the
  five would replace it; the change lead corrected that on 2026-09-02 before
  task 4.1 started, because the owner's rule names that entry as the path
  every statistic takes.
- Statistic and member layers on the map itself need `/layers` to carry a
  member axis, which no task here owns; task 4.4 renders members and
  statistics as rows of the evidence panel and the map layer is an open
  follow-up recorded in `tasks.md`.
- All six families are declared not schedulable (Seam A). Nothing is
  scheduled by this change, as the proposal states.

## Why the reader never sees an unnamed ensemble number

The failure this guards against is the one the removed consensus badge
demonstrated: a number on screen whose construction the reader cannot
recover. Every ensemble number displayed therefore names four things
together, and a number that cannot name all four is not displayed: the family
and run it came from, the statistic it is, the member set it covers, and
whether it is a provider reduction or computed here. A member selector makes
the members themselves reachable, so the statistic is never the only view of
the ensemble.
