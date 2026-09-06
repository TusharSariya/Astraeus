# Tasks

- [x] Enumerate the exact selected product paths and native quantities.
- [x] Add bounded discovery, download, identity, unit, geometry and time checks.
- [x] Preserve DQF/masks and fail closed on unreadable gridded values.
- [x] Prove a current anonymous HTTPS capture and immutable artifact readback.
- [x] Prove actual `LiveStore` sampling for every readable gridded field.
- [x] Pin DMW quality and GLM empty-detection behavior in tests.
- [x] Capture producer-good CODF and COD2KMF cells in a suitable daylight scan,
  and record the bounded fifteen-scan evidence disposition for CPSF.
- [x] Capture every expected band in complete selected DMWF and DMWVF scans.
- [x] Capture every file in a complete selected ten-minute GLM interval.
- [x] Compare stored artifact values, units, times and revisions through the
  actual `/point` and `/layers/{layer_id}/features` HTTP routes.
- [x] Distinguish successful empty vector HTTP readback from missing frames,
  malformed collections and failed reads, preserving empty-observation identity.
- [ ] Accept production source contracts, registration and scheduling (owner only).

Verification:

```text
cd experiments/st-johns-weather-map
make test-api test-registry
openspec validate experimental-goes-abi-glm --strict
uv run --project ../../tools/specs python ../../tools/specs/specctl.py validate
```
