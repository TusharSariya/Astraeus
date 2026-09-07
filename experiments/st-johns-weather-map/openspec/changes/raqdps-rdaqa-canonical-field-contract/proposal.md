# RAQDPS and RDAQA canonical field and phase contract

## Problem

The bounded experiment retrieves all 28 selected RAQDPS and RDAQA coverages, but fourteen quantities cannot enter a full `RunManifest` truthfully. The catalogue lacks PM10 column burden, nitric-oxide and other gas mole-fraction keys, wildfire-attributed particulate keys, smoke 24-hour statistics, and a required RDAQA phase identity. Existing gas mass-concentration keys are dimensionally incompatible with GeoMet's `mol/mol` values.

## Recommended decision

Approve the contract in `design.md` as one package: reuse dimensionally matching particulate and ozone keys; add the ten listed canonical keys; normalize all gas mole fractions to `nmol mol-1` by exact multiplication by 1e9; require product phase, vertical scope, attribution and statistic-window attributes; and publish one atomic logical stream per product phase and valid time. RAQDPS retains its provider reference time. RDAQA retains its provider analysis valid time with `run_time: null` and separate preliminary, final and FireWork-contribution identities.

This draft changes no accepted specification or runtime behavior. The existing adapters remain experimental, unregistered, unscheduled, nonpublishable and `operational: false` until owner acceptance and a separately reviewed implementation proves normal-route publication and API readback.

Spec-Impact: proposed canonical field and product-phase contract; no normative status transition.
Spec-Refs: GOV-SPEC-001, GOV-SPEC-002, GOV-SPEC-004, GOV-SPEC-005, GOV-SPEC-006
