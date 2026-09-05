# WeatherNext: no-charge access and bounded Avalon sampling

Reviewed: 2026-09-05. Research issue: [Determine a no-charge WeatherNext access and sampling plan](https://github.com/TusharSariya/Astraeus/issues/73).
Parent map: [Wayfinder map: implement the missing free-access evidence sources](https://github.com/TusharSariya/Astraeus/issues/70).

Classification: **no spec impact**. The original phase was public-document
investigation only. A later owner-authorized phase used an existing isolated
gcloud login for redacted configuration checks and bounded live metadata
requests. It made no billing, IAM, login, ADC, terms, or implementation change
and read no forecast values. `operational: false` remains the disposition. This
supplements [prior validation](../google-weathernext-3-validation.md).

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

## Execution preparation and anonymous control

Issue [Verify the approved WeatherNext account with a bounded sample](https://github.com/TusharSariya/Astraeus/issues/76)
prepared an executable manifest generator and validator at
`experiments/st-johns-weather-map/scripts/weathernext_probe_manifest.py`. It
enumerates 126 documented statistic arrays across all 21 one-hour surface and
station fields published on the statistics surface, not only the six cloud
fields selected for the first sample, and requires every field to remain
explicitly `retrieved`, `missing`, `unsupported`, or `deferred`. A successful
six-field sample therefore cannot be mistaken for whole-source or all-field
implementation proof.

An anonymous control request on 2026-09-05 used the JSON API object-list route
for the exact statistics prefix, `maxResults=1`, and a response-field mask. It
sent no authorization or requester-billing identity. The response was HTTP 401,
742 bytes, with `storage.objects.list` denied to the anonymous caller. This
confirms that anonymous listing is unavailable; it says nothing about the
owner's allowlisted identity, known-object reads, bucket billing configuration,
or historical-run existence.

The owner subsequently authorized a Google-native CLI validation using the
existing, separately authenticated `astraeus` gcloud configuration. A redacted
preflight on 2026-09-05 established that an account is selected and that no
default project, explicitly stored billing quota project, impersonated service
account, access-token file, credential-file override, or relevant environment
override is configured. `gcloud config get-value billing/quota_project`
reported `CURRENT_PROJECT`; configuration inspection established that this is
the SDK default sentinel, not a stored project ID. With `core/project` absent,
the installed SDK resolves that sentinel to no quota project. The validation
also set `CLOUDSDK_BILLING_QUOTA_PROJECT` to an empty command-local value and
removed related command-local environment overrides. No account or project
identifier was printed or retained.

The authenticated bucket-metadata request succeeded and reported
`requesterPays: false` for the exact statistics bucket. A bounded object list
also succeeded. This establishes that the selected login can access the GCS
statistics surface without a requester project; it does not establish access
to the excluded requester-paid full-ensemble bucket or any other WeatherNext
surface.

The proposed historical run
`2026_to_present/20260801_00hr_01_preds/predictions.zarr/` exists. Its 182,540-
byte consolidated Zarr v3 metadata declares a 360-element hourly forecast axis,
133 nodes, and all 126 documented statistic arrays. The six selected cloud
arrays are present as `float32` with units `(0 - 1)`, dimensions
`[lead_time, lat_0p1, lon_0p1]`, shape `[360, 1801, 3600]`, chunk shape
`[1, 1801, 3600]`, and Zstandard compression. This inventories the live schema
and confirms the exact chunks for proposed leads 6, 12 and 24 exist. It does
not prove that every data object behind every one of the 126 arrays is present;
that would require an exhaustive listing outside this metadata probe.

The consolidated metadata object's generation is `1787792319369404`, ETag is
`CLyhg7HNv5YDEAE=`, and SHA-256 is
`a1e1a47514c681be825ca5a5cfac7d0375e6b7d24b3dae201b64989e86724549`.
Every one of the 126 manifest fields remains `deferred`, not `retrieved`: the
live observation is metadata presence only. The inventory is the Cartesian
product already encoded by the validator: the 21 named base fields and each of
`mean`, `p10`, `p25`, `p50`, `p75`, and `p90`.

The 18 compressed objects needed for the proposed six-field, three-lead sample
total 375,209,154 bytes. That exceeds the 64 MiB received-byte cap before
decode, so no forecast values were read and no sample artifact was created.
The full-grid-per-lead chunk layout prevents the proposed point or Avalon subset
from reducing transfer size. Metadata and list activity remained under 4 MiB,
39 Cloud Storage requests, and five minutes. No token, credential file, ADC
profile, IAM setting, or billing account was read, and no cloud resource was
created or changed.

## Proposed bounded experiment (authenticated sample not executed)

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
- Anonymous control: one JSON API list request, HTTP 401, 742-byte body, no
  authorization or requester-billing identity.
- Authenticated CLI preflight: selected account present; default project,
  explicitly stored billing quota project, impersonation, token-file and
  credential-file overrides absent. `CURRENT_PROJECT` was the unstored SDK
  default and resolved to no project. Account and project values were consumed
  only to emit redacted booleans.
- Live bounded result: statistics bucket metadata accessible with
  `requesterPays: false`; target historical run and consolidated Zarr metadata
  accessible; 126/126 documented arrays present in metadata. Cloud data sample
  not run because its 18 source chunks total 375,209,154 bytes, above 64 MiB.
  Total Cloud Storage request upper bound: 39; metadata/list output below 4 MiB.
- Reproducible request semantics: every invocation included
  `--configuration=astraeus`; the process environment set
  `CLOUDSDK_BILLING_QUOTA_PROJECT` to empty and removed
  `GOOGLE_CLOUD_QUOTA_PROJECT`, `CLOUDSDK_CORE_PROJECT`, and
  `CLOUDSDK_AUTH_IMPERSONATE_SERVICE_ACCOUNT`. Listings used both `--limit` and
  `--page-size`; object content used an exact byte range after a bounded
  describe. No recursive or exhaustive CLI listing was used.
- `uv run --with pytest python -m pytest experiments/st-johns-weather-map/scripts/tests/test_weathernext_bounded_probe.py -q`
- `python3 experiments/st-johns-weather-map/scripts/weathernext_probe_manifest.py template`
- `uv run --project tools/specs python tools/specs/specctl.py validate`
- `git diff --check`

Spec-Impact: none — non-normative research and a proposed experiment procedure;
no behavior, provider registry, contract, or normative status changed.
