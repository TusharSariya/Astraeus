# Dedicated WeatherNext workspace

Classification: experiment. Owner authorization: the September 9 implementation
request supplies the dedicated workspace plan and explicitly authorizes this
experimental amendment. No normative status transition or production path.
Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-006.

## Requirements

The workspace retains the selected point and shared range, without the Series
24-hour restriction. One explicit native run is pinned; out-of-run times are
gaps. Section and product selections are explicit. Only the active section is
loaded, one quantity and native time (six statistics) per bounded page, using the existing statistics batch,
transport, native masks, two-acquisition semaphore and shared finite response
budget. Completed pages survive later-page failures. Expiry withholds values.
Cancellation prevents subsequent pages. Display changes never acquire science.

Clouds shows total, low, middle and high with a fixed 0–100 percent scale.
Temperature distinguishes gridded and station-trained air/dew point. Wind shows
10/100 m speed and retains native components in Details. Precipitation explicitly
selects model-native, IMERG or experimental one-hour amount. Solar retains
one-hour downward/direct energy in J/m2. Pressure and sea retains sea-level
pressure and masked SST. Every quantity retains mean/P10/P25/P50/P75/P90,
field-specific units, sampled grid, source/run/time and acquisition provenance.

Median is typical; P25–P75 and P10–P90 are ensemble percentile bands. Mean starts
off. No confidence intervals, density reconstruction, members, cloud summation,
combined-weather or at-any-time probabilities. Summaries cannot fully resolve
separate clusters. Missing percentiles remain missing independently of charts.

Backend threshold estimates use the closest published quantiles strictly below
and strictly above the threshold, with open tails bounded by zero/100 percentile
rank. Equal/repeated values are skipped, widening the bracket. Above reverses
the bounds; below retains them. Nonfinite/nonmonotonic or entirely missing sets
withhold estimates. Estimates include basis and provenance and remain explicitly
approximate. Threshold requests only read retained summaries, never providers.
Clouds defaults above 80%; other quantities prompt and retain separate unit keys.

The numeric grid supports only the four native cloud means, preserving existing
region, cells, masks, byte/entry/expiry bounds and field-specific cache identity.
Old map stacks and URLs remain valid; WeatherNext is a navigable/dockable view.

## Mapped verification

GOV-SPEC-001/004/006: test_weathernext_workspace.py, WeatherNext.test.tsx,
sourceGrid.test.ts, focusUrl.test.ts and the existing WeatherNext native/grid
fixtures; generated source contract check, strict experimental validation and
specctl validate. Synthetic desktop/narrow design artifacts are recorded under
`docs/evidence/weathernext-workspace-20260909/`.

## Live loading correction (September 9)

Owner request: “yeah fix it”, following the confirmed 45-second page timeout.
Pages load consecutive times of each quantity before the next quantity. Page
waiting allows the existing 90-second native acquisition to finish, with a
95-second bounded executor wait. No provider byte, object, process, concurrency
or billing limit is increased by this correction.

A workspace selection and its generation-identified summary receipts have a
fixed one-hour retention ceiling. Each acquired batch is given at most the
remaining selection lifetime; cache reads never extend it. The 60-second default
for other source consumers remains unchanged. This is retention of an explicitly
pinned run, not a claim that it is the newest forecast. Every quantity retains
its own batch provenance. Missing quantities remain pending until their page
completes; failed pages preserve earlier quantities and report a safe reason.

Verification: real six-statistic Total cloud batch on run 20260909_12hr_01_preds
succeeded in 33.5 seconds; regression cases cover bounded field groups, consecutive
chart times, merge without overwriting other quantities, receipt retention and
expiry, deadline alignment, and failure preservation.
