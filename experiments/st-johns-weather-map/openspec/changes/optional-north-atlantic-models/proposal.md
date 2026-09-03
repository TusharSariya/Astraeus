# Optional North Atlantic forecast-centre evidence

## Why

The experiment currently gives detailed treatment to HRDPS, RDPS and GFS,
while several independent global centres and two NOAA regional products can
cover the Avalon and its upstream Atlantic evidence box. More models are not
automatically more evidence: products from one centre are correlated, regional
grids can put Newfoundland at a boundary, and several otherwise attractive
feeds are available here only through an intermediary or under restricted
terms.

Live probes on 2026-09-03 settled the first admission question for RAP and the
NAM parent grid. NOAA NOMADS returned binary GRIB2 subsets for total cloud over
the whole declared box, `45.0..50.5 N, 58.0..46.0 W`, from
`rap.t00z.awp130pgrbf00.grib2` and `nam.t00z.awphys00.tm00.grib2`. Their
published inventories also contained surface visibility and pressure-level
temperature, relative humidity and wind. This proves access, field presence
and rectangular coverage for the probed runs; it does not prove edge quality,
forecast skill, stable latency or comparability with ECCC cloud quantities.

RRFS-NA 3 km appears in NOAA's current experimental model graphics, but the
ordinary anonymous production directory did not provide the same stable access
path as RAP and NAM during the probe. It remains a conditional candidate. HRRR
is not a candidate because its published CONUS and Alaska domains do not cover
the evidence box.

The repository already has adapter-backed declarations for ECMWF IFS, IFS ENS,
AIFS, AIFS ENS and DWD ICON Global. It also has live, reprocessed admissions for
Meteo-France ARPEGE World and UK Met Office Global through Open-Meteo. Those
records establish global coverage but preserve the intermediary and licence
limits. No Icelandic, Greenlandic, Nordic, Iberian or Russian regional product
was found with a documented grid covering the box; geographic or institutional
interest is not treated as coverage.

The supporting provider evidence is preserved in
`docs/research/north-atlantic-forecast-model-viability.md`. NVIDIA Earth-2,
Earth2Studio, FourCastNet and ForecastNet are evaluated separately in
`docs/research/nvidia-earth2-cpu-feasibility.md`. That research establishes
Earth2Studio as an inference framework, FourCastNet 1 as a CPU-benchmarkable
generated model, and FourCastNet 3 as a conditional probabilistic generated
family whose full CPU inference and cloud usefulness remain unverified.

Google WeatherNext 3 is evaluated in
`docs/research/google-weathernext-3-validation.md`. Its published 64-member,
hourly global product includes direct cloud-cover fields at 0.1 degrees and
uses live geostationary satellite mosaics, making it a high-priority cloud
candidate. It remains conditional and restricted: access is allowlisted, the
real-time terms constrain raw or retrievable redistribution, anonymous bucket
probes were denied, and no authenticated Avalon read or local skill result
exists.

This change makes the validated families optional evidence. It does not replace
HRDPS, change a score, make any source operational, or admit an unverified
regional grid.

## What Changes

- Add an optional-source eligibility rule based on full-box coverage, required
  field inventory, provenance, legal access and measured operational behavior.
- Admit RAP and NAM parent-grid products as optional NOAA scenarios, subject to
  adapter, fixture, latency, boundary-quality and retrospective-skill gates.
- Admit ECMWF IFS/ENS/AIFS and DWD ICON Global as optional independent-centre
  evidence using their native official feeds.
- Retain ARPEGE World and UKMO Global as optional research comparisons only
  while their available paths are intermediary-reprocessed or restricted.
- Keep RRFS conditional until its operational feed and full-box coverage are
  pinned. Keep HRRR and non-covering regional European products excluded.
- Permit Earth2Studio as an implementation framework and FourCastNet 1/3 as
  generated-here research families only after checkpoint, initializer,
  hardware, runtime and output provenance are recorded. ForecastNet is not a
  weather provider or pretrained atmospheric model and is not admitted.
- Permit WeatherNext 3 to proceed as a credential-required, restricted Google
  ensemble candidate. Preserve its ECMWF HRES input dependency, access surface,
  member/statistic identity, terms class and approximately seven-to-eight-hour
  dissemination latency; require cloud-field comparability and Avalon skill
  validation before contribution.
- Count at most one deterministic representative per forecast centre in any
  centre-level comparison. Ensembles remain labelled families, never extra
  centre votes.
- Require field-key comparability before any numerical cross-model operation;
  displayable disagreement does not imply blendable quantities.

## Capabilities

### Added Capabilities

- `optional-forecast-centres`: declares eligibility, centre-family accounting,
  product tiers, failure behavior and promotion gates for optional NWP evidence.

## Impact

- Specification only. No adapter, scheduler, registry state, score, API or UI
  behavior changes in this change.
- Follow-on implementation may update `registry/source_data.py`, add typed
  adapters and fixtures, and expose labelled optional evidence only after the
  gates in this change pass.
- The V1 provider contract remains unchanged. Promotion into a conforming V1
  path requires an owner-approved change to `ECL26-DATA-001` and mapped
  verification.
- Spec-Impact: none outside this experiment.
