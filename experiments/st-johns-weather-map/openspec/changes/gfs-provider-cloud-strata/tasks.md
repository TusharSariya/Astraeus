Owned: `ingest/adapters/noaa_s3.py`, `api/weather_api/store.py`
(`FIELD_BY_VARIABLE` additions only), `api/tests/test_adapter_noaa_s3.py`,
`docs/live-stack-report.md`. Not touched: `web/`, `registry/`, other adapters,
`api/weather_api/models.py`, `ingest/registry.py`.

## 1. Bounded selection and per-message decode

- [x] 1.1 Replace the param-only `GFS_PARAMS` selection with
      `GFS_IDX_SELECTORS`, exact (parameter, level) pairs plus an
      instantaneous-forecast filter; keep the 25 MB per-lead ceiling.
      Verify: `cd api && uv run pytest tests/test_adapter_noaa_s3.py`
- [x] 1.2 Decode one shortName per cfgrib open, `strip_message_scalars` each
      variable, assemble a flat step dataset; a fetched-but-unreadable
      message is a decode error, an unpublished optional message is not.
- [x] 1.3 Stop fetching APCP; keep precipitation undeclared in the manifest
      until its accumulation semantics are pinned.

## 2. Provider-declared strata

- [x] 2.1 Add `lcc`/`mcc`/`hcc` to `GFS_VAR_MAP` as
      `cloud_low`/`cloud_middle`/`cloud_high` and declare them optional
      (percent) in `GFS_MANIFEST`.
- [x] 2.2 Map the three canonical names in `FIELD_BY_VARIABLE`; leave
      `UNAVAILABLE_POINT_FIELDS` and the derivation prohibition untouched.

## 3. Evidence chain

- [x] 3.1 Fixture tests: selection excludes isobaric and time-averaged
      messages and stays under the ceiling against a full-size inventory;
      strata decode, rename and units; message-scalar assembly regression.
- [x] 3.2 Live smoke, one lead hour (gfs.20260830/12 f008): 10,443,974 bytes
      across 6 ranges; all eleven fields decode with canonical units.
- [x] 3.3 Worker run publishes; API `/point` readback shows GFS fields
      including strata with `source_id: noaa-gfs`; BLEND and `/timeline`
      list noaa-gfs. Recorded in `docs/live-stack-report.md`.
