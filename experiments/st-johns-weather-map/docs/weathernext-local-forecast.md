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
