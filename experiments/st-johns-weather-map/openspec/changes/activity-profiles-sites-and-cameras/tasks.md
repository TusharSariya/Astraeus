Owned by this change:
`openspec/changes/activity-profiles-sites-and-cameras/**`,
`registry/profiles/**` (new), `registry/profile_audit.py` (new),
`registry/sites/**` (new), `registry/site_audit.py` (new),
`registry/cameras/**` (new), `registry/schema.json` and
`registry/source_data.py` (the `partnership-only` status and the camera
record shape only), `api/weather_api/models.py` (the absence states and the
per-field output contract only), `api/weather_api/store.py` (absence-state
emission only), `ingest/derive/registry.py` (the sector-sampling entry and
the five disabled camera entries only), `ingest/cameras/**` (new),
`web/src/profiles/**` and `web/src/sites/**` (new), and the tests named
below.

Not touched: any adapter's retrieval logic, `openspec/config.yaml`
carve-outs, the evidence-class definitions of
`evidence-classes-and-derived-here`, the field catalogue itself from
`field-catalogue-and-families`, and any registry status promotion. No camera
is admitted and no camera derivation is enabled by this change.

Work is parallelisable across four owners: profiles; sites and derivation;
cameras; API and web. Do not edit `api/weather_api/models.py` from two owners
at once, and do not edit `ingest/derive/registry.py` from the sites owner and
the cameras owner at once.

Sources: wayfinder ticket 19 (activity profiles and the site registry),
wayfinder ticket 21 (camera geometry and admission), and the camera research
at `docs/research/wayfinder/camera-inventory.md` on branch
`research/camera-inventory`.

## 1. Profile registry and validation (profiles owner)

- [x] 1.1 Create `registry/profiles/schema.json` and the profile file shape:
  id, version, title, families, thresholds with defaults, weights, hard
  stops, graded criteria, window rule, site needs, blocked fields.
  Owns: `registry/profiles/schema.json`.
  Verify: `cd api && uv run pytest tests/test_profile_registry.py -k schema`
- [x] 1.2 Write `registry/profile_audit.py`: resolve every family, field key,
  level and unit against the field catalogue; refuse an unknown family, a
  unit mismatch, a weight out of range, a threshold with no default, and a
  field named in both the hard stops and the graded criteria.
  Owns: `registry/profile_audit.py`.
  Verify: `cd api && uv run pytest tests/test_profile_registry.py -k
  "unknown_family or unit_mismatch or no_default or both_lists"`
- [x] 1.3 Add the four first profile files with the family lists the owner
  adopted on wayfinder ticket 19, each listing its blocked fields (road
  state; light-pollution baseline; local magnetometer).
  Owns: `registry/profiles/running.yaml`, `astronomy.yaml`, `aurora.yaml`,
  `landscape_photography.yaml`.
  Verify: `python3 registry/profile_audit.py --all`
- [x] 1.4 Wire profile validation into CI so an unknown family fails the
  build, and make it unskippable by any profile file flag.
  Owns: the profile step of the registry CI target.
  Verify: `make spec-validate && python3 registry/profile_audit.py --strict`

## 2. Window rules and the output contract (API owner)

- [ ] 2.1 Resolve window rules from the registered DE442 geometry entry only;
  refuse a wall-clock window rule at validation; report an unresolved window
  naming the absent geometry field.
  Owns: `api/weather_api/profiles/windows.py` (new).
  Verify: `cd api && uv run pytest tests/test_profile_windows.py`
- [x] 2.2 Add the disjoint absence states `null`, `blocked` and `aged_out`
  and the per-field output contract (value, evidence class, quality,
  freshness, source, comparability, absence state) to the models.
  Owns: `api/weather_api/models.py`.
  Verify: `cd api && uv run pytest tests/test_models.py -k
  "absence_state or output_contract"`
- [x] 2.3 Emit `blocked` with its reason for a field no admitted source may
  redistribute, and `contract_incomplete` as `null` for a field missing any
  contract element.
  Owns: `api/weather_api/store.py`.
  Verify: `cd api && uv run pytest tests/test_point_evidence.py -k
  "blocked or contract_incomplete"`
- [ ] 2.4 Record any threshold override in the provenance of the score it
  produced, and record explicitly when no override was in force.
  Owns: `api/weather_api/profiles/overrides.py` (new).
  Verify: `cd api && uv run pytest tests/test_profile_overrides.py`

## 3. Site registry and sector sampling (sites owner)

- [ ] 3.1 Create the site record shape and `registry/site_audit.py`: id,
  name, position, elevation with datum, directional horizon at a declared
  bearing resolution, registration date and person; refuse a site with a
  missing or gapped horizon.
  Owns: `registry/sites/schema.json`, `registry/site_audit.py`.
  Verify: `cd api && uv run pytest tests/test_site_registry.py -k
  "no_horizon or horizon_gap"`
- [ ] 3.2 Register Signal Hill, Cape Spear and Quidi Vidi, each with a
  hand-registered horizon and a recorded DEM terrain-horizon check; fail a
  registration that sits below terrain beyond tolerance.
  Owns: `registry/sites/*.yaml`.
  Verify: `python3 registry/site_audit.py --all`
- [ ] 3.3 Enforce that sites are preferred and never limiting: serve every
  catalogue field at any point in the evidence box, and return `null` with
  `no_registered_horizon` for a horizon-dependent field off-site without
  borrowing a nearby site's horizon.
  Owns: `api/weather_api/sites.py` (new).
  Verify: `cd api && uv run pytest tests/test_site_registry.py -k
  "off_site or no_registered_horizon"`
- [ ] 3.4 Register the sector-sampling derivation entry (name, version,
  citation, inputs, output, range, range rule, reduction rule, parameters);
  refuse any input whose evidence class is not `retrieved`; carry the worst
  input's quality.
  Owns: the sector-sampling entry in `ingest/derive/registry.py`,
  `ingest/derive/sector.py` (new).
  Verify: `cd api && uv run pytest tests/test_derivation_registry.py -k
  sector_sampling`

## 4. Camera registration and geometry (cameras owner)

- [x] 4.1 Create the camera registration record shape covering every element
  of wayfinder ticket 21 item 1, and refuse an incomplete record naming the
  missing elements.
  Owns: `registry/cameras/schema.json`, `registry/camera_audit.py` (new).
  Verify: `cd api && uv run pytest tests/test_camera_registry.py -k
  incomplete_record`
- [x] 4.2 Implement landmark reprojection and the DEM terrain-horizon check;
  refuse a geometry that fails either, with no degraded path, and re-run both
  when `camera_moved` is raised.
  Owns: `ingest/cameras/geometry.py` (new).
  Verify: `cd api && uv run pytest tests/test_camera_geometry.py -k
  "reprojection_failed or skyline_mismatch or camera_moved"`
- [ ] 4.3 Catalogue the Coast Guard, City of St. John's and NTV cameras as
  `partnership-only` with their terms quoted from
  `docs/research/wayfinder/camera-inventory.md`, record Fort Amherst as the
  first permission request, and refuse retrieval for any of them.
  Owns: `registry/cameras/*.yaml`, the `partnership-only` status in
  `registry/schema.json` and `registry/source_data.py`.
  Verify: `python3 registry/audit.py && python3 -m unittest discover -s
  registry/tests -v`

## 5. Camera frames, derivations and refusals (cameras owner)

- [ ] 5.1 Store frames with the image, capture and retrieval times and the
  seven computed health flags under the general retention rule; refuse every
  derivation over a frame with a raised flag, naming it.
  Owns: `ingest/cameras/frames.py` (new).
  Verify: `cd api && uv run pytest tests/test_camera_frames.py -k
  "health_flag or duplicate or aged_out"`
- [ ] 5.2 Apply privacy masks before storage and service, discard a frame
  whose mask cannot be applied, and refuse the named claims (face and plate
  recognition, person and vessel tracking, military inference, black ice,
  camera-only safe-wave and safe-road).
  Owns: `ingest/cameras/privacy.py` (new).
  Verify: `cd api && uv run pytest tests/test_camera_privacy.py`
- [ ] 5.3 Register the four permitted derivations plus sky-dome night cloud
  as registry entries with `enabled: false`, and refuse numeric visibility in
  metres from an image by name.
  Owns: the camera entries in `ingest/derive/registry.py`,
  `ingest/cameras/derive.py` (new).
  Verify: `cd api && uv run pytest tests/test_derivation_registry.py -k
  "camera_disabled or numeric_visibility_refused"`
- [ ] 5.4 Flag night frames from the registered DE442 daylight boundaries,
  refuse every daytime derivation on a darkness or `darkness_unknown` frame,
  and require a 30-day METAR validation record spanning day, night, fog, rain
  and snow before any camera method may be enabled.
  Owns: `ingest/cameras/night.py` (new),
  `ingest/cameras/validation_record.py` (new).
  Verify: `cd api && uv run pytest tests/test_camera_night.py -k
  "night_frame or darkness_unknown or incomplete_validation"`

## 6. Web (web owner)

- [ ] 6.1 Show a profile's families, thresholds with any override, hard stops
  separated from grades, its window and its blocked fields with reasons;
  render `blocked`, `null` and `aged_out` as three distinguishable states.
  Owns: `web/src/profiles/`.
  Verify: `cd web && npm test -- --run profile-contract`
- [ ] 6.2 Show sites as preferred locations with their horizons, keep
  arbitrary points selectable, and state `no_registered_horizon` where a
  horizon-dependent field is unavailable off-site.
  Owns: `web/src/sites/`.
  Verify: `cd web && npm test -- --run site-preferred`
- [ ] 6.3 Show camera frames with their health flags and their
  `partnership-only` or `awaiting_validation` state, and never present a
  camera-derived claim from a disabled method.
  Owns: `web/src/cameras/` (new).
  Verify: `cd web && npm test -- --run camera-frames`

## 7. Gate

- [ ] 7.1 Run the full suite and both spec validators.
  Verify: `make test`, `openspec validate
  activity-profiles-sites-and-cameras --strict`, and `uv run --project
  ../../tools/specs python ../../tools/specs/specctl.py validate`
