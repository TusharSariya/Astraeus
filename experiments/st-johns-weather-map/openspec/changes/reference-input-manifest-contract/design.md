# Design: reference resources are not weather evidence runs

## Proposed contract

`ReferenceInputManifest` would declare:

| Concern | Required declaration |
|---|---|
| Identity | registered source id, logical resource name, provider product, immutable provider revision rule, exact access URLs |
| Payload | media type, byte ceiling, required variables or constants, units, permitted missing fields, schema/version marker |
| Time | provider publication time when present, HTTP retrieval completion, raw reference epochs with named scale, coverage start/end, effective-from boundaries, expiry when published |
| Spatial scope | `not_applicable` or `global_reference`; latitude/longitude are forbidden unless the provider resource itself is spatial |
| Validity | one declared temporal policy (`frame_window`, `coverage_interval`, or `effective_table`), freshness/expiry policy, and the interval a downstream consumer may request; no invented `run_time` |
| Grouping | all artifacts required for one revision, so version data and companion identity metadata become visible together |
| Use ceiling | `operational: false` plus explicit eligible consumer profiles; empty while the contract is experimental |

Raw epochs remain exactly provider-defined. UTC, TAI, TT, TDB and UT1 are distinct labels; converting between them is a separate accepted scientific method. A calendar date and MJD in one source row must identify the same instant. Effective dates, table expiry, provider publication, HTTP retrieval, and kernel coverage are separate fields.

## Validation split

Structural validation computes `complete` and `qc_passed`; adapters never assert them. It checks required payload members, schema/version identity, finite values, declared units, monotonic or explicitly ordered epochs, calendar/MJD agreement, coverage declarations, digest/size, expiry, and adapter decode errors. A failed result may be staged for diagnosis but cannot call `publish_run`.

Structural success does not assert that a reference is scientifically suitable. A separate `scientific_status` is `unknown`, `eligible`, or `ineligible` per accepted consumer profile. Only an accepted profile can move it from `unknown`; retrieval success cannot. For example, an Earth PCK may parse structurally while remaining unusable for astronomy until the required Earth frame, interval, observed/predicted boundary, and accuracy are approved. Whether structurally valid, scientifically unknown resources may become visible on the dedicated route is an owner choice below; the proposal does not choose it.

## Publication and reads

One reference revision is an atomic group. The immutable objects are uploaded and checked first; one database transaction advances the group pointer only after structural validation succeeds. Failure leaves the prior complete revision visible. A reader resolves the current group once, verifies every member digest, then returns that same revision or reports unavailable. It never mixes a kernel from one revision with an identity note from another.

The proposed route is `/api/experiments/weather/v0/reference-inputs/{source_id}/{logical_name}`. Its strict response declares `data_mode`, `operational: false`, revision, retrieval time, provider publication/version, coverage/effective/expiry metadata, structural verdict, scientific status, variables/constants, and notices. It is not a sampling endpoint and accepts no latitude or longitude.

## Window and retention

The generic manifest does not grant a window exception. It requires one explicit temporal policy. `frame_window` applies the existing 24-hour frame purge. `coverage_interval` validates a bounded continuous coverage range such as an EOP product. `effective_table` preserves provider effective boundaries such as leap epochs. Only a source-specific accepted contract may select among them. A downstream consumer must request an interval, and routing fails closed if the selected policy does not cover it or the resource is expired.

Reference resources remain under the existing global quota with no cold tier. This proposal does not select a retention exception. The owner must choose whether each source uses existing frame purge, current-only, or current-plus-previous retention, and must define the byte projection before activation. An expired current revision never silently becomes usable through an older revision, regardless of the selected retention policy.

## Owner decisions required before acceptance

1. Whether structurally valid but scientifically `unknown` resources may be published to the dedicated route, or must remain staged until one consumer profile is accepted.
2. Whether companion files such as a kernel identity note form one source revision or separate linked source records.
3. Whether normalized values alone are sufficient, or exact raw reference bytes must also be retained as an artifact under provider redistribution terms.
4. The first accepted consumer profile, if any, including required time scales, frame, coverage interval, accuracy, and observed/predicted eligibility.
5. Whether expiry makes the current pointer unavailable immediately or after a separately declared grace interval. The recommended default is immediate unavailability.
6. Which temporal and retention policy applies to each source, and its maximum retained bytes under the existing quota with no cold tier.
