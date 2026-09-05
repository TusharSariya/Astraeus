# WeatherNext: no-charge access and bounded Avalon sampling

Reviewed: 2026-09-05. Research issue: [Determine a no-charge WeatherNext access and sampling plan](https://github.com/TusharSariya/Astraeus/issues/73).
Parent map: [Wayfinder map: implement the missing free-access evidence sources](https://github.com/TusharSariya/Astraeus/issues/70).

Classification: **no spec impact**. Public-document investigation only; no
account inspection, authentication, dataset requests, billing changes, terms
acceptance, or implementation. `operational: false` remains the disposition.
This supplements [prior validation](../google-weathernext-3-validation.md).

## Decision

Prefer a local, metadata-first experiment against the WeatherNext 3 **GCS
statistics** surface. Google documents Requester Pays as disabled there. This
establishes a provider-paid transport path in the documentation, but does not
prove the owner's entitlement or the live bucket configuration. The full
ensemble surface does not meet the present no-charge boundary. Do not infer
that approval of an access request includes every version or surface.

## Versions and access surfaces

Google's migration guidance deprecates WeatherNext Gen and Graph on Earth Engine
and BigQuery from July 29, 2026, recommends WeatherNext 3, and says WeatherNext 2
remains available. Existing WeatherNext 2 adapters or aggregator products must
retain their own identity. [Deprecation guidance](https://developers.google.com/weathernext/guides/deprecation).

WeatherNext 3 is offered through GCS, Earth Engine and BigQuery; operational
access is allowlisted. The supplied email confirms request approval only;
account, versions and surface entitlements are still unknown.
[Access guide](https://developers.google.com/weathernext/guides/access-forecast).

| Surface | Published scope and cost boundary | Disposition |
|---|---|---|
| GCS statistics | `gs://weathernext3_statistics_spatial/weathernext_3_0_0_statistics/zarr/`; surface mean/p10/p25/p50/p75/p90; Requester Pays OFF | Preferred conditional local experiment |
| GCS full ensemble | `gs://weathernext3_spatial/weathernext_3_0_0/zarr/`; raw 64 members and pressure levels; Requester Pays ON | Exclude under no-charge policy |
| Earth Engine | 0.1° surface and 0.05° station-head statistics | Conditional fallback after noncommercial eligibility verification |
| BigQuery | Analytics Hub linked tables `weathernext_3_0_0_0p1deg` and `weathernext_3_0_0_0p05deg`, surface statistics | Sandbox compatibility and access still unproven |

GCS statistics use a flattened hourly lead-time axis; raw ensemble data need
lead-time/subtime handling. Full-ensemble storage transitions to Nearline after
28 days. Colocating paid compute does not establish a no-charge workflow.
[GCS guide](https://developers.google.com/weathernext/guides/gcs).

Cloud Storage normally bills the resource owner's project. Supplying a billing
project can charge the requester **even when Requester Pays is OFF**. A future
local client therefore needs a verified outbound-request policy omitting
`x-goog-user-project`, `userProject`, and equivalent requester-billing settings.
No automatic retry may add billing identity. Local extraction avoids creating
paid compute or destination storage, but ordinary local resource use remains.
[Requester Pays](https://docs.cloud.google.com/storage/docs/requester-pays).

BigQuery bills query processing beyond its free allowance (first 1 TiB/month),
so a small output or `LIMIT` is not evidence of no charges.
[Pricing](https://cloud.google.com/bigquery/pricing).
The sandbox supports bounded use without a billing account, but the generic
sandbox documentation does not establish that this owner's restricted
WeatherNext Analytics Hub subscription will work there. Do not enable billing
as a workaround. [Sandbox](https://docs.cloud.google.com/bigquery/docs/sandbox).
If subsequently evaluated, inspect schema first, filter the initialization
partition and select only required statistics; obtain a dry-run estimate before
any execution. WeatherNext tables partition on `init_time` and carry a repeated
`forecast` record with valid time and lead hours.
[BigQuery guide](https://developers.google.com/weathernext/guides/bigquery).

Earth Engine unpaid access requires verified noncommercial eligibility. The
WeatherNext acceptance email does not grant that status.
[Earth Engine access](https://developers.google.com/earth-engine/guides/access).
Earth Engine noncommercial compute/storage remains unpaid within that program;
other Cloud products can still cost money. Do not export to paid storage.
[Noncommercial tiers](https://developers.google.com/earth-engine/guides/noncommercial_tiers).
The two WeatherNext collections distinguish gridded forecasts from station-head
statistics; neither should be represented as individually retrieved ensemble
members. [Earth Engine guide](https://developers.google.com/weathernext/guides/earth-engine).

## Licensing boundary

Current Google guidance puts future valid times and times less than one hour
old under the real-time terms; times at least one hour in the past transition
to CC BY 4.0. Aging the **initialization** by an hour does not make future
predictions historical. This updates older research referring to a 48-hour
boundary. [Disclaimers and licensing](https://developers.google.com/weathernext/guides/disclaimers).

The September 3, 2026 terms permit internal use and qualifying value-added
services, restrict sharing of raw/retrievable data, and explicitly exclude
mere cropping, formatting or time/parameter combinations as sufficient
value-add. Publication has attribution requirements. Eligibility, termination
and deletion provisions also apply. Section 7 presently charges no dataset
access fee but allows future fees with notice. The text calls the experimental
data unsuitable for consumer use and not a substitute for official warnings.
These findings do not approve Astraeus distribution or accept terms for the
owner. [Real-time terms, §§1–7](https://storage.googleapis.com/weathernext-public/terms-of-use.pdf).

A public API returning cropped future WeatherNext arrays is consequently not
cleared merely because access is free. Owner review must resolve the permitted
product and distribution boundary before production admission. For the initial
experiment below, choose an entire run whose last forecast valid time is
already at least one hour in the past, so even decoded source chunks cannot
silently include future forecast values.

## Proposed bounded experiment (not executed)

These are experimental limits, not accepted ingestion requirements.

1. **Run:** propose initialization `2026-08-01T00:00:00Z`; its maximum
   360-hour horizon ended August 16. Verify the entire source run satisfies
   the historical cutoff and exists before any forecast read. This is a target,
   not an observed available object. If absent, explicitly select and record
   one other complete historical synoptic run; never silently substitute a
   vintage. Do not copy Google's August 26 example: that run contains future
   predictions through September 10, 2026.
2. **Region:** proposed Avalon smoke-test box `[-54.0, 46.5, -52.5, 48.0]`
   (west, south, east, north). This is not the complete accepted evidence box.
   Start with the nearest native cell to `(47.5, -52.7)` before expanding to
   that rectangle. Record actual selected cell coordinates and selection rule.
3. **Time:** exactly leads 6, 12 and 24 hours from that single initialization;
   no latest-run chase, recursive archive scan, or retry across vintages.
4. **Fields:** request only `total_cloud_cover_mean`, `low_cloud_cover_mean`,
   `medium_cloud_cover_mean`, `high_cloud_cover_mean`,
   `total_cloud_cover_p10`, and `total_cloud_cover_p90` on the 0.1° grid.
   Base cloud variables are fractions in `[0,1]`; keep that unit.
   These are provider-computed distribution statistics, not members and not
   a probability of clear sky. Record `member_id: null`, the precise statistic,
   and documented ensemble size 64 separately from any observed metadata.
   The model guide documents the four cloud fields and units; the statistics
   surface documents suffixes. [Variables](https://developers.google.com/weathernext/guides/models).
5. **Budget:** total received bytes at most 64 MiB, decoded working arrays at
   most 128 MiB, output at most 5 MiB, at most 256 object requests including
   metadata and retries, and a five-minute deadline. These are conservative
   proposed limits, not measured chunk sizes. Cap metadata at 4 MiB within the
   same total. Abort if metadata, shard layout or compression prevents a safe
   bound; a tiny selected rectangle can still require large remote chunks.
6. **Decode:** inspect coordinate direction, grid dimensions, chunk/shard
   layout, dtype, fill values and units before loading. Require all six fields
   at all three leads. Retain masks; do not fill absent values or derive cloud
   layers from humidity. Check valid time equals initialization plus lead;
   reject duplicates, unexpected dimensions or out-of-range finite cloud values.
7. **Artifact:** local experiment manifest plus bounded extracted data, checksum,
   source object generations/ETags when available, byte/request totals, native
   units, masks, model/product version, bucket and exact object paths,
   initialization/valid/observed availability/retrieval timestamps, statistic
   identity, selected coordinates, decoder versions, and terms URL/date/hash.
   Unknown source publication time stays unknown; object update time is not
   automatically model publication time. Attribute Google and retain ECMWF
   input lineage. Keep credentials and personal account details out of artifacts.

## Separate owner-account procedure

The next task must first follow the repository's credential-safety skill
requirement; this report does not authorize inspecting secrets or credentials.
No provider/account operation occurred during this research.

1. Obtain the owner's confirmation of the approved identity and requested
   version/surface without reproducing private account details in research.
   Confirm current terms permission for the intended internal experiment.
2. Use an already approved local authentication mechanism; no new billing,
   IAM grants, subscriptions, terms acceptance, or cloud resources as implicit
   fallbacks. The email alone does not prove the authenticated principal is
   the approved principal.
3. Establish the statistics bucket's current non-requester-paid configuration
   using permitted metadata access or provider confirmation. Inspect the
   client's redacted request configuration for accidental billing-project
   propagation before any read. If configuration is unknown, stop.
4. Attempt only bounded metadata discovery of the selected historical run.
   Distinguish permission denial, absent run, missing list permission and
   requester-billing requirement. Do not treat a missing list permission as
   proof that known-object reads are denied. Do not retry against the paid
   full-ensemble bucket or create a paid query job.
5. Calculate chunk/shard cost in bytes before extracting. If the sample cannot
   fit its caps, record a blocked experiment rather than enlarge limits
   silently. Earth Engine is an alternative only after its unpaid status and
   dataset entitlement are established; BigQuery needs sandbox compatibility.
6. Execute the exact experiment once. Return the local artifact and redacted
   success/failure evidence. Only a later accepted provider specification and
   mapped fixture/live/API/failure verification may admit the source.

Remaining unknowns: actual entitlements; live requester-pays configuration;
client billing propagation; historical object availability; chunk sizes and
schema; source latency; usable Avalon completeness; and owner-approved
redistribution. Public docs answer the research question, not those account or
implementation gates.

## Verification

- Read current primary pages linked above on 2026-09-05; no live dataset claims.
- `uv run --project tools/specs python tools/specs/specctl.py validate`
- `git diff --check`

Spec-Impact: none — non-normative research and a proposed experiment procedure;
no behavior, provider registry, contract, or normative status changed.
