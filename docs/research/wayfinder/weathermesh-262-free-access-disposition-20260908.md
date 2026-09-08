# WeatherMesh-6: free-access scope disposition

Reviewed 2026-09-08 for [#262](https://github.com/TusharSariya/Astraeus/issues/262),
under #70. Non-normative research; no source, registry, API or status changed.

**Recommendation:** keep #262 **open with unresolved ongoing free entitlement
and intended-use rights**. Do not close it as not planned on the basis of an
account or API-key requirement. The [owner scope in #70](https://github.com/TusharSariya/Astraeus/issues/70)
explicitly permits free registration and approved-account access; it excludes
paid subscriptions, paid trial conversion and unauthorized provider outreach.
This bounded audit prohibited account creation and authentication during the
audit only. Those task limits are not a global source-eligibility rule.

The checked docs establish a time-limited free trial, not a documented ongoing
free entitlement. They do not prove that all ongoing entitlements are paid-only
or that a suitable no-charge extension cannot exist. No free, reusable WM-6
delivery path has yet been verified; this is an unresolved prerequisite, not
proof of permanent exclusion or of no Avalon coverage.

## Existing checkpoint and narrow new evidence

The [2026-09-07 issue checkpoint](https://github.com/TusharSariya/Astraeus/issues/262#issuecomment-5565163832)
already recorded the account/trial and redistribution prerequisite. This pass
checked only plausible public-output alternatives and current documentation;
it did not repeat native forecast acquisition or a general model survey.

The [getting-started guide](https://api.windbornesystems.com/getting-started/)
still requires account-issued authentication for weather-data requests. The
no-charge entitlement is a two-week requested trial, capped at five requests
per minute and 2,000 total requests. It is not an ongoing anonymous feed.
The public SDK/CLI therefore does not by itself establish eligible data access.

The [current MCP guide](https://api.windbornesystems.com/technical-guides/integrations/mcp/)
explicitly separates anonymous documentation tools from authenticated live-data
tools. An unauthenticated MCP connection is consequently not a WM-6 forecast
integration path.

A [2024 public-download announcement](https://webflow.windbornesystems.com/blog/now-live-explore-our-ai-forecast-outputs-benchmarks)
is a real historical exception to overly broad claims that WeatherMesh has
never published outputs. Its [linked example](https://gist.github.com/KMarshland/10d46b5ec79997a3449100173bc123c7)
uses the older `forecasts.windbornesystems.com/api/v1/gridded/historical/500/geopotential`
route, selecting 24-hour leads for a December 2024 initialization. It carries no
`wm-6` model identity. Its old API-documentation link returned 404 during this
pass. Neither that announcement nor that script establishes a current WM-6
feed; no legacy forecast endpoint or payload was requested.

The [current legal page](https://webflow.windbornesystems.com/ext/legal), effective
September 4, 2026, also needs more precise treatment than a blanket prohibition
on all reuse. Section 6 includes an exception for content returned through an
AI Weather Tool. Sections 4 and 6 retain constraints, including against
systematic extraction/redistribution and competing-product use. This research
does not determine the legal application of those terms to Astraeus. The
exception does not supply an anonymous data endpoint or demonstrate rights for
an ongoing source-to-server-to-client forecast cache. No agreement was sought
or accepted.

## Geography and the next eligible prerequisite

The [WM-6 product documentation](https://api.windbornesystems.com/models-measurements/about-our-models/weathermesh-6/)
describes `wm-6` Global at 0.25 degrees, separate from regional `wm-6-3km`.
Thus lack of eligible access is **not evidence of no Avalon coverage**. No
native Avalon cell, current run or variable/member identity was verified here.
The [gridded API](https://api.windbornesystems.com/forecasts/version_1/gridded-forecast/gridded-forecast/)
is a documented delivery interface, but its authenticated examples are not
proof of a public free feed. Public city pages and benchmark displays likewise
do not establish a native WM-6 array/rights contract.

The next prerequisite is to establish whether an owner-approved free-account
entitlement, including any documented no-charge continuation, supports the
intended recurring use and rights. The getting-started guide permits requesting
a trial extension but does not establish its duration, price or intended-use
rights; this audit did not request one. Free account access must be considered
before excluding the source. Account setup, credential handling and any outreach
remain separate authorized actions, not implicit steps of this documentation
audit.

Once entitlement and rights are established, the next bounded verification can
pin Global versus HighRes, native run/valid time, variable/member/statistic
identities, units, grid-cell versus interpolated sampling, masks and measured
resource limits before a source contract and implementation. A future
not-planned recommendation would require evidence that the applicable continuing
access is paid-only or otherwise outside owner scope, not merely that no free
feed was found. No #262 closure is recommended or performed here.

Spec-Impact: none. Research-only clarification of an existing access blocker;
no scientific, API, registration or normative-status change.
Verification: current primary documentation and linked historical example read;
no credentials, account creation, outreach, paid request, forecast payload,
model execution or provider fixture acquired. Repository specctl and diff
validation recorded with the handoff commit.
