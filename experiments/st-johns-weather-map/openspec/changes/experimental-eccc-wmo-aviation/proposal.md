# Experimental ECCC and WMO aviation native acquisition

## Scope

Retain bounded native artifacts from the currently observed official Canadian
aviation paths: the CWAO `LTCN38` IWXXM TAF bulletin containing CYYT, Gander FIR
`CZQX` IWXXM SIGMET, and the CWAO `FDCN01/02/03` winds and temperatures aloft
bulletin family containing YYT and the explicit `WPM 47N 49W` point.

IWXXM METAR/SPECI are documented but absent from the live product root. AIRMET
has no live `CZQX` directory. These products remain visible as observed-absent
or geographically unavailable rather than being substituted. Existing AWC
METAR/TAF JSON and raw aircraft tracking are excluded.

Every selected artifact remains nonpublishable until an owner-approved native
field, units, time, quality, geography, rights, manifest, and API contract
exists.

Spec-Impact: experiment; no normative status transition.
Spec-Refs: GOV-SPEC-001, GOV-SPEC-002, GOV-SPEC-004, GOV-SPEC-005, GOV-SPEC-006
