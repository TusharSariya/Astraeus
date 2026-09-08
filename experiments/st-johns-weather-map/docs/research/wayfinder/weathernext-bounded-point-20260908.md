# WeatherNext bounded historical native point

Classification: experiment. Spec-Refs: GOV-SPEC-001, GOV-SPEC-004,
GOV-SPEC-006. No shared schema, route, registration, cache or serving gate changes.

At 2026-09-08 00:07 UTC the owner-authorized existing `astraeus` gcloud profile
successfully supplied runtime authentication for one historical native point.
The selected field was explicitly `experimental_tp_1hr_p10`, not cloud. Retained
cloud chunks were above the 16 MiB permission, while the precipitation candidate
fit the bound. The conservative strictly older-than-48-hours valid-time gate was
preserved. No raw ensemble/member or requester billing was used; ADC was untouched.

The actual Linux Zarr decoder returned:

| Identity | Observed result |
|---|---|
| Initialization | 2026-08-01 00:00 UTC |
| Valid time | 2026-08-01 06:00 UTC |
| Field / statistic / unit | experimental_tp_1hr_p10 / p10 / m |
| Native grid / actual cell | 0p1 / 47.5, -52.70001220703125 |
| Value | 0.0 |
| Member / pressure level | absent / absent |
| Native lead6 chunk | experimental_tp_1hr_p10/c/5/0/0 |
| Science chunk generation | 1787784429751157 |
| Science chunk bytes | 1,804,738 |
| Science chunk SHA-256 | fb8d6b447c7d73ebd4b3f27635588875b68619a59b327b2206e2a259c92d85a6 |
| Payload response bytes | 2,002,693 |
| All successful HTTP response bytes | 2,003,960 |
| HTTP requests / worker operations | 11 / 12 |
| Elapsed acquisition and decode | 10.435 seconds |

The explicitly supplied root identity was generation 1787792319369404, ETag
CLyhg7HNv5YDEAE= and size182540. No listing was performed for this point. Every
read was generation-pinned and response generation/ETag/size checked. The native
lead_time coordinate selected index5 for lead6; the earlier retained all-field
plan's c/6 pathname was not reused as a time assumption. Values were decoded
from actual retrieved chunks, not retained normalized values. No null occurred
in this selected cell; null/fill behavior remains deterministic-fixture proof.

The complete receipt, all object identities and per-response hashes are outside
Git at `/private/tmp/astraeus-weathernext-access-proof/live-point-receipt.json`.
Science bytes were decoded ephemerally and are not retained for replay. No second
live acquisition occurred. This is a historical selected-field proof, not current
forecast coverage, cloud delivery, all-field evidence or production permission.

## Source-local bridge

`weathernext_gcs_bridge.py::read_historical_point` accepts one native field and
an explicit root ObjectIdentity. The parent brokers only validated statistics
object requests. The actual native decoder runs in a Linux worker with 2 GiB
address-space limit, 80 CPU seconds, 128 MiB declared decoded chunk ceiling,
256 KiB root cap, 16 MiB payload cap and 30 worker operations. The bridge caps
received HTTP metadata plus media together to16 MiB and HTTP operations to30.
The decoder has no credentials; on macOS it runs in the existing locked Docker
image with network disabled, 2 GiB memory and 2 CPUs. No image is installed.

A 90-second maximum deadline governs parent IPC and acquisition. Worker writes
use nonblocking pipes and deadline-aware selectors. Process groups are killed
on timeout; owned Docker containers have unique names and are explicitly removed
in finally. For actual GcloudProfileToken use, each HTTP operation runs in a
short-lived host helper subprocess under the remaining deadline. Timeout kills
that process group, including a running gcloud descendant. Runtime tokens stay
in the HTTP helper's memory. No token, credential file or provider error body is
returned through worker IPC. Successful response bodies use bounded base64 IPC.
Injected test transports remain caller-controlled and are not proof of real auth.

The successful live run preceded the final subprocess HTTP/blocked-pipe cleanup
hardening. The final hardened paths were verified offline; no repeat live request
was made to restate the same proof. The standalone lower-level GCS transport's
socket timeouts alone remain a soft per-read bound. The bridge supplies the hard
process deadline for runtime transport. Cleanup may take up to five additional
seconds after the acquisition deadline.

Root integration requires `eb24e20` transport and reviewed `551b0bd` native
longitude alias (local cherry-pick1245e44 is equivalent). Only new bridge, worker,
tests and this receipt belong to this slice. No default application activation
or generic manifest-query cache wiring was added.

Verification includes actual Linux worker decoding deterministic Zarr, historical
and root refusal, overbudget chunk refusal before GET, foreign child path refusal,
blocked1MiB worker pipe timeout, killed HTTP subprocess timeout and owned Docker
cleanup. The combined WeatherNext native/transport/query/adapter suites and
specctl validation were run before handoff.
