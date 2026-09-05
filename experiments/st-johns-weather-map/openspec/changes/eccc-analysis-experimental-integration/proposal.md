# Change: prove selected ECCC analysis access paths

## Why

Issue 80 groups air-quality forecasts and analyses, precipitation analyses,
land products, hotspots, nowcasting, and public hazards. They do not share one
time or payload model. Treating the group like an RDPS forecast would invent
lead times and quality semantics.

## What changes

- Declare small selected-field contracts for RAQDPS, RDAQA, HRDPA, RDPA,
  HREPA, HRDLPS, and CaLDAS over their exact GeoMet WCS coverage identities.
- Reuse the corrected numeric WCS transport while assigning each product its
  own grid identity, cadence, time meaning, and unknown quality state.
- Retain upstream TIFF bytes beside deterministic Zarr output and record both
  digests plus finite/null counts.
- Record hotspots, integrated nowcasting, CAP alerts, thunderstorm outlooks,
  hurricane products, and retired standalone FireWork as unavailable through
  this adapter until separate typed contracts are selected.

No registry or scheduler entry is enabled. Every contract and artifact remains
`operational: false`.

Spec-Impact: experiment. Accepted governance authority: GOV-SPEC-001,
GOV-SPEC-002, GOV-SPEC-004, GOV-SPEC-005, GOV-SPEC-006.

