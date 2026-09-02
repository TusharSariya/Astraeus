## Why

The evidence layer now has a field catalogue with families
(`field-catalogue-and-families`) and six evidence classes with an
owner-approved derivation method registry
(`evidence-classes-and-derived-here`). What it does not have is any
statement of what an activity asks the evidence layer for. Running,
astronomy, aurora and landscape photography have been named in the glossary
since the first commit, but nothing says what a profile is made of, where a
profile is evaluated, or what a profile is told when the evidence it names
cannot be served.

That gap has a cost the research already measured. Road state has no feed:
NL 511 needs a key and its terms grant no reuse (wayfinder ticket 11). A
light-pollution baseline exists only in the Falchi atlas under a
non-commercial clause. The St. John's STJ magnetometer forbids
redistribution without written permission from NRCan (wayfinder ticket 8).
Each is a field a profile would name and none can be served. Today the only
honest answer the contract can give is `null`, which reads as "we did not
retrieve it this cycle" and invites a reader to wait for a value that will
never come.

Cameras have the same shape of problem one level lower. Twenty-one Avalon
cameras were probed and not one operator publishes position, bearing or
field of view, so camera geometry must be hand-registered
(`docs/research/wayfinder/camera-inventory.md` on branch
`research/camera-inventory`, wayfinder ticket 12). Three Coast Guard
harbour cameras carry a courtesy notice rather than a licence, six City of
St. John's road cameras carry no licence statement at all, and the eight NTV
cameras, including the only sky-dome camera on the peninsula, are a
broadcaster's assets with all rights reserved. Admitting any of them by
default would put unlicensed imagery on a data path.

The owner resolved both on 2026-09-02: wayfinder ticket 19 (activity profile
shape, the site registry, sector sampling, the four first profiles, the
output contract) and wayfinder ticket 21 (camera geometry registration,
admission by terms, frames as evidence, the permitted derivations, the
validation gate, the privacy refusals, night). This change writes those two
resolutions into the specification. It admits no camera, promotes no
registry status, enables no derivation method and adds no scoring code.

## What Changes

- **An activity profile is declarative data, not a code path.** A versioned
  file in a profile registry, validated in CI against the field catalogue,
  naming the field families it reads, thresholds, weights, hard stops
  separated from graded criteria, a window rule and its site needs. A new
  activity is a new file.
- **Thresholds are defaults plus per-reader overrides**, and any override is
  recorded in the provenance of the score it produced. User-defined profiles
  are out of scope here.
- **Window rules are expressed in derived-here geometry fields** from the
  pinned DE442 ephemeris: any window of a declared length in the next 24 h
  for running, astronomical night for astronomy, dark hours for aurora,
  sunrise and sunset plus or minus a declared margin for landscape
  photography.
- **Blocked fields are listed explicitly in the profile**, never silently
  omitted: road state for running, a light-pollution baseline for astronomy,
  the local magnetometer for aurora.
- **The output contract per field gains a `blocked` state** distinct from
  `null`, distinct in turn from the `aged_out` state the owner settled in
  wayfinder ticket 20. Every field returned to a
  profile carries value, evidence class, quality, freshness, source,
  comparability within its family, and its absence state.
- **The profile is a contract on the evidence layer only.** The decision
  layer that scores profiles is out of scope for this change; nothing here
  ranks, recommends or chooses.
- **A minimal site registry** is added: a site is a registered entity with
  position, elevation and a hand-registered directional horizon. Sites are
  preferred locations, not the only ones; every catalogue field is served at
  any point in the evidence box, and a profile may be evaluated anywhere.
- **Sector sampling along a bearing from a site** becomes a registered
  derivation method of class `derived_here`, reading only retrieved gridded
  fields. It is the entry already named in
  `evidence-classes-and-derived-here`, now given its own requirements.
- **A camera registration record** carries operator and terms, retrieval
  endpoint and cadence, position with elevation, bearing, horizontal and
  vertical field of view, roll, horizon landmarks with bearing, distance and
  pixel position, privacy mask regions, and the date and person of
  registration.
- **A geometry is accepted only by validation**: reprojecting the registered
  landmarks must reproduce their pixel positions within a declared tolerance,
  and a terrain horizon from a digital elevation model must match the visible
  skyline.
- **No camera is admitted without a licence or written permission.**
  Courtesy-notice and no-licence cameras are catalogued `partnership-only`.
  Fort Amherst is the first permission request.
- **Frames are stored with health flags** (stale or duplicate, blur,
  darkness, exposure, obstruction, lens water or snow, camera moved) under
  the general retention rule.
- **Four camera derivations are permitted** and numeric visibility is
  refused: fog and visibility classes with a confidence, a visibility bound
  from the farthest visible and nearest invisible registered landmark,
  daytime cloud fraction in the camera's sector, and horizon fog-bank
  presence.
- **Camera methods enter the derivation registry disabled** and are enabled
  only after a validation record against CYYT METAR visibility and cloud
  over at least 30 days spanning day, night, fog, rain and snow. Until then
  only frames and health flags are served.
- **The privacy refusals are standing rules**: mask private regions; no face
  or plate recognition, no person or vessel tracking, no military inference,
  no "black ice detected", no camera-only safe-wave or safe-road claim.
- **Night frames carry a darkness flag** and no daytime derivation runs on
  them. Night cloud from the NTV sky-dome camera by star-field visibility is
  registered now as a method, disabled pending validation.

## Capabilities

### New Capabilities

- `activity-profile`: the shape of a profile file, its CI validation against
  the field catalogue, thresholds and overrides, hard stops versus grades,
  window rules, site needs, blocked fields, the four first profiles' family
  lists, the per-field output contract, and the boundary that keeps scoring
  out of the evidence layer.
- `site-registry`: what a site is, what its record carries, the
  hand-registered directional horizon, the rule that sites are preferred and
  never limiting, and sector sampling as a registered derived-here method.
- `camera-evidence`: the camera registration record, geometry validation by
  landmark reprojection against a terrain horizon, admission by licence or
  written permission, frames and health flags under retention, the four
  permitted derivations and the refusal of numeric visibility, the 30-day
  METAR validation gate, the privacy refusals, and night handling.

### Modified Capabilities

- `point-evidence-sampling`: the absence contract gains `blocked` beside
  `null`, and every served field carries the full per-field output contract a
  profile reads.
- `source-registry-catalogue`: the `partnership-only` state this change
  relies on is specified once, in `source-admissions-ledger`'s modification
  of the status-ceiling requirement, so the two changes do not modify the
  same requirement twice; this change adds no delta of its own to that
  capability and is applied after the ledger.

## Impact

- `registry/profiles/` (new): one versioned YAML file per profile, plus a
  schema; `registry/profile_audit.py` validating every named family and field
  against the field catalogue.
- `registry/sites/` (new): the site registry with position, elevation and a
  directional horizon per site; Signal Hill, Cape Spear and Quidi Vidi first.
- `registry/cameras/` (new): camera registration records and their terms
  evidence; `registry/schema.json` and `registry/source_data.py` gain the
  `partnership-only` status and the camera record shape.
- `api/weather_api/models.py`: the per-field output contract gains `blocked`
  as an absence state beside `null` and `aged_out`; a threshold override is
  carried in score provenance.
- `ingest/derive/registry.py`: entries for sector sampling (enabled) and for
  the four camera derivations plus sky-dome night cloud (all disabled).
- `ingest/cameras/` (new): frame retrieval, health flags, privacy masking,
  darkness flagging.
- No camera is admitted, no registry status is promoted, no camera
  derivation is enabled, `operational` stays `false`. Spec-Impact: none
  outside this experiment.
