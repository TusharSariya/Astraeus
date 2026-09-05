## 1. Contract and inventory

- [x] Enumerate the exact selected HRDPS, RDPS and GDPS coverage identifiers in code.
- [x] Record retrieved, missing and not-published disposition for every selected field.
- [x] Re-probe the current WCS inventory and retain the dated result.

## 2. Experimental implementation

- [x] Add metadata-first WCS fetch, HTTP-200/XML rejection and bounded TIFF validation.
- [x] Add deterministic zipped-Zarr publication with checksum and run/access-path provenance.
- [x] Keep the module outside production registration and scheduling.

## 3. Verification

- [x] Add positive fixture retrieval and immutable artifact/API sampler round-trip.
- [x] Add missing coverage, wrong-grid and XML `NoMatch` negative cases.
- [x] Refuse omitted reference times on run-bearing layers before GetCoverage; retain unknown run identity only when the layer has no run dimension.
- [x] Fetch bounded live full fields for HRDPS, RDPS, GDPS and WEonG.
- [x] Retrieve all 245 selected coverages at one latest advertised valid time over the small Avalon API bbox; record values, units, masks, resolution, transfer, timing and exact failures.
- [x] Retain representative artifacts and checksums for reproducible reader verification.
- [ ] Owner accepts or revises the contract and production field/lead window.
- [ ] Register and schedule the production access path only after acceptance.

## Tracked follow-up work

These open tickets track remaining work beyond the completed isolated acquisition evidence. Their existence does not accept contracts or authorize production activation.

- [ ] [Complete GeoMet experimental source admission and field-window contracts](https://github.com/TusharSariya/Astraeus/issues/141).
- [ ] [Account for the remaining advertised GeoMet family fields](https://github.com/TusharSariya/Astraeus/issues/145).
