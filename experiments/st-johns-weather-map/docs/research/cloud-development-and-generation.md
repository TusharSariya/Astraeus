# Cloud development: can we draw what advection cannot?

Research pass of 2026-09-01, commissioned after the owner observed that every
interpolation method "looks like a crossfade rather than actually generating
new data" on ECCC-HRDPS total cloud, and asked whether wind, humidity and
pressure could predict cloud formation, or whether machine learning is
required.

Three literature agents plus direct measurement against this stack's own live
artifacts. **Every measurement in the "Measured here" sections was run against
the live store in this repository and is reproducible; every literature claim
carries its citation.** Where an agent's claim was wrong and I caught it, the
correction is recorded rather than quietly dropped - two are below.

Companion to `cloud-motion-interpolation.md`, which covers the motion side.

---

## 0. The headline, before the detail

1. **We were solving the wrong problem's literature.** This is not nowcasting.
   Nowcasting extrapolates from one-sided information. We hold BOTH endpoints,
   which meteorology calls **advection correction** or **morphing**, and which
   Shapiro et al. (2010) state plainly is *"an analysis problem"*, not a
   forecast one. The pySTEPS cascade machinery (S-PROG, STEPS, ANVIL) exists to
   model the *unpredictable* residual under one-sided information. Porting it
   would be a mistake.
2. **The growth/decay residual is directly computable, not learned and not
   diagnosed.** With both endpoints known, everything advection fails to
   explain is `s ≈ warp(I₁, backward) − I₀`. NowcastNet learns this field;
   Tatsubori et al. compute it as a third flow channel. We can measure it
   exactly. This is a much stronger position than diagnosing cloud from
   humidity, and it was not the design we started from.
3. **The development test is actively harmful, measured three ways.** Removing
   it entirely improves reconstruction of cells that grew, cells that decayed,
   AND sharpness. See §5.
4. **omega is a second-order effect at hourly spacing.** 2-8% relative RH
   change per hour at synoptic values. Real, but not the lever.
5. **Nobody in the literature uses omega to inform temporal interpolation of
   cloud.** Searched hard; genuine negative result. The slot exists
   (NowcastNet's `s`), but it is always learned, never diagnosed.

---

## 1. What we actually have (verified live, 2026-09-01)

Checked directly against Datamart and the NOAA S3 `.idx`, not taken from an
agent's report.

### ECCC HRDPS / RDPS

| Field | Available | Token (verified) |
| --- | --- | --- |
| Total cloud | yes | `TCDC_Sfc` / `TotalCloudCover_Sfc` |
| **Low/mid/high cloud strata** | **NO** | - |
| **Cloud water path (column)** | **yes, not ingested** | `CWAT_EATM` / `CloudWater_EAtm` |
| RH on pressure levels | yes, 28 levels | `RH_ISBL_0700` / `RelativeHumidity_IsbL-0700` |
| Temperature on levels | yes | `TMP_ISBL_0700` / **`AirTemp_IsbL-0700`** |
| Specific humidity | yes | `SPFH_ISBL` |
| Vertical velocity | yes (ingested) | `VVEL_ISBL` / `VerticalVelocity_IsbL-` |
| Condensate on levels | **NO** | - |

The complete ECCC cloud vocabulary across HRDPS/RDPS/GDPS/CAPS is `TCDC`,
`CWAT`, `SKSTATE`, `VISLFG`/`VISIFG`, `SEEI`/`TRSP`. There is no stratified
cloud product on Datamart, in GeoMet's 8401 WMS layers, or in the OGC-API
collections.

### NOAA GFS `pgrb2.0p25` (counted from a live `.idx`)

```
CLMR  22 isobaric levels      ICMR  22 isobaric levels
TCDC  22 isobaric levels      RH    33 isobaric levels
LCDC / MCDC / HCDC : low / middle / high cloud layer
```

**GFS carries everything ECCC withholds**, including condensate, in the same
byte-range request we already issue. HRDPS gives resolution; GFS gives vertical
structure.

> **Correction to the research report.** The liquid-water parameter is `CLMR`,
> not `CLWMR` - grepping for `CLWMR` returns zero hits on GFS. `ICMR` is right
> (it is not `CIWMR`). Both were verified by counting live.

> **Correction to something this repository previously believed.** The claim
> that cloud liquid water "cannot be obtained from the byte ranges we already
> request" is wrong. It is six selector tuples away.

### HRDPS `TCDC` is not a cloud fraction

Per ECCC's own WEonG technical note (v2.4.1, 2025-06-23, §7.9), the published
value is opacity-weighted:

```
NT_HRDPS = TCC · [ 1 − exp(−0.1·(W₃ + W₄)) ]
```

where `W₃`, `W₄` are column-integrated optical thickness in water and ice. So
thin cloud reads near zero and the field is always ≤ the true cloud fraction.
**This is a strong candidate explanation for HRDPS scoring SSIM 0.297 against
GFS's 0.72-0.81** - we may be interpolating a quantity that is not what the
name says, and `CWAT` is the field that would let us correct it.

*Status: **VERIFIED** against the primary PDF, 2026-09-01 (curl + `pdftotext
-layout`; WebFetch cannot parse it). Technote v2.4.1, 23 June 2025, section
7.9, p. 46, verbatim: "NT_HRDPS = TCC*[ 1 - exp(-0.1*(W3+W4))]; with
NT_HRDPS ∈ [0,1] ... where TCC is the True Cloud Cover; with TCC ∈ [0,1] and
W3 & W4 are the vertically integrated (total) optical thickness in water and
ice, respectively." The equation above is exact.*

### ECCC publishes its own repair for low cloud

The same technote gives an operational algorithm deriving low-cloud fraction
from the RH profile - the fields we already ingest - and combines it as
`NT_WEonG = max(NT_HRDPS, LLC)`. Saturated layer defined at RH ≥ 0.74, base
< 2000 m AGL, thickness ≥ 150 m, then a published RH→fraction table
(0.74→0.1 rising to 0.96→1.0), zeroed where max T ≤ −38 °C.

That is ECCC stating in its own documentation that HRDPS's published cloud
under-reports low cloud and must be repaired from RH. **Using the model
producer's own operational diagnostic is far better grounded than adopting a
generic closure with a guessed coefficient.**

*Status: **VERIFIED** against the primary PDF, 2026-09-01. Technote v2.4.1,
section 7.9, pp. 46-47. Implemented in `ingest/derive/weong_low_cloud.py`, with
every constant transcribed there. Two corrections to the summary above, both in
the zeroing step: the ice-covered-water rule is on the saturated layer's
**maximum** temperature being **less than** -15 °C "over an area of open water
covered with ice", and the homogeneous-nucleation rule is "**less than or
equal to** -38 °C". The RH→LLC table is published as half-open intervals, not
breakpoints, and matches.*

*But the algorithm is **not well-posed on the three pressure levels we
ingest**. It needs a profile: a saturated layer's thickness must be ≥ 150 m and
its base < 2000 m AGL, and the near-surface suppressions act at 122 m and 930 m
AGL. Of 850/700/500 hPa only 850 (~1.4-1.5 km AGL here) is inside the base
window at all, one level cannot have a thickness, and nothing is held near the
surface. `low_cloud_from_pressure_levels` is therefore a documented reduction -
RH table + the -38 °C zeroing at 850 hPa - which is an **upper bound** on LLC
(every omitted test can only remove cloud) and is **blind below ~850 hPa**,
i.e. blind to exactly the marine stratus and advection fog section 2 says
dominate the Avalon. Use it as a ceiling on how much cloud RH could justify
adding, not as a cloud fraction.*

---

## 2. Where the Avalon sits

This decides which methods are worth building at all.

- **~75% of fog offshore Newfoundland is warm-advection fog**; visibility below
  ~1 km **45% of the time in July**. 21 years of Hibernia platform
  observations (WAF 35(2), 2020).
- **"There is no diurnal variation in the frequency of occurrence of fog."**
  Same source. Radiation fog and burn-off-driven stratus have a strong diurnal
  signature by construction; its absence is close to a direct measurement that
  the cloud is being *transported in* rather than made and destroyed locally.
- St. John's: ~121-124 fog days/yr; Argentia exceeds 200.
- **But not purely advective.** C-FOG (BAMS 102(2), 2021) ran its supersite at
  Ferryland, on this exact peninsula, and found a split: at the coastal site
  fog "forms over the ocean and is advected toward land", while at the elevated
  Downs site "terrain-induced flow and terrestrial aerosols affect fog
  formation."

**Consequence.** An advection-based interpolant is the physically correct
default here, and by a wide margin. The predictable failure mode is
**stationary orographic stratus banked against Avalon terrain being smeared
downwind when it should stay pinned** - which is an argument for a *localised*
development term, not a global one.

No HRDPS-specific published marine-fog verification appears to exist.

---

## 3. Diagnosing cloud from humidity: the honest ceiling

### The scheme that is actually usable

Sundqvist, Berge & Kristjánsson (1989), MWR 117 - note **1989, not the 1978
paper**, which is a condensation scheme:

```
C = 1 − sqrt( (1 − RH) / (1 − RH_crit) )     for RH > RH_crit, else 0
```

Not ad hoc: Tompkins (ECMWF lecture notes, 2005) derives it exactly from a
**uniform PDF of total water** with half-width `Δq = (1−RH_crit)·q_s`. So
`RH_crit` is a statement about subgrid humidity variance, not a free knob.

**Slingo (1987)** is the one classical operational scheme that uses omega as a
second predictor, and is evaluable with exactly the fields we hold:

```
C*_mid = [ (RH − RH_crit)/(1 − RH_crit) ]²
C_mid  = C*_mid · (ω₅₀₀ / ω_crit)   for ω_crit < ω₅₀₀ < 0 ;  0 for subsidence
```

### Xu-Randall

```
C = RH^k1 · [ 1 − exp( −k2·q_l / ((1 − RH)·q_s)^k3 ) ],   k1=0.25, k2=100, k3=0.49
```

Default cloud-fraction scheme in WRF. **Available for GFS** (needs `q_l` =
`CLMR`); **not available for HRDPS**, which publishes no condensate on levels.
Do not substitute a parcel-derived `q_l` proxy - the coefficients are
CRM-calibrated against real condensate and a proxy invalidates them.

### The ceiling, measured by others

Grundner et al. (2022), against coarse-grained storm-resolving output:

| model | MSE (%)² |
| --- | --- |
| constant (climatological mean) | 109.63 |
| **tuned RH-only Sundqvist** | **51.14** |
| NN with condensate, cell-based | 15.19 |
| NN, neighbourhood-based | 1.01 |

**A tuned RH-only scheme removes about half the variance.** That is the
realistic ceiling for what humidity alone can tell us.

### Three warnings that matter more than the ceiling

1. **C is NOT monotone in RH for liquid cloud.** Chen et al. (2023, JAMES),
   against CloudSat: holding condensate fixed, liquid cloud fraction
   *decreases* with RH up to RH≈0.8 and only rises after. Every RH-ramp scheme
   assumes monotonicity. **It is empirically wrong exactly for marine stratus
   and fog - which is the Avalon's dominant regime.**
2. **Sundqvist underestimates low cloud at all latitudes in all seasons**, with
   the mid-to-high-latitude low-cloud underestimate worst near 60°N. We are at
   47.5°N.
3. **The RH-over-ice convention will swamp everything else.** ERA5 computes RH
   w.r.t. liquid above 0 °C, ice below −23 °C, blended between. At −20 °C,
   `e_s,water/e_s,ice ≈ 1.21`, so RH 0.85 over water is ~1.03 over ice - the
   difference between clear and overcast under any threshold. **Check each
   model's GRIB convention before diagnosing anything at 500 hPa.**

### RH_crit must differ between our two models

From aircraft data (Morcrette 2012, ECMWF workshop), RH_crit ≈ 0.95 at 1.5 km
grid length, with a log-linear fit reaching 1.00 at ~180 m. Extrapolated:
**~0.94 for HRDPS (2.5 km), ~0.88 for GFS (0.25°)**. Expect HRDPS-diagnosed
fields to look patchier; that is correct, not a bug.

Counterpoint worth keeping: Walcek (1994) found correlation between cloud and
RH *increases* with averaging area, and that at RH=80%, 800-730 hPa, the
probability of observing any given cloud amount is **nearly uniform** - RH tells
you almost nothing there.

### Do not invert total cloud into strata

One equation, N unknowns, through an overlap operator whose decorrelation
length is uncertain across the literature by a factor of ~10 (0.3-5 km). The
honest version is the forward one: diagnose each layer from RH independently,
combine under an overlap assumption, then **rescale so the total matches the
model's own `total_cloud`**.

---

## 4. What omega can and cannot do

For a parcel lifted dry-adiabatically (Clausius-Clapeyron plus the dry
adiabat):

```
d(ln RH)/dt = (ω/p) · [ 1 − κ·L_v/(R_v·T) ],      κ = R_d/c_p = 0.2857
```

Bracket values: **−4.41** at 850 hPa/283 K, **−4.80** at 700/268, **−5.23** at
500/253. Resulting RH multiplier per hour of sustained ascent:

| ω (Pa/s) | 850 hPa | 700 hPa | 500 hPa |
| --- | --- | --- | --- |
| −0.10 | ×1.019 | ×1.025 | ×1.038 |
| −0.30 | ×1.058 | ×1.077 | ×1.120 |
| −1.00 | ×1.205 | ×1.280 | ×1.457 |

**Typical synoptic omega changes RH by 2-8% relative per hour.** Between hourly
frames this is a second-order correction. It becomes first-order only under
strong forcing or over 3+ hours. **Do not oversell it.**

Below saturation the dry approximation is *exact*. Past saturation it is
unbounded - RH reaches 1.96 after 3 h at ω = −1 Pa/s. **The fix is a hard clamp
at RH = 1, not the moist adiabat**: once cloud fraction saturates at 1 the extra
fidelity buys nothing and introduces a latent-heat feedback that cannot be
closed without condensate.

The most important structural caveat: **in a two-endpoint interpolation the net
tendency is already known exactly.** Omega can only say how to *distribute* a
known change across the interval and across space - never what the change is.
That is a genuinely smaller win than it first appears.

---

## 5. Measured here: the development test does not earn its place

The display weight falls back to a cross-dissolve where two half-warps
disagree, on the reasoning that cloud grew or decayed in place. Radanovics et
al. (GMD 18, 2025) warn that *"conventional pixel-based metrics obscure these
fundamental development prediction failures"* and recommend scoring growing and
decaying regions separately. Doing that here, on live artifacts, plus a
sharpness ratio (mean |∇| of the reconstruction over mean |∇| of truth,
1.0 = as sharp as reality):

| layer | variant | MAE grew | MAE decayed | sharpness |
| --- | --- | --- | --- | --- |
| eccc-hrdps total_cloud | shipped (flat 25) | 26.49 | 23.35 | 0.775 |
| | gradient-relative | 25.75 | 22.87 | 0.783 |
| | **no development test** | **24.91** | **22.40** | **0.853** |
| noaa-gfs total_cloud | shipped | 15.72 | 16.04 | 0.790 |
| | gradient-relative | 15.33 | 15.58 | 0.796 |
| | **no development test** | **14.26** | **14.18** | **0.867** |
| noaa-gfs cloud_middle | shipped | 18.17 | 17.66 | 0.778 |
| | gradient-relative | 17.03 | 16.86 | 0.788 |
| | **no development test** | **14.99** | **15.50** | **0.862** |

**Removing the development test improves growth, decay AND sharpness on every
layer.** The obvious counter-hypothesis - that MAE is simply rewarding blur -
is refused by the sharpness column: the variant with the best MAE is also the
*least* blurred. This is not a metric artefact.

Whole-field scores agree, but **only the fixed-control ones may be used to
rank methods against each other.** HRDPS total_cloud, live cycle:

| metric | baseline | no development test |
| --- | --- | --- |
| improvement over crossfade (fixed control) | 0.1341 | **0.1527** |
| midpoint MAE, percent (fixed truth) | 19.0510 | **18.6408** |
| midpoint SSIM (fixed truth) | 0.3073 | 0.3072 (tied) |
| improvement over reversed flow (**moving** control) | 0.2314 | 0.2898 |

**The reversed-flow control moves with the method and must not be used for
cross-method ranking.** It is "this construction with its motion negated", so
the baseline's control still dissolves wherever its agreement term is low and
is less damaged by the reversal, while a fully-advecting method's control is
advected hard in the wrong direction. That inflated the apparent lead here by
more than double - +0.0584 against the moving control, +0.0186 against a fixed
one. The score answers *"does this method's motion carry information"*, which
is what `MIN_HELD_OUT_IMPROVEMENT` correctly gates on; it does not answer
*"which method draws the better picture"*.

This was found by the `residual-advection` implementation, which measured a
case where the moving control ranked a construction with MAE 14.87 / SSIM
0.392 above one with MAE 14.57 / SSIM 0.402 - i.e. gating on it would have
switched on the worse picture. `development-residual` still gates on it and
should be revisited.

This is consistent with §2: on a coast where cloud arrives already formed,
advection is close to the whole story, and a term that suppresses advection
where two warps disagree is mostly suppressing advection where the *flow* is
imperfect - not where the weather developed.

**Note every variant is under-sharp (0.78-0.87 < 1.0).** All of them blur.
That is the real remaining defect, and §6 says where it comes from.

---

## 6. Where the blur comes from

NowcastNet (Nature 619, 2023) abandoned bilinear resampling for the advected
state, verbatim: *"applying bilinear interpolation for several steps will blur
the precipitation fields"* - keeping a parallel bilinear path only to carry
gradients. **If a trajectory is evaluated by chained resampling rather than a
single composed displacement, the blur is manufactured by the implementation.**
Worth auditing our C1 Hermite path against this.

Second source: fusing two warps that disagree is how a double image is made.
Joyce & Xie (2011) replaced CMORPH's time weights with **error-variance
weights**; IMERG V06 uses **squared correlation**. Both are the principled
version of what our per-pixel weight approximates.

---

## 7. Verification: MAE alone is not admissible

pySTEPS' own paper measures S-PROG cutting MAE by ~40% relative to plain
extrapolation, and the mechanism is scale filtering - blur. Ebert (2008) and
Wernli et al. (2008) both give worked examples where the MSE or hit-rate winner
is the worst forecast.

Recommended, and mostly not yet implemented here:

- **FSS** (Roberts & Lean 2008). Threshold both fields, replace each point by
  the fraction exceeding it in an n×n neighbourhood, then
  `FSS(n) = 1 − MSE(n)/MSE(n)_ref`. Plotting FSS against n gives *the smallest
  scale at which the interpolation has skill* - exactly the question "did the
  extra advection buy real structure, or move blur around".
- **SAL's S component** (Wernli et al. 2008) - signed, cheap, and a direct blur
  detector: negative S means objects too small or too peaked, positive means
  too large or too flat.
- **A sharpness or PSD constraint.** NowcastNet's own protocol tuned on skill
  *subject to* power spectral density being no worse than pySTEPS. The
  sharpness ratio in §5 is a cheap stand-in and already proved decisive.
- **Stratify by growth and decay** (Radanovics et al. 2025). One experiment,
  and it resolved a question that whole-field MAE could not.

---

## 8. What ships, ranked by evidence (updated 2026-09-01, after the second pass)

The set below is what `generated-cloud-development` builds, under the
governing-rule amendment (carve-out (d) in `openspec/config.yaml`). Ranking is
by strength of evidence, not by measured gain here - the gate decides that.

1. **Baseline without the development test.** Removing the test improves
   growth, decay and sharpness on every layer (§5). Advection weight becomes
   `clip(support / SUPPORT_FLOOR)`; the agreement term is gone. Default.
2. **Error-variance fusion** (Joyce & Xie 2011; IMERG V06 squared-correlation
   weights, Tan et al. 2019). Changes only the mix, never what appears.
3. **Computed residual with timing options** (`residual-advection`, and its
   generative sibling `residual-generative`). `s = warp(I₁, backward) − I₀`,
   drawn on an envelope `e(t) = t(1−t)(a + b t)` that vanishes at both real
   frames. Timing switches, each admitted only on a fixed control: humidity
   threshold crossing under GEM's own Sundqvist closure (§3, §11), omega
   shift (§4, folded in here rather than a separate method), daytime
   dissipation acceleration (Ghonima 2016; Pauli 2022), scale split (STEPS
   lifetimes), regime gate (Bley 2016 decorrelation). Every option is a
   physics prior with no interpolation precedent (§11 gaps), so refusal of
   all of them is a valid result.
4. **Height-steering** (kept enabled, owner decision). Only the hour around a
   live scan; forecast frames draw the baseline exactly and the map says so.
5. **GOES-transfer** (kept enabled, owner decision). Needs a rolling scan
   sequence the ingest does not keep; today draws the baseline exactly and
   the map says so.
6. **WEonG low-cloud repair as a separate derived layer**
   (`eccc-hrdps-low-cloud-weong`). ECCC's own operational diagnostic (§1),
   now well-posed on the nine-level 1015-850 hPa profile, disclosed as
   generated, absent when the kill switch is off.

Deliberately **not** on the list, unchanged from the first pass: pySTEPS
cascades (wrong information regime); a total→strata inversion (ill-posed); a
moist-adiabatic tendency (clamp instead); a pretrained deep flow; Xu-Randall
for GFS (dropped from the build: operational GFSv16 does not use it, §11).

### Retired 2026-09-01, with the measurement that retired each

Deleted from the registry, not disabled: under carve-out (d) the registry is
a list of science-backed constructions, and a transfer from video or
nowcasting that measured worse is not one. Numbers are from the bench's own
`tasks.md`, live cycles of 2026-09-01.

| method | measured reason |
| --- | --- |
| `intermediate-flow` | A wash: largest gain +0.0068 (GFS mid), largest loss −0.0011 (RDPS), HRDPS +0.0001. After the neighbourhood fill the two derived directions invert well enough that the construction coincides with the baseline on real fields. |
| `visibility-blend` | Slightly negative on the headline control: −0.0106 on HRDPS, only gain +0.0003 (GFS low). Weight asymmetry 0.015-0.103 exists but not where the score is decided. |
| `scale-cascade` | Refused by its own control: the same per-pixel boost with NO scale split scored −0.214 MAE / +0.0059 SSIM against the cascade's −0.142 / +0.0047, beating it on 5 of 6 layers. The cascade's isolated contribution is negative, and no correct one-pass shader exists (~961 texture reads per fragment). |
| `flow-net` | Lost to DIS on 5 of 6 layers (mean −0.037). The single HRDPS win was resolution: DIS at the network's own 360×480 scored 0.2506 there versus the network's 0.2968 and native 0.2331. 312× the cost. |
| `full-advection` | Not a construction: a display-weight change. Its measured table (§5) becomes the baseline's docstring and `advect_weight = clip(support / SUPPORT_FLOOR)` is the baseline. |
| `development-residual` | A wash to a slight loss: −0.0003 against the control, MAE 14.5657 vs 14.5465, SSIM 0.40401 vs 0.40435; gated on the moving control (§5). Its omega term survives as the `omega_shift` timing option of the computed residual, where two endpoints already fix the net change and omega can only decide WHEN. |

---

## 9. Practice elsewhere

- **ECCC's own MSC AniMet does not temporally interpolate at all.** Its
  "Interpolation" control is spatial resampling only.
- **Windy does**, and exposes it as a user-visible toggle ("Smooth animation of
  radar and satellite"). Algorithm undocumented. Community complaints in its
  own forum describe a "smearing effect" and object that it "violates mass
  conservation… creating false precipitation displays" - the clearest available
  argument for disclosure.
- **LibreWXR** interpolates hourly ECMWF IFS to 10-minute steps with dense
  motion vectors and *falls back to a static crossfade where the flow finds
  insufficient gradient signal* - the same fallback policy we ship.
- **No WMO, AMS or NWS standard on disclosing synthesised frames appears to
  exist.** WMO's AI guidance is being written, not published. The nearest
  operational analogue is "future radar" labelling, handled by vendor
  disclosure text rather than any standard.

---

## 10. Open questions

1. ~~Verify the WEonG `NT = TCC·[1−exp(−0.1(W₃+W₄))]` formula and the LLC
   table against the primary PDF before building on either.~~ **CLOSED
   2026-09-01, verified in code.** Both transcribed from technote v2.4.1
   §7.9 into `ingest/derive/weong_low_cloud.py` (`nt_hrdps_from_opacity`,
   `llc_from_max_rh`, `combine_nt_weong`), with the two corrections to the
   zeroing step recorded in §1 and in that module's docstring. The same
   section's [0.25, 0.5, 0.25] hourly smoother and 40 km averaging are in
   §11.2.
2. ~~Determine the RH-over-ice convention in HRDPS and GFS GRIB metadata.~~
   **CLOSED 2026-09-01, verified in code.** GRIB2 0/1/1 codes no phase key,
   so it was MEASURED from each model's own SPFH on the same level
   (`ingest/grib.py`, `ECCC_RH_PHASE_BASIS`, `GFS_RH_PHASE_BASIS`,
   `declare_rh_phase`): HRDPS and RDPS divide by saturation over liquid
   water at every temperature (500 hPa matched water to 0.08 % / 0.13 %,
   missed ice by 19-20 %); GFS is mixed-phase, a linear ramp in temperature
   from all-ice at 253.16 K to all-water at 273.16 K (NCEP's standard
   function). Consequence: `U0 = 0.94` on HRDPS/RDPS and `0.88` on GFS are
   not interchangeable below freezing, where GFS reads up to ~24 % higher for
   identical air; the convention is stamped on every RH field.
3. Confirm GFS low/mid/high sigma boundaries against ECMWF's pressure
   fractions (0.80 p_s, 0.45 p_s) before comparing strata across models.
   Partly answered in §11.2: ccpp-physics `gethml` uses latitude-interpolated
   pressure boundaries (VERIFIED), which are not ECMWF's. Still open for the
   cross-model comparison itself.
4. Audit the Hermite trajectory for chained resampling (§6).
5. ~~Decide whether the development test survives §5 at all.~~ **CLOSED
   2026-09-01, decided: removed.** The owner-approved display semantics were
   amended (carve-out (d)); the baseline drops `_development_agreement` and
   the table in §5 - better growth, decay AND sharpness on every layer with
   the test gone - is the measured reason, carried into the baseline's
   docstring.

---

## 11. Second literature pass, 2026-09-01

Two agents, run after the owner amended the governing rule (carve-out (d)),
to settle what a generated term may lean on and what a verification protocol
must look like. Condensed. **Every claim carries the tag the agent gave it**:
VERIFIED means the agent read the primary source (abstract, doxygen, PDF, or a
byte decode here); REPORTED means the agent relayed the claim from secondary
knowledge without reading the primary; UNREAD means the paper was identified
but not opened, and no number from it may be attributed; GAP is a negative
result of the search. Nothing tagged REPORTED has been promoted.

### 11.1 Growth and decay between two held frames

**The both-endpoints lineage (this is an analysis problem).**

- Anagnostou & Krajewski 1999, JTECH 16: advection correction, a
  linear-in-t Lagrangian blend of the two frames warped toward each other.
  **VERIFIED** via the pySTEPS `advection_correction` example, which
  implements exactly this.
- Shapiro et al. 2010, JAS 67, Parts I and II: spatially variable advection
  correction beats a constant-velocity one. **REPORTED.**
- Shapiro et al. 2015, JAS 72: Lagrangian temporal interpolation beats linear
  (Eulerian) interpolation, and the gain grows with the sampling interval.
  **REPORTED.** The relevant direction for us: our interval is an hour.
- Thorndahl & Nielsen 2014: advection-interpolated radar preserves peak
  intensities that a linear blend flattens. **REPORTED.**
- Bowler, Pierce & Seed 2006, QJRMS, STEPS: lifetimes are scale-dependent,
  coarse scales persist and fine scales decorrelate fast. **REPORTED.** This is
  the ONLY physical argument in the literature for a non-uniform envelope in
  time, which is why `scale_split` exists as an option.
- CMORPH, Joyce et al. 2004: linear-in-t Lagrangian morphing between
  microwave overpasses. **REPORTED.** The known blind spot, stated by the
  authors: development that starts and ends INSIDE the interval is invisible
  to any two-endpoint method. Same limit as ours; the menu's gap sentence says
  it.
- LUPIN, arXiv:2402.10747: advection plus a separate growth/decay network,
  composed through a semi-Lagrangian operator. **VERIFIED** (abstract). Confirms
  the decomposition "advect, then add a source term" is the standard shape,
  learned there and computed here.
- Vandal & Nemani, IEEE TNNLS (arXiv:1907.12013): temporal interpolation of
  GOES-16 with a spatially varying, non-linear-in-time weighting. **VERIFIED**
  via ar5iv. Band 13 (10.3 µm) at t = 0.5: PSNR 38.67 → 45.44, RMSE 2.29 →
  0.99, SSIM 0.782 → 0.933 against linear. Gains are TINY in the visible
  bands, and in band 3 linear wins. The strongest quantitative
  both-endpoints result found, and the evidence for a per-cell (a, b) rather
  than a global gain.
- Lorenz 2009, clear-sky-index interpolation: interpolate the smooth latent
  variable, then re-apply the non-linear transform. **REPORTED.** The pattern
  behind `rh_timing`: interpolate RH (smooth), cross the closure (sharp).

**Physics of the timing options.**

- Ghonima et al. 2016, JAS: marine stratocumulus thinning ACCELERATES once
  the layer is thin; the Bowen ratio and marine advection control lifetime.
  **REPORTED.** Basis for the late-weighted `solar_dissipation` sigmoid on
  decaying cells.
- Pauli et al. 2022, QJRMS 148: fog and low-stratus dissipation timing is
  logistic in form. **REPORTED.** Basis for the sigmoid shape rather than a
  linear ramp.
- Akyurek & Kleissl 2017, JAS 74: closed-form stratocumulus dissipation.
  **UNREAD.** Not attributed.
- Wood 2012, MWR 140, the stratocumulus review. **UNREAD.** Do not attribute
  numbers to it.
- Bley, Deneke & Senf 2016, JAMC 55: about 30 min Lagrangian decorrelation
  time for convective cloud fields in SEVIRI. **REPORTED.** Basis for the
  `regime_gate`: where motion-compensated lag-1 correlation is low, the field
  is being remade and an hourly residual has no timing information.
- PDF-closure caveat: Larson 2013, GMD 6; Bogenschutz & Krueger 2013, JAMES.
  **REPORTED.** Interpolating RH and then applying a closure gives a
  sharper-than-physical crossing, because the real subgrid PDF broadens the
  transition. The sigmoid width `w = 0.15` is the acknowledgement; it is a
  prior, not a measurement.

**Verification of interpolation quality.**

- CloudCast, Partio 2025: MSE-trained models blur and under-produce cloud
  formation. **REPORTED.** Same warning as §7: pointwise error rewards blur.
- FloLPIPS, arXiv:2207.08119: a flow-aware perceptual metric for video frame
  interpolation. **VERIFIED** (abstract). Not adopted (needs a pretrained
  perceptual network); cited as the field's own admission that PSNR/SSIM miss
  motion artifacts.

**Gaps (negative results of the search, all three GAP).**

1. No paper ablates linear-vs-Lagrangian-vs-envelope placement for the
   growth/decay term with both endpoints held. **GAP.**
2. No published method interpolates NWP cloud between output times. **GAP.**
   Everything above is radar or satellite.
3. Nobody uses omega or RH tendency to time a two-endpoint interpolation.
   **GAP.** Confirms §0 item 5 a second time. Every timing option is
   therefore a physics prior with no precedent, and the harness decides.

### 11.2 Model cloud fields, and how to verify against them

**What GFS `TCDC` is.**

- The Xu-Randall formula in §3 is **VERIFIED** (EMC doxygen), but operational
  GFSv16 uses the GFDL microphysics' unified diagnostic cloud fraction, not
  Xu-Randall - **REPORTED**; and what v17 will use is a **GAP**. Xu-Randall
  for GFS is therefore dropped from the build (§8).
- ccpp-physics `gethml`: **VERIFIED** in source. Total cloud is the
  maximum-random overlap `TCC = 1 − ∏(1 − c)` across layers; the low/mid/high
  boundaries are LATITUDE-INTERPOLATED between 1050/650/400 hPa and
  1050/750/500 hPa. Not ECMWF's sigma fractions (open question 3).
- UPP recomputes the strata only for FV3R/NMMB, using 642/350/150 hPa.
  **VERIFIED.** Not the GFS path.
- GFS pgrb2 carries BOTH PDT 4.0 (instantaneous) and PDT 4.8 (averaged)
  `TCDC` for every lead. **VERIFIED by byte decode here.** The 4.8 window is
  1 h out to f120 and 3 h beyond. The adapter selects 4.0
  (`noaa_s3.py`, `_INSTANTANEOUS_FORECAST`). Recorded as a hard-won fact in
  `openspec/config.yaml`.

**What HRDPS `TCDC` is.**

- GEM RPN physics documentation v3.6: **VERIFIED.** Sundqvist cloud fraction
  `b = 1 − sqrt((1 − U)/(1 − U0))` in sections 6.3 and 8.2; maximum-random
  overlap in section 9.2. This is the closure `rh_timing` uses, because it is
  the producer's own.
- HRDPS v7+ with P3 microphysics: how cloud fraction is diagnosed there is a
  **GAP.**
- WEonG technote v2.4.1 section 7.9: **VERIFIED verbatim**, including the LLC
  table, and two facts not in the first pass: the CIEL (ceiling) field is
  smoothed in time with a [0.25, 0.5, 0.25] hourly kernel, and fields are
  spatially averaged over 40 km. ECCC's own product treats HRDPS hourly cloud
  timing as uncertain to about an hour. That is the menu header.
- Datamart HRDPS `TCDC` = `NT_HRDPS` WITHOUT the LLC repair. **VERIFIED.** The
  repair is a WEonG post-process, which is why the layer here is separate.
- HRDPS and RDPS `TCDC` are PDT 4.0 instantaneous: **VERIFIED by decode here**
  (JPEG2000 packing, 12-bit, 0.1 % quantum).
- Milbrandt et al. 2016, WAF 31: large sensitivity of forecast cloud to the
  microphysics scheme. **REPORTED.** A reason to expect the two models' cloud
  fields to differ beyond what the overlap definitions explain.

**How model cloud verifies against reality (why a fixed control matters).**

- Perez et al., Solar Energy: GFS reports clear sky falsely about 54 % of the
  time at the studied sites. **REPORTED.** The direction is the same as
  HRDPS's opacity-weighted under-report: models under-produce cloud.
- Dorman et al. 2020, WAF 35; Fernando et al. 2021, BAMS 102 (C-FOG);
  Formby-Fernandez et al. 2025, QJRMS: regional fog and low-cloud
  verification. **REPORTED.** No HRDPS-specific marine-fog verification
  found (unchanged from §2).
- Gilleland et al. 2009, WAF 24: the double penalty. **REPORTED.** A
  displaced feature is punished twice pointwise, so a blurred forecast wins.
- Harris et al. 2001, J. Hydromet. 2: spectral (multiscale) verification.
  **REPORTED.** Basis for the radial-PSD ratio.
- Ritvanen et al. 2025, GMD 18: cell-tracking framework separating growth
  and decay. **VERIFIED.** S-PROG has the maximum blurring of the models
  compared; every model scores 10-15 % better on decaying tracks than on
  growing ones. Growth is the hard half, and it is scored separately here
  (`mae_grew`, `mae_decayed`).
- Ravuri et al. 2021, Nature 597: the PSD-matching protocol - skill subject to
  the power spectrum being no worse than the reference. **REPORTED.**
- Skok, arXiv:2311.11985: FSS reference and its neighbourhood semantics.
  **REPORTED.**

**Recommended protocol, adopted in `harness.py` (stream C).** Fixed controls
only - persistence, plain crossfade, and advection-linear on the same two
frames; FSS at 25/50/75 % over 1- and 3-cell neighbourhoods; SAL's structure
component where cheap; MAE as a GUARD only, never a ranking; radial-PSD
spectral-ratio error; sharpness ratio; error stratified by object growth and
decay; and stratification by regime (the motion-compensated lag-1 correlation
of `regime_gate`). The reversed-motion control stays the veto on whether
motion is displayed and is used for nothing else.

---

## 12. Menu copy

The five entries after `generated-cloud-development`, verbatim from the
approved plan (section 0b). Generative options are switches inside entry 3,
not entries. Each entry carries a plain sentence, a "gap" sentence, and an
expandable "the science" note (server-supplied `notes` beside `summary`,
rendered collapsed under the plain copy).

### Title / plain / gap

1. **Move the cloud** (default) / We work out how the cloud moved between
   the two hourly pictures and slide it along that path. / Cloud that
   appeared or vanished in place fades evenly; that is most Avalon fog.
2. **Move the cloud, trust the clearer picture** / Same slide, but where
   one picture explains the in-between better, it wins instead of the two
   being averaged into a ghost. / Only changes the mix, not what appears.
3. **Move the cloud, then grow and clear it** (generated) / Same slide,
   plus we measure how much cloud formed or dissolved in place and draw
   that happening; switches decide WHEN in the hour: humidity reaching
   saturation, rising air, daytime burn-off. / Cloud that forms and clears
   entirely inside one hour is invisible; timing is physics-based and
   measured against real frames, not observed.
4. **Steer by the observed cloud top** / Uses the satellite's measured
   cloud height to pick which level's wind moves each patch. / Only the
   hour around a live scan; forecast frames draw exactly entry 1.
5. **Motion borrowed from the satellite** / Ten-minute satellite frames
   give motion in short steps instead of one hourly jump. / Needs a rolling
   scan sequence the ingest does not keep; today draws exactly entry 1.

### "The science" note per entry

1. Dense optical flow (OpenCV DIS, Kroeger et al. 2016) both ways;
   forward-backward consistency (Sundaram, Brox & Keutzer 2010);
   normalized-convolution fill; C1 cubic Hermite trajectories through
   neighbouring frames. Advection correction: Anagnostou & Krajewski 1999
   (JTECH 16); pySTEPS `advection_correction`; Shapiro et al. 2010 (JAS
   67). Steering wind fill at 850/700/500 hPa from the same run.
   Development test dropped 2026-09-01: measured worse on growth, decay
   and sharpness on every layer (Radanovics et al. 2025 GMD 18).
2. Inverse-error-variance fusion: Joyce & Xie 2011 (KF-CMORPH, J.
   Hydrometeorol. 12); IMERG V06 squared-correlation weights, Tan et al.
   2019 (JTECH 36).
3. Computed residual s = warp(I1, backward) - I0: NowcastNet's source term
   in dx/dt + (v.grad)x = s (Zhang et al. 2023, Nature 619); Tatsubori et
   al. 2022 (arXiv:2203.01277) third flow channel; computed, not learned,
   because both endpoints are held. Timing: humidity threshold crossing
   under GEM's own Sundqvist closure b = 1 - sqrt((1-U)/(1-U0))
   (Sundqvist, Berge & Kristjansson 1989 MWR 117; RPN physics doc v3.6
   sec 6.3/8.2), RH_crit ~0.94 at 2.5 km (Morcrette 2012); omega via
   d ln RH/dt = (omega/p)(1 - kappa L/(R_v T)); daytime dissipation
   acceleration (Ghonima et al. 2016 JAS; Pauli et al. 2022 QJRMS 148);
   scale-split lifetimes (Seed 2003 S-PROG; Bowler, Pierce & Seed 2006
   QJRMS); spatially varying non-linear time weighting validated on GOES
   (Vandal & Nemani 2021 IEEE TNNLS, arXiv:1907.12013). Regime gate from
   motion-compensated lag-1 correlation (Bley, Deneke & Senf 2016 JAMC
   55: ~30 min decorrelation for convective fields). Gated on fixed
   controls with sharpness and PSD ratio (Ravuri et al. 2021 Nature 597;
   Harris et al. 2001; Roberts & Lean 2008 FSS; Wernli et al. 2008 SAL).
4. Per-cell steering level from GOES-19 ACHAF cloud-top height; AMV
   height assignment (Liu et al. 2025 GRL; EUMETrain); CIRACast / INCA.
5. CMORPH morphing (Joyce et al. 2004, J. Hydrometeorol. 5): short-step
   displacements from the ten-minute GOES-19 cloud mask composed
   Lagrangian into one model interval; displacement only, never a value.

In every note: "HRDPS TCDC is opacity-weighted, NT = TCC[1 -
exp(-0.1(W3+W4))] (ECCC WEonG technote v2.4.1 sec 7.9); GFS TCDC is a
geometric max-random fraction (ccpp-physics `gethml`). Not the same
quantity."

Menu header: "HRDPS's producer treats its hourly cloud timing as uncertain
to about an hour (WEonG smooths it 0.25/0.5/0.25). Everything here is
display between two real frames, never evidence."
Score line: "X% closer to the real frame than a plain fade; sharpness 0.NN
of real" (fixed control + sharpness), not the reversed-motion number.
Any entry that reduced to entry 1 on a layer says so ON THE MAP.

## 13. residual-generative: measured

Non-normative record of what the shipped generative method actually does,
measured 2026-09-01 on synthetic fixtures. No live artifact was readable in
this environment (`data/` holds only the ephemeris cache, no published
`*.zarr.zip`), so every number below is from hand-built frame sequences of
the kind `api/tests/test_method_residual_advection.py` uses: a stationary
40x40 blob plus a uniform offset developing on a named profile, five frames
at an hourly interval, with a synthetic HRDPS-shaped run beside it carrying
`relative_humidity_700hPa` (90 to 122 %, liquid-water convention),
`temperature_700hPa` (-5 degC) and `omega_700hPa` (0 to -0.3 Pa s-1). Live
HRDPS numbers must be re-measured before any of this is quoted as a
property of the layer.

**The construction.** `(gen_a, gen_b)` are fitted per cell by least squares
over `HELD_OUT_FRACTIONS` so `t(1-t)(a + b t)` best matches `s (F*(t) - t)`,
where `F*` is the accepted options' target delivered fraction. The starting
point is bit-for-bit the non-generative sibling: with no option accepted the
fit returns `a = 4 * RESIDUAL_GAIN * s`, `b = 0` to 5e-15 absolute, because
that target lies in the span of the two basis functions and the fit
reproduces it exactly rather than approximately.

**Options accepted, per fixture** (greedy, each on `harness.admit` over the
accepted set; `improvement_over_crossfade` at the midpoint):

| fixture (development profile) | applied | gain | options accepted | start | best |
|---|---|---|---|---|---|
| `2t - t^2` (front-loaded) | no | 0.125 | none | 0.667 | 0.667 |
| `t^2` (back-loaded) | no | 0.125 | residual itself refused by the parent | - | - |
| `t` (linear) | no | 0.125 | residual itself refused by the parent | - | - |
| `1 - e^-12t` (saturating) | yes | **0.5** | gain only | 0.253 | 0.988 |
| translating blob + saturating | yes | **0.5** | gain only | 0.402 | 0.900 |

On the saturating fixture the accepted gain is 0.5 - twice the
non-generative ceiling - and it is accepted on all four checks:
`improvement_over_crossfade` 0.988 against 0.506 at gain 0.25,
`midpoint_ssim` 0.99999 against 0.98955, `midpoint_sharpness_ratio` 0.99999
against 0.99999, mean MAE over every held-out fraction lower. Gain 0.75 and
1.0 are then refused (crossfade 0.484 and -0.006), so the search does not
run to the ceiling: it stops where the measurement stops improving.

**Every option's numbers on the saturating fixture** (crossfade / advection
/ SSIM / sharpness at the midpoint):

- `accepted_start` (gain 0.125): 0.2529 / 0.2529 / 0.9735 / 1.00000
- `gain=0.25`: 0.5058 / 0.5058 / 0.98955 / 0.99999
- `gain=0.5`: **0.9883 / 0.9883 / 0.99999 / 0.99999** (accepted)
- `gain=0.75`: 0.4837 / 0.4837 / 0.99253 / 0.98947
- `gain=1.0`: -0.0064 / -0.0064 / 0.96829 / 0.92303
- `rh_timing`: 0.6156 / 0.6156 / 0.99355 / 0.99999 (refused: worse than the
  accepted gain on the crossfade skill)
- `omega_shift`: not offered - it shifts a humidity crossing time and the
  humidity timing was refused, so it is arithmetically a no-op
- `solar_dissipation`: identical to the accepted state (a growing field has
  no decaying cell, so the option reaches nothing)
- `scale_split`: 2.2e-06 / 2.2e-06 / 0.94772 / 0.99997 (refused)
- `regime_gate`: 0.9737 / 0.9737 / 0.96713 / **1.2591** (refused - it buys
  its number by manufacturing edges, which is exactly what the sharpness
  check exists to catch)

**Nothing but the gain was accepted on any fixture.** That is the outcome
the plan named as valid: five of the six options are physics-based priors
with no interpolation precedent, and on synthetic development that is
spatially uniform there is nothing for a spatially varying timing to buy. A
humidity crossing, a solar burn-off and a scale split can only pay where the
development is not uniform, and these fixtures are uniform by construction
(that is what makes them a controlled test of WHEN rather than of WHERE).
They must be re-measured on a live HRDPS pair before anything is claimed for
them.

**Bounds, verified rather than argued.**

- Endpoint exactness: the composite at `t = 1e-6` and `t = 1 - 1e-6` differs
  from the retrieved frame by under 1e-3 percent with both coefficients at
  the cap, so the vanishing is the envelope's own `t(1-t)` and not the two
  guards.
- The envelope cap is enforced by scaling `(a, b)` down together, and the
  peak is located analytically (the cubic's stationary points are the roots
  of a quadratic) rather than by sampling - a sampled maximum let the cap be
  exceeded by 0.0012 percent between two samples.
- Swept over six option combinations on a field whose residual saturates
  `RESIDUAL_CAP_PERCENT`, the drawn envelope never exceeds the cap.
- With the shipped constants the cap does not bind on the sigmoid timing
  alone: the worst fitted peak over `t*` in (0, 1) and widths 0.02 to 0.15
  from a residual at the 50 percent cap is 32.3 percent. It binds on the
  gain option (gain 1.0 on a capped residual peaks at exactly 50) and on the
  scale split, where the fine band can exceed the whole residual.

**What makes it generative, demonstrated.** With the residual equal to the
pair's own change - which is what it IS where nothing moved - the delivered
fraction at gain 0.25 stays at or under 1.0 at every `t` (the sibling's
guarantee), while at gain 1.0 it exceeds 1.0: the display draws a value in
neither retrieved frame. That is the licence carve-out (d) grants and the
reason this method is a separate registry entry with `generative = True`,
its own disclosure and the deployment kill switch. The drawn field is still
clipped to [0, 100] percent.

**Solar elevation.** The in-module Spencer (1971) formulation was checked
against a known value: at the June solstice, maximising over the day at
23.44 N / 0 E gives 89.92 degrees, against the 90 degrees the subsolar point
at the Tropic of Cancer requires (0.08 degrees out, found at 12:01 UTC -
the equation of time, not 12:00).

### 13b. Live cycle, 2026-09-01 18Z HRDPS run, `cloud-motion-bench-v6` (measured)

First derive after the bench moved to fixed controls. HRDPS `total_cloud`,
21 held-out frames. Every number is from the published `per_method.options`
block of the live motion artifact.

| method | term | crossfade skill with / without | SSIM with / without | sharpness with / without | verdict |
| --- | --- | --- | --- | --- | --- |
| baseline | steering prior | 0.1784 / 0.1695 | 0.3524 / 0.3539 | 0.860 / 0.866 | prior refused (SSIM, sharpness) |
| error-variance-blend | inverse-variance weights | 0.1695 / 0.1715 | 0.3539 / 0.3543 | 0.866 / 0.856 | refused (skill lower) |
| residual-advection | computed residual, gain 1/8 | 0.1750 / 0.1715 | 0.3514 / 0.3543 | 0.837 / 0.856 | refused (SSIM, sharpness) |
| residual-generative | every option | all refused | | | refused |

Against the NEGATED residual the residual wins on skill (0.1750 vs 0.1568),
SSIM (0.3514 vs 0.3464) and mean MAE (20.82 vs 21.24) and loses only on
sharpness (0.837 vs 0.899): the sign of the residual carries information,
but on this cycle delivering it blurs the field more than it helps.

**On every GFS layer the same held: no method's own term was admitted.** The
only true switch on GFS was the inherited steering-prior flag, which the
API had been reading as the method's own until 2026-09-01 (fixed in
`app._reduced_to_default`). The map therefore draws the baseline
construction for every method on every layer this cycle, and says so.

This is the outcome the plan named as valid. The earlier +MAE/+SSIM result
for the residual (section 5, 00Z run f005-f009) was one cycle; this is
another; the gate is per cycle and per variable by design. What it means for
the owner's question: on an advection-dominated coast, on these two cycles,
the computed residual does not reliably beat plain advection on structure,
and the humidity/omega timing options had nothing to improve because the
residual itself was not admitted. The next things worth measuring are a
regime stratification (marine stratus vs post-frontal cumulus, section 11)
and the WEonG-repaired layer once its profile is ingested, since a field that
under-reports low cloud by ~35 points (section 13a) is a different
interpolation target.

### 13c. WEonG-repaired layer, live (2026-09-02 00:14Z, HRDPS 18Z run)

First HRDPS run ingested with the nine-level profile (parallel pool 6,
host interval 0.1 s: run fetched in ~8 min at ~4.7 MB/s, zero 429s). The
derived layer `eccc-hrdps-low-cloud-weong` published, motion derived for
all six methods, browser readback passed.

| layer | baseline crossfade skill | midpoint SSIM | sharpness |
| --- | --- | --- | --- |
| eccc-hrdps-surface-total-cloud (published NT) | 0.1715 | 0.354 | 0.856 |
| eccc-hrdps-low-cloud-weong (NT_WEonG) | 0.2293 | 0.484 | 0.880 |

The repaired field is materially easier to interpolate by advection than
the published opacity-weighted one (SSIM 0.48 vs 0.35), consistent with
section 1's suspicion that thin-cloud opacity weighting, not motion, was
costing HRDPS its structure score. The fixed-control gate again admitted
no method's own term on this layer; all six draw the baseline and say so.
