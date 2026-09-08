# NVIDIA FourCastNet NIM 1.0.0 native delivery

Classification: isolated experiment under GOV-SPEC-001/004/005/006. This implements
source-local transport software only and does not claim V1 conformance. The
[optional forecast-centre experiment](../../../openspec/changes/optional-north-atlantic-models/specs/optional-forecast-centres/spec.md)
requires explicit generated lineage, non-contributing status and no inferred
cloud evidence. The [inference handoff](inference-candidate-handoff.md) distinguishes
this deployment contract from FCN1, FCN3, Earth2Studio and hosted examples.
No shared API, registry, application route or scientific mapping was changed.

## Verified versioned boundary

NVIDIA's [1.0.0 quickstart](https://docs.nvidia.com/nim/earth-2/fourcastnet/1.0.0/quickstart-guide.html)
identifies the default SFNO profile and a complete FP32 input tensor with shape
`(1,1,73,721,1440)`. The response includes initialization and subsequent six-hour
states named by forecast lead and batch index. For a four-step request the
example returns five NumPy members, from `000_000.npy` through `024_000.npy`.
These facts were checked on 2026-09-07; version 1.0.0 is intentionally pinned,
not asserted to be the newest NIM release.

The [versioned OpenAPI](https://docs.nvidia.com/nim/earth-2/fourcastnet/1.0.0/_static/yaml/fourcastnet.openapi.yaml)
defines multipart `POST /v1/infer` with `input_array`, `input_time` and
`simulation_length`; the upstream step range is 1..120. It also defines seed
and variable selection. This client fixes seed zero, requests all native
variables and imposes a default four-step ceiling. The native NumPy request
endpoint is separate from NVIDIA's hosted service with historical example
indexes and is not an anonymous current forecast feed.

## Implemented seam

`api/weather_api/nvidia_fcn_delivery.py` exports `infer`, `Initialization`,
`Deployment`, `Limits`, `Delivery` and `DeliveryRefused`. Callers must supply:

- A deployed service origin, exact container/checkpoint SHA256, runtime and
  device, pinned NIM version and the local `SFNO ERA5 73ch` profile label.
- A complete native initializer file; source, run, UTC input timestamp,
  transformation identifiers and an ordered-channel contract SHA256.
- An unused destination archive path and an explicit simulation length.

The profile label scopes this client; it is not a claimed NIM profile hash.
Container, checkpoint and channel digests are caller attestations. This client
cannot prove which checkpoint a remote service actually loaded.

The initializer is snapshotted before upload, with exact shape, C-order FP32,
length and finite-value checks. It records the bytes' SHA256. HTTP redirects,
environment proxy configuration and transparent response compression are disabled.
The client does not retry, substitute an old run, deploy services, obtain initial
conditions, inspect credentials, download checkpoints or make an implicit call.
A supplied `httpx.MockTransport` exercises the complete request boundary offline.

Transfers are streamed to temporary disk under a byte budget. Fixed TAR headers
are checked before metadata bodies can be parsed: traversal, links, directories,
sparse/PAX/long-name headers, duplicate names, unexpected lead/batch indexes,
missing members, truncation and hidden trailing archives all refuse delivery.
NumPy header lengths are checked before NumPy can allocate their bodies.
No TAR member is extracted. Each member has a bounded C-order FP32 NumPy envelope
with native element cardinality; its actual shape, checksum, initialization,
lead and valid time are retained. A hard link publishes the complete archive
without overwriting an existing destination; failures remove temporary files.

Default disk allowance is one 303 MB initializer snapshot plus up to 1.6 GB of
response. The caller's original initializer is additional storage. The 180-second
wall deadline is checked between chunks and before upload; HTTP operations have
finite timeouts. This synchronous implementation cannot forcibly interrupt an
already-blocked operating-system read or a caller-supplied transport that ignores
timeouts. Limits are policy ceilings, not measured runtime predictions.

## Precisely remaining gates

The ordered 73-channel definitions, coordinate orientation, per-channel units,
initializer transformations and actual output axis arrangement have not been
verified against a pinned deployed native fixture. A caller-supplied digest
records that contract's identity; it does not certify its content. Therefore the
client preserves outputs as `native-channels-unmapped`. Output physical bounds,
finite/missing values and scientific QC are not evaluated or normalized. No
point forecast, direct cloud, visibility, ceiling, fog, centre vote, forecast
skill, CPU feasibility or current-run claim follows from a delivered archive.

A real caller-owned initializer and named deployed endpoint are still required
for execution proof. No live inference, paid request, credential read, model
payload download or deployment was performed. Reduced synthetic arrays validate
transport/refusal plumbing. A sparse file with the real native input dimensions
separately exercises full input validation; it is not meteorological evidence.

Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-005, GOV-SPEC-006.
Verification maps generated-lineage/non-contribution to `test_complete_delivery`;
input authority to native-input/nonfinite/configuration tests; bounded delivery
and absence on failure to archive/transport/budget/deadline tests.

Validation on 2026-09-07:

- `uv run --project experiments/st-johns-weather-map/api pytest experiments/st-johns-weather-map/api/tests/test_nvidia_fcn_delivery.py -q`: 49 passed.
- `uv run --project tools/specs python tools/specs/specctl.py validate`: 0 errors, 0 warnings.
- `git diff --check`: clean.
