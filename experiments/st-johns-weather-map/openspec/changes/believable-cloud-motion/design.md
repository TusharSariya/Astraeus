# Design: why the display dissolved, and what replaces the gate

## What the measurements said

| Quantity (live HRDPS, 23:00->00:00Z pair) | Value |
| --- | --- |
| Median flow magnitude | 45 output px/hour (~15 grid cells) |
| MAE, persistence | 53.4 percent |
| MAE, full warp | 34.7 percent |
| MAE where confidence was exactly 0: persistence / warp | 52.4 / 31.7 |
| Median served confidence | 0.00 |
| Cells with confidence > 0.5 | 23% |
| Median served \|v - F\| (Hermite tangents) | 0.00 px |

The flow was good, the gate rejected it, and the C1 tangents - whose trust is
the minimum confidence of the adjacent knots - collapsed to the linear model
everywhere as a consequence. One miscalibrated constant disabled two shipped
changes at once.

## Why an absolute tolerance was the wrong test

`CONSISTENCY_LIMIT_CELLS = 2.0` asked: does the round trip close to within
two cells? For a field moving fifteen cells an hour that is a 13% relative
demand, which dense optical flow on a coarse quantized cloud field does not
meet. The literature's own test is relative (Sundaram, Brox & Keutzer 2010:
`|f + b|² < 0.01(|f|² + |b|²) + 0.5`); this implementation keeps a continuous
score with the same shape.

## What the display should actually mix on

Three candidates, ranked by held-out skill rather than by argument:

| Weighting | HRDPS vs reversed control | GFS vs reversed control |
| --- | --- | --- |
| `min(support, agreement)` | +0.056 | +0.351 |
| `agreement` gated by a support floor | **+0.090** | **+0.377** |

The forward-backward score answers "is this vector invertible", which is a
good question about a flow field and a poor one about a picture. The
half-interval warp agreement answers "does advecting these two frames toward
each other land on the same image", which is exactly what the reader sees. So
agreement leads and support only gates: a vector nothing trustworthy stood
behind cannot carry the display however plausible the two warps look.

## Why a reversed-motion control, not just a crossfade

Any blend of two warped frames is smoother than the average of the frames,
and a smoother field scores better on MAE against almost anything. Measured:
three independent noise fields "improve" on a crossfade by up to +0.02 while
scoring -0.001 to +0.001 against the same construction with the motion
reversed. The control cancels the smoothing advantage and isolates whether
the *direction* carries information. The veto threshold (0.02) sits an order
of magnitude above that null and well below the weakest real field (HRDPS
total cloud at +0.056 before the weighting change, +0.090 after).

## Why the estimator was not the lever

Presmoothing at sigma 1/2/3 cells, DIS with and without spatial propagation,
and the ultrafast preset with the finest scale forced were all measured on
live HRDPS: median consistency moved 0.30 -> 0.33 and the display weight 0.25
-> 0.29. This matches pySTEPS (GMD 2019), which found under 2% skill spread
across flow estimators. The lever is what the display does with the flow,
not which flow it is.

## What HRDPS can honestly deliver

Held-out skill against the reversed control: GFS strata +0.35 to +0.43,
HRDPS and RDPS total cloud +0.09. At 2.5 km and hourly, most of what changes
between two frames genuinely is development rather than translation, and the
leave-one-out test spans two hours, which makes it a conservative estimate.
So HRDPS will always show a mixture: cloud that moved advects, cloud that
grew dissolves. That is the honest picture rather than a failure, and the
development weight is what makes the mixture spatially selective instead of
uniform.

## The steering prior, and why it is fenced

The winds now ingested (850/700/500 hPa) are the levels that steer low, mid
and high cloud. Four fences, all mandatory:

1. **Unsupported cells only.** An observed motion is never overridden.
2. **Agreement-weighted.** The prior's weight is how well it matches the flow
   in the cells that *are* trusted. A wind the imagery contradicts reaches
   nothing, and a field with no trusted flow at all corroborates nothing, so
   the prior stays out and the crossfade stands.
3. **Stationarity gate.** Where a well-supported flow reports the field
   standing still, the prior is refused. This is not tuning: orographic and
   marine cloud over the Avalon forms and dissipates in place while wind
   blows through it, and a prior applied there would drag standing fog across
   the peninsula and call it motion.
4. **Earned per variable.** The held-out reconstruction is scored with and
   without the prior; the prior is applied only if it wins, and both numbers
   are published either way, so "the wind helped" is checkable rather than
   asserted.

### One thing not pinned about the winds

HRDPS and RDPS publish on a rotated lat/lon grid, and whether their u/v
components are grid-relative or earth-relative is not verified here. Over the
Avalon the domain sits near the rotated equator, so the two differ by a small
angle, and the design fails safe either way: a systematically rotated prior
agrees less with the trusted image flow, so it is weighted down, and if it
does not improve the held-out reconstruction it is not applied at all. If the
prior turns out to earn its place on some cycles and not others, this is the
first thing to check.

## Rendering stays exact

The owner chose hard native cells everywhere (2026-08-31). No smoothing was
added to the raster path or to the interpolation path; the frames are still
drawn at their stored cells. Believability has to come from the motion, which
is the honest place for it to come from.
