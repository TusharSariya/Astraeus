# Repositories, documentation, APIs, and SDK index

Last reviewed: 2026-08-10

## Purpose

This is the navigation index for implementing Astraeus integrations. Detailed
scientific suitability, limitations, licences, and source-selection decisions
remain in the domain research documents.

The word `SDK` is used narrowly. A GRIB directory, S3 bucket, OGC service,
OpenAPI description, command-line program, or example notebook is not an SDK.

## Source labels

| Label | Meaning |
| --- | --- |
| Official documentation | Published by the data producer, model owner, or software project |
| Official API/feed | Producer-operated machine interface or file service |
| Official SDK/client | Maintained by the producer or owning software organization |
| Official repository | Canonical source repository for the software or model |
| Community client | Third-party convenience library; maintenance and endpoint coverage require verification |
| Generated client | Code generated from a versioned OpenAPI or similar schema |
| Raw protocol/file access | HTTP, S3, AMQP, OGC, GRIB, NetCDF, GeoTIFF, XML, or another format—not an SDK |

For every dependency, pin a version or commit, record its licence, and archive
the upstream schema/product version used by the adapter.

## Domain navigation

| Domain | Detailed tooling and source links |
| --- | --- |
| Operational weather, cloud, fog, and local simulation | [Cloud, fog, and astronomical line-of-sight forecasting](cloud-fog-line-of-sight.md#integration-and-implementation-tooling) |
| Paid weather, aerosol, smoke, and air-quality providers | [Paid environmental APIs](paid-environmental-apis.md#provider-documentation-and-sdk-map) |
| Historical forecast and observation retrieval | [Historical environmental-data retrieval](historical-data-retrieval.md#retrieval-tools-and-repositories) |
| Astronomy, eclipses, aurora, and event archives | [Historical celestial events](historical-celestial-events.md) |
| Terrain, buildings, vegetation, access, and routing | [Observation-site obstructions and public access](site-obstructions-and-access.md) |
| Source selection for the MVP | [Data-source recommendations](data-sources.md) |
| Weather and space-weather models | [State-of-the-art models](sota-models.md) |
| Existing consumer applications and vendor interfaces | [Product landscape](product-landscape.md) |
| Reddit and practitioner evidence | [Community findings](community-findings.md) |
| Application libraries and runtime choices | [Implementation plan](implementation-plan.md#core-implementation-library-references) |

## Core application libraries

| Project | Documentation | Repository |
| --- | --- | --- |
| Python | [Documentation](https://docs.python.org/3/) | [python/cpython](https://github.com/python/cpython) |
| FastAPI | [Documentation](https://fastapi.tiangolo.com/) | [fastapi/fastapi](https://github.com/fastapi/fastapi) |
| Pydantic | [Documentation](https://docs.pydantic.dev/) | [pydantic/pydantic](https://github.com/pydantic/pydantic) |
| NumPy | [Documentation](https://numpy.org/doc/) | [numpy/numpy](https://github.com/numpy/numpy) |
| SciPy | [Documentation](https://docs.scipy.org/doc/scipy/) | [scipy/scipy](https://github.com/scipy/scipy) |
| pandas | [Documentation](https://pandas.pydata.org/docs/) | [pandas-dev/pandas](https://github.com/pandas-dev/pandas) |
| pytest | [Documentation](https://docs.pytest.org/) | [pytest-dev/pytest](https://github.com/pytest-dev/pytest) |

## Weather and scientific-file tooling

| Project | Documentation | Repository | Status |
| --- | --- | --- | --- |
| xarray | [Documentation](https://docs.xarray.dev/) | [pydata/xarray](https://github.com/pydata/xarray) | Community scientific library |
| ecCodes | [Documentation](https://confluence.ecmwf.int/display/ECC) | [ecmwf/eccodes](https://github.com/ecmwf/eccodes) | Official ECMWF decoder/toolkit |
| cfgrib | [Documentation](https://github.com/ecmwf/cfgrib) | [ecmwf/cfgrib](https://github.com/ecmwf/cfgrib) | Official ECMWF xarray GRIB engine |
| netCDF4-python | [Documentation](https://unidata.github.io/netcdf4-python/) | [Unidata/netcdf4-python](https://github.com/Unidata/netcdf4-python) | Official Unidata Python interface |
| h5py | [Documentation](https://docs.h5py.org/) | [h5py/h5py](https://github.com/h5py/h5py) | Python HDF5 interface (NSRDB / S3) |
| Zarr | [Documentation](https://zarr.readthedocs.io/) | [zarr-developers/zarr-python](https://github.com/zarr-developers/zarr-python) | Chunked array storage |
| Dask | [Documentation](https://docs.dask.org/) | [dask/dask](https://github.com/dask/dask) | Parallel/lazy array execution |
| kerchunk | [Documentation](https://fsspec.github.io/kerchunk/) | [fsspec/kerchunk](https://github.com/fsspec/kerchunk) | Community reference-file virtualization |

## Geospatial tooling

| Project | Documentation | Repository | Role |
| --- | --- | --- | --- |
| GDAL | [Documentation](https://gdal.org/) | [OSGeo/gdal](https://github.com/OSGeo/gdal) | Raster/vector formats and transforms |
| PROJ | [Documentation](https://proj.org/) | [OSGeo/PROJ](https://github.com/OSGeo/PROJ) | Coordinate transformations |
| Rasterio | [Documentation](https://rasterio.readthedocs.io/) | [rasterio/rasterio](https://github.com/rasterio/rasterio) | Python raster access |
| pyproj | [Documentation](https://pyproj4.github.io/pyproj/) | [pyproj4/pyproj](https://github.com/pyproj4/pyproj) | Python PROJ interface |
| Shapely | [Documentation](https://shapely.readthedocs.io/) | [shapely/shapely](https://github.com/shapely/shapely) | Planar geometry |
| GeoPandas | [Documentation](https://geopandas.org/) | [geopandas/geopandas](https://github.com/geopandas/geopandas) | Tabular vector analysis |
| PDAL | [Documentation](https://pdal.io/) | [PDAL/PDAL](https://github.com/PDAL/PDAL) | Point-cloud/LiDAR processing |

## Astronomy tooling

| Project | Documentation | Repository or API | Status |
| --- | --- | --- | --- |
| Skyfield | [Documentation](https://rhodesmill.org/skyfield/) | [skyfielders/python-skyfield](https://github.com/skyfielders/python-skyfield) | Primary local astronomy engine |
| Astropy | [Documentation](https://docs.astropy.org/) | [astropy/astropy](https://github.com/astropy/astropy) | Official Astropy Project library |
| JPL Horizons | [API documentation](https://ssd-api.jpl.nasa.gov/doc/horizons.html) | [Hosted API](https://ssd.jpl.nasa.gov/horizons/) | Official API, not an SDK |
| NAIF SPICE | [Toolkit documentation](https://naif.jpl.nasa.gov/naif/toolkit.html) | [Generic kernels](https://naif.jpl.nasa.gov/naif/data_generic.html) | Official NASA toolkit and kernel archive |
| SpiceyPy | [Documentation](https://spiceypy.readthedocs.io/) | [AndrewAnnex/SpiceyPy](https://github.com/AndrewAnnex/SpiceyPy) | Community Python wrapper around CSPICE |
| USNO services | [API documentation](https://aa.usno.navy.mil/data/api.html) | [Hosted services](https://aa.usno.navy.mil/data/) | Official API, no general language SDK |
| Space Weather Canada (STJ) | [API & data docs](https://www.spaceweather.gc.ca) | [Hosted services](https://spaceweather.gc.ca/api/) | Official NRCan CANMOS geomagnetic feed for St. John's |

## Coastal and meteorological feeds

| Project | Documentation | Repository or API | Status |
| --- | --- | --- | --- |
| SmartAtlantic | [Portal](https://www.smartatlantic.ca) | [ERDDAP server](https://www.smartatlantic.ca/erddap/index.html) | Official MUN Marine Institute ERDDAP REST API |
| ECCC CIOPS-East | [Documentation](https://eccc-msc.github.io/open-data/msc-data/nwp_ciops/readme_ciops-east_en/) | [GeoMet / Datamart](https://dd.weather.gc.ca/model_ciops/east/2km/) | Official 2 km coupled hydrodynamic ocean model (SST, currents) |
| NL 511 | [Developer Portal](https://511nl.ca) | [511 NL API](https://511nl.ca/api/v2/get/) | Official NL Dept of Transportation RWIS & Camera API |
| Atlantic DataStream | [Documentation](https://atlanticdatastream.ca) | [Hosted Portal](https://atlanticdatastream.ca) | Open water quality and provincial climate data portal |
| CWOP / APRS-WX | [Protocol Docs](http://www.findu.com/citizenweather.html) | [APRS-IS Servers](http://www.aprs-is.net/) | High-density crowdsourced PWS network across Avalon |
| PurpleAir | [API Documentation](https://api.purpleair.com/) | [Hosted REST API](https://api.purpleair.com/) | Real-time optical laser particle aerosol counts |

## Routing and map tooling

| Project | Documentation | Repository | Status |
| --- | --- | --- | --- |
| OpenStreetMap | [Developer resources](https://wiki.openstreetmap.org/wiki/Develop) | [Core software organization](https://github.com/openstreetmap) | Open data/ecosystem, not a single SDK |
| Overpass API | [Documentation](https://wiki.openstreetmap.org/wiki/Overpass_API) | [drolbr/Overpass-API](https://github.com/drolbr/Overpass-API) | Query service and server implementation |
| OSMnx | [Documentation](https://osmnx.readthedocs.io/) | [gboeing/osmnx](https://github.com/gboeing/osmnx) | Community Python network/data client |
| OSRM | [API documentation](https://project-osrm.org/docs/v5.24.0/api/) | [Project-OSRM/osrm-backend](https://github.com/Project-OSRM/osrm-backend) | Open-source routing engine |
| Valhalla | [Documentation](https://valhalla.github.io/valhalla/) | [valhalla/valhalla](https://github.com/valhalla/valhalla) | Open-source routing engine |
| routingpy | [Documentation](https://routingpy.readthedocs.io/) | [giscience/routingpy](https://github.com/giscience/routingpy) | Community multi-provider client |

## Persistence

| Project | Documentation | Repository |
| --- | --- | --- |
| SQLite | [Documentation](https://www.sqlite.org/docs.html) | [Official source browser](https://sqlite.org/src/) |
| DuckDB | [Documentation](https://duckdb.org/docs/) | [duckdb/duckdb](https://github.com/duckdb/duckdb) |
| PostgreSQL | [Documentation](https://www.postgresql.org/docs/) | [postgres/postgres mirror](https://github.com/postgres/postgres) |
| PostGIS | [Documentation](https://postgis.net/documentation/) | [postgis/postgis](https://github.com/postgis/postgis) |

## Adoption checklist

Before adding any provider or package:

1. Confirm the linked project is canonical and currently maintained.
2. Record licence, attribution, caching, display, and redistribution terms.
3. Pin package version or repository commit and upstream schema/product version.
4. Confirm the client exposes the required model run, member, level, quality,
   and provenance dimensions rather than only a convenient point summary.
5. Archive the raw response or source subset before normalization.
6. Add a fixture and contract test using a known timestamp and coordinate.
7. Define explicit missing, stale, throttled, and schema-change failure modes.
8. Prefer direct documented protocols over abandoned thin wrappers.

Community clients are candidates for evaluation, not automatic dependencies.
Their presence does not change the scientific quality or licensing of the
underlying data.
