Owned: `ingest/derive/cloud_motion.py`, `ingest/adapters/eccc_datamart.py`,
`ingest/adapters/noaa_s3.py`, `ingest/registry.py`,
`api/weather_api/grids.py`, `api/tests/test_cloud_motion.py`,
`api/tests/test_flow_endpoint.py`, `api/tests/test_adapter_eccc_datamart.py`,
`api/tests/test_adapter_noaa_s3.py`, `web/src/MapPanel.tsx`,
`openspec/config.yaml` (carve-out).
Not touched: rendering (hard native cells stay, owner decision), the
timeline transport, the flow texture's geometry or scale headers.

## 1. Diagnosis

- [x] 1.1 Establish from the owner's recording and the live API why the
      display looks like a dissolve: zero measured displacement over 96
      weather-minutes; sharpness peaking at real frames; median served
      confidence 0 while warping beat persistence 34.7 vs 53.4 percent MAE;
      served tangents equal to the segment flow (median |v-F| = 0.00 px).
      Verify: measurements recorded in proposal.md

## 2. Make the motion apply

- [x] 2.1 Relative forward-backward consistency; confidence-weighted fill
      with a support field; display weight from the half-interval warp
      agreement gated by support, smoothed; per-pair persistence floor.
      Verify: `cd api && uv run pytest tests/test_cloud_motion.py -q`
- [x] 2.2 `/flow` serves the display weight in the blue channel, falling
      back to the stored consistency for artifacts that predate it; the
      semantics header says which.
      Verify: `cd api && uv run pytest tests/test_flow_endpoint.py -q`
- [x] 2.3 Disclosure names the dissolve-where-it-grew behaviour.
      Verify: `cd web && npm test -- --run src/MapPanel.test.tsx`

## 3. Validate with held-out frames

- [x] 3.1 Leave-one-out midpoint reconstruction against the real frame,
      scored against both a crossfade and a reversed-motion control; the
      control-based margin vetoes a variable's motion entirely.
      Verify: `cd api && uv run pytest tests/test_cloud_motion.py -q`

## 4. Steering winds (staged B2, bundled by owner request)

- [x] 4.1 Ingest 850/700/500 hPa u/v for HRDPS, RDPS (Datamart ISBL tokens)
      and GFS (idx exact pairs), declared optional so a missing level costs
      the prior and never the artifact.
      Verify: `cd api && uv run pytest tests/test_adapter_eccc_datamart.py tests/test_adapter_noaa_s3.py -q`
- [x] 4.2 Prior fills only unsupported cells, weighted by agreement with the
      trusted flow, refused where a supported flow reports stillness, and
      applied only where it improves the held-out score - both scores in
      provenance.
      Verify: `cd api && uv run pytest tests/test_cloud_motion.py -q`

## 5. Governance and verification

- [x] 5.1 Carve-out amended for the steering prior's four conditions.
      Verify: `openspec validate --all`
- [x] 5.2 Full suites and build.
      Verify: `cd api && uv run pytest -q; cd ../web && npm test -- --run && npm run build; cd .. && openspec validate --all && make test`
- [ ] 5.3 Docker rebuild; a cycle ingests the winds and re-derives under
      `cloud-motion-development-v3`; the served blue channel is no longer
      zero for the median pixel; served tangents differ from the segment
      flow; provenance carries the held-out scores with and without the
      prior; a fresh recording shows the field translating during playback
      and a flattened sharpness sawtooth at real frames.
      Verify: `docker compose up -d --build api web worker` then the checks above
      Status 2026-09-01: stack rebuilt; one cycle ingested the steering winds
      (HRDPS surface artifact now carries all six 850/700/500 hPa fields) and
      re-derived all three sources under `cloud-motion-development-v3`.
      Served, for the 23:00->00:00Z pair: HRDPS display weight median 0.443
      (was 0.000; 45% of cells above 0.5), RDPS 0.416, GFS mid-cloud 0.804
      with every cell above 0.5. The C1 tangents are live for the first time
      - median |v - F| of 0.54/0.80 px on HRDPS and 8.15/3.48 px on GFS,
      against 0.00 px before. Provenance held-out skill against the
      reversed-motion control: HRDPS +0.114, RDPS +0.087, GFS strata +0.342
      to +0.440. The steering prior was applied to HRDPS (+0.0045), RDPS
      (+0.0065), GFS low and total cloud (+0.0005 and +0.00003) and DECLINED
      for GFS mid and high cloud, where it scored worse - the machinery
      refusing its own feature, which is what it is for. `/point` carries no
      850/700/500 hPa field.
      Note on one acceptance criterion: gradient energy ("sharpness") is a
      bad proxy here and is dropped. A cross-dissolve of two frames offset by
      fifteen cells is a double image, and the doubled edges raise gradient
      energy rather than lowering it, so the dissolve can score "sharper"
      than the advected composite it is worse than. The held-out
      reconstruction error above is the measurement that means what it says.
      Remaining for the owner: whether it now reads as weather moving.
