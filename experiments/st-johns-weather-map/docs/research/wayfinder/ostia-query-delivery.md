# Isolated OSTIA daily analysis query delivery

Classification: experiment. No V1 admission, scheduler registration, public
route, shared-schema changes, fog calculation or forecast applicability.

Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-005, GOV-SPEC-006;
experiment contracts `current-sst-analysis-inputs/specs/artifact-ingestion`
(Current SST analyses preserve producer identity and quality; Current SST
retrieval is bounded and anonymous) and
`timestamp-demand-query-cache/specs/demand-query-cache` (timestamp identity,
coalescing, fixed cache expiry and evidence semantics).

## Root-owned wiring proposal

- Source: `metoffice-ostia-sst`; product token proposal: `OSTIA SST`.
- Helper: `weather_api.ostia_query.OSTIAQueryService.point_fields(latitude,
  longitude, selected, refresh=False)`; retain one service instance.
- Three fields: `sea_surface_temperature` (degC, native kelvin),
  `sea_surface_temperature_uncertainty` (degC difference, native kelvin), and
  `sea_surface_temperature_mask` (native flag).
- Native identity: `METOFFICE-GLO-SST-L4-NRT-OBS-SST-V2`, retrieved Level-4
  daily foundation SST analysis. `run_time=null`, actual analysis in
  `valid_time`, actual retrieval time and immutable adapter revision retained.
- Geography: existing contract's fixed 45.0–50.5 N, -58.0–-46.0 E native crop.
  Uses existing containing-cell index implementation; no interpolation.
- Availability: only latest published exact analysis timestamp accepted by
  adapter discovery. No daily carry-forward or historical archive lookup.
  `OSTIAUnavailable` means unsupported/unavailable selection. Invalid
  coordinates/naive timestamps raise `ValueError` before transport.
- Evidence: `retrieved`, `published_cell`, `available-not-stored`,
  `operational=false`, `source_display_primary=false`. No Series advertised.
- Public registration remains an integration decision; this file does not
  authorize production admission or alter the existing capture-only gate.

## Bounds and verification

One in-flight acquisition, identical misses coalesced, one crop cache shared
across points. Cache retains at most 8 MiB encoded JSON, fixed 300-second TTL
from acquisition start; failed refresh retains only an unexpired old entry.
Default acquisition owns a 90-second Linux process, 2 GiB address space,
1 GiB per-file limit, bounded stdin/stdout/stderr. Existing polite adapter
ceilings remain 2 MiB metadata, 16 MiB compressed chunk, 16 intersecting chunks
per field. Before native field retrieval, query preflight rejects declared
chunks larger than 64 MiB decoded. Crop output is at most 100,000 cells.
Native water/land/sea-ice flags and missing mask sentinel survive; sea ice is
not converted into another scientific variable. All required fields pass the
existing adapter completeness/QC gate before caching.

Offline Linux tests exercise the actual compressed native adapter and the
actual bounded worker via a mocked PoliteClient, with Docker networking off.
No live provider requests, credentials, global SST download or remote writes.

Exact command (worktree mount path may be changed by integrator):

```sh
docker run --rm --network none --memory 3g \
  -v /private/tmp/astraeus-api-first-sst-delivery/experiments/st-johns-weather-map:/work:ro \
  -e PYTHONPATH=/work/api:/work:/work/api/tests -w /work \
  astraeus-lightning-proof:c88ff83 python -m pytest \
  api/tests/test_ostia_query.py api/tests/test_adapter_sst_analysis.py -q -p no:cacheprovider
uv run --project tools/specs python tools/specs/specctl.py validate
```

Mapped checks cover native units/date, land and fill nulls, water+sea-ice flag,
shared crop reuse, defensive copy, exact-time refusal before field payload,
failed-refresh and expiry semantics, duplicate-miss coalescing, malformed
point preflight, oversized native chunk preflight, and actual Linux child.
Residual: no current live-access proof, public API/client integration or
source-specific timeline discovery. NOAA OISST retains its existing capture
adapter and is not added to the query service.
