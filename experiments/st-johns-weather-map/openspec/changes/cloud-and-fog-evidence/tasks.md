Ownership is disjoint by work package; do not edit another package's files.
Nobody edits `registry/source_data.py`, `ingest/meteorology.py`,
`api/weather_api/models.py`, `api/weather_api/fixtures.py`, `compose.yaml` or
`web/src/MapPanel.tsx`. Files under `openspec/` belong to the spec agent only.

## 1. WP1: model total cloud (ecCodes upgrade, live smoke, documented finding)

Owned: `worker/Dockerfile`, `api/pyproject.toml`, `api/uv.lock`,
`ingest/adapters/eccc_datamart.py`, `api/tests/test_adapter_eccc_datamart.py`,
`docs/live-stack-report.md`.

- [ ] 1.1 `api/pyproject.toml`: add `[project.optional-dependencies] grib =
      ["eccodeslib==2.48.0.26"]`, keeping the cfgrib pin. Run `cd api && uv lock`
      and confirm the lock gains `eccodeslib` and `eckitlib` with
      cp313-manylinux_2_28 wheels. Verify: `cd api && uv lock && uv run pytest -q`
- [ ] 1.2 `worker/Dockerfile`: `uv sync --frozen --no-dev --no-install-project
      --extra grib`; delete the apt `libeccodes-dev` block with a comment that the
      library comes from the `eccodeslib` wheel via `findlibs`. Do not set
      `ECCODES_PYTHON_USE_FINDLIBS`. Verify: `docker compose build worker`
- [ ] 1.3 Confirm the load path: `docker compose run --rm --no-deps --entrypoint
      python worker -c "import eccodes, findlibs; print(eccodes.__version__,
      eccodes.codes_get_api_version(), findlibs.find('eccodes'),
      eccodes.codes_definition_path())"` prints 2.48.0 with no UserWarning. If
      the definitions path is empty, set `ECCODES_DEFINITION_PATH` in the
      Dockerfile and report either way.
- [ ] 1.4 Live smoke: one polite download (`ingest.http.PoliteClient`, 10 MB cap)
      of today's HRDPS `TCDC_Sfc` PT006H file; print `centre, tablesVersion,
      localTablesVersion, discipline, parameterCategory, parameterNumber,
      productDefinitionTemplateNumber, typeOfFirstFixedSurface,
      typeOfSecondFixedSurface, paramId, shortName, name, units, cfVarName`,
      then open with cfgrib (`indexpath: ''`) and print data_vars and units.
      Repeat once for RDPS `TotalCloudCover_Sfc`. Probe the GDPS listing first
      and skip if no cycle is populated. Record verbatim.
- [ ] 1.5 Expected branch (units `unknown`): leave the variable maps untouched;
      rewrite the comment at `eccc_datamart.py:59-71` with the verified cause
      (WMO 0/6/1, `typeOfSecondFixedSurface=255` vs concept 8, no CWAO local
      concept, withheld pending owner decision); delete the ">= 2.42.0" sentence.
      Unexpected branch (units declared): add `"total_cloud": ("TCDC","Sfc")` to
      `HRDPS_VARS` and `("TotalCloudCover","Sfc")` to `RDPS_VARS`, confirm
      `normalize_units` maps `%` to `percent`, run one worker cycle and read back
      `/point`. Verify: `docker compose exec worker python /app/worker/runtime.py
      --once --source eccc-hrdps` then `curl -fsS
      'http://localhost:8000/api/experiments/weather/v0/point?latitude=47.5615&longitude=-52.7126'
      | jq '[.fields[] | select(.provenance.source_id=="eccc-hrdps") | .field]'`
- [ ] 1.6 Tests in `api/tests/test_adapter_eccc_datamart.py`:
      `test_total_cloud_is_not_declared_until_the_decoder_states_its_units`
      (`total_cloud` absent from all three maps; a mocked decode returning
      variable `unknown` with units `unknown`, declared as `total_cloud`, fails
      `validate_run` with `bad_units:total_cloud:unknown`); the existing mocked
      fetch test asserts a complete, QC-passed run with the six fields only; an
      optional `@pytest.mark.live_smoke` asserting `parameterCategory == 6` and
      `parameterNumber == 1` and printing units, never asserting a unit outcome.
      Verify: `cd api && uv run pytest -q tests/test_adapter_eccc_datamart.py`
- [ ] 1.7 `docs/live-stack-report.md`: replace the 2.28.0 note; add a dated "TCDC
      finding" subsection with the GRIB keys, the concept text and the owner
      question.
- [ ] 1.8 Verify WP1 end to end:
      `cd api && uv lock && uv run pytest -q`;
      `docker compose build worker`;
      `docker compose run --rm --no-deps --entrypoint python worker -c "import eccodes; print(eccodes.codes_get_api_version())"`;
      `docker compose up -d --build worker && docker compose ps`;
      `docker compose exec worker python /app/worker/runtime.py --once --source eccc-hrdps`;
      the `/point` readback above; `make test`.

## 2. WP2: METAR/TAF cloud layers and fog codes to `/point` to the point panel

Owned: `ingest/adapters/awc.py`, `api/weather_api/store.py`,
`api/tests/test_adapter_awc.py`, new `api/tests/test_point_cloud_layers_and_fog.py`,
`web/src/api.ts`, `web/src/App.tsx`, `web/src/types.ts`, `web/src/fixtures.ts`,
`web/src/App.test.tsx`, `web/src/api.test.ts`.

- [ ] 2.1 `awc.py` present-weather parser: frozen dataclass `PresentWeather(fog,
      fog_vicinity, mist: bool; raw: str | None)`; `FOG_PHENOMENON = "FG"`,
      `MIST_PHENOMENON = "BR"`; `parse_present_weather(wx_string)`. Tokenise on
      whitespace; per token strip leading `+`/`-`, detect and strip leading `VC`,
      read the remainder as consecutive two-letter pairs. None/empty yields all
      False and raw None. Docstring cites WMO No. 306 FM 15 table 4678 and
      NAV CANADA MANOBS. Interpret nothing else.
      Verify: `cd api && uv run pytest -q tests/test_adapter_awc.py`
- [ ] 2.2 `awc.py` cloud-layer parser: `MAX_CLOUD_LAYERS = 6`,
      `CLOUD_COVER_FLAGS = {"SKC":0,"CLR":1,"NSC":2,"FEW":3,"SCT":4,"BKN":5,
      "OVC":6,"VV":7,"OVX":8,"CAVOK":9}`, `CLOUD_COVER_FLAG_MEANINGS`,
      `FEET_TO_METRES = 0.3048`, `parse_cloud_layers(clouds) ->
      (list[CloudLayer(code_flag, cover_pct | None, base_m | None)],
      decode_errors)`. Errors: `cloud_cover_code:<code>@<stamp>`,
      `cloud_layers_truncated:<n>@<stamp>`, `cloud_base:<value>@<stamp>`. A
      missing base stays NaN. `parse_cloud_cover_percent` and `total_cloud` are
      untouched. Verify: `cd api && uv run pytest -q tests/test_adapter_awc.py`
- [ ] 2.3 METAR dataset: `(n_times, 1, 1)` arrays `cloud_layer_{n}_cover_code`,
      `_cover`, `_base` for n = 1..6 plus `weather_fog_code`,
      `weather_fog_vicinity_code`, `weather_mist_code` (0/1). Attrs: cover_code
      `units: "code"`, `original_units: "code"`, `flag_values: [0..9]`,
      `flag_meanings`, `long_name: "METAR cloud layer N cover code as reported"`;
      cover `units: "percent"`, `original_units: "okta_fraction"`; base
      `units: "m"`, `original_units: "ft"`, `long_name: "cloud base above ground
      level"`; codes `units: "flag"`, `original_units: "present_weather_group"`,
      `flag_values: [0, 1]`, `flag_meanings: "absent present"`. Dataset attr
      `present_weather_strings` (raw or "" per step). `METAR_MANIFEST` optional
      fields `cloud_layer_1_cover_code` (code), `cloud_layer_1_base` (m),
      `weather_fog_code` (flag); slots 2-6 undeclared. Provenance
      `original_units` gains `cloud_layer_{n}_base: "ft"`.
      `adapter_version = "awc-metar-v2"`.
      Verify: `cd api && uv run pytest -q tests/test_adapter_awc.py`
- [ ] 2.4 TAF: the same per forecast period; `TAF_MANIFEST` gains the same
      optionals; `adapter_version = "awc-taf-v2"`. Do not change the duplicate
      TEMPO/BECMG stamps (open question).
      Verify: `cd api && uv run pytest -q tests/test_adapter_awc.py`
- [ ] 2.5 `store.py`: widen `Sample.value` to `float | str | None`. In
      `_sample_dataset`, when attrs carry `flag_values` / `flag_meanings` and the
      value is not None, map `int(value)` to its meaning; unmapped yields None.
      Extend `FIELD_BY_VARIABLE` with the 18 per-slot names (field == variable)
      and add `FOG_INPUTS = frozenset({"weather_fog_code",
      "weather_fog_vicinity_code", "weather_mist_code"})`, sampled but skipped
      alongside `DERIVATION_INPUTS` so they are never served raw. In the
      per-source loop derive `fog_state(provider_diagnostic=None, visibility_m=
      vis or None, fog_code=bool(fog) or bool(vicinity))`, basis
      `replace(fog, variable="fog_state", value=None, units="category")`,
      provenance `derivation=FOG_DERIVATION`, `derivation_version=
      FOG_DERIVATION_VERSION = "fog-state-present-weather-v1"`, both defined in
      `store.py`; the derivation text names FG/VCFG as fog evidence, BR as mist
      and not, and states that `not_indicated` cannot be produced. Import
      `fog_state` from `.science`. `UNAVAILABLE_POINT_FIELDS` unchanged, with a
      comment saying why.
      Verify: `cd api && uv run pytest -q tests/test_point_cloud_layers_and_fog.py tests/test_api.py`
- [ ] 2.6 New `api/tests/test_point_cloud_layers_and_fog.py` reusing `StubStore`,
      `artifact`, `rectilinear` from `test_live_sampling.py`: fog 1 yields
      `evidence_present` with derivation_version and units `category`; 0 yields
      `unknown`; NaN yields `unknown`; vicinity only yields `evidence_present`;
      raw `weather_*_code` never served; flag 6 serves `"OVC"`; out-of-table
      serves None; base provenance carries `original_units: ft`.
      Verify: `cd api && uv run pytest -q tests/test_point_cloud_layers_and_fog.py`
- [ ] 2.7 `api/tests/test_adapter_awc.py`: present-weather fog vs mist table;
      per-layer publication from `SAMPLE_METAR_JSON` (flag 6 OVC at 14Z, base
      800 * 0.3048, original_units ft, slot 2 absent, total_cloud unchanged);
      unknown vocabulary is a decode error; more than six layers is reported;
      fog/mist flags and `present_weather_strings`; TAF periods.
      Verify: `cd api && uv run pytest -q tests/test_adapter_awc.py`
- [ ] 2.8 Web `types.ts`: `CloudLayerReading { index; coverCode: string | null;
      coverPct: number | null; baseM: number | null }` and `cloudLayers:
      CloudLayerReading[]` on `EvidenceSnapshot`. `api.ts`: add the 18 per-slot
      names to `DISPLAYED_FIELDS`; `normalizePoint` keeps a slot when any of the
      three fields returned, accepts `baseM` only when the unit is `m` / metre(s),
      else null; `fieldSources.cloud_layer_1_cover_code` attribution.
      `fixtures.ts`: `cloudLayers: []` on both snapshots.
      Verify: `cd web && npm test -- --run && npx tsc -b --force`
- [ ] 2.9 `App.tsx`: `Metric label="Cloud layers"` reading `Unknown` or a join
      such as `BKN · 4267 m  |  OVC · base Unknown`, detail "As reported, in
      provider order (cover code · base AGL); not bucketed into strata",
      mode/source from `cloud_layer_1_cover_code`. Dedicated `Metric label="Fog"`
      with the three existing strings, mode/source from `fog_state`.
      `evidenceRows` gains `Cloud layers`. `Cloud L / M / H` left as is.
      Verify: `cd web && npm test -- --run && npm run build`
- [ ] 2.10 Web tests: renders `BKN · 4267 m`; Unknown when none; L/M/H stays
      Unknown; Fog metric with source tag; `normalizePoint` drops a non-metre
      base. Verify: `cd web && npm test -- --run`
- [ ] 2.11 Verify WP2 end to end:
      `cd api && uv run pytest -q tests/test_adapter_awc.py tests/test_point_cloud_layers_and_fog.py tests/test_api.py tests/test_wms_proxy.py`;
      `cd web && npm test -- --run && npx tsc -b --force && npm run build`;
      `docker compose up -d --build worker api && docker compose up -d --build --no-deps web`;
      `docker compose exec worker python /app/worker/runtime.py --once --source awc-metar-speci`;
      `docker compose exec worker python /app/worker/runtime.py --once --source awc-taf`;
      `curl -fsS 'http://localhost:8000/api/experiments/weather/v0/point?latitude=47.5615&longitude=-52.7126' | jq '.fields[] | select(.field|test("cloud_layer_|fog_state")) | {field, value, src: .provenance.source_id, u: .provenance.normalized_units, ou: .provenance.original_units, d: .provenance.derivation_version}'`;
      `make test`.

## 3. WP3: WEonG fog-visibility imagery proxies

Owned: `api/weather_api/wms.py`, `api/weather_api/app.py`,
`ingest/adapters/eccc_geomet.py` (parser only), `api/tests/test_wms_proxy.py`,
`api/tests/test_adapter_eccc_geomet.py`, `docs/geomet-layers.md`.

- [ ] 3.1 `eccc_geomet.py`: `_EXPERIMENTAL_FLAG = re.compile(r"\s*\[experimental\]\s*$",
      re.IGNORECASE)`, stripped in `parse_title_units` before `_TITLE_UNITS`;
      add `is_experimental(title) -> bool`. `Current-Alerts [experimental]` still
      yields `(None, None, False)`.
      Verify: `cd api && uv run pytest -q tests/test_adapter_eccc_geomet.py`
- [ ] 3.2 `wms.py`: extend `ForecastLayerSpec` with `product: str = "HRDPS"` and
      `semantics: str | None = None`. Add four specs
      `geomet-live-hrdps-weong-fog-liquid` / `-ice` and
      `geomet-live-rdps-weong-fog-liquid` / `-ice` over
      `HRDPS-WEonG_2.5km_{Liquid,Ice}FogVisibility` and
      `RDPS-WEonG_10km_{Liquid,Ice}FogVisibility`; fields
      `visibility_through_liquid_fog` / `visibility_through_ice_fog`; titles
      "HRDPS-WEonG visibility through liquid fog (live proxy)" and so on;
      products `HRDPS-WEonG` / `RDPS-WEonG`; `semantics = WEONG_FOG_SEMANTICS`,
      which extends `LIVE_PROXY_SEMANTICS` to state this is an ECCC WEonG
      post-processed fog diagnostic (visibility through fog, metres), not a raw
      model field, display evidence only, not sampled by `/point`, not feeding
      `fog_state`, that HRDPS-WEonG corresponds to `eccc-hrdps-weg-prognos` and
      that RDPS-WEonG has no registry record. Update the `FORECAST_LAYERS`
      docstring. Verify: `cd api && uv run pytest -q tests/test_wms_proxy.py`
- [ ] 3.3 `forecast_coverage`: `experimental: bool` on `ForecastCoverage` from
      `is_experimental(title)`; notice `"{layer_id}: ECCC marks {wms_layer}
      '[experimental]' in its capabilities title"`. The RDPS pair's units must be
      `m`. Verify: `cd api && uv run pytest -q tests/test_wms_proxy.py`
- [ ] 3.4 `app._proxied_forecast_layers`: `product=coverage.spec.product`,
      `semantics=coverage.spec.semantics or wms.LIVE_PROXY_SEMANTICS`, title
      prefixed `[experimental] ` when flagged. Note that 13 capability fetches fit
      the 16-call budget on a cold cache and how much headroom remains.
      Verify: `cd api && uv run pytest -q tests/test_wms_proxy.py tests/test_api.py`
- [ ] 3.5 Tests: `test_adapter_eccc_geomet.py` asserts
      `parse_title_units("RDPS-WEonG - Visibility through liquid fog [m] [experimental]") == ("m", "m", True)`,
      `Current-Alerts [experimental]` yields `(None, None, False)`, and
      `is_experimental`; the live smoke gains the four layers expecting canonical
      `m` and a 1 h period, and the render smoke one map image plus legend for
      HRDPS liquid. `test_wms_proxy.py` replaces the `HRDPS.CONTINENTAL_` prefix
      assertion with `upstream_wms_layer == wms.forecast_spec(id).wms_layer` plus a
      product check, and adds
      `test_weong_fog_proxies_are_declared_as_diagnostics_not_sampled_by_point`
      and `test_an_experimental_title_yields_metres_and_a_notice`.
      Verify: `cd api && uv run pytest -q tests/test_wms_proxy.py tests/test_adapter_eccc_geomet.py`
- [ ] 3.6 `docs/geomet-layers.md`: add a "WEonG fog visibility (live proxies)"
      table with names, titles, dimensions, bounds and probe results; move
      HRDPS-WEonG out of the rejected list.
- [ ] 3.7 Verify WP3 end to end:
      for each of the four WMS layers, `curl -sS -o /dev/null -w "$L GetMap %{http_code} %{content_type} %{size_download}B\n" "https://geo.weather.gc.ca/geomet/?service=WMS&version=1.3.0&request=GetMap&layers=$L&crs=EPSG:4326&bbox=46.5,-55.0,48.5,-51.0&width=400&height=200&format=image/png&transparent=true&time=$(date -u -v+18H +%Y-%m-%dT%H:00:00Z)"`
      and `curl -sS -o /dev/null -w "$L Legend %{http_code} %{content_type} %{size_download}B\n" "https://geo.weather.gc.ca/geomet/?service=WMS&version=1.3.0&request=GetLegendGraphic&layer=$L&format=image/png&sld_version=1.1.0"`;
      `cd api && uv run pytest -q tests/test_wms_proxy.py tests/test_adapter_eccc_geomet.py`;
      `cd api && WEATHER_LIVE_SMOKE=1 uv run pytest -m live_smoke -q tests/test_adapter_eccc_geomet.py`;
      `docker compose up -d --build api`;
      `curl -fsS http://localhost:8000/api/experiments/weather/v0/layers | jq '.layers[] | select(.id|startswith("geomet-live-")) | {id, product, units, group, n: (.times|length), legend_available}'` (13 rows; RDPS pair units `m`);
      `curl -sS -o /dev/null -w '%{http_code} %{content_type}\n' 'http://localhost:8000/api/experiments/weather/v0/layers/geomet-live-hrdps-weong-fog-liquid/legend'`;
      `make test`.

## 4. Stop-for-owner gates (owner decisions; agents do not tick these)

- [ ] 4.1 WP1: publish `total_cloud` from WMO 0/6/1 keys, or ship a local ecCodes
      definitions overlay for CWAO. Default: withheld, cause recorded.
- [ ] 4.2 WP2: any low/middle/high bucketing of reported layers. Default: none;
      WMO étage thresholds are noted in the proposal only.
- [ ] 4.3 WP2: `VCFG` counted as fog evidence. Default: yes; if rejected, drop
      `or vicinity` from the derivation and amend the derivation text.
- [ ] 4.4 WP2/WP3: use WEonG fog visibility as `provider_diagnostic` so
      `fog_state` can say `not_indicated`. Default: no.
- [ ] 4.5 WP3: show "[experimental]" products (default: shown, labelled), and
      create an `eccc-rdps-weg` registry record (owner-only; default: none).

## 5. Open questions (recorded, not resolved here)

- TAF TEMPO/BECMG periods duplicate `valid_time` stamps and
  `_nearest_time_index` picks arbitrarily.
- The WEonG default-TIME tile was 390 B near-empty; confirm a non-trivial render
  at a foggy hour before calling it "verified rendering".
- GDPS listing returned 404 for today's 00 cycle; no GDPS total cloud mapping
  until a listing shows the file.
