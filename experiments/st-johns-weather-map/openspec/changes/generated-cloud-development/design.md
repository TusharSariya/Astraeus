# Design: what a generated term is allowed to be, and what stops it lying

## The contract every stream builds against

| Decision | Choice |
| --- | --- |
| Envelope the shader evaluates | `e(t) = t(1-t)(a + b t)` added after the advection mix, clamped to [0,1] alpha. Stored per cell as float32 `gen_a`, `gen_b` (cloud percent), both vetoed suffixes. Every generative option maps to (a, b). `res_s` stays stored as a diagnostic, vetoed, not served. |
| Served texture | Keeps the name `residual` but serves R = `gen_a`, G = `gen_b`, signed, fitted scale per request (`X-Weather-Flow-Scale` in percent); refused by name unless the method's shader is `residual-advection`, as `visibility` is refused today. |
| `backward` texture | Deleted; its only consumer was `intermediate-flow`. Stored `u10`/`v10` stay (read by `_segment_tangents` and error-variance). |
| Generative method | `residual-generative` (`generative = True`, subclass of `ResidualAdvectionMethod`, same shader). `residual-advection` at gain <= 1/4 stays non-generative and survives the kill switch. |
| Baseline | Absorbs full-advection: `advect_weight = clip(support / SUPPORT_FLOOR)`; `_development_agreement` deleted; its measured table moves into the baseline docstring. |
| Harness gate | `admit(with_, without)`: strictly better `improvement_over_crossfade` at the midpoint, `midpoint_ssim` not lower, mean MAE over `by_fraction` not worse, sharpness ratio not further from 1.0. Shared by every `configure`. `improvement_over_reversed_flow` stays only as the motion veto. |
| WEonG artifact | Separate derived artifact per source, `logical_name = low_cloud_weong`, variable `total_cloud_weong` (+ `llc`), with the run's own steering/omega/RH/T copied in; motion artifact `cloud_motion_low_cloud_weong`. Provider `surface` artifact untouched. |
| Kill switch | `generated_display_enabled()` reading `WEATHER_GENERATED_DISPLAY`; honoured by `enabled_methods()`, the WEonG derive, and reported by `/methods`. |
| Versions | `cloud-motion-bench-v6`; `weong-low-cloud-v1`. |

## Why an envelope, and why this one

Two endpoints fix the net change `s` at every cell. Whatever timing physics
proposes, the display must still pass through both retrieved frames exactly,
so the only freedom is a term that vanishes at `t = 0` and `t = 1`.
`t(1-t)` is the lowest-order such term; `(a + b t)` lets the timing be
asymmetric (early or late in the hour) without a second texture read. Every
timing option - a humidity crossing, an omega shift, a daytime dissipation
curve, a scale split, a regime gate - reduces to a least-squares fit of
`(a, b)` to that option's target delivered fraction at the held-out fractions,
so the shader is one branch and the bench scores exactly what the map draws.
A composite that drifted from its own shader would mis-rank its own method,
which is the same reason the bench pins endpoint exactness by test rather
than by convention.

The cap is `|e| <= RESIDUAL_CAP_PERCENT` and the composite is clipped to
[0, 100]: bounded to the variable's physical range and to a published cap, as
carve-out (d) requires.

## Why fixed controls, and why the reversed-motion score stays

The reversed-motion control is "this construction with its motion negated".
It moves with the method: a construction that dissolves more is less damaged
by the reversal, so the score it yields cannot compare two constructions. It
was measured inflating a lead by more than double, and ranking a worse
picture above a better one. It still answers the one question it was built
for - does this method's motion carry information - so it stays as the veto
that decides whether MOTION is displayed at all, and nothing else.

Ranking, and every admission of a generated term, is against controls that
do not move: a plain crossfade of the same two frames, and linear advection
along the baseline flow on the same two frames (`BaselineMethod(use_prior=False)`,
memoised per pair so the generative options reuse one DIS run rather than
recomputing it per option). Beside MAE and SSIM the harness reports a
sharpness ratio, a radial-PSD log-ratio error, FSS at 25/50/75 percent over
1- and 3-cell neighbourhoods, and MAE stratified into cells that grew and
cells that decayed. `admit` requires the midpoint crossfade skill to be
strictly better, SSIM not lower, the mean MAE over all fractions not worse,
and the sharpness ratio not further from 1.0 - because the one thing a
generated term must never be allowed to win by is blur.

## Why delete rather than disable

The bench kept losing methods registered `enabled = False` so their code and
last score stayed readable. That was the right call under the old rule, where
every construction was a permitted warp-and-mix. Under carve-out (d) the
registry is a list of science-backed constructions, and a transfer from video
interpolation that measured worse is not one. Keeping it disabled would make
the registry say something it does not mean. The measured reason for each
deletion is recorded in the proposal and in the research document, section
8, which is where a reader looks for it; `grep -rn` for the six ids returns
only those two places and the openspec history.

## Why a separate layer for WEonG, not a repaired `total_cloud`

`total_cloud` on the provider `surface` artifact is what HRDPS published, and
the governing rule says it stays that way. ECCC's WEonG repair is a
producer's own documented diagnostic - the strongest possible grounding for a
generated field - but it is still generated: it adds cloud RH says should be
there and HRDPS's opacity-weighted NT did not report. So it is its own
derived artifact and its own rendered layer, titled with the suffix
"(generated: WEonG low-cloud repair)", disclosed as derived in every response,
carrying the run's own steering/omega/RH/T so every interpolation method
works on it unchanged, and absent - from derive, from `/layers`, from the
menu - when the kill switch is off. `NT = max(NT_HRDPS, LLC)` also means
`total_cloud_weong >= total_cloud` everywhere, which the derive integration
test asserts.

The nine-level profile (1015-850 hPa, RH, T and geopotential height) is what
makes the algorithm well-posed: a saturated layer needs a thickness and a base
height AGL, and three steering levels cannot give either. The levels are
optional at ingest, so a run that lacks them still publishes its surface
artifact; only the WEonG derive declines, naming the missing level.

## Fail-closed at every rung

- A generative construction whose ingredient is absent (no RH at the steering
  level, no omega) reduces to the permitted advection with a diagnostic
  saying so (`rh_reached`, `omega_reached`), and the map note says it reduced.
- A timing option the gate refuses is published with its scores and
  `applied: false`; nothing refused reaches (a, b).
- A vetoed pair zeroes `res_s`, `gen_a` and `gen_b` together, so a field the
  motion veto refused cannot carry a generated term.
- The `residual` texture is refused by name for any method whose shader does
  not evaluate it; the client fetches it only when the served shader is
  `residual-advection`.
- The kill switch removes generative methods from `enabled_methods()` before
  any derive, so a method never derived is never scored and never offered.
- A stored generative menu choice is never restored across a reload; the
  reader chooses it again, with the confirm, every time.
- `/point`, `/timeline`, `/features`, stories and readings never read
  `gen_a`, `gen_b`, `total_cloud_weong` or `llc`.

## What this change does not decide

Whether any timing option earns its place on live data. Every one is a
physics-based prior with no interpolation precedent; the harness may refuse
all of them, and that is a valid outcome to report with its numbers, not a
failure to hide. Nothing here promotes a generated construction over the
default; the default stays `baseline` until a measurement says otherwise and
the owner agrees.
