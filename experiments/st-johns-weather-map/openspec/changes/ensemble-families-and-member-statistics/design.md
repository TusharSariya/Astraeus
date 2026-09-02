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

## Why the reader never sees an unnamed ensemble number

The failure this guards against is the one the removed consensus badge
demonstrated: a number on screen whose construction the reader cannot
recover. Every ensemble number displayed therefore names four things
together, and a number that cannot name all four is not displayed: the family
and run it came from, the statistic it is, the member set it covers, and
whether it is a provider reduction or computed here. A member selector makes
the members themselves reachable, so the statistic is never the only view of
the ensemble.
