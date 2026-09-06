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

One reference revision is an atomic group, including every required companion. Each source contract declares measured per-revision acquisition and stored bounds, reserved before retrieval. Admission projects all current and retained-superseded reference bytes against one 64 MiB aggregate sub-budget inside the unchanged hot-store quota. The immutable objects are uploaded and checked first; one database transaction advances the group pointer only after structural validation succeeds. Failure leaves the prior complete revision visible. Exactly one revision is current and routable. Supersession makes the former current revision immediately non-routable.

A reader resolves the current group once, verifies every member digest, then returns that same revision or reports unavailable. It never mixes members from different revisions. The experimental route is `/api/experiments/weather/v0/reference-inputs/{source_id}/{logical_name}` and declares `data_mode`, `operational: false`, revision, retrieval time, provider publication/version, coverage/effective/expiry metadata, structural verdict, scientific status, variables/constants, and notices. It accepts no latitude or longitude. Structural success permits visibility only here; all science and operational consumers refuse the resource until an accepted consumer profile makes it eligible.

## Window and retention

Each source selects `coverage_interval` or `effective_table`; `frame_window` is permitted only when primary source evidence proves the resource is genuinely a frame. A consumer interval must be fully covered. Provider expiry makes the current revision immediately unavailable, with no grace and no fallback to a retained predecessor. A source without provider expiry must declare an owner-approved `max_age` before activation or remain unavailable.

The unchanged 64 GiB hot-store quota and no-cold-tier policy continue to apply. Retain the current revision plus at most seven superseded revisions per source. A superseded revision is audit-only, never routable, and is removed after 30 days. A ninth revision evicts the oldest eligible superseded revision first. The eight-version and 30-day limits are retention ceilings, not guaranteed capacity. The initially measured IERS and LSK corpus is about 3.8 MiB, so 64 MiB provides about 16 times that measured headroom while remaining below 0.1 percent of the 64 GiB hot quota. Admission uses the actual projected retained set; it deletes eligible superseded revisions oldest-first and refuses the acquisition if the reference total would still exceed 64 MiB or the global quota. Never evict the sole unexpired current revision to admit a fetch. If eligible superseded eviction cannot make the projected set fit, reject acquisition and preserve the current pointer. Expired artifacts may remain physically retained for audit under the 30-day/eight-version limits but are unavailable to reads.

Exact raw bytes and normalized form are retained where redistribution terms permit. If terms prohibit raw retention, the source contract must name the permitted representation and reproducible integrity evidence; otherwise activation remains blocked.

## Single owner decision required before acceptance

Approve this policy as one contract: experimental-only visibility after structural validation; 67,108,864 bytes aggregate across all retained reference-input objects (raw, normalized, and required companions), inside the 64 GiB hot quota; one routable current plus seven audit-only predecessors for at most 30 days; immediate unavailability at provider expiry; source-specific `coverage_interval` or `effective_table`; required companions atomic; exact raw retention unless terms explicitly require another approved representation. This approval would unblock experimental publication/readback for issue #123. It would not register an adapter, authorize a science consumer, or promote operational status.

## Alternatives for owner review

The aggregate sub-budget could instead be 32 MiB (about eight times the measured initial corpus, with less growth room), 128 MiB (about 32 times the corpus and twice the recommended reserved footprint), or omitted in favor of only the 64 GiB global quota (weaker blast-radius isolation). Retention could be current-only or current-plus-one, reducing audit depth relative to the recommended maximum of eight versions for 30 days. The eight-version and 30-day values are ceilings within the aggregate budget, never reserved capacity. Structurally valid resources could also remain staged-only; the recommendation exposes them on the experimental route with an explicit scientific-unknown refusal for every consumer.
