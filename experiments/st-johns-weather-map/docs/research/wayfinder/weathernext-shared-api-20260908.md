# WeatherNext historical shared API completion

Classification: experiment. Spec-Refs: GOV-SPEC-001, GOV-SPEC-004,
GOV-SPEC-006; api-first-source-delivery native identity/configuration contracts.
The conservative valid-time age strictly greater than48hours remains unchanged.

The shared selector `WeatherNext 3 historical` uses the reviewed historical
adapter: source google-weathernext-3-statistics, product
weathernext_3_0_0_statistics, native temperature_2m_mean K converted to canonical
temperature_2m degC. Provider ensemble_mean, unknown QC, masks, exact run/time/cell,
2m level and native_variable survive. Evidence stays nonprimary/nonconsensus and
operational false. Series and other WeatherNext fields remain unsupported.

The point API requires explicit offset-aware valid_time and validates exact
hourly lead against the configured run before acquisition. Only this historical
selector bypasses the generic current forecast window. Members/nonmean statistics,
quantiles and thresholds are refused. No AQHI, METAR, other model, substituted
run or neighbouring hour is requested. The catalogue advertises the software
without reading provider data. Registry state stays catalogued: implemented-
unverified requires ingestion registration, which remains excluded. Credential-
required would force a fictitious WEATHER_SECRET_* API key. Runtime Google auth
is accurately declared without inventing one or weakening the registry schema.

## Explicit runtime configuration

WEATHER_WEATHERNEXT_HISTORICAL_CONFIG names a nonsecret JSON file bounded to16KiB.
Exactly three keys are accepted: initialization (aware ISO timestamp),
gcloud_profile (existing profile name) and root_identity (bucket, name,
generation, etag, size). A concrete known proof configuration is:

```json
{"initialization":"2026-08-01T00:00:00+00:00","gcloud_profile":"astraeus","root_identity":{"bucket":"weathernext3_statistics_spatial","name":"weathernext_3_0_0_statistics/zarr/2026_to_present/20260801_00hr_01_preds/predictions.zarr/zarr.json","generation":"1787792319369404","etag":"CLyhg7HNv5YDEAE=","size":182540}}
```

No tokens, credential files, account identifiers or ADC are inspected by this
loader. Missing, unreadable, oversized or invalid JSON yields missing_configuration
with fixed safe wording. Configured JSON without gcloud yields product_unavailable;
non-Linux execution without Docker yields missing_compute. Readiness establishes
local prerequisites only. The service cache is keyed by validated immutable config.
Actual401/403 codes survive the HTTP child, bridge, delivery and retry cooldown;
the shared monitor reports access_denied without provider text or token disclosure.
The decoder uses `docker --pull never`; it cannot implicitly download an image.

**Docker boundary:** the current UI5173/API8000 deployment is not configured by
host gcloud access. No credential is copied into the repository, compose, logs or
container by this change. With absent nonsecret JSON, container status remains
missing_configuration; adding JSON alone cannot supply absent gcloud/identity.
The existing worker bridge is local IPC, not a host-network credential broker.
A container deployment needs a separately provisioned Linux gcloud runtime and
approved runtime identity through the existing secure workflow. No automatic
login, credential mount/copy, SDK installation, host proxy or ADC mutation occurs.
The approved host runtime can separately run the API with its existing profile
and config; that is not a claim about the currently running8000 container.

## Evidence and precise #140 residuals

`/private/tmp/astraeus-weathernext-shared-api-proof/` contains actual FastAPI
TestClient point.json, catalogue.json, status.json and receipt.json. Deterministic
native fixtures traversed shared dispatch and the source cache: two HTTP calls,
one fixture acquisition, identical fields. No provider or auth call occurred.
Frontend received these exact artifacts for historical selector/time verification.

The preceding authenticated host native point remains recorded separately in
`/private/tmp/astraeus-weathernext-access-proof/live-temperature-delivery.json`:
Aug1 00Z run/06Z valid,12.185510253906273degC at47.5/-52.70001220703125,
11HTTP requests/19,691,271bytes and identical receipt on the cache repeat. It was
not reacquired for API wiring and is not a live HTTP8000 proof.

Residuals: configure/authenticate the actual serving runtime and prove its live
HTTP path; broader historical fields/run inventory and cloud coverage; current or
future serving terms; native Series; full-source latency/scientific validation
and production admission. These are not represented as a missing API key.

Verification:249 registry/shared tests passed with whole-repository Linux mount;
125 focused native/shared/status regressions passed after denied-status changes.
Tests assert no AQHI or unrelated-source calls, strict historical/run/statistic
refusal before acquisition, null/native provenance and cache replay, safe missing
configuration and redacted denial through worker IPC. Root regenerates assembled
catalogue fixtures centrally after serial source integration. Specctl is required
before handoff.
