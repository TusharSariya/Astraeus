# OSTIA native chunk delivery correction

Classification: isolated experiment; GOV-SPEC-001/004/005/006.
Owning contract: [current-sst-analysis-inputs](../../../openspec/changes/current-sst-analysis-inputs/specs/artifact-ingestion/spec.md),
particularly current SST identity/quality and bounded anonymous retrieval.

The bounded next-source audit found existing RAQDPS/RDAQA WCS capture with
explicitly deferred canonical gas/analysis semantics, existing named Open-Meteo
surface/profile capture, and working OSTIA/OISST capture adapters. The selected
local gap was OSTIA's refusal when the required evidence box crossed native
chunk boundaries. No new source, catalogue mapping, API route, activation or
scientific inference was needed.

OSTIA now enumerates only intersecting chunks for each of its three required
fields, copies their unmodified indexed cells into the evidence-box array,
and applies the existing native fill, scaling, uncertainty and water-mask
rules. A maximum of sixteen chunks per field bounds changed provider layouts;
the existing 16 MiB per-chunk transport ceiling and shared polite client remain
in force. Each chunk retains a distinct temporary filename and source URL.
A missing intersecting chunk aborts before writing a normalized artifact.

Verification from the experiment directory:

- `uv run --project api pytest -q api/tests/test_adapter_sst_analysis.py`:
  **14 passed**. Fixed MockTransport bodies prove one-chunk and four-chunk
  layouts produce the same exact native coordinate/value/mask/error crop,
  request each required chunk once, refuse missing chunks without writing a
  partial artifact, and stop before field transport when the chunk count
  exceeds its bound. Existing OISST tests also pass.
- `openspec validate current-sst-analysis-inputs --strict`: valid.
- Repository root: `uv run --project tools/specs python tools/specs/specctl.py validate`:
  zero errors and warnings.

No provider requests occurred. Existing local netCDF4/NumPy deprecation and
optional ecCodes loading warnings do not affect the SST fixture results.
This proves source-local artifact delivery under the existing contract; it
adds no public source-demand route or source-admission authority. Both SST
sources remain catalogued and unschedulable, with no operational claim.
