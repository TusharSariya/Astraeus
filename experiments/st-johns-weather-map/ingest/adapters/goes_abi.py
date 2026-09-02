"""GOES-19 ABI L2 cloud-mask adapter (ABI-L2-ACMF + ABI-L2-ACHAF).

Ingests the NOAA Enterprise Cloud Mask Full Disk product from the public
``noaa-goes19`` bucket over anonymous HTTPS, together with the scan-paired
Cloud Top Height granule used for parallax correction. Full Disk is
mandatory here: St. John's sits ~0.23 degrees east of the live CONUS sector
boundary, so the 5-minute CONUS product never covers it.

The whole ~25 MB ACMF granule is downloaded per scan. HDF5 byte-range
subsetting would need an ROS3-enabled h5py that this codebase does not
carry, and 25 MB every 10 minutes is trivially polite next to the GRIB
pulls this worker already makes.

Every geometric quantity — sub-satellite longitude, perspective height,
ellipsoid axes, sweep axis, scan angles — is read from the granule's own
``goes_imager_projection`` metadata. Nothing about the geometry is
hard-coded, and a granule missing those attributes is refused rather than
assumed.

Parallax: a cloud imaged off-nadir is georeferenced where its top's line of
sight meets the ellipsoid, displaced AWAY from the sub-satellite point by
roughly cloud-top height times tan(viewing zenith) — about 1.6x the cloud
height at St. John's ~58.6 degree viewing zenith. The correction therefore
shifts cloudy pixels TOWARD the sub-satellite point by that distance along
the great-circle azimuth. Cloudy pixels with no valid cloud-top height keep
their apparent position and carry an explicit ``parallax_uncorrected`` flag.
GOES-19 cloud-top height is NOAA "Provisional" maturity; that is disclosed
in the artifact attrs and surfaced by the API layer.

The ACHAF height itself is also RETAINED, as ``cloud_top_height`` in metres,
NaN where no valid retrieval reached the cell. It was previously read, used
to displace pixels, and dropped. Keeping it adds no new trust - the parallax
correction already moves the picture by this number - but it gives the
display-time motion derivation an observed per-cell height to assign a
steering level from, which is the dominant error term in multi-layer
atmospheric-motion-vector work (Liu et al., GRL 2025). It is
display-derivation input only, exactly like the 850/700/500 hPa steering
winds: it is in no served-field map and reaches no data path.
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ElementTree
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

import numpy
import xarray

from ingest.contract import (
    ATLANTIC_CONTEXT_BOUNDS,
    MEDIA_ZARR,
    AdapterUnavailable,
    Artifact,
    FetchWindow,
    RunCandidate,
    RunResult,
)
from ingest.grib import write_zarr
from ingest.http import PoliteClient
from ingest.manifest import declared_classes
from ingest.registry import register

UTC = timezone.utc
_log = logging.getLogger(__name__)

GOES_S3_BASE = "https://noaa-goes19.s3.amazonaws.com"
ACMF_PREFIX = "ABI-L2-ACMF"
ACHAF_PREFIX = "ABI-L2-ACHAF"

# Observed granule sizes: ACMF ~25 MB, ACHAF ~1.5 MB. Ceilings leave
# headroom without ever permitting a runaway download.
MAX_ACMF_BYTES = 80 * 1024 * 1024
MAX_ACHAF_BYTES = 20 * 1024 * 1024

# Mean-sphere radius for converting a metric parallax displacement to
# degrees. The displacement is 0-25 km; the sub-percent error of a spherical
# Earth is far below the ~5 km native footprint at this viewing angle.
EARTH_RADIUS_M = 6_371_008.8

# Crop padding so a parallax shift cannot move a pixel out of the window:
# 0.4 degrees (~30-44 km) covers a 15 km cloud top at this viewing zenith.
PARALLAX_PAD_DEG = 0.4

# The regrid target cell is the measured native footprint stretched by this
# factor, so the target is never finer than what the instrument resolved.
TARGET_CELL_FACTOR = 1.05

INVALID_CLASS = 255
CLASS_MEANINGS = "0=clear 1=probably_clear 2=probably_cloudy 3=cloudy 255=invalid_or_unobserved"
CLOUDY_CLASSES = (2, 3)

REGRID_DISCLOSURE = (
    "Values are regridded nearest-neighbour from the ABI geostationary fixed "
    "grid onto a regular latitude/longitude grid no finer than the local "
    "native pixel footprint; nothing is interpolated or smoothed."
)
PARALLAX_DISCLOSURE = (
    "Cloudy and probably-cloudy pixels with a valid cloud-top height are "
    "shifted toward the sub-satellite point by height x tan(viewing zenith) "
    "to correct parallax; cloudy pixels without a valid height keep their "
    "apparent position and carry parallax_uncorrected=1. The GOES-19 "
    "cloud-top height product is NOAA Provisional maturity."
)
ACCURACY_DISCLOSURE = (
    "NOAA's published Enterprise Cloud Mask validation reports roughly 90% "
    "balanced detection accuracy by day and 88% at night, weaker for very "
    "thin cirrus. These are the provider's figures, not locally measured."
)
HEIGHT_DISCLOSURE = (
    "cloud_top_height is the ACHAF retrieval carried through the same "
    "nearest-neighbour regrid and the same parallax shift as the mask it "
    "belongs to, in metres. It is NaN wherever ACHAF was absent, unaligned "
    "or invalid; an absent height is published absent and is never gap-"
    "filled, smoothed or interpolated across a hole. Display-derivation "
    "input only - it is not a reading and reaches no data path."
)

_KEY = re.compile(r"OR_ABI-L2-(ACMF|ACHAF)-M\d+_G19_s(\d{14})_e(\d{14})_c\d{14}\.nc$")
_REQUIRED_PROJ_ATTRS = (
    "longitude_of_projection_origin",
    "perspective_point_height",
    "semi_major_axis",
    "semi_minor_axis",
    "sweep_angle_axis",
)


def parse_scan_stamp(stamp: str) -> datetime:
    """Decode the sYYYYDDDHHMMSSt scan-start stamp from a granule key."""
    if len(stamp) != 14 or not stamp.isdigit():
        raise ValueError(f"not a GOES scan stamp: {stamp!r}")
    return datetime(int(stamp[0:4]), 1, 1, tzinfo=UTC) + timedelta(
        days=int(stamp[4:7]) - 1,
        hours=int(stamp[7:9]),
        minutes=int(stamp[9:11]),
        seconds=int(stamp[11:13]),
        milliseconds=int(stamp[13]) * 100,
    )


def parse_bucket_keys(xml_text: str) -> list[str]:
    """Object keys from an S3 ListObjectsV2 XML document."""
    root = ElementTree.fromstring(xml_text)
    keys: list[str] = []
    for contents in root.iter():
        if contents.tag.endswith("}Contents") or contents.tag == "Contents":
            for child in contents:
                if (child.tag.endswith("}Key") or child.tag == "Key") and child.text:
                    keys.append(child.text)
    return keys


def _hour_prefix(product: str, moment: datetime) -> str:
    return f"{product}/{moment.year}/{moment.timetuple().tm_yday:03d}/{moment.hour:02d}/"


def _index_window(coords_m: numpy.ndarray, lo: float, hi: float, axis_name: str) -> slice:
    inside = numpy.nonzero((coords_m >= lo) & (coords_m <= hi))[0]
    if inside.size == 0:
        raise ValueError(f"context bounds select no {axis_name} pixels; wrong domain, not a thin crop")
    return slice(int(inside.min()), int(inside.max()) + 1)


def viewing_geometry(
    lat_deg: numpy.ndarray, lon_deg: numpy.ndarray, sub_lon_deg: float, sat_radius_m: float
) -> tuple[numpy.ndarray, numpy.ndarray]:
    """Per-pixel viewing zenith (radians) and great-circle bearing toward the
    sub-satellite point (radians from north), on a mean sphere."""
    lat = numpy.radians(lat_deg)
    dlon = numpy.radians(lon_deg - sub_lon_deg)
    cos_c = numpy.cos(lat) * numpy.cos(dlon)
    sin_c = numpy.sqrt(numpy.clip(1.0 - cos_c**2, 0.0, 1.0))
    slant = numpy.sqrt(
        sat_radius_m**2 + EARTH_RADIUS_M**2 - 2.0 * sat_radius_m * EARTH_RADIUS_M * cos_c
    )
    sin_vza = numpy.clip(sat_radius_m * sin_c / slant, 0.0, 1.0)
    vza = numpy.arcsin(sin_vza)
    # Great-circle initial bearing from (lat, lon) toward (0, sub_lon).
    bearing = numpy.arctan2(numpy.sin(-dlon), -numpy.sin(lat) * numpy.cos(dlon))
    return vza, bearing


def process_granules(
    acmf_path: Path,
    achaf_path: Path | None,
    *,
    bounds: Mapping[str, float] = ATLANTIC_CONTEXT_BOUNDS,
) -> tuple[xarray.Dataset, dict[str, Any]]:
    """Crop, parallax-correct and regrid one ACMF (+ACHAF) scan.

    Returns the regridded dataset (one valid_time) plus the stats the caller
    needs to compute completeness and QC honestly.
    """
    from pyproj import CRS, Transformer  # noqa: PLC0415  (heavy import kept local)

    with xarray.open_dataset(acmf_path, engine="netcdf4") as ds:
        if "goes_imager_projection" not in ds.variables:
            raise ValueError("granule carries no goes_imager_projection; geometry will not be assumed")
        proj_attrs = dict(ds["goes_imager_projection"].attrs)
        missing = [name for name in _REQUIRED_PROJ_ATTRS if name not in proj_attrs]
        if missing:
            raise ValueError(f"granule projection attrs missing {missing}; geometry will not be assumed")
        for var in ("ACM", "Cloud_Probabilities", "DQF"):
            if var not in ds.variables:
                raise ValueError(f"granule does not carry {var}")
        scan_start_text = ds.attrs.get("time_coverage_start")
        scan_end_text = ds.attrs.get("time_coverage_end")
        if not scan_start_text:
            raise ValueError("granule missing time_coverage_start; the key timestamp is not scan time")
        scan_start = datetime.fromisoformat(str(scan_start_text).replace("Z", "+00:00"))
        height_m = float(proj_attrs["perspective_point_height"])
        sub_lon = float(proj_attrs["longitude_of_projection_origin"])
        semi_major = float(proj_attrs["semi_major_axis"])
        crs = CRS.from_dict(
            {
                "proj": "geos",
                "h": height_m,
                "lon_0": sub_lon,
                "sweep": str(proj_attrs["sweep_angle_axis"]),
                "a": semi_major,
                "b": float(proj_attrs["semi_minor_axis"]),
                "units": "m",
            }
        )
        to_geodetic = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
        to_fixed = Transformer.from_crs("EPSG:4326", crs, always_xy=True)

        south = float(bounds["south"]) - PARALLAX_PAD_DEG
        north = float(bounds["north"]) + PARALLAX_PAD_DEG
        west = float(bounds["west"]) - PARALLAX_PAD_DEG
        east = float(bounds["east"]) + PARALLAX_PAD_DEG
        edge_lon = numpy.concatenate(
            [
                numpy.linspace(west, east, 65),
                numpy.linspace(west, east, 65),
                numpy.full(65, west),
                numpy.full(65, east),
            ]
        )
        edge_lat = numpy.concatenate(
            [
                numpy.full(65, south),
                numpy.full(65, north),
                numpy.linspace(south, north, 65),
                numpy.linspace(south, north, 65),
            ]
        )
        edge_x, edge_y = to_fixed.transform(edge_lon, edge_lat)
        edge_x = numpy.asarray(edge_x)
        edge_y = numpy.asarray(edge_y)
        finite = numpy.isfinite(edge_x) & numpy.isfinite(edge_y)
        if not finite.any():
            raise ValueError("context bounds fall entirely outside this granule's disk")

        x_m = numpy.asarray(ds["x"].values, dtype="float64") * height_m
        y_m = numpy.asarray(ds["y"].values, dtype="float64") * height_m
        x_slice = _index_window(x_m, edge_x[finite].min(), edge_x[finite].max(), "x")
        y_slice = _index_window(y_m, edge_y[finite].min(), edge_y[finite].max(), "y")
        sub = ds.isel(x=x_slice, y=y_slice)
        sub_x = x_m[x_slice]
        sub_y = y_m[y_slice]

        acm = numpy.asarray(sub["ACM"].values, dtype="float64")
        prob = numpy.asarray(sub["Cloud_Probabilities"].values, dtype="float64")
        dqf = numpy.asarray(sub["DQF"].values, dtype="float64")

    grid_x, grid_y = numpy.meshgrid(sub_x, sub_y)
    lon2d, lat2d = to_geodetic.transform(grid_x, grid_y)
    lon2d = numpy.asarray(lon2d, dtype="float64")
    lat2d = numpy.asarray(lat2d, dtype="float64")
    on_disk = numpy.isfinite(lon2d) & numpy.isfinite(lat2d) & (numpy.abs(lat2d) <= 90.0)

    cloud_height = numpy.full(lat2d.shape, numpy.nan, dtype="float64")
    achaf_used = False
    if achaf_path is not None:
        with xarray.open_dataset(achaf_path, engine="netcdf4") as hds:
            if "HT" in hds.variables and "goes_imager_projection" in hds.variables:
                h_height = float(
                    hds["goes_imager_projection"].attrs.get("perspective_point_height", height_m)
                )
                ht = hds["HT"].assign_coords(
                    x=numpy.asarray(hds["x"].values, dtype="float64") * h_height,
                    y=numpy.asarray(hds["y"].values, dtype="float64") * h_height,
                )
                ht_x = numpy.asarray(ht["x"].values)
                ht_y = numpy.asarray(ht["y"].values)
                tol_x = 0.75 * float(numpy.median(numpy.abs(numpy.diff(ht_x)))) if ht_x.size > 1 else None
                tol_y = 0.75 * float(numpy.median(numpy.abs(numpy.diff(ht_y)))) if ht_y.size > 1 else None
                aligned = ht.reindex(
                    y=sub_y, x=sub_x, method="nearest",
                    tolerance=max(t for t in (tol_x, tol_y) if t is not None) if (tol_x or tol_y) else None,
                )
                cloud_height = numpy.asarray(aligned.values, dtype="float64")
                achaf_used = True

    sat_radius = height_m + semi_major
    vza, bearing = viewing_geometry(lat2d, lon2d, sub_lon, sat_radius)
    tan_vza = numpy.tan(numpy.clip(vza, 0.0, numpy.radians(85.0)))

    cloudy = numpy.isin(acm, CLOUDY_CLASSES) & on_disk
    has_height = numpy.isfinite(cloud_height) & (cloud_height > 0.0)
    corrected = cloudy & has_height
    uncorrected = cloudy & ~has_height

    displacement = numpy.where(corrected, cloud_height * tan_vza, 0.0)
    lat_shift = numpy.degrees(displacement * numpy.cos(bearing) / EARTH_RADIUS_M)
    lon_shift = numpy.degrees(
        displacement * numpy.sin(bearing)
        / (EARTH_RADIUS_M * numpy.clip(numpy.cos(numpy.radians(lat2d)), 1e-6, None))
    )
    lat_c = lat2d + lat_shift
    lon_c = lon2d + lon_shift

    # Native footprint measured on the actual crop, in degrees. The 95th
    # percentile (not the median) is used because the footprint stretches
    # across the crop; a median-derived target leaves unobserved holes in the
    # half of the box where pixels are wider than the median.
    native_dlat = float(numpy.nanpercentile(numpy.abs(numpy.diff(numpy.where(on_disk, lat2d, numpy.nan), axis=0)), 95))
    native_dlon = float(numpy.nanpercentile(numpy.abs(numpy.diff(numpy.where(on_disk, lon2d, numpy.nan), axis=1)), 95))
    if not (native_dlat > 0.0 and native_dlon > 0.0):
        raise ValueError("could not measure the native pixel footprint on this crop")
    target_dlat = native_dlat * TARGET_CELL_FACTOR
    target_dlon = native_dlon * TARGET_CELL_FACTOR

    out_south = float(bounds["south"])
    out_north = float(bounds["north"])
    out_west = float(bounds["west"])
    out_east = float(bounds["east"])
    n_lat = max(int(numpy.floor((out_north - out_south) / target_dlat)), 1)
    n_lon = max(int(numpy.floor((out_east - out_west) / target_dlon)), 1)
    lat_axis = out_south + (numpy.arange(n_lat) + 0.5) * target_dlat
    lon_axis = out_west + (numpy.arange(n_lon) + 0.5) * target_dlon

    out_class = numpy.full((n_lat, n_lon), INVALID_CLASS, dtype="uint8")
    out_prob = numpy.full((n_lat, n_lon), numpy.nan, dtype="float32")
    out_uncorr = numpy.zeros((n_lat, n_lon), dtype="uint8")
    # The ACHAF height is retained rather than consumed and dropped. The
    # parallax correction above already displaces pixels by this value, so
    # keeping it adds no new trust to the artifact - only a new consumer.
    # float32 because ACHAF resolves cloud tops to tens of metres and this
    # field lands on every 10-minute scan; float64 would double its cost for
    # digits the retrieval does not have.
    out_height = numpy.full((n_lat, n_lon), numpy.nan, dtype="float32")
    observed = numpy.zeros((n_lat, n_lon), dtype=bool)

    src_ok = on_disk & numpy.isfinite(lat_c) & numpy.isfinite(lon_c)
    iy = numpy.floor((lat_c - out_south) / target_dlat).astype("int64")
    ix = numpy.floor((lon_c - out_west) / target_dlon).astype("int64")
    in_grid = src_ok & (iy >= 0) & (iy < n_lat) & (ix >= 0) & (ix < n_lon)

    flat_bins = (iy[in_grid] * n_lon + ix[in_grid]).ravel()
    src_lat = lat_c[in_grid].ravel()
    src_lon = lon_c[in_grid].ravel()
    src_acm = acm[in_grid].ravel()
    src_prob = prob[in_grid].ravel()
    src_dqf = dqf[in_grid].ravel()
    src_uncorr = uncorrected[in_grid].ravel()
    # `corrected`, not `has_height`: the retained height is exactly the set of
    # pixels the parallax correction actually displaced - cloudy AND carrying a
    # valid retrieval. ACHAF arrives on its own grid and is reindexed nearest
    # onto this one, so a clear pixel can sit nearest a neighbouring cloud's
    # retrieval; publishing that would be attributing a cloud top to clear sky.
    src_height = numpy.where(corrected, cloud_height, numpy.nan)[in_grid].ravel()

    if flat_bins.size:
        centre_lat = out_south + (flat_bins // n_lon + 0.5) * target_dlat
        centre_lon = out_west + (flat_bins % n_lon + 0.5) * target_dlon
        cos_lat = numpy.cos(numpy.radians(centre_lat))
        dist2 = (src_lat - centre_lat) ** 2 + ((src_lon - centre_lon) * cos_lat) ** 2
        order = numpy.lexsort((dist2, flat_bins))
        _, first = numpy.unique(flat_bins[order], return_index=True)
        chosen = order[first]
        rows = flat_bins[chosen] // n_lon
        cols = flat_bins[chosen] % n_lon
        chosen_acm = src_acm[chosen]
        chosen_dqf = src_dqf[chosen]
        chosen_prob = src_prob[chosen]
        chosen_uncorr = src_uncorr[chosen]
        chosen_height = src_height[chosen]
        good = numpy.isfinite(chosen_acm) & numpy.isfinite(chosen_dqf) & (chosen_dqf == 0.0)
        observed[rows, cols] = True
        keep = good
        out_class[rows[keep], cols[keep]] = chosen_acm[keep].astype("uint8")
        out_prob[rows[keep], cols[keep]] = numpy.clip(chosen_prob[keep], 0.0, 1.0).astype("float32")
        out_uncorr[rows[keep], cols[keep]] = chosen_uncorr[keep].astype("uint8")
        # NaN travels through unchanged: a cell whose winning pixel had no
        # ACHAF retrieval is published without a height, not with a guess.
        out_height[rows[keep], cols[keep]] = chosen_height[keep].astype("float32")
        # Quality-flagged pixels stay INVALID_CLASS: never clear, never NaN-dropped.

    total_cells = out_class.size
    populated_fraction = float(observed.sum()) / total_cells if total_cells else 0.0
    # Instrument coverage is judged at APPARENT positions: parallax correction
    # legitimately vacates cells on the anti-satellite side of a cloud (ground
    # the slant view could not see). Those cells stay invalid/unobserved in the
    # output, but they are not a retrieval gap.
    cov_iy = numpy.floor((numpy.where(on_disk, lat2d, out_south - 1.0) - out_south) / target_dlat).astype("int64")
    cov_ix = numpy.floor((numpy.where(on_disk, lon2d, out_west - 1.0) - out_west) / target_dlon).astype("int64")
    cov_in = on_disk & (cov_iy >= 0) & (cov_iy < n_lat) & (cov_ix >= 0) & (cov_ix < n_lon)
    covered = numpy.zeros((n_lat, n_lon), dtype=bool)
    covered[cov_iy[cov_in], cov_ix[cov_in]] = True
    coverage_fraction = float(covered.sum()) / total_cells if total_cells else 0.0
    invalid_fraction = float((observed & (out_class == INVALID_CLASS)).sum()) / total_cells if total_cells else 0.0
    cloudy_cells = int(numpy.isin(out_class, CLOUDY_CLASSES).sum())
    uncorrected_cells = int((out_uncorr == 1).sum())

    valid_time = numpy.datetime64(scan_start.replace(tzinfo=None), "ns")
    dataset = xarray.Dataset(
        {
            "cloud_class": (("latitude", "longitude"), out_class),
            "cloud_probability": (("latitude", "longitude"), out_prob),
            "parallax_uncorrected": (("latitude", "longitude"), out_uncorr),
            "cloud_top_height": (
                ("latitude", "longitude"),
                out_height,
                {"units": "m", "role": "ACHAF cloud-top height; display-derivation input only"},
            ),
        },
        coords={"latitude": lat_axis, "longitude": lon_axis},
        attrs={
            "source": "NOAA GOES-19 ABI L2 Enterprise Cloud Mask (ABI-L2-ACMF, Full Disk)",
            "scan_start": scan_start.isoformat(),
            "scan_end": str(scan_end_text) if scan_end_text else "",
            "satellite_longitude_deg": sub_lon,
            "class_meanings": CLASS_MEANINGS,
            "native_footprint_deg": f"{native_dlat:.5f} lat x {native_dlon:.5f} lon (measured on this crop)",
            "target_cell_deg": f"{target_dlat:.5f} lat x {target_dlon:.5f} lon",
            "regrid_disclosure": REGRID_DISCLOSURE,
            "parallax_disclosure": PARALLAX_DISCLOSURE,
            "accuracy_disclosure": ACCURACY_DISCLOSURE,
            "cloud_top_height_disclosure": HEIGHT_DISCLOSURE,
            "cloud_top_height_used": "yes" if achaf_used else "no (all cloudy pixels uncorrected)",
        },
    ).expand_dims(valid_time=[valid_time])

    stats = {
        "scan_start": scan_start,
        "populated_fraction": populated_fraction,
        "coverage_fraction": coverage_fraction,
        "invalid_fraction": invalid_fraction,
        "cloudy_cells": cloudy_cells,
        "uncorrected_cells": uncorrected_cells,
        "height_cells": int(numpy.isfinite(out_height).sum()),
        "achaf_used": achaf_used,
        "native_footprint_deg": (native_dlat, native_dlon),
        "target_cell_deg": (target_dlat, target_dlon),
        "probability_in_range": bool(
            numpy.all(numpy.isnan(out_prob) | ((out_prob >= 0.0) & (out_prob <= 1.0)))
        ),
        "classes_in_range": bool(
            numpy.all(numpy.isin(out_class, numpy.array([0, 1, 2, 3, INVALID_CLASS], dtype="uint8")))
        ),
    }
    return dataset, stats


class GOESCloudMaskAdapter:
    """Ingests GOES-19 ACMF cloud mask with ACHAF parallax correction."""

    source_id = "noaa-goes-east"
    adapter_version = "goes-abi-cloud-mask-v1"

    def __init__(
        self,
        *,
        base_url: str = GOES_S3_BASE,
        bounds: Mapping[str, float] = ATLANTIC_CONTEXT_BOUNDS,
        client: PoliteClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._bounds = dict(bounds)
        self._client = client

    def _get_client(self) -> PoliteClient:
        return self._client or PoliteClient()

    def discover(self, window: FetchWindow) -> list[RunCandidate]:
        client = self._get_client()
        acmf: dict[str, str] = {}
        achaf: dict[str, str] = {}
        # The newest hour prefix being empty is normal (a granule lands about
        # a minute after scan end), so the previous hours are listed too and
        # the newest stamp found wins. Four hours is far beyond freshness.
        for hours_back in range(4):
            moment = window.now - timedelta(hours=hours_back)
            for product, into in ((ACMF_PREFIX, acmf), (ACHAF_PREFIX, achaf)):
                url = f"{self._base_url}/?list-type=2&prefix={_hour_prefix(product, moment)}"
                try:
                    text = client.get_text(url)
                except Exception as error:  # noqa: BLE001 - one missing hour is not an outage
                    _log.warning("GOES listing failed for %s: %s", url, error)
                    continue
                for key in parse_bucket_keys(text):
                    match = _KEY.search(key)
                    if match:
                        into[match.group(2)] = key
        candidates: list[RunCandidate] = []
        for stamp in sorted(acmf, reverse=True):
            scan_start = parse_scan_stamp(stamp)
            if scan_start > window.now:
                continue
            candidates.append(
                RunCandidate(
                    provider_run_id=f"goes19-acmf-{stamp}",
                    run_time=scan_start,
                    urls=[f"{self._base_url}/{acmf[stamp]}"],
                    detail={
                        "acmf_key": acmf[stamp],
                        "achaf_key": achaf.get(stamp),
                        "scan_stamp": stamp,
                    },
                )
            )
            if len(candidates) >= 2:
                break
        if not candidates:
            raise AdapterUnavailable(
                "no GOES-19 ABI-L2-ACMF Full Disk granules listed in the last four hours"
            )
        return candidates

    def fetch(self, candidate: RunCandidate, window: FetchWindow, workdir: Path) -> RunResult:
        client = self._get_client()
        retrieved_at = datetime.now(UTC)
        acmf_key = str(candidate.detail["acmf_key"])
        achaf_key = candidate.detail.get("achaf_key")
        notes: list[str] = []

        acmf_path = workdir / Path(acmf_key).name
        client.download(f"{self._base_url}/{acmf_key}", acmf_path, max_bytes=MAX_ACMF_BYTES)

        achaf_path: Path | None = None
        if achaf_key:
            achaf_path = workdir / Path(str(achaf_key)).name
            try:
                client.download(f"{self._base_url}/{achaf_key}", achaf_path, max_bytes=MAX_ACHAF_BYTES)
            except Exception as error:  # noqa: BLE001 - height is an enhancement, not the product
                _log.warning("GOES ACHAF download failed (%s); publishing uncorrected", error)
                notes.append("ACHAF download failed; all cloudy pixels flagged parallax_uncorrected")
                achaf_path = None
        else:
            notes.append("no scan-paired ACHAF granule listed; all cloudy pixels flagged parallax_uncorrected")

        dataset, stats = process_granules(acmf_path, achaf_path, bounds=self._bounds)

        zarr_path = workdir / "goes19_cloud_mask.zarr.zip"
        write_zarr(dataset, zarr_path)

        complete = stats["coverage_fraction"] >= 0.99
        qc_passed = bool(stats["probability_in_range"] and stats["classes_in_range"])
        if not complete:
            notes.append(f"only {stats['coverage_fraction']:.3f} of target cells covered by the scan")

        provenance = {
            "source_id": self.source_id,
            "producer": "NOAA / NESDIS",
            "product": "GOES-19 ABI L2 Enterprise Cloud Mask (ACMF Full Disk) + Cloud Top Height (ACHAF)",
            "native_resolution": "2 km nadir fixed grid; " + dataset.attrs["native_footprint_deg"],
            "native_crs": "ABI fixed grid (geostationary); published regridded EPSG:4326",
            "adapter_version": self.adapter_version,
            "scan_start": stats["scan_start"].isoformat(),
            "populated_fraction": stats["populated_fraction"],
            "coverage_fraction": stats["coverage_fraction"],
            "invalid_fraction": stats["invalid_fraction"],
            "occlusion_note": (
                "cells vacated by parallax correction were occluded from the "
                "satellite and are published as unobserved, never as clear"
            ),
            "cloudy_cells": stats["cloudy_cells"],
            "parallax_uncorrected_cells": stats["uncorrected_cells"],
            "cloud_top_height_cells": stats["height_cells"],
            "cloud_top_height_disclosure": HEIGHT_DISCLOSURE,
            "cloud_top_height_maturity": "NOAA Provisional",
            "regrid_disclosure": REGRID_DISCLOSURE,
            "parallax_disclosure": PARALLAX_DISCLOSURE,
            "accuracy_disclosure": ACCURACY_DISCLOSURE,
            # NOAA's own cloud mask and cloud-top height values, moved onto
            # this deployment's grid nearest-neighbour and parallax-corrected
            # in place. No value is computed here and no intermediary stands
            # between the producer and this deployment, so the class is
            # retrieved; the regrid and parallax disclosures above are what
            # tell a reader the cells were moved.
            **declared_classes(["retrieved"]),
        }

        artifact = Artifact(
            logical_name="cloud_mask",
            media_type=MEDIA_ZARR,
            payload_path=zarr_path,
            provenance=provenance,
        )
        return RunResult(
            source_id=self.source_id,
            provider_run_id=candidate.provider_run_id,
            run_time=stats["scan_start"],
            retrieved_at=retrieved_at,
            complete=complete,
            qc_passed=qc_passed,
            artifacts=[artifact],
            native_crs="EPSG:4326",
            notes="; ".join(notes) if notes else "scan regridded with parallax correction",
        )


GOES_ADAPTER = register(GOESCloudMaskAdapter())
