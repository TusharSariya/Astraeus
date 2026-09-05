# Free-source implementation roster

Audited September 5, 2026. This is the human-readable index for
[`free-source-implementation-roster.json`](free-source-implementation-roster.json),
the exhaustive machine-readable routing artifact for the free-provider map.
Research is evidence, not authority. Every row keeps `operational: false`.

## Coverage

The roster contains **288 accounting rows**. This is not a count of unique
sources: registry entries, product/access rows and grouped research leads
overlap deliberately so each audited distinction has a destination.

- **118 registered source IDs**, exactly matching the audit inventory: 14
  ordinary retrieval paths, 95 absent adapters, four unfinished ensembles, two
  nonpublishing placeholders, one disabled adapter, one image proxy and one
  static DE442 path.
- **136 product/access rows** from the three audit appendices: 38 AI and
  commercial, 61 environmental, and 37 geospatial/celestial rows.
- **34 narrative groups** that the appendices name outside tables: 13
  historical environmental groups, seven explicit environmental exclusions,
  six AI/global-model leads, two space-weather groups, one camera group and
  five geospatial/tool/alternative groups.

The narrative rows matter. Omitting them would lose MET Norway, conditional
RRFS, the environmental archive families, space-weather and camera leads, and
recorded dead or out-of-box products. Related products remain grouped exactly
where the audit grouped them. The downstream task must split a group before
implementation when its products have different producers, access paths,
fields, licences or evidence classes.

Every registered row carries the registry's exact field/level declaration,
coverage, authentication and licence blocks. Every research row carries its
exact audit text and line. Both kinds name a GitHub destination, existing
implementation state, free-access disposition, contract gap and the same five
part completion proof: fixture, live upstream retrieval, validated immutable
artifact, Astraeus API readback, and failure/provenance evidence.

## Authority and contract status

Accepted `GOV-SPEC-001`, `GOV-SPEC-002`, `GOV-SPEC-004`, `GOV-SPEC-005`,
`GOV-SPEC-006`, `EVD-PROV-001` and `EVD-MASK-001` govern truthfulness,
authority, traceability, provenance and masks. They do not admit any new
provider product or field.

The experiment's `artifact-ingestion`, `evidence-truth-boundary` and
`source-registry-catalogue` contracts are executable design inputs, but their
source-specific additions remain OpenSpec drafts. Each unimplemented roster
row therefore records a contract gap. Implementation waits for an accepted
product/access/field decision; a research probe or passing fixture cannot fill
that gap. Existing ordinary paths still require live artifact/API/provenance
verification before they can count as completed by this map.

The root worktree contains an uncommitted readiness-container clarification in
the source-admissions change. It is unrelated to roster behavior and is not
copied here. The optional North Atlantic draft also contains a rented-GPU task;
the map's free-only instruction makes that path deferred and unauthorised, so
the roster does not mark it complete.

## Required task splits

The following existing family tickets exceed one bounded implementation
session. Create these children before executing their rows; the final coverage
ticket must be blocked by every child.

| Existing ticket | Required bounded children |
| --- | --- |
| [Implement named Open-Meteo and Bright Sky source retrieval](https://github.com/TusharSariya/Astraeus/issues/78) | “Implement Open-Meteo deterministic atmosphere and Bright Sky MOSMIX”; “Implement Open-Meteo marine and GFS-Wave”; “Implement Open-Meteo composition and LSA SAF”; “Preserve refused and unavailable Open-Meteo paths” |
| [Implement the remaining free cloud and atmospheric satellite products](https://github.com/TusharSariya/Astraeus/issues/85) | “Implement GOES ABI expansion and GLM”; “Implement VIIRS and JPSS cloud products”; “Implement NUCAPS retrieved profiles”; “Evaluate Copernicus, MODIS and GPM satellite paths”; “Resolve native Holyrood radar acquisition” |
| [Implement free aerosol, radiation and fire observations](https://github.com/TusharSariya/Astraeus/issues/86) | “Implement native CAMS and local air-quality products”; “Implement NASA and NOAA aerosol observations”; “Implement AERONET validation observations”; “Implement CWFIS and FIRMS fire products” |
| [Implement free marine, ocean, ice and hydrometric evidence](https://github.com/TusharSariya/Astraeus/issues/87) | “Implement ocean, wave and surge grids”; “Implement SST, ice and satellite-ocean products”; “Implement buoy, profile and water-level observations”; “Implement federal and provincial hydrometric products”; “Implement marine advisories and navigation hazards” |
| [Implement additional free local and aviation observations](https://github.com/TusharSariya/Astraeus/issues/88) | “Implement aviation hazards and reports”; “Implement SWOB partner, WMO and city products”; “Implement community weather and MADIS paths”; “Implement local air-quality observations” |
| [Implement free terrain, light-pollution and site-evidence acquisition](https://github.com/TusharSariya/Astraeus/issues/91) | “Implement terrain and canopy acquisition”; “Implement building and OSM obstruction acquisition”; “Implement night-light and sky-brightness evidence”; “Implement land and site-access records” |
| [Implement free orbital and celestial catalogue acquisitions](https://github.com/TusharSariya/Astraeus/issues/92) | “Implement versioned IERS time inputs and supplementary kernels”; “Implement eclipse and geometry validation catalogues”; “Implement orbital and small-body catalogues”; “Implement meteor, photometry and transient catalogues” |
| [Implement the selected free historical acquisition windows](https://github.com/TusharSariya/Astraeus/issues/94) | “Implement bounded forecast and reanalysis archives”; “Implement bounded environmental observation archives”; “Implement bounded marine and hydrology archives”; “Implement bounded space-weather and optical-aurora archives”; “Implement bounded radiosonde and celestial validation archives” |
| [Implement eligible free published AI forecast products](https://github.com/TusharSariya/Astraeus/issues/96) | “Implement published NOAA AI-GFS and AI-GEFS”; one “Implement bounded AIWP archive for <model and initializer>” child per selected family after the archive decision |

## Explicitly routed edge cases

- Native Holyrood per-site radar is distinct from the implemented national
  composite and is routed to the satellite/radar family for a product-path
  decision before integration.
- IGRA/UWyoming radiosondes and optical aurora archives route to bounded
  historical acquisition. They cannot stand in for a live CYYT sounding or a
  current aurora forecast.
- IERS/time inputs and supplementary kernels route to the celestial catalogue
  ticket. Built-in Skyfield time data and DE442 do not prove those acquisitions.
- MET Norway's named products route to deterministic-provider evaluation; the
  producer and any intermediary transformations must stay explicit.
- Globe at Night and local SQM/photometer observations route to the
  light-pollution task as observations, distinct from Falchi modelled
  brightness and VIIRS observed radiance.

## Verification

Run from repository root:

```text
python3 tools/specs/build_free_source_roster.py
uv run --project tools/specs python tools/specs/specctl.py validate
```

`build_free_source_roster.py --write` regenerates registered rows from the
audited 118-ID JSON and the current registry's field/access declarations, and
extracts the appendix table rows. Validation fails on a missing/duplicate
registry ID, missing research group, unknown target ticket, missing required
column, duplicate roster ID or any `operational` value other than false. It
also freezes SHA-256 digests for all four audit inputs; a prose edit fails and
forces an explicit routing review instead of silently changing a line-number
classification.

Spec-Impact: none. This artifact routes audited work and records specification
gaps; it changes no runtime, source admission, contract or normative status.
