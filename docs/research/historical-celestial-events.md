# Historical celestial events and visibility reconstruction

Last reviewed: 2026-08-10

## Purpose

This document describes how Astraeus should calculate or retrieve historical
Sun, Moon, eclipse, aurora, and other celestial-event data, then join those
events to historical weather and site visibility.

The objective is not merely to answer whether an event occurred. It is to
reconstruct, for a specific location and UTC interval:

```text
what was geometrically present
+ where it appeared in the sky
+ whether the site had an unobstructed view
+ whether the atmosphere permitted observation
+ what operational forecasts were available beforehand
+ what observers or instruments actually reported
```

Environmental retrieval is covered separately in
[Historical environmental-data retrieval](historical-data-retrieval.md).

## Executive recommendation

Use two fundamentally different acquisition strategies.

### Calculate deterministic geometry locally

Use:

```text
Skyfield
+ pinned JPL DE442 (`de442.bsp`) ephemeris
+ pinned leap-second and IERS Earth-orientation inputs
+ exact WGS84 observer location and elevation
+ explicit refraction and horizon conventions
```

This applies to:

- Sun and Moon altitude and azimuth;
- sunrise, sunset, and twilight;
- Moon phase and illumination;
- perigee, apogee, angular diameter, and conventional Moon labels;
- eclipse geometry and local visibility circumstances;
- planetary positions, conjunctions, transits, and many occultations;
- predicted meteor-shower radiant position.

Validate representative results against JPL Horizons, USNO, and authoritative
NASA eclipse catalogues. A paid astronomy API is not needed for this geometry.

### Retrieve stochastic and observational history

Use archives for:

- auroral drivers, oval estimates, geomagnetic activity, and optical reports;
- actual meteor activity and fireballs;
- comet brightness and morphology;
- novae, supernovae, and other discovered transients;
- the actual brightness or colour of a lunar eclipse;
- user-visible outcomes.

These cannot be recovered from celestial mechanics alone.

## Historical-data taxonomy

Do not collapse these records into a single `historical_event` type.

| Record type | Meaning | Example |
| --- | --- | --- |
| Deterministic calculation | Geometry computed from pinned inputs | Moon altitude at Halifax at 03:00 UTC |
| Event catalogue | Authoritative list or discovery record | NASA solar-eclipse catalogue |
| Issued forecast vintage | What a service predicted at a known issue time | An archived OVATION grid |
| Retrospective reconstruction | Model rerun using later or cleaned inputs | OVATION-like hindcast driven by final OMNI |
| Physical measurement | Instrumental state relevant to an event | Solar-wind Bz or a magnetometer trace |
| Optical observation | Evidence that light was actually detected | All-sky camera image or calibrated light curve |
| Human observation | A report with variable reliability | Naked-eye Aurorasaurus report |
| Conventional label | A rule applied to calculated events | Monthly blue Moon |

Only an issued forecast vintage answers what Astraeus could have known in
advance. A reconstruction can be scientifically better while still leaking
information that was unavailable at issuance time.

## Reproducible calculation foundation

### Recommended stack

| Tool or source | Role | Access | Recommendation |
| --- | --- | --- | --- |
| [Skyfield](https://rhodesmill.org/skyfield/) | Application-level ephemeris, almanac, topocentric geometry | Free/local | Primary engine |
| [JPL DE440/DE441](https://ssd.jpl.nasa.gov/doc/de440_de441.html) and later DE442 kernels | Planetary and lunar ephemerides | Free/local | Pin `de442.bsp` (DE442) for V1 modern dates; retain DE440 docs for historical comparison |
| [JPL Horizons API](https://ssd-api.jpl.nasa.gov/doc/horizons.html) | Authoritative observer/vector tables | Free hosted | Validation and diagnostics |
| [NAIF SPICE kernels](https://naif.jpl.nasa.gov/naif/data_generic.html) | Precise kernels, frames, advanced geometry | Free/local | Advanced science and validation |
| [Astropy coordinates/time](https://docs.astropy.org/en/latest/coordinates/solarsystem.html) | Coordinate frames, time scales, IERS integration | Free/local | Use where its ecosystem adds value |
| [USNO data services](https://aa.usno.navy.mil/data/) | Rise/set, phases, eclipse circumstances | Free hosted | Independent authoritative check |
| [IERS Earth orientation](https://www.iers.org/iers/en/organization/productcentres/rapidservicepredictioncentre/rapid) | UT1, polar motion, Earth orientation | Free download | Archive the exact file used |

### Astronomy access and software status

The hosted JPL and USNO services are not interchangeable with local software.
Record whether a result came from a raw service response or from a calculation
performed with locally pinned code and inputs.

| Resource | Interface and stewardship | Implementation note |
| --- | --- | --- |
| [Skyfield documentation](https://rhodesmill.org/skyfield/) and [official project repository](https://github.com/skyfielders/python-skyfield) | Maintained open-source Python library; local SDK | Pin the package and ephemeris file separately; the library does not make an unversioned hosted forecast call |
| [Horizons API](https://ssd-api.jpl.nasa.gov/doc/horizons.html) | Official JPL raw HTTP API | Archive the request parameters and complete response; JPL does not require a Python SDK |
| [`astroquery.jplhorizons`](https://astroquery.readthedocs.io/en/latest/jplhorizons/jplhorizons.html) | Maintained Astropy-affiliated community client for Horizons, not a JPL SDK | Useful client convenience, but preserve the generated query and raw Horizons response for auditability |
| [NAIF Toolkit](https://naif.jpl.nasa.gov/naif/toolkit.html) and [generic kernels](https://naif.jpl.nasa.gov/naif/data_generic.html) | Official JPL/NAIF local toolkit and data | Best authoritative route for advanced SPICE geometry; pin toolkit, kernel, and frame versions |
| [SpiceyPy](https://github.com/AndrewAnnex/SpiceyPy) | Maintained community Python wrapper for the NAIF Toolkit | Not an official JPL SDK; validate critical calculations against NAIF examples or another engine |
| [Astropy repository](https://github.com/astropy/astropy) and [solar-system documentation](https://docs.astropy.org/en/latest/coordinates/solarsystem.html) | Maintained community-governed scientific Python SDK | Official for the Astropy project, not an authoritative ephemeris publisher; its answer still depends on selected ephemerides and IERS inputs |
| [USNO Astronomical Applications data services](https://aa.usno.navy.mil/data/) | Official hosted pages and service outputs | No endorsed general-purpose application SDK was identified; treat page/service schemas as external interfaces and monitor changes |

JPL documents DE440 for 1550–2650 and DE441 for approximately −13,200 to
+17,191. DE440 is preferable for the modern era. Never silently substitute a
different kernel when a date falls outside the pinned kernel's coverage.

### Inputs that must be versioned

For every reproducible result store:

```text
calculation and event-definition version
library versions
ephemeris kernel filename and SHA-256
leap-second input and SHA-256
IERS/EOP input, retrieval time, and SHA-256
Delta T source or value
input time scale and normalized UTC timestamp
latitude_deg, longitude_deg, ellipsoid_height_m, datum
coordinate and apparent-position conventions
refraction model and meteorological inputs
terrain/obstruction-mask version
```

Maintain both `as_issued_geometry` and `best_reconstructed_geometry` where the
calculation depends on time inputs that were later finalized.

### Time scales

- UTC is the API and user civil-time boundary.
- TAI is continuous atomic time.
- TT is used for terrestrial dynamical calculations.
- TDB is an ephemeris time argument.
- UT1 represents Earth rotation.
- Delta T is `TT - UT1`.

For modern planning, Earth-orientation uncertainty is usually much smaller than
near-horizon refraction and terrain uncertainty. For old eclipse paths, Delta T
uncertainty can materially move the shadow geographically.

## Sun, sunrise, sunset, and twilight

### Calculate rather than archive

Historical sunrise and sunset do not require a historical API. Calculate them
for the exact site with the pinned ephemeris, then use USNO or Horizons for
regression checks.

Recommended standard definitions:

| Event | Definition |
| --- | --- |
| Sunrise/sunset | Solar centre altitude −0.8333°, approximating upper limb plus standard refraction |
| Civil twilight | Solar centre altitude −6° |
| Nautical twilight | Solar centre altitude −12° |
| Astronomical twilight | Solar centre altitude −18° |

Store the threshold, not just the event name. Standard almanac times assume a
nominal atmosphere and smooth horizon; they do not include mountains, trees,
buildings, or anomalous marine refraction.

For observation reconstruction return three distinct values where useful:

```text
standard_almanac_time
terrain_adjusted_geometric_time
refraction_uncertainty_interval
```

### Historical sunsets and sunrises as visual events

Geometry determines the solar ray and horizon crossing, but a colourful sunset
or sunrise is an atmospheric event. Reconstruct it with:

- 3-D cloud and fog fields along both the observer ray and solar illumination
  path;
- aerosols and smoke;
- cloud optical properties and cloud-top height;
- terrain horizon;
- satellite imagery and surface observations.

See [Cloud, fog, and astronomical line-of-sight forecasting](cloud-fog-line-of-sight.md).

## Moon geometry and named Moon events

### Deterministic quantities

Calculate locally:

- topocentric altitude and azimuth;
- rise, transit, and set;
- geocentric and topocentric phase geometry;
- illuminated fraction;
- angular diameter and observer distance;
- full, new, first-quarter, and last-quarter instants;
- geocentric perigee and apogee extrema.

Moonrise and Moonset must be calculated for each site because lunar parallax is
large. Near the horizon, refraction, semidiameter, observer elevation, and the
directional terrain mask dominate the practical error.

### Full and new Moon

Recommended phase-angle convention:

```text
0°   new Moon
90°  first quarter
180° full Moon
270° last quarter
```

Phase events are instants, not whole calendar days. Record whether phase and
illumination are geocentric or topocentric.

### Supermoon

`Supermoon` is not a uniquely standardized astronomical event. NASA describes
a common convention based on a full Moon being within 90% of its closest
approach. Astraeus must version the exact formula instead of storing only a
boolean.

Recommended fields:

```text
definition_id
full_moon_time_utc
distance_at_full_moon_km
nearest_perigee_time_utc
nearest_perigee_distance_km
time_separation_seconds
angular_diameter_arcsec
classification_result
```

NASA reference: [Supermoons](https://science.nasa.gov/moon/supermoons/).

### Blue Moon

`Blue Moon` is also a convention, not a physical change in the Moon:

- monthly: the second full Moon in a civil calendar month;
- seasonal: the third full Moon in an astronomical season containing four.

The monthly result depends on the selected calendar timezone. Store
`definition_id` and `calendar_timezone`. A physically blue-looking Moon is an
atmospheric scattering observation and must not be inferred from the calendar
label.

NASA reference: [Super Blue Moons FAQ](https://science.nasa.gov/solar-system/moon/super-blue-moons-your-questions-answered/).

### Blood or red Moon

A `blood Moon` normally refers to a total lunar eclipse. Eclipse geometry and
shadow immersion are deterministic. Observed redness or darkness depends on
Earth's atmospheric aerosol, cloud, and volcanic state around the refracted
sunlight path. Store the total-lunar-eclipse classification separately from
observed colour or a Danjon-scale report.

## Solar eclipses

### Authoritative catalogues

- [NASA solar eclipse portal](https://eclipse.gsfc.nasa.gov/solar.html)
- [Five Millennium Catalog of Solar Eclipses](https://eclipse.gsfc.nasa.gov/SEcat5/SEcatalog.html), −1999 through +3000
- [NASA catalogue key and definitions](https://eclipse.gsfc.nasa.gov/SEcat5/catkey.html)
- [USNO eclipse services](https://aa.usno.navy.mil/data/), local products for 1501–2100

Use catalogues to discover events and ingest authoritative Besselian elements
or path products. Recompute and validate local circumstances for the exact
candidate site.

### Local historical record

For each site calculate and store:

```text
C1 partial phase begins
C2 total or annular phase begins, where applicable
maximum eclipse
C3 total or annular phase ends, where applicable
C4 partial phase ends
Sun altitude and azimuth at every contact
magnitude and obscuration
totality/annularity duration
distance to path centre and edge
terrain/structure/vegetation horizon clearance
Delta T and EOP provenance
```

Then join cloud, fog, aerosol, smoke, and surface visibility over the complete
event window. For a low-altitude eclipse, evaluate the slanted 3-D atmospheric
ray rather than only cloud directly over the observer.

Highest-precision solar contact calculations also depend on the lunar limb
profile. A broad eclipse-path catalogue is not sufficient for property-level
contact accuracy.

## Lunar eclipses

Sources:

- [NASA lunar eclipse catalogue and figures](https://eclipse.gsfc.nasa.gov/LEcat5/figure.html)
- [Five Millennium Canon of Lunar Eclipses](https://eclipse.gsfc.nasa.gov/5MCLE/5MKLE-214173.pdf), −1999 through +3000
- USNO eclipse services
- Skyfield's lunar-eclipse search for local deterministic computation

Store P1/P4, U1/U4, U2/U3 when applicable, greatest eclipse, and Moon
altitude/azimuth at each phase. A global eclipse can only be locally visible
while the Moon clears the effective site horizon and the atmosphere is usable.

## Aurora and space-weather history

### Three records are required

```text
1. Upstream solar-wind and geomagnetic measurements
2. The model or forecaster output issued at the time
3. Optical or human evidence of what was visible
```

No one of these substitutes for the others. Final cleaned measurements are
excellent for scientific reconstruction but are not necessarily what an
operational forecast consumed.

### Source matrix

| Source | Role and approximate coverage | Historical semantics |
| --- | --- | --- |
| [SWPC real-time solar wind](https://www.swpc.noaa.gov/index.php/products/real-time-solar-wind) | Operational L1 stream; interactive history shown from Feb 1998 | Closest to operational input; rolling JSON is short-lived |
| [NCEI DSCOVR archive](https://www.ncei.noaa.gov/products/deep-space-climate-observatory-dscovr) | Raw, operational, and science products from 2016-era mission | Preserve product level and processing version |
| NASA SPDF/CDAWeb ACE | Calibrated ACE MAG/SWEPAM from 1998 | Science measurement, not exact screen vintage |
| [NASA OMNIWeb](https://omniweb.gsfc.nasa.gov/form/omni_min.html) | Merged, normalized, Earth-shifted solar wind | Retrospective composite; ideal for hindcasts, not issued forecasts |
| [GFZ Kp](https://datapub.gfz-potsdam.de/download/10.5880.Kp.0001/) | Kp since 1932 | Keep definitive, provisional, and nowcast semantics separate |
| [GFZ Hp30/Hp60](https://kp.gfz.de/en/hp30-hp60/data) | Higher-cadence geomagnetic indices | Verify current file coverage/version; CC BY 4.0 |
| [Kyoto WDC](https://wdcvmweb.kugi.kyoto-u.ac.jp/wdc/Sec3.html) | Dst, AE/AL/AO, SYM/ASY; product-dependent history from 1957 | Separate quicklook, provisional, and final |
| [SWPC OVATION latest JSON](https://services.swpc.noaa.gov/json/ovation_aurora_latest.json) | Current auroral forecast grid | Mutable current product, not a complete archive |
| [WSA-Enlil at SWPC](https://www.spaceweather.gov/products/wsa-enlil-solar-wind-prediction) | Operational CME/solar-wind model; NOAA output history is product- and retention-dependent | A saved run is a genuine forecast vintage; a CCMC rerun is a reconstruction unless its issue-time inputs are preserved |
| [NASA DONKI](https://api.nasa.gov/) | CME, flare, shock, and notification event catalogue | Event analysis, not complete forecast-screen history |
| [NRCan geomagnetic data](https://www.geomag.nrcan.gc.ca/data-donnee/sd-en.php) | Regional 1-second/1-minute magnetometer data, station-dependent | Valuable Atlantic context; commercial redistribution terms require review |
| [SuperMAG](https://supermag.jhuapl.edu/) | Normalized multi-network magnetometers and electrojet indices | Hosted research service rather than an unrestricted raw-data mirror; registration, acknowledgement, and rules-of-the-road apply |
| [THEMIS all-sky imagers](https://themis.igpp.ucla.edu/instrument_asi.shtml) and [download service](https://themis.igpp.ucla.edu/data_download.shtml) | Optical images, station-dependent from about 2005/2007 | Strong evidence only within a camera's usable footprint |
| [AuroraX metadata catalogue](https://docs.aurorax.space/about_the_data/metadata_in_aurorax/) / [AuroraMAX](https://auroramax.com/learning/auroramax-observatory) | Canadian discovery metadata and imagery | AuroraX is a catalogue/query layer rather than ownership of every underlying image; excellent northern evidence, weak direct Atlantic coverage |
| [Aurorasaurus public release](https://zenodo.org/records/16783265) | Citizen reports, 2014–2025 release | Direct but biased/noisy human evidence |

### The OVATION archive gap

The normal SWPC endpoint exposes the latest OVATION grid and recent animation
frames, not a documented immutable archive of all operational grids. Re-running
OVATION today with final OMNI data is a hindcast, not the historical NOAA
forecast.

Start an immutable archival job immediately. For each poll retain:

```text
retrieved_at_utc
observation_time_utc
forecast_valid_time_utc
raw grid bytes and checksum
hemispheric power
input spacecraft/source and fallback state, if exposed
product/model version
```

Poll frequently enough to preserve updates, for example every five minutes,
and deduplicate identical checksums. Also archive SWPC forecast discussions,
alerts, Kp forecasts, real-time solar-wind data, WSA-Enlil run identifiers, and
quality/source metadata.

### Aurora access and implementation status

| Resource | Access type and status | Correct use |
| --- | --- | --- |
| [SWPC JSON directory](https://services.swpc.noaa.gov/json/) | Official operational raw endpoints; mutable/rolling rather than an SDK | Ingest defensively, retain retrieval time and bytes, and do not assume that every product has permanent history |
| [NCEI DSCOVR archive](https://www.ncei.noaa.gov/products/deep-space-climate-observatory-dscovr) | Official mission archive with multiple processing levels | Use for measurements and hindcasts; it does not recreate the exact values shown by SWPC at every historical instant |
| [NASA OMNIWeb](https://omniweb.gsfc.nasa.gov/form/omni_min.html) | Official retrospective merged data service/raw download | Excellent normalized reconstruction driver, but not an issued forecast-vintage API |
| [GFZ Kp archive](https://datapub.gfz-potsdam.de/download/10.5880.Kp.0001/) and [Hp30/Hp60 data/API](https://kp.gfz.de/en/hp30-hp60/data) | Official index publisher downloads and documented web access | Preserve definitive/provisional/nowcast status; Hp data are CC BY 4.0, while each product's current terms still need checking |
| [Kyoto WDC service](https://wdcvmweb.kugi.kyoto-u.ac.jp/wdc/Sec3.html) | Official index-publisher download service | Archive version class because quicklook, provisional, and final series can differ |
| [NCEP WSA-Enlil product tree](https://www.nco.ncep.noaa.gov/pmb/products/wsa_enlil/) | Official raw operational output tree | Treat retention and filenames as operational interfaces, not a stable SDK contract |
| [CCMC Runs on Request](https://ccmc.gsfc.nasa.gov/tools/runs-on-request/) | Official NASA-hosted research execution service | Useful for experiments and reconstructions; not a NOAA operational forecast archive or low-latency production API |
| [THEMIS download service](https://themis.igpp.ucla.edu/data_download.shtml) and [CSA open-data mirror](https://donnees-data.asc-csa.gc.ca/en/dataset/d700c863-8622-4ec2-a4ee-a1c377880e2e) | Official project/agency research archives | Confirm station, cadence, processing level, licence, and camera state before using frames as labels |

No maintained official NOAA client SDK for OVATION or SWPC JSON was identified.
Use the official raw endpoints directly behind an Astraeus provider adapter.
The historical [OVATION Prime SourceForge release](https://sourceforge.net/projects/ovation-prime/)
is archival IDL research code, while
[OvationPyme](https://github.com/lkilcommons/OvationPyme) is a community Python
implementation; neither should be described as the code that produces NOAA's
current operational OVATION product.

### Aurora reconstruction hierarchy for Atlantic Canada

1. Exact locally archived operational forecast vintage.
2. Historical operational L1 input stream used by SWPC.
3. Regional NRCan or licensed SuperMAG magnetometers.
4. Final OMNI plus definitive Kp/Hp and Kyoto indices for retrospective context.
5. DMSP/SSUSI, THEMIS, or other optical/particle evidence.
6. Geolocated images and explicit camera-versus-naked-eye reports.
7. Reconstructed darkness, Moon, cloud, fog, and obstructions.

If no exact OVATION grid exists, generate a versioned hindcast and label it
`not_operational_vintage: true`.

### What establishes local visibility

Strong positive evidence includes a timestamped and geolocated all-sky image,
an explicit naked-eye/camera report, or multiple independent observations near
the site. Bz, Kp, AE, a magnetic bay, hemispheric power, or an OVATION grid are
activity evidence; none alone proves that aurora was optically visible in Nova
Scotia, New Brunswick, Prince Edward Island, or Newfoundland and Labrador.

A useful negative label requires proof that:

- an observer or camera was operating;
- the sky was dark;
- the relevant horizon was unobstructed;
- cloud and fog did not hide the emission;
- sensitivity and exposure were sufficient;
- no aurora was detected.

A cloudy frame is `unobservable`, not `no_aurora`.

## Meteor showers, meteors, and fireballs

Separate predictable shower geometry from observed activity.

Calculate locally:

- radiant altitude and azimuth;
- solar longitude and expected peak interval;
- Moon illumination, separation, and altitude;
- darkness and usable observing duration.

Retrieve observations for actual rates and event validation from sources such
as:

- [International Meteor Organization](https://www.imo.net/) shower calendars,
  visual observations, and activity profiles;
- [Global Meteor Network](https://globalmeteornetwork.org/) orbit and detection
  products;
- [NASA CNEOS fireball data](https://cneos.jpl.nasa.gov/fireballs/) for bright
  atmospheric events;
- [American Meteor Society](https://www.amsmeteors.org/) reports and fireball
  event aggregation.

Nominal peak time and zenithal hourly rate are not guarantees for a particular
site. Preserve source revisions and distinguish predicted activity, instrument
detections, and crowd reports.

## Comets and small bodies

### Geometry and orbit sources

- [JPL Small-Body Database API](https://ssd-api.jpl.nasa.gov/doc/sbdb.html)
- [JPL Horizons](https://ssd.jpl.nasa.gov/horizons/) for time-dependent
  topocentric ephemerides
- [Minor Planet Center](https://minorplanetcenter.net/) for official
  observations and orbital elements
- [NAIF SPICE](https://naif.jpl.nasa.gov/naif/data_generic.html) where kernels
  exist

Pin an orbit solution identifier or element epoch. A modern best-fit orbit can
differ from the orbit and uncertainty known before a historical close approach.

### Brightness is not deterministic geometry

Retrieve light curves and visual estimates from the
[AAVSO International Database](https://www.aavso.org/aavso-international-database)
and appropriate comet-observation archives. Comet activity, outbursts, coma,
tail structure, and magnitude can depart strongly from a simple ephemeris
prediction. Store observed magnitude, aperture/band, observer/instrument, and
quality metadata separately from calculated position.

## Occultations, conjunctions, and transits

Planetary conjunctions and many transits can be discovered by searching local
ephemeris extrema, then calculating topocentric separation and altitude for
each site. Define whether `conjunction` means equal right ascension, equal
ecliptic longitude, or minimum apparent separation.

High-precision stellar occultations require:

- a versioned body orbit;
- a Gaia-era star position with proper motion;
- Earth orientation and observer coordinates;
- body shape and, where relevant, atmosphere/rings;
- observed chord reports for ground truth.

IOTA and regional occultation networks are useful prediction and observation
sources, but terms, machine access, and archive completeness should be checked
before integration. A calculated shadow path should not be treated as an
observed positive.

## Novae, supernovae, and other transients

These events must be retrieved because their occurrence and brightness are not
deterministically schedulable.

Candidate sources:

| Source | Best use |
| --- | --- |
| [Transient Name Server](https://www.wis-tns.org/) | Official transient discovery/classification registry |
| [AAVSO](https://www.aavso.org/data-access) | Historical variable-star and transient light curves |
| [NASA HEASARC](https://heasarc.gsfc.nasa.gov/) | High-energy mission catalogues and observations |
| [SIMBAD](https://simbad.cds.unistra.fr/simbad/) | Object identity and bibliography, not primary light-curve truth |
| [VizieR](https://vizier.cds.unistra.fr/) | Published astronomical catalogues |
| Survey alert/archive services such as ZTF or ASAS-SN | Discovery photometry and light curves, subject to current access terms |

Preserve discovery time separately from first-detection time and later
classification time. When recreating what a user could have known, query the
alert/publication state at issuance time rather than using only the final object
classification.

## Free versus paid astronomy services

### Free and authoritative foundation

The local JPL/Skyfield/IERS calculation stack plus NASA, USNO, SWPC, SPDF,
GFZ, Kyoto, MPC, IMO, and public observation archives covers the scientific
foundation. Costs are primarily engineering, storage, bandwidth, and operating
reliable archival jobs.

### What paid APIs can add

Commercial astronomy APIs can add:

- convenient normalized JSON;
- managed uptime and support;
- address/timezone handling;
- precomputed calendars and illustrations;
- fewer source-specific integrations.

Examples to evaluate include AstronomyAPI and timeanddate's astronomy APIs.
Before procurement verify:

```text
underlying ephemeris and algorithm
geocentric versus topocentric semantics
coordinate order and elevation support
refraction and horizon definitions
time-scale and timezone handling
historical and future date limits
rate and bulk-export limits
caching and derived-data rights
service versioning and correction policy
commercial-display and redistribution rights
```

Paid convenience does not make deterministic geometry more accurate than a
properly pinned JPL-based local calculation. It also does not solve historical
forecast-vintage or optical-ground-truth gaps.

## Normalized data model

### Calculated event

```json
{
  "event_id": "...",
  "event_type": "total_lunar_eclipse",
  "semantics": "deterministic_calculation",
  "calculation_version": "astronomy-v1",
  "start_time_utc": "...",
  "peak_time_utc": "...",
  "end_time_utc": "...",
  "observer": {
    "latitude_deg": 44.6488,
    "longitude_deg": -63.5752,
    "ellipsoid_height_m": 60,
    "datum": "WGS84"
  },
  "view": {
    "azimuth_deg": 118.2,
    "altitude_geometric_deg": 16.4,
    "altitude_apparent_deg": 16.5
  },
  "inputs": {
    "ephemeris": "DE442",
    "ephemeris_file": "de442.bsp",
    "ephemeris_sha256": "...",
    "eop_sha256": "...",
    "definition_id": "..."
  }
}
```

### Observed or forecast datum

```json
{
  "source": "nasa_omni",
  "product": "high_resolution_1min",
  "semantics": "retrospective_measurement_composite",
  "native_time_utc": "...",
  "issue_time_utc": null,
  "valid_time_utc": "...",
  "parameter": "Bz_GSM",
  "value": -12.4,
  "unit": "nT",
  "quality": {
    "percent_interpolated": 0,
    "time_shift_sigma_seconds": 180
  },
  "retrieved_at_utc": "...",
  "raw_sha256": "..."
}
```

Required semantic values should include at least:

```text
deterministic_calculation
issued_forecast_vintage
retrospective_hindcast
near_real_time_measurement
final_measurement
optical_observation
human_report
catalogue_record
```

## Joining celestial events to historical weather

For each event/site pair:

1. Normalize the event interval to UTC.
2. Calculate topocentric direction and elevation throughout the interval, not
   only at peak time.
3. Intersect the changing ray with the directional terrain, building, and
   vegetation horizon.
4. Ray-march through historical/reconstructed 3-D cloud, fog, and aerosol.
5. Join the forecast vintage that was available at recommendation issue time.
6. Join later observations and satellite retrievals as outcome evidence.
7. Classify outcome confidence and observability separately.

Recommended outcome labels:

```text
confirmed_naked_eye
confirmed_camera_only
confirmed_instrumental_optical
likely_visible
physically_active_local_visibility_unknown
clear_attempted_negative
unobservable_weather
unobservable_obstruction
no_evidence
```

Never use `no report` as a negative observation.

## Atlantic Canada validation set

Use a geographically varied test set including:

- Halifax and Yarmouth, Nova Scotia;
- Cape Breton coastal and highland sites;
- Moncton and northern New Brunswick;
- Charlottetown and exposed Prince Edward Island coast;
- St. John's, Gander, and western Newfoundland;
- Labrador locations where data coverage permits.

Include:

- ocean horizons and elevated terrain horizons;
- DST transitions in `America/Halifax` and Newfoundland's half-hour timezone;
- polar-day/night edge cases where relevant to Labrador;
- Moon events near midnight local time;
- eclipses or aurora at low elevation;
- dates around leap seconds and model/source transitions.

## Fact-check and regression suite

### Deterministic geometry

- Compare Sun/Moon altitude and azimuth against Horizons at multiple sites and
  dates.
- Compare rise/set and twilight against USNO under identical definitions.
- Verify phase instants against USNO or an authoritative almanac.
- Validate local lunar-eclipse geometry against NASA/USNO.
- Validate solar-eclipse local circumstances against USNO and published path
  data before exposing an eclipse planner.
- Assert longitude is always east-positive internally and API coordinate order
  is explicitly documented.

### Historical semantics

- Assert a final OMNI record cannot be tagged as an operational input vintage.
- Assert every forecast has both `issue_time_utc` and `valid_time_utc`.
- Assert every hindcast visibly carries `not_operational_vintage: true`.
- Assert mutable endpoints retain retrieval timestamp and raw checksum.
- Assert provisional and definitive geomagnetic indices are not overwritten.

### Visibility labels

- Reject cloudy/offline camera periods as negative aurora labels.
- Keep naked-eye and camera-only reports separate.
- Require event-direction horizon clearance, not a scalar site openness score.
- Preserve unknowns instead of inventing clear-sky or access assumptions.

## Implementation and archival order

1. Pin Skyfield, DE442 (`de442.bsp`), leap-second, and EOP inputs.
2. Implement and validate Sun/Moon position, twilight, rise/set, phase, and
   illumination for Atlantic Canada.
3. Define the normalized event and provenance schemas.
4. Begin immutable OVATION, SWPC solar-wind, forecast-discussion, alert, and Kp
   forecast archival immediately.
5. Create solar/lunar eclipse catalogue ingestion and local lunar-eclipse
   calculations; defer a bespoke high-precision solar shadow solver until it
   has dedicated tests.
6. Add geomagnetic, optical-camera, and citizen-report retrieval adapters.
7. Add meteor, comet, and transient adapters only when their event modules enter
   product scope.
8. Join events to the environmental archive and site-obstruction pipeline.
9. Build labelled historical case studies, preserving `unknown` and
   `unobservable` outcomes.

## Known limitations

- Standard refraction is not the atmosphere that existed historically.
- Terrain data do not capture every historical tree, temporary structure, or
  building change.
- A modern ephemeris reconstruction is not always the geometry published to a
  user at the historical issue time.
- Exact historical OVATION grids are generally unavailable unless someone
  archived them.
- Optical aurora coverage in Atlantic Canada is sparse.
- Citizen reports are strongly affected by population, notifications, weather,
  equipment, and reporting behaviour.
- Comet and transient brightness cannot be reconstructed from orbit alone.
- `Supermoon`, `blue Moon`, and similar labels require explicit conventions.
- Geometry establishes opportunity, not successful human observation.
