# Selected-layer point data

Status: accepted for implementation in the isolated weather-map experiment.
No operational or verified status is asserted.

Owner authorization, September 8, 2026: @TusharSariya explicitly approved this
contract and instructed: “yeah sure i agree with the controact, go and implement”.
This resolves the recorded conflict and authorizes the specified replacement.

## Why

The owner supplied the selected-layer Point data panel implementation plan on
September 8, 2026. Selected fields need independent readings at shared Focus,
including fields whose map imagery is hidden or unavailable.

The current desktop contract instead requires binary map membership, a separate
visibility control, Active-row removal on click, and details-only point rows.
The accepted delta names their replacement, as required
by GOV-SPEC-004 and GOV-SPEC-005.

## What changes

- Replace binary membership with Off, Map + data and Data only, retaining
  explicit Remove and independent opacity/order.
- Expose supported individual point fields with explicit capability identities.
- Add a persistent, minimizable bottom-left Point data panel with family groups,
  selected-field filtering and independent exact-request results.
- Preserve URL and saved-stack compatibility, returned native-time semantics,
  provenance, camera and keyboard return context.

## Scope and authority

This is a requirement change within the isolated weather-map experiment. The
proposed contract supplements and replaces the conflicting selection clauses
in `desktop-evidence-workbench/specs/desktop-evidence-workbench/spec.md` under the owner acceptance recorded above. Existing right-side Layers placement, data
truth boundaries, provider contracts and scientific metadata remain governing.

No provider integration, scientific derivation, numeric raster-colour sampling,
acquisition schedule, operational status or verified status is proposed.

## Implementation evidence

Read-only inspection found existing seams in `LayerRow.tsx`, `MapStack.tsx`,
`DiscoveryBrowser.tsx`, `discovery.ts`, `layerIdentity.ts`, `focusUrl.ts`,
`WorkbenchShell.tsx`, `App.tsx` and `api.ts::loadPoint`. `loadPoint` already
accepts cancellation and ensemble selectors and normalizes point responses.
The present desktop selects one point product for its evidence ledger; the new
panel requires independent request identities and results.

The implementation uses these existing seams, with explicit point capability
references in selections, family-grouped readings, a cancellable two-slot request
queue and compatible restoration. See [implementation evidence](implementation-evidence.md)
for exact verification commands and browser captures. No provider acquisition or
scientific code was modified. Unmatched map identities remain numeric-unavailable;
removed capabilities and unsupported selector paths remain explicitly unavailable.

Spec-Refs: [GOV-SPEC-001](../../../../../docs/specv1/GOVERNANCE.md#gov-spec-001--specifications-are-authoritative),
[GOV-SPEC-004](../../../../../docs/specv1/GOVERNANCE.md#gov-spec-004--behavior-changes-are-spec-traceable),
[GOV-SPEC-005](../../../../../docs/specv1/GOVERNANCE.md#gov-spec-005--conflicts-fail-closed),
[GOV-SPEC-006](../../../../../docs/specv1/GOVERNANCE.md#gov-spec-006--verification-is-part-of-the-requirement).

## Compact capability-aware amendment, September 8, 2026

Owner authorization: @TusharSariya supplied the “Compact, capability-aware
Point data” plan and instructed this session to implement it, including updating
the approved experimental contract. This explicitly replaces the earlier
image-only-in-category and unchanged-point-time clauses. It authorizes the
optional directional policy and connection of existing GeoMet radar sampling,
within this isolated experiment; no operational or verified status is asserted.

Verification mapping: the reading and request scenarios map to
`PointDataPanel.test.tsx`, `pointRequests.test.ts`, API directional and radar
tests, source capability checks and `scripts/prove-point-data.mjs`.

Current amendment results and source-discovery limitations: [compact implementation evidence](compact-implementation-evidence.md).
