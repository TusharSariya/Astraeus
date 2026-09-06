# North Atlantic forecast-model viability for Newfoundland

Last reviewed: 2026-09-03

Status: non-normative research. This note records evidence and recommendations;
it does not admit a provider, change a registry state, or alter V1 behavior.

## Question and decision boundary

The target is the whole Astraeus evidence box, not merely a point at St. John's:

```text
north 50.5 N
south 45.0 N
west  58.0 W
east  46.0 W
```

A candidate is useful only if it covers that box and the required upstream
sector, publishes relevant quantities with defined semantics, has a lawful and
stable machine path, and adds skill or uncertainty information. National
proximity or interest in the North Atlantic does not establish any of those
facts.

## Live NOAA coverage observations

On 2026-09-03 NOAA NOMADS returned HTTP 200 binary GRIB2 subsets for total cloud
over all four declared bounds:

| Product | File | Response |
| --- | --- | --- |
| RAP full-domain grid | `rap.t00z.awp130pgrbf00.grib2` | 133,177 bytes, `GRIB` signature |
| NAM parent grid | `nam.t00z.awphys00.tm00.grib2` | 1,790 bytes, `GRIB` signature |

The associated inventories exposed surface visibility and gust plus
pressure-level temperature, relative humidity, and wind. NAM files extended to
forecast hour 84 in the probed directory; the RAP graphics exposed hourly
forecast frames. These observations validate one-run rectangular access and
field presence. They do not validate boundary quality, cadence, latency,
completeness, cloud semantics, or forecast skill.

Primary sources:

- [NOAA RAP and RRFS model fields](https://rapidrefresh.noaa.gov/RAP/)
- [NCEP NAM product inventory](https://www.nco.ncep.noaa.gov/pmb/products/nam/)
- [NOMADS production data](https://nomads.ncep.noaa.gov/pub/data/nccf/com/)

## Candidate conclusions

| Family | Coverage/access conclusion | Proposed role |
| --- | --- | --- |
| HRDPS | Native Canadian regional coverage; existing primary | Primary regional evidence |
| RDPS | Native Canadian regional coverage | Canadian fallback and comparison |
| REPS | Canadian ensemble family where validated | Within-family uncertainty |
| ECMWF IFS | Official global open data; repository adapter-backed | Independent deterministic comparison |
| ECMWF ENS | Official global ensemble; repository adapter-backed | High-priority uncertainty family |
| ECMWF AIFS/ENS | Global official data; cloud value still to prove | AI scenario families, not extra ECMWF votes |
| DWD ICON Global | Official anonymous global GRIB; adapter-backed | Independent deterministic comparison |
| NOAA GFS/GEFS | Official global data; existing adapters | One NOAA representative plus ensemble family |
| NOAA RAP | Full-box subset observed once | Event-day optional candidate |
| NOAA NAM parent | Full-box subset observed once | Lower-priority NOAA diagnostic scenario |
| NOAA RRFS-NA | Visible in experimental graphics; stable ordinary production path not established | Conditional only |
| NOAA HRRR | CONUS/Alaska domains do not cover the box | Exclude |
| Météo-France ARPEGE World | Global values observed through Open-Meteo | Research until native official path is accepted |
| UKMO Global | Global values observed through Open-Meteo | Owner-only research while terms/path are restricted |
| Icelandic, Nordic, Greenlandic and Iberian regional systems | No documented full-box grid identified | Exclude until exact grid evidence says otherwise |
| Russian products | Product, access, licence, coverage and reliability not pinned | Unvalidated research candidate |

Official global-feed references:

- [ECMWF open data](https://www.ecmwf.int/en/forecasts/datasets/open-data)
- [DWD open data](https://www.dwd.de/EN/ourservices/opendata/opendata.html)

## Centre independence

Model count is not independent-evidence count. GFS, GEFS, RAP, NAM and RRFS are
NOAA/NCEP families. IFS, IFS ENS and AIFS are ECMWF families. A centre-level
comparison should use at most one deterministic representative per centre at
an instant. Other deterministic products remain named scenarios; ensemble
members remain one correlated distribution.

The delivery route does not create independence. UKMO delivered by Open-Meteo
is still UK Met Office evidence, with Open-Meteo named as intermediary.

## Field comparability

Availability does not make two same-named fields comparable. In particular,
HRDPS opacity-weighted total cloud and GFS geometric-overlap total cloud can be
displayed as disagreement but cannot be averaged without an accepted mapping.
Every cross-model statistic must use the field catalogue's quantity, vertical
support, phase convention, and temporal semantics.

## Recommended validation order

1. IFS and ICON Global live smoke and retrospective verification.
2. IFS ENS as the next independent uncertainty family.
3. RAP multi-cycle full-box, eastward-transect, latency and skill measurements.
4. NAM parent-grid measurements using the same protocol.
5. Native official access and terms work for UKMO Global and ARPEGE World.
6. RRFS only after the operational product and distribution stabilize.

Verification truth should come from DQF-passing GOES evidence and surface
observations, not another forecast model. Cases should include marine
fog/stratus, frontal cloud, and clear controls.
