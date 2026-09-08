# WeatherNext historical temperature app-delivery seam

Classification: experiment. Spec-Refs: GOV-SPEC-001, GOV-SPEC-004,
GOV-SPEC-006. The owner approved isolated native instantaneous 2 m temperature
provider-mean mapping to the existing temperature_2m Celsius field. No source
admission, public route, shared catalogue or current/future terms approval is
implied. The canonical precipitation p10/one-hour interval mapping was not assumed.

`weathernext_delivery.py::WeatherNextHistoricalDelivery` implements descriptors,
configuration, point EvidenceField delivery and explicit unsupported Series over
the existing bounded native bridge. Its immutable HistoricalConfiguration
requires the exact initialization, generation-qualified root ObjectIdentity and
explicit existing gcloud profile. No account, credential file or ADC is inspected.
The `latest` method default resolves only that configured run; it does not query
or claim the latest provider forecast. Other run identifiers fail before transport.
The descriptor therefore declares no temporal run selection or native Series.

Mapping: native `temperature_2m_mean` K -> canonical `temperature_2m` degC by
subtracting273.15. Product identity stays `weathernext_3_0_0_statistics`;
`Provenance.native_variable` carries the native array. The variant is the existing
`ensemble_mean` provider statistic, computed_here false, with no invented member
or member set. Source is `google-weathernext-3-statistics`, native level2m, actual
cell coordinates, native0.1-degree resolution and exact run/valid time. Evidence
is retrieved, published_cell, nonprimary, operational false, available-not-stored.
The absence of a supplied provider QC verdict remains unknown QC. A native null
remains null with native_fill_mask; it is never a zero or a favorable value.

The finite cache holds at most8 entries and256KiB serialized point accounting.
At most2 distinct acquisitions run concurrently; identical misses and refreshes
coalesce. Cache TTL60seconds starts after successful completion and ordinary
hits do not extend it. An unchanged refresh while unexpired preserves the old
receipt and expiry. Failed refresh raises a safe error, retains an unexpired
entry for an ordinary read, and has a5-second retry cooldown. Expired entries
are withheld. Failure state is bounded to8 entries. The strictly greater-than-
48-hour historical valid-time gate is checked before cache access and after
acquisition. Readiness means explicit configuration, not current coverage or
entitlement to another object.

The owner explicitly allowed up to64MiB total for this single-field slice.
The bridge/worker now accept a validated max_received_bytes parameter, capped at
64MiB; their existing default remains16MiB. This ceiling covers HTTP metadata
and payload bodies. Thirty operations,90seconds, Linux decoder2GiB and128MiB
native chunk declaration remain unchanged. IPC is bounded for64MiB base64 and
uses the existing deadline-aware pipe/HTTP subprocess lifecycle. Each successful
transport operation now records its actual completion time for SourceTransferReceipt.
No receive cap is silently raised based on object size.

## Live evidence

One actual historical temperature mean read succeeded through the final runtime
HTTP subprocess, Linux native decoder, mapping and point-cache path. An immediate
repeat returned an identical SourceAcquisition and issued no new requests.

- Initialization2026-08-01T00:00Z; valid2026-08-01T06:00Z.
- Native cell47.5,-52.70001220703125.
- Native temperature285.33551025390625K; canonical12.185510253906273degC.
- Provider ensemble_mean, native_variable temperature_2m_mean, no member.
- Eleven HTTP requests;19,691,271 successful response-body bytes, below64MiB.
- Root generation1787792319369404 explicitly pinned; no listing.

Full serialized point, object transfer receipts/digests, descriptor and repeated-
receipt equality are outside Git at
`/private/tmp/astraeus-weathernext-access-proof/live-temperature-delivery.json`.
No raw science payload is committed. This historical one-field proof establishes
neither current forecasts nor multi-field/cloud delivery. No additional live read
was made during final test/fixture checks.

## Integration and verification

Root prerequisite `b13c0fd` adds optional Provenance.native_variable (local
cherry-pick8809171 is equivalent). Root owns registration, API selection and UI.
The source-local reader can be constructed with HistoricalConfiguration and
called through the existing read_point signature. The new deterministic fixture
`api/tests/fixtures/weathernext3/historical-temperature-point.json` provides a
consumable descriptor and point JSON with explicit fixture data_mode.

Offline tests cover canonical mapping/native provenance, nulls, wrong native
field/statistic/unit/grid/run/member/location/generation/bytes, coalesced misses,
fixed expiry, unchanged refresh, failed refresh/cooldown, withheld expiry, deep
copy isolation, cache count, historical gate on hits and64MiB bound validation.
The existing native/bridge/transport/adapter/query suites and specctl run before
handoff. Source-local implementation is ready for root's reviewed app wiring;
no shared models/routes/catalogue were changed by this slice.
