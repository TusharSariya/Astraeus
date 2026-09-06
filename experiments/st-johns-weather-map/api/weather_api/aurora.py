"""The aurora-oval layer, rendered from the published OVATION probability grid.

NOAA SWPC's OVATION nowcast is a *model* grid, not an observation, and the one
thing this layer must never do is dress it up as either a photograph of the sky
or a promise of aurora. Rules, mirroring ``weather_api.satellite``:

* **Only stored values, nearest-neighbor, at the stored cells.** The artifact
  is the OVATION grid exactly as retrieved (percent, 1-degree cells, cropped
  to the Atlantic context box); nothing here interpolates, smooths or invents
  an edge.
* **Times are the file's own.** The single offered frame is the payload's own
  Forecast Time, stored by the adapter; a requested instant with no stored
  frame within tolerance is a 422, never a silently substituted frame.
* **Transparent means below the disclosed threshold.** Cells under
  :data:`THRESHOLD_PERCENT` are fully transparent and the legend says so; the
  colormap is identical day and night.
* **A feed gap fails closed.** A grid older than the staleness tolerance makes
  the layer unavailable with a notice — a missing feed is never rendered as an
  absence of aurora.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from . import grids
from .grids import FrameNotStored, GridNotPublished, GridUnavailable  # noqa: F401  (shared error contract)

UTC = timezone.utc
LOGGER = logging.getLogger(__name__)

SOURCE_ID = "noaa-swpc-ovation"
LOGICAL_NAME = "aurora_grid"
LAYER_ID = "noaa-swpc-aurora-oval"
VARIABLE = "aurora_probability"
TITLE = "Aurora probability (OVATION model nowcast)"
UNITS = "percent"

#: The cadence SWPC publishes the OVATION file at, used when fewer than two
#: frames are stored (the artifact normally carries exactly one Forecast Time).
NOMINAL_CADENCE_SECONDS = 600

#: The unknown-cadence fallback only. The tolerance actually published is one
#: native interval derived from the stored instants through the shared rule
#: (``grids.frame_tolerance_seconds``); this constant answers only when the
#: artifact carries a single Forecast Time and no modal gap can be measured, in
#: which case it is the OVATION grid's own 10-minute interval - one missed
#: update, not six.
STALENESS_TOLERANCE_SECONDS = NOMINAL_CADENCE_SECONDS

#: Below this stored probability a cell is fully transparent. Disclosed in the
#: colormap doc, the legend caption and the layer semantics.
THRESHOLD_PERCENT = 2.0

#: The ramp endpoints (green at the threshold, red at 100 percent) and the
#: alpha range. Alpha never reaches opaque so the basemap stays readable.
GREEN_RGB = (0, 176, 80)
RED_RGB = (255, 40, 40)
ALPHA_MIN = 64
ALPHA_MAX = 217

COLORMAP_DOC = (
    "OVATION probability percent -> fully transparent below 2 percent (the disclosed "
    "threshold), then a linear green (RGB 0,176,80) to red (RGB 255,40,40) ramp from 2 to "
    "100 percent with alpha scaled linearly from 64 to 217 over the same range; cells with "
    "no stored value are fully transparent; identical at every hour, day and night; "
    "colormap-version aurora-green-red-v1"
)

RENDER_SEMANTICS_DOC = (
    "each pixel is the stored OVATION probability of the single 1-degree grid cell "
    "containing it (nearest-neighbor); nothing is interpolated, smoothed or extrapolated; "
    "a transparent pixel means no stored cell, no stored value, or a stored probability "
    "below the disclosed 2 percent threshold"
)

RENDER_DERIVATION = (
    "weather_api.aurora: nearest-neighbor rasterization of the published OVATION grid at "
    "its native 1-degree cells; colormap " + COLORMAP_DOC
)
RENDER_DERIVATION_VERSION = "aurora-oval-v1"

#: The frame is the OVATION file's own Forecast Time: a model validity instant.
TIME_SEMANTICS = "valid at the instant in X-Weather-Valid-Time (the OVATION file's own Forecast Time)"

MODEL_SENTENCE = (
    "Values are OVATION model probabilities of visible aurora - a nowcast roughly 30-40 "
    "minutes past its observation instant, not an observation and not a forecast skill claim."
)
GUIDANCE_SENTENCE = (
    "NOAA's own viewline guidance: at St. John's geomagnetic latitude (~53-54 N) aurora is "
    "typically photographable from about Kp 4-5."
)

LEGEND_CAPTION = (
    "OVATION model nowcast (~30-40 minute horizon): probability of visible aurora per "
    "1-degree cell, in percent, as retrieved from NOAA SWPC. Cells below the 2 percent "
    "threshold are fully transparent. " + GUIDANCE_SENTENCE + " "
    "Rendered by this experiment from the stored grid; the ramp is presentation only and "
    "identical day and night."
)


def semantics() -> str:
    """What the layer says about itself, verbatim, in ``/layers``."""
    return (
        "rendered by this experiment from the stored NOAA SWPC OVATION aurora nowcast grid "
        "(1-degree cells cropped to the Atlantic context box), displayed nearest-neighbor at "
        "the stored cells and never smoothed, valid at the file's own Forecast Time. "
        + MODEL_SENTENCE + " " + GUIDANCE_SENTENCE + " "
        "Cells below the 2 percent threshold are fully transparent; a stale or missing grid "
        "makes the layer unavailable with a notice, never an absence of aurora. Colormap "
        "(presentation only): " + COLORMAP_DOC + "."
    )


def claims(artifact: Any) -> bool:
    """True for the published artifact this module renders; the generic
    artifact-derived listing must skip it so it is offered exactly once."""
    return (
        getattr(artifact, "source_id", None) == SOURCE_ID
        and getattr(artifact, "logical_name", None) == LOGICAL_NAME
    )


def _artifact(store: Any) -> Any | None:
    for artifact in store.current():
        if claims(artifact):
            return artifact
    return None


def colorize(probability: Any, inside: Any) -> Any:
    """RGBA for a sampled probability array, exactly as the colormap doc says.

    ``inside`` is the in-grid mask from :func:`grids.sample_field`; pixels
    outside the stored grid, without a stored value, or below the disclosed
    threshold are fully transparent.
    """
    import numpy  # noqa: PLC0415

    values = numpy.asarray(probability, dtype="float64")
    height, width = values.shape
    rgba = numpy.zeros((height, width, 4), dtype="uint8")

    drawn = inside & numpy.isfinite(values) & (values >= THRESHOLD_PERCENT)
    # NaN cells are never drawn; zero them before the cast so the arithmetic
    # below is defined everywhere (the mask keeps them transparent regardless).
    filled = numpy.where(numpy.isfinite(values), values, 0.0)
    scaled = numpy.clip((filled - THRESHOLD_PERCENT) / (100.0 - THRESHOLD_PERCENT), 0.0, 1.0)
    for channel in range(3):
        ramp = GREEN_RGB[channel] + scaled * (RED_RGB[channel] - GREEN_RGB[channel])
        rgba[..., channel][drawn] = numpy.rint(ramp).astype("uint8")[drawn]
    alpha = numpy.rint(ALPHA_MIN + scaled * (ALPHA_MAX - ALPHA_MIN)).astype("uint8")
    rgba[..., 3][drawn] = alpha[drawn]
    return rgba


@dataclass(frozen=True)
class AuroraImage:
    """One rendered aurora frame plus everything needed to say what it is."""

    payload: bytes
    content_type: str
    valid_time: datetime
    run_time: datetime | None
    crs: str
    product: str
    licence: str
    attribution: str

    @property
    def byte_size(self) -> int:
        return len(self.payload)

    def headers(self) -> dict[str, str]:
        return {
            "Cache-Control": "public, max-age=60",
            "X-Weather-Layer-Id": LAYER_ID,
            "X-Weather-Data-Mode": "live",
            "X-Weather-Operational": "false",
            "X-Weather-Evidence-Basis": "published_artifact",
            "X-Weather-Image-Basis": "rendered_grid",
            "X-Weather-Retrieval-Status": "retrieved",
            "X-Weather-Render-Semantics": RENDER_SEMANTICS_DOC,
            "X-Weather-Colormap": COLORMAP_DOC,
            "X-Weather-Derivation": RENDER_DERIVATION,
            "X-Weather-Derivation-Version": RENDER_DERIVATION_VERSION,
            "X-Weather-Source-Id": SOURCE_ID,
            "X-Weather-Product": self.product,
            "X-Weather-Units": UNITS,
            "X-Weather-Crs": self.crs,
            "X-Weather-Valid-Time": self.valid_time.isoformat(),
            "X-Weather-Time-Semantics": TIME_SEMANTICS,
            "X-Weather-Reference-Time": self.run_time.isoformat() if self.run_time else "none",
            "X-Weather-Byte-Size": str(self.byte_size),
            "X-Weather-Licence": self.licence,
            "X-Weather-Attribution": self.attribution,
        }


def _times_and_cadence(dataset: Any) -> tuple[list[datetime], int]:
    times = grids._dataset_times(dataset)
    cadence = grids._modal_cadence(times) or NOMINAL_CADENCE_SECONDS
    return times, cadence


def render_aurora(
    store: Any,
    *,
    bounds: Mapping[str, float],
    width: int,
    height: int,
    crs: str = "EPSG:4326",
    valid_time: datetime | None = None,
) -> AuroraImage:
    """Render one stored frame, or raise naming exactly what is missing."""
    import numpy  # noqa: PLC0415

    artifact = _artifact(store)
    if artifact is None:
        raise GridNotPublished(f"no {SOURCE_ID} {LOGICAL_NAME} artifact is currently published")
    try:
        dataset = store.open(artifact)
    except Exception as error:
        raise GridUnavailable(f"the published artifact could not be read: {type(error).__name__}: {error}") from error
    if VARIABLE not in dataset.data_vars:
        raise GridNotPublished(f"the published {SOURCE_ID} artifact does not carry {VARIABLE}")

    times, cadence = _times_and_cadence(dataset)
    if not times:
        raise GridNotPublished(f"the published {SOURCE_ID} artifact carries no forecast instant")
    moment = (valid_time or datetime.now(UTC)).astimezone(UTC)
    nearest = min(times, key=lambda stamp: abs((stamp - moment).total_seconds()))
    tolerance = grids.frame_tolerance_seconds(cadence)
    distance = abs((nearest - moment).total_seconds())
    if distance > tolerance:
        raise FrameNotStored(
            f"no stored frame within {tolerance} s of {moment.isoformat()}; the nearest is "
            f"{nearest.isoformat()} ({int(distance)} s away). Frames are only the forecast instants that were ingested."
        )

    time_name = grids._time_name(dataset)
    frame = dataset[VARIABLE].sel({time_name: numpy.datetime64(nearest.replace(tzinfo=None), "ns")})
    if tuple(frame.dims) != ("latitude", "longitude"):
        frame = frame.transpose("latitude", "longitude")

    sampled, inside = grids.sample_field(
        frame.values,
        dataset["latitude"].values,
        dataset["longitude"].values,
        bounds=bounds,
        width=width,
        height=height,
        crs=crs,
    )
    rgba = colorize(sampled, inside)
    licence, attribution = grids._registry_terms(SOURCE_ID)
    provenance = dict(artifact.provenance or {})
    return AuroraImage(
        payload=grids.encode_png(rgba),
        content_type="image/png",
        valid_time=nearest,
        run_time=artifact.run_time,
        crs=crs,
        product=str(provenance.get("product", SOURCE_ID)),
        licence=licence,
        attribution=attribution,
    )


def legend_png() -> bytes:
    """The colormap as a picture: the transparent below-threshold segment over
    a checkered backdrop, then the green-to-red ramp from 2 to 100 percent.

    This is OUR ramp - the exact mapping the renderer applies - so a drawn
    field is never unexplained. It is not a provider graphic and the headers
    say so.
    """
    import numpy  # noqa: PLC0415

    width, height, threshold_w = 256, 24, 32
    rgba = numpy.zeros((height, width, 4), dtype="uint8")
    rgba[..., 3] = 255

    # Below-threshold segment: genuinely transparent in the layer, shown here
    # over a visible checker so the most important state is not invisible.
    yy, xx = numpy.mgrid[0:height, 0:threshold_w]
    checker = (((yy // 8) + (xx // 8)) % 2).astype("float64")
    backdrop = (176.0 + checker * 40.0).astype("uint8")
    for channel in range(3):
        rgba[:, :threshold_w, channel] = backdrop

    ramp_w = width - threshold_w
    scaled = numpy.arange(ramp_w, dtype="float64") / (ramp_w - 1)
    alpha = numpy.rint(ALPHA_MIN + scaled * (ALPHA_MAX - ALPHA_MIN)) / 255.0
    for channel in range(3):
        colour = GREEN_RGB[channel] + scaled * (RED_RGB[channel] - GREEN_RGB[channel])
        # Composite the alpha-scaled ramp over a mid grey so the served legend
        # shows what the reader will actually see over a basemap.
        rgba[:, threshold_w:, channel] = numpy.rint(196.0 * (1 - alpha) + colour * alpha).astype("uint8")[None, :]
    return grids.encode_png(rgba)


def legend_headers() -> dict[str, str]:
    return {
        "Cache-Control": "public, max-age=3600",
        "X-Weather-Layer-Id": LAYER_ID,
        "X-Weather-Operational": "false",
        "X-Weather-Image-Basis": "rendered_grid",
        "X-Weather-Legend-Basis": "renderer_colormap",
        "X-Weather-Colormap": COLORMAP_DOC,
        "X-Weather-Legend-Semantics": LEGEND_CAPTION,
    }


def aurora_layers(store: Any, layer_model: Any, *, z_index: int, now: datetime | None = None) -> tuple[list[Any], list[str]]:
    """The `/layers` entry for the aurora layer, or a notice for its absence.

    Fail-closed both ways: an absent artifact removes the layer WITH a notice
    naming the missing feed, and a grid older than the staleness tolerance is
    not offered — a feed gap is never rendered as absence of aurora.
    """
    moment = (now or datetime.now(UTC)).astimezone(UTC)
    artifact = _artifact(store)
    if artifact is None:
        return [], [
            f"{LAYER_ID}: no {SOURCE_ID} {LOGICAL_NAME} artifact is currently published; the aurora layer "
            "is not offered. A missing feed is never rendered as absence of aurora."
        ]
    try:
        dataset = store.open(artifact)
    except Exception as error:
        return [], [f"{LAYER_ID}: the published {SOURCE_ID} artifact could not be read ({type(error).__name__}); the layer is not offered"]
    if VARIABLE not in dataset.data_vars:
        return [], [f"{LAYER_ID}: the published {SOURCE_ID} artifact does not carry {VARIABLE}; the layer is not offered"]
    times, cadence = _times_and_cadence(dataset)
    if not times:
        return [], [f"{LAYER_ID}: the published artifact carries no forecast instant; the layer is not offered"]
    tolerance = grids.frame_tolerance_seconds(cadence)
    age = (moment - max(times)).total_seconds()
    if age > tolerance:
        return [], [
            f"{LAYER_ID}: the newest stored OVATION forecast instant is {int(age)} s old, beyond the "
            f"{tolerance} s staleness tolerance; the layer is unavailable rather than "
            "showing an old nowcast as current. A feed gap is never rendered as absence of aurora."
        ]
    provenance = dict(artifact.provenance or {})
    layer = layer_model(
        id=LAYER_ID,
        title=TITLE,
        kind="raster",
        field=VARIABLE,
        product=str(provenance.get("product", SOURCE_ID)),
        units=UNITS,
        semantics=semantics(),
        times=times,
        cadence_seconds=grids._modal_cadence(times),
        staleness_tolerance_seconds=tolerance,
        z_index=z_index,
        evidence_basis="published_artifact",
        group="rendered_grid",
        raster_available=True,
        legend_available=True,
        upstream_wms_layer=None,
        upstream_endpoint=None,
    )
    return [layer], []
