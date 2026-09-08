# Internal WeatherNext forecast experiment

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
