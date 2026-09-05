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
- [x] Fetch bounded live full fields for HRDPS, RDPS, GDPS and WEonG.
- [ ] Owner accepts or revises the contract and production field/lead window.
- [ ] Register and schedule the production access path only after acceptance.
