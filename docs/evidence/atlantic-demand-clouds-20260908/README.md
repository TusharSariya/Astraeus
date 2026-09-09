# Atlantic demand-cloud implementation evidence

Classification: isolated experiment; no production status transition.
Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-006.
Owner authorization: supplied implementation plan, 2026-09-08 local date.
The working tree contained pre-existing WN3 grid/time changes; those were preserved
and extended. This receipt covers the working tree, not a claimed clean commit.

## Implementation

- GOES-19 observed cloud mask (`noaa-goes19-demand-cloud-mask`): actual archive
  scan discovery; one ACMF/paired ACHAF acquisition; existing nearest-neighbour
  regrid, parallax and five-state palette. Missing height remains uncorrected.
- RDPS total cloud · white opacity (`eccc-rdps-demand-total-cloud`): cloud-only
  Atlantic request through the existing coordinator, native rotated-cell sampling,
  white percentage alpha, violet-grey missing. Legacy point bounds unchanged.
- WN3 forecast/historical mean total cloud: app requests Atlantic; default API
  remains Avalon. Native 151 × 301 intersecting cells, indexed map geometry,
  selected-cell inspection, 2 MiB response/worker output, existing upstream limits.
- Metadata-only times feed the bottom rail, Tracks and navigation. GOES offers
  Latest available scan for gaps. These demand paths do not prefetch sequences.

## Fixed verification

From repository root:

```sh
uv run --project experiments/st-johns-weather-map/api pytest -q experiments/st-johns-weather-map/api/tests/test_demand_clouds.py experiments/st-johns-weather-map/api/tests/test_source_grid.py experiments/st-johns-weather-map/api/tests/test_source_times.py experiments/st-johns-weather-map/api/tests/test_rdps_query.py experiments/st-johns-weather-map/api/tests/test_satellite_layer.py experiments/st-johns-weather-map/api/tests/test_adapter_goes_abi.py
uv run --project experiments/st-johns-weather-map/api python experiments/st-johns-weather-map/scripts/generate_source_contract.py --check
uv run --project tools/specs python tools/specs/specctl.py validate
```

API: 78 passed, 5 platform/live skips; the added public Atlantic point-route regression also passed. Generated contract check passed.
Specctl: zero errors, zero warnings. `git diff --check` passed.

From experiment web directory:

```sh
npm test -- src/workbench/demandCloudTimes.test.ts src/workbench/sourceGrid.test.ts src/workbench/sourceTimes.test.ts src/workbench/MapEvidenceDetails.test.tsx src/api.test.ts src/App.test.tsx
npm run build
npm run check:source-types
```

214 frontend tests passed initially; the added lazy-cell inspector regression and 94 App tests passed on the final rerun (99 tests). Production build and generated types passed.
Vite retains the existing large-chunk advisory.

Linux dependency preparation used `astraeus-cloud-proof:20260908`, digest
`sha256:b757d6a49ff20646c78cd123585d58733507f46ce9e6975c424101bfe545f0bd`.
Current source was mounted read-only over the prepared environment:

```sh
docker run --rm --network none --memory 3g -e PYTHONPATH=/work:/work/api -v "$PWD:/work:ro" -w /work astraeus-cloud-proof:20260908 /app/api/.venv/bin/python -m pytest -q -p no:cacheprovider api/tests/test_demand_clouds.py api/tests/test_source_grid.py api/tests/test_rdps_query.py
```

49 passed on the final run, including actual default GOES and Avalon/Atlantic WN3 workers and the public Atlantic point-route regression.
Provider network was disabled; fixtures use synthetic NetCDF/Zarr and MockTransport.

Strict OpenSpec validation from the experiment directory:
`npx --yes @fission-ai/openspec validate --all --strict`: 91 passed, one unrelated
pre-existing failure in `swob-demand-query`. The requirements “SWOB native fields,
provenance and expiry remain bounded” and “SWOB default composition is cache-only
and evidence-only” lack Scenario sections. `atlantic-demand-clouds` passed.
This unrelated specification was not rewritten.

## Live evidence (distinct from fixtures)

Provider traffic occurred in these opt-in checks. GOES scan 2026-09-09 00:50:21 UTC
returned a 34,274-byte PNG. RDPS run 2026-09-08 18:00 UTC, valid 2026-09-09 02:00 UTC,
returned a 70,770-byte PNG. WN3 valid 2026-09-09 02:00 UTC returned 45,451 cells in
850,522 bytes. Hashes, bounded inventories and WN3 provenance are in
`live-receipts.json`. PNGs are renderer outputs, not source captures. Header wording
was subsequently corrected to disclose RDPS missingness consistently.

Browser inspection at http://127.0.0.1:5173 confirmed both optional layer names,
loading and gap states, the Latest available scan action moving selection to the
actual 00:50:21 scan, all three layers drawn after adding WN3, and observed/forecast time
markers. Normal viewport was 1728 × 874. The 200%-equivalent layout was checked at
864 × 437 CSS pixels: Layers and timeline controls remain usable. Browser shortcut
zoom was unavailable through the automation surface, so this is an effective
viewport check, not a claim of native browser zoom verification.

Final browser verification on the rebuilt app confirmed a WN3 point outside Avalon
(47.869° N, 47.920° W) returns 99.1% and a native rectangle click opens cell 24311
with its exact percentage and geometry while preserving the Focus URL. The public
WN3 point route now accepts Atlantic coordinates; other products retain their
existing point coverage. A regression checks boundary-cell agreement and reuse
without additional native reads.

## Viewing

Open http://127.0.0.1:5173, then Layers → Browse. Search the exact layer names above
and enable them. Open Tracks and select an advertised time; for GOES gaps use
Latest available scan. WN3: search “WN3 forecast · mean · total cloud cover” (or
historical) and select Map + data. Zoom out to see the Atlantic footprint.
The local API/web Compose services were rebuilt; default selection definitions
and scheduled ingestion were unchanged.

## Map-only UI correction

Owner feedback identified GOES being labelled Unknown in Browse and Point
unsupported in the point panel. This correction follows GOV-SPEC-001,
GOV-SPEC-004 and GOV-SPEC-006 and the amended map-only scenario above.
Raster layers with no declared point mapping now use Map/Off selection and do
not produce failed point readings or an Open point data action. Demand-layer
Browse status is Map on demand before selection and reflects actual loading,
drawn or unavailable receipts afterward; archive metadata is still not claimed
to be downloaded imagery.

142 affected frontend tests passed (PointDataPanel, discovery, pointSelections,
MapStack and App). Production build, strict validation of atlantic-demand-clouds,
`git diff --check` and specctl passed. The web service was rebuilt and restarted.
Browser verification of live GOES scan 2026-09-09 01:20:21 UTC showed 1 of 1
layers drawn, Drawn in both Active and Browse, and no GOES point-failure row.

## Compact scan timestamp selector

Owner feedback requested directly discoverable GOES timestamps. The compact
timeline now includes a labelled native scan selector and Latest GOES scan
button, preserving the exact selected time until a user chooses a scan. It uses
the existing metadata inventory and exposes loading/empty failures. No science
sequence is downloaded. Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-006.

102 affected frontend tests passed (ObservedScanTimes, demandCloudTimes,
sourceTimes and App); production build, strict atlantic-demand-clouds validation
and specctl passed. The web service was rebuilt and restarted. Browser inspection
with a future 22:00 UTC selection showed 35 actual scan options, and clicking
Latest GOES scan changed the URL selection to 2026-09-09T01:50:21.000Z.
