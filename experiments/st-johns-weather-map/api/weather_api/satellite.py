"""The GOES-19 observed-clouds layer, rendered from the published cloud-mask artifact.

The four proxied GOES-East composites are provider-rendered RGB pictures whose
look changes completely at the day/night terminator. This layer is different:
it draws NOAA's Enterprise Cloud Mask *classification* (ABI-L2-ACMF, ingested
and regridded by the worker) with one palette at every hour, so midnight reads
exactly like noon. It stands BESIDE the proxies in the same satellite group so
the processed and unprocessed views can be compared at the same instant.

Rules, mirroring ``weather_api.grids``:

* **Only stored values, nearest-neighbor, at the stored cells.** The artifact
  is already regridded no finer than the instrument's local footprint; nothing
  here interpolates, smooths, or invents an edge.
* **Opacity encodes detection confidence, never cloud thickness.** Clear is
  fully transparent; probably-clear is faint white; probably-cloudy medium
  white; cloudy white scaled by the stored cloud probability, capped below
  opaque so the basemap stays readable.
* **Invalid is never clear.** A quality-flagged or unobserved cell inside the
  grid renders as a distinct dim non-white state — including the cells a
  parallax-corrected cloud vacated, which the satellite could not see.
* **Frames are observed scans only.** The offered times are exactly the
  ingested scan times; beyond half a cadence the answer is 422; beyond the
  staleness tolerance the layer reports itself unavailable. A feed gap is
  never rendered, and in particular never rendered as clear sky.
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

SOURCE_ID = "noaa-goes-east"
LOGICAL_NAME = "cloud_mask"
LAYER_ID = "noaa-goes19-cloud-mask"
TITLE = "GOES-19 observed clouds (cloud mask)"

#: The scan cadence NOAA actually publishes at (Full Disk, mode 6), used when
#: fewer than two frames are stored; with two or more the modal gap wins.
NOMINAL_CADENCE_SECONDS = 600

#: Beyond this the layer declares itself unavailable rather than showing an
#: old scan as current: three missed scans.
STALENESS_TOLERANCE_SECONDS = 1800

INVALID_CLASS = 255

#: The five states, exactly as drawn. Alpha 0-255.
ALPHA_PROBABLY_CLEAR = 31    # ~0.12: uncertainty is not silently shown as clear
ALPHA_PROBABLY_CLOUDY = 115  # ~0.45
ALPHA_CLOUDY_MIN = 140       # ~0.55 at stored probability 0
ALPHA_CLOUDY_MAX = 217       # ~0.85 at stored probability 1; never opaque
INVALID_RGBA = (128, 96, 128, 128)  # dim violet-grey: visibly not clear, not white

COLORMAP_DOC = (
    "cloud-mask class -> neutral white whose ALPHA ENCODES DETECTION CONFIDENCE, "
    "not cloud thickness: clear fully transparent; probably_clear white alpha 31; "
    "probably_cloudy white alpha 115; cloudy white alpha 140 + round(stored cloud "
    "probability * 77) capped at 217 so the basemap stays readable; invalid or "
    "unobserved cells RGBA (128,96,128,128), never transparent and never white; "
    "identical at every hour, day and night; colormap-version goes-cloud-mask-alpha-v1"
)

RENDER_SEMANTICS_DOC = (
    "each pixel is the stored NOAA Enterprise Cloud Mask value of the single grid cell "
    "containing it (nearest-neighbor; the artifact grid is itself no finer than the "
    "instrument's local footprint); nothing is interpolated, smoothed or extrapolated; "
    "a transparent pixel inside the grid is a retrieved 'clear' classification, and an "
    "invalid/unobserved cell is drawn as a distinct dim state, never as clear"
)

RENDER_DERIVATION = (
    "weather_api.satellite: nearest-neighbor rasterization of the published GOES-19 "
    "cloud-mask grid; colormap " + COLORMAP_DOC
)
RENDER_DERIVATION_VERSION = "satellite-cloud-mask-v1"

#: Observed imagery: the frame is the scan instant, not a forecast validity.
TIME_SEMANTICS = "observed at the instant in X-Weather-Valid-Time"

ACCURACY_SENTENCE = (
    "NOAA's published validation for this product is roughly 90% balanced detection "
    "accuracy by day and 88% at night, weaker for very thin cirrus; these are the "
    "provider's figures, not locally measured. This layer is satellite cloud "
    "probability, never a definitive statement of clear sky."
)
PARALLAX_SENTENCE = (
    "cloudy pixels were parallax-corrected toward the sub-satellite point using the "
    "GOES-19 cloud-top height product, which carries NOAA Provisional maturity; cloudy "
    "pixels without a valid height keep their apparent position (displaced up to tens "
    "of km away from the sub-satellite point) and carry parallax_uncorrected=1"
)

LEGEND_CAPTION = (
    "Opacity encodes cloud-DETECTION CONFIDENCE, not cloud thickness. The clear swatch "
    "is genuinely transparent and is shown over a checkered backdrop. "
    + ACCURACY_SENTENCE + " " + PARALLAX_SENTENCE + ". "
    "Values are NOAA Enterprise Cloud Mask classifications regridded nearest-neighbour "
    "from the geostationary fixed grid, rendered by this experiment."
)


def semantics() -> str:
    """What the layer says about itself, verbatim, in ``/layers``."""
    return (
        "rendered by this experiment from the retrieved NOAA GOES-19 Enterprise Cloud Mask "
        "(ABI-L2-ACMF Full Disk, 10-minute scans): per-cell cloud classification and cloud "
        "probability, regridded nearest-neighbour from the geostationary fixed grid no finer "
        "than the instrument's local footprint, displayed with one palette at every hour so "
        "day and night read identically. " + ACCURACY_SENTENCE + " " + PARALLAX_SENTENCE + ". "
        "An invalid or unobserved cell is drawn as a distinct dim state, never as clear; a "
        "feed gap makes the layer unavailable, never a clear sky. Colormap (presentation "
        "only): " + COLORMAP_DOC + "."
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


def colorize(cloud_class: Any, probability: Any, inside: Any) -> Any:
    """RGBA for sampled class/probability arrays. The five states, nothing else.

    ``inside`` is the in-grid mask from :func:`grids.sample_field`; a pixel
    outside the stored grid is fully transparent (the layer simply ends
    there), while an in-grid invalid/unobserved cell is the dim state.
    """
    import numpy  # noqa: PLC0415

    classes = numpy.asarray(cloud_class, dtype="float64")
    prob = numpy.asarray(probability, dtype="float64")
    height, width = classes.shape
    rgba = numpy.zeros((height, width, 4), dtype="uint8")

    invalid = inside & (~numpy.isfinite(classes) | (classes == INVALID_CLASS))
    probably_clear = inside & (classes == 1)
    probably_cloudy = inside & (classes == 2)
    cloudy = inside & (classes == 3)

    for channel, value in enumerate(INVALID_RGBA):
        rgba[..., channel][invalid] = value
    for mask, alpha in ((probably_clear, ALPHA_PROBABLY_CLEAR), (probably_cloudy, ALPHA_PROBABLY_CLOUDY)):
        rgba[..., 0:3][mask] = 255
        rgba[..., 3][mask] = alpha
    # Cloudy alpha scales with the stored probability; a cloudy cell whose
    # probability did not decode is drawn at the scale's midpoint, not hidden.
    scaled = numpy.where(numpy.isfinite(prob), numpy.clip(prob, 0.0, 1.0), 0.5)
    cloudy_alpha = numpy.rint(ALPHA_CLOUDY_MIN + scaled * (ALPHA_CLOUDY_MAX - ALPHA_CLOUDY_MIN)).astype("uint8")
    rgba[..., 0:3][cloudy] = 255
    rgba[..., 3][cloudy] = cloudy_alpha[cloudy]
    return rgba


@dataclass(frozen=True)
class SatelliteImage:
    """One rendered cloud-mask frame plus everything needed to say what it is."""

    payload: bytes
    content_type: str
    valid_time: datetime
    crs: str
    product: str
    licence: str
    attribution: str
    cloud_top_height_maturity: str

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
            "X-Weather-Units": "cloud-mask class / probability 0-1",
            "X-Weather-Crs": self.crs,
            "X-Weather-Valid-Time": self.valid_time.isoformat(),
            "X-Weather-Time-Semantics": TIME_SEMANTICS,
            "X-Weather-Reference-Time": self.valid_time.isoformat(),
            "X-Weather-Cloud-Top-Height-Maturity": self.cloud_top_height_maturity,
            "X-Weather-Byte-Size": str(self.byte_size),
            "X-Weather-Licence": self.licence,
            "X-Weather-Attribution": self.attribution,
        }


def _times_and_cadence(dataset: Any) -> tuple[list[datetime], int]:
    times = grids._dataset_times(dataset)
    cadence = grids._modal_cadence(times) or NOMINAL_CADENCE_SECONDS
    return times, cadence


def render_satellite(
    store: Any,
    *,
    bounds: Mapping[str, float],
    width: int,
    height: int,
    crs: str = "EPSG:4326",
    valid_time: datetime | None = None,
) -> SatelliteImage:
    """Render one stored scan, or raise naming exactly what is missing."""
    import numpy  # noqa: PLC0415

    artifact = _artifact(store)
    if artifact is None:
        raise GridNotPublished(f"no {SOURCE_ID} {LOGICAL_NAME} artifact is currently published")
    try:
        dataset = store.open(artifact)
    except Exception as error:
        raise GridUnavailable(f"the published artifact could not be read: {type(error).__name__}: {error}") from error
    for name in ("cloud_class", "cloud_probability"):
        if name not in dataset.data_vars:
            raise GridNotPublished(f"the published {SOURCE_ID} artifact does not carry {name}")

    times, cadence = _times_and_cadence(dataset)
    if not times:
        raise GridNotPublished(f"the published {SOURCE_ID} artifact carries no scan times")
    moment = (valid_time or datetime.now(UTC)).astimezone(UTC)
    nearest = min(times, key=lambda stamp: abs((stamp - moment).total_seconds()))
    tolerance = grids.frame_tolerance_seconds(cadence)
    distance = abs((nearest - moment).total_seconds())
    if distance > tolerance:
        raise FrameNotStored(
            f"no stored scan within {tolerance} s of {moment.isoformat()}; the nearest is "
            f"{nearest.isoformat()} ({int(distance)} s away). Frames are only the scans that were ingested."
        )

    time_name = grids._time_name(dataset)
    selector = {time_name: numpy.datetime64(nearest.replace(tzinfo=None), "ns")}
    classes = dataset["cloud_class"].sel(selector)
    probability = dataset["cloud_probability"].sel(selector)
    if tuple(classes.dims) != ("latitude", "longitude"):
        classes = classes.transpose("latitude", "longitude")
        probability = probability.transpose("latitude", "longitude")

    latitudes = dataset["latitude"].values
    longitudes = dataset["longitude"].values
    sampled_class, inside = grids.sample_field(
        classes.values, latitudes, longitudes, bounds=bounds, width=width, height=height, crs=crs
    )
    sampled_prob, _ = grids.sample_field(
        probability.values, latitudes, longitudes, bounds=bounds, width=width, height=height, crs=crs
    )
    rgba = colorize(sampled_class, sampled_prob, inside)
    licence, attribution = grids._registry_terms(SOURCE_ID)
    provenance = dict(artifact.provenance or {})
    return SatelliteImage(
        payload=grids.encode_png(rgba),
        content_type="image/png",
        valid_time=nearest,
        crs=crs,
        product=str(provenance.get("product", SOURCE_ID)),
        licence=licence,
        attribution=attribution,
        cloud_top_height_maturity=str(provenance.get("cloud_top_height_maturity", "NOAA Provisional")),
    )


def legend_png() -> bytes:
    """The five states as swatches over a checkered backdrop.

    The checker matters: the clear state is genuinely transparent, and an
    invisible swatch would hide the most important row of the legend. The
    caption (served in the headers) explains that opacity is confidence.
    """
    import numpy  # noqa: PLC0415

    swatch_w, height = 52, 26
    states = [
        (0, 0, 0, 0),  # clear: fully transparent
        (255, 255, 255, ALPHA_PROBABLY_CLEAR),
        (255, 255, 255, ALPHA_PROBABLY_CLOUDY),
        (255, 255, 255, (ALPHA_CLOUDY_MIN + ALPHA_CLOUDY_MAX) // 2),
        INVALID_RGBA,
    ]
    width = swatch_w * len(states)
    # Checkered backdrop, 8 px squares, two greys.
    yy, xx = numpy.mgrid[0:height, 0:width]
    checker = (((yy // 8) + (xx // 8)) % 2).astype("float64")
    backdrop = 176.0 + checker * 40.0
    rgba = numpy.zeros((height, width, 4), dtype="uint8")
    for index, (red, green, blue, alpha) in enumerate(states):
        sl = slice(index * swatch_w, (index + 1) * swatch_w)
        opacity = alpha / 255.0
        for channel, value in enumerate((red, green, blue)):
            rgba[:, sl, channel] = numpy.rint(backdrop[:, sl] * (1 - opacity) + value * opacity).astype("uint8")
        rgba[:, sl, 3] = 255
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


def satellite_layers(store: Any, layer_model: Any, *, z_index: int, now: datetime | None = None) -> tuple[list[Any], list[str]]:
    """The `/layers` entry for the cloud-mask layer, or a notice for its absence.

    Fail-closed staleness: when the newest stored scan is older than the
    declared tolerance the layer is NOT offered, with a notice saying so — an
    old scan shown as current would misdate the sky, and a silent omission
    would be indistinguishable from "never existed".
    """
    moment = (now or datetime.now(UTC)).astimezone(UTC)
    artifact = _artifact(store)
    if artifact is None:
        return [], []
    try:
        dataset = store.open(artifact)
    except Exception as error:
        return [], [f"{LAYER_ID}: the published {SOURCE_ID} artifact could not be read ({type(error).__name__}); the layer is not offered"]
    missing = [name for name in ("cloud_class", "cloud_probability") if name not in dataset.data_vars]
    if missing:
        return [], [f"{LAYER_ID}: the published {SOURCE_ID} artifact does not carry {', '.join(missing)}; the layer is not offered"]
    times, cadence = _times_and_cadence(dataset)
    times = [stamp for stamp in times if stamp <= moment]  # observed scans only, never a forward frame
    if not times:
        return [], [f"{LAYER_ID}: the published artifact carries no past scan; the layer is not offered"]
    age = (moment - max(times)).total_seconds()
    if age > STALENESS_TOLERANCE_SECONDS:
        return [], [
            f"{LAYER_ID}: the newest stored scan is {int(age)} s old, beyond the {STALENESS_TOLERANCE_SECONDS} s "
            "staleness tolerance; the layer is unavailable rather than showing an old scan as current. "
            "A feed gap is never rendered as clear sky."
        ]
    provenance = dict(artifact.provenance or {})
    layer = layer_model(
        id=LAYER_ID,
        title=TITLE,
        kind="raster",
        field="cloud_mask",
        product=str(provenance.get("product", SOURCE_ID)),
        units="cloud-mask class / probability 0-1",
        semantics=semantics(),
        times=times,
        cadence_seconds=cadence,
        staleness_tolerance_seconds=STALENESS_TOLERANCE_SECONDS,
        z_index=z_index,
        evidence_basis="published_artifact",
        group="satellite",
        raster_available=True,
        legend_available=True,
        upstream_wms_layer=None,
        upstream_endpoint=None,
    )
    return [layer], []
