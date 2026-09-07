# Tasks

- [x] Add a bounded current `AQHI-OBS` point-feature decoder and one-entry coalesced cache.
- [x] Select only actual nearby native station observations at or before the chosen instant with age less than one hour.
- [x] Expose native identity, unknown provider QC, sampled station coordinate/distance, and typed bounded acquisition metadata.
- [x] Compose AQHI only into the default unselected point response and preserve metadata-only expiry failures.
- [x] Replace the retained AQHI catalogue layer with cache-only demand capability metadata and disable scheduled ingestion.
- [x] Verify fixed-body/fixed-clock cache, time, distance, QC, provenance, expiry, API, and no-upstream catalogue behavior.
- [ ] Obtain owner resolution for the separate selected-product companion proposal before implementing that behavior.

## API-first adapter verification (2026-09-07)

- [x] Add explicit `entry(refresh=True)` / `point_field(..., refresh=True)` acquisition; concurrent refreshes coalesce and failed refresh withholds invalidated values.
- [x] Keep expiry anchored to final received byte, including decoder elapsed time; reject payloads whose deadline passes during validation.
- [x] Preserve numeric zero provider QC as native metadata while local QC remains unknown.
- [x] Add a narrow `is_aqhi_observation_companion` identity predicate for the separately authorized selected-model API composition. This helper neither changes selection headers nor relabels observations.

Mapped verification: `api/tests/test_aqhi_query.py` exercises the requirements
“AQHI demand queries retain actual native station observations”, “AQHI cache
and public acquisition metadata are bounded”, and “AQHI default evidence is
independent of retained artifacts”. The explicit refresh and companion helper
remain within the user-authorized API-first experiment; production status and
provider verification status are unchanged.

Live transport/normalization receipt: 2026-09-07T21:06:54.483183Z, canonical
`AQHI-OBS` GetFeatureInfo JSON returned HTTP 200, 2,626 bytes, SHA-256
`dfef946a0fdd35a19b97f669c313683525ea073f58e353f3ba001e6e4a23245e`.
Three native point features had observation time 2026-09-07T21:00:00Z; the
St. John's feature was AQHI 1.5 at 47.5658333333333, -52.7252777777778.
This receipt proves anonymous transport and normalization only; it does not
claim an end-to-end sandboxed live decoder run. macOS rejects the required
locked RLIMIT_AS; the fixed decoder test is explicitly skipped there.

Provider references: [ECCC AQHI documentation](https://eccc-msc.github.io/open-data/msc-data/aqhi/readme_aqhi_en/)
and [GeoMet OGC API documentation](https://eccc-msc.github.io/open-data/msc-geomet/ogc_api_en/).
The settled canonical WMS JSON endpoint remains in use. Native Series could
expose only the actual rows in this current document (maximum 50), under the
same expiry and station identities. No archive, regular hourly sequence,
forecast, or interpolated Series is promised by this implementation.

The live payload also distinguished `properties.location_id` (station identity,
for example `ABEFS`) from `properties.id` (time-bearing feature identity).
The decoder now uses the native location ID for `native_report.station_id` and
retains the full feature ID in `native_metadata.provider_feature_id`. Legacy
fixtures without a location ID retain their original identifier. An explicitly
non-observation `aqhi_type` is rejected; missing type remains accepted under
the existing canonical AQHI-OBS endpoint contract.

Final verification: host targeted tests passed (22 passed, 1 macOS skip).
The exact worktree was then mounted read-only into prepared Linux image
`astraeus-lightning-proof:c88ff83` (`cedb792b595c`) with `--network none`;
`python -m pytest api/tests/test_aqhi_query.py -o addopts='' -p no:cacheprovider -q`
passed all 23 tests, including the genuine bounded child decoder. This closes
the fixed-payload Linux decoder proof; the live receipt remains separately
scoped to transport and normalization. `specctl validate` reported zero errors
and zero warnings.
