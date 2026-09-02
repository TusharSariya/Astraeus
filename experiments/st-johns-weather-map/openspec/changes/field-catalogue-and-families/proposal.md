## Why

Three adapters declare a manifest field named `total_cloud`, and two of them
are not the same quantity. HRDPS cloud is opacity-weighted, so thin cloud
reads near zero; GFS cloud is a geometric maximum-random overlap fraction
(hard-won facts in `openspec/config.yaml`). Nothing stopped the collision,
because the canonical names adapters declare in `RequiredField` are
conventions with no registry behind them. The same is true of relative
humidity, which two models publish over different phases, of "transparency",
which the astronomy research found under four incompatible encodings, and of
GEFS total cloud, which is a six-hour average carrying the same name as an
instantaneous field.

The owner decided on 2026-09-02 (wayfinder ticket 18) that the evidence
layer exposes a canonical field catalogue: one physical quantity per field,
related quantities grouped in field families that carry the comparability
note, machine-readable and enforced in CI, with every adapter manifest and
every derivation method referencing only catalogue keys. The owner also
decided the catalogue's scope: every field every admitted source publishes,
nothing dropped at the field level, with the storage rule from ticket 20
deciding what is fetched from feeds that cannot subset server side. Research
behind the decisions: `docs/research/wayfinder/astronomy-tool-needs.md`,
`transparency-seeing-sources.md`, `geomet-wcs-inventory.md`,
`size-probe-full-fields.md`.

## What Changes

- **A field catalogue exists as a versioned registry**, validated in CI. A
  field is one quantity at one level with one unit; its key keeps the project
  style already in use (`temperature_2m`, `wind_u_10m`), with a CF
  `standard_name` attached where one exists.
- **Different quantities never share a key.** HRDPS opacity-weighted cloud
  and GFS geometric cloud become distinct fields; GEFS six-hour-mean cloud is
  a third. Related fields form a **field family** (cloud cover, transparency,
  seeing, humidity, wind) that carries the note on which members are
  comparable. Activity profiles refer to families.
- **Humidity phase is an attribute, not a key**, stamped on the value, with a
  comparability rule that flags liquid-versus-mixed pairs below freezing.
- **Levels**: height fields carry the level in the key (`_2m`, `_10m`,
  `_40m`, `_80m`, `_120m`); pressure-level fields are one profile field with a
  level coordinate.
- **Manifests and derivation methods reference catalogue keys only.** A
  manifest naming a key the catalogue lacks fails validation; a key with the
  wrong unit fails as it does today.
- **Scope: every published field.** For sources that subset server side
  (GeoMet), every published field is stored. For feeds that cannot subset
  (GFS, GEFS, ECMWF, ICON), the fields the catalogue's families use are
  stored and the remaining records are catalogued `available-not-stored`, so
  a field is never hidden, only not fetched.
- **One catalogue** for meteorology, space weather, marine and astronomy
  geometry, organised as families; Sun and Moon geometry are catalogue fields
  of class `derived_here` from the pinned DE442 ephemeris.
- **Raw beside derived.** Sources store what they publish (u and v, or speed
  only); speed and direction from u and v are derived-here and shown beside
  the raw values. A gap (REPS direction) stays `null` and the catalogue
  records it.

## Capabilities

### New Capabilities

- `field-catalogue`: the catalogue, families, comparability rules, phase and
  level conventions, enforcement.

### Modified Capabilities

- `artifact-ingestion`: manifests reference catalogue keys; the
  every-published-field scope and `available-not-stored`.
- `point-evidence-sampling`: responses carry family and comparability, and
  the phase attribute.
- `web-evidence-interface`: non-comparable family members are never drawn on
  one colour ramp or one axis without saying so.

## Impact

- New `registry/fields.py` and `registry/fields.schema.json`; CI check in
  `registry/audit.py`.
- `ingest/manifest.py`: key validation against the catalogue; every adapter's
  `RequiredField` list re-keyed (`total_cloud` splits by producer).
- `api/weather_api/models.py`: `family`, `comparability`, `phase` on field
  responses.
- `web/src/`: family grouping and comparability disclosure.
- No adapter retrieval logic changes; Spec-Impact none outside the experiment.
