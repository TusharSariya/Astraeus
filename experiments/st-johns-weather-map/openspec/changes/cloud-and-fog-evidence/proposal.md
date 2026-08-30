## Why

The map cannot say anything about cloud or fog at St. John's, the two things a
reader on the Avalon most wants to know. Three gaps, each verified live on
2026-08-30:

1. HRDPS/RDPS total cloud (`TCDC_Sfc`, `TotalCloudCover_Sfc`) decodes as
   `paramId=0`, units `unknown`. The code comment blames ecCodes `< 2.42.0`; the
   real cause is that ECCC writes WMO 0/6/1 with `typeOfSecondFixedSurface=255`
   while the `tcc` concept requires 8, so the upgrade will not fix it.
2. AWC METAR/TAF `clouds[]` (cover + base in feet) is collapsed to one maximum
   percent and `wxString` is never read, so `fog_state` can only ever be
   `unknown`.
3. ECCC WEonG fog-visibility layers exist and render, but `parse_title_units`
   would read the `[experimental]` suffix as the unit and publish
   `units: "experimental"`.

Classification: Experiment, Spec-Impact: none. `docs/specv1` is untouched.

## What Changes

- **WP1 (model total cloud):** replace the Debian `libeccodes` with the
  `eccodeslib` wheel (ecCodes 2.48.0), run one polite live smoke of the HRDPS and
  RDPS total-cloud messages, record the GRIB keys verbatim, and rewrite the
  wrong comment with the verified cause. `total_cloud` is **not** added to any
  variable map unless the smoke shows declared units; a message whose concept
  does not match is withheld with the cause recorded. Stops at an owner gate.
- **WP2 (METAR/TAF cloud layers + fog):** publish each reported cloud layer as
  retrieved (`cloud_layer_{n}_cover_code` as a CF flag-coded int, `_cover` in
  percent, `_base` in metres with `ft` as original units, n = 1..6) and the
  present-weather group as `weather_fog_code` / `weather_fog_vicinity_code` /
  `weather_mist_code`. `/point` serves flag codes as their retrieved meaning
  (`"OVC"`, not `6`) and derives `fog_state` from those codes only, naming the
  derivation. The web point panel lists layers as reported, in provider order,
  never bucketed into low/middle/high, and shows fog with its own attribution.
- **WP3 (WEonG fog imagery):** strip and disclose the provider `[experimental]`
  flag rather than reading it as a unit; proxy the four HRDPS-WEonG / RDPS-WEonG
  fog-visibility layers as display evidence only, stamped `live_proxy`, not
  sampled by `/point` and never feeding `fog_state`.

What remains unverified: whether ecCodes 2.48.0 changes the TCDC outcome
(expected not to); whether a WEonG tile renders non-trivially at a foggy hour
(the 15Z probe returned a near-empty 390 B PNG, which is a reading, not proof of
rendering); GDPS total cloud, whose listing 404'd today.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `grib-decoding`: a message whose parameter concept does not match is withheld
  and the cause recorded, never published under a guessed name.
- `artifact-ingestion`: METAR/TAF cloud layers and present-weather groups are
  published as retrieved; unknown vocabulary is a decode error; more than six
  layers is reported, not dropped; a null `wxString` is retrieved absence.
- `point-evidence-sampling`: flag-coded categoricals are served as their
  retrieved meaning; `fog_state` is derived only from retrieved codes and says
  which; with no provider diagnostic it cannot yield `not_indicated`.
- `web-evidence-interface`: cloud layers are listed as reported, never bucketed;
  fog carries its own attribution.
- `geomet-wms-access`: a provider experimental flag is disclosed, not read as a
  unit; WEonG diagnostics are proxied as display evidence only.

## Impact

Ownership is disjoint so the three work packages can run in parallel:

- WP1: `worker/Dockerfile`, `api/pyproject.toml`, `api/uv.lock`,
  `ingest/adapters/eccc_datamart.py`, `api/tests/test_adapter_eccc_datamart.py`,
  `docs/live-stack-report.md`.
- WP2: `ingest/adapters/awc.py`, `api/weather_api/store.py`,
  `api/tests/test_adapter_awc.py`, new
  `api/tests/test_point_cloud_layers_and_fog.py`,
  `web/src/{api.ts,App.tsx,types.ts,fixtures.ts,App.test.tsx,api.test.ts}`.
- WP3: `api/weather_api/wms.py`, `api/weather_api/app.py`,
  `ingest/adapters/eccc_geomet.py` (parser only), `api/tests/test_wms_proxy.py`,
  `api/tests/test_adapter_eccc_geomet.py`, `docs/geomet-layers.md`.

Nobody touches `registry/source_data.py`, `ingest/meteorology.py`,
`api/weather_api/models.py`, `api/weather_api/fixtures.py`, `compose.yaml`,
`web/src/MapPanel.tsx`. `UNAVAILABLE_POINT_FIELDS` is unchanged, so the twelve
unavailable point fields stay as specified.

Risk: adapter versions bump to `awc-metar-v2` / `awc-taf-v2`; proxied layer
count goes from 9 to 13 against a per-request budget of 16 upstream calls, which
fits a cold cache but leaves little headroom. Five decisions are held for the
owner and listed as gates in `tasks.md`.
