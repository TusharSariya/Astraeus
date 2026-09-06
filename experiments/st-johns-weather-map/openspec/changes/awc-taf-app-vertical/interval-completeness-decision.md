# TAF interval and structural completeness decision

Status: proposed for owner decision. This document does not authorize source
activation.

## Observed mismatch

The bounded 2026-09-06 CYYT response contains one prevailing group followed by
six change/conditional groups. The response is structurally complete, but the
generic timestamp-grid validator rejects it for two reasons:

1. the prevailing group begins at 12:00Z and governs conditions after the
   scheduler window begins at 13:30Z, so its native start stamp lies just before
   the window even though its validity interval intersects it; and
2. BECMG, TEMPO and PROB groups omit unchanged elements. Counting every omitted
   group/field cell as absent gives coverage `0.8095`, below the manifest's
   `0.9` threshold.

The retained response is 3,086 bytes with seven groups. A Linux bounded replay
produces a 33,658-byte artifact, correctly marked incomplete and QC-failed by
the current generic validator.

## Primary-source semantics

Transport Canada's 2026 Aeronautical Information Manual states that an FM
group is a complete replacement forecast and includes all elements. It also
states that BECMG normally contains only elements that change and omitted
elements remain as in the prior period; TEMPO likewise contains only temporary
changes and omitted elements remain as in the prior period. See TC AIM,
MET 7.4.3, pages 156–159:
<https://tc.canada.ca/sites/default/files/2026-03/aim-2026-1_access_en.pdf>.

The Aviation Weather Center's official product help independently states that
each FM group contains all TAF elements and only temporarily changed elements
appear in a TEMPO group:
<https://www.connect.aviationweather.gov/help/data/>.

These rules explain the provider payload. They do not authorize this
experiment to synthesize inherited values.

## Recommended narrow contract

Treat a TAF as an ordered set of native validity intervals and sparse change
groups, rather than a regular timestamp grid:

- Preserve the initial prevailing group and every intersecting FM, BECMG,
  TEMPO and probability group in provider order with native `timeFrom`,
  `timeTo`, `timeBec`, change label and probability.
- A group is applicable when its half-open native interval intersects the
  requested evidence window. Its native start MUST NOT be clamped or replaced.
- Require the initial prevailing group and every FM group to carry the complete
  mandatory field set.
- Permit BECMG, TEMPO and probability groups to omit unchanged fields. Record
  each omission as `not_stated_in_change_group`, distinct from an unknown or
  malformed value.
- Do not materialize inherited values in the artifact or API. A later explicit
  composition contract may compute a prevailing-at-instant view, but this
  source slice publishes the sparse native groups only.
- Structural completeness requires one valid CYYT report, aware issue time,
  increasing overall validity, 1–32 valid ordered groups, a complete prevailing
  group, complete FM groups, and valid syntax/units for every field that is
  present. It does not use the generic per-cell `0.9` coverage ratio.
- Any malformed identity, time, group, field, unit, unknown cloud vocabulary or
  unsupported seventh cloud layer fails the whole run.

This leaves the existing generic `validate_run` behavior unchanged for gridded
and point-time-series sources. A TAF-specific structural validator returns the
same one-way `ValidationResult` and publication remains fail closed.

## Alternatives rejected

- Carrying prior values forward would create new values and choose BECMG
  transition timing, which is a separate product decision.
- Clamping the prevailing start to the request window would fabricate native
  time identity.
- Lowering `min_coverage_fraction` would hide the semantic mismatch and still
  misclassify deliberate omissions as missing evidence.
- Dropping the overlapping prevailing group would remove the conditions that
  govern the beginning of the requested window.

## Required owner resolution

Accept or reject the recommended sparse interval/group contract. Acceptance
authorizes a source-specific structural validator and native sparse API/read
path; it does not authorize inheritance, interpolation, change-transition
timing, aviation decision support, operational status, or any other aviation
family expansion.
