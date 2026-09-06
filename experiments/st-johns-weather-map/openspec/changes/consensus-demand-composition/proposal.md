# Consensus composition from timestamp-demand sources

## Why

Issue #223 replaces the remaining retained-artifact acquisition inside the
existing BLEND point path. The accepted registry eligibility and consensus
calculation remain unchanged.

## What changes

- Query migrated HRDPS and GFS point seams concurrently for the selected aware instant.
- Preserve each successful source field and provenance without round-tripping it through storage models.
- Omit source failures independently and feed only eligible retrieved temperature evidence to the existing consensus calculation.
- Never read or fall back to retained forecast artifacts for BLEND.

With no migrated ensemble family today, HRDPS plus GFS cannot meet the existing
minimum-evidence rule. The response therefore truthfully selects fresh HRDPS as
primary while keeping GFS visible as independent supporting evidence. This is
an acquisition change only; it creates no new blend science or operational
promotion.

## Verification

- Exact demand composition preserves HRDPS and GFS field provenance while the
  unchanged consensus policy reports minimum evidence unmet and selects fresh
  HRDPS as primary.
- A cold browser readback shows HRDPS, GFS, and METAR response-backed evidence
  together without retained-artifact substitution.
- Production HRDPS and GFS cache services load once on the first composed
  request and add zero loader calls for an identical immediate repeat.
- The complete API suite passes with retained artifact readers still covered as
  audit paths and explicitly excluded from default BLEND acquisition.
