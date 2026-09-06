# NL provincial provisional air-quality CSV evidence

Captured 2026-09-06 for issue 118. This is non-normative evidence for an
isolated experiment. It does not grant redistribution, validate the readings,
or promote the source.

## Source eligibility and bounds

The selected source is exactly the Government of Newfoundland and Labrador's
St. John's NAPS Station 010102 rolling CSV at
`https://www.mae.gov.nl.ca/wrmd/pp_adrs/Data/StJohns_Line.csv`. The official
[station page](https://www.gov.nl.ca/eccc/env-protection/science/airmon/naps/stjohns/)
identifies the Water Street station, coordinates 47.56038/-52.71147, elevation
6.71 m and monitored pollutants. The legacy publisher
[near-real-time page](https://www.mae.gov.nl.ca/wrmd/pp_adrs/template_airmon.asp?station=stjohns)
links the CSV, calls every value provisional and not quality controlled, and
states that the page and contents are copyright with all rights reserved.

Eligibility is therefore limited to local isolated retrieval and readback.
The source stays unregistered from scheduling, `operational: false`, an
`uncalibrated_observation`, not display primary, not a derivation input and not
redistributable. The validated NAPS annual archive, other station/sensor
networks, and forecast models are excluded. The capture ceiling was 1 MiB with
38 GiB physical disk free; the response was 59,194 bytes.

## Complete upstream field disposition

| CSV column | Meaning and units | Disposition |
| --- | --- | --- |
| `STAT_NUM` | `StJohns` station identity | metadata; any other value fails |
| `DATE_TIME` | local observation time | metadata; `America/St_Johns` converted to UTC |
| `PM2_5_RUN_AVG` | producer graph labels this a 24-hour running average, µg/m³ | retrieved as `pm2_5_surface_24h_mean`, normalized to kg/m³ |
| `PM10_RUN_AVG` | PM10 running average | deferred; outside selected PM2.5/ozone scope |
| `NO` | nitric oxide | deferred; outside selected scope |
| `NO2` | nitrogen dioxide | deferred; outside selected scope |
| `NOX` | oxides of nitrogen | deferred; outside selected scope |
| `O3` | producer graph labels ozone in ppb | retrieved as `ozone_surface_mole_fraction`, numerically retained as nmol/mol |
| `SO2` | sulphur dioxide | deferred; outside selected scope |
| `CO` | carbon monoxide | deferred; outside selected scope |

The graph images linked from the publisher page are the direct unit authority:
`StJohns_PM2_5_Run_Avg.png` labels “PM2.5 Running 24 Hr Avg (ug/m3)” and
`StJohns_O3.png` labels “Ozone (ppb)”. Ozone is not mapped to the existing mass
concentration field because conversion from mole fraction to mass concentration
depends on atmospheric state that this file does not publish.

The CSV omits an explicit UTC offset. Its official XML twin represents the same
latest local instant as `2026-09-05T21:00:00-02:30`; the adapter uses the IANA
`America/St_Johns` rules rather than treating local wall time as UTC or a fixed
offset.

## Live receipt and comparison

- Actual bounded HTTP capture completed: `2026-09-06T03:47:49.524702Z`.
- Artifact/API replay uses that same HTTP completion instant as its candidate
  and `RunResult.retrieved_at`: `2026-09-06T03:47:49.524702Z`.
- URL: `https://www.mae.gov.nl.ca/wrmd/pp_adrs/Data/StJohns_Line.csv`.
- Parameters: none.
- HTTP response: 200, `application/octet-stream`; `Content-Length: 59197`;
  `Last-Modified: Sun, 06 Sep 2026 03:45:07 GMT`.
- Provider bytes: 59,197; SHA-256
  `0f4d5c067fc4d71ca70bb1536d4cfe05823a31ffebe747cc3e5363b0408ec36e`.
- Selected window: 22 rows from `2026-09-05T04:30:00Z` through
  `2026-09-06T01:30:00Z`; latest publisher wall time
  `2026-09-05T23:00:00-02:30`.
- Provider identity:
  `stjohns-provisional-202609060130-0f4d5c067fc4`.
- Immutable artifact: 5,844 bytes; SHA-256/revision
  `027942cc40d0590b02c14c46457e381c781476ae380a74d6e6a66474036fa4cb`.
- Actual FastAPI HTTP `/point` readback at the latest valid time: 200, live,
  `operational: false`; PM2.5 `5.900000000000001e-09 kg m-3`, ozone
  `16.1 nmol mol-1`; both `uncalibrated_observation`, quality `unknown` with
  `provisional` and `not_quality_controlled` flags.
- Direct provider comparison: latest CSV values were PM2.5 `5.9 µg/m³` and
  ozone `16.1 ppb`; the API result is the exact declared PM conversion and
  exact ozone identity conversion.

The raw CSV, XML, graph images and rebuilt artifact remain only under
`/private/tmp/astraeus-nl-air-quality-capture` for root hash/readback review.
They are not in Git.

Exact retained-byte replay command:

```sh
PYTHONPATH=api:. uv run --project api python scripts/capture-nl-air-quality.py \
  --scratch /private/tmp/astraeus-nl-air-quality-capture/final-verifiable/artifact \
  --provider-file /private/tmp/astraeus-nl-air-quality-capture/final-verifiable/StJohns_Line.csv \
  --captured-at 2026-09-06T03:47:49.524702Z
```

## Verification coverage and remaining limits

Fixture tests cover the exact ten-column schema, station identity, provisional
warning, local-time conversion, field units and interval, missing selected
values, invalid values, an empty window, upstream failure, and the 1 MiB byte
ceiling. The immutable artifact is reopened through the real `LiveStore`, then
read through the actual FastAPI `/point` route with provenance and
`operational: false` assertions.

The source contract and licence remain draft/restricted. There is no production
scheduler registration, science admission, verification use, display-primary
status, or redistribution grant. Provider publication cadence and the meaning
of missing cells beyond empty CSV fields remain unverified operational facts.

Spec-Refs: GOV-SPEC-001, GOV-SPEC-002, GOV-SPEC-004, GOV-SPEC-005, GOV-SPEC-006
