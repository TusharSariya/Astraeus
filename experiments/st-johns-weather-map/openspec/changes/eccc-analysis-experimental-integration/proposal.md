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

## Review status and bounded work

This is a contract/transport scaffold, not completed source acquisition.
Independent review found only two JSON retrieval summaries without retained
live artifacts or product-specific HTTP proof. The family remains open and
blocked by these acquisition tickets:

- [Native RAQDPS and RDAQA fields](https://github.com/TusharSariya/Astraeus/issues/133).
- [HRDPA and HREPA precipitation analyses](https://github.com/TusharSariya/Astraeus/issues/134).
- [HRDLPS and CaLDAS land analyses](https://github.com/TusharSariya/Astraeus/issues/135).
- [Native RDPA geometry and units](https://github.com/TusharSariya/Astraeus/issues/136).
- [Public alerts, outlooks and nowcasting](https://github.com/TusharSariya/Astraeus/issues/137).

CWFIS/FIRMS and wildfire hotspots remain owned by the existing fire-source
ticket, not duplicated by the public-hazard child. Standalone FireWork stays
superseded. An unsupported path in this scaffold is not proof that the
producer has no public data.

Spec-Impact: experiment. Accepted governance authority: GOV-SPEC-001,
GOV-SPEC-002, GOV-SPEC-004, GOV-SPEC-005, GOV-SPEC-006.
