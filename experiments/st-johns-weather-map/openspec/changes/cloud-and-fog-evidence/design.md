## Context

Three retrieval paths already exist and each stops one step short of the reader.

- **GRIB.** `ingest/adapters/eccc_datamart.py` subsets HRDPS/RDPS by `.idx` and
  decodes through cfgrib on Debian bookworm's ecCodes 2.28.0. Live headers of
  the total-cloud messages are centre 54 (CWAO), tables 4, template 4.0,
  discipline 0 / category 6 / number 1, `typeOfFirstFixedSurface=1`,
  `typeOfSecondFixedSurface=255`. ecCodes' `tcc` concept requires second surface
  8 in every version inspected and there is no `localConcepts/cwao`, so the
  message decodes as `paramId=0`, units `unknown` today and will after upgrade.
- **METAR/TAF.** AWC JSON carries `clouds: [{cover, base}]` with base in feet AGL
  and `wxString` (null when absent). `awc.py` keeps one maximum percent, drops
  bases and never reads `wxString`. `ingest/meteorology.fog_state(
  provider_diagnostic, visibility_m, fog_code)` with `provider_diagnostic=None`
  can return only `evidence_present` or `unknown`.
- **WEonG.** `HRDPS-WEonG_2.5km_{Liquid,Ice}FogVisibility` and
  `RDPS-WEonG_10km_{Liquid,Ice}FogVisibility` answer GetMap and GetLegendGraphic
  200 image/png. The RDPS titles end `[m] [experimental]`; `parse_title_units`
  is anchored to the last bracket and reads `experimental` as the unit.

`/point` today emits only `FIELD_BY_VARIABLE` variables, coerces every value to
`float`, and `Sample.value` is `float | None`; `EvidenceField.value` already
allows `str`. The proxied-layer list is `FORECAST_LAYERS`, and
`app._proxied_forecast_layers` hard-codes `product="HRDPS"`.

## Goals / Non-Goals

**Goals:**
- Publish what METAR/TAF actually report about cloud and fog, per layer, with
  the provider's own vocabulary and units carried in provenance.
- Make `fog_state` derivable from retrieved evidence and say what it was derived
  from, so `unknown` means "no present-weather group was read" and nothing else.
- Establish, with GRIB keys recorded verbatim, why total cloud is withheld, so
  the owner can decide on the evidence rather than on a version number.
- Offer the WEonG fog diagnostics as imagery, labelled as post-processed
  diagnostics and, where ECCC says so, as experimental.

**Non-Goals:**
- Any low/middle/high étage bucketing of layers. The WMO thresholds are noted in
  the proposal only, for the owner.
- Publishing `total_cloud` from WMO 0/6/1 keys or a local definitions overlay.
- Using WEonG fog visibility as a `provider_diagnostic` for `fog_state`.
- A registry record for RDPS WEonG, or any change to `registry/source_data.py`,
  `ingest/meteorology.py` or `models.py`.
- Resolving the duplicate TAF TEMPO/BECMG valid-time stamps.

## Decisions

**The parameter concept is the gate, not the version.** A GRIB message that the
decoder cannot name is not published under a name the adapter assumes it
deserves. WP1 upgrades ecCodes cleanly (the wheel is one dependency extra and a
Dockerfile line), runs the smoke, and expects `unknown` to persist. The value of
the work package is the recorded finding and the corrected comment, not a new
field. Alternative considered: ship a local `localConcepts/cwao` overlay mapping
0/6/1 with second surface 255 to `tcc`. Rejected here because it is the adapter
asserting what the message means; it is gate 1 for the owner.

**Flat per-slot variables, CF flag coding, provider order.** Cloud layers are
published as `cloud_layer_{n}_cover_code` / `_cover` / `_base`, n = 1..6, rather
than a ragged layer dimension, because every consumer downstream (`validate_run`,
`_sample_dataset`, the point response) is built for `(time, 1, 1)` arrays and a
ragged dimension would need new sampling semantics. The cover code is a CF
flag-coded integer with `flag_values` / `flag_meanings`, so the vocabulary
(`SKC CLR NSC FEW SCT BKN OVC VV OVX CAVOK`) travels with the data. A seventh
layer is a loud `cloud_layers_truncated` decode error that fails QC for the run,
not a silent drop; six is the most any AWC record observed carries, and if that
assumption is wrong the run says so.

**Meaning is resolved at the point sampler, once.** `_sample_dataset` maps a
flag value to its meaning string when the variable's attrs carry the CF flag
pair, and returns `None` for a value outside the table. `Sample.value` widens to
`float | str | None`. This keeps the artifact numeric and the API readable
without a parallel lookup table in the client. The raw `weather_*_code`
variables are sampled but never served (`FOG_INPUTS`, skipped alongside
`DERIVATION_INPUTS`), because a bare `1` labelled "fog code" invites the client
to interpret it.

**Fog vocabulary follows WMO No. 306 FM 15 table 4678.** `FG` (including
`FZFG`, `MIFG`, `BCFG`, `PRFG`, with or without intensity) is fog; `VCFG` is
vicinity fog; `BR` is mist and is not fog; `HZ`, `FU`, `DU`, `SA`, `VA` are not
fog. Nothing else in the group is interpreted. `fog_state` is derived with
`fog_code = fog OR fog_vicinity` and `provider_diagnostic=None`, so its live
values are `evidence_present` or `unknown` only, and the derivation string says
in words that `not_indicated` cannot be produced. Counting `VCFG` as fog
evidence is the default and is gate 3 for the owner.

**A null `wxString` is a retrieved absence, not a gap.** The adapter writes `0`
for all three codes and an empty string into `present_weather_strings`. Only a
step that was never retrieved carries NaN, and the sampler turns NaN into
`unknown`. This is the distinction the governing rule requires: "the observer
reported no weather" is a reading; "we did not read the observer" is not.

**`[experimental]` is a disclosure, not a unit.** `parse_title_units` strips the
suffix before the unit regex and `is_experimental(title)` reports it. The layer
title is prefixed `[experimental]`, `ForecastCoverage.experimental` is set, and
the index carries a notice naming the layer and quoting ECCC. Showing the layer
at all is gate 5; the default is shown and labelled.

**WEonG layers declare what they are.** `ForecastLayerSpec` gains `product` and
`semantics`, so the four fog layers say `HRDPS-WEonG` / `RDPS-WEonG` and carry
text stating they are a post-processed diagnostic (visibility through fog,
metres), not a raw model field, that they are display evidence only, are not
sampled by `/point`, and do not feed `fog_state`. HRDPS-WEonG names its registry
record `eccc-hrdps-weg-prognos`; RDPS-WEonG states it has none.

## Risks / Trade-offs

**Adapter version bumps invalidate nothing but must be visible.**
`awc-metar-v2` / `awc-taf-v2` appear in provenance; older artifacts keep their
v1 stamp and simply carry no layer variables, which the sampler reports as
absent. No migration.

**Upstream budget headroom shrinks.** 13 proxied layers need 13 capability
fetches on a cold cache against a per-request ceiling of 16. It fits, but a
future addition will not. This change keeps the ceiling and notes the headroom
rather than raising a politeness limit against a free public service.

**A near-empty WEonG tile is ambiguous until seen at a foggy hour.** The probe
returned 390 B at 15Z with no fog forecast. That is a reading under the existing
transparent-tile rule, but it is not proof of a rendered field; the open
question is recorded in `tasks.md` and the layer is described accordingly.

**TAF duplicate stamps remain.** TEMPO/BECMG periods share `valid_time` values
and `_nearest_time_index` picks one arbitrarily. Cloud layers and fog codes
inherit that existing behaviour; fixing it is out of scope and recorded as an
open question rather than being papered over.
