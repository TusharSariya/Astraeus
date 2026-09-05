# Space-weather integration evidence

Captured 2026-09-05 for issue 89. This is experimental acquisition evidence;
every response remains `operational: false` and registry state remains a ceiling.
Raw provider responses and rebuilt artifacts were removed with their temporary
directories. The ten retained JSON receipts in
`space-weather-receipts/` identify each response and artifact by byte count and
SHA-256 and include the exact artifact revision returned through the real HTTP
API route. The route uses the production `LiveStore.read_series` decoder over
a test-only local backing store; the harness independently hashes each artifact
before readback and compares every served field/platform's latest value, unit
and instant with the HTTP response.

The bounded run received 5,213,784 bytes and built 356,713 bytes of temporary
zipped-Zarr artifacts. Each artifact was read through `LiveStore.read_series`
by `GET /api/experiments/weather/v0/space-weather/products`; all ten readbacks
returned HTTP 200, `data_mode: live`, and `operational: false` with matching
source, logical name, provider run and revision identity.

Structural decoding and required-field presence are reported separately from
upstream scientific quality. The capture requires every selected physical
field to contain at least one finite retrieved value; all ten passed that
structural gate. Because the adapters preserve but do not interpret native
provider quality flags, API provenance reports scientific quality `unknown`
with `upstream_quality_not_interpreted`, never `passed`.

| Source | Scope and product | Field disposition |
|---|---|---|
| `noaa-swpc-rtsw` | L1 magnetometer, `valid_time x spacecraft` | Retrieved `bx_gsm`, `by_gsm`, `bz_gsm`, `bt`, GSM angles, `active`, `manual_mode`, telemetry/data/overall flags. Catalogue maps Bz and Bt; remaining values preserve the native row and QC context. |
| `noaa-swpc-plasma` | L1 plasma, `valid_time x spacecraft` | Retrieved density, bulk speed, temperature, `active`, and all eight published quality flags. All three physical fields map to the catalogue. |
| `noaa-swpc-propagated-solar-wind` | Provider-propagated bow-shock series | Retrieved speed, velocity components, density, temperature, magnetic components and provider propagation instant. Catalogue maps speed, density, Bz and Bt; no lag is derived here. |
| `noaa-swpc-kp-1m` | Planetary one-minute Kp | Retrieved Kp, estimated Kp and the provider thirds code. Catalogue maps Kp; code remains native QC/context. |
| `noaa-swpc-alerts` | Issued product | Retrieved product id, message verbatim, message code, serial and NOAA scale text. Catalogue maps the issued alert text. No staleness inference is made from a quiet interval. |
| `noaa-swpc-scales` | Planetary current/forecast day offsets | Retrieved R/S/G scales, their published probabilities, each block's instant and observed/current/forecast kind. Catalogue maps the three scales. |
| `gfz-hp30` | Planetary half-hour index | Retrieved Hp30 over the requested 24-hour selection. Response licence is required to equal CC BY 4.0. The feed declares no per-value provisional/final flag, which remains absent. |
| `noaa-goes-magnetometer` | Geosynchronous, `valid_time x satellite` | Retrieved He, Hp, Hn, total and arcjet flag. Four physical fields map to the catalogue; arcjet remains native QC. |
| `noaa-goes-xray` | Geosynchronous, `valid_time x satellite` | Retrieved both named XRS channels, observed flux, correction and contamination flag. The two corrected flux channels map to the catalogue; unknown energy bands fail closed. |
| `noaa-swpc-kyoto-dst` | Planetary Kyoto WDC relay | Retrieved Dst is declared `reprocessed`, names NOAA SWPC as intermediary, and is never display primary or a derivation input. The feed exposes no final/provisional flag, which remains absent. |

Explicit exclusions remain unchanged: the STEREO-A and hourly Kp prediction
records stay `unavailable`; NRCan STJ stays `partnership-only`; the Canadian
regional forecast stays link/citation-only; imagery and the existing SWPC Kp
and OVATION adapters are outside this change. GFZ Kp/Hp60 are catalogued
follow-ups rather than substitutes for the selected Hp30 acquisition.

Verification commands and outcomes:

```text
cd experiments/st-johns-weather-map/api
uv sync
uv run pytest tests/test_adapter_swpc_products.py tests/test_space_weather_series.py tests/test_space_weather_products.py tests/test_space_weather.py tests/test_adapter_swpc.py tests/test_adapter_gfz.py -q
# 70 passed, 2 skipped

cd ..
PATH="$PWD/api/.venv/bin:$PATH" make test-registry
# 235 passed
```

The capture command was:

```text
PYTHONPATH=.. uv run python ../scripts/space_weather_capture.py noaa-swpc-rtsw noaa-swpc-plasma noaa-swpc-propagated-solar-wind noaa-swpc-kp-1m noaa-swpc-alerts noaa-swpc-scales gfz-hp30 noaa-goes-magnetometer noaa-goes-xray noaa-swpc-kyoto-dst
```

Classification: Experiment. This changes only the isolated weather-map
experiment and does not claim V1 conformance or production admission.
Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-005, GOV-SPEC-006.
