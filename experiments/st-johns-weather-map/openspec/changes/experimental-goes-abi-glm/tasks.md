# Tasks

- [x] Enumerate the exact selected product paths and native quantities.
- [x] Add bounded discovery, download, identity, unit, geometry and time checks.
- [x] Preserve DQF/masks and fail closed on unreadable gridded values.
- [x] Prove a current anonymous HTTPS capture and immutable artifact readback.
- [x] Prove actual `LiveStore` sampling for every readable gridded field.
- [x] Pin DMW quality and GLM empty-detection behavior in tests.
- [ ] Capture a scan with producer-good CODF, COD2KMF and CPSF pixels in the
  evidence box; the September 5 capture correctly returns them unavailable.
- [ ] Accept production source contracts, registration and scheduling (owner only).

Verification:

```text
cd experiments/st-johns-weather-map
make test-api test-registry
openspec validate experimental-goes-abi-glm --strict
uv run --project ../../tools/specs python ../../tools/specs/specctl.py validate
```
