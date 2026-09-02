Owned by this change: `docs/research/ensembles-and-source-plurality.md`,
`docs/research/01-atmospheric-nwp-satellite.md` (section 2 and the uncertainty
register only), `openspec/changes/ensemble-members-and-source-plurality/**`,
`openspec/config.yaml` (hard-won facts only), `registry/source_data.py`
(record corrections only). Not touched in this change: any adapter, anything
under `ingest/`, `api/` or `web/`, and any registry status promotion.

## 1. Research record

- [x] 1.1 Write `docs/research/ensembles-and-source-plurality.md` in the house
  style of `cloud-development-and-generation.md`: numbered sections, every
  claim tagged VERIFIED / REPORTED / UNREAD / GAP with the tag rule stated
  inline, endpoints as literal URLs, measurements with units and date, open
  questions struck through in place when closed.
  Verify: the tag vocabulary is defined in the document itself and every
  section 2 row carries the HTTP status it actually received.
  Verify result: written, 9 sections. Reachability table carries the status
  code for each of 8 probes made on 2026-09-02.

- [x] 1.2 Close the GEFS member-count question with a live measurement rather
  than documentation, since the AWS Open Data page still describes GEFS v11.
  Verify: page the full S3 listing for one cycle and count distinct member
  prefixes.
  Verify result: 7 listing pages for `gefs.20260901/12/atmos/pgrb2ap5/` yield
  exactly 31 members, `gec00` plus `gep01` through `gep30`. Open question 1 is
  struck through and closed in the document.

- [x] 1.3 Correct the WeatherNext 2 row in
  `docs/research/01-atmospheric-nwp-satellite.md` section 2: the licence
  splits on valid time, not run age, so every forward-looking value is in the
  restricted tier; add the verified band list and the absence of any cloud
  variable; cross-reference the new document.
  Verify: the row quotes both tier definitions verbatim and names the
  consequence for a forward-looking forecast.
  Verify result: row rewritten. Also records that an aggregator's WeatherNext
  cloud cover must be that aggregator's own humidity closure.

- [x] 1.5 Record the 2026-09-02 source re-verification in
  `docs/research/01-atmospheric-nwp-satellite.md` as sections R1 to R5, and
  correct `04-gap-analysis.md`, whose top-ranked recommendation has been
  withdrawn upstream.
  Verify: every row re-probed carries the result observed on 2026-09-02.
  Verify result: R1 records that the ECCC forecast sounding is gone, leaving a
  directory containing only `doc/`, the same shape as the GEPS and REPS
  disappearance, which makes three ECCC feeds lost in three days. R2 inventories
  GeoMet WCS: 6123 coverages, 377 HRDPS, including the 40/80/120 m
  boundary-layer stack, humidity on 28 pressure levels, boundary-layer height,
  skin temperature and ice cover. R3 re-probed VIIRS cloud base, NUCAPS and
  five GOES-19 L2 prefixes, all populated today. R4 re-probed ARCO-ERA5
  (1940 to 2026-08-26, updated 2026-09-01) and Mode-S winds aloft (11 aircraft
  overhead, 9 reporting wind and outside air temperature). R5 records the
  aggregator finding that prompted the rule change. `04-gap-analysis.md` #1 is
  struck through and the ranking replaced.

- [x] 1.4 Add the ECCC ensemble finding to the same document's uncertainty
  register: GEPS and REPS 404 on every open ECCC HTTP path including the one
  the registry declares, and survive only through GeoMet.
  Verify: the entry names the paths probed and both hosts.
  Verify result: entry 10 added, naming `dd.weather.gc.ca`, the
  `hpfx.collab.science.gc.ca` mirror, the four 404 paths, the GeoMet route for
  each ensemble, and MetPX Sarracenia as the one route not probed.

## 2. Specification

- [x] 2.1 Remove both consensus requirements from `point-evidence-sampling`
  and restate display selection without the consensus rung.
  Verify: `openspec validate ensemble-members-and-source-plurality --strict`.
  Verify result: valid. Both are REMOVED with a reason and a named
  replacement, not MODIFIED: the validator refuses a MODIFIED block that drops
  a scenario the accepted spec still carries, and the dropped scenario is the
  consensus badge itself.

- [x] 2.2 Add the source-plurality requirement and the member-sampling
  requirement to `point-evidence-sampling`, each with an absence scenario per
  `config.yaml` `rules.specs`.
  Verify: every ADDED requirement has a scenario covering absence.
  Verify result: source plurality has "One source published nothing" and "A
  published field with no number in the cell", which separate the two kinds of
  absence; member sampling has "A member dimension nobody addressed".

- [x] 2.3 Remove consensus eligibility from `source-registry-catalogue`,
  restate the surviving half as display ordering, and add the ensemble-shape
  declaration.
  Verify: the non-comparable-product scenario survives the removal.
  Verify result: carried into the replacement as "A non-comparable product is
  offered", so ocean, wave, surge, analysis and post-processed records still
  cannot be presented as raw-model air temperature.

- [x] 2.4 Add member carriage and completeness to `artifact-ingestion`, and
  the rule that a provider's own statistic is stored as retrieved.
  Verify: a partial ensemble is specified as partial, not as complete.
  Verify result: three scenarios, covering all members present, some missing
  and none decoding.

- [x] 2.5 Add the member-coordinate preservation rule to `grib-decoding`.
  Verify: the requirement says what happens when two members would collapse.
  Verify result: the decode fails naming the member values it saw, on the
  grounds that a silently collapsed ensemble is indistinguishable from a
  deterministic field.

- [x] 2.6 Add the all-sources display requirement to
  `web-evidence-interface`, including the text alternative.
  Verify: no consensus wording remains anywhere in the delta.
  Verify result: added, with scenarios for several sources, one source, no
  source, and the text alternative.

- [x] 2.7 Cross-check every REMOVED and ADDED heading against
  `openspec/specs/`, which `openspec validate` does not do: a REMOVED heading
  that exists only in another open change validates cleanly and still fails to
  apply, and an ADDED heading that already exists in the accepted spec
  collides at archive.
  Verify: script the check over the change's delta files.
  Verify result: 3 REMOVED headings all resolve against the accepted specs, 0
  ADDED headings collide.

## 2b. Source-delivery declaration (owner decision 2026-09-02)

- [x] 2b.1 Loosen the published-cell rule in `point-evidence-sampling` to
  admit a declared reprocessed source, keeping the unmodified-cell default and
  all three of its original scenarios unchanged.
  Verify: the three original scenarios survive verbatim, and the new ones
  cover an undeclared transformed source and an undocumented transformation.
  Verify result: removed and restated rather than modified, for the same
  reason as the other two: the heading had to change to stay honest, and a
  MODIFIED block cannot rename. All three original scenarios are carried
  verbatim into the replacement, plus four new ones.

- [x] 2b.2 Require every record to declare `published_cell` or `reprocessed`,
  and require a reprocessed record to name the intermediary separately from
  the producer.
  Verify: a record declaring neither is unschedulable, and a byte-for-byte
  mirror is not an intermediary.
  Verify result: both scenarios present. The mirror case matters because the
  project already retrieves NOAA data from an AWS mirror, which copies files
  rather than transforming fields, and must stay `published_cell`.

- [x] 2b.3 Require the interface to name both parties wherever a reprocessed
  value appears, including the text alternative.
  Verify: there is a scenario for the case where nothing is reprocessed.
  Verify result: present, so the label carries information rather than
  becoming decoration.

- [ ] 2b.4 Implementation, NOT in this change: add the delivery-kind field to
  `registry/schema.json` and every record in `registry/source_data.py`, the
  audit rule that refuses a reprocessed record as display primary, the
  provenance fields, and the interface label.

## 3. Registry corrections

- [x] 3.1 `google-weathernext-2`: split the licence into the historic
  Creative Commons tier with its required citation and the restricted
  real-time tier, and move `review_state` off `pending` to reflect that the
  terms have now been read. Status stays `credential_required`.
  Verify: `python3 registry/audit.py`.
  Verify result: audit valid, 63 sources, `credential_required=7` unchanged.
  `review_state` moves from `pending` to `restricted`, which is the honest
  value now that the terms have been read: the historic tier is CC BY 4.0 with
  a verbatim citation and the real-time tier restricts redistribution and
  proxying. The status reason now also records the verified band list and that
  no cloud variable exists.

- [x] 3.2 `eccc-geps` and `eccc-reps`: correct `access_endpoints` to the
  GeoMet route and record the 404 evidence in the status reason.
  Verify: `python3 registry/audit.py && python3 -m unittest discover -s registry/tests`.
  Verify result: audit valid, 6 registry tests pass. `_eccc_model` gained
  optional `endpoints` and `reason` overrides, because it hard-coded
  `dd.weather.gc.ca/today/model_<name>/` for every ECCC record and a default
  that 404s reads as verified. Both records now point at GeoMet and carry the
  probe evidence. GEPS's product name and levels were corrected too: it was
  described as "all members and control", which is the opposite of what it
  publishes.

## 4. Governing record

- [x] 4.1 Add the new hard-won facts to `openspec/config.yaml`: the consensus
  contradiction and its resolution, so nobody reintroduces the gate; GEFS
  total cloud is a six-hour average; GEPS publishes no members while REPS
  publishes 21 through GeoMet and both are 404 on the open HTTP feed;
  WeatherNext 2 publishes no cloud variable.
  Verify: `make spec-validate` and `openspec validate --all`.
  Verify result: `specctl validate` reports 0 errors and 0 warnings;
  `openspec validate --all` reports 30 passed, 0 failed, up from 29 with this
  change added. Five facts added.

## 5. Whole-change verification

- [x] 5.1 `openspec validate ensemble-members-and-source-plurality --strict && openspec validate --all`
- [x] 5.2 `make spec-validate`
- [x] 5.3 `python3 registry/audit.py && python3 -m unittest discover -s registry/tests`
- [x] 5.4 `cd api && uv run pytest -q` — no code changed in this change, so the
  suite must be exactly as it was. Result: 787 tests, 2 failures, both the
  pre-existing `test_layer_frame_contract` GOES and aurora frame-roll cases,
  25 skipped. The registry edit was checked not to shift collection by running
  `tests/test_api.py` with and without it: both collect the same four cases of
  `test_refresh_rejects_a_source_the_scheduler_could_never_run`.

## 6. Owner gates (owner decisions; agents do not tick these)

- [ ] 6.1 Accept the removal of consensus. It is a behaviour change readers
  will see, and no implementation may start before it.
- [ ] 6.2 Decide whether WeatherNext 2 is worth pursuing at all given that it
  publishes no cloud variable, and if so whether the restricted real-time
  terms will be accepted or only the Creative Commons historic tier used.
- [ ] 6.3 Decide whether GeoMet WCS becomes the main ECCC route now that three
  Datamart feeds have been withdrawn, and accept the upstream-call cost of a
  per-layer coverage fan-out against the budget `geomet-wms-access` enforces.
- [ ] 6.4 Decide the ensemble ingest order, given that GEFS is 31 files per
  lead and REPS is a large GeoMet fan-out against an upstream call budget.
