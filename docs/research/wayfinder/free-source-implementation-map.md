# Free-source implementation Wayfinder

Created September 5, 2026 at the owner's request to implement all missing
data sources using free providers such as Open-Meteo.

The canonical artifact is [Wayfinder map: implement the missing free-access
evidence sources](https://github.com/TusharSariya/Astraeus/issues/70).
It carries an explicit execution override: implementation and verification
are in scope, rather than stopping at proposals.

## Resume

Read the map once, query its native child issues/dependencies, and claim the
first eligible unassigned ticket before working. The first implementation
planning task is [Reconcile every audited source with the free-provider
implementation roster](https://github.com/TusharSariya/Astraeus/issues/71).

The initial chart has 27 child tickets spanning the roster, free-use research,
capacity and contracts, WeatherNext, Open-Meteo, native forecasts, ensembles,
WCS, local/air-quality/marine/satellite/space-weather sources, cameras,
terrain/celestial inputs, bounded archives, Earth-2 and final verification.
Exact current status belongs to the tracker, not this document.

Starting research:

- [Verify Open-Meteo free access, provenance and request budgets](https://github.com/TusharSariya/Astraeus/issues/72).
- [Determine a no-charge WeatherNext access and sampling plan](https://github.com/TusharSariya/Astraeus/issues/73).

## Boundaries and evidence

The [source audit](../unimplemented-data-sources.md) and its appendices were
published at `333d5e2` on `research/unimplemented-source-audit` before charting.
It accounts for 118 registry entries plus additional research-only products.
Every eligible missing free source must be assigned; rejected, unavailable,
permission-dependent and superseded rows retain explicit dispositions.

The owner supplied a WeatherNext access-request acceptance email. No account
or entitlement was inspected while charting. Dataset version, authorized
surface, no-charge retrieval and representative sample remain separate checks.
Public source access does not authorize billed queries, egress, subscriptions
or rented compute.

Existing 64 GiB hot storage, rolling history and two-run limits remain until
the capacity/archive decisions explicitly change them. Free historical,
terrain and celestial sources are accounted for rather than silently excluded;
their acquisition must stay bounded. Successful FourCastNet prototypes must
create integration children that block final verification.

The older data-foundation charter and front-end design map remain reference
inputs. No front-end deferral, source-status promotion, paid purchase, provider
outreach or production deployment was authorized by charting this map.

Spec-Impact: none; tracker navigation and scope record only.
Spec-Refs: GOV-SPEC-001, GOV-SPEC-002, GOV-SPEC-004, GOV-SPEC-005, GOV-SPEC-006.
Verification: native child/dependency/label and acyclicity checks; specctl.
