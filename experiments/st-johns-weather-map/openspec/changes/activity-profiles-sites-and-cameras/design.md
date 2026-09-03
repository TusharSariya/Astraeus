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

## Seam

Pinned by the change lead on 2026-09-03 before any task was dispatched, so
that two agents never guess the same interface. Every task prompt carries
the parts it touches verbatim. A task that needs to depart from a pin
records the departure under Deviations rather than silently renaming.

### Absence states and the per-field output contract (models.py, store.py, web)

- `api/weather_api/models.py` gains `AbsenceState = Literal["null", "blocked",
  "aged_out"]`, `ABSENCE_STATES = ("null", "blocked", "aged_out")`,
  `BLOCKED_FLAG = "blocked"` and `CONTRACT_INCOMPLETE_FLAG =
  "contract_incomplete"` beside the existing `AGED_OUT_FLAG`.
- `BlockedReason(StrictModel)`: `kind: Literal["licence", "credential",
  "partnership"]`, `source_id: str`, `terms: str` (the terms or notice, named
  or quoted), `request: str | None = None` (an outstanding permission or
  credential request, for example the Fort Amherst request).
- `EvidenceField` gains `absence_state: AbsenceState | None = None`,
  `blocked: BlockedReason | None = None` and `comparability: str | None =
  None`. A model validator fills them: `comparability` is the catalogue
  family note (`catalogue.family(name).note`) whenever the field has a key;
  when `value is None` and `absence_state` is unset it is derived from the
  flags in this order: `aged_out` in `quality.flags` -> `"aged_out"`,
  `blocked` in flags -> `"blocked"`, otherwise `"null"`. When `value` is not
  `None`, `absence_state` and `blocked` must be `None`. `absence_state ==
  "blocked"` requires `blocked` to be set and the `blocked` flag to be
  present; `absence_state == "aged_out"` keeps the existing
  `last_valid_time` rule. `retrieval_failed` and `no_retrieval` stay reason
  flags on a `"null"` absence; `available-not-stored` and `not-published`
  stay `storage` values, not absence states.
- The wire keeps the flag carrier: a blocked field is `value: null`,
  `quality.flags` containing `"blocked"` and `"blocked:<kind>"`,
  `absence_state: "blocked"`, and the `blocked` object. The web reads
  `absence_state` first and falls back to the flag order it already has.
- `api/weather_api/store.py` gains `blocked_reason_for(source: Mapping) ->
  BlockedReason | None` (status `licence-blocked` or a `restricted_terms`
  block with `redistribution: false` -> `licence`; `credential-required` ->
  `credential`; `partnership-only` -> `partnership`; `request` is taken from
  the record's `admission_condition.condition` when present),
  `blocked_field(field, *, valid_time, reason, units, key=None, level=None)
  -> EvidenceField` and `enforce_output_contract(field) -> EvidenceField`,
  which returns the field unchanged when every element (value or absence
  state, evidence class, quality, freshness, source id, comparability) is
  present and otherwise a copy with `value=None`, `absence_state="null"` and
  the flag `contract_incomplete:<element>`.

### Profile files (registry/profiles)

- One YAML file per profile at `registry/profiles/<id>.yaml`, validated by
  `registry/profiles/schema.json` (JSON Schema draft 2020-12,
  `additionalProperties: false`). Top-level keys, all required:
  `id` (`^[a-z][a-z0-9_]*$`, equal to the file stem), `version` (integer
  >= 1), `title`, `families` (list of catalogue family names), `thresholds`
  (map name -> `{field, default, units, comparison}` with `comparison` in
  `ge|gt|le|lt`; `default` required), `weights` (map criterion name ->
  number in `[0, 1]`), `hard_stops` (list of `{name, field, threshold}`),
  `graded_criteria` (list of `{name, field, threshold, weight}` where
  `weight` names a key of `weights`), `window` (below), `site_needs`
  (`{horizon_required: bool, sectors: [{name, field, bearing_deg,
  width_deg, max_range_km}]}`; a sector is a parameter set of the
  registered sector-sampling entry `sector_sampling_along_bearing`),
  `blocked_fields` (list of `{field, reason, source_id, terms, request}`,
  `reason` in `licence|credential|partnership`, `request` nullable) and
  `wanted_not_catalogued` (list of `{field, note}` for quantities the
  owner's list names that the field catalogue does not yet carry, so the
  profile discloses them instead of omitting them). No key of any kind may
  skip validation.
- `window` is `{rule, geometry_entry, geometry_fields, params}` with `rule`
  in `any_window_within_24h` (params `length_hours`, `daylight_only`),
  `astronomical_night` (sun altitude below -18), `dark_hours` (sun altitude
  below -12), `sunrise_sunset_margin` (param `margin_minutes`, around the
  -0.833 crossings); `geometry_entry` must equal
  `de442_sun_moon_geometry` and `geometry_fields` must be outputs of that
  entry (`sun_altitude`, `sun_azimuth`, `moon_altitude`, `moon_azimuth`,
  `moon_illuminated_fraction`, `moon_phase_angle`). Any `local_time`,
  `wall_clock` or hour-range key is refused at validation.
- `registry/profile_audit.py` exposes `load_profile(path) -> Profile`,
  `load_profiles(root=PROFILES_ROOT) -> dict[str, Profile | ProfileError]`,
  `audit_profile(profile) -> list[str]` and `main(argv)` with `--all` and
  `--strict` (strict also fails on warnings). It resolves families with
  `registry.fields.family`, field keys with `registry.fields.field`, units
  with `registry.fields.units_for`, and fails closed with
  `catalogue_unavailable` when the catalogue cannot be imported. A
  `blocked_fields[].field` and a `wanted_not_catalogued[].field` must match
  the catalogue key pattern but are not required to exist in the catalogue;
  a `blocked_fields[].field` that does exist in the catalogue is an error
  (an admitted source can supply it, so the entry must be removed first).
  Error strings start with the profile id and the offending name.
- Threshold field keys and the quantities the owner named that the
  catalogue lacks: humidex, wind chill, UV, AQHI, OVATION probability and a
  daylight field are listed under `wanted_not_catalogued`; the blocked
  keys are `road_state` (running, `licence`, `nl-511`),
  `light_pollution_baseline` (astronomy, `licence`, Falchi atlas
  non-commercial clause, source id `falchi-light-pollution-atlas`), and
  `magnetometer_local_disturbance` (aurora, `partnership`,
  `nrcan-stj-magnetometer`).

### Window resolution and overrides (api/weather_api/profiles)

- New package `api/weather_api/profiles/` with `__init__.py`,
  `windows.py` and `overrides.py`. Nothing in it calls Skyfield or reads the
  kernel: geometry arrives as samples.
- `windows.py`: `WindowRule` (from the profile `window` block),
  `GeometrySample(at: datetime, sun_altitude: float | None)`,
  `resolve_window(rule, samples, *, now) -> WindowResolution` where
  `WindowResolution` has `intervals: list[tuple[datetime, datetime]]`,
  `unresolved: str | None` (the absent geometry field, e.g.
  `sun_altitude`, or `geometry_entry_disabled`), and `provenance`
  (`{"derivation": "de442_sun_moon_geometry", "derivation_version":
  "de442-skyfield-1.55-v1", "kernel_sha256": EPHEMERIS_SHA256}` from
  `api.weather_api.ephemeris`). `validate_window_rule(rule) -> list[str]`
  refuses wall-clock rules naming the profile and rule. The entry is looked
  up with `ingest.derive.registry.get(DE442_GEOMETRY)` and
  `resolve(DE442_GEOMETRY)`; a refusal yields `unresolved`.
- `overrides.py`: `ThresholdOverride(threshold, profile_default, value)`,
  `OverrideProvenance(profile_id, profile_version, overrides:
  list[ThresholdOverride], no_override_in_force: bool)` and
  `record_overrides(profile, overrides: Mapping[str, float]) ->
  OverrideProvenance`; an unknown threshold name raises `ValueError`.

### Site records (registry/sites)

- One YAML file per site at `registry/sites/<id>.yaml`, schema
  `registry/sites/schema.json`. Keys, all required: `id`, `name`,
  `position: {latitude, longitude}`, `elevation: {metres, datum}` (datum
  `CGVD2013` or `WGS84_ellipsoid`), `horizon: {bearing_resolution_deg,
  elevation_deg: [...]}` with exactly `360 / bearing_resolution_deg`
  values starting at true north and every value in `[-90, 90]`;
  `terrain_check: {status, dem, tolerance_deg, terrain_elevation_deg,
  note}` with `status` in `passed|failed|not_run`, `dem` and
  `terrain_elevation_deg` nullable only when `status` is `not_run`;
  `registered: {date, by}`.
- `registry/site_audit.py` exposes `load_site(path)`, `load_sites(root)`,
  `audit_site(site) -> list[str]` (errors `site_horizon_missing`,
  `site_horizon_gap:<bearing>`, `below_terrain:<bearing>:<registered>:<terrain>`
  when the registered angle sits below the terrain angle by more than
  `tolerance_deg`) and `main(argv)` with `--all` and `--strict`.
- First three site ids: `signal-hill`, `cape-spear`, `quidi-vidi`. No DEM
  is checked into this repository, so the three records carry
  `terrain_check.status: not_run` naming the absent DEM; the below-terrain
  rule is exercised by tests with a synthetic terrain horizon.
- `api/weather_api/sites.py`: `EVIDENCE_BOX = (45.0, 50.5, -58.0, -46.0)`
  as (south, north, west, east), `inside_evidence_box(lat, lon)`,
  `load_site_registry() -> SiteRegistry` (`sites`, `notice`), and
  `horizon_for(site_id: str | None) -> Horizon | None`. A request that
  names no site gets `None` and the caller emits `null` with flag
  `no_registered_horizon`; nothing looks up a nearest site. A point outside
  the box is refused with `outside_evidence_box` naming the box.

### Derivation registry entries (ingest/derive/registry.py)

- Sector sampling keeps its name `sector_sampling_along_bearing`
  (`SECTOR_SAMPLING`) and version `geodesic-sector-v1`; task 3.4 flips it
  to `enabled=True`, rewrites its summary and adds `conventions` naming the
  reduction rule (`mean` over sampled cells), the parameters (origin,
  bearing, width, max range, elevation-angle band) and the minimum covered
  fraction (`0.8`). `ingest/derive/sector.py` exposes
  `SectorParameters(origin_latitude, origin_longitude, bearing_deg,
  width_deg, max_range_km, elevation_band_deg)`, `SectorInput(field,
  family, source_id, evidence_class, quality_status, cells:
  Sequence[tuple[lat, lon, value | None]])` and `sample_sector(inputs,
  params) -> SectorResult(value, quality_status, covered_fraction,
  refusal)`; refusal codes `input_class_refused:<class>`,
  `uncovered_fraction:<fraction>`, `blend_refused`. Pure `math`, no numpy.
- Camera entries, every one `enabled=False`, constants and names:
  `CAMERA_FOG_VISIBILITY_CLASS = "camera_fog_and_visibility_class"`
  (`camera-class-v0`), `CAMERA_VISIBILITY_BOUND =
  "camera_visibility_bound_from_landmarks"` (`camera-landmark-bound-v0`),
  `CAMERA_SECTOR_CLOUD_FRACTION = "camera_daytime_sector_cloud_fraction"`
  (`camera-sector-cloud-v0`), `CAMERA_HORIZON_FOG_BANK =
  "camera_horizon_fog_bank_presence"` (`camera-fog-bank-v0`),
  `CAMERA_SKYDOME_NIGHT_CLOUD = "camera_skydome_night_cloud_from_starfield"`
  (`camera-starfield-v0`), and `CAMERA_METHODS` naming all five. Inputs use
  `Input(field="camera_frame", family="camera_frame",
  source="registered-camera")` and, for the bound,
  `Input(field="camera_landmarks", family="camera_geometry",
  source="registered-camera")`. Outputs: `camera_fog_class` and
  `camera_visibility_class` (category) plus `camera_class_confidence`
  (fraction 0-1); `visibility_bound_lower_m` and `visibility_bound_upper_m`
  (m, 0-100000, clamp); `camera_sector_cloud_fraction` (fraction);
  `horizon_fog_bank_present` (category); `skydome_night_cloud_fraction`
  (fraction). Registration refuses a `CAMERA_METHODS` entry with
  `enabled=True` (`camera_method_enabled_without_validation`).
- `ingest/cameras/derive.py`: `NUMERIC_VISIBILITY_REFUSED =
  "numeric_visibility_from_image_refused"`; `request_numeric_visibility(...)`
  raises `RefusedClaim` naming it; `derive(method, frame, ...)` returns
  `null` with `awaiting_validation` naming the method for every disabled
  camera method.

### Camera records (registry/cameras)

- One YAML file per camera at `registry/cameras/<id>.yaml`, schema
  `registry/cameras/schema.json`. Ids: `ccg-fort-amherst`,
  `ccg-st-johns-base`, `ccg-sir-humphrey-gilbert`, `city-new-gower-street`,
  `city-middle-pond`, `city-shea-heights`, `city-thorburn-road`,
  `city-windsor-lake`, `city-kenmount-road`, `ntv-st-johns-sky`,
  `ntv-quidi-vidi-lake`, `ntv-downtown`, `ntv-george-street`,
  `ntv-admirals-green`, `ntv-logy-bay-road`, `ntv-st-philips-bell-island`,
  `ntv-port-de-grave`.
- Required keys: `id`, `name`, `source_id` (the ledger record:
  `ccg-harbour-cameras`, `city-st-johns-road-cameras`, `ntv-cameras`),
  `operator`, `status` (`partnership-only` for all seventeen), `terms:
  {text, url, read_date, redistribution: false, permission:
  {requested_on, requested_from, granted_on, document}}` (`granted_on` and
  `document` null until permission arrives; unresolved terms are stated in
  `text`), `endpoint: {url, format, cadence_seconds, cadence_measured_on}`,
  `position: {latitude, longitude, elevation: {metres, datum}, surveyed:
  bool}`, `orientation: {bearing_deg, hfov_deg, vfov_deg, roll_deg}`,
  `image: {width_px, height_px}`, `landmarks: [{name, bearing_deg,
  distance_m, pixel: {x, y}}]`, `privacy_masks: [{name, polygon:
  [[x, y], ...]}]`, `registered: {date, by}`, `geometry_validation:
  {reprojection_tolerance_px, skyline_tolerance_deg, status, dem}` with
  `status` in `not_run|passed|failed|unvalidated`. Geometry values nobody
  has registered are `null`; `registry/camera_audit.py` reports such a
  record `incomplete` naming the missing elements (`orientation.bearing_deg`
  and so on), which keeps it in the catalogue and out of retrieval.
- `registry/camera_audit.py` exposes `load_camera(path)`, `load_cameras
  (root)`, `audit_camera(camera) -> CameraVerdict(status: complete |
  incomplete, missing: list[str], errors: list[str])`,
  `retrieval_allowed(camera) -> Refusal | None` (refuses every
  `partnership-only` camera naming the camera and its terms) and `main`.
- `registry/schema.json` gains an optional source property `cameras`
  (array of camera record ids, pattern `^[a-z0-9]+(?:-[a-z0-9]+)*$`), and
  the three ledger records list their camera ids there and carry an
  `admission_condition` naming the outstanding written-permission request
  (Fort Amherst first). No status changes.

### Frames, privacy, geometry, night (ingest/cameras)

- Package `ingest/cameras/` with `__init__.py`. Modules are pure Python
  (`math`, `dataclasses`); no numpy, no Pillow. An image is a `Raster
  (width, height, pixels: bytes)` greyscale abstraction defined in
  `ingest/cameras/frames.py`.
- `frames.py`: `HEALTH_FLAGS = ("stale_or_duplicate", "blur", "darkness",
  "exposure", "obstruction", "lens_water_or_snow", "camera_moved")`,
  `CAPTURE_TIME_UNKNOWN = "capture_time_unknown"`, `Frame(camera_id,
  sha256, capture_time, retrieval_time, raster, flags: frozenset[str])`,
  `FrameStore.put(frame, previous)` computing the flags,
  `FrameStore.frame_at(camera_id, instant) -> Frame | FrameAbsence(state:
  "null" | "aged_out", detail)` with the window from
  `ingest.window.window_bounds(now)`, and `derivation_refusal(frame) ->
  str | None` naming the first raised flag.
- `privacy.py`: `MaskRegion(name, polygon)`, `apply_masks(raster, masks)
  -> Raster` (fills the polygon), `MaskUnavailable` raised when `masks` is
  empty or a polygon leaves the raster, `PRIVACY_MASK_UNAVAILABLE =
  "privacy_mask_unavailable"`, `REFUSED_CLAIMS = ("face_recognition",
  "licence_plate_recognition", "person_tracking", "vessel_tracking",
  "military_inference", "black_ice_detected", "safe_wave_camera_only",
  "safe_road_camera_only")`, `RefusedClaim(Exception)` and
  `refuse_claim(name)` raising it with rule `standing_privacy_refusal`.
- `geometry.py`: `CameraGeometry(latitude, longitude, elevation_m,
  bearing_deg, hfov_deg, vfov_deg, roll_deg, width_px, height_px)`,
  `Landmark(name, bearing_deg, distance_m, pixel_x, pixel_y)`,
  `project_landmark(geometry, landmark) -> (x, y)` by a pinhole model,
  `validate_geometry(geometry, landmarks, *, terrain_horizon:
  Sequence[float] | None, skyline: Sequence[float] | None,
  reprojection_tolerance_px, skyline_tolerance_deg) -> GeometryVerdict
  (status: "accepted" | "refused" | "not_run", reprojection_errors:
  list[(name, px)], skyline_disagreements: list[(bearing, terrain, skyline)],
  unrun_check: str | None)`, `GEOMETRY_FAILED = "geometry_failed"`, and
  `on_camera_moved(state) -> state` marking `unvalidated` and re-running
  both checks.
- `night.py`: `SUN_HORIZON_DEG = -0.833`, `darkness_flag(sun_altitude:
  float | None) -> "darkness" | "darkness_unknown" | None`, and
  `refuse_daytime_derivation(frame_flags) -> str | None`.
  `validation_record.py`: `REQUIRED_CONDITIONS = frozenset({"day", "night",
  "fog", "rain", "snow"})`, `MINIMUM_DAYS = 30`, `ValidationRecord(method,
  start, end, conditions, metar_gaps, approved_by)`, and
  `may_enable(record) -> str | None` returning
  `incomplete_validation:<missing conditions or days or gap>`.

### Web module boundaries (web/src)

- `web/src/profiles/` (6.1): `types.ts` mirroring the profile file and the
  per-field contract (`absence_state`, `blocked`, `comparability`),
  `ProfilePanel.tsx`, and the test `profile-contract.test.tsx`. It reads
  `absence_state` first and falls back to `resolveAbsenceState` from
  `../fieldFamily`.
- `web/src/sites/` (6.2): `types.ts`, `SitePanel.tsx`,
  `site-preferred.test.tsx`.
- `web/src/cameras/` (6.3): `types.ts`, `CameraPanel.tsx`,
  `camera-frames.test.tsx`; states shown are `partnership-only` and
  `awaiting_validation`; a claim from a disabled method is never rendered.
- Vitest filters by file name, so the test file names above are the verify
  commands' filters.

## Deviations

Recorded by the change lead as the task agents reported them, 2026-09-03.
None changes a registry status, admits a camera or enables a camera
derivation.

1. **Test dependencies.** `api/pyproject.toml` (dev group) gains
   `jsonschema==4.25.1` and `pyyaml==6.0.3`; jsonschema was absent from the
   api environment, and the profile, site and camera audits validate YAML
   against JSON Schema. `api/uv.lock` follows.
2. **Audit scripts.** `profile_audit.py`, `site_audit.py` and
   `camera_audit.py` all take `--root` so tests audit a temporary registry;
   `--strict` alone implies `--all`; `profile_audit.py` exposes
   `profile_warnings` beside `audit_profile` as the warning channel
   `--strict` fails on. `site_audit.py` exits 1 on a not-servable site,
   not only an unreadable one.
3. **Absence states on the wire.** The three spec states ride on the new
   explicit `EvidenceField.absence_state`. The store's five-name
   `ABSENCE_STATES` legend and the web's `resolveAbsenceState` flag order
   from earlier steps are left as they were: `retrieval_failed` and
   `no_retrieval` are reason flags on a `null` absence, and
   `available-not-stored` stays a storage value. The web profile panel folds
   a `retrieval_failed` fallback into `null`. `EvidenceField` gained two
   extra guard messages (`absence_with_value`, `blocked_without_state`)
   and `aged_out_without_flag`; `comparability` is filled only for
   catalogued fields.
4. **Blocked reasons.** `blocked_reason_for` writes `"<id>: the terms are
   not recorded in the registry"` where a record states no clause, because
   `BlockedReason.terms` is required and nothing is invented. No record
   carries status `licence-blocked` today, so the `licence` kind is
   exercised through `restricted_terms.redistribution: false`
   (`google-weathernext-2`) and `request` through a synthetic mapping.
   `missing_contract_element` is public beside `enforce_output_contract`.
5. **Profile files.** The schema carries a `wanted_not_catalogued` list the
   spec does not name, so a profile can disclose a quantity the owner
   listed that the catalogue lacks (humidex, wind chill, UV index) instead
   of omitting it. AQHI, OVATION probability and daylight are catalogue
   fields (`air_quality_health_index`, `aurora_probability`,
   `sun_altitude`) and were moved out of that list by the lead into the
   families. Blocked-field keys (`road_state`,
   `light_pollution_baseline`, `magnetometer_local_disturbance`) are not
   catalogue keys, by design: a blocked field has no admitted source.
6. **Sites.** No digital elevation model is checked into the repository, so
   all three site records carry `terrain_check.status: not_run` with the
   disclosure the spec's "No digital elevation model" scenario requires;
   the below-terrain rule is exercised with a synthetic terrain horizon.
   Horizons were hand-registered from map reading on 2026-09-03 (open sea
   at -0.5 deg for horizon dip; Quidi Vidi ridges 4 to 12 deg) and await a
   field survey, stated in an optional top-level `note`. The evidence box
   is restated in `api/weather_api/sites.py` rather than imported from an
   adapter's retrieval bounds. `HORIZON_DEPENDENT_FIELDS` names derivation
   outputs, not catalogue keys, so a horizon-dependent null is emitted with
   `key=None`.
7. **Camera records.** Seventeen records are catalogued with every geometry
   value null; `camera_audit.py` reports each `incomplete` naming the
   missing elements, which keeps them listed and out of retrieval. The
   tolerances are placeholders (5 px, 0.5 deg) because the schema requires
   positive numbers. `terms.redistribution` is `const: false`, so a
   permitted camera will need a schema conditional when permission
   arrives. `registry/schema.json` gains an optional `cameras` list on a
   source, `registry/audit.py` a `camera_id_errors` check that each listed
   id has a file, and the three ledger records an unsatisfied
   `admission_condition` naming the outstanding written-permission request
   (Fort Amherst first, sent 2026-09-02). The two other CCG cameras carry
   `requested_on: null` and say the request covers Fort Amherst first.
8. **Sector sampling** is now `enabled=True` (the proposal's Impact section
   says so; the spec's disabled scenario is still tested through the
   three kill-switch levels). `sector.py` uses spherical haversine and
   forward-azimuth formulas, documented as within 0.5 percent of the
   entry's Karney geodesic citation at this range; the elevation-angle band
   is carried in provenance and not applied to a two-dimensional grid.
   `test_disabled_entry_produces_nothing` and the reader-switch catalogue
   test now use `camera_fog_and_visibility_class` as the registered,
   disabled example.
9. **Camera derivation entries** are versioned `v0` with citations that
   name the approach as pending validation (WMO No. 8 Part I Chapter 9 for
   the landmark bound, ROI sky fraction, star-count night cloud); the
   `camera_method_enabled_without_validation` check lives in
   `validation_errors`, which `DerivationRegistry.__post_init__` runs.
   `test_the_first_entries_are_registered` was extended with the five
   names.
10. **Frames.** Every health-flag threshold is a provisional named constant
    pending the 30-day validation; `capture_time_unknown` is added by
    `compute_health_flags` and is not a member of `HEALTH_FLAGS`; a frame
    with no capture time is aged on its retrieval time.
11. **Privacy.** `RefusedClaim` is shared from `ingest/cameras/derive.py`
    rather than redefined; a raster whose pixel count disagrees with its
    size raises `MaskUnavailable` (a fourth cause beside the three pinned).
12. **Windows.** `any_window_within_24h` treats only samples inside its 24 h
    as needed, so a null altitude days out does not unresolve today's
    window; the `-0.833` crossing is interpolated linearly between samples;
    `record_overrides` also refuses a threshold with no default.
13. **Web.** The profile panel does not reuse `absenceBadge` for its rows
    because the per-field contract carries no last valid time to format;
    the three states differ in text and `data-absence`.
14. **Open questions still open.** The DEM that will serve both the site
    registry and camera validation, and the per-camera reprojection
    tolerance, remain as the design's open questions; nothing here chose
    them.
15. **Tasks 5.4, 6.2 and 6.3** reported no deviation; `may_enable` also
    refuses a non-camera method under the `incomplete_validation` prefix,
    and `ValidationRecord.days` is a read-only convenience.
16. **Gate.** Task 7.1 is left for the main session. On the lead's merged
    tip (a fresh worktree): api 1397 passed and 36 skipped, web 410 passed
    in 22 files, registry unittest 235 passed, registry audit clean, strict
    validate valid.
