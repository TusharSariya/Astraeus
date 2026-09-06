# Daily SST analysis freshness and admission proposal

## Owner decision requested

Approve one source-specific experimental class, `daily_l4_analysis`, for `metoffice-ostia-sst` and `noaa-oisst-v2-1` with a 60-hour valid-time freshness ceiling. Admit only the newest provider analysis when its native analysis time is in `now-60h .. now`; never substitute retrieval time. Refuse the source as aged out once that ceiling passes, with no older fallback.

This recommendation also authorizes these two source IDs for experimental registration only after each implements and verifies complete-operation resource bounds under the accepted pre-discovery gate. It does not make either source operational, accept scientific quality, or authorize fog inference.

The storage exception is limited to these two daily analysis sources. Their latest and previous complete revisions may remain auditable while their native valid times lie inside the 60-hour source window; anything older is purged and unavailable. All other observations retain the accepted 24-hour window, forecasts retain the 14-day horizon, the 64 GiB hot quota is unchanged, and no cold or historical tier is added.

Spec-Impact: proposal only; owner acceptance is required before a specification delta or implementation.
Spec-Refs: GOV-SPEC-001, GOV-SPEC-002, GOV-SPEC-004, GOV-SPEC-005, GOV-SPEC-006
