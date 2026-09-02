# Experimental source registry

This directory is the non-production, machine-readable audit for the St. John's
weather-map experiment. It does not modify or claim conformance with Astraeus
V1. `source_data.py` materializes every declaration into the exact structure in
`schema.json`; `catalogue_coverage.json` makes omissions from the POC catalogue
detectable.

## Two registries, two questions

- **`source_data.py` + `schema.json`** answer *which products this deployment
  may retrieve*: licence, cadence, endpoint, registry state, delivery kind,
  and how far each source reaches.
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

## The horizon fields

Five optional fields say how far a source reaches and when its runs appear.
All are keyword-only in `_source(...)` with no default: **absent means absent**,
because a reach nobody stated and a latency nobody measured are exactly the
values that must not exist.

| Field | On which records | What it says |
| --- | --- | --- |
| `reach` | every record with a registered adapter | `earliest_hours` and `latest_hours` of valid time relative to run time, plus an optional `per_cycle` map of `"HH"` to `latest_hours` where the cycles differ. An observation is `0` to `0`. |
| `run_cadence_seconds` | forecast records | the producer's own run cadence, declared, never parsed into existence |
| `native_cadence_seconds` | observation and nowcast records | the layer's own publication interval |
| `publication_latency` | forecast records | `estimate_seconds`, `observation_count`, `last_observed`, `measured`, `basis` |
| `datamart_fallback_path` | the three ECCC Datamart models | the dated `/{YYYYMMDD}/WXO-DD/{model}/{HH}/{FFF}/` layout the adapter walks |

`reach` is a declared fact and is never rewritten from what a fetch returned: a
run that publishes fewer leads than it promised leaves those instants uncovered
*by that run*, which is a different statement from a shorter reach.

Publication latency is held apart from cadence because it is **measured, not
promised**. Today every record's `measured` is false: the seven seeds (ICON,
GFS, GEFS and the four ECMWF records) come from
`docs/research/wayfinder/planning-horizon-matrix.md`, measured on 2026-09-02
against the producers' clocks, and they are the estimator's starting point, not
this deployment's observation. GDPS, GEPS, REPS and WeatherNext 2 have neither
a seed nor an observation and carry a null estimate with `basis: "none"`;
scheduling for them falls back to the run time itself. The audit refuses a
defaulted latency: an estimate that is not null must name a basis, and `"none"`
is not one.

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
network stack. The same static read collects each adapter's `source_id`, and
every record behind one must declare a reach; the summary line reports how many
records declare one, how many latencies are seeded and how many are measured
here (`registry/tests/test_reach.py` covers each rule). A field's `storage` state (`stored`, `available-not-stored`,
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
