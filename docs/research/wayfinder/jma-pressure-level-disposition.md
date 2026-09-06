# JMA GSM pressure-level disposition

Research note, 2026-09-06. This is non-normative evidence for issue 143 and
the draft `experimental-openmeteo-brightsky` change. It does not authorize a
source-contract change, interpolation, source substitution, registration, or
scheduling.

## Finding

The four null surfaces are not an Astraeus decode or retrieval defect. The
global JMA GSM product does not publish 975, 950, 900, or 800 hPa. Open-Meteo's
JMA page presents the 16-level inventory of JMA's geographically limited
Japan-area product as API pressure-level choices even when `models=jma_gsm`
serves the global product. The API accepts those names and returns arrays of
JSON nulls. Astraeus preserves those masks and correctly leaves the
experimental profile incomplete and nonpublishable.

No current free native JMA path was found for these four levels over the
Avalon evidence box. JMA does publish them in its Japan-area GSM product, but
that product covers 20-50 N, 120-150 E. The Japan Meteorological Business
Support Center lists current online distribution with a charge, so it is also
outside this queue's no-charge constraint. An alternate global model is a
different source and cannot fill a JMA value.

## Producer inventory

JMA's current information catalogue distinguishes two products:

| Product | Geography | Native pressure inventory | Relative humidity |
|---|---|---|---|
| GSM global | global | 1000, 925, 850, 700, 600, 500, 400, 300, 250, 200, 150, 100, 70, 50, 30, 20, 10 hPa | 1000 through 300 hPa in that inventory |
| GSM Japan area | 20-50 N, 120-150 E | 1000, 975, 950, 925, 900, 850, 800, 700, 600, 500, 400, 300, 250, 200, 150, 100 hPa | 1000 through 300 hPa in that inventory |

Sources: JMA's [current product catalogue](https://www.data.jma.go.jp/suishin/cgi-bin/catalogue/make_product_page.cgi?id=ZenModel)
and [March 2025 technical notice](https://www.data.jma.go.jp/suishin/jyouhou/pdf/645.pdf).
The catalogue names the global and Japan-area products, fields, pressure
levels, grids, forecast ranges, cadence, and filenames separately.

As an independent artifact check, the official
[JMA GSM sample](https://www.data.jma.go.jp/developer/gpv_sample.html) was
downloaded with a 32 MB transfer ceiling and decoded with ecCodes multi-field
support. Its global file contains height, temperature, U/V wind, and vertical
velocity at 1000, 925, 850, 700, 600, 500, 400, 300, 250, 200, 150, 100, 70,
50, 30, 20, and 10 hPa; RH occurs at 1000 through 300 hPa. It contains none of
975, 950, 900, or 800 hPa. The ZIP was 26,683,943 bytes with SHA-256
`dc2935c9bf2fb5056273dda8d719054931af41b029089c1ea0b3dfc37f201b75`;
the 33,251,093-byte GRIB was
`2c9838ecd4b652e623d87ee91384c27fce4cd883ebdd4cd256a7ebed27450f1b`.
The sample and decoded GRIB remain available for independent review under
`/private/tmp/astraeus-jma-143-producer-20260906`; neither body is in Git.

## Intermediary behavior

Open-Meteo's official [JMA API documentation](https://open-meteo.com/en/docs/jma-api)
shows all 16 Japan-area pressure surfaces in its pressure-level selector and
lists `JMA GSM` as a model. The same page says the global GSM grid is 0.5
degrees and that only a limited JMA dataset is available. It does not explain
that four choices are unavailable for `jma_gsm` globally.

Open-Meteo's first-party implementation at commit
[`6c45053`](https://github.com/open-meteo/open-meteo/blob/6c45053fb1ef0c049de931292a0f5cb35f14c0ba/Sources/App/JMA/JmaDownloader.swift#L573-L582)
declares the `gsm` pressure levels separately from `msm_upper_level`; its GSM
list excludes 975, 950, 900, and 800 hPa, while the regional upper-level list
includes them. The downloader maps only GRIB messages actually present. This
supports an intermediary documentation/selection limitation rather than a
lost Astraeus array.

## Bounded current API evidence

Two forecast hours, 2026-09-06T06:00Z and 07:00Z, were requested from
`https://api.open-meteo.com/v1/forecast` with the exact `jma_gsm` selector.
Raw responses and headers remain in bounded local scratch at
`/private/tmp/astraeus-jma-143-live-20260906` for review and are excluded from
Git. The committed receipt contains hashes and sizes.

At St. John's, every one of temperature, RH, derived dew point, derived cloud
cover, wind speed, wind direction, vertical velocity, and geopotential height
was null at 975, 950, 900, and 800 hPa for both hours. Every family was finite
at the 925 hPa control. A second call requested canonical temperature and wind
speed/direction at the same five levels for St. John's, Tokyo, and 0 N / 0 E.
Each location produced 12 all-null arrays at the four disputed levels and
three finite arrays at 925 hPa. The result is invariant by field family, both
valid times, and tested geography.

A 16-level control at St. John's confirmed finite temperature and wind at
1000, 925, 850, 700, 600, 500, 400, 300, 250, 200, 150, and 100 hPa and nulls
only at the disputed four. RH is finite from 1000 through 300 on native levels
and null at 250 through 100, matching the producer's field-specific inventory.

## Disposition and owner decision

| Layer | Disposition | Evidence |
|---|---|---|
| JMA global producer | unavailable at the four levels | current catalogue and official GRIB sample |
| Open-Meteo intermediary | accepts advertised variable names but returns explicit nulls | current bounded calls at three locations |
| Astraeus adapter | no defect proven | retained response comparator, missing masks, incomplete verdict, and publication refusal already cover this shape |

The existing draft contract requires every advertised canonical level, and
issue 143 explicitly forbids silently removing required levels. The concrete
decision for `@TusharSariya` is one of these source-specific contracts:

1. **Keep partial/deferred.** Retain the current 16-level selection, all-null
   masks at 975/950/900/800 hPa, `complete=false`, and publication refusal.
   This is the current behavior and needs no adapter change.
2. **Propose a global-product contract.** Require canonical temperature and
   wind only at the 12 Open-Meteo-exposed native global levels from 1000 to
   100 hPa: 1000, 925, 850, 700, 600, 500, 400, 300, 250, 200, 150, and 100.
   Account for raw RH, derived dew point, and derived cloud only at 1000, 925,
   850, 700, 600, 500, 400, and 300 hPa. Account for vertical velocity and
   geopotential height at all 12. Explicitly mark 975/950/900/800 unsupported
   by the global producer product and keep the Japan-area 16-level product as
   a distinct, geographically ineligible access path. The producer also has
   70/50/30/20/10 hPa fields, but Open-Meteo does not advertise them in this
   API selection; they remain intermediary-unexposed rather than required.

Option 2 changes the experimental source contract and therefore needs owner
authority before code or OpenSpec requirement changes. Until then,
implementation is blocked by missing authority rather than code failure.
Vertical interpolation would create a derived value and needs separate
science and provenance authority; the Japan-area product and other models do
not replace JMA global evidence over Avalon.

The host reported 36 GiB free during this research. The 64 GiB constraint is
the experiment's hot-store quota, not a minimum free-disk margin. This bounded
producer inspection used about 60 MB and retained it for review.
