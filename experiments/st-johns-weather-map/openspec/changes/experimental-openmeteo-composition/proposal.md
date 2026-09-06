# Experimental Open-Meteo composition and LSA SAF retrieval

## Classification

Experiment. Accepted governance is the only normative authority. Issue 75
permits isolated adapters and verification while the source-specific contracts
remain draft. This change does not register an adapter, schedule retrieval,
promote a source, add scoring, or claim V1 conformance.

## Products and dispositions

- `openmeteo-cams-aod`: retrieve CAMS total AOD at 550 nm through the named
  `cams_global` air-quality path and map only to
  `aerosol_optical_depth_550nm`. Speciation stays unsupported.
- `openmeteo-air-quality-particulates`: retrieve PM2.5, PM10, ozone, NO2, SO2,
  CO and dust for comparison. Normalize every mass concentration from the
  provider's micrograms per cubic metre to catalogue kilograms per cubic metre.
  The source remains catalogued and RAQDPS remains primary.
- `openmeteo-lsa-saf-radiation`: retrieve LSA SAF hour-mean and instantaneous
  shortwave, direct, diffuse, DNI, tilted and terrestrial series from the
  satellite archive under distinct catalogue keys carrying interval identity. The
  Meteosat limb-geometry admission condition remains unsatisfied.

Native CAMS, AQ indices, UV, pollen, forecast beam decompositions, and archive
expansion are excluded.

Spec-Refs: GOV-SPEC-001, GOV-SPEC-002, GOV-SPEC-004, GOV-SPEC-005, GOV-SPEC-006.
