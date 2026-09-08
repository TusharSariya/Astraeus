# OSTIA shared point completion, September 8, 2026

Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-005, GOV-SPEC-006.
Experiment under `current-sst-analysis-inputs` and
`timestamp-demand-query-cache`, supporting #153. No production admission,
scheduler activation, fog inference or scientific field expansion.

The existing `OSTIAQueryService` now supplies the shared `OSTIA SST` point
selector through a source-specific descriptor/reader. SST, native uncertainty
and native surface mask are all returned; catalog reads do no acquisition.
The reader offers only the exact latest published daily analysis, with no
selectable forecast run or Series. The route retains the existing five UTC
calendar date SST envelope, which accommodates real provider latency; native
discovery still refuses neighboring timestamps. API coverage remains the
existing Avalon core within the source's larger fixed native crop.

A live native-grid defect was corrected locally: OSTIA float32 latitude and
longitude rounding exceeds the raster helper's relative uniformity tolerance.
The source sampler now validates spacing within native float32 quantization,
then chooses one original published centre inside half-cell edge bounds. It
neither rewrites coordinates nor interpolates SST. A changed spacing beyond
that precision still fails closed. The regression uses 110 native-style
0.05-degree float32 coordinates rather than only a two-cell toy axis.

## Evidence and exact verification

Seven bounded anonymous requests acquired the September 6 00:00 UTC analysis:
metadata, time, latitude, longitude and one intersecting chunk for each required
field, totaling 1,466,909 bytes. Original UTC completion receipts and raw bytes
were retained outside Git. The initial public read exposed the float32
sampling refusal. After correction, network-disabled replay of those same
bytes ran through the real Linux bounded leaf and actual FastAPI TestClient.
The replay retained captured completion times and used a fixed monotonic clock;
it is not a second live capture or an assertion that expired cache is current.

`/point?product=OSTIA SST&latitude=47.5&longitude=-52.0&valid_time=2026-09-06T00:00:00Z`
returned HTTP 200, SST **14.529998779296875 degC**, error
**0.47999998927116394 degC**, native mask **1**, and revision
`ostia-20260906-1c63dd7f81dad443`. The response preserved original kelvin units,
actual daily analysis time, null forecast run, original retrieval UTC,
non-primary status and `operational=false`. Repeat point/cache reads made zero
additional provider requests. The compact
[receipt](ostia-shared-point-receipt-20260908.json) contains exact URLs, bytes,
digests and the full HTTP response. Raw payloads and runnable proof are under
`/private/tmp/astraeus-ostia-shared-live-proof/`.

```sh
docker run --rm --network none --memory 3g \
  -v /private/tmp/astraeus-api-first-sst-delivery/experiments/st-johns-weather-map:/work:ro \
  -e PYTHONPATH=/work/api:/work -w /work astraeus-lightning-proof:c88ff83 \
  python -m pytest api/tests/test_ostia_delivery.py api/tests/test_ostia_query.py api/tests/test_adapter_sst_analysis.py -q -p no:cacheprovider
uv run --project tools/specs python tools/specs/specctl.py validate
```

The 31 offline Linux tests cover native units/date/revision, water+sea-ice and
land masks, native fill nulls, no-primary/no-run/no-Series behavior, 36/96-hour
analysis latency, source-window refusal before I/O, cache reuse, coalescing,
failed-refresh expiry, killed-worker cleanup and float32-grid precision.

#153 source/backend delivery is complete once this commit is integrated with
the already completed OISST path. Root owns final browser consumption proof,
assembled checks and issue closure. Broader SST/ice products and fog science
remain outside #153; no admission claim follows from successful HTTP readback.
