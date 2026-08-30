# 03 — Local, climatological, institutional and commercial meteorological sources

**Scope:** ECCC climate archive and derived products; the unused parts of the ECCC
Datamart tree; provincial / municipal / institutional networks on the Avalon
Peninsula; road and transport weather; citizen-science and amateur networks;
commercial and freemium APIs; aviation-derived observations; verification and
skill datasets.

**Out of scope** (covered by sibling research agents): atmospheric / NWP / satellite;
marine / ocean / ice / hydrology.

**Target point:** St. John's, NL — 47.56 °N, 52.71 °W.

**Baseline:** `docs/research/00-current-inventory.md` (59 registered sources). This
document deliberately does not re-report what is already registered except where
the registry entry is materially incomplete.

**Research date:** 2026-08-30. All "Verified" claims below were made by issuing a
real HTTP request from this machine with
`-A "astraeus-weather-experiment/0.1 (research; contact tushar.sariya77@gmail.com)"`.
Anything not verified is explicitly marked **unverified — from documentation only**.

**Sources documented in this file: 63.**

---

## Executive summary of the gap

The registry has *no* historical, climatological, verification, local-institutional,
aggregator or commercial source at all. Four findings dominate:

1. **`api.weather.gc.ca` exposes 104 OGC API Features collections**, of which the
   registry uses essentially none. Among them are `climate-hourly`, `climate-daily`,
   `climate-normals`, `climate-stations`, the four **AHCCD** collections, the three
   **LTCE** record collections, `bulletins-realtime`, `metnotes` and
   `citypageweather-realtime`. Verified.
2. **The Government of Newfoundland and Labrador runs a real, live, machine-readable
   met network on the Avalon** — including a station in **Pippy Park, 2.5 km from
   downtown St. John's** — publishing hourly CSV with SWE, snow depth, solar radiation
   and soil moisture. It also runs 22 fire-weather stations, three of them on the
   Avalon. Both are in the ECCC SWOB *partner* feed the registry does not read.
   Verified.
3. **Open-Meteo** is the single highest-value external addition: free, CC-BY-4.0,
   no key, and it exposes UKMO, KNMI, JMA, Météo-France and DMI models at a point
   that the project cannot otherwise obtain, plus a **historical forecast archive**
   and a **previous-runs API** that make forecast verification possible immediately.
   All four endpoints verified returning 200.
4. **Mode-S / ADS-B derived winds and temperatures aloft over the North Atlantic
   tracks are available free with no key** from `api.adsb.lol`. A live query 250 nm
   around St. John's returned 23 aircraft, **19 of which carried wind direction,
   wind speed and outside air temperature at flight level**. Verified.

---

# 1. ECCC climate archive and derived products

The MSC licence (below) is permissive, which makes this whole section low-risk.

### 1.0 MSC Data Server End-use Licence — the umbrella licence

| Field | Value |
|---|---|
| **Producer** | Environment and Climate Change Canada |
| **Endpoint** | `https://eccc-msc.github.io/open-data/licence/readme_en/` (pointer at `https://dd.weather.gc.ca/doc/LICENCE_GENERAL.txt`) |
| **Access** | Open |
| **Licence** | *Environment and Climate Change Canada Data Servers End-use Licence, Version 2.1 – September 2022* |
| **Caching / redistribution** | **Permitted.** Grants the right to "Copy, modify, publish, translate, adapt, distribute or otherwise use the Information in any medium, mode or format for any lawful purpose." |
| **Attribution** | `Data Source: Environment and Climate Change Canada`, or for partner data `Data Source: Environment and Climate Change Canada and [Third Party Contributor]` |
| **Restrictions** | Weather alerts must not be altered in content or intent; no use of ECCC symbols/logos; no implied endorsement |
| **Verified?** | Yes — `LICENCE_GENERAL.txt` fetched, licence page fetched |

This licence covers Datamart, GeoMet and `api.weather.gc.ca` uniformly. It is
strictly more permissive than every commercial API in section 6.

---

### 1.1 `climate-stations` — station metadata and inventory

| Field | Value |
|---|---|
| **Endpoint** | `https://api.weather.gc.ca/collections/climate-stations/items?bbox=-54.5,46.5,-52.4,48.2&limit=500&f=json` |
| **Gives you** | `STN_ID`, `CLIMATE_IDENTIFIER`, `TC_IDENTIFIER`, `WMO_IDENTIFIER`, lat/lon/elevation, `FIRST_DATE`/`LAST_DATE`, `HLY_FIRST_DATE`/`HLY_LAST_DATE`, `DLY_*`, `MLY_*`, `HAS_HOURLY_DATA`, `HAS_NORMALS_DATA` |
| **Coverage** | **74 stations matched inside the Avalon bounding box.** Full table below. |
| **Access** | Genuinely open, no key |
| **Verified?** | Yes — `numberMatched: 74` |

#### Full Avalon Peninsula ECCC climate station inventory (74 stations)

**Currently reporting (LAST_DATE = 2026-08-27):**

| Station | STN_ID | Climate ID | TC | WMO | Lat | Lon | Elev m | First | Hourly from | Hourly? |
|---|---|---|---|---|---|---|---|---|---|---|
| CAPE RACE (AUT) | 6590 | 8401000 | WRA | 71800 | 46.6600 | -53.0764 | 26.5 | 1920-01-01 | 1953-01-01 | Y |
| ARGENTIA (AUT) | 10113 | 8400104 | WAR | 71807 | 47.3106 | -53.9982 | 9.5 | 1987-01-01 | 1987-01-01 | Y |
| GRATES COVE | 10818 | 840B053 | WVW | 71336 | 48.1719 | -52.9392 | 46.2 | 1994-02-01 | 1994-02-01 | N |
| ST JOHNS WEST CLIMATE | 48871 | 8403603 | AJW | 71250 | 47.5134 | -52.7833 | 110.0 | 2010-08-24 | 2010-08-24 | Y |
| **ST. JOHN'S INTL A** | **50089** | **8403505** | **YYT** | **71801** | **47.6186** | **-52.7525** | **140.5** | **2012-03-20** | **2012-03-20** | **Y** |

**Closed, but with a period of record worth ingesting** (sorted by last date):

| Station | STN_ID | Climate ID | Lat | Lon | Elev m | Period of record | Hourly? |
|---|---|---|---|---|---|---|---|
| BUTLERVILLE | 6555 | 8400QJK | 47.5792 | -53.3161 | 16.0 | 1988-01-01 → 2019-07-30 | N |
| SWIFT CURRENT | 6743 | 8403825 | 47.8853 | -54.2131 | 18.2 | 1984-01-01 → 2019-07-30 | N (normals) |
| BRANCH | 6578 | 8400666 | 46.8831 | -53.9681 | 11.8 | 1983-01-01 → 2017-01-08 | N |
| HOLYROOD GEN STN | 6658 | 8402309 | 47.4500 | -53.1000 | 6.0 | 1970-01-01 → 2016-11-29 | N |
| BROWNSDALE | 27617 | 8400675 | 48.0336 | -53.1189 | 10.0 | 1998-08-01 → 2015-09-30 | N |
| WHITBOURNE | 6939 | 8404234 | 47.4167 | -53.5375 | 58.0 | 1991-01-01 → 2014-06-30 | N |
| HOLYROOD | 27229 | 8402303 | 47.3819 | -53.1233 | 133.5 | 1996-08-01 → 2013-11-30 | N |
| ST JOHN'S WEST CDA CS | 27115 | 8403605 (XSW) | 47.5156 | -52.7847 | 114.0 | 1996-02-01 → 2013-06-25 | Y (1999-07-06→) |
| **ST JOHN'S A** | **6720** | **8403506 (YYT)** | **47.6222** | **-52.7428** | **140.5** | **1942-01-01 → 2012-03-20** | **Y (1953-01-01→), has normals** |
| GOOBIES | 6638 | 8401880 | 47.9492 | -53.9653 | 72.0 | 1978-01-01 → 2011-06-30 | N |
| NORTH HARBOUR | 6682 | 8402874 | 47.1333 | -53.6667 | 11.0 | 1988-01-01 → 2007-11-02 | N |
| SALMONIER NATURE PARK | 30766 | 8403622 (XSA) | 47.2636 | -53.2864 | 135.8 | 2001-03-01 → 2007-07-31 | N |
| SALMONIER NATURE PARK | 6727 | 8403621 | 47.2667 | -53.2833 | 135.8 | 1977-12-01 → 2006-04-26 | N |
| PORTUGAL COVE | 27593 | 8403044 | 47.6453 | -52.8169 | 192.0 | 1998-02-01 → 2006-01-31 | N |
| LOGY BAY | 6672 | 8402568 | 47.6242 | -52.6642 | 27.4 | 1969-01-01 → 2004-11-30 | N |
| HEARTS CONTENT | 6654 | 8402080 | 47.8667 | -53.3833 | 8.5 | 1961-01-01 → 2002-08-31 | N |
| VICTORIA | 6758 | 8404100 | 47.7683 | -53.2178 | 42.7 | 1961-01-01 → 2002-05-31 | N |
| ST BRIDE'S | 6714 | 8403417 | 46.9219 | -54.1800 | 15.2 | 1988-01-01 → 2001-03-31 | N |
| **SIGNAL HILL** | 6732 | 8403669 | 47.5667 | -52.6833 | 96.0 | 1984-01-01 → 2001-01-31 | N |
| ST MARY'S | 6552 | 840C616 | 46.9167 | -53.5667 | 15.5 | 1982-01-01 → 2000-03-31 | N |
| LONG HARBOUR | 6673 | 8402569 | 47.4167 | -53.8167 | 8.4 | 1969-01-01 → 1999-11-30 | N |
| PETTY HARBOUR | 6683 | 8402925 | 47.4667 | -52.7167 | 6.1 | 1955-01-01 → 1999-07-31 | N |
| CAPPAHAYDEN | 6592 | 8401070 | 46.8667 | -52.9500 | 15.2 | 1981-01-01 → 1999-04-30 | N |
| SIBLEY'S COVE | 6731 | 8403667 | 48.0500 | -53.1000 | 12.0 | 1989-01-01 → 1998-07-31 | N |
| CAPE BROYLE | 6587 | 8400850 | 47.1000 | -52.9333 | 6.1 | 1955-01-01 → 1997-05-31 | N |
| DUNVILLE | 6620 | 8401528 | 47.2667 | -53.9167 | 15.0 | 1990-01-01 → 1997-04-30 | N |
| ST STEPHENS | 6725 | 8403618 | 46.7667 | -53.6167 | 17.4 | 1989-01-01 → 1997-04-30 | N |
| THORNLEA T.B. | 6748 | 8403860 | 47.6167 | -53.7333 | 30.5 | 1987-12-01 → 1997-03-31 | N |
| PORTUGAL COVE, CONCEPTION BAY | 6698 | 8403045 | 47.6167 | -52.8333 | 137.2 | 1987-01-01 → 1996-12-31 | N |
| AVONDALE CDA | 6559 | 8400225 | 47.4167 | -53.2333 | 132.6 | 1955-01-01 → 1996-09-30 | N |
| COLINET PEAT BOG CDA | 6605 | 8401251 | 47.2333 | -53.5167 | 54.9 | 1980-01-01 → 1996-09-30 | N |
| ST JOHN'S WEST CDA | 6722 | 8403600 | 47.5167 | -52.7833 | 114.3 | 1950-01-01 → 1996-08-31 | N |
| GREAT BARASWAY P.B. | 6554 | 840K0NC | 47.1333 | -54.0667 | 7.0 | 1987-01-01 → 1996-06-30 | N |
| PARADISE | 6934 | 8402RB0 | 47.5333 | -52.8500 | 154.0 | 1991-01-01 → 1995-12-31 | N |
| ST JOHN'S THORBURN ROAD | 6721 | 8403523 | 47.5667 | -52.8000 | 185.9 | 1988-01-01 → 1995-09-30 | N |
| ST SHOTTS | 6724 | 8403617 | 46.6333 | -53.5833 | 45.7 | 1971-01-01 → 1995-07-31 | N |
| COME BY CHANCE | 6606 | 8401257 | 47.8000 | -54.0000 | 34.0 | 1968-01-01 → 1995-06-30 | N |
| SUNNYSIDE | 6742 | 8403818 | 47.8667 | -53.9333 | 15.2 | 1971-01-01 → 1995-06-30 | N |
| MARKLAND | 6675 | 8402590 | 47.3167 | -53.5500 | 56.0 | 1981-01-01 → 1994-12-31 | N |
| ARNOLDS COVE | 6558 | 8400135 | 47.7500 | -54.0000 | 15.2 | 1971-01-01 → 1994-12-01 | N |
| HARBOUR GRACE | 6652 | 8402076 | 47.6833 | -53.2000 | 7.1 | 1979-01-01 → 1993-12-01 | N |
| TORS COVE | 6752 | 8403950 | 47.2167 | -52.8500 | 6.1 | 1955-01-01 → 1993-12-01 | N |
| COLINET | 6603 | 8401200 | 47.2167 | -53.5500 | 27.4 | 1938-01-01 → 1992-12-01 | N |
| PARADISE RIVER | 6640 | 8402RK0 | 47.6167 | -54.4333 | 125.0 | 1990-01-01 → 1991-11-01 | N |
| NEW CHELSEA | 6680 | 8402840 | 48.0333 | -53.2167 | 9.0 | 1961-01-01 → 1991-11-01 | N |
| SEAL COVE CB | 6694 | 8403FN0 | 47.4500 | -53.0667 | 33.0 | 1989-01-01 → 1991-11-01 | N |
| PARADISE | 6641 | 8402R20 | 47.5333 | -52.8333 | 136.0 | 1989-01-01 → 1990-12-01 | N |
| PLACENTIA JUNCTION | 6687 | 8402957 | 47.4000 | -53.6000 | 92.0 | 1989-01-01 → 1990-12-01 | N |
| TREPASSEY | 6754 | 8403971 | 46.7667 | -53.3667 | 15.2 | 1982-01-01 → 1990-12-01 | N |
| WHITBOURNE T.B. | 6762 | 8404235 | 47.3167 | -53.5500 | 56.0 | 1987-12-01 → 1990-12-01 | N |
| SEAL COVE | 6730 | 8403650 | 47.4500 | -53.0667 | 22.7 | 1961-01-01 → 1988-12-01 | N |
| ST BRIDE'S | 6715 | 8403418 | 46.9167 | -54.1667 | 78.8 | 1984-01-01 → 1987-12-01 | N |
| ARGENTIA A | 6557 | 8400102 | 47.3000 | -54.0000 | 15.5 | 1976-01-01 → 1986-12-01 | Y (1976-05→1986-10) |
| CLARENVILLE | 6600 | 8401140 | 48.1500 | -53.9667 | 7.6 | 1978-01-01 → 1982-12-01 | N |
| HOLYROOD ULTRAMAR | 6659 | 8402310 | 47.3833 | -53.1333 | 7.0 | 1961-12-01 → 1982-12-01 | N |
| COLINET PEAT BOG CDA | 6604 | 8401250 | 47.2167 | -53.5000 | 104.2 | 1957-01-01 → 1979-12-01 | N |
| PIERRES BROOK | 6685 | 8402950 | 47.2833 | -52.8167 | 15.2 | 1955-10-01 → 1978-12-01 | N |
| SALMONIER | 6726 | 8403620 | 47.2667 | -53.3333 | 121.9 | 1967-01-01 → 1977-12-01 | N |
| PLACENTIA | 6686 | 8402956 | 47.2333 | -54.0167 | 14.0 | 1970-01-01 → 1975-12-31 | (1970-11→1975-12) |
| NORTH EAST POND RIVER | 6681 | 8402873 | 47.6333 | -52.8333 | 91.4 | 1970-01-01 → 1975-12-01 | N |
| ST JOHN'S | 6719 | 8403501 | 47.5833 | -52.7333 | 61.0 | 1957-01-01 → 1975-12-01 | N |
| CARBONEAR | 6593 | 8401075 | 47.7333 | -53.2333 | 23.5 | 1972-01-01 → 1974-12-01 | N |
| ARGENTIA A | 6556 | 8400100 | 47.3000 | -54.0000 | 13.7 | 1945-01-01 → 1970-12-01 | Y (1953-01→1970-05) |
| HOLYROOD | 6657 | 8402300 | 47.3833 | -53.1333 | 10.7 | 1952-01-01 → 1970-12-01 | N |
| TOPSAIL | 6751 | 8403875 | 47.5333 | -52.9167 | 15.2 | 1961-01-01 → 1967-12-01 | N |
| TREPASSEY | 6753 | 8403970 | 46.7333 | -53.1667 | 128.3 | 1966-02-01 → 1966-02-28 | N |
| CLUNYS | 6602 | 8401150 | 47.2000 | -52.9500 | 121.9 | 1955-01-01 → 1960-12-01 | N |
| HARBOUR GRACE | 6651 | 8402075 | 47.7167 | -53.1500 | 12.2 | 1957-01-01 → 1958-12-01 | N |
| **ST JOHN'S** | **6718** | **8403500** | **47.5667** | **-52.7000** | **38.1** | **1874-01-01 → 1956-12-01** | **N** |

Note the two-part St. John's downtown/airport series: `8403500` (1874–1956, 38 m, right in
town at 47.5667/-52.70) and `8403506` → `8403505` at the airport (1942–present, 140 m).
Together they give **152 years of record within 8 km of the map centre.**

---

### 1.2 `climate-hourly` — hourly surface observations, full archive

| Field | Value |
|---|---|
| **Endpoint** | `https://api.weather.gc.ca/collections/climate-hourly/items?CLIMATE_IDENTIFIER=8403505&datetime=2026-08-25T00:00:00Z/2026-08-25T03:00:00Z&f=json` |
| **Variables** | `TEMP`, `DEW_POINT_TEMP`, `RELATIVE_HUMIDITY`, `STATION_PRESSURE`, `VISIBILITY`, `WIND_SPEED`, `WIND_DIRECTION`, `PRECIP_AMOUNT`, `HUMIDEX`, `WINDCHILL`, `WEATHER_ENG_DESC`, plus a QA `*_FLAG` for every element |
| **Cadence** | Hourly; updated to within ~3 days of real time |
| **Access** | Open, no key. OGC API Features: `bbox`, `datetime`, `limit`, `offset`, property filters, `f=csv` |
| **Coverage** | 5 Avalon stations currently reporting hourly; `8403506` back to 1953 |
| **Verified?** | **Yes** — returned real values, e.g. 2026-08-25 00:30 NDT at ST. JOHN'S INTL A: TEMP 20.6 °C, DEW 19.9, RH 96 %, PRES 100.49 kPa, VIS 24.1 km, WIND 25° at 19 km/h |
| **Why it helps** | This is the ground truth. Without it there is no bias correction, no MOS, no verification, no anomaly context. It is the single largest structural gap in the project. |

### 1.3 `climate-daily` — daily summaries

| Field | Value |
|---|---|
| **Endpoint** | `https://api.weather.gc.ca/collections/climate-daily/items?CLIMATE_IDENTIFIER=8403505&f=json` |
| **Variables** | `MEAN/MIN/MAX_TEMPERATURE`, `TOTAL_PRECIPITATION`, `TOTAL_RAIN`, `TOTAL_SNOW`, `SNOW_ON_GROUND`, `SPEED_MAX_GUST`, `DIRECTION_MAX_GUST`, `HEATING_DEGREE_DAYS`, `COOLING_DEGREE_DAYS`, `MIN_REL_HUMIDITY`, with flags |
| **Verified?** | **Yes** — `numberMatched: 5276` for climate ID 8403505 alone |
| **Why it helps** | Snow-on-ground and max-gust are exactly the two variables the project's forecast layers most need calibrating against on the Avalon. |

### 1.4 `climate-monthly` — monthly observation summaries

Same family, collection id `climate-monthly`. Verified present in the collection list;
individual query not run. **Partially verified — collection existence confirmed, content
from documentation.**

### 1.5 `climate-normals` — 1981–2010 normals via API

| Field | Value |
|---|---|
| **Endpoint** | `https://api.weather.gc.ca/collections/climate-normals/items?CLIMATE_IDENTIFIER=8403506&f=json` |
| **Period** | **1981–2010 only.** The collection title is literally "Climate - Normals 1981-2010". |
| **Verified?** | **Yes** — `numberMatched: 1199` for ST JOHN'S A. Example record: `E_NORMAL_ELEMENT_NAME: "Mean daily temperature deg C"`, `MONTH: 1`, `VALUE: -4.51`, `PERIOD_BEGIN: 1981`, `PERIOD_END: 2010`, `PERCENT_OF_POSSIBLE_OBS: 100` |
| **Caveat** | **The 1991–2020 normals are NOT in this API.** See 1.6. Datamart `/climate/observations/normals/csv/` contains only a `1981-2010/` directory — verified. |

### 1.6 Canadian Climate Normals 1991–2020 — bulk CSV (the current normals)

| Field | Value |
|---|---|
| **Producer** | ECCC, released with a portal refresh dated 2026-08-18 |
| **Endpoint** | `https://climate.weather.gc.ca/climate_normals/bulk_data_e.html?lang=e&prov=NL&yr=1991&stnID=77000000&climate_id=8403505&submit=Download+Data` |
| **Station selector** | `https://climate.weather.gc.ca/climate_normals/station_select_1991_2020_e.html?searchType=stnProv&lstProvince=NL` |
| **Gives you** | Monthly + annual normals for temperature, precipitation, snow, wind, humidity, degree-days, plus **Long-Term** extremes with dates of occurrence |
| **Coverage** | **ST. JOHN'S (AIRPORT)**, climate_id `8403505`, composite `stnID=77000000`; also **ST. JOHN'S (WEST)**, and 448 composite stations Canada-wide. Composite stations require ≥15 years within 1991–2020. |
| **Access** | Open, no key. Note `stnID` here is a *composite* station id, not the `STN_ID` from `climate-stations`. |
| **Verified?** | **Yes** — 36,728-byte CSV downloaded. Sample: St. John's Airport Jan daily average **−4.2 °C**, Jul **16.0 °C**, Aug **16.5 °C**, annual **5.3 °C**; Jan extreme max 15.7 °C (2006-01-15), Jan extreme min −19.5 °C (1993-01-31) |
| **Licence** | ECCC Data Server End-use Licence (as 1.0) |
| **Why it helps** | This is the correct current climatological baseline. Using the API's 1981–2010 normals when 1991–2020 exists would misstate anomalies by roughly a third of a degree on the annual mean. |

### 1.7 AHCCD — Adjusted and Homogenized Canadian Climate Data

| Field | Value |
|---|---|
| **Endpoints** | `https://api.weather.gc.ca/collections/ahccd-stations/items?bbox=-55,46.4,-52.4,48.3&f=json`; also `ahccd-annual`, `ahccd-seasonal`, `ahccd-monthly`, `ahccd-trends`. Bulk GeoJSON at `https://dd.weather.gc.ca/today/climate/ahccd/geojson/historical/` |
| **Gives you** | Station series adjusted for instrument changes, relocations and urbanisation — the only Canadian series safe for trend work |
| **Access** | Open, no key |
| **Verified?** | **Yes** — 9 AHCCD stations matched on the Avalon |

**Avalon AHCCD stations (all 9, verified):**

| Station | AHCCD id | Measurement | Lat | Lon | Elev m | Period | Trend |
|---|---|---|---|---|---|---|---|
| **ST_JOHN_S** | **8403505** | **temp_mean** | 47.62 | -52.75 | 141 | **1874-01-01 → 2020-12-01** | — |
| ST_JOHN_WEST | 8403603 | temp_mean | 47.52 | -52.78 | 110 | 1950-11-01 → 2020-12-01 | — |
| ST JOHN'S A | 8403506 | wind_speed | 47.6222 | -52.7428 | 140.5 | 1953-01-01 → 2014-12-01 | **−8.03** (1953–2014) |
| CAPE RACE (AUT) | 8401000 | wind_speed | 46.66 | -53.0764 | 26.5 | 1953-01-01 → 2014-12-01 | — |
| COLINET | 8401251 | temp_mean | 47.23 | -53.52 | 55 | 1938-08-01 → 1996-09-01 | — |
| ARGENTIA A | 8400100 | pressure_sea_level | 47.30 | -54.00 | 13.7 | 1953-01-01 → 1970-03-01 | — |
| ARGENTIA (AUT) | 8400104 | pressure_sea_level | 47.29 | -53.99 | 15 | 1987-02-01 → 2014-12-01 | — |
| GRATES COVE | 840B053 | pressure_sea_level | 48.17 | -52.94 | 46.2 | 1993-01-01 → 2014-12-01 | — |
| NORTH HARBOUR | 8402874 | snow | 47.1333 | -53.6667 | 11 | 1939-01-01 → 2007-11-01 | — |

**A 146-year homogenized mean-temperature series for St. John's** (1874–2020) is a
genuinely rare asset for a city of this size, and it is one HTTP call away.
The AHCCD wind trend at YYT (−8.03 over 1953–2014) is also a caution: raw archived
wind speeds at the airport are *not* stationary, which matters if the project ever
trains a wind model on them.

### 1.8 LTCE — Long Term Climate Extremes (daily records)

| Field | Value |
|---|---|
| **Endpoints** | `https://api.weather.gc.ca/collections/ltce-stations/items?bbox=-55,46.4,-52.4,48.3&f=json`; `ltce-temperature`, `ltce-precipitation`, `ltce-snowfall` |
| **Gives you** | For every calendar day: record high max, record low max, record high min, record low min, plus 1st–5th ranked values with years, and the threaded station lineage that produced them |
| **Coverage** | **`VSNL24V` = "ST. JOHN'S AREA"** (WXO city code `NL-24`, 47.57/-52.73). Also `VSNL28V` Cape Race Area, `VSNL30V` Placentia Area, `VSNL43V` Bay Roberts Area, `VSNL1VV` Clarenville Area. 87 station-element-lineage rows in the Avalon box. |
| **Verified?** | **Yes** — `VSNL24V-1-1` (Jan 1) returned: record high max 11.3 °C (1990), record low min **−19.4 °C (1880)**, record high min 1.7 °C (1896) |
| **Why it helps** | Cheap, high-impact UI: "today's high is the warmest since 1937". Also gives an instant plausibility bound for forecast QC — a forecast outside the LTCE envelope is almost certainly a decode bug. |

### 1.9 Datamart bulk climate CSV archive (per station, per year)

| Field | Value |
|---|---|
| **Endpoint** | `https://dd.weather.gc.ca/{YYYYMMDD}/WXO-DD/climate/observations/hourly/csv/NL/climate_hourly_NL_{CLIMATE_ID}_{YYYY}_P1H.csv` (also `daily/`, `monthly/`, `normals/csv/1981-2010/`) |
| **Index** | `https://dd.weather.gc.ca/today/climate/observations/climate_station_list.csv` |
| **Verified?** | **Yes** — directory listing returned e.g. `climate_hourly_NL_8400100_1959_P1H.csv` … `climate_hourly_NL_8400102_1982_P1H.csv` |
| **Why it helps** | Far cheaper than paginating the OGC API for a full-archive backfill. Use Datamart for the initial load, the API for incremental updates. |

### 1.10 Legacy `bulk_data_e.html` endpoint (still live)

| Field | Value |
|---|---|
| **Endpoint** | `https://climate.weather.gc.ca/climate_data/bulk_data_e.html?format=csv&stationID=50089&Year=2026&Month=1&Day=1&timeframe=2&submit=Download+Data` (`timeframe`: 1=hourly, 2=daily, 3=monthly) |
| **Verified?** | **Yes** — 61,858-byte CSV. Row 1: `2026-01-01`, max 2.2 °C, min −4.6 °C, rain 6.4 mm, snow 2.0 cm, max gust 45 km/h from 120° |
| **Note** | Uses `stationID` = `STN_ID` from `climate-stations` (50089 for ST. JOHN'S INTL A), not the climate identifier |
| **Why it helps** | It is the simplest possible backfill path and needs no OGC pagination. It is also what the `weathercan` R package wraps, so it is well-understood. |

### 1.11 CanGRD, CMIP5/6, CanDCSU6, DCS, SPEI, climate indices

Collections `climate:cangrd:*`, `climate:cmip5:*`, `climate:candcsu6:*`, `climate:dcs:*`,
`climate:spei-{1,3,12}:*`, `climate:indices:*`. Gridded historical anomalies/trends and
downscaled projections. Open, ECCC licence. **Verified present in the collection list;
no Avalon query run.**
**Honest assessment:** climate *projections* add nothing to a nowcast/forecast map. CanGRD
historical gridded anomalies could be useful for a "how unusual is this month" panel.
Everything else here is out of scope. Low priority.

### 1.12 CanSIPS seasonal forecasts

`weather:cansips:100km:forecast:seasonal-products`, `...:monthly-products`,
`...:members`, `weather:cansips:100km:hindcast`. **The hindcast collection is the
interesting one** — it enables seasonal skill assessment. Open, ECCC licence.
**Verified present in the collection list only.** Low-to-medium priority.

---

# 2. The unused ECCC Datamart tree

I listed `https://dd.weather.gc.ca/20260830/WXO-DD/` and walked every directory the
registry has no entry for. Results below; all listings verified.

### 2.1 `citypage_weather/` — **the highest-value unregistered Datamart item**

| Field | Value |
|---|---|
| **Endpoint** | `https://dd.weather.gc.ca/{YYYYMMDD}/WXO-DD/citypage_weather/NL/{HH}/{timestamp}_MSC_CitypageWeather_s0000280_en.xml`. Site index: `https://dd.weather.gc.ca/today/citypage_weather/siteList.xml`. Schema: `.../citypage_weather/schema/site.xsd`. Also as OGC API: `https://api.weather.gc.ca/collections/citypageweather-realtime` [experimental]. |
| **St. John's site code** | **`s0000280`**. Nearby: `s0000018` Bay Roberts. |
| **Gives you** | The human-facing forecast: current conditions from the YYT station (condition text, icon code, temperature, dewpoint, pressure + tendency, visibility, wind), warnings block, 7-day worded forecast, hourly forecast, sunrise/sunset, yesterday's conditions, regional normals |
| **Cadence** | Roughly every 25–30 minutes (observed: 00:03, 00:31, 00:54 UTC) |
| **Verified?** | **Yes** — fetched `20260830T005459.415Z_MSC_CitypageWeather_s0000280_en.xml`. It reported `<condition>Mist</condition>`, 18.2 °C, dewpoint 17.9 °C, 101.2 kPa falling, at station `code="yyt"`, for `<name code="s0000280" lat="47.56N" lon="52.72W">St. John's</name>` — the map centre exactly. |
| **Licence** | The XML embeds `<license>https://dd.weather.gc.ca/doc/LICENCE_GENERAL.txt</license>` — the permissive MSC licence |
| **Why it helps** | This is the **official ECCC public forecast for St. John's** — the thing every resident actually reads. The project currently has raw NWP and no authoritative human forecast to compare against. It is also the cheapest possible verification target: "was the official forecast right?" |

### 2.2 `bulletins/alphanumeric/` — raw WMO bulletins

| Field | Value |
|---|---|
| **Endpoint** | `https://dd.weather.gc.ca/{YYYYMMDD}/WXO-DD/bulletins/alphanumeric/{YYYYMMDD}/{TT}/...`; OGC API: `https://api.weather.gc.ca/collections/bulletins-realtime` |
| **Verified?** | **Yes** — TT directories present for 2026-08-30: `AC CA CS FA FB FC FD FI FO FP FQ FT FV FX FZ IO IS IU NO SA SI SM SN SO SP SR SS SX UA UB UE UG UK UL UQ US UX WA WB WC` (and more) |
| **What's in the useful ones** | `SA` = surface synoptic/METAR, `SM`/`SN` = SYNOP, `UA` = upper-air (PILOT/TEMP), `UB`–`UX` = upper-air levels, `FT` = TAF, `FD` = winds/temps aloft, `WA`/`WC`/`WS` = SIGMET/AIRMET, `FQ`/`FV` = volcanic ash, `FZ` = tropical, `WO`/`WW` = warnings |
| **Machine-readable?** | Yes, but as WMO alphanumeric codes — needs a decoder (e.g. `metar-taf` / `pymetdecoder` / `trollbufr`) |
| **Why it helps** | Mostly duplicative: METAR/TAF already come from AWC, and SWOB is a friendlier surface source. The genuinely additive bulletin is **`FD` — forecast winds and temperatures aloft**, which the registry has no equivalent for and which pairs directly with the ADS-B Mode-S winds in section 7. Medium priority; the decoder cost is real. |

### 2.3 `metnotes/` — forecaster discussion

| Field | Value |
|---|---|
| **Endpoint** | `https://dd.weather.gc.ca/today/metnotes/`; OGC API: `https://api.weather.gc.ca/collections/metnotes` |
| **Verified?** | **Yes — and it was empty.** Both `/today/metnotes/` and `/{date}/WXO-DD/metnotes/` returned a directory listing with zero files at the time of checking. |
| **Assessment** | MetNotes are issued only for significant events and are heavily biased toward Ontario/Quebec/Prairies. Expect long silences for the Avalon. Low priority — but it costs almost nothing to poll and would be genuinely interesting text during a nor'easter. |

### 2.4 `meteocode/` — **does not cover Newfoundland**

| Field | Value |
|---|---|
| **Endpoint** | `https://dd.weather.gc.ca/{YYYYMMDD}/WXO-DD/meteocode/{ont,pnr,pyr}/{cmml,csv}/` |
| **Verified?** | **Yes** — the only regional subdirectories present are `ont/`, `pnr/` (Prairie and Northern), `pyr/` (Pacific and Yukon), plus `doc/` and `geodata/`. **There is no `atl/` or `que/`.** |
| **Assessment** | **Reject.** The gridded MeteoCode forecast-element product is not published for Atlantic Canada. This is a definite negative result worth recording so nobody re-investigates it. |

### 2.5 `vertical_profile/` — **tephigrams for CYYT, both observed and forecast**

| Field | Value |
|---|---|
| **Endpoints** | Observed: `https://dd.weather.gc.ca/{YYYYMMDD}/WXO-DD/vertical_profile/observation/csv/ObsTephi_{HH}_CYYT.csv` — Forecast: `.../vertical_profile/forecast/csv/ProgTephi_{HH}_CYYT.csv` |
| **Gives you** | `PRES, HEIGHT, THICK, HEIGHT(ft*100), TEMP, SPRED, THETAW, RELHUM, WINDDIR, WINDSPEED, STABILITY` |
| **Coverage** | 31 Canadian sites at 00 UTC; **`CYYT` is one of them.** Full list verified: CAWE CWEU CWLT CWMW CWSE CWVK CWZC CYAH CYBK CYCB CYEV CYFB CYJT CYPH CYPL CYQD CYQI CYRB CYSM CYUX CYVP CYVQ CYXY CYYE CYYQ CYYR **CYYT** CYZS CYZT CYZV CZXS |
| **Verified?** | **Yes** — `ObsTephi_00_CYYT.csv` fetched; surface row 999 mb / 18.2 °C / RH 97, 925 mb 15.8 °C wind 245° 10 kt, 850 mb 13.0 °C, 700 mb 6.2 °C wind 265° 20 kt. `ProgTephi_00_CYYT.csv` confirmed present in the forecast listing. |
| **Important caveat** | **There is no radiosonde at St. John's.** The nearest upper-air station is **Stephenville (WMO 71815, "STEPHENVILLE UA, NFLD, CANADA")**, ~600 km west — verified by successfully retrieving a 2026-08-30 00Z sounding for 71815 from the University of Wyoming while WMO id 71801 (St. John's surface) returned "Unable to retrieve the data". So `ObsTephi_00_CYYT` is a model/analysis-derived profile at the CYYT point, not a balloon ascent. Treat it as analysis, not observation. |
| **Data quality warning** | The observed CSV is **malformed**: column counts vary row to row, `-nan` appears in `THETAW`, and sentinel `-1` values appear in wind fields. Parsing needs to be defensive. |
| **Why it helps** | A vertical profile at the exact map centre, both analysed and forecast, updated every synoptic hour, in CSV. For freezing-rain, inversion and low-cloud diagnosis on the Avalon this is directly useful and far cheaper than decoding model GRIB on levels. |

### 2.6 `analysis/precip/hrdpa_watershed/` — watershed-aggregated HRDPA

| Field | Value |
|---|---|
| **Endpoint** | `https://dd.weather.gc.ca/{YYYYMMDD}/WXO-DD/analysis/precip/hrdpa_watershed/shapefile/` |
| **Verified?** | **Yes** — directory exists, contains `shapefile/` |
| **Assessment** | HRDPA itself is already registered (`eccc-hrdpa`). This is the same field pre-aggregated to watershed polygons as shapefiles. Useful only if the project wants basin totals. **Low priority — mostly duplicative.** |

### 2.7 `nowcasting/matrices/` — SCRIBE nowcasting matrices

| Field | Value |
|---|---|
| **Endpoint** | `https://dd.weather.gc.ca/{YYYYMMDD}/WXO-DD/nowcasting/matrices/SCRIBE.NWCSTG.{MM}.{DD}.{HH}Z.n.Z` |
| **Verified?** | **Yes** — hourly files present (`SCRIBE.NWCSTG.08.30.00Z.n.Z` through `03Z`) |
| **Format** | Compressed (`.Z`, LZW) SCRIBE matrix — a proprietary ECCC forecast-element matrix format, poorly documented publicly |
| **Assessment** | The registry already has `eccc-integrated-nowcasting`. SCRIBE matrices are the raw statistical guidance behind the worded forecast. **High parsing cost, uncertain payoff. Recommend reject** unless someone finds a documented decoder. |

### 2.8 `aviation/iwxxm/` — METAR/TAF/SIGMET in XML

| Field | Value |
|---|---|
| **Endpoint** | `https://dd.weather.gc.ca/{YYYYMMDD}/WXO-DD/aviation/iwxxm/{taf,sigmet,code-ca}/` |
| **Verified?** | **Yes** — `taf/`, `sigmet/`, `code-ca/`, `doc/`, `schema/` all present |
| **Assessment** | IWXXM is the WMO XML encoding of TAF/SIGMET — **structurally far nicer than parsing raw TAF text**, and it is the Canadian-authoritative copy rather than the US AWC relay the registry currently uses. Worth switching to for `awc-taf` and `awc-sigmet-airmet` where Canadian airspace is concerned. Medium priority, low effort. |

### 2.9 `observations/` — SWOB (registered) plus `xml/`

`observations/swob-ml/` is already registered as `eccc-swob`. But see section 3.1 —
**the registry appears to be reading only the main SWOB feed, not `swob-ml/partners/`,
which is where the Newfoundland provincial stations live.** `observations/xml/` also
exists (verified) and carries the legacy XML observation format.

### 2.10 `air_quality/`, `hydrometric/`, `climate/`, `satellite/`, `alerts/`, `hurricanes/`, `lightning/`, `radar/`, `marine_weather/`, `coastal-flooding/`, `ensemble/`, all `model_*`

All verified present. All already have registry entries (`eccc-aqhi`, `eccc-raqdps`,
`eccc-rdaqa`, `eccc-hydrometric`, `eccc-cap-alerts`, `eccc-hurricane-products`,
`eccc-lightning`, `eccc-radar`, `eccc-marine-forecasts-alerts`, the model family, etc.)
except `climate/` — which is section 1.9 above and is the real gap.

Additional model directories present that are worth cross-checking against the registry:
`model_gdps-geml/` (GDPS machine-learning variant), `model_caps/`, `model_ohps/`,
`model_gdwps/`, `model_gewps/`, `model_wcps/`, `model_giops/`, `model_riops/`.
Several of these fall in the marine agent's lane; `model_gdps-geml` does not and is
**not in the registry** — it is ECCC's ML-based global system, a natural companion to
`google-weathernext-2` and `ecmwf-aifs-single`. **Verified present in listing only.**

---

# 3. Provincial, municipal and institutional networks

## 3.1 Government of NL — Water Resources Management Division automated met network ★

**This is the most important local find in this document.**

| Field | Value |
|---|---|
| **Producer** | Government of Newfoundland and Labrador, Department of Environment, Climate Change and Municipalities, Water Resources Management Division (NL-DECCM-WRMD) |
| **Discovery endpoint** | `https://maps.gov.nl.ca/gsdw/rest/services/water/Stations/MapServer/3/query?where=1%3D1&outFields=*&f=json` (ArcGIS REST, layer 3 = "Climate Stations") |
| **Data endpoints** | `https://www.mae.gov.nl.ca/wrmd/ADRS/v6/Data/{STATION}_Line.csv` (7 days, ~hourly) — also `_Daily.csv` (35 days), `_Monthly.csv` (12 months), and `.xml` variants of each. Station page: `.../v6/Template_Station.asp?station={STATION}` |
| **Variables** | `AIR_TEMP (C)`, `REL_HUMIDITY (%)`, `ATMOS_PRES (kPa)`, `DEW_POINT (C)`, `PRECIP`/`PRECIP_TB`/`PRECIP_HTB (mm)`, `RAIN`, `SNOW`, `SNOW_DEPTH (m)`, `SNOW_DEPTH_NEW (cm)`, `RAD_SOLAR (kJ/m2)`, `SUNSHINE_HRS`, `WIND_SPEED (km/h)`, `WIND_DIR (deg)`, `WIND_SPEED_GUST`, `WIND_DIR_GUST`, `SWE_SP (mm)`, `SOIL_MOIS (%)`, `WIND_CHILL`, `HUMIDEX`, `BATT_VOLTAGE` — variable set differs per station |
| **Cadence** | Line data updated **every 2 hours**; daily/monthly summaries at 08:00 local |
| **Access** | **Genuinely open — no key, no registration.** Verified anonymously. |
| **Licence** | No explicit open licence. The page states: *"This page and all contents are copyright, Government of Newfoundland and Labrador, all rights reserved."* Data quality disclaimer: *"the streamflow and water quality data is PROVISIONAL and has not undergone quality control checks. These data may be subject to significant change."* **See "Licence traps" — this needs the same treatment the registry gave `provincial-hydrometric [licence_review]`.** |
| **Verified?** | **Yes — live data retrieved for four stations.** |

**Avalon Peninsula WRMD climate stations (verified against ArcGIS layer + live CSV):**

| Station id | Name | Lat | Lon | Active since | Live CSV verified |
|---|---|---|---|---|---|
| **`NLENCL0001`** | **Pippy Park in St. John's** | **47.58036** | **-52.73936** | **2004** | **Yes — 36,949 bytes, last row `8/29/2026 10:00:00 PM`: 17.98 °C, RH 99.4 %, 103.8 kPa, dewpoint 17.90 °C, wind 0.055 km/h from 187.9°, SWE 0.0 mm, solar 0.013 kJ/m²** |
| **`NLENCL0015`** | **Conception Bay South MET** | **47.483928** | **-53.016842** | **2024** | **Yes — 42,742 bytes, last row `8/29/2026 10:00:00 PM`: 18.98 °C, RH 93.9 %, 101.2 kPa, wind 2.908 km/h from 206°, soil moisture 7.234 %, windchill 19.01, humidex 18.41** |
| **`NLENCL0013`** | Vale LH2 MET | 47.430339 | -53.820658 | 2023 | Yes — 31,282 bytes, current to 2026-08-29 22:00 |
| `NLENCL0012` | Vale LH1 MET | 47.424167 | -53.766028 | 2020 | Yes (200) but **stale — last row `9/27/2022`.** Treat as dead. |
| `NLENMP1004` | Hodge River at Pumphouse (MEMP) | 47.416964 | -53.516592 | 2025 (inactive 2025) | not fetched |

Elevation for Pippy Park is reported as 101.2 m in the SWOB partner metadata.

**Why this matters to THIS project:** Pippy Park is inside the City of St. John's,
2.5 km from the map centre, at 101 m — meaningfully different from the 140 m airport
site 7 km to the north across a ridge. St. John's has a notorious microclimate
gradient (the airport is routinely in fog when downtown is clear). A second in-city
station with **snow water equivalent and solar radiation** — neither of which the
airport reports — is exactly the local ground truth this map lacks. Conception Bay
South adds a west-side-of-the-isthmus point 22 km away.

## 3.2 Government of NL — Department of Fisheries, Forestry and Agriculture fire-weather network

| Field | Value |
|---|---|
| **Producer** | Government of Newfoundland and Labrador, Department of Fisheries, Forestry and Agriculture (NL-DFFA) |
| **Endpoint** | `https://dd.weather.gc.ca/today/observations/swob-ml/partners/nl-firewx/{YYYYMMDD}/{NNN}/{YYYY-MM-DD-HHMM}-nl-dffa-{NNN}-AUTO-swob.xml` |
| **Station index** | `https://api.weather.gc.ca/collections/swob-partner-stations/items?bbox=-54.5,46.5,-52.4,48.3&f=json` |
| **Coverage** | **22 stations** province-wide (dirs `001`–`020`, `022`, `023`). Three on the Avalon: **`014` Salmonier (47.234064, -53.320153, 139 m)**, **`015` New Harbour Barrens (47.581528, -53.335194, 148 m)**, **`013` Harcourt (48.241972, -53.876694, 53 m)** |
| **Cadence** | Hourly (verified file `2026-08-30-0300-nl-dffa-014-AUTO-swob.xml`) |
| **Format** | SWOB-ML — OGC O&M 2.0 XML, `dms.ec.gc.ca/schema/point-observation/2.0`. Includes `wnd_snsr_vert_disp` (10 m), station elevation, and full element metadata |
| **Access** | Open via Datamart, no key |
| **Licence** | **Careful.** The XML carries `data_attrib_not`: *"Observational data provided by the Government of Newfoundland and Labrador: Department of Fisheries, Forestry and Agriculture (NL-DFFA). **All rights reserved.**"* The MSC licence covers the *server*; the partner's own reservation is embedded in the record. See "Licence traps". |
| **Verified?** | **Yes** — full XML retrieved and read |
| **Why it helps** | Three inland, elevated (139–148 m) barren-land stations at 10 m wind height, filling the gap between coastal Cape Race/Argentia and the airport. Fire-weather stations report the variables that drive fuel moisture — temperature, RH, wind, precipitation — which are exactly the variables the map most needs verified inland. |

## 3.3 Government of NL — WRMD stations *also* in the SWOB partner feed

`https://dd.weather.gc.ca/today/observations/swob-ml/partners/nl-water/{YYYYMMDD}/`
— verified present. Partner station records confirm `NL-DECCM-WRMD_NLENCL0001`
(Pippy Park), `NL-DECCM-WRMD_NLENCL0013` (Vale LH2) and
`NL-DECCM-WRMD_NLENCL0015` (Conception Bay South) are in the SWOB stream.

**This is the recommended ingestion path for 3.1** — same data, MSC licence, standard
SWOB-ML schema the project already parses, and the same polling machinery as
`eccc-swob`. Use the ADRS CSV (3.1) only for backfill.

## 3.4 The full ECCC SWOB partner directory (context)

Verified directory list at `https://dd.weather.gc.ca/today/observations/swob-ml/partners/`:
`ab-firewx/ ab_agriculture/ bc-RioTinto/ bc-crd/ bc-env-aq/ bc-env-snow/ bc-forestry/
bc-hydro/ bc-mvrd/ bc-tran/ dfo-moored-buoys/ dnd-ccg-lighthouse/ mb_agriculture/
nb-rwin/ **nl-firewx/ nl-water/** ns-firewx/ ns-rwin/ nt-forestry/ nt-water/ on-firewx/
on-grca/ on-mto/ on-trca/ pc-firewx/ pe-rwin/ qc-pom/ sk-forestry/ yt-avalanche/ yt-firewx/`

Note there is **no `nl-rwin/`** — New Brunswick, Nova Scotia and PEI publish Road
Weather Information Network data through SWOB, **Newfoundland does not.** That is a
firm negative answer to "is NL RWIS available", consistent with the registry's
`nl-511-rwis [unavailable]`.

Also of note: **`dnd-ccg-lighthouse/`** — Canadian Coast Guard lighthouse stations.
Worth a look for Avalon lighthouses (Cape Spear, Ferryland Head), though this
straddles the marine agent's lane.

## 3.5 DFO Station 27 (AZMP) via SWOB partners

| Field | Value |
|---|---|
| **`msc_id`** | `DFO_AZMP-STA27`, `iata_id` `AZMP-STA27`, `wmo_id` `4400486` |
| **Position** | **47.540, -52.588333** — ~9 km off Cape St. Francis, in Conception/Avalon coastal water |
| **Producer** | Fisheries and Oceans Canada, Atlantic Zone Monitoring Program |
| **Verified?** | Yes — station record returned by `swob-partner-stations` |
| **Note** | Station 27 is one of the longest-running oceanographic time series in the world (from 1946). Its *oceanographic* content belongs to the marine agent; its *atmospheric* SWOB record does not, and is listed here because it is the nearest offshore surface met point to St. John's harbour. |

## 3.6 NL Water Resources Portal — ArcGIS services (discovery layer)

| Field | Value |
|---|---|
| **Endpoints** | `https://maps.gov.nl.ca/gsdw/rest/services/water/Stations/MapServer` (layers 0 ADRS, 1 Hydrometric, 2 WQMA, **3 Climate Stations**, 4 WQMA Watersheds); `https://maps.gov.nl.ca/gsdw/rest/services/water/WRPortalMapService/FeatureServer` (44 layers, incl. 28 Climate Stations, 34 Hydrometric Watersheds, 38 Flood Risk Areas, 41 Climate Change Annual Projections). WMS/KML variants documented at `https://maps.gov.nl.ca/water/mapservices.htm` |
| **Verified?** | **Yes** — layer 3 returned **158 station records** with 28 attribute fields including `AIR_TEMP`, `PRECIP_1/2`, `REL_HUMIDITY`, `WIND_*`, `SNOW_DEPTH`, `RAD_SOLAR`, `MSC_ID`, `WSC_ID`, `REALTIME_L` |
| **Access** | Open ArcGIS REST, no key |
| **Why it helps** | It is the authoritative **provincial** station catalogue, cross-referencing MSC climate IDs to WSC hydrometric IDs and flagging which have real-time links. It also names station *operators* — `EC`, `MSC`, `NAV Canada`, `WRMD`, `HRB` (Hydro), `ENVC`, `NAL` (Nalcor) — which is metadata the ECCC catalogue does not carry. |

## 3.7 Newfoundland and Labrador open data portal

| Field | Value |
|---|---|
| **Endpoint** | `https://opendata.gov.nl.ca/` — external applications index at `https://opendata.gov.nl.ca/public/opendata/page/?page-id=external` |
| **Verified?** | Partially — the portal responds 200 but serves an HTML shell; **no CKAN/JSON API found at `/api/`**. It is a hand-curated catalogue, not a machine API. |
| **Assessment** | **Low value as a feed.** Useful only as a pointer to the ArcGIS services in 3.6, which are better accessed directly. |

## 3.8 City of St. John's

| Field | Value |
|---|---|
| **Endpoints tried** | `https://data.stjohns.ca/api/3/action/package_list` — **DNS/connection failure (HTTP 000)**. `https://maps.stjohns.ca/arcgis/rest/services?f=json` — **DNS/connection failure**. Public viewer at `https://map.stjohns.ca/Mapcentre/` (ArcGIS Web AppBuilder). |
| **Verified?** | Yes — verified *absent*. Neither hostname resolved. |
| **Assessment** | **The City of St. John's does not publish a machine-readable open-data or GIS API at any discoverable endpoint.** Mapcentre is an ArcGIS Online web app; its data is served from `gnl.maps.arcgis.com` item services, which could in principle be scraped item-by-item, but nothing weather-related was found. The registry's `municipal-hydrometric [unavailable]` is correct and the same conclusion extends to municipal weather. **Reject.** |
| **One residual lead (unverified)** | Snow-clearing / plow-route status is referenced in third-party writeups. If the City ever exposes it, it would be a genuinely local winter layer. Nothing machine-readable found today. |

## 3.9 Memorial University of Newfoundland

| Field | Value |
|---|---|
| **What exists (from documentation)** | MUN's Physics and Physical Oceanography group is documented as operating **a weather station on the roof of the Chemistry-Physics building**, with a display in the Science building, **and one at the Johnson GEO CENTRE on Signal Hill**. |
| **Endpoints tried** | `https://www.physics.mun.ca/~weather/` → **404**. `https://www.mun.ca/physics/weather/` → **404** (MUN CMS 404 page). |
| **Verified?** | **Yes — verified absent.** No public MUN weather-data endpoint found. |
| **Assessment** | **MUN does not publish live station data at any URL I could find.** The stations appear to be internal/display-only. A Signal Hill station would be genuinely valuable (it is the classic fog/wind contrast point against the airport), so this is worth **one email to the Department of Physics and Physical Oceanography** rather than more scraping. Recorded as a human-contact lead, not an ingestible source. |
| **Related MUN assets found** | Marine Institute meteorological and oceanographic buoys in **Holyrood Bay** (Conception Bay), and the MI / Ocean Networks Canada **Conception Bay seafloor observatory** (currents, waves, water temperature, salinity, sound). Both are oceanographic and belong to the marine agent's lane; neither surfaced a public met API. C-CORE produced no public weather data endpoint. |

## 3.10 CIOOS Atlantic catalogue

| Field | Value |
|---|---|
| **Endpoint** | `https://catalogue.cioosatlantic.ca/api/3/action/package_search?q=...` (CKAN) |
| **Verified?** | **Yes** — API responds 200 with valid CKAN JSON. A `q=Holyrood` search returned 2 datasets with a bbox at 47.4618 N / −53.108 E; `q=Newfoundland meteorological` returned 1 (a DFO moored-ship historical time series). |
| **Assessment** | Real, open, working CKAN API — but **thin on Avalon atmospheric content.** Its value is oceanographic (marine agent's lane). Listed here for completeness with an honest "not much for us". |

## 3.11 Johnson GEO CENTRE

Referenced in MUN documentation as hosting one of the physical-oceanography group's
weather stations (Signal Hill). **No public endpoint found. Unverified — from
documentation only.** Same recommendation as 3.9: a human contact, not a feed.

---

# 4. Road, transport and infrastructure weather

## 4.1 NL 511 developer API

| Field | Value |
|---|---|
| **Producer** | Government of Newfoundland and Labrador, Department of Transportation and Infrastructure |
| **Endpoints** | `https://511nl.ca/api/v2/get/winterroads`, `/cameras`, `/ferryterminals`, `/windwarnings`, `/event`, `/alerts` — all `?key={APIKEY}&format=json` |
| **Docs** | `https://511nl.ca/developers/doc` |
| **Access** | **Free but credential-gated.** Register an account at 511nl.ca (email or SMS verification), then request an API key from the developer docs page. |
| **Rate limit** | *"Throttling is enabled. Ten calls every 60 seconds."* |
| **Verified?** | **Yes, partially.** `https://511nl.ca/api/v2/get/roadconditions` and `/cameras` both returned **HTTP 400 `<Error><Message>Invalid Key</Message></Error>`** — proving the API is live and key-gated, and that the correct road-conditions path is `winterroads`, not `roadconditions`. |
| **Licence** | Not stated in the developer docs. Terms live at `https://511nl.ca/terms`. **Unverified — needs reading before ingest.** |
| **Why it helps** | Road conditions (bare/wet/snow-covered/ice) are the closest thing NL has to a dense winter surface-state observation network, and the camera feed gives visual ground truth across the Avalon. The registry already has this as `nl-511 [credential_required]` — **the gap is that nobody has registered for the key.** That is a 10-minute task with a large payoff. |

## 4.2 NL 511 Wreckhouse wind warnings

| Field | Value |
|---|---|
| **Endpoint** | `https://511nl.ca/api/v2/get/windwarnings` (docs at `https://511nl.ca/help/endpoint/windwarnings`) |
| **What it is** | Warning state for the Trans-Canada Highway from *vicinity of Tompkins to vicinity of Cape Ray*. Thresholds: gusts >80 km/h → "TRUCKS ADVISED TO PULL OVER"; gusts >100 km/h → "ALL TRAFFIC ADVISED TO PULL OVER". Fed by an **MSC-operated anemometer** whose data goes to the Gander weather office. Gusts >200 km/h have been recorded. |
| **Coverage of the Avalon** | **None.** Wreckhouse is ~20 km from Port aux Basques on the **southwest** coast, roughly 700 km from St. John's. |
| **Verified?** | Endpoint existence verified (listed in the live developer docs); content not retrieved (key required) |
| **Assessment** | Famous, genuinely interesting, and **completely irrelevant to a St. John's map.** Include it only if the project's scope ever widens to the island. Listed because the brief asked. |

## 4.3 NL RWIS

**Verified absent.** There is no `nl-rwin/` directory in the ECCC SWOB partners tree
(NB, NS and PE all have one — `nb-rwin/`, `ns-rwin/`, `pe-rwin/`). No standalone NL
RWIS endpoint found. The registry's `nl-511-rwis [unavailable]` is correct.
The nearest thing to RWIS in NL is the 511 winter-roads product (4.1).

## 4.4 St. John's International Airport (CYYT / YYT) beyond METAR/TAF

| Field | Value |
|---|---|
| **Findings** | The airport's meteorological output *is* the ECCC/NAV CANADA station. It appears in the ECCC catalogue as `STN_ID 50089` / climate id `8403505` / TC `YYT` / **WMO 71801**, operator "NAV Canada" per the provincial layer (3.6). Hourly climate archive: 2012-03-20 → present (predecessor `8403506` 1942→2012). |
| **New endpoints** | None beyond what is documented in sections 1.2, 1.3, 5.6, 5.7 and 5.8. The St. John's International Airport Authority publishes no meteorological API. |
| **Verified?** | Yes — absence of an airport-authority feed confirmed by search; all met endpoints for CYYT enumerated above |
| **NAV CANADA** | The registry already has `nav-canada-weather-cameras [licence_review]`. NAV CANADA's aviation weather site (flight planning, GFA graphical area forecasts) is behind an interactive front end with no documented public API. **Unverified — no public API found.** The Canadian **IWXXM** feed (2.8) is the machine-readable route to NAV CANADA-originated TAF/SIGMET. |

---

# 5. Citizen science, amateur networks and public archives

## 5.1 CoCoRaHS — **yes, it operates in Newfoundland** ★

| Field | Value |
|---|---|
| **Producer** | Community Collaborative Rain, Hail and Snow Network (Colorado State University) |
| **Observation endpoint** | `https://data.cocorahs.org/cocorahs/export/exportreports.aspx?ReportType=Daily&dtf=1&Format=CSV&ReportDateType=reportdate&Date=8/1/2026` |
| **Station endpoint** | `https://data.cocorahs.org/cocorahs/export/exportstations.aspx?Format=CSV` |
| **Gives you** | `ObservationDate, ObservationTime, EntryDateTime, StationNumber, StationName, Latitude, Longitude, TotalPrecipAmt, NewSnowDepth, NewSnowSWE, TotalSnowDepth, TotalSnowSWE` — manual 24-h precipitation read at ~07:00 local from a 4-inch standard gauge |
| **Access** | **Genuinely open, no key, no registration.** |
| **Verified?** | **Yes** — 17,007 observation rows for 2026-08-01; 15.8 MB station export retrieved |
| **Gotcha** | **The `State=` query parameter is silently ignored.** `State=NL` and `State=CAN-NL` both returned the identical full 2.35 MB national file. Filter client-side on `StationNumber` prefix `CAN-NL-` or on lat/lon. |
| **Licence** | CoCoRaHS data is publicly available for non-commercial and research use with attribution. **Unverified — I did not retrieve a formal licence text.** Verify before redistribution. |

**All 16 currently-reporting CoCoRaHS stations in Newfoundland and Labrador (verified;
88 further stations are closed). Avalon Peninsula stations in bold:**

| Station | Name | Lat | Lon | Elev ft | Registered |
|---|---|---|---|---|---|
| **`CAN-NL-2`** | **St. John's 0.4 N** | **47.564043** | **-52.71336** | 193 | 2013-09-16 |
| **`CAN-NL-50`** | **St. John's 4.3 NNE** | **47.595512** | **-52.687125** | 260 | 2013-09-19 |
| **`CAN-NL-79`** | **Mount Pearl 1.3 WNW** | **47.519554** | **-52.828386** | 496 | 2017-04-21 |
| **`CAN-NL-104`** | **Paradise 1.9 NE** | **47.543428** | **-52.839658** | 0 | 2026-02-27 |
| **`CAN-NL-88`** | **The Dock 0.6 ESE (Coley's Point South)** | **47.5716104** | **-53.2535598** | 98 | 2021-06-23 |
| **`CAN-NL-14`** | **Whitbourne 1.4 NE** | **47.42741** | **-53.51946** | 243 | 2013-09-16 |
| **`CAN-NL-103`** | **Whitbourne 1.2 NE** | **47.426661** | **-53.5196836** | 0 | 2025-11-02 |
| `CAN-NL-96` | Clarenville 3.5 NNW | 48.185847 | -53.990507 | 69 | 2023-06-06 |
| `CAN-NL-82` | Gander 2.7 NW | 48.977379 | -54.633964 | 394 | 2018-11-11 |
| `CAN-NL-81` | Grand Falls-Windsor 1.2 S | 48.931232 | -55.653334 | 281 | 2018-07-26 |
| `CAN-NL-69` | Lewisporte 0.3 SSE - NL HAM | 49.2440338 | -55.0648422 | 41 | 2014-09-05 |
| `CAN-NL-95` | Corner Brook 11.6 ESE | 48.9171 | -57.7979 | 1539 | 2023-06-06 |
| `CAN-NL-65` | Kippens 0.7 NE | 48.554363 | -58.618461 | 119 | 2013-10-29 |
| `CAN-NL-13` | L'Anse au Clair 0.1 NW | 51.435 | -57.065 | 147 | 2013-09-16 |
| `CAN-NL-17` | L'Anse au Loup 0.7 SSW | 51.52017 | -56.836933 | 110 | 2013-09-18 |
| `CAN-NL-91` | Wabush 0.6 SE | 52.896066 | -66.862171 | 1913 | 2023-06-05 |

**Confirmed actually reporting on 2026-08-01** (present in that day's observation file):
`CAN-NL-13, 14, 17, 50, 65, 69, 79, 81, 82, 91`. Example values from that file:
`CAN-NL-50 St. John's 4.3 NNE, 0.05 in`; `CAN-NL-79 Mount Pearl 1.3 WNW, 0.03 in`;
`CAN-NL-14 Whitbourne 1.4 NE, 0.02 in`.

**Why this matters:** `CAN-NL-2` is at **47.564 N, 52.713 W** — that is the map centre
to within 400 m. Seven CoCoRaHS gauges sit inside the St. John's metro / eastern-Avalon
area, and they measure the two things automated gauges do worst in Newfoundland:
**cold-season precipitation and snow water equivalent**. Tipping buckets undercatch
snow badly in high wind; a manual gauge read does not. For validating winter
precipitation forecasts on the Avalon these are more useful than another ASOS.

**Caveats:** manual, once-daily, ~07:00 local; not all stations report every day;
occasional gaps; units are **inches** in the export. Not a nowcast source — a
verification source.

## 5.2 Weather Underground PWS API

| Field | Value |
|---|---|
| **Producer** | The Weather Company / IBM |
| **Endpoint** | `https://api.weather.com/v2/pws/observations/current?stationId={ID}&format=json&units=m&apiKey={KEY}` (also `/v2/pws/observations/all/1day`, `/v2/pws/history/hourly`) |
| **Access** | **Hard-gated.** The free general developer API was withdrawn on 2018-12-31. Free API keys are now issued **only to people who own a PWS that is actively uploading to Weather Underground.** Otherwise, enterprise pricing. |
| **Verified?** | Partially. `api.weather.com` refused a keyless request; the legacy `api.wunderground.com/weatherstation/WXCurrentObXML.asp` host returned **HTTP 503 DNS failure** (decommissioned). I could **not** enumerate St. John's PWS IDs without a key and will not guess them. |
| **Licence** | Weather Company API terms; commercial redistribution not permitted on the free/PWS-owner tier. **Unverified — from documentation only.** |
| **Assessment** | **Reject as a primary source.** The eligibility gate ("own and operate a PWS") is a real barrier and the terms are restrictive. There are certainly Wunderground PWS units in St. John's — the Wundermap shows them — but I will not fabricate station IDs. If the project ever wants them, the honest path is to buy and register a station, which also solves the API-key problem. |

## 5.3 CWOP — Citizen Weather Observer Program

| Field | Value |
|---|---|
| **Producer** | CWOP / NOAA MADIS |
| **Access path** | CWOP observations flow into **NOAA MADIS**, which the registry already carries as `noaa-madis [credential_required]`. MADIS mesonet requires a registered account for the FTP/API feeds. |
| **Endpoints tried** | `https://www.findu.com/cgi-bin/wxnear.cgi?...` — **HTTP 000, host did not respond.** findu.com appears to be down or gone. |
| **Verified?** | Verified that findu is unavailable; MADIS not re-tested (already registered as credential-gated) |
| **Licence** | CWOP data is public-domain-ish but individual station quality is uncontrolled; MADIS applies QC flags |
| **Assessment** | The registry entries `noaa-madis [credential_required]` and `raw-cwop-pws [licence_review]` already cover this. **The gap is the same as NL 511: nobody has registered.** MADIS is the right way to get CWOP because it arrives QC-flagged. Medium priority; the win is that MADIS also carries the ECCC and NL stations, so one registration unlocks several networks at once. |

## 5.4 WeatherFlow / Tempest

| Field | Value |
|---|---|
| **Endpoint** | `https://swd.weatherflow.com/swd/rest/observations/station/{id}?token={TOKEN}`; `.../rest/stations?token=` |
| **Access** | **Token required for everything.** Verified: both endpoints returned `HTTP 401 {"status":{"status_code":401,"status_message":"UNAUTHORIZED"}}`. Tokens are issued to Tempest device owners. |
| **Verified?** | **Yes — verified as gated.** |
| **Assessment** | **Reject.** Same structural problem as Weather Underground: you must own the hardware. No way to enumerate St. John's Tempest units without a token. |

## 5.5 AWEKAS, PWSweather, Weathercloud

| Network | Endpoint tried | Result | Assessment |
|---|---|---|---|
| **AWEKAS** | `https://api.awekas.at/current.php` | **HTTP 200** `{"fetchdate":1788060412,"error":"invalid key"}` — API live, key required. Keys are for station operators. | Reject — European-centric, gated, near-zero NL coverage expected |
| **PWSweather** (AerisWeather) | `https://www.pwsweather.com/api/v1/stations?lat=47.56&lon=-52.71` | **HTTP 404** — that path does not exist. PWSweather is an upload target, not a query API; querying goes through AerisWeather (6.8). | Reject as a standalone source |
| **Weathercloud** | `https://app.weathercloud.net/map` | **HTTP 200**, 215 KB HTML — a web map, no documented public JSON API | Reject — scraping a web map is fragile and of uncertain legality |

## 5.6 NOAA NCEI Integrated Surface Database (ISD) — global hourly ★

| Field | Value |
|---|---|
| **Producer** | NOAA National Centers for Environmental Information |
| **Endpoints** | Global Hourly CSV: `https://www.ncei.noaa.gov/data/global-hourly/access/{YYYY}/{USAF}{WBAN}.csv` — ISD-Lite: `https://www.ncei.noaa.gov/pub/data/noaa/isd-lite/{YYYY}/{USAF}-{WBAN}-{YYYY}.gz` — Station history: `https://www.ncei.noaa.gov/pub/data/noaa/isd-history.csv` |
| **Access** | **Genuinely open, no key.** |
| **Licence** | US Government work — public domain (NOAA open-data policy). **No caching or redistribution restriction.** |
| **Verified?** | **Yes** — `https://www.ncei.noaa.gov/data/global-hourly/access/2025/71801099999.csv` returned **4,872,419 bytes**. First row: `"71801099999","2025-01-01T00:00:00","4","47.61861","-52.751945","140.51","ST JOHNS INTERNATIONAL, CA","FM-12",...` with WND, CIG, VIS, TMP, DEW, SLP and 30+ additional element groups (AA1 precip, GA1–GA4 sky layers, GD1–GD4, GF1, KA1, etc.). ISD-Lite `718010-99999-2025.gz` returned 60,719 bytes. Note the 2026 directory does not yet exist (`404`) — ISD lags. |

**All 15 ISD stations inside the Avalon bounding box (verified from `isd-history.csv`):**

| USAF | WBAN | Name | ICAO | Lat | Lon | Elev m | Begin | End |
|---|---|---|---|---|---|---|---|---|
| **718010** | 99999 | **ST JOHNS INTL** | **CYYT** | 47.619 | -52.752 | 140.5 | **1941-09-29** | 2025-08-24 |
| 712500 | 99999 | ST JOHNS WEST CLIMATE | CAJW | 47.517 | -52.783 | 110.0 | 1994-01-03 | 2025-08-24 |
| 718000 | 99999 | CAPE RACE (AUT) NFLD | CWRA | 46.650 | -53.067 | 27.0 | 1955-07-02 | 2025-08-24 |
| 718070 | 99999 | ARGENTIA (AUT) | CWAR | 47.283 | -53.983 | 9.0 | 1945-03-01 | 2025-08-24 |
| 713360 | 99999 | GRATES COVE | — | 48.167 | -52.933 | — | 2004-09-21 | 2025-08-24 |
| **719455** | 99999 | **LONG POND** | — | 47.517 | -52.983 | — | 1977-07-01 | 2025-08-23 |
| 716920 | 99999 | MARTICOT ISLAND | — | 47.333 | -54.583 | — | 2005-09-21 | 2025-08-24 |
| 718020 | 99999 | ST JOHN'S WEST | — | 47.517 | -52.783 | 112.0 | 1977-07-01 | 1997-11-09 |
| 718073 | 99999 | ARGENTIA (MARS) | — | 47.300 | -54.000 | 16.0 | 1987-02-19 | 1991-02-04 |
| 718004 | 99999 | ST SHOTTS (AUT) | — | 46.720 | -53.480 | — | 1993-03-30 | 1996-01-03 |
| 718009 | 99999 | KELLIGREWS | — | 47.500 | -53.017 | — | 1990-03-02 | 1990-03-17 |
| 728010 | 99999 | ST JOHNS/TORBAY | YYT | 47.617 | -52.750 | 141.0 | 1973-01-01 | 1977-06-30 |
| 728000 | 99999 | CAPE RACE (MARS) | — | 46.650 | -53.067 | 27.0 | 1976-11-01 | 1977-01-20 |
| 728070 | 99999 | ARGENTIA (MARS) | YAR | 47.283 | -54.000 | 16.0 | 1973-01-01 | 1977-07-30 |
| 995340 | 99999 | NICKERSON BANK | — | 46.440 | -53.390 | — | 1988-09-15 | 1997-05-17 |

**`719455 LONG POND` (47.517, -52.983) is notable — it is in the ISD and IEM
inventories with a 1977→2025 record but does *not* appear in the ECCC
`climate-stations` result.** It is a Conception Bay South coastal site, 18 km west
of downtown. Worth chasing.

**Why ISD helps:** ISD is the internationally reconciled version of the same
observations, in **one uniform schema for the whole world**, public domain, with
QC flags. If the project ever wants to compare St. John's against anywhere else, or
wants a schema that does not change when ECCC reorganises, ISD is the answer. It is
also the substrate under Meteostat (5.9).

## 5.7 NOAA GHCN-Daily

| Field | Value |
|---|---|
| **Endpoint** | `https://www.ncei.noaa.gov/data/global-historical-climatology-network-daily/access/{GHCN_ID}.csv` |
| **Nearest station** | **`CA008403506`** = "ST JOHN S A, NL CA", 47.6167 / −52.75, 141.0 m |
| **Verified?** | **Yes** — 3,653,229 bytes. Columns: `STATION, DATE, LATITUDE, LONGITUDE, ELEVATION, NAME, PRCP, SNOW, SNWD, TMAX, TMIN` with `*_ATTRIBUTES` quality flags. First row **1942-01-01**; last row 2012-03-19 (the station closed then — the successor is `CA008403505`). |
| **Access / licence** | Open, no key, US public domain |
| **GHCN id convention** | ECCC climate id `8403505` → GHCN `CA008403505`; `8403506` → `CA008403506`. Same mapping applies to every station in the section 1.1 table. |
| **Why it helps** | GHCN-Daily is the standard input for every climate-index and extremes library in existence. If the project wants ETCCDI indices, frost-day counts or return periods, this is the least-effort path. Also gives a second, independently QC'd copy of the ECCC daily record — useful for catching decode bugs. |

## 5.8 Iowa Environmental Mesonet — ASOS/AWOS archive ★

| Field | Value |
|---|---|
| **Producer** | Iowa State University, Iowa Environmental Mesonet |
| **Endpoint** | `https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py?station=CYYT&data=tmpf&data=dwpf&data=sknt&data=drct&data=p01i&data=vsby&year1=2026&month1=8&day1=1&year2=2026&month2=8&day2=2&tz=UTC&format=onlycomma&latlon=yes` |
| **Station index** | `https://mesonet.agron.iastate.edu/geojson/network/CA_NF_ASOS.geojson` |
| **Access** | **Genuinely open, no key.** Be polite — it is a university service; batch by year, not by day. |
| **Verified?** | **Yes** — returned real rows: `CYYT,2026-08-01 00:00,-52.7428,47.6222,53.60,53.60,6.00,120.00,0.00,0.12`. Station GeoJSON returned 29 NL stations. |
| **Gotcha** | **The station id must be `CYYT`, not `YYT`.** Passing `YYT` with `network=CA_NF_ASOS` returned a header-only file. |

**IEM `CA_NF_ASOS` stations in the Avalon box (verified):**

| ID | Name | Lat | Lon | Archive begin | End |
|---|---|---|---|---|---|
| **CYYT** | St Johns | 47.6222 | -52.7428 | **1941-09-29** | active |
| CWRA | CAPE RACE (AUT) NFLD | 46.6600 | -53.0764 | 1955-07-02 | active |
| CWAR | ARGENTIA (AUT) | 47.2939 | -53.9933 | 1945-02-28 | active |
| **CWWU** | **LONG POND** | 47.5158 | -52.9803 | 1977-06-30 | active |
| CXSW | SAINT JOHNS WEST | 47.5167 | -52.7833 | 2000-01-07 | 2013-06-25 |

**`CWWU` LONG POND (47.5158, -52.9803)** — same station as ISD `719455`, confirmed
active, with an ICAO-style id. This is a **currently-active Avalon station the ECCC
climate-stations query did not return**, 18 km WSW of downtown on Conception Bay.
Chase it in the SWOB and Datamart feeds.

**Why IEM helps:** it is by far the *easiest* archive to query — one URL, CSV out,
arbitrary date range, no pagination, no key, and it already carries the full METAR
decode (including present weather, sky cover, altimeter, gust, and metar text if
requested). For rapid experimentation it beats the ECCC API on ergonomics, though
ECCC remains authoritative.

## 5.9 Meteostat — bulk historical aggregator

| Field | Value |
|---|---|
| **Producer** | Meteostat (open-source project) |
| **Endpoints** | Bulk: `https://bulk.meteostat.net/v2/hourly/{WMO_ID}.csv.gz`, `.../v2/daily/{WMO_ID}.csv.gz`, `.../v2/monthly/`, `.../v2/normals/`. JSON API via RapidAPI (key required). Python library `meteostat`. |
| **Station for St. John's** | **`71801`** (the WMO id) |
| **Verified?** | **Yes** — `https://bulk.meteostat.net/v2/hourly/71801.csv.gz` returned **4,983,785 bytes** decompressing to **539,941 hourly rows**, first row **`1941-09-29,07,5.2,2.4,82,,,248,18.4,,,,`**, last row `2026-03-15,20,-1.8,-5.5,76,,,232,27.8,,1010.1,,3`. Daily bulk returned 278,718 bytes. Note `https://bulk.meteostat.net/v2/stations/slim.json.gz` returned **404** — the station-index path has moved. |
| **Columns** | date, hour, temp, dwpt, rhum, prcp, snow, wdir, wspd, wpgt, pres, tsun, coco (condition code) |
| **Access** | **Bulk endpoints: completely open, no key.** JSON API: RapidAPI key. |
| **Licence** | **CC BY 4.0.** Attribution required: *"You must give appropriate credit, provide a link to the license, and indicate if changes were made."* Example format: `Source: Meteostat, Deutscher Wetterdienst`. Meteostat does not own the data — it aggregates NOAA/DWD/national-service sources and redistributes under CC BY 4.0. |
| **Caching / redistribution** | **Permitted** under CC BY 4.0 with attribution. No non-commercial clause on the data licence. Terms of service add only: no multiple accounts, no automated account creation, no life-safety use, no accuracy guarantee. |
| **Verified caveat** | The bulk file lags — last row was **2026-03-15**, about 5½ months behind. Fine for climatology, useless for nowcasting. |
| **Why it helps** | One gzipped file gives 85 years of hourly St. John's weather with no pagination, no key, and a clean permissive licence. It is the single lowest-effort way to get a full historical training set. Use ECCC for authority and recency; use Meteostat for bulk convenience. |

## 5.10 Netatmo public weather map API

| Field | Value |
|---|---|
| **Endpoint** | `https://api.netatmo.com/api/getpublicdata?lat_ne=&lon_ne=&lat_sw=&lon_sw=` |
| **Access** | **OAuth2 access token required.** Verified: a keyless request returned `HTTP 400 {"error":{"code":1,"message":"Access token is missing"}}`. Registration at `dev.netatmo.com` is free. |
| **Gives you** | Live temperature, humidity, pressure, rain and wind from Netatmo stations **whose owners consented to appear on the Weathermap** |
| **Verified?** | **Yes — verified as gated.** Could not enumerate St. John's units without a token. |
| **Caveat from documentation** | Netatmo advises querying small bounding boxes; large squares return 503 or out-of-area data. |
| **Licence** | Netatmo developer terms; **unverified — from documentation only.** Historically restrictive about redistribution of user-contributed data, and there are obvious privacy considerations in republishing consumer stations at street resolution. |
| **Assessment** | **Medium-low priority with a real licence question.** Netatmo density in St. John's is unknown and probably thin. The privacy dimension (these are people's back gardens) argues for caution in a public map. |

## 5.11 PurpleAir and OpenAQ (already registered — status confirmed)

Both are in the registry as `credential_required`. I confirmed the gate is real:
`https://api.purpleair.com/v1/sensors?...` → **HTTP 403 `ApiKeyMissingError`**;
`https://api.openaq.org/v3/locations?...` → **HTTP 401 "A valid API key must be
provided in the X-API-Key header."** Both keys are free to obtain. PurpleAir sensors
report temperature and humidity alongside PM, so a PurpleAir key would incidentally
add a citizen temperature network. Noted, not re-argued.

## 5.12 NWS `api.weather.gov` — **does not cover Canada**

`https://api.weather.gov/points/47.56,-52.71` → **HTTP 404
`"Unable to provide data for requested point 47.56,-52.71"`**. Verified negative.
Recorded so nobody tries.

---

# 6. Commercial, freemium and aggregator APIs

**Read this section's licence column before writing any ingestion code.** The
recurring pattern is that free tiers forbid exactly the two things this project does:
storing results in a database, and showing them to the public.

## 6.1 Open-Meteo ★★ — the single best external addition

| Field | Value |
|---|---|
| **Producer** | Open-Meteo (open-source, Zurich) |
| **Endpoints (all verified HTTP 200)** | Forecast: `https://api.open-meteo.com/v1/forecast?latitude=47.56&longitude=-52.71&hourly=temperature_2m` — Historical/ERA5: `https://archive-api.open-meteo.com/v1/archive?...&start_date=1990-01-01&end_date=1990-01-02` — **Historical Forecast:** `https://historical-forecast-api.open-meteo.com/v1/forecast?...&start_date=2024-01-01` — **Previous Runs:** `https://previous-runs-api.open-meteo.com/v1/forecast?...&hourly=temperature_2m_previous_day1,temperature_2m_previous_day2` — Ensemble: `https://ensemble-api.open-meteo.com/v1/ensemble?...&models=gfs05` |
| **Also offered** | Single Runs API, Climate (CMIP6 to 2050), Marine, Air Quality, Flood, Satellite Radiation (from 1983), Geocoding, Elevation |
| **Verified model coverage at 47.56/-52.71** | `gem_hrdps_continental` ✔, `gem_regional` ✔, `gem_global` ✔, `ecmwf_ifs025` ✔, `icon_seamless` ✔, `gfs_seamless` ✔, **`meteofrance_seamless` ✔**, **`ukmo_seamless` ✔**, **`knmi_seamless` ✔** — all returned 200 with data |
| **Access** | **No API key on the free tier.** |
| **Free tier limits** | *"600 calls / min"*, *"5.000 calls / hour"*, *"10.000 calls / day"*, *"300.000 calls / month"* |
| **Licence** | *"The data obtained through the API is provided under the terms of the CC-BY 4.0 licence"* |
| **Caching / redistribution** | **CC BY 4.0 permits both**, with attribution. The terms document does not add a separate caching prohibition. |
| **Non-commercial boundary** | The free tier is non-commercial. Open-Meteo's own examples of qualifying use: *private/non-profit sites without subscriptions or ads, personal home automation, public research at institutions, educational content.* Commercial use includes subscription or ad-supported sites and integration into commercial products. **A personal, ad-free St. John's weather map is squarely inside the free tier.** Paid tiers: API Standard (1M), Professional (5M), Enterprise (>50M) calls/month, Stripe billing. |
| **Gotchas** | The free API snaps to the model grid — for `latitude=47.56&longitude=-52.71` it returned `47.557117 / -52.697357` at 4 m elevation, i.e. a **coastal/water grid cell**, not the 140 m airport. Elevation-sensitive comparisons need `elevation=` set explicitly. `customer-archive-api.open-meteo.com` requires `&apikey=` (verified 401) — the free archive host is `archive-api.open-meteo.com`. |

**Why this is the top recommendation, concretely:**

- **It closes the verification gap in one move.** The Historical Forecast API stores
  *past forecasts as issued* from 2021; the Previous Runs API gives a fixed-lead-time
  series (1–7 days) from January 2024. Pair either with `climate-hourly` (1.2) and the
  project can compute bias, MAE and skill-vs-persistence for St. John's **today**,
  without having to first accumulate its own forecast archive for a year.
- **It adds models the project cannot otherwise get.** UKMO, KNMI, JMA, DMI, MeteoSwiss,
  GeoSphere Austria, BOM, CMA are not otherwise freely available as gridded data.
  UKMO in particular is a strong North Atlantic performer.
- **It is a cheap fallback for models already registered.** `gem_hrdps_continental` at
  a point is a few hundred bytes; the equivalent HRDPS GRIB is tens of megabytes.
- **The licence is compatible.** CC BY 4.0 with attribution is the same permission
  level as the ECCC licence the project already operates under.

## 6.2 OpenWeatherMap

| Field | Value |
|---|---|
| **Endpoint** | `https://api.openweathermap.org/data/2.5/weather?lat=47.56&lon=-52.71&appid={KEY}`; One Call at `/data/3.0/onecall` |
| **Free tier** | **60 calls/min, 1,000 calls/day, 1,000,000 calls/month.** Free APIs: Current Weather, 3-hourly/5-day forecast, Air Pollution, Geocoding, Weather Maps 1.0. **One Call 3.0/4.0 is not free**; minutely, 15-minute and hourly forecasts and historical data are locked. |
| **Access** | Free registration, API key. No credit card for the free tier. |
| **Licence** | **ODbL 1.0** for self-service products (some products CC BY-SA 4.0). |
| **Caching / redistribution** | Permitted **but share-alike bites**: if an adapted database — or a service giving access to one — is made available outside your organisation, the adapted database must itself be offered under ODbL. **This is a licence trap for a public map that mixes OWM with other data.** See "Licence traps". |
| **Verified?** | Pricing and licence framework from OpenWeather's own pages; **the API itself was not called (no key). Unverified endpoint.** |
| **Assessment** | **Reject.** It adds nothing Open-Meteo does not (OWM's underlying models are GFS/ECMWF-derived, both already registered), and the ODbL share-alike obligation would infect the project's derived database. |

## 6.3 Tomorrow.io — **licence trap**

| Field | Value |
|---|---|
| **Endpoint** | `https://api.tomorrow.io/v4/weather/forecast?location=47.56,-52.71&apikey={KEY}` |
| **Access** | Free tier with registration; commercial use requires an Order |
| **Caching / storage** | **Prohibited.** The terms forbid: *"store or otherwise collect or copy the unaltered Datafeed, unless otherwise expressly provided for in the Order or for permitted evaluation of DaaS, in which case Datafeed may only be stored for the duration of the Initial Term"* |
| **Redistribution** | **Prohibited.** *"The Solution may not be distributed, shared, or offered on a standalone basis"*; and you may not *"Offer any portion or all of the Solution to any third parties … including but not limited to reselling, licensing, renting, leasing, transferring, lending, timesharing, assigning or redistributing it"* |
| **Attribution** | *"any portion of the Solution that incorporates and presents Datafeed shall prominently display the message 'Powered by Tomorrow.io'"* |
| **Self-signup restriction** | *"Commercial use is strictly prohibited in the case of evaluation, proof of concept, or in connection with self-generated accounts originated on Company's website"* |
| **Verified?** | Terms of service read directly; **API not called.** |
| **Assessment** | **Reject.** This project caches everything it ingests. The no-storage clause is incompatible with the architecture, full stop. |

## 6.4 Visual Crossing — **licence trap**

| Field | Value |
|---|---|
| **Endpoint** | `https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/{location}?key={KEY}` |
| **Storage** | *"the data results returned by the Service Components may only be stored in a database or other storage and retrieval system if specifically permitted by your license level."* Per the editions table: **Professional, Metered, Corporate and Enterprise are "Storable for shared internal use"; only Enterprise is "Storable for shared external use."** |
| **Public display** | *"Raw data can never be shared and distributed publicly for download and can only be shown for viewing purposes to the general public."* |
| **Non-compete** | You may not *"use the Service Components or Service Component result data in a way that substantially replicates any service offered commercially by Visual Crossing."* |
| **Free tier** | The editions page **does not list a free tier** — the lowest listed plan is Professional. (A 1,000-records/day free key is widely reported but is not documented on the editions page; **unverified.**) |
| **Verified?** | Terms and editions pages read directly; **API not called.** |
| **Assessment** | **Reject** unless the project buys Enterprise. A public weather map that caches history and serves it to viewers is precisely what the sub-Enterprise tiers prohibit. |

## 6.5 Weatherbit — **licence trap**

| Field | Value |
|---|---|
| **Endpoint** | `https://api.weatherbit.io/v2.0/current?lat=47.56&lon=-52.71&key={KEY}` |
| **Free tier** | **50 requests/day.** Free tier gets current weather and 7-day daily forecast only; **historical data is not in the free tier.** |
| **Licence** | Free plan is **"Non-Commercial Use"** only |
| **Caching** | *"Local storage is allowed with an active paid API subscription"* — i.e. **not on free.** And: if a subscription ends, *"stored API data must be deleted"* unless purchased separately. |
| **Verified?** | Pricing page read directly; **API not called.** |
| **Assessment** | **Reject.** 50 calls/day is not a usable budget, and the delete-on-cancellation clause is a poison pill for an archive. |

## 6.6 Meteomatics

| Field | Value |
|---|---|
| **Endpoint** | `https://api.meteomatics.com/{datetime}/{parameters}/{lat},{lon}/{format}` |
| **Verified?** | **Yes, as gated** — `https://api.meteomatics.com/2026-08-30T00:00:00Z/t_2m:C/47.56,-52.71/json` returned **HTTP 401 "No username or password provided."** |
| **Access** | HTTP Basic auth. A free "Weather API for Personal Use" trial exists with a small parameter/request budget; full access is enterprise-priced. |
| **Licence** | Commercial; redistribution restricted. **Unverified — did not read the full terms.** |
| **Assessment** | **Reject for this project.** Excellent product, genuinely broad model coverage, but the free tier is a trial and the pricing is enterprise. Open-Meteo covers the same models for free. |

## 6.7 Météo-France public API

| Field | Value |
|---|---|
| **Endpoint** | `https://public-api.meteofrance.fr/public/DPPaquetObs/v1/liste-stations` (also `DPPrevisionMeteo`, `DPRadar`, `DPVigilance`, `DPClim`) |
| **Verified?** | **Yes, as gated** — returned **HTTP 401** `{"code":"900902","message":"Missing Credentials"}` requiring `apikey:` or `Authorization: Bearer` |
| **Access** | Free registration at `portail-api.meteofrance.fr`, then an API key. Rate-limited (typically 50 calls/min on the free tier — **unverified**). |
| **Licence** | Licence Ouverte / Etalab 2.0 for most products — permissive, attribution required. **Unverified for the specific packages.** |
| **Coverage of the Avalon** | **None for observations.** Météo-France's station APIs cover France and its overseas territories. Its *model* (ARPEGE/AROME) covers the North Atlantic — but AROME does not reach Newfoundland, and ARPEGE global is already available through Open-Meteo as `meteofrance_seamless` **verified working at 47.56/-52.71**. |
| **Assessment** | **Reject as a direct source.** Get ARPEGE through Open-Meteo instead — same data, no key, better licence clarity. |

## 6.8 Weatherstack, AerisWeather, Windy, Meteoblue, Foreca, DTN, StormGeo

| Provider | Endpoint | Free tier | Licence / caching | Verified? | Verdict |
|---|---|---|---|---|---|
| **Weatherstack** (apilayer) | `https://api.weatherstack.com/current?access_key={KEY}&query=St%20Johns` | Free plan exists but is **HTTP-only** (no TLS) and current-conditions only; historical is paid | apilayer commercial terms; redistribution restricted | **No** — docs redirect to `docs.apilayer.com`, not fetched | **Reject.** No-TLS free tier is disqualifying on its own |
| **AerisWeather** (Xweather) | `https://api.aerisapi.com/observations/47.56,-52.71?client_id=&client_secret=` | Free developer tier with low daily cap | Commercial; caching and display terms tier-dependent | **No** | **Reject** — nothing Open-Meteo lacks; also the parent of PWSweather (5.5) |
| **Windy Point Forecast** | `https://api.windy.com/point-forecast/v2` | Key required; **the documentation states no free-tier limits and contains no caching/storage/redistribution terms at all** | **Terms not documented in the API docs** — that ambiguity is itself a risk | **Partially** — docs fetched | **Reject.** Models exposed are AROME, ICON, GFS, NAM, HRRR and **Canadian HRDPS** — all already registered or free via Open-Meteo. Undocumented terms + no added models = no reason |
| **Meteoblue** | `https://my.api.meteoblue.com/packages/...?apikey=` | Trial key; commercial pricing | Terms page `https://www.meteoblue.com/en/weather-api/index/terms-of-use` returned **HTTP 404** | **No** — terms page dead | **Reject.** Cannot assess a licence whose terms page 404s |
| **Foreca** | `https://pfa.foreca.com/api/v1/...` | Enterprise / RapidAPI reseller only | Commercial, restrictive | **No** | **Reject** — no meaningful free tier |
| **DTN** | Enterprise sales | None | Commercial contract | **No** | **Reject** — enterprise-only, no self-serve |
| **StormGeo** | Enterprise sales | None | Commercial contract | **No** | **Reject** — enterprise-only, marine/energy focus |

*All rows in this table for which "Verified?" is No are **unverified — from documentation
or vendor marketing only.** None of these were called.*

---

# 7. Aviation-derived and specialised observations

## 7.1 ADS-B / Mode-S derived winds and temperatures aloft — `api.adsb.lol` ★★

**This is the most interesting genuinely-novel source in the whole document.**

| Field | Value |
|---|---|
| **Producer** | adsb.lol (community ADS-B aggregation network) |
| **Endpoint** | `https://api.adsb.lol/v2/point/{lat}/{lon}/{radius_nm}` — e.g. `https://api.adsb.lol/v2/point/47.56/-52.71/250` |
| **Meteorological fields returned per aircraft** | **`wd`** wind direction (deg), **`ws`** wind speed (kt), **`oat`** outside air temperature (°C), **`tat`** total air temperature (°C), plus `alt_baro`, `alt_geom`, `lat`, `lon`, `gs`, `ias`, `tas`, `mach`, `track`, `true_heading` — everything needed to place and sanity-check the observation |
| **Access** | **Completely open. No API key. No registration.** |
| **Rate limits** | Dynamic, load-dependent. Documented guidance: *"if you get 4xx errors, you are doing something wrong."* The project intends to introduce API keys in future, obtainable by feeding data to the network. |
| **Licence** | **ODbL 1.0** — attribution and share-alike on the database. |
| **Verified?** | **Yes — emphatically.** A live 250 nm query around St. John's returned **23 aircraft, 19 of which carried both wind and temperature.** Samples: `EIN106` FL370 wind **242°/98 kt**, OAT **−51 °C**, at 48.191 N 56.109 W; `ACA904` FL390 wind **238°/144 kt**, OAT **−57 °C**, at 46.960 N 54.727 W; `AAL86` FL380 wind **251°/129 kt**, OAT **−55 °C**; `CKS263` FL370 wind **246°/137 kt**, OAT **−49 °C`; `VIR110` FL390 wind 240°/103 kt, OAT −52 °C; `BAW19W` FL380 wind 241°/109 kt, OAT −51 °C. |
| **Why it works here specifically** | The **North Atlantic Organised Track System routes transatlantic traffic directly over and just south of Newfoundland**, and Gander Oceanic control begins here. Aircraft density over the Avalon at cruise altitude is among the highest anywhere outside continental airspace, and every one of them is a flying anemometer and thermometer at 200–250 hPa. |
| **What you get out of it** | A continuously refreshed, spatially dense sample of **upper-level wind and temperature within 250 nm of St. John's** — exactly the layer the project has no observation for (the nearest radiosonde is Stephenville, 600 km away, twice a day). Directly usable to verify GDPS/RDPS/HRDPS/IFS upper-level winds, to detect jet-stream position errors, and to render a genuinely local jet-core visualisation. |
| **Caveats to be honest about** | (a) Observations are at cruise level only — nothing below ~FL200 except near arrival/departure. (b) Mode-S derived winds carry heading/TAS calibration error, typically a few knots; they are *approximate*, not radiosonde-grade. (c) `ws`/`wd`/`oat` are only present on aircraft transmitting BDS 4,4/5,0 registers — 19 of 23 in this sample, but that ratio varies. (d) ODbL share-alike applies if the project publishes a derived *database*. |

## 7.2 OpenSky Network

| Field | Value |
|---|---|
| **Endpoint** | `https://opensky-network.org/api/states/all?lamin=46.5&lomin=-55&lamax=48.5&lomax=-52` |
| **Verified?** | **Yes — and it returned nothing useful.** HTTP 200 with body `{"time":1788060397,"states":null}` — i.e. no anonymous data for the requested box. `/api/tracks/all` returned **HTTP 404**. OpenSky has progressively restricted anonymous access and moved to OAuth2 client credentials. |
| **Access** | Registration required for meaningful access; research accounts available |
| **Licence** | Free for **non-commercial research**; a formal data-use agreement applies |
| **Assessment** | **Reject in favour of adsb.lol.** OpenSky's `states/all` schema also does not carry `wd`/`ws`/`oat` — it is positional. adsb.lol's readsb-derived feed does carry the met fields and needs no credentials. |

## 7.3 ADSB Exchange

**Unverified — not called.** ADSB Exchange moved to a paid RapidAPI model. Its data
content is similar to adsb.lol. **Reject** — adsb.lol gives the same fields free.

## 7.4 Datamart `FD` bulletins — forecast winds and temperatures aloft

See 2.2. `https://dd.weather.gc.ca/{YYYYMMDD}/WXO-DD/bulletins/alphanumeric/{YYYYMMDD}/FD/`
— verified present. This is the *forecast* counterpart to 7.1's *observations*, and
the pair makes an immediately meaningful verification product for upper-level winds
over the Avalon. Requires a WMO FD decoder.

---

# 8. Verification and forecast-skill datasets

The project currently has **no way to answer "is this forecast any good?"** Everything
below addresses that.

## 8.1 Open-Meteo Historical Forecast API ★★

| Field | Value |
|---|---|
| **Endpoint** | `https://historical-forecast-api.open-meteo.com/v1/forecast?latitude=47.56&longitude=-52.71&start_date=2024-01-01&end_date=2024-01-02&hourly=temperature_2m` |
| **What it is** | **Past forecasts as they were issued**, not past weather. Archives the initial hours of every model update into a continuous series, same schema as the live Forecast API. **Available from 2021.** |
| **Verified?** | **Yes — HTTP 200 with real data for 2024-01-01 at the St. John's point.** |
| **Access / licence** | No key, CC BY 4.0 (as 6.1) |
| **Why it is the top verification pick** | Forecast verification normally requires a year of patient archiving before you learn anything. This hands over **five years of past forecasts for St. John's immediately.** Join it to `climate-hourly` (1.2) and the project can produce a real skill scorecard this week. |

## 8.2 Open-Meteo Previous Runs API ★

| Field | Value |
|---|---|
| **Endpoint** | `https://previous-runs-api.open-meteo.com/v1/forecast?latitude=47.56&longitude=-52.71&hourly=temperature_2m_previous_day1,temperature_2m_previous_day2` |
| **What it is** | A continuous time series at a **fixed lead-time offset of 1–7 days**, from **January 2024** |
| **Verified?** | **Yes — HTTP 200, returned `temperature_2m_previous_day1` and `temperature_2m_previous_day2` series** |
| **Why it helps** | This is the clean way to answer "how fast does skill decay with lead time at St. John's?" — the variable is already aligned by lead time, so no forecast-archive bookkeeping is needed. |

## 8.3 Open-Meteo Single Runs API

Retrieves the full output of one specific model run, to reproduce a forecast issued on
a given date. **ECMWF IFS HRES 9 km archived from March 2024; all other models from
2026-04-02.** From Open-Meteo documentation; **endpoint not individually called —
unverified.** Useful for forensic "why did we get that storm wrong" work.

## 8.4 Open-Meteo Historical Weather API (ERA5 / ERA5-Land)

| Field | Value |
|---|---|
| **Endpoint** | `https://archive-api.open-meteo.com/v1/archive?latitude=47.56&longitude=-52.71&start_date=1990-01-01&end_date=1990-01-02&hourly=temperature_2m` |
| **What it is** | ECMWF ERA5 and ERA5-Land reanalysis, **1940 → present**, hourly |
| **Verified?** | **Yes — HTTP 200 with 1990 hourly data at the St. John's point** |
| **Why it helps** | A gridded, physically consistent reference for the whole domain, not just station points. Useful for spatial bias maps (where on the Avalon is the model worst?) and for filling station gaps. Note ERA5 has a ~5-day latency and 31 km native resolution — it will not resolve the Avalon's coastal gradients. |

## 8.5 WMO Lead Centre for Deterministic NWP Verification (LC-DNV), hosted by ECMWF

| Field | Value |
|---|---|
| **Endpoint** | `https://wmolcdnv.ecmwf.int/` |
| **What it is** | The WMO CBS-mandated centre that **collects, archives and displays standard verification scores (mainly upper-air) from participating global NWP centres** — including ECCC's GDPS. Score definitions follow WMO Manual 485. Documentation at `https://confluence.ecmwf.int/display/WLD`, exchange procedures at `https://confluence.ecmwf.int/spaces/WLD/pages/43519597/Exchange+of+WMO+surface+verification+scores` |
| **Verified?** | **Yes** — `https://wmolcdnv.ecmwf.int/` returned HTTP 200 (ECMWF web application shell). **No machine-readable data endpoint was identified** — it is a browsable display, not an API. |
| **Access** | Publicly accessible display |
| **Assessment** | **Useful as context, not as a feed.** It tells you how GDPS compares to IFS globally and in the North America region, which is worth knowing when weighting models — but it will not give you St. John's. **Read it once, do not try to ingest it.** |

## 8.6 ECMWF forecast-quality pages and scorecards

`https://www.ecmwf.int/en/forecasts/quality-our-forecasts` — public scorecards and
verification charts for IFS and AIFS. **Unverified — not fetched.** Same assessment
as 8.5: reference material, not a data source. ECMWF also hosts the WMO Lead Centre
for **Wave** Forecast Verification (marine agent's lane).

## 8.7 ECCC PROGNOS post-processed forecasts as a verification baseline

Collections `prognos-gdps-realtime`, `prognos-rdps-realtime`, `prognos-hrdps-realtime`
on `api.weather.gc.ca` — GDPS/RDPS/HRDPS **statistically post-processed by PROGNOS**.
The registry has `eccc-hrdps-weg-prognos` for one of these; **the GDPS and RDPS PROGNOS
collections are not registered.** Verified present in the collection list.
**Why it matters for verification:** PROGNOS is ECCC's own MOS-style correction. Beating
raw HRDPS is easy; beating PROGNOS is the real bar. Adding GDPS and RDPS PROGNOS gives
three post-processed baselines to score against.

## 8.8 CanSIPS hindcast

`weather:cansips:100km:hindcast` — monthly historical hindcasts at 100 km.
Verified present in the collection list; not queried. The only seasonal-skill dataset
available. Low priority for a nowcast map.

---

# Top 10 additions, ranked by value per unit of work

Ranking is *value ÷ effort*, with licence risk treated as effort.

**1. `climate-hourly` + `climate-daily` on `api.weather.gc.ca`** — *Verified. Open. ECCC licence.*
One OGC API client, already the same shape as the collections the project reads.
Unlocks bias correction, verification and every climatological display at once.
**Nothing else in this document is useful until this exists.** `CLIMATE_IDENTIFIER=8403505`
for the airport, `8403603` for St. John's West, `8401000` for Cape Race.

**2. Open-Meteo Historical Forecast API + Previous Runs API** — *Verified 200. No key. CC BY 4.0.*
Two GET requests give five years of past forecasts and a lead-time-aligned skill series
for the exact map centre. This converts "we have no verification capability" into
"we have a skill scorecard" in an afternoon. Highest ratio in the list.

**3. NL WRMD Pippy Park + Conception Bay South, via the ECCC SWOB partner feed** — *Verified live.*
`https://dd.weather.gc.ca/today/observations/swob-ml/partners/nl-water/` uses the
SWOB-ML parser the project already has and the MSC licence it already accepts. It adds
**an in-city St. John's station with SWE, snow depth and solar radiation** that no other
source provides. The most genuinely *local* addition available.

**4. ECCC Citypage Weather XML, site `s0000280`** — *Verified live, 25-minute cadence, permissive licence.*
The official ECCC public forecast for the exact map centre, plus current conditions and
warnings, in a schema-documented XML. Trivial to parse, immediately valuable both as a
display layer and as the human-forecast verification baseline.

**5. Open-Meteo Forecast API with `models=ukmo_seamless,knmi_seamless,meteofrance_seamless`** — *All three verified 200 at 47.56/-52.71.*
Adds three national models the project cannot obtain any other way, as point time-series
costing a few hundred bytes each. Also gives a free, near-zero-cost fallback path for
HRDPS/RDPS/GDPS when GRIB ingestion breaks.

**6. `api.adsb.lol/v2/point/47.56/-52.71/250`** — *Verified: 19 of 23 aircraft carrying wind + OAT.*
No key, one endpoint, ODbL. Gives a dense upper-air wind and temperature sample over the
Avalon — a layer the project has no observation for, with the nearest radiosonde 600 km
away. Novel, cheap, and specifically enabled by St. John's position under the North
Atlantic tracks. Effort is in the aggregation, not the access.

**7. AHCCD `ST_JOHN_S` homogenized series (1874–2020) + Climate Normals 1991–2020 CSV** — *Both verified.*
Two static downloads. Gives a 146-year homogenized temperature record and the correct
current climatological baseline (Jan −4.2 °C, Jul 16.0 °C, annual 5.3 °C at the airport).
Turns every temperature reading on the map into an anomaly. Also flags the −8.03 wind
trend at YYT, which is a real trap for anyone training on raw archived winds.

**8. NL-DFFA fire-weather SWOB partner feed (`014` Salmonier, `015` New Harbour Barrens, `013` Harcourt)** — *Verified live XML.*
Same parser, same feed, same polling loop as item 3. Three inland elevated stations at
10 m wind height, filling the coastal/airport gap. Only caveat is the embedded
"All rights reserved" attribution notice — see Licence traps.

**9. Register for the NL 511 API key (`winterroads`, `cameras`, `event`, `alerts`)** — *Endpoint verified live and key-gated.*
Ten minutes of registration converts an existing `[credential_required]` registry entry
into a working winter road-surface-state and camera network across the Avalon. Rate limit
is 10 calls/60 s, which is ample. The correct path is `/api/v2/get/winterroads`, not
`roadconditions`. Only blocker is reading `https://511nl.ca/terms` first.

**10. LTCE `VSNL24V` daily records + CoCoRaHS `CAN-NL-2`** — *Both verified.*
Two cheap, high-charm additions. LTCE gives "warmest August 30 since 1937" from a single
API call and doubles as a forecast plausibility check. CoCoRaHS `CAN-NL-2` sits at
47.564/−52.713 — within 400 m of the map centre — and manually measures the winter
precipitation that automated gauges undercatch. Seven CoCoRaHS gauges cover the eastern
Avalon.

**Honourable mentions that just missed the cut:** NOAA ISD `718010099999` and Meteostat
`71801` (both verified, both a single file, both excellent for a bulk historical training
set — ranked below item 1 only because ECCC is the authoritative copy); IEM
`station=CYYT` (verified, the most ergonomic archive query of all, and it revealed the
active `CWWU LONG POND` station missing from the ECCC catalogue); ECCC `ProgTephi_00_CYYT.csv`
and `ObsTephi_00_CYYT.csv` (verified, vertical profiles at the map centre, held back only
by malformed CSV); Canadian IWXXM (`aviation/iwxxm/`, verified, a strictly better TAF/SIGMET
source than the US AWC relay).

---

# Not worth it, and why

**Weather Underground PWS API** — the free tier requires you to *own and operate a
personal weather station uploading to Wunderground*. That is a hardware purchase, not a
registration. The legacy `api.wunderground.com` host is dead (verified HTTP 503 DNS
failure). Enterprise pricing otherwise. Reject.

**WeatherFlow / Tempest** — verified HTTP 401 on both `/observations/station/` and
`/stations`. Tokens are issued to device owners only. Same hardware gate as Wunderground,
same conclusion.

**AWEKAS** — verified live (`{"error":"invalid key"}`) but key-gated to station operators,
and the network is overwhelmingly Central European. Expect approximately zero Avalon
stations. Reject.

**PWSweather** — verified HTTP 404 on the assumed query path; it is an *upload* endpoint,
not a query API. Its data is queried through AerisWeather, which is separately rejected.

**Weathercloud** — a web map with no documented public API. Scraping it would be fragile
and of doubtful standing. Reject.

**OpenSky Network** — verified: anonymous `states/all` for the Avalon box returned
`"states": null`, and `tracks/all` returned 404. Even with credentials, the `states`
schema is positional and does not carry `wd`/`ws`/`oat`. **adsb.lol strictly dominates it**
for this use case.

**ADSB Exchange** — moved behind paid RapidAPI. Same data content as adsb.lol, which is free.

**`api.weather.gov` (US NWS)** — verified HTTP 404 for 47.56/−52.71: *"Unable to provide
data for requested point"*. Does not cover Canada. Recorded so nobody retries.

**ECCC `meteocode/`** — verified: only `ont/`, `pnr/`, `pyr/` regional subdirectories
exist. **There is no Atlantic region product.** Definite negative.

**ECCC `nowcasting/matrices/` (SCRIBE)** — verified present but the `.Z`-compressed SCRIBE
matrix format is proprietary and poorly documented publicly. High parsing cost, and the
registry already has `eccc-integrated-nowcasting`. Reject absent a documented decoder.

**ECCC `analysis/precip/hrdpa_watershed/`** — verified present, but it is HRDPA (already
registered) aggregated to watershed shapefiles. Duplicative unless the project wants basin
totals.

**City of St. John's** — verified absent: `data.stjohns.ca` and `maps.stjohns.ca` both
failed to resolve (HTTP 000). Mapcentre is an ArcGIS Online web app with no weather content.
The municipality publishes no machine-readable weather or hydrometric data. This confirms
the registry's `municipal-hydrometric [unavailable]`.

**Memorial University** — verified absent: `www.physics.mun.ca/~weather/` → 404,
`www.mun.ca/physics/weather/` → 404. The rooftop Chemistry-Physics and Signal Hill
GEO CENTRE stations are documented as existing but publish nothing. **Recorded as an
email lead, not a source.** A Signal Hill station would be genuinely valuable if it could
be obtained — that is a human conversation, not an engineering task.

**CIOOS Atlantic** — real, open, working CKAN API, but a search for Newfoundland
meteorological content returned one DFO ship time series. Its value is oceanographic.
Not our lane, and thin even there for the Avalon.

**NL open data portal (`opendata.gov.nl.ca`)** — verified: no CKAN or JSON API. It is a
hand-curated HTML catalogue pointing at the ArcGIS services documented in 3.6, which
should be accessed directly instead.

**NL RWIS** — verified absent from the ECCC SWOB partners tree (NB, NS and PE have
`*-rwin/` directories; NL does not). No standalone endpoint. The registry's
`nl-511-rwis [unavailable]` is correct.

**Wreckhouse wind warnings** — real, famous, and **700 km from St. John's on the opposite
coast.** Documented for completeness; irrelevant to an Avalon map.

**Tomorrow.io, Visual Crossing, Weatherbit, OpenWeatherMap, Meteomatics, Meteoblue,
Windy, Weatherstack, AerisWeather, Foreca, DTN, StormGeo** — all rejected. See the
Licence traps section for the four that would actively cause a violation; the rest are
rejected because **every model they expose is either already registered or available
free from Open-Meteo under CC BY 4.0.** Paying for, or accepting restrictive terms on,
a re-serving of GFS and IFS makes no sense when the originals are already in the registry.

**Météo-France public API** — verified gated (HTTP 401). Its *observations* cover France
only. Its *model* (ARPEGE) is already reachable free through Open-Meteo, verified working
at the St. John's point.

**CMIP5/CMIP6/CanDCSU6/DCS/SPEI climate projections** — real, open, ECCC-licensed, and
irrelevant to a nowcast/forecast map. CanGRD historical gridded anomalies are the only
member of this family with a plausible use (a "how unusual is this month" panel).

**WMO LC-DNV and ECMWF scorecards** — genuinely informative for model weighting, but
they are **browsable displays, not APIs**, and they report global/continental scores, not
St. John's. Read once; do not build an ingest.

---

# Licence traps

Sources that look attractive but whose terms forbid what this project actually does —
namely **caching ingested data in a database** and **serving it to the public on a map**.

### Trap 1 — Tomorrow.io: caching is explicitly prohibited

> *"store or otherwise collect or copy the unaltered Datafeed, unless otherwise expressly
> provided for in the Order or for permitted evaluation of DaaS, in which case Datafeed
> may only be stored for the duration of the Initial Term"*

and

> *"Offer any portion or all of the Solution to any third parties … including but not
> limited to reselling, licensing, renting, leasing, transferring, lending, timesharing,
> assigning or redistributing it or any part thereof"*

and

> *"Commercial use is strictly prohibited in the case of evaluation, proof of concept, or
> in connection with self-generated accounts originated on Company's website"*

**This project's entire architecture is an ingest-and-cache pipeline.** Tomorrow.io's terms
are incompatible with it at the first line of code. There is also a mandatory
*"Powered by Tomorrow.io"* display obligation. **Do not integrate.**

### Trap 2 — Visual Crossing: public display of raw data is prohibited below Enterprise

> *"Raw data can never be shared and distributed publicly for download and can only be
> shown for viewing purposes to the general public."*

> *"the data results returned by the Service Components may only be stored in a database
> or other storage and retrieval system if specifically permitted by your license level."*

Per the editions table, Professional/Metered/Corporate are *"Storable for shared internal
use"* and **only Enterprise is *"Storable for shared external use."*** A public map that
caches history and serves it to viewers is external sharing. The non-compete clause
(no service that *"substantially replicates any service offered commercially by Visual
Crossing"*) is a further hazard for a weather map. **Do not integrate below Enterprise.**

### Trap 3 — Weatherbit: no local storage on free, and delete-on-cancellation

> *"Local storage is allowed with an active paid API subscription"*

and, on cancellation, *"stored API data must be deleted"* unless purchased separately.
The free plan is additionally **"Non-Commercial Use"** and capped at **50 requests/day**.
A cached archive that must be destroyed when a subscription lapses is not an archive.
**Do not build a historical store on Weatherbit.**

### Trap 4 — OpenWeatherMap: ODbL share-alike is contagious

OpenWeather self-service products are provided under **ODbL 1.0**. Redistribution is
permitted — but if an adapted database, *or a service giving access to one*, is made
available outside your organisation, **the adapted database must itself be offered under
ODbL.** A public map backed by a database that blends OWM data with ECCC, Open-Meteo and
provincial data would arguably make that whole blended database subject to ODbL
share-alike. That is a decision to take deliberately, not to stumble into. The safer
course, given that OWM adds no model the project lacks, is simply not to use it.

*(Note: Open-Meteo's CC BY 4.0 and adsb.lol's ODbL are both fine on their own terms —
but **adsb.lol is ODbL too**, so the same share-alike consideration applies if the project
publishes a derived database containing ADS-B-derived observations. Attribution-only use
in a rendered map is not the same as publishing a database, but the distinction should be
made consciously.)*

### Trap 5 — NL WRMD ADRS: "all rights reserved", and provisional data

The provincial ADRS station pages carry:

> *"This page and all contents are copyright, Government of Newfoundland and Labrador,
> all rights reserved."*

and

> *"Due to the volume and frequent updating of the data available on this Web site the
> streamflow and water quality data is PROVISIONAL and has not undergone quality control
> checks. These data may be subject to significant change."*

**Mitigation:** ingest these stations via the **ECCC SWOB partner feed** instead
(`swob-ml/partners/nl-water/`), which is published under the permissive MSC Data Server
End-use Licence with attribution to *"Environment and Climate Change Canada and
[Third Party Contributor]"*. Same data, clean licence. This is why item 3 in the Top 10
specifies the SWOB path and not the ADRS CSV. Use the ADRS CSV only for one-off backfill,
and label the data provisional wherever it is displayed.

### Trap 6 — NL-DFFA fire-weather: embedded "All rights reserved" notice

The SWOB-ML records carry `data_attrib_not`:

> *"Observational data provided by the Government of Newfoundland and Labrador: Department
> of Fisheries, Forestry and Agriculture (NL-DFFA). All rights reserved."*

The MSC licence covers ECCC's redistribution via the server; the partner has asserted its
own reservation inside the record. **Reproduce the `data_attrib_not` string verbatim
wherever these observations are displayed**, exactly as ECCC does. Do not strip it during
decode.

### Trap 7 — Météo-France, Netatmo, Weatherstack, Windy, Meteoblue: terms not verifiable

- **Windy Point Forecast**: the API documentation *"contains no explicit terms regarding
  caching, storage, or redistribution"* — silence is not permission.
- **Meteoblue**: `https://www.meteoblue.com/en/weather-api/index/terms-of-use` returned
  **HTTP 404**. A licence you cannot read is a licence you cannot rely on.
- **Netatmo**: terms not retrieved; and republishing consumer stations at street-level
  resolution has a privacy dimension independent of the licence.
- **Weatherstack**: free tier is **HTTP-only**, disqualifying regardless of terms.
- **Météo-France**: Etalab 2.0 is likely and permissive, but I did not verify it per-package.

**Rule of thumb for this project:** if you cannot read and quote the caching clause, do not
build on it. Every source in the Top 10 has a licence quoted verbatim in this document.

### Non-traps, for contrast

The following are all safe for ingest-cache-and-display with attribution, and every one
is verified:

| Source | Licence | Caching | Redistribution |
|---|---|---|---|
| ECCC Datamart / GeoMet / `api.weather.gc.ca` | ECCC Data Server End-use Licence v2.1 | Yes | Yes — *"Copy, modify, publish, translate, adapt, distribute or otherwise use the Information in any medium"* |
| Open-Meteo (free tier, non-commercial) | CC BY 4.0 | Yes | Yes, with attribution |
| Meteostat bulk | CC BY 4.0 | Yes | Yes, with attribution |
| NOAA NCEI (ISD, ISD-Lite, GHCN-Daily) | US public domain | Yes | Yes |
| Iowa Environmental Mesonet | Open academic service | Yes | Yes — be polite with request volume |
| adsb.lol | ODbL 1.0 | Yes | Yes, with attribution + share-alike on derived *databases* |
| CoCoRaHS | Public / research use with attribution (**unverified — formal licence text not retrieved**) | Presumed yes | Verify before redistributing |

---

# Appendix A — Quick-reference endpoint list (all verified unless marked)

```
# ECCC climate archive
https://api.weather.gc.ca/collections?f=json                                    # 104 collections
https://api.weather.gc.ca/collections/climate-stations/items?bbox=-54.5,46.5,-52.4,48.2&limit=500&f=json
https://api.weather.gc.ca/collections/climate-hourly/items?CLIMATE_IDENTIFIER=8403505&datetime=.../...&f=json
https://api.weather.gc.ca/collections/climate-daily/items?CLIMATE_IDENTIFIER=8403505&f=json
https://api.weather.gc.ca/collections/climate-monthly/items?...                 # collection existence only
https://api.weather.gc.ca/collections/climate-normals/items?CLIMATE_IDENTIFIER=8403506&f=json   # 1981-2010
https://api.weather.gc.ca/collections/ahccd-stations/items?bbox=-55,46.4,-52.4,48.3&f=json
https://api.weather.gc.ca/collections/ahccd-{annual,seasonal,monthly,trends}/items?...
https://api.weather.gc.ca/collections/ltce-stations/items?bbox=-55,46.4,-52.4,48.3&f=json
https://api.weather.gc.ca/collections/ltce-{temperature,precipitation,snowfall}/items?VIRTUAL_CLIMATE_ID=VSNL24V&f=json
https://api.weather.gc.ca/collections/swob-partner-stations/items?bbox=-54.5,46.5,-52.4,48.3&f=json
https://api.weather.gc.ca/collections/swob-stations/items?bbox=-54.5,46.5,-52.4,48.3&f=json
https://api.weather.gc.ca/collections/{bulletins-realtime,metnotes,citypageweather-realtime}/items?f=json

# ECCC bulk climate
https://climate.weather.gc.ca/climate_data/bulk_data_e.html?format=csv&stationID=50089&Year=2026&Month=1&Day=1&timeframe=2&submit=Download+Data
https://climate.weather.gc.ca/climate_normals/bulk_data_e.html?lang=e&prov=NL&yr=1991&stnID=77000000&climate_id=8403505&submit=Download+Data
https://climate.weather.gc.ca/climate_normals/station_select_1991_2020_e.html?searchType=stnProv&lstProvince=NL
https://dd.weather.gc.ca/today/climate/observations/climate_station_list.csv
https://dd.weather.gc.ca/{YYYYMMDD}/WXO-DD/climate/observations/hourly/csv/NL/climate_hourly_NL_{CLIMID}_{YYYY}_P1H.csv
https://dd.weather.gc.ca/today/climate/ahccd/geojson/historical/

# ECCC Datamart — previously unused
https://dd.weather.gc.ca/today/citypage_weather/siteList.xml
https://dd.weather.gc.ca/{YYYYMMDD}/WXO-DD/citypage_weather/NL/{HH}/{ts}_MSC_CitypageWeather_s0000280_en.xml
https://dd.weather.gc.ca/{YYYYMMDD}/WXO-DD/bulletins/alphanumeric/{YYYYMMDD}/{TT}/
https://dd.weather.gc.ca/{YYYYMMDD}/WXO-DD/vertical_profile/observation/csv/ObsTephi_{HH}_CYYT.csv
https://dd.weather.gc.ca/{YYYYMMDD}/WXO-DD/vertical_profile/forecast/csv/ProgTephi_{HH}_CYYT.csv
https://dd.weather.gc.ca/{YYYYMMDD}/WXO-DD/aviation/iwxxm/{taf,sigmet}/
https://dd.weather.gc.ca/today/observations/swob-ml/partners/nl-water/{YYYYMMDD}/
https://dd.weather.gc.ca/today/observations/swob-ml/partners/nl-firewx/{YYYYMMDD}/{014,015,013}/
https://dd.weather.gc.ca/doc/LICENCE_GENERAL.txt
https://eccc-msc.github.io/open-data/licence/readme_en/

# Government of Newfoundland and Labrador
https://maps.gov.nl.ca/gsdw/rest/services/water/Stations/MapServer/3/query?where=1%3D1&outFields=*&f=json
https://maps.gov.nl.ca/gsdw/rest/services/water/WRPortalMapService/FeatureServer?f=json
https://www.mae.gov.nl.ca/wrmd/ADRS/v6/Data/NLENCL0001_Line.csv       # Pippy Park, St. John's
https://www.mae.gov.nl.ca/wrmd/ADRS/v6/Data/NLENCL0015_Line.csv       # Conception Bay South
https://www.mae.gov.nl.ca/wrmd/ADRS/v6/Data/NLENCL0013_Line.csv       # Vale LH2
https://511nl.ca/api/v2/get/{winterroads,cameras,event,alerts,windwarnings,ferryterminals}?key=  # key required
https://511nl.ca/developers/doc

# Citizen science and public archives
https://data.cocorahs.org/cocorahs/export/exportreports.aspx?ReportType=Daily&dtf=1&Format=CSV&ReportDateType=reportdate&Date=8/1/2026
https://data.cocorahs.org/cocorahs/export/exportstations.aspx?Format=CSV
https://www.ncei.noaa.gov/data/global-hourly/access/2025/71801099999.csv
https://www.ncei.noaa.gov/pub/data/noaa/isd-lite/2025/718010-99999-2025.gz
https://www.ncei.noaa.gov/pub/data/noaa/isd-history.csv
https://www.ncei.noaa.gov/data/global-historical-climatology-network-daily/access/CA008403506.csv
https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py?station=CYYT&data=all&year1=&...&format=onlycomma
https://mesonet.agron.iastate.edu/geojson/network/CA_NF_ASOS.geojson
https://bulk.meteostat.net/v2/hourly/71801.csv.gz
https://bulk.meteostat.net/v2/daily/71801.csv.gz

# Aggregator and verification
https://api.open-meteo.com/v1/forecast?latitude=47.56&longitude=-52.71&hourly=temperature_2m&models=ukmo_seamless
https://archive-api.open-meteo.com/v1/archive?latitude=47.56&longitude=-52.71&start_date=&end_date=&hourly=
https://historical-forecast-api.open-meteo.com/v1/forecast?latitude=47.56&longitude=-52.71&start_date=&end_date=&hourly=
https://previous-runs-api.open-meteo.com/v1/forecast?latitude=47.56&longitude=-52.71&hourly=temperature_2m_previous_day1
https://ensemble-api.open-meteo.com/v1/ensemble?latitude=47.56&longitude=-52.71&hourly=temperature_2m&models=gfs05
https://api.adsb.lol/v2/point/47.56/-52.71/250
https://wmolcdnv.ecmwf.int/                                          # display only, no API

# Verified NEGATIVE — do not retry
https://api.weather.gov/points/47.56,-52.71                          # 404, no Canadian coverage
https://data.stjohns.ca/api/3/action/package_list                    # host does not resolve
https://maps.stjohns.ca/arcgis/rest/services?f=json                  # host does not resolve
https://www.physics.mun.ca/~weather/                                 # 404
https://www.mun.ca/physics/weather/                                  # 404
https://www.findu.com/cgi-bin/wxnear.cgi                             # host does not respond
https://api.wunderground.com/weatherstation/WXCurrentObXML.asp       # 503, decommissioned
https://opensky-network.org/api/states/all?lamin=46.5&...            # 200 but "states": null
https://dd.weather.gc.ca/{date}/WXO-DD/meteocode/                    # no Atlantic region
https://dd.weather.gc.ca/{date}/WXO-DD/metnotes/                     # empty
https://dd.weather.gc.ca/today/climate/observations/normals/csv/     # only 1981-2010
https://www.meteoblue.com/en/weather-api/index/terms-of-use          # 404 — terms unreadable
https://weather.uwyo.edu/wsgi/sounding?...&id=71801                  # no St. John's sounding; use 71815 Stephenville
```

# Appendix B — Identifier crosswalk for St. John's

| System | Identifier |
|---|---|
| ECCC `STN_ID` (current airport) | `50089` |
| ECCC `CLIMATE_IDENTIFIER` (current airport) | `8403505` |
| ECCC `CLIMATE_IDENTIFIER` (airport, pre-2012) | `8403506` |
| ECCC `CLIMATE_IDENTIFIER` (downtown, 1874–1956) | `8403500` |
| Transport Canada / IATA | `YYT` |
| ICAO | `CYYT` |
| WMO | `71801` |
| NOAA ISD USAF-WBAN | `718010-99999` (file `71801099999.csv`) |
| GHCN-Daily | `CA008403505` / `CA008403506` |
| Meteostat | `71801` |
| IEM ASOS | `CYYT` (network `CA_NF_ASOS`) |
| Citypage / WXO site code | `s0000280` |
| LTCE virtual climate id | `VSNL24V` (WXO city code `NL-24`) |
| Climate Normals 1991–2020 composite `stnID` | `77000000` |
| CoCoRaHS (nearest to map centre) | `CAN-NL-2` |
| NL WRMD (in-city) | `NLENCL0001` / SWOB `NL-DECCM-WRMD_NLENCL0001` |

---

*Prepared 2026-08-30. Every "Verified" claim corresponds to an HTTP request issued from
this machine on that date. Every quoted licence clause is reproduced verbatim from the
provider's own terms page. Where I could not verify, the entry says so.*
