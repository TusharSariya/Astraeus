# Tasks

- [x] Re-enumerate live REPS and GEPS WCS inventory, time axes, source CRS,
  grid offsets and selected units.
- [x] Require EPSG:4326 subsetting and record the 133 by 61 REPS output as
  server-resampled geometry rather than native geometry.
- [x] Decode selected cloud and wind fields for all 21 REPS member identifiers
  while leaving the control identifier null.
- [x] Retain GEPS mean, standard deviation, percentile and threshold
  probability output without fabricating members or recomputing statistics.
- [x] Retain immutable live artifacts plus checksums, numeric/null counts and
  upstream receipts.
- [x] Retain all selected source TIFFs and the exact capability inventory with
  per-response hashes, capture times, and a machine-readable disposition for
  all 1,771 advertised REPS/GEPS coverages; verify offline raw replay through
  the core reader and a test-only HTTP harness.
- [x] Preserve run and valid-time identity on artifact axes and fail closed on
  missing or wrong time, nodata, geometry, and bounded-response violations.
- [x] Account for the 1,197 unselected REPS coverage IDs in follow-up issue 147
  and the 527 unselected GEPS reductions in follow-up issue 148; do not claim
  completion of either advertised family from this bounded selection.
- [x] Verify missing selected reduction, missing member, absent pressure level
  and non-TIFF failure paths without false completion.
- [ ] Production registration, scheduling, registry promotion and V1 status
  remain pending accepted owner decisions.
