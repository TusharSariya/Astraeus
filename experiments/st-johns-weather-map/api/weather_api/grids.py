"""Map images rendered by this experiment from its own retrieved grids.

Everything else `/layers/{id}/raster` serves is rendered upstream by ECCC
GeoMet. The three layers here are different: no provider publishes low/middle/
high cloud-strata rasters for this region, but the worker already ingests the
NOAA GFS grids that carry them (`cloud_low` / `cloud_middle` / `cloud_high`,
the provider's own LCDC/MCDC/HCDC at its low/middle/high cloud layers), so the
image is drawn *here*, from the published artifact, under these rules:

* **Only stored values, at their native cells.** Every output pixel is the
  stored value of the single 0.25 degree cell that geographically contains it
  — pure nearest-neighbor. Nothing is interpolated, smoothed, resampled onto a
  finer grid, or extrapolated past the grid edge. The blocky look is the
  honest look.
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
import zlib
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

#: What every rendered pixel is, in words, for the response headers.
RENDER_SEMANTICS_DOC = (
    "each pixel is the stored value of the single native 0.25 deg grid cell containing it "
    "(nearest-neighbor); nothing is interpolated, smoothed or extrapolated; a transparent "
    "pixel means no stored cell or no stored value there, or a stored cover of 0 percent"
)

#: The rendering disclosed as a derivation-style statement. Drawing pixels from
#: stored numbers is presentation, but it is still this experiment's own step
#: between the artifact and the reader's eye, so it is versioned and disclosed
#: the way a derivation would be.
RENDER_DERIVATION = (
    "weather_api.grids: nearest-neighbor rasterization of the stored grid at its native "
    "0.25 deg cells; colormap " + COLORMAP_DOC
)
RENDER_DERIVATION_VERSION = "rendered-grid-nearest-v1"


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
)

_SPEC_BY_ID = {spec.layer_id: spec for spec in RENDERED_GRID_SPECS}


def rendered_grid_spec(layer_id: str) -> RenderedGridSpec | None:
    return _SPEC_BY_ID.get(layer_id)


def grid_semantics(spec: RenderedGridSpec) -> str:
    """What the layer says about itself, verbatim, in ``/layers``."""
    return (
        f"rendered by this experiment from retrieved NOAA GFS GRIB2 fields: the provider-declared "
        f"{spec.title_field} ({spec.variable} at the provider's own {spec.provider_level}), "
        "0.25 deg native resolution, displayed nearest-neighbor at the native cells and never "
        "smoothed - the blocky cells are the stored data. Values and times are read from the "
        "published noaa-gfs artifact; no pixel is interpolated, extrapolated or substituted. "
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
    raw = b"".join(b"\x00" + data[row].tobytes() for row in range(height))

    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw, 6))
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


def rasterize(
    values: Any,
    latitudes: Any,
    longitudes: Any,
    *,
    bounds: Mapping[str, float],
    width: int,
    height: int,
    crs: str = "EPSG:4326",
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

    field = numpy.asarray(values, dtype="float64")
    if field.ndim != 2:
        raise GridUnavailable("the stored variable is not a 2-D (latitude, longitude) field")

    # Pixel-centre longitudes are linear in both CRS (mercator x is linear in
    # longitude). Latitudes are linear in EPSG:4326 and linear in mercator y
    # for EPSG:3857. Row 0 is the top of the image (north).
    column_lon = west + (numpy.arange(width, dtype="float64") + 0.5) * (east - west) / width
    if crs == "EPSG:3857":
        if abs(south) > WEB_MERCATOR_MAX_LATITUDE or abs(north) > WEB_MERCATOR_MAX_LATITUDE:
            raise ValueError(f"latitude bounds are outside EPSG:3857's defined range (+/-{WEB_MERCATOR_MAX_LATITUDE})")
        y_north, y_south = float(_mercator_y(north)), float(_mercator_y(south))
        row_y = y_north - (numpy.arange(height, dtype="float64") + 0.5) * (y_north - y_south) / height
        row_lat = numpy.degrees(numpy.arctan(numpy.sinh(row_y / WEB_MERCATOR_RADIUS_M)))
    else:
        row_lat = north - (numpy.arange(height, dtype="float64") + 0.5) * (north - south) / height

    row_index = _cell_indices(row_lat, latitudes)
    column_index = _cell_indices(column_lon, longitudes)

    inside = (row_index[:, None] >= 0) & (column_index[None, :] >= 0)
    safe_rows = numpy.where(row_index < 0, 0, row_index)
    safe_columns = numpy.where(column_index < 0, 0, column_index)
    sampled = field[safe_rows[:, None], safe_columns[None, :]]

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


def _grid_artifact(store: Any, spec: RenderedGridSpec) -> Any | None:
    for artifact in store.current():
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
            "X-Weather-Render-Semantics": RENDER_SEMANTICS_DOC,
            "X-Weather-Colormap": COLORMAP_DOC,
            "X-Weather-Derivation": RENDER_DERIVATION,
            "X-Weather-Derivation-Version": RENDER_DERIVATION_VERSION,
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

    time_name = _time_name(dataset)
    variable = dataset[spec.variable]
    import numpy  # noqa: PLC0415

    frame = variable.sel({time_name: numpy.datetime64(nearest.replace(tzinfo=None), "ns")})
    lat_name = "latitude" if "latitude" in dataset.coords else "lat"
    lon_name = "longitude" if "longitude" in dataset.coords else "lon"
    if lat_name not in dataset.coords or lon_name not in dataset.coords:
        raise GridUnavailable("the stored grid carries no latitude/longitude coordinates")
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
    )
    licence, attribution = _registry_terms(spec.source_id)
    provenance = dict(artifact.provenance or {})
    return RenderedGridImage(
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
    )


def legend_png() -> bytes:
    """The colormap as a picture: 0..100 percent, left to right.

    This is OUR ramp - the one the renderer actually applies - documented in
    :data:`COLORMAP_DOC` and served so a drawn field is never unexplained. It
    is not a provider graphic and the response headers say so.
    """
    import numpy  # noqa: PLC0415

    width, height = 256, 24
    percent = (numpy.arange(width, dtype="float64") / (width - 1)) * 100.0
    alpha = numpy.rint(percent * 2.55).astype("uint8")
    rgba = numpy.zeros((height, width, 4), dtype="uint8")
    rgba[..., 0:3] = 255
    rgba[..., 3] = alpha[None, :]
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
                semantics=grid_semantics(spec),
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
