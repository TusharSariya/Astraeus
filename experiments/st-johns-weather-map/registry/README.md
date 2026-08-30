# Experimental source registry

This directory is the non-production, machine-readable audit for the St. John's
weather-map experiment. It does not modify or claim conformance with Astraeus
V1. `source_data.py` materializes every declaration into the exact structure in
`schema.json`; `catalogue_coverage.json` makes omissions from the POC catalogue
detectable.

Run the audit:

```sh
python3 experiments/st-johns-weather-map/registry/audit.py
python3 experiments/st-johns-weather-map/registry/audit.py --summary-json
python3 experiments/st-johns-weather-map/registry/audit.py --export > /tmp/st-johns-source-registry.json
python3 -m unittest discover -s experiments/st-johns-weather-map/registry/tests -v
```

No source is `active` yet. `active` is deliberately fail-closed: the audit
requires both fixture and opt-in live smoke tests to pass. Credential-gated
records name the official registration page but contain no credential values;
no credential should be requested until that adapter is ready for its live
test.

The `as_of` date records when primary documentation and endpoints were audited.
It is not proof that every endpoint is healthy. Live status belongs in adapter
smoke-test evidence and must preserve response/product schema versions.
