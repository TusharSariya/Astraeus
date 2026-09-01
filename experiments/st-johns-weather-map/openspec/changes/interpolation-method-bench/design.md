# Design: what a method is, and what stops the bench from lying

## The contract

A method is a class with two hooks and an optional third:

| Hook | Answers |
| --- | --- |
| `motion(context)` | one `PairMotion` per adjacent frame pair |
| `composite(previous, following, motion, t)` | what the client draws at `t` |
| `configure(context)` | settles this variable's options by measurement |

`composite` is the load-bearing one. It is the shader written in Python, and
the harness scores *it*, so a method is ranked by its own construction rather
than by the baseline's. That also means a composite that drifts from its own
shader silently mis-ranks its own method - which is why every method's
endpoint exactness is pinned by a test rather than left as a convention.

`configure` exists because the steering prior taught us the shape: an
optional ingredient decides whether it earns its place by scoring the
held-out reconstruction with it and without it, and publishes both numbers
either way. That policy belongs to the method that owns the ingredient, not
to the derive loop, so a later method can earn its own features the same way.

## Why all methods are published, not computed on demand

The alternative was one stored artifact and an API that derives the requested
variant. Rejected: the first request per variant would be slow enough to
stutter a scrub, and - the deciding reason - variants computed in different
requests would be scored against whatever frames happened to be current,
which is not a comparison. Deriving every enabled method in one pass means
every score in provenance comes from the same held-out frames of the same
cycle, and the ranking means something.

The cost is linear in the number of methods, in both derive time and artifact
bytes. That is the price of a comparison, and a method that cannot earn its
storage is registered `enabled = False` rather than deleted, so its code and
its last measured score stay readable.

## Why the harness had to change first

The shipped harness scored one hard-coded construction, at `t = 0.5`, on MAE.
Three problems for a bench:

1. **It could only score the baseline.** Parameterising it by the method is
   the whole mechanism.
2. **The midpoint is not the only place the reader looks.** A construction can
   be right in the middle and wrong on the way there - exactly what playback
   shows. Holding a frame out of a three-interval span reaches `t = 1/3` and
   `2/3` with no new data.
3. **MAE rewards blur**, and blur is the artifact the bench exists to remove.
   A method can win on MAE by dissolving harder. Structural similarity falls
   when structure is smeared, so the two together separate "closer on average"
   from "actually the same weather".

The reversed-motion control stays exactly as it was, and stays the veto:
beating a plain crossfade is available to any blend of two warps (measured:
pure noise beats a crossfade by up to 2% while scoring 0.000 against the
control), so only the control says whether the direction carried information.

## Storage layout

Arrays gain a leading `method` axis - `("method", "pair", "y", "x")` with a
string `method` coordinate - and every field name is unchanged. An artifact
with no such axis predates the bench and is read as the single method it was,
which is the baseline. That is why the switch could ship before any second
method exists: nothing that worked yesterday depends on the axis being there.

A method may publish extra fields (`extra_suffixes`); methods that do not
publish that suffix store an explicit zero field rather than leaving the
artifact ragged, and only the method that declared a suffix reads it.

## Fail-closed at every rung

- A method the registry does not know is a 422. The API never guesses.
- A known method the artifact does not carry is a 404 naming it, which is the
  disclosed crossfade rung the client already has - never another method's
  fields under the requested method's name.
- A registry the client cannot read leaves the map on the default
  construction and says the registry was unreadable.
- A stored menu choice the server no longer publishes falls back to the
  default rather than asking every cycle for fields nobody offers.
- A published method the API has never heard of raises a notice on `/methods`
  rather than being dropped: the two components are out of step, and saying so
  is more useful than hiding it.

## The disclosure

The map already says, in words, that an instant between two frames is a
display composite and how it was constructed. The bench adds the method's
name whenever it is not the default. This is not decoration: an admin menu
that silently changes what is drawn is the one thing this experiment's
governing rule does not tolerate, and a screenshot has to be unambiguous
about which construction produced it.

## What the bench does not decide

Whether a method is *good* is a measured question, and the answer will differ
per variable and per source - the steering prior was already accepted for
HRDPS, RDPS and two GFS strata and refused for the other two. Nothing here
picks a winner or promotes one; the default stays `baseline` until a
measurement says otherwise and the owner agrees.

## ML, and where the line is

Owner decision this session: a network that emits a **displacement field** is
an ordinary method - every displayed pixel still comes from a retrieved
frame, so the governing rule is untouched and no amendment is needed. A
method that **synthesises pixels** gets a registry slot flagged `generative`,
disabled, and may not ship until a carve-out amendment makes the disclosure
say the pixels were generated. The flag exists now so that the day it is
needed, turning it on is a governance decision rather than a code change
nobody notices.
