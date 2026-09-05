# Arbitrary-point Focus on the Map

Discussion draft for [Settle arbitrary-point Focus behavior on the Map](https://github.com/TusharSariya/Astraeus/issues/67). The owner selected the Map disclosure, placement, site-selection and coordinate-precision choices below; unsupported-coordinate handling remains pending. No behavior or normative status changes.

## Inherited decisions

- [Shell and Focus](https://github.com/TusharSariya/Astraeus/issues/39#issuecomment-5529784058): one shared point/site and instant, URL persistence, nearest registered site and distance as context, no borrowed horizon.
- [Sky: Horizon instrument](https://github.com/TusharSariya/Astraeus/issues/51#issuecomment-5548244041): only the registered site's horizon, hand-registration disclosure retained; an arbitrary point never borrows a horizon or invented directional cloud/celestial geometry.
- [Map station/point: Layer-led](https://github.com/TusharSariya/Astraeus/issues/58#issuecomment-5548645284): readings/absence below the Map, shared inspector, reference locations distinct from weather reports and model samples.
- [Activity contract](https://github.com/TusharSariya/Astraeus/issues/48#issuecomment-5532460091): point-dependent evidence remains available; site-dependent sector/horizon fields can be null with the reason visible. A point does not become an entirely blocked verdict.

## Current implementation evidence

`weather_api/sites.py` looks up horizons by exact registered site id. `horizon_dependent_null` returns `absence_state: null`, with `no_registered_horizon`; it does not return blocked or aged-out. The older shell resolution's phrase “blocked off-site” must not be copied into the API absence enum without resolving that terminology against the later Activity decision and owning contract.

The shell prototype chooses a registered site through an explicit site control, and a blank-map click sets an arbitrary coordinate. The station prototype keeps airport/reference inspection separate from changing Focus, retains custom-coordinate queries, and shows query coordinate versus model cell/distance in provenance. These are observed prototype behaviors, not independent approvals of every implementation detail.

The subagent found further implementation limits:

- Helper/prototype bounds are 45–50.5 N, 58–46 W, while actual point/astronomy route checks restrict to 46.5–48.5 N, 55–51 W (`app.py:254`, `fixtures.py:42`). The site-registry experiment spec describes any-point evidence-box service. This conflict must be resolved before changing geographic service behavior; the UI must not claim the larger box is served.
- `app.py` and `store.py` do not call the site-horizon helpers; `/point` accepts coordinates but no site id. Helper tests and client registry behavior are not evidence of a wired site-aware point API.
- Shell/station map clicks round coordinates to four decimals before requesting; shell URL serialization can also round typed coordinates. Do not call this lossless exact-coordinate preservation. Query precision versus display precision remains a design/contract choice.
- Registered horizons at Signal Hill, Cape Spear and Quidi Vidi are hand-read and terrain-check status is `not_run`; no surveyed-geometry claim follows from registration.

These findings must feed the paused API discussion and implementation proposal. They do not authorize widening live coverage or relabeling current failures.

## Owner decisions: site and sample geometry

The owner answered “yes, yes” to both choices:

1. **Site geometry on leaving a site.** Remove that site's horizon/sector overlay from the active Focus display when the Focus moves off-site. Keep a compact “No registered horizon at this point” explanation and nearby site references as context. Do not leave old geometry beneath a new point label. Selecting a registered site explicitly can restore that site's registered geometry, subject to its evidence status; no new sector capability is implied.
2. **Model sampling geometry.** Keep the shared Focus as the main marker. Reveal the selected field's sampled model-cell marker and its distance from Focus only while inspecting that field. Label it as a model sample, never a station or a second Focus. If no sample coordinates are returned, show the absence instead of inferring geometry. Different sources may sample different cells; only the selected reading's geometry is highlighted.

## Owner decisions: placement, site selection and precision

The owner answered “yes, yes, yes” to these three choices:

1. A click on empty Map space moves the shared Focus immediately, preserving the current instant, layer state and viewport. Pan/zoom gestures do not move Focus. Keep an explicit recenter action rather than automatically moving the map after each selection.
2. Clicking a registered-site reference opens its information first. A distinct “Use this site” action adopts its registered identity and position as the shared Focus. Selecting a site in the shell's dedicated site picker remains a direct explicit choice. Inspecting station reports or sampled cells never changes Focus implicitly.
3. Preserve query coordinates through requests and URL state without reducing them merely for a shorter label. Round only displayed labels; expose the full stored query coordinates in inspection. A numeric coordinate alone never acquires a nearby site's identity or horizon.

Unsupported-coordinate behavior remains a separate decision because the audit found conflicting service bounds. No choice here authorizes widening the geographic API contract or converting a refusal into evidence.

## Boundaries

Camera placement, phone brief and band math remain deferred. No new site registration, source admission, sector derivation, horizon estimation or production Map implementation. The separate API discussion already selected read-only site/horizon registry exposure; route shapes remain draft.

Classification: no spec impact, evidence gathering and proposed interaction choices only. Spec-Refs: GOV-SPEC-001, GOV-SPEC-002, GOV-SPEC-005. Read-only subagent audit completed. Specctl validation passed (0 errors, 0 warnings); implementation behavior was not changed or tested by this documentation task.


## Next discussion: unsupported coordinates

Proposed, not selected: retain the clicked coordinate as Focus even when the API explicitly refuses geographic coverage. Mark that Focus “Outside supported data area,” show the refusal reason and no point values, and do not snap to a supported point or substitute nearby evidence. Preserve the shared instant and layer selection. Previously returned readings must not appear to describe the new Focus. Distinguish an explicit geographic refusal from network/server failure or an unknown coverage boundary.

A reference basemap or independently valid layer is not itself evidence that point sampling is supported; its existing provenance/disclosure rules still apply. This UX choice does not settle the wider helper-versus-route coverage conflict or authorize expanding service. The alternative is to reject the selection and keep the previous Focus with an input error.
