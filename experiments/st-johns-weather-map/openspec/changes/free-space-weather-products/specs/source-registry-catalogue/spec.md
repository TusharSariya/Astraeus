## ADDED Requirements

### Requirement: An admission condition is recorded satisfied by named evidence
A record whose admission condition is met SHALL keep the condition block,
mark it satisfied with the date and name the adapter version, fixture and
receipt that satisfy it. A record whose recorded access endpoint no longer
answers SHALL have the endpoint corrected with the failing status and date
stated in its reason, never swapped in silence; the corrected endpoint SHALL
serve the same producer product.

#### Scenario: The RTSW condition
- **WHEN** the v2 real-time solar wind adapter stores every quality flag and
  its fixture passes
- **THEN** the record is `implemented-unverified` with the condition marked
  satisfied on 2026-09-05 naming adapter, fixture and receipt

#### Scenario: A dead plasma endpoint
- **WHEN** `products/solar-wind/plasma-7-day.json` answers 404
- **THEN** the plasma record's endpoint is the live RTSW plasma feed and its
  reason states the 404 and the date
