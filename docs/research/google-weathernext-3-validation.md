# Google WeatherNext 3 validation

Last reviewed: 2026-09-03

Status: non-normative, time-sensitive research. This note does not approve a
provider or change operational behavior.

## Executive conclusion

WeatherNext 3 is a valid, high-priority candidate for Astraeus validation. It
is materially more relevant to cloud forecasting than FourCastNet 1 or 3: the
published product includes direct total, high, medium and low cloud-cover
fields, hourly surface output, 64 ensemble members and live geostationary
satellite mosaics as model input. It is not a replacement for 2.5 km HRDPS:
its gridded surface products are published at 0.1 degrees, approximately 10 km,
and its operational usefulness around the Avalon remains unmeasured.

It is not yet an admissible live source. Access requires Google's allowlist,
anonymous Google Cloud Storage listing returned `401` on 2026-09-03, and the
real-time product has restricted and revocable terms. No authenticated live
read, Newfoundland schema sample, latency study, cost measurement or local
skill evaluation has been completed. The proposed specification therefore
treats it as a credential-required, restricted Google ensemble that contributes
no operational evidence until all gates pass.

## Published product

Google's model guide describes WeatherNext 3 as follows:

| Property | Published value |
|---|---|
| Release | August 2026 |
| Domain | Global |
| Initialization | 24 runs per day |
| Members | 64 |
| Time step | Hourly |
| Main cycles | 00, 06, 12 and 18 UTC; 15 days / 360 hours |
| Interim cycles | Other hourly initializations; 48 hours |
| Gridded surface resolution | 0.1 degrees, approximately 10 km |
| Pressure-level resolution | 0.25 degrees, approximately 25 km |
| Station-head resolution | 0.05 degrees, approximately 5 km |
| Architecture | Flexible Graph Network mesh transformer |
| Live inputs | Geostationary satellite mosaics and ECMWF HRES analysis |
| Training data | ERA5/HRES forecast-zero, IMERG, stations and satellite mosaics |
| Published history | 2026, with 2024 and 2025 backfill described |

The direct gridded cloud variables are `total_cloud_cover`,
`high_cloud_cover`, `medium_cloud_cover` and `low_cloud_cover`, expressed as
fractions from zero to one at 0.1 degrees. Published surface variables also
include 2 m temperature and dew point, 10 m and 100 m winds, solar radiation,
precipitation heads, mean sea-level pressure and sea-surface temperature.
Pressure-level products include geopotential, specific humidity, temperature,
horizontal wind and vertical velocity.

The guide does not document direct fog, visibility, ceiling, cloud-base,
cloud-top, optical-depth or condensate fields. WeatherNext cloud fractions must
not be averaged or voted with HRDPS or GFS cloud quantities until their
physical and temporal semantics are registered as comparable.

## Access, cost and delivery

Google documents three access surfaces: Google Cloud Storage in Zarr v3,
BigQuery and Earth Engine. Access requires an allowlist request, although a
Google account rather than an existing Google Cloud customer relationship is
sufficient to request access. The full 64-member ensemble and pressure-level
data are available through Google Cloud Storage.

The documented buckets are:

- `gs://weathernext3_spatial/weathernext_3_0_0/zarr/`
- `gs://weathernext3_statistics_spatial/weathernext_3_0_0_statistics/zarr/`

The full-ensemble bucket is Requester Pays, so a Google Cloud project incurs
ordinary storage-request, processing and egress charges. Google's real-time
terms currently state that access itself is offered without charge, but Google
may introduce fees with notice. Free access therefore does not mean cost-free
retrieval and is not a durable pricing commitment.

Anonymous JSON listing probes for both documented buckets returned HTTP `401`
and `storage.objects.list` denial on 2026-09-03. This is consistent with the
allowlist requirement, but does not validate authenticated object reads.

## Dissemination latency

An hourly initialization is not an hourly-fresh forecast. Google's published
targets are:

| Cycle | GCS target | BigQuery / Earth Engine target |
|---|---:|---:|
| Main 00/06/12/18 UTC | initialization + 7 h 45 min | + 8 h 10 min |
| Interim hourly | initialization + 7 h 10 min | + 7 h 25 min |

Google reports typical variation of plus or minus 15 minutes and occasional
variation of an hour or more. The paper also states that the latest satellite
mosaic has operational latency just under one hour, while the ECMWF analysis
input has materially longer latency. A scheduler must name initialization,
publication and retrieval times separately and must not present a newly
published interim cycle as one-hour-old evidence.

## Terms and redistribution

The real-time terms distinguish data about times less than one hour ago or in
the future from data at least one hour old. The former is restricted
"Real-Time Experimental Data"; the latter is offered under CC BY 4.0. The
restricted class permits internal use and qualifying value-added services, but
limits redistribution of raw or retrievable data. Simple recolouring,
cropping, regridding or combining times is expressly insufficient value-add.
Public non-retrievable value-added output requires the specified attribution
and experimental-data disclaimer.

The terms describe the data as approximate and experimental, not intended for
consumer use, and make access revocable. They also include termination,
deletion and downstream-notification obligations. Owner and legal review is
required before caching, redistribution, public visualization or derivation.
The terms should be snapshotted with each retrieval because this summary is not
legal advice and the terms may change.

## Scientific and operational limitations

- Google's evaluations are global and do not establish skill for Avalon fog,
  marine stratus, frontal timing or clear-sky controls.
- Sixty-four members represent one Google model family, not 64 independent
  centre votes.
- The model is initialized partly from ECMWF HRES analysis, so that dependency
  must remain visible even though WeatherNext 3 is a distinct learned model.
- Google documents possible jumps in station and other non-autoregressive
  one-hour heads across six-hour windows, member-dependent station biases, and
  experimental precipitation artifacts including hexagonal patterns.
- Historical backfill is incomplete and must not be assumed to provide every
  operational vintage required for retrospective evaluation.
- Direct satellite input is a meaningful design advantage, but it does not by
  itself prove cloud calibration, boundary-layer fog skill or low-cloud skill.

## Admission recommendation

WeatherNext 3 should enter the optional-provider backlog only after these
gates, in order:

1. Owner review of the current real-time terms, redistribution boundary,
   attribution, deletion obligations and potential fee changes.
2. Approved allowlist access and secret-safe credential handling.
3. Authenticated reads from the selected surface, including a complete Avalon
   evidence-box sample and exact dimensions, coordinates, missing values,
   member identity and units.
4. A seven-day publication-latency, completeness and retrieval-cost sample.
5. Field-catalogue entries for every used variable, including cloud semantics
   and explicit absence of unsupported fog/visibility/ceiling fields.
6. Preservation of initialization, publication, retrieval, member, product
   version, access surface, terms class and ECMWF-input dependency provenance.
7. Retrospective validation against GOES quality-controlled cloud evidence and
   SWOB/METAR observations, with at least two fog/stratus, two frontal-cloud
   and two clear-control cases.
8. Owner approval before registry promotion or any V1 provider-contract
   change.

Until then its status is `conditional-restricted`, not operational, and absent
WeatherNext evidence remains absent rather than being replaced with cached,
fixture or neighbouring-model data.

## Primary sources

- Google DeepMind, WeatherNext: <https://deepmind.google/science/weathernext/>
- Google for Developers, model guide:
  <https://developers.google.com/weathernext/guides/models>
- Google for Developers, forecast access:
  <https://developers.google.com/weathernext/guides/access-forecast>
- Google for Developers, Google Cloud Storage:
  <https://developers.google.com/weathernext/guides/gcs>
- Google for Developers, dissemination:
  <https://developers.google.com/weathernext/guides/dissemination>
- Google for Developers, benefits and limitations:
  <https://developers.google.com/weathernext/guides/benefits-limitations>
- Google DeepMind, WeatherNext 3 paper:
  <https://storage.googleapis.com/deepmind-media/papers/weathernext_3.pdf>
- Google, real-time data terms of use:
  <https://storage.googleapis.com/weathernext-public/terms-of-use.pdf>
