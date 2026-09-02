# Design

## Why a profile is a file and not a code path

Four activities were named before any of them was specified, and the obvious
implementation is four modules with four sets of thresholds. That shape is
wrong for three reasons. It puts the thresholds where CI cannot check them
against the field catalogue, so a profile naming a field the catalogue
dropped compiles and fails at read time. It makes a fifth activity a code
change rather than a file. And it hides the one thing a reader most needs to
see, which is exactly what a profile looked at and what it could not get.

A versioned file validated against the field catalogue in CI inverts all
three. Every family name and field key in the file is resolved at validation
time, so an unknown family is a build failure, not a runtime `null`. The file
is the artefact a reader is shown. And the profile registry can be diffed:
"the running profile's humidex threshold changed on this date" is a line in
version control rather than an archaeology exercise.

## Why the profile names families and not fields

The glossary already says it: "Activity profiles refer to families; the
decision layer chooses members." Cloud is the case that forces it. HRDPS
total cloud is opacity-weighted and GFS total cloud is a geometric
maximum-random overlap fraction, and the config's hard-won facts forbid
comparing their values, thresholds or scores. A threshold written against a
family is written against the family's comparability note, and the member
chosen at evaluation time carries its own comparability so the threshold is
either applicable or the field is served with the comparability mismatch
visible. A threshold written against a single member key would be silently
wrong the moment a different centre answered.

The exception is where the profile must be specific to be honest: a
`sector` or `window` parameter, a level, a declared bearing. Those are
profile parameters, not field keys, and they are validated for range rather
than resolved against the catalogue.

## Why blocked is a state and not a null

The governing rule makes `null` mean "not retrieved, with provenance". Three
fields the four first profiles want are not merely unretrieved this cycle;
they cannot be retrieved at all under current terms. Road state has no
reusable feed. A light-pollution baseline exists only under a
non-commercial clause. The STJ magnetometer needs written permission from
NRCan. Serving those as `null` tells a reader to wait, and a reader who waits
is being misled by an honest-looking value.

`blocked` says the opposite: the evidence layer knows exactly what this field
is, knows where it lives, and is refusing to serve it for a stated reason of
licence, credential or partnership. That reason is the useful part. It is
also the state a partnership request is tracked against, which is why the
camera capability reuses it: a courtesy-notice camera is `partnership-only`
in the registry and every derivation over it is `blocked`, with Fort Amherst
named as the outstanding request.

Three absence states now exist and they are disjoint: `null` (not retrieved
this cycle), `blocked` (terms forbid it), `aged_out` (retrieved once, outside
the retention window). A fourth would be a smell; these three answer
different reader questions.

## Why hard stops are separated from grades

Lightning in range is not a low score. An alert in force is not a low score.
Precipitation above a declared rate is not a low score. Collapsing them into
a weighted sum lets a strong score on eight criteria outvote a thunderstorm,
which is the failure mode every activity-scoring product eventually ships.
Separating the two lists means a hard stop is evaluated first and answers on
its own, and the graded criteria never run. It also means a hard stop whose
field is absent is not a pass: an unknown hard stop is stated as unknown and
the profile says so, because "we could not check for lightning" is not "there
is no lightning". This is the same shape as the existing rule that absent
hazard evidence is not an all-clear.

## Why the window rule lives in derived-here geometry

Every one of the four windows is an astronomical quantity: 24 h from now,
astronomical night, dark hours, sunrise and sunset with a margin. The DE442
ephemeris entry in the derivation method registry already produces those
boundaries as derived-here fields with a pinned kernel. Writing the window
rule in those field keys means a window is computed by the same registered,
cited method as everything else, carries the same provenance, and is
reproducible from the profile file plus the kernel version. Writing it in
free text or in local wall-clock offsets would put a second, unregistered
solar model in the codebase.

## Why the site registry is minimal, and why sites are preferred not required

The temptation is a rich site model: access, parking, trail, elevation gain,
travel time. All of that is decision-layer material and none of it is
evidence. The evidence-layer question a site answers is narrow: at this
position and elevation, what is the horizon in each direction. That is what
sector sampling needs, that is what a landmark visibility bound needs, and
that is what obstruction masking needs. Everything else can be added later
without changing an evidence contract.

Sites are preferred and never limiting because the foundation already serves
every catalogue field at any point in the evidence box. A site registry that
restricted evaluation to registered points would be a regression dressed as a
feature, and it would quietly make the unregistered half of the Avalon
unavailable. The registry is a convenience list, and the specification says
so in a requirement rather than a comment, because convenience lists become
allowlists by accident.

The horizon is hand-registered because nothing publishes it at the resolution
that matters, and because a horizon derived from a digital elevation model
alone misses buildings, trees and the harbour's own structures. The DEM
horizon still has a job: it is the check that the hand registration is not
wrong, in the site registry as in camera geometry validation.

## Why sector sampling is a derivation and not a query parameter

"Cloud to the north for aurora" and "cloud in the Sun's azimuth sector" look
like sampling options. They are not: a sector sample reads many cells of a
gridded field along a bearing and reduces them to one number, which is a
computation over retrieved inputs, which is derived-here by definition. As a
registered method it carries a name, a version, a citation, declared inputs,
a declared output range and a quality no better than its worst input. As a
query parameter it would carry none of those, and its reduction rule would
live in whatever function happened to implement it.

Its inputs are restricted to retrieved gridded fields for the same reason the
class exists: a sector sample over a reprocessed or intermediary-derived
grid would launder a non-primary value into a value a profile scores.

## Why camera geometry is validated by reprojection and not trusted

Twenty-one cameras were probed and not one publishes bearing or field of
view. Every geometry in this system will therefore be someone's estimate, and
an estimate that nothing checks is a fabrication with a schema. Landmark
reprojection is the check that costs nothing to run and catches the errors
that actually happen: a bearing off by ten degrees, a field of view guessed
from the wrong sensor, a camera that was repointed and nobody noticed. The
terrain horizon from a DEM is the second, independent check, and it catches
the case reprojection cannot, which is a geometry that is self-consistent
across three landmarks and still points somewhere else.

Both checks run on registration and on demand, because "camera moved" is one
of the health flags and a moved camera is a geometry that silently stopped
being true. A geometry that fails either check is not degraded; it is
refused, and every derivation over that camera goes to `null` with the
failure named. There is no partial-credit path where a camera with a
suspicious geometry still contributes a cloud fraction.

## Why numeric visibility from an image is refused

A visibility bound from registered landmarks is defensible: the farthest
landmark still visible is a lower bound, the nearest invisible landmark is an
upper bound, both are measured distances, and the answer is an interval with
the landmarks named. A number in metres from the image alone is not
defensible, because it requires a contrast model, an assumed target
reflectance and an assumed illumination, none of which this deployment
retrieves. It is also the exact claim a reader would trust most and check
least. The interval is honest and the number is not, so the interval is
specified and the number is refused by name.

The same reasoning drives the four privacy refusals. Face and plate
recognition, person and vessel tracking, and military inference are refused
because a camera admitted to see fog must not become a surveillance input.
"Black ice detected" and camera-only safe-wave or safe-road claims are
refused because they are safety claims the imagery cannot support, and
because a reader acting on them is exposed in a way no disclosure repairs.

## Why every camera method starts disabled

The derivation method registry already has a three-level kill switch and an
`enabled` flag. Camera derivations use it as the default state rather than
the exception. Nothing here has been validated against ground truth, and CYYT
METAR is the ground truth within the evidence box: hourly visibility and
cloud, close to the harbour cameras, already retrieved. Thirty days spanning
day, night, fog, rain and snow is the smallest window that sees the Avalon's
actual conditions rather than one weather regime; a summer fortnight of fog
would validate nothing about snow on a lens.

Until a validation record exists, frames and health flags are served and
nothing is claimed from them. That is a real product: a reader looking at a
fresh Fort Amherst frame with a "lens water" flag has been told something
true, and the system has claimed nothing it cannot defend.

## Why night is a flag and not a filter

Daytime cloud fraction on a night frame is not a bad measurement; it is a
measurement of nothing, and the number it produces would look like cloud. So
the darkness flag is set at retrieval and every daytime derivation refuses on
it. The refusal is `null` with the flag named, not a substituted construction
and not a silently skipped field, so a reader sees why the sector cloud
fraction stopped at dusk.

The sky-dome camera is the one night path worth having, because star-field
visibility is a genuine night cloud signal and the NTV camera is the only
camera on the Avalon whose stated subject is the sky. It is registered now
and disabled now, so the method exists to be validated rather than being
invented later under pressure.

## Open questions carried into implementation

- The reprojection tolerance in pixels, which depends on the resolution of
  each camera and on how well the landmark pixel positions can be picked by
  hand.
- Which digital elevation model provides the terrain horizon inside the
  evidence box, and whether one model serves both the site registry and
  camera validation.
- Whether a threshold override recorded in score provenance is stored per
  score or per reader session; the requirement pins that it is recorded, not
  where.
- The shape of the validation record itself: this change requires one and
  names what it must span, and the statistics it reports are settled when the
  first camera is admitted.
