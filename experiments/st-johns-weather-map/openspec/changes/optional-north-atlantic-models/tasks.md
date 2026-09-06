# Tasks

## 1. Evidence and registry declarations

- [ ] 1.1 Record RAP three-cycle full-box and upstream-transect probes, exact
      product inventory, grid geometry, licence and seven-day latency sample.
      Verify: evidence contains HTTP status, content signature, byte count,
      cycle, file, bounds and selected messages for every probe.
- [ ] 1.2 Expand `noaa-rap` from its current aerosol-only catalogue description
      only after cloud, visibility and upper-air semantics are pinned.
      Verify: `python3 registry/audit.py` and registry unit tests pass.
- [ ] 1.3 Record NAM three-cycle full-box and upstream-transect probes and clear
      the existing admission condition only if every required check passes.
      Verify: `python3 registry/audit.py` reports the condition satisfied and
      the evidence names the parent grid rather than a non-covering nest.
- [ ] 1.4 Record RRFS as conditional, with no endpoint or field promise, until
      an official operational distribution is stable and probeable.
      Verify: the registry audit refuses it as schedulable while conditional.
- [ ] 1.5 Record HRRR and each investigated non-covering regional European model
      as excluded or catalogued with its exact domain evidence, so absence is
      not later mistaken for an oversight.
      Verify: every decision names a primary producer reference and probe date.

## 2. Native independent centres

- [ ] 2.1 Run live adapter smoke, fixture and provenance checks for ECMWF IFS
      and DWD ICON Global over the evidence box.
      Verify: exact adapter tests plus `python3 registry/audit.py` pass.
- [ ] 2.2 Bound IFS ENS retrieval to the approved fields, members, cycles and
      horizon without reducing members into a synthetic mean.
      Verify: ensemble fixture tests preserve member and control identities.
- [ ] 2.3 Evaluate whether AIFS adds cloud-relevant evidence; do not admit it
      merely because its feed is available.
      Verify: the evaluation names available and missing cloud variables.
- [ ] 2.4 Identify and review native official ARPEGE World and UKMO Global data
      paths. Until then keep their Open-Meteo records reprocessed, non-primary,
      and barred from derivation inputs; preserve UKMO's restricted terms.
      Verify: registry delivery-kind and restricted-terms tests pass.

## 3. Scientific validation

- [ ] 3.1 Build retrospective cases for marine fog/stratus, frontal cloud and
      clear controls using GOES DQF-passing cloud evidence and SWOB/METAR.
      Verify: cases cover at least two events of each class and do not use one
      forecast model as truth for another.
- [ ] 3.2 Report per-source availability, bias/error by comparable field,
      timing error, rank contribution and failure rate. Keep non-comparable
      cloud definitions separate.
      Verify: field-catalogue comparability tests pass for every computed pair.
- [ ] 3.3 Select at most one deterministic representative per centre and retain
      every other product as a labelled scenario or ensemble family.
      Verify: a test fixture containing GFS, RAP, NAM and GEFS produces one NOAA
      centre contribution, not four.

## 4. Promotion gates

- [ ] 4.1 Add typed adapters and completeness manifests only for candidates
      that pass sections 1 to 3.
      Verify: fixture, live smoke, artifact validation, API readback and
      provenance checks all pass with exact commands recorded.
- [ ] 4.2 Seek owner approval before changing registry state or the V1 provider
      contract. No task in this change marks a source operational.
      Verify: approval evidence and Spec-Refs are present before promotion.

## 5. NVIDIA Earth-2 generated-model research

- [ ] 5.1 Benchmark one full FourCastNet 1 six-hour step on CPU and record
      hardware, software, checkpoint and input digests, wall time, peak RSS and
      output checksum.
      Verify: the run uses the real checkpoint and global input, not a dummy
      wrapper, and its evidence is reproducible.
- [ ] 5.2 Load the full FourCastNet 3 checkpoint on CPU and then attempt one
      member and one six-hour step under explicit time and memory bounds.
      Verify: success, timeout, out-of-memory and unsupported-operation are all
      reported as measured outcomes without relabelling a load test as inference.
- [ ] 5.3 If CPU inference is impractical, repeat the identical FCN3 case on a
      named rented GPU and measure actual peak VRAM; do not infer a hard minimum
      from Earth2Studio's recommended-memory badge.
      Verify: the initializer, checkpoint, precision, seed and output request
      are identical or their differences are declared.
- [ ] 5.4 Register Earth2Studio only as an inference framework and FourCastNet
      outputs only as generated-here evidence. Do not register ForecastNet as a
      provider.
      Verify: provenance names initializer, checkpoint digest, framework,
      precision, device, member/seed and transformations.

## 6. Google WeatherNext 3

- [ ] 6.1 Obtain owner review of the current real-time terms, including raw,
      retrievable and non-retrievable output boundaries, attribution, deletion,
      downstream notification and potential fee changes.
      Verify: a dated terms snapshot and owner decision are linked before use.
- [ ] 6.2 Establish allowlisted access through the approved secret workflow;
      do not embed credentials or assume anonymous access.
      Verify: credential handling passes repository secret-safety checks.
- [ ] 6.3 Probe the selected GCS, BigQuery or Earth Engine surface for a full
      evidence-box sample and pin dimensions, coordinates, members, units,
      missing values, product version and exact cloud variables.
      Verify: an authenticated live fixture covers every corner and upstream
      sector without treating statistics as ensemble members.
- [ ] 6.4 Measure publication latency, completeness and retrieval cost across at
      least seven days, separating initialization, publication and retrieval.
      Verify: main and interim cycles are reported separately with failures.
- [ ] 6.5 Register WeatherNext cloud keys and explicitly record the absence of
      documented fog, visibility, ceiling, cloud-base and cloud-top products.
      Verify: comparability tests reject undeclared cross-model operations.
- [ ] 6.6 Evaluate at least two Avalon cases each for fog/stratus, frontal cloud
      and clear controls against GOES DQF-passing evidence and SWOB/METAR.
      Verify: the report includes availability, timing, calibration/error and
      failure behavior and does not use another forecast model as truth.
