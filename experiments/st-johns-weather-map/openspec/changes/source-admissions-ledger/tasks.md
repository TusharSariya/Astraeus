Owned by this change: `openspec/changes/source-admissions-ledger/**`,
`registry/schema.json` (the `status` enum, the credential block, the
restricted-terms block, the condition block), `registry/source_data.py` (every
record edit below), `registry/audit.py` (state, credential, terms, condition
and ledger-completeness rules), `registry/tests/**`,
`api/weather_api/sources.py` (the ceiling table and schedulability),
`api/weather_api/tests/` for the two API tasks, and the `CONTEXT.md` glossary
line for registry state.

Not touched: any adapter's retrieval logic, `openspec/config.yaml` carve-outs,
`api/weather_api/models.py` (owned by
`openspec/changes/evidence-classes-and-derived-here/`), the requirement "The
registry is the only catalogue" (removed and replaced by
`openspec/changes/ensemble-members-and-source-plurality/`), and any delivery
kind definition (same change). No record is promoted; `operational` stays
unreachable.

Owners: **Schema owner** (sections 1 and 2), **Registry owner** (sections 3 to
8, the record edits), **API owner** (section 9), **Gate owner** (section 10).
Sections 3 to 8 are parallelisable across several registry owners because the
records are disjoint, but only one owner at a time may hold
`registry/source_data.py`; split by taking the sections in order and rebasing,
never by concurrent edits to that file.

Verification commands used below, run from
`experiments/st-johns-weather-map/`:

- `python3 registry/audit.py`
- `python3 -m unittest discover -s registry/tests -v`

## 1. State vocabulary in the schema (Schema owner)

- [x] 1.1 Replace `$defs/status` in `registry/schema.json` with the ten states
  `operational`, `implemented-unverified`, `catalogued`, `credential-required`,
  `licence-blocked`, `link-only`, `partnership-only`, `unavailable`,
  `rejected`, `superseded`.
  Verify: `python3 registry/audit.py` reports every record against the new
  enum and fails on any record still carrying `implementing`,
  `credential_required`, `licence_review`, `retired`, `duplicate_evidence` or
  `unsupported_field`.
- [x] 1.2 Add the `credential` block (credential name, registration URL, no
  value field permitted) required for state `credential-required`, and the
  `restricted_terms` block (`terms_text`, `terms_source_url`,
  `redistribution: false`, read date).
  Verify: `python3 -m unittest discover -s registry/tests -v` with new cases
  `test_credential_block_required` and `test_restricted_terms_require_text`.
- [x] 1.3 Add the `admission_condition` block (condition text, what would
  satisfy it, satisfied flag) and the `superseded_by` field required for state
  `superseded`.
  Verify: `python3 -m unittest discover -s registry/tests -v` with
  `test_superseded_requires_successor` and
  `test_condition_blocks_schedulability`.
- [x] 1.4 Update `CONTEXT.md`'s registry-state glossary line to note that the
  state the glossary calls credential-blocked is written
  `credential-required`.
  Verify: `python3 registry/audit.py` cross-checks the glossary state list
  against the schema enum and passes.

## 2. Audit rules (Schema owner)

- [x] 2.1 Refuse `operational` on any record, and map every unknown state to
  `unavailable` in the exported ceiling rather than guessing.
  Verify: `python3 -m unittest discover -s registry/tests -v -k operational`.
- [x] 2.2 Implement the `implementing` split rule: `implemented-unverified`
  only when a registered adapter claims the id, `integration.kind` is not
  `link_only` and `fixture_status` is `passing`; `catalogued` otherwise.
  Verify: `python3 registry/audit.py --summary-json` shows the two counts and
  no record left on a retired status value.
- [x] 2.3 Add ledger completeness: every source id named in the resolutions of
  tickets 24, 25, 26 and 28 has a record, and every record has a state, an
  access path or an explicit none, and a reason.
  Verify: `python3 -m unittest discover -s registry/tests -v -k ledger`.
- [x] 2.4 Refuse a record that declares restricted terms without terms text or
  source URL, and refuse an export path carrying such values.
  Verify: `python3 -m unittest discover -s registry/tests -v -k restricted`.
- [x] 2.5 Refuse an access endpoint on any `link-only` or `partnership-only`
  record.
  Verify: `python3 -m unittest discover -s registry/tests -v -k no_endpoint`.

## 3. Migrate the 63 existing records (Registry owner)

- [x] 3.1 Migrate every `implementing` record by the 2.2 rule, writing the
  resulting state and keeping each record's existing status reason.
  Verify: `python3 registry/audit.py`.
- [x] 3.2 Rename the seven `credential_required` records to
  `credential-required` and give each its `credential` block:
  `google-weathernext-2`, `copernicus-cams`, `nasa-earthdata-aerosol`,
  `nl-511`, `noaa-madis`, `purpleair`, `openaq`.
  Verify: `python3 registry/audit.py`.
- [x] 3.3 Migrate the two `unavailable` records unchanged (`nl-511-rwis`,
  `municipal-hydrometric`) and confirm each states why.
  Verify: `python3 registry/audit.py`.

## 4. State changes on existing records (Registry owner)

- [x] 4.1 `eccc-rewps` to `rejected`, reason: Great Lakes domain only, verified
  on GeoMet 2026-09-02; no access path.
  Verify: `python3 -m unittest discover -s registry/tests -v -k rewps`.
- [x] 4.2 `eccc-radiosonde` to `unavailable`, reason: the CYYT sounding is gone
  from Datamart and absent from GeoMet, the served vertical profile is HRDPS
  and RDPS pressure levels, with a standing re-probe recorded.
  Verify: `python3 -m unittest discover -s registry/tests -v -k radiosonde`.
- [x] 4.3 `eccc-raqdps-firework` from `retired` to `superseded`, with
  `superseded_by` naming the RAQDPS smoke-plume layers.
  Verify: `python3 -m unittest discover -s registry/tests -v -k firework`.
- [x] 4.4 `nav-canada-weather-cameras` from `licence_review` to
  `credential-required`, credential NC-SPACES account, reason: the public
  registry endpoint is dead and the owner holds NC-SPACES credentials.
  Verify: `python3 -m unittest discover -s registry/tests -v -k nav_canada`.
- [x] 4.5 `provincial-hydrometric` from `licence_review` to `catalogued`, and
  `raw-cwop-pws` from `licence_review` to `implemented-unverified` carrying the
  unread-terms admission condition until the CWOP licence text is recorded.
  Verify: `python3 registry/audit.py`.
- [x] 4.6 `eccc-integrated-nowcasting` to `catalogued` with the WMS re-probe as
  its admission condition (zero WCS coverages on 2026-09-02).
  Verify: `python3 -m unittest discover -s registry/tests -v -k nowcasting`.
- [x] 4.7 `eccc-rdwps` to `implemented-unverified` with the Atlantic-domain
  check over the evidence box as an outstanding admission condition.
  Verify: `python3 -m unittest discover -s registry/tests -v -k rdwps`.
- [x] 4.8 `noaa-goes-east` re-pointed at GOES-19 with the admitted product set
  (Enterprise Cloud Mask, ABI-L2-CCLF five-layer cloud fraction, cloud-top
  height at 2 km, cloud-top phase and temperature) and the recorded fact that
  no fog product exists.
  Verify: `python3 -m unittest discover -s registry/tests -v -k goes`.
- [x] 4.9 `noaa-swpc-rtsw` to `catalogued` with the re-implementation condition:
  the feed now interleaves SWFO-L1, ACE and IMAP and every quality flag must be
  stored.
  Verify: `python3 -m unittest discover -s registry/tests -v -k rtsw`.
- [x] 4.10 Correct the `copernicus-cams` licence text to the ADS catalogue's
  CC BY 4.0, with the catalogue URL and read date.
  Verify: `python3 -m unittest discover -s registry/tests -v -k cams_licence`.

## 5. New space-weather and astronomy records (Registry owner)

- [x] 5.1 `celestrak-gp`, `implemented-unverified`, CelesTrak GP element sets,
  with the unread-usage-policy admission condition; passes stay derived-here.
  Verify: `python3 -m unittest discover -s registry/tests -v -k celestrak`.
- [x] 5.2 `space-track`, `rejected`, no access path, reason: CelesTrak serves
  the same elements without the account terms.
  Verify: `python3 registry/audit.py`.
- [x] 5.3 `noaa-swpc-plasma`, `implemented-unverified`, SWPC plasma product.
  Verify: `python3 registry/audit.py`.
- [x] 5.4 `noaa-swpc-propagated-solar-wind`, `implemented-unverified`.
  Verify: `python3 registry/audit.py`.
- [x] 5.5 `noaa-swpc-kp-1m`, `implemented-unverified`, 1-minute Kp.
  Verify: `python3 registry/audit.py`.
- [x] 5.6 `noaa-swpc-alerts`, `implemented-unverified`, alert text products.
  Verify: `python3 registry/audit.py`.
- [x] 5.7 `noaa-swpc-scales`, `implemented-unverified`, NOAA scales.
  Verify: `python3 registry/audit.py`.
- [x] 5.8 `gfz-hp30`, `implemented-unverified`, GFZ Hp30 half-hour index.
  Verify: `python3 registry/audit.py`.
- [x] 5.9 `noaa-goes-magnetometer`, `implemented-unverified`.
  Verify: `python3 registry/audit.py`.
- [x] 5.10 `noaa-goes-xray`, `implemented-unverified`, X-ray flux.
  Verify: `python3 registry/audit.py`.
- [x] 5.11 `noaa-swpc-kyoto-dst`, `implemented-unverified`, delivery kind
  `reprocessed`, producer Kyoto WDC, intermediary SWPC.
  Verify: `python3 -m unittest discover -s registry/tests -v -k dst`.
- [x] 5.12 `noaa-swpc-stereo-a` and `noaa-swpc-kp-hourly-prediction`,
  `unavailable`, reason: stale behind HTTP 200.
  Verify: `python3 registry/audit.py`.
- [x] 5.13 `nrcan-stj-magnetometer`, `partnership-only`, no access path,
  reason: NRCan FDSN terms forbid redistribution without written permission;
  record the request sent with Fort Amherst.
  Verify: `python3 -m unittest discover -s registry/tests -v -k magnetometer`.
- [x] 5.14 `space-weather-canada-regional` and
  `nasa-soho-sdo-goes-suvi-imagery`, `link-only`, citation only, no endpoint.
  Verify: `python3 -m unittest discover -s registry/tests -v -k link_only`.

## 6. New aggregator and foreign-model records (Registry owner)

- [x] 6.1 `openmeteo-cams-aod`, `implemented-unverified`, `reprocessed`,
  producer CAMS, intermediary Open-Meteo, the six transformations plus the 0.1
  versus 0.4 degree upsampling trap and the no-speciation limit.
  Verify: `python3 -m unittest discover -s registry/tests -v -k cams_aod`.
- [x] 6.2 `openmeteo-lsa-saf-radiation`, `implemented-unverified`,
  `reprocessed`, producer EUMETSAT LSA SAF, intermediary Open-Meteo, with the
  Meteosat limb-geometry check as an outstanding admission condition.
  Verify: `python3 -m unittest discover -s registry/tests -v -k lsa_saf`.
- [x] 6.3 `openmeteo-gfs-wave`, `implemented-unverified`, `reprocessed`, model
  `ncep_gfswave016`, with `cell_selection=sea` mandatory and the all-null
  column recorded as a retrieval failure.
  Verify: `python3 -m unittest discover -s registry/tests -v -k gfs_wave`.
- [x] 6.4 `openmeteo-jma-gsm`, `implemented-unverified`, `reprocessed`,
  producer JMA, intermediary Open-Meteo, six transformations named.
  Verify: `python3 registry/audit.py`.
- [x] 6.5 `openmeteo-arpege`, `implemented-unverified`, `reprocessed`, producer
  Météo-France, intermediary Open-Meteo.
  Verify: `python3 registry/audit.py`.
- [x] 6.6 `openmeteo-ukmo-global`, `implemented-unverified`, `reprocessed`,
  restricted terms CC BY-SA recorded, `redistribution: false`.
  Verify: `python3 -m unittest discover -s registry/tests -v -k ukmo`.
- [x] 6.7 `brightsky-dwd-mosmix-71801`, `implemented-unverified`,
  `reprocessed`, producer DWD, intermediary Bright Sky, station 71801.
  Verify: `python3 registry/audit.py`.
- [x] 6.8 `openmeteo-kma-gdps`, `openmeteo-cma-grapes`, `openmeteo-graphcast`,
  `unavailable`, reasons stale, flat and null respectively.
  Verify: `python3 -m unittest discover -s registry/tests -v -k unavailable_aggregator`.
- [x] 6.9 `openmeteo-weathernext-2-cloud`, `implemented-unverified`, delivery
  kind `intermediary_derived`, producer Google WeatherNext 2, intermediary
  Open-Meteo, never display primary, never a derivation input.
  Verify: `python3 -m unittest discover -s registry/tests -v -k weathernext_cloud`.
- [x] 6.10 The Open-Meteo catalogued set:
  `openmeteo-air-quality-particulates`, `openmeteo-marine-currents-sealevel`,
  `openmeteo-glofas`, `openmeteo-elevation`, each `catalogued` with its reason.
  Verify: `python3 registry/audit.py`.
- [x] 6.11 The Open-Meteo refused set: `openmeteo-marine-sst`,
  `openmeteo-uv-index`, `openmeteo-pollen-ammonia`, `openmeteo-aqi-indices`,
  `openmeteo-beam-split`, `openmeteo-climate-cmip6`,
  `openmeteo-seasonal-seas5`, each `rejected` with its reason.
  Verify: `python3 -m unittest discover -s registry/tests -v -k openmeteo_rejected`.

## 7. New local, marine and transparency records (Registry owner)

- [x] 7.1 `eccc-riops`, `implemented-unverified`, GeoMet every field, reason:
  the Datamart root path is 404 and GeoMet is the path.
  Verify: `python3 registry/audit.py`.
- [x] 7.2 `eccc-gdwps`, `implemented-unverified` with the Atlantic-domain check
  as an outstanding admission condition.
  Verify: `python3 -m unittest discover -s registry/tests -v -k gdwps`.
- [x] 7.3 `ccg-navwarn`, `implemented-unverified`, Coast Guard NAVWARN hazard
  feed.
  Verify: `python3 registry/audit.py`.
- [x] 7.4 `nl-air-quality-csv`, `implemented-unverified`, uncalibrated
  observation, NL provincial hourly PM2.5 and ozone CSV, provisional.
  Verify: `python3 -m unittest discover -s registry/tests -v -k nl_air_quality`.
- [x] 7.5 `falchi-night-sky-atlas`, `implemented-unverified`, restricted terms
  CC BY-NC 4.0 recorded, `redistribution: false`.
  Verify: `python3 -m unittest discover -s registry/tests -v -k falchi`.
- [x] 7.6 `viirs-dnb-night-lights`, `credential-required`, Earthdata
  credential, fails closed.
  Verify: `python3 registry/audit.py`.
- [x] 7.7 `7timer`, `link-only`; `meteosource`, `noaa-rap`, `noaa-nam`,
  `globe-at-night`, `netatmo`, `weather-underground`, `catalogued` with their
  reasons.
  Verify: `python3 registry/audit.py`.
- [x] 7.8 `ccg-harbour-cameras`, `city-st-johns-road-cameras`, `ntv-cameras`,
  `partnership-only`, no endpoints, permission requests recorded.
  Verify: `python3 -m unittest discover -s registry/tests -v -k partnership`.

## 8. Field-level admissions on existing records (Registry owner)

- [ ] 8.1 Add the ECCC seeing index and sky-transparency index to `eccc-rdps`
  as class-index fields with their family comparability note (unlabelled
  integer classes, a fourth incompatible transparency encoding).
  Verify: `python3 -m unittest discover -s registry/tests -v -k seeing`.
- [ ] 8.2 Record on `eccc-marine-buoys-synop` that no ECCC buoy in the box
  carries dew point or visibility and no ship reports were observed, and on
  `smartatlantic-other-validated` that state is per buoy: in-box
  `implemented-unverified`, out-of-box `catalogued`.
  Verify: `python3 registry/audit.py`.
- [ ] 8.3 Record the `dwd-icon-global` two-path declaration: retrieved
  nearest-cell point samples on the published CLAT/CLON mesh, derived-here
  regridded rasters through the registered CDO-weights method.
  Verify: `python3 -m unittest discover -s registry/tests -v -k icon`.

## 9. API ceiling and schedulability (API owner)

- [x] 9.1 Extend the ceiling table to the ten states, map `operational` and
  every unknown state to `unavailable`, and keep `active` unemittable.
  Verify: `python3 -m unittest discover -s registry/tests -v -k ceiling`.
- [x] 9.2 Refuse `POST /refresh` for every non-schedulable state and for any
  record with an outstanding admission condition, naming the ids and their
  states; emit no access endpoint for `link-only` or `partnership-only`
  records.
  Verify: `python3 -m unittest discover -s registry/tests -v -k schedulable`.

## 10. Gate (Gate owner)

- [ ] 10.1 Run the full gate from `experiments/st-johns-weather-map/` and fix
  until all three pass with no error:
  `make test`,
  `openspec validate source-admissions-ledger --strict`,
  `uv run --project ../../tools/specs python ../../tools/specs/specctl.py validate`.
