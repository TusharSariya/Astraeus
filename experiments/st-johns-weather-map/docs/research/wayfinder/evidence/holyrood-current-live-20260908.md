# CASHR current original-image delivery proof

Experiment only; Spec-Refs: GOV-SPEC-001, GOV-SPEC-002, GOV-SPEC-004,
GOV-SPEC-005, GOV-SPEC-006. No scientific or operational status transition.

At 2026-09-08 00:04:19 UTC, one bounded default acquisition fetched the exact
native CASHR Rain/Snow DPQPE GIF pair valid at **2026-09-08 00:00 UTC**. The
actual bounded Linux structural worker validated both 580x480 images. The
mounted integrated API metadata and exact revision GIF routes returned the
same bytes; an ordinary cache read and all API reads made zero extra requests.
Original producer legend/map rendering survives unchanged. Scientific freshness
and source QC remain unknown; primary and operational remain false. This is
not a numerical pixel, georeferencing, blank-image, or no-precipitation proof.

| Response | Bytes | SHA-256 |
| --- | ---: | --- |
| Directory listing | 1,384 | ca8f88fe52caeeedd0763dd47cc2043e4080093cf9af03b6ff24a704ed4d4db3 |
| Rain GIF | 14,718 | 77ea272926523679049a0f6433da59a52ee7999ddac3391a1a721c34d20b27d1 |
| Snow GIF | 16,812 | 3cddd7b971805059da82e9c42752dcc3c879216e131744fa8e45bfb723779e45 |

Three anonymous provider GETs, 32,914 response body bytes, 0.655 seconds for
acquisition plus cache/API proof. No provider retry during this successful run.
Raw payloads, original receipt headers/completions, metadata and harness stay
outside Git at `/private/tmp/astraeus-holyrood-current-live-proof/`:
`corrected-receipt.json`, `metadata.json`, `Rain.gif`, `Snow.gif`, the original
native filenames, `listing.html`, and `prove.py`.

## Listing capacity diagnosis and evidence limit

Two earlier bounded listing attempts before midnight failed at the original
131,072-byte ceiling. The instrumented second failure at 23:56:32 UTC recorded
`HolyroodUnavailable: CASHR response exceeds byte ceiling`; this was a local
capacity refusal, not DNS, TLS, sandbox, or decoder failure. No successful
provider payload was retained from those attempts. Root authorized the finite
listing ceiling correction to 524,288 bytes; per-GIF ceiling remains 524,288.
Commit `c678c8e` implements that correction and adds acceptance of a valid
listing larger than the old limit plus refusal above the new limit.

The successful proof crossed UTC rollover: the new day's listing was only
1,384 bytes. Therefore it proves current acquisition/delivery using the fixed
code, **not** live receipt of a >128KiB directory. The typed prior refusal and
synthetic boundary regressions provide the larger-directory evidence.

## Reproduction environment and checks

The proof used locked Linux image `astraeus-lightning-proof:c88ff83`, memory
1GiB, current root integration experiment mounted read-only at `/work`, and a
read-only overlay of the committed `holyrood_radar.py` capacity correction.
`PYTHONPATH=/work/api:/work`, `WEATHER_DATA_MODE=live`; no credentials.
The test dependency override reused the very same default-acquired service
for mounted API reads, without fake payloads or provider reacquisition.

Focused verification after the source fix:

```sh
docker run --rm --network none --memory 1g \
  -v /private/tmp/astraeus-api-first-holyrood-delivery/experiments/st-johns-weather-map:/work:ro \
  -w /work -e PYTHONPATH=/work/api:/work \
  astraeus-lightning-proof:c88ff83 python -m pytest -q -p no:cacheprovider \
  api/tests/test_holyrood_api.py api/tests/test_holyrood_presentation.py \
  api/tests/test_holyrood_query.py api/tests/test_experimental_holyrood_radar.py
uv run --project tools/specs python tools/specs/specctl.py validate
```

Result: 33 tests passed; specctl 0 errors, 0 warnings. Frontend listing receipt
guard is separately owned by the frontend worker and must use the same 512KiB
listing ceiling. Existing dated evidence documents retain the historical
128KiB limit as history; this entry records its explicit replacement.
