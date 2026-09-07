# Native Series implementation evidence, September 7, 2026

Conforming implementation under the existing single owner acceptance record;
GOV-SPEC-001, GOV-SPEC-004 and GOV-SPEC-006. This records implementation choices,
not a new product decision or a verified source/status transition.

## Implemented seam and bounds

`api/weather_api/desktop_series.py` adds `POST /point/series` and
`POST /point/series/changes`, retaining existing `EvidenceField` / `Provenance`.
Initial reads accept exact coordinates, an offset-qualified half-open window,
canonical catalogue keys and request-local selector IDs. Continuations accept
only their opaque signed cursor. Selected response backing stays process-local.

| Bound | Implementation |
|---|---|
| Selectors | 1–2; duplicate selector IDs rejected |
| Window | Positive, at most 24 hours |
| Native acquisition | At most 12 distinct source/timestamp point reads, sharing one read across selected fields from that source/time |
| Returned samples | At most 48, including native nulls |
| Selection bytes | At most 512 KiB including charged selection/cursor/identity metadata |
| Page | 1–24 units; a native reading or a row with no readings occupies a unit |
| Read duration | 45 seconds; timed-out source operation retains its slot until it exits, then stops before another point read |
| Concurrent acquisition | Two slots, no unbounded executor queue |
| Cache | At most 16 selections and 8 MiB serialized backing; five-minute fixed, nonrenewing expiry |

The existing coordinator still owns each individual transport/decoder bound and
source cache. HTTP timeout does not claim to forcibly kill its running worker.
No source worker/decoder, database, artifact store or ingestion schedule changed.
Capacity rejects new selections instead of evicting an unexpired reader pin.
Expired cursors remain distinguishable after lazy backing cleanup through their
signed expiry; process restarts cannot recover response backing.

Change checks consult only the selected native source/fields, comparing original
identities, values, availability and interpretation metadata. Retrieval time,
freshness and transport revalidation receipts do not themselves signal a change.
A source's ordinary finite cache may still answer the check; the response and UI
say so. Failed comparison is unknown; a slow comparison cannot outlive expiry.
Checks never replace displayed values or acknowledge a previously observed change.

## Native delivery coverage and residuals

This slice uses HRDPS, RDPS, GDPS and GFS coordinators' native inventory and exact
point sampling seams directly. It does not use the hourly `/timeline`, `/point`
observation fanout, or a retained-store fallback. It filters every returned field
by canonical key, exact advertised native valid time and source identity.
An empty consulted run listing is unknown, not proof of source-wide absence.
Fields missing from advertised timestamps are unknown; explicit returned nulls
remain native absences. Unsupported sources and unsupported named run pins are
explicitly unavailable, without substitutes.

Still open: inventory/read support for actual named previous runs and two-run
comparison; additional native observation/ensemble/environmental readers; full
source field admission; imagery availability/joins; camera metadata. Four
coordinator connections do not complete those source issues or the full Series
view. No live provider payload was captured or committed in this slice.

## Mapped verification

- `api/tests/test_desktop_series.py`: sparse independent timestamps, exact source
  filtering, zero/native absence, immutable pages, altered cursor, geographic
  refusal, window/read/byte/capacity limits, concurrent misses, failed refresh,
  deadline slots, unrelated/relevant update, fixed expiry including during check.
- Existing HRDPS/RDPS/GDPS/GFS query tests exercise their existing cache/sample
  seams. Two catalogue-exclusivity assertions failed identically at the preceding
  merged Bench revision; they now assert their particular live proxy survives a
  failed legacy store without excluding other admitted proxies.
- `web/src/workbench/NativeSeries.test.tsx`: native tables/axes, cursor continuation,
  exact Focus, cross-view and Compare selection persistence, explicit refresh,
  failed replacement, fixed expiry, and StrictMode initial-read replay.
- `web/scripts/prove-desktop-series.mjs`: real Chrome, fixed responses and clock,
  all external requests blocked; shared Bench, native null/zero, inspection and
  Escape focus return, Compare pin continuity, change check, failed refresh,
  expiry, three themes and 200% text zoom. Receipts/screenshots remain outside Git
  at `/tmp/astraeus-series-proof/`. This is browser verification, not a provider,
  screen-reader or outdoor proof.

The controller lives in App so changing stage/dock does not discard a selection.
Overview and temporary Compare share two selected tracks with separate value axes;
changing the Compare display alone does not acquire a replacement. Unknown class,
refused derivation and unmodelled provenance do not become plotted numbers.

Final validation is recorded in the pull request and existing handoff.

Validation: affected API/source suites 89 passed; complete client suite 473
passed, followed by the final eight Focus/Series cases after the unresolved-site
guard; production build passed. Both changed OpenSpec packages passed strict
validation and repository specctl reported zero errors/warnings. The browser
procedure passed after final view changes. The prior merged revision reproduced
both repaired catalogue assertions (two failures), establishing fixture drift.


## Read-only camera and geometry completion

The Sky batch adds `/registry/cameras` beside the existing site/horizon read.
An explicit public-field allowlist separates registry eligibility from image
implementation and actual retrieval. Version hashes cover only public content;
private terms/endpoints and audit exception text never enter the response.
Existing camera audit/refusal logic remains the authority. Outside-core point
and astronomy reads now return the typed `outside_supported_area` refusal with
exact requested coordinates. Unsupported geometry returns nulls. Registry,
camera, site, space-weather and astronomy checks: 77 passed, six kernel-dependent
astronomy tests skipped. This completes task 5, not imagery joins or camera delivery.
