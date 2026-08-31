# HRDPS and RDPS total cloud as rendered white-alpha layers

## Why

The owner wants every cloud-cover map layer drawn as white with opacity
proportional to cloud fraction (0 percent invisible, 100 percent opaque
white). The GFS strata and the GOES cloud mask already render exactly that
way. The only total-cloud imagery for the ECCC models, however, is the
`geomet-live-hrdps-nt` live proxy, whose pixels ECCC renders as an opaque
dark-grey-to-white ramp - readable as "1 percent cloud paints the map black".

What evidence exists (probed live 2026-08-31): ECCC's GetCapabilities for
`HRDPS.CONTINENTAL_NT` advertises exactly three styles - `CLOUD` (the
default; opaque grey ramp), `CLOUD-50` (transparent below 50 percent, opaque
grey above) and `CloudCover_50-100Pct_Dis` (three discrete opaque blues).
None is a transparency ramp, and recolouring ECCC's pixels client-side is
barred by geomet-wms-access ("colour ramps are retrieved, never invented").
So the honest route is the one the GFS strata already took: render the
stored grid here, under the declared `grid-cloud-alpha-v1` colormap.

That required unblocking the data. The registered Datamart adapters withheld
`total_cloud` because CWAO stamps `typeOfSecondFixedSurface=255` where
ecCodes' `tcc` concept requires 8, so the decoder declares name and units
`unknown` (verified live 2026-08-30, ecCodes 2.48.0). The withholding was
explicitly "pending the owner's decision". **Owner decision 2026-08-31:
publish from the message's own coded WMO keys** - discipline 0, category 6,
number 1 is WMO code table 4.2's "Total cloud cover" in percent, and those
keys are retrieved facts in the message itself, unlike the 0-100 value
range, which is only an inference. The declaration and its basis are
recorded in the variable's attrs; a message whose keys do not match stays
refused.

One more retrieved fact shapes the design: HRDPS and RDPS are published on
rotated lat/lon grids (2-D coordinates over anonymous y/x dims - a recorded
hard-won fact), so the rectilinear containing-cell renderer cannot draw
them. A curvilinear nearest-published-cell method is added, mirroring the
`curvilinear_nearest_cell` rule `/point` sampling already discloses.

Unverified until the next worker run: the live HRDPS/RDPS artifacts do not
yet carry `total_cloud`, so the two layers appear only after an ingest cycle
completes under the new maps. The layer index fails closed (absent layer,
notice for a missing variable) until then.

Classification: Experiment, Spec-Impact: none. `docs/specv1` is untouched.

## What Changes

- **`ingest/grib.py`**: `open_grib` accepts `read_keys` (extra ecCodes keys
  exposed as `GRIB_*` attrs); `declare_wmo_total_cloud` names an
  ecCodes-`unknown` field `percent` only when the coded keys are exactly
  WMO 0/6/1 with first fixed surface 1, recording `original_units:
  "unknown"` and a `units_basis` sentence; `normalize_units` keeps an
  existing `original_units` record instead of clobbering it.
- **`ingest/adapters/eccc_datamart.py`**: `total_cloud` joins `HRDPS_VARS`
  (`TCDC`/`Sfc`) and `RDPS_VARS` (`TotalCloudCover`/`Sfc`) - not
  `GDPS_VARS`; the fetch path requests the identity keys for that field and
  refuses it (`undeclared_units` decode error) when the declaration does
  not apply. The withholding comment now records the owner decision.
- **`api/weather_api/grids.py`**: two new `RenderedGridSpec` entries
  (`eccc-hrdps-surface-total-cloud`, `eccc-rdps-surface-total-cloud`);
  `sample_field_curvilinear` (nearest published cell centre within half a
  cell diagonal, scipy cKDTree, equirectangular scaling as in `store.py`);
  `rasterize` dispatches on coordinate dimensionality; render semantics,
  derivation and derivation-version become per-method and ride the response
  as `X-Weather-Sample-Method` et al.; `grid_semantics` reads product and
  native resolution from the artifact's own provenance instead of asserting
  GFS facts; the served legend composites the alpha ramp over mid grey so
  the graphic is visible (the mapping is unchanged and the headers say so).
- **`api/pyproject.toml`**: `scipy` becomes a direct pinned dependency (it
  was already in the locked tree via metpy).
- **Web**: no code change - the interface is generic over `/layers` and the
  `rendered_grid` group; the new layers inherit the drawer, legend caption,
  opacity slider, frame fallback and the display-interpolation toggle.

## Non-goals

- The `geomet-live-hrdps-nt` proxy keeps ECCC's default style and provider
  legend (owner decision 2026-08-31: keep both layers).
- GDPS total cloud stays unpublished (no owner ask).
- GFS strata and GOES mask tiles are unchanged; only the shared cloud
  legend graphic gains the backdrop.
