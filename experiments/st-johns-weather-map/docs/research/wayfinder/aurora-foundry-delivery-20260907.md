# Prepared Aurora 1.5 Foundry submission software

Classification: **experiment**, source-local and unregistered. The owner's
API-first instruction authorizes prepared software despite missing compute and
access. This narrows the earlier [research handoff](inference-candidate-handoff.md):
a concrete deterministic SDK submission path is now settled. It does not admit
Microsoft Aurora to a provider, worker, model registry, API route, or client UI.
`api/weather_api/aurora.py` remains the unrelated astronomical aurora module.

## Reviewed upstream contract

- SDK distribution: `microsoft-aurora==2.0.1`; reviewed wheel SHA-256
  `f9b72b268d579c0799e476afe121c62cd8dde6501f8505f3480c4cb89a5ce019`.
- Submission source `aurora/foundry/client/api.py` SHA-256
  `073ca4c7a2159079180368485f207e086140f19fad39d8a0ac534bf869b8f26c`.
- Reviewed upstream tree: `7179f501b9f1a66e0444b782ecd06aa07062c8bc`.
- Selected model: `aurora-0.25-v1.5`, deterministic, hosted by an Aurora-1.5
  deployment. Ensemble, original Aurora, wave and pollution variants are excluded.

The [official submission API](https://microsoft.github.io/aurora/foundry/api.html)
and [submission source](https://microsoft.github.io/aurora/_modules/aurora/foundry/client/api.html)
provide `submit(batch, model_name, num_steps, channel, foundry_client, ...)`.
The wrapper calls that API with explicit fine lead times and surface outputs,
empty atmospheric/static selections, synchronous server uploads and downloaded
native predictions. It preserves the SDK task creation, input upload,
acknowledgement, polling and indexed prediction-file sequence.

The [official 1.5 example](https://microsoft.github.io/aurora/foundry/demo_v1p5.html)
defines supplied native surface/history, atmosphere/pressure-level and static
inputs. The source-local contract accepts one global float32 Batch: 19 surface
arrays including caller-prepared insolation, 5 atmosphere arrays on 13 ordered
pressure levels, and all 36 static arrays. Input dimensions are `(1,2,721,1440)`,
`(1,2,13,721,1440)`, and `(721,1440)` respectively. History is six hours, latitude
decreases from 90 to -90, and longitude increases from 0 to 359.75.
No input acquisition, missing-value replacement, normalization, regridding,
insolation generation, or unit conversion is implemented.

The pinned [model forward path](https://github.com/microsoft/aurora/blob/7179f501b9f1a66e0444b782ecd06aa07062c8bc/aurora/model/aurora.py)
uses [Batch.crop](https://github.com/microsoft/aurora/blob/7179f501b9f1a66e0444b782ecd06aa07062c8bc/aurora/batch.py),
removing the final latitude row: output is `(1,1,720,1440)` with latitude ending
at -89.75. The wrapper verifies this native geometry and every requested valid
time. It does not interpolate the removed pole or equate cloud fields with an
accepted Astraeus cloud quantity.

## Software boundary and invocation

`api/weather_api/aurora_foundry_delivery.py` exports `Initialization`,
`ForecastRequest`, `RuntimeConfig`, `ReceivedBatch`, and `deliver`. The versioned
contract is `aurora-foundry-delivery-v1`. Runtime configuration names are:

| Name | Default or requirement |
| --- | --- |
| `endpoint_url` | Supplied HTTPS endpoint, no embedded user info/query/fragment |
| `deployment_id` | Supplied deployment identity; not remotely verified |
| `sdk_revision` | Exact reviewed upstream revision |
| `request_timeout_seconds` | 30 seconds, maximum 120 |
| `deadline_seconds` | 900 seconds, maximum 3600 |
| `poll_interval_seconds` | 2 seconds, maximum 60 |
| `max_polls` | 450, maximum 3600 |
| `max_input_bytes` | 1 GiB logical/native and transport cap |
| `max_output_bytes` | 256 MiB aggregate output cap, maximum 1 GiB |

A runtime owner supplies `BoundedClient` and `BoundedChannel` implementations.
The client endpoint must equal configuration. Transports must enforce the
supplied timeout and byte limits before allocation/deserialization and suppress
upstream-body logging. `ReceivedBatch` reports serialized bytes actually read;
aggregate accounting charges the larger of serialized and native tensor sizes.
The known tensor size of all requested outputs must fit before job submission.
Network I/O and storage implementations remain required integration work:
**raw SDK FoundryClient/BlobStorageChannel do not satisfy this bounded contract**.
Their reviewed request/poll/download paths have no suitable complete bounds.

```python
forecast = deliver(
    native_batch, initialization, ForecastRequest(),
    RuntimeConfig(endpoint_url=endpoint_url, deployment_id=deployment_id),
    client=bounded_endpoint_transport, channel=bounded_blob_transport,
)
```

Without an injected `sdk_submit`, the wrapper loads the installed 2.0.1 SDK only
when its source digest matches. It installs nothing. Tests inject the submission
call and bounded transport fixtures. No credentials are read or constructed here.

`Initialization` requires source/run identity, UTC previous/current times,
input/static/checkpoint SHA-256 attestations, transformation version, native-unit
contract and terms reference. **Those hashes, units, permissions and checkpoint
identity are caller attestations, not verified against a serialized Batch or a
live deployment.** Supplying them does not establish initializer availability,
licence clearance, scientific validity, or measured deployment provenance.

A failure returns no partial result, uses safe fixed error codes, and never
substitutes another source/run. Client deadline/poll exhaustion closes the local
iterator but **does not cancel a remote job**; this SDK contract exposes no
verified cancellation operation. Enforcing a timeout while inside an I/O call
depends on the injected transport honoring it. A runtime supervisor must own
remote-job cleanup and resource/cost controls.

## Verification and remaining owners

`api/tests/test_aurora_foundry_delivery.py` covers the native schema, time/grid,
input completeness, nonfinite refusal, request/output preflight, task failure,
poll/deadline caps, receipts, output completion and safe errors. Fixtures use
broadcast arrays; they are not real initial conditions or inference evidence.
All 26 tests passed with the reviewed wheel supplied; `specctl` reported zero
errors and zero warnings. An optional test loads the hash-checked wheel's actual `submit` source, replaces
imports with fixture types and executes its orchestration without torch/model
execution or network. Reproduce with the reviewed wheel path:

```sh
AURORA_SDK_WHEEL=/private/tmp/microsoft_aurora-2.0.1-py3-none-any.whl \
PYTHONPATH=experiments/st-johns-weather-map/api \
python -m pytest experiments/st-johns-weather-map/api/tests/test_aurora_foundry_delivery.py -q
uv run --project tools/specs python tools/specs/specctl.py validate
```

Deployment and bounded network/storage transport owner: unresolved. Complete,
lawful IFS initializer and transformation/static-data owner: unresolved. No
endpoint was deployed, paid request submitted, model loaded, initialization
payload obtained or real prediction verified. Consumers receive only a
`generated-here`, `admitted=False` source-local result; physical cloud bounds,
accumulation semantics and forecast skill need separate scientific verification.

Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-006. No accepted V1 Aurora provider
requirement is claimed. This experiment preserves the optional forecast-centre
contract's admission, provenance, no-extra-vote and absent-evidence constraints.
