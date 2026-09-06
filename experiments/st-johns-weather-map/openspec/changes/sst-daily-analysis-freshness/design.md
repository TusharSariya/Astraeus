# Design

## Why 60 hours

Both selected products are daily analyses rather than instantaneous station observations. NOAA documents preliminary OISST as daily with one-day latency and replacement by a final product after two weeks. Copernicus identifies OSTIA as a daily Level-4 analysis updated daily at 12:00. At the bounded checks on 2026-09-06, both providers' newest public analyses were dated September 4: OSTIA 00:00 was 54.0 hours old and OISST 12:00 was 42.0 hours old. This repeated the earlier 2026-09-06 00:15 check rather than indicating a one-off capture failure.

A 60-hour ceiling covers the observed daily delivery geometry through the next documented update boundary while remaining finite. The ceiling always uses native analysis valid time. Retrieval completion remains provenance only, so repeated retrieval cannot refresh stale evidence.

At the measured artifact sizes, retaining the current and previous revision for both sources totals at most 154,512 logical bytes (2 × (65,695 + 11,561)), before existing storage accounting and staging margin. This is a measured consequence, not a reservation estimate. Complete-operation bounds remain a separate implementation prerequisite, and the existing 64 GiB quota still decides admission.

## Route and retention

Only the current eligible revision is routable. A retained previous revision is audit/restart material and is not selectable from the current API after supersession. When the current revision exceeds 60 hours, current lookup refuses it as aged out even if bytes remain pending purge. Purge removes both current and previous revisions once their valid times exceed the source-specific window. No retrieval-time fallback, nearest-day fallback, archive refill, or cold tier is allowed.

Preliminary and final OISST retain distinct producer identities and content-addressed revisions. A final replacement for the same analysis day supersedes the preliminary revision atomically; it does not create a fresher valid time.

## Alternatives

- **Keep 24 hours and leave both sources unadmitted.** This preserves one universal window but cannot normally serve the verified daily products; it is the honest choice if source-specific freshness is undesirable.
- **Use 48 hours.** This can admit the observed OISST publication at some clocks but already excludes the verified 54-hour OSTIA latest analysis. It does not resolve the named scope.
- **Use 72 hours.** This gives more provider-outage tolerance but permits evidence a full additional daily cycle older than the measured maximum. Current evidence does not justify that larger exception.
- **Use retrieval age.** Rejected as unsafe: downloading an unchanged analysis would make stale evidence appear current.
