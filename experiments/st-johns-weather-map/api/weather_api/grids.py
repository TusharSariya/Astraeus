"""Map images rendered by this experiment from its own retrieved grids.

Everything else `/layers/{id}/raster` serves is rendered upstream by ECCC
GeoMet. The layers here are different: no provider publishes a raster that says
what the stored grid says under this experiment's rules - GFS cloud strata
(`cloud_low` / `cloud_middle` / `cloud_high`, the provider's own LCDC/MCDC/HCDC)
have no upstream raster for this region at all, and HRDPS/RDPS total cloud is
only offered upstream as an opaque grey ramp - so the image is drawn *here*,
from the published artifact, under these rules:

* **Only stored values, at their native cells.** On a rectilinear grid every
  output pixel is the stored value of the single native cell that
  geographically contains it; on a rotated (curvilinear) grid it is the value
  of the nearest published cell centre, accepted only within half a cell
  diagonal - pure nearest-neighbor either way. Nothing is interpolated,
  smoothed, resampled onto a finer grid, or extrapolated past the grid edge.
  The blocky look is the honest look.
* **Times are what was ingested.** The offered frames are exactly the valid
  times the artifact carries for that variable; a requested instant with no
  stored frame within tolerance is a 422, never the silent reuse of an older
  frame.
* **The colormap is presentation, not derivation.** It is a single-hue ramp,
  declared in :data:`COLORMAP_DOC`, disclosed on every response and served as
  a legend, and it never changes a value: 0 percent and missing cells are
  fully transparent, 100 percent is opaque white.
* **Provenance rides the response.** Source, product, model run, valid time,
  CRS and the rendering rules are stated in ``X-Weather-*`` headers, the same
  pattern the proxied imagery uses. ``operational`` stays false.
"""

from __future__ import annotations

import logging
import math
import struct
import threading
import time
import weakref
import zlib
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from .store import FIELD_BY_VARIABLE, layer_id_for  # noqa: F401  (shared id rule)

UTC = timezone.utc
LOGGER = logging.getLogger(__name__)

#: The CRS a rendered grid may be asked for. Positioning is exact in both: the
#: pixel row/column centres are computed in the requested CRS and each is
#: assigned the stored cell that contains it.
SUPPORTED_GRID_CRS = ("EPSG:4326", "EPSG:3857")

#: EPSG:3857 constants, matching ``ingest.adapters.eccc_geomet``.
WEB_MERCATOR_RADIUS_M = 6378137.0
WEB_MERCATOR_MAX_LATITUDE = 85.051128779807

#: The colormap, in words, exactly as applied. Presentation only: no stored
#: value is changed by it, and the mapping is linear and invertible.
COLORMAP_DOC = (
    "cloud cover percent -> white (RGB 255,255,255) with alpha = round(percent * 2.55), "
    "linear from fully transparent at 0 percent to opaque at 100 percent; "
    "cells with no stored value are fully transparent; colormap-version grid-cloud-alpha-v1"
)

#: What every rendered pixel is, in words, for the response headers - one
#: statement per sampling method, because a rectilinear grid's pixel is "the
#: cell containing it" while a rotated grid's pixel is "the nearest published
#: cell centre", and the header must say which rule actually ran.
RENDER_SEMANTICS_BY_METHOD = {
    "rectilinear": (
        "each pixel is the stored value of the single native grid cell containing it "
        "(nearest-neighbor); nothing is interpolated, smoothed or extrapolated; a transparent "
        "pixel means no stored cell or no stored value there, or a stored cover of 0 percent"
    ),
    "curvilinear_nearest_cell": (
        "each pixel is the stored value of the nearest published cell centre of the provider's "
        "own rotated (curvilinear) grid, accepted only within half a cell diagonal; nothing is "
        "interpolated, smoothed or extrapolated; a transparent pixel means no stored cell or no "
        "stored value there, or a stored cover of 0 percent"
    ),
}
RENDER_SEMANTICS_DOC = RENDER_SEMANTICS_BY_METHOD["rectilinear"]

#: The rendering disclosed as a derivation-style statement. Drawing pixels from
#: stored numbers is presentation, but it is still this experiment's own step
#: between the artifact and the reader's eye, so it is versioned and disclosed
#: the way a derivation would be.
RENDER_DERIVATION_BY_METHOD = {
    "rectilinear": (
        "weather_api.grids: nearest-neighbor rasterization of the stored grid at its native "
        "cells; colormap " + COLORMAP_DOC
    ),
    "curvilinear_nearest_cell": (
        "weather_api.grids: nearest-published-cell rasterization of the stored rotated grid, "
        "each pixel matched to one cell centre within half a cell diagonal; colormap " + COLORMAP_DOC
    ),
}
RENDER_DERIVATION_VERSION_BY_METHOD = {
    "rectilinear": "rendered-grid-nearest-v1",
    "curvilinear_nearest_cell": "rendered-grid-nearest-cell-v1",
}
RENDER_DERIVATION = RENDER_DERIVATION_BY_METHOD["rectilinear"]
RENDER_DERIVATION_VERSION = RENDER_DERIVATION_VERSION_BY_METHOD["rectilinear"]


class GridUnavailable(RuntimeError):
    """The artifact could not be read; nothing is substituted for it."""


class GridNotPublished(LookupError):
    """No current artifact carries this layer's variable."""


class FrameNotStored(ValueError):
    """The requested instant has no stored frame within tolerance."""


@dataclass(frozen=True)
class RenderedGridSpec:
    """One stored-grid variable offered as a map layer rendered here.

    Identity only. Times, units and the grid itself are read from the
    published artifact at request time - they are retrieved facts.
    """

    layer_id: str
    source_id: str
    logical_name: str
    variable: str
    field: str
    title_field: str
    #: The provider's own level name for the stratum, disclosed verbatim.
    provider_level: str


RENDERED_GRID_SPECS: tuple[RenderedGridSpec, ...] = (
    RenderedGridSpec(
        "noaa-gfs-surface-cloud-low", "noaa-gfs", "surface", "cloud_low",
        "cloud_low", "low cloud cover", "low cloud layer",
    ),
    RenderedGridSpec(
        "noaa-gfs-surface-cloud-middle", "noaa-gfs", "surface", "cloud_middle",
        "cloud_middle", "middle cloud cover", "middle cloud layer",
    ),
    RenderedGridSpec(
        "noaa-gfs-surface-cloud-high", "noaa-gfs", "surface", "cloud_high",
        "cloud_high", "high cloud cover", "high cloud layer",
    ),
    RenderedGridSpec(
        "eccc-hrdps-surface-total-cloud", "eccc-hrdps", "surface", "total_cloud",
        "total_cloud", "total cloud cover", "surface (whole-column cover)",
    ),
    RenderedGridSpec(
        "eccc-rdps-surface-total-cloud", "eccc-rdps", "surface", "total_cloud",
        "total_cloud", "total cloud cover", "surface (whole-column cover)",
    ),
)

_SPEC_BY_ID = {spec.layer_id: spec for spec in RENDERED_GRID_SPECS}


def rendered_grid_spec(layer_id: str) -> RenderedGridSpec | None:
    return _SPEC_BY_ID.get(layer_id)


def grid_semantics(spec: RenderedGridSpec, provenance: Mapping[str, Any]) -> str:
    """What the layer says about itself, verbatim, in ``/layers``.

    Product and native resolution are read from the published artifact's own
    provenance - stating them here would repeat a fact this module cannot
    verify for a source it did not ingest.
    """
    product = str(provenance.get("product", spec.source_id))
    resolution = str(provenance.get("native_resolution", "an undeclared native resolution"))
    return (
        f"rendered by this experiment from the retrieved {product} field: the provider-declared "
        f"{spec.title_field} ({spec.variable} at the provider's own {spec.provider_level}), "
        f"native grid {resolution}, displayed nearest-neighbor at the native cells and never "
        "smoothed - the blocky cells are the stored data. Values and times are read from the "
        f"published {spec.source_id} artifact; no pixel is interpolated, extrapolated or substituted. "
        f"Colormap (presentation only): {COLORMAP_DOC}."
    )


# ------------------------------------------------------------------ PNG

def encode_png(rgba: Any) -> bytes:
    """A minimal RGBA PNG encoder (no dependency on an imaging library).

    ``rgba`` is an ``(height, width, 4)`` uint8 array. Filter type 0 on every
    row, one zlib-compressed IDAT. Deliberately boring: the pixels are the
    evidence and nothing here may resample or requantise them.
    """
    import numpy  # noqa: PLC0415

    data = numpy.ascontiguousarray(rgba, dtype="uint8")
    if data.ndim != 3 or data.shape[2] != 4:
        raise ValueError("encode_png expects an (height, width, 4) uint8 array")
    height, width = data.shape[:2]
    # Filter byte 0 prepended per row, built in one array operation: the
    # Python-level per-row loop was hundreds of milliseconds at full size.
    filtered = numpy.zeros((height, width * 4 + 1), dtype="uint8")
    filtered[:, 1:] = data.reshape(height, width * 4)
    raw = filtered.tobytes()

    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw, 3))
        + chunk(b"IEND", b"")
    )


# ------------------------------------------------------------ rasterizing

def _mercator_y(latitude: Any) -> Any:
    import numpy  # noqa: PLC0415

    lat = numpy.asarray(latitude, dtype="float64")
    return WEB_MERCATOR_RADIUS_M * numpy.log(numpy.tan(numpy.pi / 4 + numpy.radians(lat) / 2))


def _uniform_step(coordinates: Any) -> float:
    """The uniform spacing of a 1-D coordinate axis, or raise.

    The whole exactness claim rests on knowing where each cell's edges are.
    A non-uniform axis would need per-cell edges; rather than guess, refuse.
    """
    import numpy  # noqa: PLC0415

    values = numpy.asarray(coordinates, dtype="float64")
    if values.ndim != 1 or values.size < 2:
        raise GridUnavailable("the grid axis is not a 1-D coordinate of at least two cells")
    gaps = numpy.diff(values)
    step = float(gaps[0])
    if step == 0 or not numpy.allclose(gaps, step, rtol=0, atol=abs(step) * 1e-6):
        raise GridUnavailable("the grid axis is not uniformly spaced; refusing to place cells by guesswork")
    return step


def _cell_indices(targets: Any, centres: Any) -> Any:
    """Index of the cell containing each target coordinate, or -1 outside.

    Cells are the closed-open intervals ``centre - step/2 .. centre + step/2``
    of a uniform axis. A target beyond the outermost cell edge maps to -1:
    the grid ends where its cells end, and nothing is painted past it.
    """
    import numpy  # noqa: PLC0415

    values = numpy.asarray(centres, dtype="float64")
    step = _uniform_step(values)
    position = (numpy.asarray(targets, dtype="float64") - values[0]) / step
    index = numpy.round(position).astype("int64")
    outside = (position < -0.5) | (position > values.size - 0.5)
    index[outside] = -1
    index[index >= values.size] = values.size - 1
    return index


def _pixel_centres(
    *, south: float, west: float, north: float, east: float, width: int, height: int, crs: str
) -> tuple[Any, Any]:
    """Latitude of each pixel row centre and longitude of each column centre.

    Pixel-centre longitudes are linear in both CRS (mercator x is linear in
    longitude). Latitudes are linear in EPSG:4326 and linear in mercator y
    for EPSG:3857. Row 0 is the top of the image (north).
    """
    import numpy  # noqa: PLC0415

    column_lon = west + (numpy.arange(width, dtype="float64") + 0.5) * (east - west) / width
    if crs == "EPSG:3857":
        if abs(south) > WEB_MERCATOR_MAX_LATITUDE or abs(north) > WEB_MERCATOR_MAX_LATITUDE:
            raise ValueError(f"latitude bounds are outside EPSG:3857's defined range (+/-{WEB_MERCATOR_MAX_LATITUDE})")
        y_north, y_south = float(_mercator_y(north)), float(_mercator_y(south))
        row_y = y_north - (numpy.arange(height, dtype="float64") + 0.5) * (y_north - y_south) / height
        row_lat = numpy.degrees(numpy.arctan(numpy.sinh(row_y / WEB_MERCATOR_RADIUS_M)))
    else:
        row_lat = north - (numpy.arange(height, dtype="float64") + 0.5) * (north - south) / height
    return row_lat, column_lon


def sample_field(
    values: Any,
    latitudes: Any,
    longitudes: Any,
    *,
    bounds: Mapping[str, float],
    width: int,
    height: int,
    crs: str = "EPSG:4326",
) -> tuple[Any, Any]:
    """Nearest-neighbor sample of one stored 2-D field at each pixel centre.

    The shared core of every locally rendered layer: pixel centres are
    computed in the requested CRS, converted to the geographic coordinate they
    represent, and each is assigned the stored cell containing it. Returns the
    sampled values and the inside-the-grid mask; pixels outside the grid carry
    cell 0's value and inside=False, and the caller must not paint them.
    """
    import numpy  # noqa: PLC0415

    south, west = float(bounds["south"]), float(bounds["west"])
    north, east = float(bounds["north"]), float(bounds["east"])
    field = numpy.asarray(values, dtype="float64")
    if field.ndim != 2:
        raise GridUnavailable("the stored variable is not a 2-D (latitude, longitude) field")

    row_lat, column_lon = _pixel_centres(south=south, west=west, north=north, east=east, width=width, height=height, crs=crs)
    row_index = _cell_indices(row_lat, latitudes)
    column_index = _cell_indices(column_lon, longitudes)

    inside = (row_index[:, None] >= 0) & (column_index[None, :] >= 0)
    safe_rows = numpy.where(row_index < 0, 0, row_index)
    safe_columns = numpy.where(column_index < 0, 0, column_index)
    sampled = field[safe_rows[:, None], safe_columns[None, :]]
    return sampled, inside


# The pixel-to-cell lookup of a curvilinear grid (KDTree build + query +
# pitch medians) is a pure function of (grid, bounds, size, crs) and by far
# the most expensive step of a render - and it is identical for every frame
# of a scrub at a fixed viewport. Cached per caller-supplied token (the open
# dataset's identity plus the artifact revision), bounded, thread-safe. A
# repeat render reuses only index arithmetic; the sampled values are always
# read fresh from the requested frame.
_LOOKUP_CACHE_MAX = 8
_lookup_cache: "OrderedDict[tuple, tuple[Any, Any]]" = OrderedDict()
_lookup_lock = threading.Lock()


def _lookup_cache_get(key: tuple) -> tuple[Any, Any] | None:
    with _lookup_lock:
        held = _lookup_cache.get(key)
        if held is not None:
            _lookup_cache.move_to_end(key)
        return held


def _lookup_cache_put(key: tuple, value: tuple[Any, Any]) -> None:
    with _lookup_lock:
        _lookup_cache[key] = value
        _lookup_cache.move_to_end(key)
        while len(_lookup_cache) > _LOOKUP_CACHE_MAX:
            _lookup_cache.popitem(last=False)


def sample_field_curvilinear(
    values: Any,
    latitudes: Any,
    longitudes: Any,
    *,
    bounds: Mapping[str, float],
    width: int,
    height: int,
    crs: str = "EPSG:4326",
    cache_token: tuple | None = None,
) -> tuple[Any, Any]:
    """Nearest-published-cell sample of a curvilinear grid at each pixel centre.

    HRDPS and RDPS are published on rotated lat/lon grids, so ``latitude`` and
    ``longitude`` arrive as 2-D fields and the containing-cell lookup of
    :func:`sample_field` has no axes to work with. The honest analogue is the
    same rule ``/point`` sampling applies (``curvilinear_nearest_cell`` in
    ``store.py``): each pixel centre takes the single nearest published cell
    centre by equirectangular distance, and is accepted only within half a
    cell diagonal of it - a pixel farther than that from every centre is
    outside the grid and must not be painted. Nothing is interpolated,
    regridded or averaged: every painted pixel is one stored value.
    """
    import numpy  # noqa: PLC0415
    from scipy.spatial import cKDTree  # noqa: PLC0415

    south, west = float(bounds["south"]), float(bounds["west"])
    north, east = float(bounds["north"]), float(bounds["east"])
    field = numpy.asarray(values, dtype="float64")
    lat2d = numpy.asarray(latitudes, dtype="float64")
    lon2d = numpy.asarray(longitudes, dtype="float64")
    if lat2d.ndim != 2 or lat2d.shape != lon2d.shape or field.shape != lat2d.shape:
        raise GridUnavailable("the stored variable and its 2-D coordinates do not describe one curvilinear grid")
    if lat2d.size < 4:
        raise GridUnavailable("the stored curvilinear grid is too small to establish a cell pitch")

    # The same cos(latitude) longitude scaling the point sampler uses, taken
    # at the request window's centre - the window is a few hundred km across,
    # where the correction is effectively constant.
    scale = math.cos(math.radians((south + north) / 2.0))
    lon2d = ((lon2d + 180.0) % 360.0) - 180.0

    lookup_key = None if cache_token is None else (
        cache_token, round(south, 9), round(west, 9), round(north, 9), round(east, 9), width, height, crs,
    )
    held = _lookup_cache_get(lookup_key) if lookup_key is not None else None
    if held is not None:
        index, inside = held
    else:
        row_lat, column_lon = _pixel_centres(south=south, west=west, north=north, east=east, width=width, height=height, crs=crs)
        pixel_lat = numpy.repeat(row_lat, width)
        pixel_lon = numpy.tile(column_lon, height)

        tree = cKDTree(numpy.column_stack([lat2d.ravel(), lon2d.ravel() * scale]))
        distance, index = tree.query(numpy.column_stack([pixel_lat, pixel_lon * scale]))

        # The grid's own cell pitch along each axis, as the median spacing of
        # adjacent cell centres; the acceptance radius is half a cell diagonal
        # (plus 5 percent so a pixel exactly on a cell corner is not dropped to
        # floating-point noise).
        pitch_rows = numpy.median(numpy.hypot(numpy.diff(lat2d, axis=0), numpy.diff(lon2d, axis=0) * scale))
        pitch_columns = numpy.median(numpy.hypot(numpy.diff(lat2d, axis=1), numpy.diff(lon2d, axis=1) * scale))
        if not (numpy.isfinite(pitch_rows) and numpy.isfinite(pitch_columns)) or pitch_rows <= 0 or pitch_columns <= 0:
            raise GridUnavailable("the stored curvilinear grid has no measurable cell pitch")
        limit = 0.5 * math.hypot(float(pitch_rows), float(pitch_columns)) * 1.05
        inside = (distance <= limit).reshape(height, width)
        if lookup_key is not None:
            _lookup_cache_put(lookup_key, (index, inside))

    sampled = field.ravel()[index].reshape(height, width)
    return sampled, inside


def rasterize(
    values: Any,
    latitudes: Any,
    longitudes: Any,
    *,
    bounds: Mapping[str, float],
    width: int,
    height: int,
    crs: str = "EPSG:4326",
    cache_token: tuple | None = None,
) -> Any:
    """RGBA pixels for one stored 2-D field over ``bounds``. Nearest-neighbor only.

    ``values`` is ``(latitude, longitude)``-shaped percent cover. Each output
    pixel centre is computed in the requested CRS, converted to the geographic
    coordinate it represents, and assigned the stored cell containing it. In
    EPSG:3857 the pixel rows are uniform in mercator metres - which is what
    makes corner-pinning the result onto a web-mercator canvas exact - and are
    inverted back to latitude before the cell lookup, so the same stored cell
    answers regardless of projection.
    """
    import numpy  # noqa: PLC0415

    if crs not in SUPPORTED_GRID_CRS:
        raise ValueError(f"crs must be one of {', '.join(SUPPORTED_GRID_CRS)}, not {crs!r}")
    south, west = float(bounds["south"]), float(bounds["west"])
    north, east = float(bounds["north"]), float(bounds["east"])
    if south >= north or west >= east:
        raise ValueError("bounds must be a south-west to north-east box")
    if width < 1 or height < 1:
        raise ValueError("a rendered image needs at least one pixel in each dimension")

    if numpy.asarray(latitudes).ndim == 2:
        sampled, inside = sample_field_curvilinear(
            values, latitudes, longitudes, bounds=bounds, width=width, height=height, crs=crs, cache_token=cache_token,
        )
    else:
        sampled, inside = sample_field(values, latitudes, longitudes, bounds=bounds, width=width, height=height, crs=crs)
    finite = numpy.isfinite(sampled) & inside
    percent = numpy.clip(numpy.where(finite, sampled, 0.0), 0.0, 100.0)
    alpha = numpy.rint(percent * 2.55).astype("uint8")
    alpha[~finite] = 0

    rgba = numpy.zeros((height, width, 4), dtype="uint8")
    rgba[..., 0:3] = 255
    rgba[..., 3] = alpha
    return rgba


# ----------------------------------------------------------- store access

MIN_TOLERANCE_SECONDS = 60
UNKNOWN_CADENCE_TOLERANCE_SECONDS = 900


def frame_tolerance_seconds(cadence_seconds: int | None) -> int:
    """Half a cadence, exactly the rule the layer index publishes."""
    if cadence_seconds is None or cadence_seconds <= 0:
        return UNKNOWN_CADENCE_TOLERANCE_SECONDS
    return max(MIN_TOLERANCE_SECONDS, cadence_seconds // 2)


def _modal_cadence(stamps: Sequence[datetime]) -> int | None:
    if len(stamps) < 2:
        return None
    gaps = [round((later - earlier).total_seconds()) for earlier, later in zip(stamps, stamps[1:])]
    gaps = [gap for gap in gaps if gap > 0]
    return max(set(gaps), key=gaps.count) if gaps else None


def _dataset_times(dataset: Any) -> list[datetime]:
    import pandas  # noqa: PLC0415

    for name in ("valid_time", "time"):
        if name in dataset.coords or name in dataset.dims:
            return sorted({pandas.Timestamp(value).to_pydatetime().replace(tzinfo=UTC) for value in dataset[name].values})
    return []


def _time_name(dataset: Any) -> str | None:
    for name in ("valid_time", "time"):
        if name in dataset.coords or name in dataset.dims:
            return name
    return None


# ``store.current()`` is a database round trip; a scrub issues many raster
# requests in a burst that all want the same answer. Memoised for a few
# seconds per store instance (held by weak reference so a replaced store, or
# a test's fake, never answers for another). The staleness ceiling is well
# inside every layer's own tolerance.
_CURRENT_TTL_SECONDS = 5.0
_current_cache: dict[int, tuple[Any, float, list[Any]]] = {}
_current_lock = threading.Lock()


def _current_artifacts(store: Any) -> list[Any]:
    key = id(store)
    now = time.monotonic()
    with _current_lock:
        held = _current_cache.get(key)
        if held is not None and held[0]() is store and now - held[1] < _CURRENT_TTL_SECONDS:
            return held[2]
    artifacts = list(store.current())
    try:
        reference = weakref.ref(store)
    except TypeError:
        return artifacts
    with _current_lock:
        for stale in [k for k, (ref, stamp, _) in _current_cache.items() if ref() is None or now - stamp >= _CURRENT_TTL_SECONDS]:
            del _current_cache[stale]
        _current_cache[key] = (reference, now, artifacts)
    return artifacts


def _grid_artifact(store: Any, spec: RenderedGridSpec) -> Any | None:
    for artifact in _current_artifacts(store):
        if artifact.source_id == spec.source_id and artifact.logical_name == spec.logical_name:
            return artifact
    return None


@dataclass(frozen=True)
class RenderedGridImage:
    """One locally rendered image plus everything needed to say what it shows."""

    payload: bytes
    content_type: str
    valid_time: datetime
    run_time: datetime | None
    crs: str
    units: str
    source_id: str
    product: str
    licence: str
    attribution: str
    #: ``rectilinear`` (containing cell on 1-D axes) or
    #: ``curvilinear_nearest_cell`` (nearest cell centre on a rotated grid) -
    #: the same vocabulary the point sampler discloses.
    sample_method: str = "rectilinear"

    @property
    def byte_size(self) -> int:
        return len(self.payload)

    def headers(self, *, layer_id: str) -> dict[str, str]:
        """Every one of these is a retrieved fact or the disclosed rendering rule."""
        return {
            "Cache-Control": "public, max-age=60",
            "X-Weather-Layer-Id": layer_id,
            "X-Weather-Data-Mode": "live",
            "X-Weather-Operational": "false",
            # The values come from a published artifact; the image bytes are
            # rendered here, from those values, and never stored.
            "X-Weather-Evidence-Basis": "published_artifact",
            "X-Weather-Image-Basis": "rendered_grid",
            "X-Weather-Retrieval-Status": "retrieved",
            "X-Weather-Render-Semantics": RENDER_SEMANTICS_BY_METHOD[self.sample_method],
            "X-Weather-Sample-Method": self.sample_method,
            "X-Weather-Colormap": COLORMAP_DOC,
            "X-Weather-Derivation": RENDER_DERIVATION_BY_METHOD[self.sample_method],
            "X-Weather-Derivation-Version": RENDER_DERIVATION_VERSION_BY_METHOD[self.sample_method],
            "X-Weather-Source-Id": self.source_id,
            "X-Weather-Product": self.product,
            "X-Weather-Units": self.units,
            "X-Weather-Crs": self.crs,
            "X-Weather-Valid-Time": self.valid_time.isoformat(),
            "X-Weather-Time-Semantics": "valid at the instant in X-Weather-Valid-Time",
            "X-Weather-Reference-Time": self.run_time.isoformat() if self.run_time else "none",
            "X-Weather-Byte-Size": str(self.byte_size),
            "X-Weather-Licence": self.licence,
            "X-Weather-Attribution": self.attribution,
        }


def _registry_terms(source_id: str) -> tuple[str, str]:
    """Licence and attribution from the registry record, or an honest absence."""
    try:
        from ingest.registry import get_config  # noqa: PLC0415

        config = get_config(source_id)
        if config is not None:
            return str(config.licence), str(config.attribution)
    except Exception:  # pragma: no cover - registry read is best effort here
        LOGGER.debug("registry terms unavailable for %s", source_id, exc_info=True)
    return "see registry record", "see registry record"


# Finished renders, keyed by everything that determines the bytes (layer,
# frame, dataset identity + revision, bounds, size, CRS). Bounded; the entry
# is the immutable RenderedGridImage itself.
_IMAGE_CACHE_MAX = 256
_image_cache: "OrderedDict[tuple, RenderedGridImage]" = OrderedDict()
_image_lock = threading.Lock()


def render_grid(
    store: Any,
    spec: RenderedGridSpec,
    *,
    bounds: Mapping[str, float],
    width: int,
    height: int,
    crs: str = "EPSG:4326",
    valid_time: datetime | None = None,
) -> RenderedGridImage:
    """Render one stored frame, or raise naming exactly what is missing.

    The frame is the stored valid time nearest the request, accepted only
    within half the layer's own cadence - the same tolerance rule the layer
    index publishes - and the frame's real instant is what the response
    carries, never the requested one.
    """
    artifact = _grid_artifact(store, spec)
    if artifact is None:
        raise GridNotPublished(f"no {spec.source_id} {spec.logical_name} artifact is currently published")
    try:
        dataset = store.open(artifact)
    except Exception as error:
        raise GridUnavailable(f"the published artifact could not be read: {type(error).__name__}: {error}") from error
    if spec.variable not in dataset.data_vars:
        raise GridNotPublished(f"the published {spec.source_id} artifact does not carry {spec.variable}")

    times = _dataset_times(dataset)
    if not times:
        raise GridNotPublished(f"the published {spec.source_id} artifact carries no time axis")
    moment = (valid_time or datetime.now(UTC)).astimezone(UTC)
    nearest = min(times, key=lambda stamp: abs((stamp - moment).total_seconds()))
    tolerance = frame_tolerance_seconds(_modal_cadence(times))
    distance = abs((nearest - moment).total_seconds())
    if distance > tolerance:
        raise FrameNotStored(
            f"no stored frame within {tolerance} s of {moment.isoformat()}; the nearest is "
            f"{nearest.isoformat()} ({int(distance)} s away). Frames are only what was ingested."
        )

    # Frames are immutable per published revision, so an identical render is
    # answered from a bounded cache of finished images. The dataset's own
    # identity is part of the key: a republished revision opens a new dataset
    # and never inherits another's pixels.
    cache_token = (id(dataset), str(getattr(artifact, "revision_id", "")))
    image_key = (
        spec.layer_id, nearest.isoformat(), cache_token,
        round(float(bounds["south"]), 9), round(float(bounds["west"]), 9),
        round(float(bounds["north"]), 9), round(float(bounds["east"]), 9),
        width, height, crs,
    )
    with _image_lock:
        held_image = _image_cache.get(image_key)
        if held_image is not None:
            _image_cache.move_to_end(image_key)
            return held_image

    time_name = _time_name(dataset)
    variable = dataset[spec.variable]
    import numpy  # noqa: PLC0415

    frame = variable.sel({time_name: numpy.datetime64(nearest.replace(tzinfo=None), "ns")})
    lat_name = "latitude" if "latitude" in dataset.coords else "lat"
    lon_name = "longitude" if "longitude" in dataset.coords else "lon"
    if lat_name not in dataset.coords or lon_name not in dataset.coords:
        raise GridUnavailable("the stored grid carries no latitude/longitude coordinates")
    if dataset[lat_name].ndim == 2:
        # Rotated (curvilinear) grid: the 2-D coordinates span anonymous
        # dimensions, and the frame must be ordered the way they are.
        sample_method = "curvilinear_nearest_cell"
        grid_dims = tuple(dataset[lat_name].dims)
        if tuple(frame.dims) != grid_dims:
            frame = frame.transpose(*grid_dims)
    else:
        sample_method = "rectilinear"
        if tuple(frame.dims) != (lat_name, lon_name):
            frame = frame.transpose(lat_name, lon_name)

    rgba = rasterize(
        frame.values,
        dataset[lat_name].values,
        dataset[lon_name].values,
        bounds=bounds,
        width=width,
        height=height,
        crs=crs,
        cache_token=cache_token,
    )
    licence, attribution = _registry_terms(spec.source_id)
    provenance = dict(artifact.provenance or {})
    image = RenderedGridImage(
        payload=encode_png(rgba),
        content_type="image/png",
        valid_time=nearest,
        run_time=artifact.run_time,
        crs=crs,
        units=str(variable.attrs.get("units", "unknown")),
        source_id=spec.source_id,
        product=str(provenance.get("product", spec.source_id)),
        licence=licence,
        attribution=attribution,
        sample_method=sample_method,
    )
    with _image_lock:
        _image_cache[image_key] = image
        _image_cache.move_to_end(image_key)
        while len(_image_cache) > _IMAGE_CACHE_MAX:
            _image_cache.popitem(last=False)
    return image


# ------------------------------------------------------- derived motion

#: Logical name of the worker-derived cloud-motion artifact (see
#: ``ingest/derive/cloud_motion.py``). Display-support only: it feeds the
#: /flow endpoint below and nothing else.
CLOUD_MOTION_LOGICAL_NAME = "cloud_motion"

FLOW_SEMANTICS_DOC = (
    "each pixel carries the derived motion vector of the stored cell under it, in output pixels "
    "over the frame interval, quantized to 8 bits over the declared scale; blue channel is the "
    "weight the display mixes advection against a plain crossfade on (255 = advect, 0 = "
    "crossfade), being the lesser of the local trusted-flow support and the photometric "
    "agreement of the two half-interval warps, and zero for a pair whose warp does not beat "
    "persistence; artifacts predating that weight carry the raw forward-backward consistency "
    "there instead; this is a display derivation computed between two published frames - not "
    "provider output, not evidence"
)

TANGENT_SEMANTICS_DOC = (
    "cubic Hermite segment tangents for the pair, side by side: the left half is the start-knot "
    "velocity, the right half the end-knot velocity, R/G the vector in output pixels over the "
    "frame interval, quantized to 8 bits over the declared scale, alpha opaque; knot velocities "
    "are QVI central differences of the neighbouring pairs' flows, derived only from the layer's "
    "retrieved frames; display derivation - not provider output, not evidence"
)

#: The texture variants /flow serves. ``motion`` is the pairwise flow the
#: first carve-out approved; ``tangents`` is the C1 Hermite extension.
FLOW_TEXTURES = ("motion", "tangents")


class FlowNotAvailable(LookupError):
    """No derived motion exists for the requested frame pair."""


@dataclass(frozen=True)
class FlowImage:
    """One derived-motion texture plus its disclosure."""

    payload: bytes
    content_type: str
    frame_from: datetime
    frame_to: datetime
    scale_pixels: float
    crs: str
    source_id: str
    method: str
    version: str
    texture: str = "motion"

    def headers(self, *, layer_id: str) -> dict[str, str]:
        return {
            "Cache-Control": "public, max-age=60",
            "X-Weather-Layer-Id": layer_id,
            "X-Weather-Operational": "false",
            "X-Weather-Image-Basis": "derived_motion",
            "X-Weather-Evidence-Basis": "published_artifact",
            "X-Weather-Flow-Texture": self.texture,
            "X-Weather-Render-Semantics": TANGENT_SEMANTICS_DOC if self.texture == "tangents" else FLOW_SEMANTICS_DOC,
            "X-Weather-Derivation": self.method,
            "X-Weather-Derivation-Version": self.version,
            "X-Weather-Flow-Scale": f"{self.scale_pixels:.4f}",
            "X-Weather-Frame-From": self.frame_from.isoformat(),
            "X-Weather-Frame-To": self.frame_to.isoformat(),
            "X-Weather-Source-Id": self.source_id,
            "X-Weather-Crs": self.crs,
        }


def _forward_pixel_y(latitudes: Any, *, south: float, north: float, height: int, crs: str) -> Any:
    """Fractional output-pixel row for geographic latitudes (row 0 = north)."""
    import numpy  # noqa: PLC0415

    if crs == "EPSG:3857":
        y_north, y_south = float(_mercator_y(north)), float(_mercator_y(south))
        return (y_north - _mercator_y(numpy.clip(latitudes, -WEB_MERCATOR_MAX_LATITUDE, WEB_MERCATOR_MAX_LATITUDE))) / (y_north - y_south) * height
    return (north - latitudes) / (north - south) * height


def render_flow(
    store: Any,
    spec: RenderedGridSpec,
    *,
    frame_from: datetime,
    frame_to: datetime,
    bounds: Mapping[str, float],
    width: int,
    height: int,
    crs: str = "EPSG:4326",
    texture: str = "motion",
) -> FlowImage:
    """One derived-motion texture for one adjacent frame pair.

    ``texture="motion"`` is the pairwise flow (R/G vector, B consistency).
    ``texture="tangents"`` is the pair's two cubic Hermite knot velocities,
    side by side in one double-width image (left = start knot, right = end
    knot), alpha opaque - a vector component never rides the alpha channel,
    where browser premultiplication would destroy its precision near zero.
    Both are resampled with the same pixel-to-cell rule as the frame raster,
    so their pixels align with frame pixels, vectors converted from grid
    cells to output pixels of exactly this request. A pair with no derived
    motion - or an artifact predating tangents - raises
    :class:`FlowNotAvailable`: the client then falls back one honest rung
    (linear advection, then crossfade), and says so.
    """
    import numpy  # noqa: PLC0415

    if crs not in SUPPORTED_GRID_CRS:
        raise ValueError(f"crs must be one of {', '.join(SUPPORTED_GRID_CRS)}, not {crs!r}")
    if texture not in FLOW_TEXTURES:
        raise ValueError(f"texture must be one of {', '.join(FLOW_TEXTURES)}, not {texture!r}")
    south, west = float(bounds["south"]), float(bounds["west"])
    north, east = float(bounds["north"]), float(bounds["east"])
    if south >= north or west >= east:
        raise ValueError("bounds must be a south-west to north-east box")

    surface = _grid_artifact(store, spec)
    if surface is None:
        raise GridNotPublished(f"no {spec.source_id} {spec.logical_name} artifact is currently published")
    motion = next(
        (item for item in _current_artifacts(store)
         if item.source_id == spec.source_id and item.logical_name == CLOUD_MOTION_LOGICAL_NAME),
        None,
    )
    if motion is None:
        raise FlowNotAvailable(f"no derived cloud-motion artifact is published for {spec.source_id}")
    if str(motion.provenance.get("base_revision_id", "")) != str(getattr(surface, "revision_id", "")):
        raise FlowNotAvailable(
            f"the published cloud-motion artifact derives from revision "
            f"{motion.provenance.get('base_revision_id')!r}, not the current surface revision"
        )
    try:
        surface_dataset = store.open(surface)
        motion_dataset = store.open(motion)
    except Exception as error:
        raise GridUnavailable(f"a published artifact could not be read: {type(error).__name__}: {error}") from error

    import pandas  # noqa: PLC0415

    pair_from = [pandas.Timestamp(value).to_pydatetime().replace(tzinfo=UTC) for value in motion_dataset["pair_from"].values]
    pair_to = [pandas.Timestamp(value).to_pydatetime().replace(tzinfo=UTC) for value in motion_dataset["pair_to"].values]
    wanted_from = frame_from.astimezone(UTC)
    wanted_to = frame_to.astimezone(UTC)
    pair_index = next(
        (index for index, (start, end) in enumerate(zip(pair_from, pair_to)) if start == wanted_from and end == wanted_to),
        None,
    )
    if pair_index is None:
        raise FlowNotAvailable(
            f"no derived motion pair covers {wanted_from.isoformat()} -> {wanted_to.isoformat()}; "
            "motion exists only between adjacent published frames"
        )
    if texture == "tangents":
        suffixes = ("vs_u", "vs_v", "ve_u", "ve_v")
    else:
        # The blue channel is the weight the client mixes advection against a
        # crossfade on. Newer artifacts publish the display weight (support
        # AND development agreement, vetoed per pair on measured skill); older
        # ones carry only the raw consistency, which is what they mixed on, so
        # they keep serving that rather than nothing.
        weight_name = f"{spec.variable}_advect_weight"
        weight_suffix = "advect_weight" if weight_name in motion_dataset.data_vars else "confidence"
        suffixes = ("u01", "v01", weight_suffix)
    names = [f"{spec.variable}_{suffix}" for suffix in suffixes]
    if any(name not in motion_dataset.data_vars for name in names):
        raise FlowNotAvailable(
            f"the cloud-motion artifact carries no {texture} data for {spec.variable}"
            + (" (it predates the Hermite derivation)" if texture == "tangents" else "")
        )

    lat_name = "latitude" if "latitude" in surface_dataset.coords else "lat"
    lon_name = "longitude" if "longitude" in surface_dataset.coords else "lon"
    if lat_name not in surface_dataset.coords or lon_name not in surface_dataset.coords:
        raise GridUnavailable("the stored grid carries no latitude/longitude coordinates")
    lat_values = numpy.asarray(surface_dataset[lat_name].values, dtype="float64")
    lon_values = numpy.asarray(surface_dataset[lon_name].values, dtype="float64")
    if lat_values.ndim == 2:
        lat2d, lon2d = lat_values, ((lon_values + 180.0) % 360.0) - 180.0
    else:
        lon_wrapped = ((lon_values + 180.0) % 360.0) - 180.0
        lat2d, lon2d = numpy.meshgrid(lat_values, lon_wrapped, indexing="ij")

    fields = {
        suffix: numpy.asarray(motion_dataset[f"{spec.variable}_{suffix}"].isel(pair=pair_index).values, dtype="float64")
        for suffix in suffixes
    }
    if any(field.shape != lat2d.shape for field in fields.values()):
        raise GridUnavailable("the motion grid does not match the stored grid it claims to describe")

    # Which stored cell sits under each output pixel: the exact rule the frame
    # raster uses, obtained by sampling a cell-index field through it.
    index_field = numpy.arange(lat2d.size, dtype="float64").reshape(lat2d.shape)
    cache_token = (id(surface_dataset), str(getattr(surface, "revision_id", "")))
    if lat_values.ndim == 2:
        sampled_index, inside = sample_field_curvilinear(
            index_field, lat2d, lon2d, bounds=bounds, width=width, height=height, crs=crs, cache_token=cache_token,
        )
    else:
        sampled_index, inside = sample_field(index_field, lat_values, lon_values, bounds=bounds, width=width, height=height, crs=crs)
    rows, cols = numpy.unravel_index(numpy.rint(sampled_index).astype("int64"), lat2d.shape)

    from scipy.ndimage import map_coordinates  # noqa: PLC0415

    def pixel_vectors(u_cells: Any, v_cells: Any) -> tuple[Any, Any]:
        """One cell-space vector field converted to output pixels, zero outside."""
        end_rows = rows + v_cells[rows, cols]
        end_cols = cols + u_cells[rows, cols]
        end_lat = map_coordinates(lat2d, [end_rows, end_cols], order=1, mode="nearest")
        end_lon = map_coordinates(lon2d, [end_rows, end_cols], order=1, mode="nearest")
        start_lat = lat2d[rows, cols]
        start_lon = lon2d[rows, cols]
        delta_lat = end_lat - start_lat
        delta_lon = ((end_lon - start_lon + 180.0) % 360.0) - 180.0
        pixel_dx = delta_lon / (east - west) * width
        pixel_dy = _forward_pixel_y(start_lat + delta_lat, south=south, north=north, height=height, crs=crs) \
            - _forward_pixel_y(start_lat, south=south, north=north, height=height, crs=crs)
        return numpy.where(inside, pixel_dx, 0.0), numpy.where(inside, pixel_dy, 0.0)

    def quantized(component: Any, scale: float) -> Any:
        return numpy.clip(numpy.rint((component / scale * 0.5 + 0.5) * 255.0), 0, 255).astype("uint8")

    if texture == "tangents":
        start_dx, start_dy = pixel_vectors(fields["vs_u"], fields["vs_v"])
        end_dx, end_dy = pixel_vectors(fields["ve_u"], fields["ve_v"])
        scale = float(max(*(numpy.max(numpy.abs(component)) for component in (start_dx, start_dy, end_dx, end_dy)), 1e-6))
        rgba = numpy.zeros((height, width * 2, 4), dtype="uint8")
        rgba[:, :width, 0] = quantized(start_dx, scale)
        rgba[:, :width, 1] = quantized(start_dy, scale)
        rgba[:, width:, 0] = quantized(end_dx, scale)
        rgba[:, width:, 1] = quantized(end_dy, scale)
        rgba[..., 3] = 255
    else:
        pixel_dx, pixel_dy = pixel_vectors(fields["u01"], fields["v01"])
        pixel_confidence = numpy.where(inside, fields[suffixes[2]][rows, cols], 0.0)
        scale = float(max(numpy.max(numpy.abs(pixel_dx)), numpy.max(numpy.abs(pixel_dy)), 1e-6))
        rgba = numpy.zeros((height, width, 4), dtype="uint8")
        rgba[..., 0] = quantized(pixel_dx, scale)
        rgba[..., 1] = quantized(pixel_dy, scale)
        rgba[..., 2] = numpy.clip(numpy.rint(pixel_confidence * 255.0), 0, 255).astype("uint8")
        rgba[..., 3] = 255

    attrs = dict(motion_dataset.attrs or {})
    return FlowImage(
        payload=encode_png(rgba),
        content_type="image/png",
        frame_from=wanted_from,
        frame_to=wanted_to,
        scale_pixels=scale,
        crs=crs,
        source_id=spec.source_id,
        method=str(attrs.get("method", "derived motion")),
        version=str(attrs.get("derivation_version", "unversioned")),
        texture=texture,
    )


def legend_png() -> bytes:
    """The colormap as a picture: 0..100 percent, left to right.

    This is OUR ramp - the one the renderer actually applies - documented in
    :data:`COLORMAP_DOC` and served so a drawn field is never unexplained. It
    is not a provider graphic and the response headers say so. The ramp is a
    transparency ramp, so it is composited over a mid grey here - the way the
    aurora and cloud-mask legends already are - because a served legend that
    is itself transparent reads as a blank box; the compositing changes the
    backdrop, never the mapping.
    """
    import numpy  # noqa: PLC0415

    width, height = 256, 24
    percent = (numpy.arange(width, dtype="float64") / (width - 1)) * 100.0
    alpha = numpy.rint(percent * 2.55) / 255.0
    rgba = numpy.zeros((height, width, 4), dtype="uint8")
    rgba[..., 3] = 255
    composited = numpy.rint(196.0 * (1 - alpha) + 255.0 * alpha).astype("uint8")
    for channel in range(3):
        rgba[..., channel] = composited[None, :]
    return encode_png(rgba)


def rendered_grid_layers(store: Any, layer_model: Any, *, z_index: int, staleness: Any) -> tuple[list[Any], list[str]]:
    """The `/layers` entries for every stored-grid spec that is actually published.

    ``layer_model`` is the ``Layer`` pydantic model (passed in to avoid a
    circular import); ``staleness`` is the shared tolerance rule. A spec whose
    artifact is absent, unreadable or missing the variable is simply not
    offered - with a notice where something was expected and failed, silence
    where nothing is published at all.
    """
    layers: list[Any] = []
    notices: list[str] = []
    for spec in RENDERED_GRID_SPECS:
        artifact = _grid_artifact(store, spec)
        if artifact is None:
            continue
        try:
            dataset = store.open(artifact)
        except Exception as error:
            notices.append(f"{spec.layer_id}: the published {spec.source_id} artifact could not be read ({type(error).__name__}); the layer is not offered")
            continue
        if spec.variable not in dataset.data_vars:
            notices.append(f"{spec.layer_id}: the published {spec.source_id} artifact does not carry {spec.variable}; the layer is not offered")
            continue
        times = _dataset_times(dataset)
        cadence = _modal_cadence(times)
        provenance = dict(artifact.provenance or {})
        product = str(provenance.get("product", spec.source_id))
        layers.append(
            layer_model(
                id=spec.layer_id,
                title=f"{product} {spec.title_field} (rendered grid)",
                kind="raster",
                field=spec.field,
                product=product,
                units=str(dataset[spec.variable].attrs.get("units", "unknown")),
                semantics=grid_semantics(spec, provenance),
                times=times,
                cadence_seconds=cadence,
                staleness_tolerance_seconds=staleness(cadence),
                z_index=z_index,
                evidence_basis="published_artifact",
                group="rendered_grid",
                raster_available=bool(times),
                legend_available=True,
                upstream_wms_layer=None,
                upstream_endpoint=None,
            )
        )
    return layers, notices
