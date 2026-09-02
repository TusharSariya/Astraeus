# Experimental source registry

This directory is the non-production, machine-readable audit for the St. John's
weather-map experiment. It does not modify or claim conformance with Astraeus
V1. `source_data.py` materializes every declaration into the exact structure in
`schema.json`; `catalogue_coverage.json` makes omissions from the POC catalogue
detectable.

## Two registries, two questions

- **`source_data.py` + `schema.json`** answer *which products this deployment
  may retrieve*: licence, cadence, endpoint, registry state, delivery kind.
- **`fields.py` + `fields.schema.json`** answer *what a field key means*: one
  physical quantity at one level with one unit and one declared phase, grouped
  into families that carry the comparability note, with the per-source mapping
  that says what each producer calls it and whether this deployment stores it.

`fields.py` is the single source of truth for field keys across ingest, the API
and the interface. Its query surface is the block of functions at the bottom of
the module (`field`, `resolve`, `family`, `members`, `comparability`,
`source_mapping`, `storage_of`, `available_not_stored`, ...); nothing outside it
should reach into its tables. It imports nothing heavier than `re`, so the
worker image can validate manifests against it.

Run the audit:

```sh
python3 experiments/st-johns-weather-map/registry/audit.py
python3 experiments/st-johns-weather-map/registry/audit.py --summary-json
python3 experiments/st-johns-weather-map/registry/audit.py --export > /tmp/st-johns-source-registry.json
python3 experiments/st-johns-weather-map/registry/audit.py --export-catalogue > /tmp/st-johns-field-catalogue.json
python3 -m unittest discover -s experiments/st-johns-weather-map/registry/tests -v
```

The audit checks both registries and refuses a field key any adapter manifest
declares that the catalogue does not carry. Adapter manifests are read
statically out of `ingest/`, so the check runs without numpy, xarray or a
network stack. A field's `storage` state (`stored`, `available-not-stored`,
`not-published`) is a scope decision about what is fetched; it is never a
registry status and promotes nothing.

No source is `active` yet. `active` is deliberately fail-closed: the audit
requires both fixture and opt-in live smoke tests to pass. Credential-gated
records name the official registration page but contain no credential values;
no credential should be requested until that adapter is ready for its live
test.

The `as_of` date records when primary documentation and endpoints were audited.
It is not proof that every endpoint is healthy. Live status belongs in adapter
smoke-test evidence and must preserve response/product schema versions.
