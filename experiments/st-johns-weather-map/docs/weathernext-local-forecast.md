# Internal WeatherNext forecast experiment

## Current surface delivery (2026-09-08)

The owner authorized all 126 surface statistics (21 native fields, each mean,
p10, p25, p50, p75 and p90) and hiding both WeatherNext 2 entries. The current
[experimental contract](../openspec/changes/weathernext3-surface-point/specs/source-delivery/spec.md)
replaces the earlier temperature-only restriction described in the historical
implementation notes below. Each selection fetches just one native array,
retaining the existing 64 MiB receive, 128 MiB decoded-chunk and 90-second worker
bounds, native units, null masks, grid and immutable object provenance.

The opt-in compose runtime enables `WEATHER_WEATHERNEXT_AUTO_RUNS=1`. It reuses
the configured `astraeus` identity and checks at most four main-cycle roots,
under a 15-second/64 KiB metadata budget; successful metadata pins the exact
run generation before any science download. The next hourly valid time at or
after the timeline selection is verified against native coordinates. There is
no interpolation, raw-member access, requester-pays billing project, scheduled
ingestion or primary-source admission. Disabling that environment variable
restores explicit pinned-run selection. Legacy exact-time temperature calls
remain compatible.

History currently uses declared `2026_to_present` archive paths. Missing runs,
2024/2025 backfill, out-of-horizon selections and oversized fields remain
unavailable. The historical reader retains its conservative older-than-48-hour
boundary; the internal local path can serve recent past and future times under
its separately authorized internal-use scope. Historical forecasts are model
predictions, not observations. Live access requires the short-lived runtime
token, which `make up` refreshes using the existing approved profile.

Provider statistics include surface and station-trained temperature/dew point,
10/100 m scalar winds and components, pressure, total/low/mid/high clouds,
three distinct hourly precipitation heads, two solar-energy components and sea
surface temperature. Cloud overlap assumptions and relative humidity are not
inferred. Solar values remain one-hour energy (J/m2), precipitation remains
one-hour accumulation (mm), and land SST masks stay null.

The separate live checks returned a future cloud mean and a historical
precipitation p90 through the real default Linux worker. This is not a claim
that all 126 fields have been reacquired live in this change; all 126 mappings
are tested with constructed receipts and earlier all-field acquisition evidence
remains linked in the original experimental design.

## Earlier temperature-only implementation notes

Classification: experiment. Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-006.

The owner authorized the existing `astraeus` gcloud profile for the local
experimental map. The WeatherNext experimental delta requires exact native
identity and production isolation; it does not impose a 48-hour temporal rule.
The historical reader's conservative guard remains the default. No accepted
specification status or production registration changes in this slice.

The [official terms, modified September 3, 2026](https://storage.googleapis.com/weathernext-public/terms-of-use.pdf)
section 2(a) permits internal purposes. This isolated internal experiment does
not authorize public redistribution. The [official GCS guide](https://developers.google.com/weathernext/guides/gcs)
documents hourly statistics and 360-hour forecasts for main six-hour cycles.

Call `weathernext_gcs_bridge.read_local_experimental_point(selection,
root_identity=identity, now=actual_aware_clock, transport=transport,
max_received_bytes=64*1024**2)` explicitly. The worker receives
`internal_experimental_forecast`; native decoding still validates the exact
run, hourly lead, units, statistic, coordinates and nulls. Initialization must
already have occurred. The historical entry point retains its strict age gate.
Both paths retain pinned object generations, bounded bytes/operations/deadline,
no raw members, no billing project, no ADC mutation, and network-free decoding.

Deterministic native and Linux child tests cover future valid times and reject
unknown scope, naive clocks and future initialization before object access.
Historical, transport and delivery regression tests remain in the focused suite.
Live proof artifacts stay outside Git; current forecast values are not published.
Host profile availability does not configure the Docker API container.

## Shared local delivery and runtime authentication

`WeatherNext 3 local` is an explicit point selector alongside the unchanged
historical selector. Both retain the same native producer/product/field identity;
clients enumerate distinct declared point paths instead of choosing one implicitly.
Only the provider temperature mean is mapped. The requested time must be an exact
native hourly lead inside the configured run and the application's current time
window. No latest-run selection, native Series, other fields, primary admission,
or automatic run rollover is claimed.

`WEATHER_WEATHERNEXT_LOCAL_CONFIG` names bounded nonsecret JSON containing
`initialization`, `root_identity` and `gcloud_profile`, with the same generation-
pinned shape as the historical configuration. `WEATHER_WEATHERNEXT_ACCESS_TOKEN_FILE`
optionally supplies a short-lived OAuth token from the already approved identity.
It must be a private regular file owned by the API user, at most 16 KiB. The file
is reread by each bounded HTTP worker, and missing/invalid credentials fail closed
without falling back to another identity. Without this explicit file setting,
the existing named gcloud profile transport remains unchanged.

For the local Linux container, configure the token file as
`/tmp/weathernext-auth/access-token` on its existing tmpfs. Then run from the
experiment directory:

```sh
python scripts/refresh_weathernext_runtime_token.py --profile astraeus
```

This captures only the chosen profile's access token and sends it through stdin
to an atomic private runtime file. It does not mount the shared Google credential
database, alter ADC, log in, or put tokens in arguments, logs, browser responses,
or Git. Expiry and container recreation require running the command again;
automatic token renewal is not implemented. Pinned run configuration also needs
an explicit update as that run stops covering the intended forecast window.

The assembled actual shared API proof returned 16.148217773437523 degC from
289.2982177734375 K for September 8 12Z, initialized September 7 18Z, at native
47.5 N / -52.70001220703125 E. It took 32.83 seconds; the repeated API call used
the cache with zero additional acquisition. The browser replay preserved exact
Focus, source/run/valid time, mean statistic and full provenance. Live captures
remain outside Git under `/private/tmp/astraeus-weathernext-current-api-proof`
and `/private/tmp/astraeus-weathernext-current-browser-proof`.

The actual running Linux API on port8000 was configured with the private token
file and returned the same future forecast in63.17seconds; its repeat took8ms
with identical evidence. Exact runtime receipt:
`/private/tmp/astraeus-weathernext-current-api-proof/docker-receipt.json`.
The session compose override is `/private/tmp/astraeus-weathernext-runtime.yaml`
and the nonsecret pinned-run JSON is
`/private/tmp/astraeus-weathernext-current-api-proof/local.json`. Preserve this
override when recreating the local API, then refresh its tmpfs token. The normal
API launch command is restored; diagnostic faulthandler overrides are removed.

Final verification:119 API tests passed with2platform-dependent skips;
554 frontend tests passed; production build, generated contract drift checks,
specctl and independent code/security review passed.

The actual localhost:5173 desktop Bench also returned `Live API` and one field
for the future selection. Opening Point evidence ledger displayed `16.1 degC`,
source `google-weathernext-3-statistics`, valid September8 12Z, run September7 18Z.
This explicit evidence remains nonprimary; it does not become the default map
summary or consensus temperature. Source catalogue copy now says WeatherNext3
statistics, with distinct local/historical selectors. The label change passed
all237 registry tests; regenerated frontend fixture consumption passed separately.
