"""ECCC GeoMet (``geo.weather.gc.ca/geomet``) OGC client and adapter family.

GeoMet exposes ECCC's model, radar, lightning, hazard and air-quality output
through one credential-free OGC endpoint whose ``GetFeatureInfo`` response
already carries what provenance needs — the value, the valid time, the run time
(``dim_reference_time``), the units (inside the brackets of ``title_en``) and
the *actual* grid coordinate that was sampled.

Three properties of the service shape this module and are easy to get wrong:

* ``GetFeatureInfo`` answers for exactly **one pixel at one time**. There is no
  TIME range form and no multi-layer form. Every value costs one polite
  request, which is why the sample geometry here is a declared, bounded set
  of points and boxes rather than a dense grid. A dense field belongs to GRIB,
  not to WMS.
* A ``TIME`` the layer does not advertise is refused with ``NoMatch``, verified
  live. :meth:`TimeExtent.nearest` therefore refuses client-side rather than
  letting the service fall back to the layer default and attach a valid time
  the value does not have.
* **Radar answers ``{"value": 0, "class": "Undetected"}``** where there is no
  echo, verified live on 2026-08-30. That zero is not a precipitation rate: it
  is the mosaic saying it detected nothing. It is recorded as an absent rate
  plus an explicit ``radar_echo`` flag, never as ``0 mm/h``. Likewise an empty
  ``features`` array — and the bare ``{}`` the lightning layer returns — is a
  real answer meaning *no value here*, and is recorded as absence.

**Registered scope.** ``eccc-hrdps`` and ``eccc-rdps`` belong to
``ingest.adapters.eccc_datamart``: native GRIB2 gives strictly stronger
provenance for a gridded forecast field (real run time from the file's own
stamp, native units, native CRS, real lead hours, a dense field), whereas a
gridded field over ``GetFeatureInfo`` costs hundreds of requests and takes its
provenance from a rendering service rather than from the source GRIB. This
module therefore registers only the four ids nothing else claims: radar,
lightning, CAP alerts and AQHI. The HRDPS/RDPS classes are kept as a working
fallback and are registered only by flipping :data:`MODEL_SOURCE_OWNER`.

Layer identifiers, titles, units and time extents used here were read back from
the live service on 2026-08-30; ``docs/geomet-layers.md`` is the evidence trail,
including the candidates that were rejected and why.
"""

from __future__ import annotations

import json
import math
import re
import tempfile
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from ingest.contract import (
    AVALON_CORE_BOUNDS,
    MEDIA_GEOJSON,
    MEDIA_ZARR,
    ST_JOHNS,
    AdapterUnavailable,
    Artifact,
    FetchWindow,
    RunCandidate,
    RunResult,
)
from ingest.grib import normalize_precipitation, normalize_units, write_zarr
from ingest.http import PoliteClient
from ingest.manifest import RequiredField, RunManifest, declared_classes, validate_run
from ingest.registry import register

UTC = timezone.utc

GEOMET_BASE_URL = "https://geo.weather.gc.ca/geomet/"
WMS_VERSION = "1.3.0"

# The unfiltered capabilities document measured 39,635,828 bytes (641,737
# gzipped) on 2026-08-30. The service accepts a single-layer ``LAYERS`` filter
# on GetCapabilities and answers in ~18-21 KB, so that is the only path this
# module uses; a group name such as ``LAYERS=HRDPS`` is rejected with
# ``InvalidLayersParameter``, as is an unknown layer, which is how a wrong
# identifier surfaces immediately instead of silently.
CAPABILITIES_MAX_BYTES = 64 << 20

# Radar advances every six minutes, so a long TTL would leave us asking for a
# frame the layer no longer advertises. Five minutes keeps a cached extent
# usable for a worker cycle without going stale enough to matter.
DEFAULT_CACHE_TTL_SECONDS = 300

# A 512x512 radar tile over the Avalon measured 1,096 bytes with no echo and a
# 113x490 radar legend measured 10,260 bytes, both on 2026-08-30. The ceiling is
# far above a busy tile and far below anything that could fill memory; a render
# that exceeds it is refused rather than truncated, because half a PNG is not a
# smaller picture, it is a corrupt one.
IMAGE_MAX_BYTES = 8 << 20

# ``GetMap`` is the only request in this module whose cost the *caller* chooses,
# so the pixel count is bounded here rather than trusting whatever a tile proxy
# asks for.
MAX_IMAGE_PIXELS = 4096 * 4096

# Rendered images reuse the capabilities cache exactly -- same TTL, same reason:
# a radar frame that has aged past the extent must be re-resolved, not re-served.
# The entry count is capped because an image is bytes rather than the handful of
# distilled fields a LayerCapability holds.
IMAGE_CACHE_MAX_ENTRIES = 64

ATTRIBUTION = "Environment and Climate Change Canada — MSC GeoMet"
LICENCE = "Environment and Climate Change Canada Data Servers End-use Licence"

_TITLE_UNITS = re.compile(r"\[([^\[\]]+)\]\s*$")
# ECCC appends ``[experimental]`` to the title of a layer it has not made
# operational (``Current-Alerts``, the RDPS-WEonG family). It sits in the same
# trailing-bracket position as the unit, so it is stripped *before* the unit is
# read and reported separately by :func:`is_experimental` -- never as a unit.
_EXPERIMENTAL_FLAG = re.compile(r"\s*\[experimental\]\s*$", re.IGNORECASE)
# The GOES-East imagery titles end in ``[1 km]`` / ``[2 km]``: a *pixel
# resolution* in the trailing-bracket position the unit occupies. A distance
# is not the unit of a picture, so a bracket that is a number followed by
# ``km`` or ``m`` is stripped before the unit is read and reported separately
# by :func:`parse_title_resolution`. A bare ``[m]`` has no number and stays a
# unit (the WEonG fog-visibility layers depend on that).
_RESOLUTION_FLAG = re.compile(r"\s*\[(\d+(?:\.\d+)?\s*(?:km|m))\]\s*$", re.IGNORECASE)
_ISO_DURATION = re.compile(
    r"^P(?:(?P<days>\d+(?:\.\d+)?)D)?"
    r"(?:T(?:(?P<hours>\d+(?:\.\d+)?)H)?"
    r"(?:(?P<minutes>\d+(?:\.\d+)?)M)?"
    r"(?:(?P<seconds>\d+(?:\.\d+)?)S)?)?$"
)

# GeoMet states units inside the brackets of ``title_en``. Every entry here is a
# *spelling* normalization of a unit observed live — no entry changes a number.
# Anything absent is carried through verbatim and flagged, never guessed at,
# which is the policy ``ingest.grib.normalize_units`` documents.
CANONICAL_BY_GEOMET_UNIT = {
    "°c": "degC",
    "k": "K",
    "%": "percent",
    "m/s": "m s-1",
    "kt": "kt",
    "pa": "Pa",
    "hpa": "hPa",
    "m": "m",
    "mm": "mm",
    "cm": "cm",
    "mm/h": "mm h-1",
    "cm/h": "cm h-1",
    "°": "degree",
    "deg true": "degree",
    # ``Lightning_2.5km_Density`` publishes ``[flash/km²/min]``. "flash" is kept
    # rather than dropped: the quantity counts flashes, and a bare ``km-2 min-1``
    # would read as a density of something unspecified.
    "flash/km²/min": "flash km-2 min-1",
}



# ``GetMap`` may be asked for in either of two coordinate reference systems.
# EPSG:4326 (WMS 1.3.0: latitude-first bbox) is the historical default;
# EPSG:3857 (WGS 84 / Pseudo-Mercator, bbox in metres, easting/northing order)
# is what a web-mercator map canvas actually displays, so a tile requested in
# it needs no client-side warp: corner-pinning it onto the mercator canvas is
# exact. Anything else is refused client-side rather than sent upstream.
SUPPORTED_GETMAP_CRS = ("EPSG:4326", "EPSG:3857")

#: WGS 84 spherical mercator radius used by EPSG:3857, in metres.
WEB_MERCATOR_RADIUS_M = 6378137.0
#: EPSG:3857 is undefined at the poles; the projection's standard latitude cap.
WEB_MERCATOR_MAX_LATITUDE = 85.051128779807


def web_mercator_metres(latitude: float, longitude: float) -> tuple[float, float]:
    """``(x, y)`` in EPSG:3857 metres for one WGS 84 coordinate.

    The standard spherical formulas: ``x = R*lon_rad``,
    ``y = R*ln(tan(pi/4 + lat_rad/2))``. Latitudes beyond the projection's
    ~85.05 degree definition are refused rather than clamped, because a
    silently clamped bound would place the tile edge somewhere the caller did
    not ask about.
    """
    if abs(latitude) > WEB_MERCATOR_MAX_LATITUDE:
        raise ValueError(
            f"latitude {latitude} is outside EPSG:3857's defined range "
            f"(+/-{WEB_MERCATOR_MAX_LATITUDE})"
        )
    x = WEB_MERCATOR_RADIUS_M * math.radians(longitude)
    y = WEB_MERCATOR_RADIUS_M * math.log(math.tan(math.pi / 4 + math.radians(latitude) / 2))
    return x, y


class GeoMetError(RuntimeError):
    """GeoMet answered, but not with something this module may use."""


class GeoMetServiceException(GeoMetError):
    """The service returned an OGC ``ServiceExceptionReport``."""


class TimeOutsideExtent(GeoMetError):
    """A valid time was requested that the layer does not advertise."""


class GeoMetNotAnImage(GeoMetError):
    """A render request came back as something other than the image asked for."""


def parse_title_units(title: str | None) -> tuple[str | None, str | None, bool]:
    """Return ``(raw, canonical, recognised)`` for the units in ``title_en``.

    An unrecognised unit is returned unchanged with ``recognised=False`` so the
    caller can flag it. Inventing a conversion for an unknown unit is the one
    failure mode this project cannot tolerate, so there is no fallback guess.
    """
    if not title:
        return None, None, False
    match = _TITLE_UNITS.search(_strip_trailing_flags(title))
    if not match:
        return None, None, False
    raw = match.group(1).strip()
    canonical = CANONICAL_BY_GEOMET_UNIT.get(raw.lower())
    if canonical is None:
        return raw, raw, False
    return raw, canonical, True


def _strip_trailing_flags(title: str) -> str:
    """``title`` without the provider flags that share the unit's bracket position."""
    return _RESOLUTION_FLAG.sub("", _EXPERIMENTAL_FLAG.sub("", title.strip()))


def parse_title_resolution(title: str | None) -> str | None:
    """The pixel resolution ECCC states in a trailing ``[1 km]``-style bracket, or ``None``.

    A retrieved provider fact about the imagery's grid, surfaced so a caller
    can disclose it. It is never a unit: :func:`parse_title_units` strips it
    before reading the unit, exactly as it strips ``[experimental]``.
    """
    if not title:
        return None
    match = _RESOLUTION_FLAG.search(_EXPERIMENTAL_FLAG.sub("", title.strip()))
    return match.group(1).strip() if match else None


def is_experimental(title: str | None) -> bool:
    """Whether ECCC flags the layer ``[experimental]`` in its ``title_en``.

    A retrieved provider fact, surfaced so a caller can disclose it. It says
    nothing about the unit, which :func:`parse_title_units` reads separately.
    """
    return bool(title) and _EXPERIMENTAL_FLAG.search(title.strip()) is not None


def parse_iso_duration(text: str) -> timedelta | None:
    """Parse the ``PT1H``/``PT6M``/``PT10M`` periods GeoMet uses in extents."""
    match = _ISO_DURATION.match(text.strip())
    if not match:
        return None
    parts = {key: float(value) for key, value in match.groupdict(default="0").items()}
    total = timedelta(days=parts["days"], hours=parts["hours"], minutes=parts["minutes"], seconds=parts["seconds"])
    return total if total > timedelta(0) else None


def parse_iso_instant(text: str) -> datetime | None:
    """Parse one instant, treating GeoMet's literal ``N/A`` as absence.

    Radar publishes ``"dim_reference_time": "N/A"`` because a mosaic has no run
    time; that must read as *no run time*, not as a parse failure to paper over.
    """
    candidate = text.strip()
    if not candidate or candidate.upper() == "N/A":
        return None
    try:
        parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


@dataclass(frozen=True)
class TimeExtent:
    """One WMS ``Dimension`` extent, either a period or an explicit value list."""

    start: datetime
    end: datetime
    period: timedelta | None
    default: datetime | None
    values: tuple[datetime, ...] = ()

    def contains(self, moment: datetime) -> bool:
        return self.start <= moment <= self.end

    def steps(self, *, limit: int = 4096) -> tuple[datetime, ...]:
        """Materialise the advertised instants, bounded so a tiny period over a
        long extent cannot blow up memory."""
        if self.values:
            return self.values
        if self.period is None:
            return (self.start,) if self.end == self.start else (self.start, self.end)
        out: list[datetime] = []
        moment = self.start
        while moment <= self.end and len(out) < limit:
            out.append(moment)
            moment = moment + self.period
        return tuple(out)

    def nearest(self, moment: datetime) -> datetime:
        """Snap to the advertised instant closest to ``moment``.

        Raises rather than snapping when ``moment`` is outside the extent. The
        service answers such a request with ``NoMatch`` (verified live), and
        were it instead to fall back to the layer default we would attach the
        wrong valid time to a real number.
        """
        if not self.contains(moment):
            raise TimeOutsideExtent(
                f"{moment.isoformat()} is outside the advertised extent "
                f"{self.start.isoformat()}..{self.end.isoformat()}"
            )
        candidates = self.steps()
        if not candidates:
            raise TimeOutsideExtent("the layer advertises an empty time extent")
        return min(candidates, key=lambda item: abs((item - moment).total_seconds()))


def parse_time_extent(text: str, *, default: str | None = None) -> TimeExtent | None:
    """Parse ``start/end/period`` or a comma-separated list of instants."""
    body = text.strip()
    if not body:
        return None
    default_at = parse_iso_instant(default) if default else None
    if "/" in body:
        pieces = body.split("/")
        if len(pieces) < 2:
            return None
        start = parse_iso_instant(pieces[0])
        end = parse_iso_instant(pieces[1])
        if start is None or end is None:
            return None
        period = parse_iso_duration(pieces[2]) if len(pieces) > 2 else None
        return TimeExtent(start=start, end=end, period=period, default=default_at)
    values = tuple(sorted(filter(None, (parse_iso_instant(piece) for piece in body.split(",")))))
    if not values:
        return None
    return TimeExtent(start=values[0], end=values[-1], period=None, default=default_at, values=values)


@dataclass(frozen=True)
class LayerCapability:
    """The distilled capabilities of one WMS layer.

    Only these fields are retained; the capabilities tree is never held whole.
    """

    name: str
    title: str
    abstract: str
    bounds: Mapping[str, float] | None
    time: TimeExtent | None
    reference_time: TimeExtent | None
    update_sequence: str | None = None

    @property
    def units(self) -> tuple[str | None, str | None, bool]:
        return parse_title_units(self.title)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


# Elements that carry their own <Name>/<Title>; while inside one, a Name does
# not belong to the enclosing Layer. ``Style`` is the one that matters in
# practice — every GeoMet layer has styles whose names would otherwise
# overwrite the layer identifier.
_NAME_SHADOWING = frozenset({"Style", "AuthorityURL", "MetadataURL", "Attribution", "Dimension", "Extent"})


@dataclass
class _PartialLayer:
    name: str | None = None
    title: str = ""
    abstract: str = ""
    bounds: dict[str, float] | None = None
    time: TimeExtent | None = None
    reference_time: TimeExtent | None = None


def parse_capabilities(path: Path) -> tuple[dict[str, LayerCapability], str | None]:
    """Distil a WMS capabilities document with a bounded-memory parse.

    ``iterparse`` plus ``clear()`` on every closed ``<Layer>`` keeps peak memory
    proportional to the deepest open layer rather than to the document, which
    matters because the unfiltered document is ~40 MB. WMS dimension and
    bounding-box inheritance is applied from the enclosing group layers, which
    is why a stack is kept rather than each element being read alone.
    """
    layers: dict[str, LayerCapability] = {}
    stack: list[_PartialLayer] = []
    shadow = 0
    update_sequence: str | None = None

    for event, element in ElementTree.iterparse(str(path), events=("start", "end")):
        tag = _local(element.tag)
        if event == "start":
            if tag in {"WMS_Capabilities", "WMT_MS_Capabilities"}:
                update_sequence = element.get("updateSequence")
            elif tag == "Layer":
                stack.append(_PartialLayer())
            elif tag in _NAME_SHADOWING:
                shadow += 1
            continue

        if tag in _NAME_SHADOWING:
            shadow -= 1

        if not stack:
            if tag not in {"Layer"}:
                element.clear()
            continue
        current = stack[-1]

        if tag == "Name" and shadow == 0:
            current.name = (element.text or "").strip() or None
        elif tag == "Title" and shadow == 0:
            current.title = (element.text or "").strip()
        elif tag == "Abstract" and shadow == 0:
            current.abstract = (element.text or "").strip()
        elif tag == "EX_GeographicBoundingBox":
            current.bounds = _geographic_bounds(element)
        elif tag in {"Dimension", "Extent"}:
            dimension = (element.get("name") or "").strip().lower()
            extent = parse_time_extent(element.text or "", default=element.get("default"))
            if extent is None:
                pass
            elif dimension == "time":
                current.time = extent
            elif dimension == "reference_time":
                current.reference_time = extent
        elif tag == "Layer":
            finished = stack.pop()
            parent = stack[-1] if stack else None
            if finished.name:
                layers[finished.name] = LayerCapability(
                    name=finished.name,
                    title=finished.title,
                    abstract=finished.abstract,
                    bounds=finished.bounds or (parent.bounds if parent else None),
                    time=finished.time or (parent.time if parent else None),
                    reference_time=finished.reference_time or (parent.reference_time if parent else None),
                    update_sequence=update_sequence,
                )
            element.clear()

    return layers, update_sequence


def _geographic_bounds(element: ElementTree.Element) -> dict[str, float] | None:
    keys = {
        "westBoundLongitude": "west",
        "eastBoundLongitude": "east",
        "southBoundLatitude": "south",
        "northBoundLatitude": "north",
    }
    bounds: dict[str, float] = {}
    for child in element:
        target = keys.get(_local(child.tag))
        if target is None or child.text is None:
            continue
        try:
            bounds[target] = float(child.text.strip())
        except ValueError:
            return None
    return bounds if len(bounds) == 4 else None


_EXCEPTION_CODE = re.compile(r'ServiceException[^>]*\bcode="([^"]+)"')


def _service_exception(text: str) -> str | None:
    """The OGC fault in one line, code first.

    The code is what identifies the fault -- ``InvalidLayersParameter`` for an
    unknown layer, ``NoMatch`` for a TIME outside the extent -- and it lives in
    an attribute, so stripping tags alone would throw away the only part worth
    reading.
    """
    if "ServiceException" not in text:
        return None
    code = _EXCEPTION_CODE.search(text)
    body = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).strip()
    parts = [part for part in (code.group(1) if code else None, body) if part]
    return ": ".join(parts) if parts else "unspecified service exception"


@dataclass(frozen=True)
class GeoMetSample:
    """One ``GetFeatureInfo`` reading, carrying its own provenance."""

    layer: str
    value: float
    valid_time: datetime | None
    reference_time: datetime | None
    units_raw: str | None
    units: str | None
    units_recognised: bool
    latitude: float | None
    longitude: float | None
    title: str
    classification: str | None
    requested_latitude: float
    requested_longitude: float

    def as_provenance(self) -> dict[str, Any]:
        return {
            "layer": self.layer,
            "title_en": self.title,
            "valid_time": None if self.valid_time is None else self.valid_time.isoformat(),
            "reference_time": None if self.reference_time is None else self.reference_time.isoformat(),
            "units": self.units,
            "units_as_published": self.units_raw,
            "units_recognised": self.units_recognised,
            "sampled_latitude": self.latitude,
            "sampled_longitude": self.longitude,
            "requested_latitude": self.requested_latitude,
            "requested_longitude": self.requested_longitude,
            "class": self.classification,
        }


@dataclass(frozen=True)
class GeoMetImage:
    """One rendered WMS image, carrying the provenance of the request that made it.

    The bytes are never separated from ``url``, ``layer``, ``valid_time`` and
    ``reference_time``: a picture with no statement of what it shows and when is
    exactly the kind of unattributed evidence this project refuses to display.
    ``bbox`` is ``(south, west, north, east)`` — the WMS 1.3.0 EPSG:4326 order,
    kept in that order so nothing downstream has to guess which pair is which.
    """

    payload: bytes
    content_type: str
    layer: str
    url: str
    style: str | None
    valid_time: datetime | None
    reference_time: datetime | None
    width: int | None
    height: int | None
    bbox: tuple[float, float, float, float] | None
    #: The CRS the render was requested in. The recorded ``bbox`` stays the
    #: named geographic south/west/north/east mapping in every case; for an
    #: EPSG:3857 render the wire bbox was those bounds projected to metres.
    crs: str = "EPSG:4326"

    @property
    def byte_size(self) -> int:
        return len(self.payload)

    def as_provenance(self) -> dict[str, Any]:
        return {
            "layer": self.layer,
            "url": self.url,
            "style": self.style,
            "content_type": self.content_type,
            "byte_size": self.byte_size,
            "valid_time": None if self.valid_time is None else self.valid_time.isoformat(),
            "reference_time": None if self.reference_time is None else self.reference_time.isoformat(),
            "width": self.width,
            "height": self.height,
            # Named rather than positional, because a bare four-tuple is where
            # the WMS 1.3.0 axis order gets silently transposed.
            "bbox": (
                None
                if self.bbox is None
                else {
                    "south": self.bbox[0],
                    "west": self.bbox[1],
                    "north": self.bbox[2],
                    "east": self.bbox[3],
                }
            ),
            "crs": self.crs,
            "endpoint": GEOMET_BASE_URL,
            "licence": LICENCE,
            "attribution": ATTRIBUTION,
        }


@dataclass
class GeoMetClient:
    """Shared, cached, polite access to one GeoMet WMS endpoint.

    Transport, pacing, retries and byte ceilings belong to
    ``ingest.http.PoliteClient``; this class only knows OGC. Capabilities are
    cached in memory for :data:`DEFAULT_CACHE_TTL_SECONDS` so one worker cycle
    resolves a layer's time extent once rather than once per sampled step.
    """

    client: PoliteClient | None = None
    base_url: str = GEOMET_BASE_URL
    scratch_dir: Path | None = None
    cache_ttl_seconds: float = DEFAULT_CACHE_TTL_SECONDS
    # A pixel query needs a box; 0.1 degrees over 20 pixels is a ~1 km sample
    # cell, finer than the 2.5 km HRDPS grid it interrogates.
    probe_half_span_degrees: float = 0.1
    probe_pixels: int = 20
    _capabilities: dict[str, LayerCapability] = field(default_factory=dict, init=False)
    _fetched_at: dict[str, float] = field(default_factory=dict, init=False)
    # Keyed by the fully-formed request URL, so two callers that differ in any
    # parameter — a pixel, a style, a frame — can never share a render.
    _images: dict[str, GeoMetImage] = field(default_factory=dict, init=False)
    _images_fetched_at: dict[str, float] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        self._owned_client: PoliteClient | None = None

    def _http(self) -> PoliteClient:
        if self.client is not None:
            return self.client
        if self._owned_client is None:
            self._owned_client = PoliteClient()
        return self._owned_client

    def close(self) -> None:
        if self._owned_client is not None:
            self._owned_client.close()
            self._owned_client = None

    def url(self, params: Mapping[str, Any]) -> str:
        from urllib.parse import urlencode  # noqa: PLC0415

        merged: dict[str, Any] = {"service": "WMS", "version": WMS_VERSION}
        merged.update({key: value for key, value in params.items() if value is not None})
        return f"{self.base_url}?{urlencode(merged)}"

    # ------------------------------------------------------------ capabilities

    def capabilities(self, layer: str, *, refresh: bool = False) -> LayerCapability:
        """Fetch and distil the capabilities of exactly one layer.

        The single-layer ``LAYERS`` filter cuts the 40 MB document to ~18 KB.
        The service rejects a group name and an unknown name identically, with
        ``InvalidLayersParameter``, so a wrong identifier fails here and loudly
        rather than becoming a silent gap later.
        """
        now = datetime.now(UTC).timestamp()
        if not refresh:
            cached = self._capabilities.get(layer)
            fetched = self._fetched_at.get(layer)
            if cached is not None and fetched is not None and now - fetched < self.cache_ttl_seconds:
                return cached

        url = self.url({"request": "GetCapabilities", "LAYERS": layer})
        base = self.scratch_dir or Path(tempfile.gettempdir())
        base.mkdir(parents=True, exist_ok=True)
        destination = base / f"geomet-capabilities-{re.sub(r'[^A-Za-z0-9_.-]', '_', layer)}.xml.part"
        try:
            self._http().download(url, destination, max_bytes=CAPABILITIES_MAX_BYTES)
            head = destination.read_bytes()[:4096].decode("utf-8", "replace")
            problem = _service_exception(head)
            if problem:
                raise AdapterUnavailable(f"GeoMet GetCapabilities rejected {layer}: {problem}")
            parsed, _sequence = parse_capabilities(destination)
        except AdapterUnavailable:
            raise
        except Exception as error:  # transport, XML or filesystem
            raise AdapterUnavailable(f"GeoMet capabilities unavailable for {layer}: {error}") from error
        finally:
            destination.unlink(missing_ok=True)

        found = parsed.get(layer)
        if found is None:
            raise AdapterUnavailable(f"GeoMet does not advertise layer {layer}")
        self._capabilities[layer] = found
        self._fetched_at[layer] = now
        return found

    def time_dimension(self, name: str) -> tuple[datetime, ...]:
        """The instants a layer advertises, oldest first.

        Empty for a layer with no time dimension: ``Current-Alerts`` and
        ``AQHI-OBS`` are both time-independent "current" layers, verified live.
        """
        extent = self.capabilities(name).time
        return () if extent is None else extent.steps()

    def resolve_time(self, name: str, moment: datetime | None) -> datetime | None:
        """Snap ``moment`` onto the layer's advertised extent.

        Returns ``None`` when the layer has no time dimension, meaning the
        request must omit ``TIME`` entirely.
        """
        extent = self.capabilities(name).time
        if extent is None:
            return None
        if moment is None:
            return extent.default or extent.end
        return extent.nearest(moment)

    def resolve_reference_time(self, name: str, moment: datetime | None = None) -> datetime | None:
        """The model run a layer advertises, or ``None`` when it has none.

        Radar and the two vector layers publish no ``reference_time`` dimension
        at all, and radar's ``dim_reference_time`` property is the literal
        ``"N/A"`` because a mosaic has no run. ``None`` here therefore means
        *this product genuinely has no run time*, and the request must omit
        ``DIM_REFERENCE_TIME`` rather than invent one.
        """
        extent = self.capabilities(name).reference_time
        if extent is None:
            return None
        if moment is None:
            return extent.default or extent.end
        return extent.nearest(moment)

    # ----------------------------------------------------------------- queries

    def _probe_params(
        self, latitude: float, longitude: float, bounds: Mapping[str, float] | None = None
    ) -> dict[str, Any]:
        """The pixel-query geometry, either a tight cell or a declared box.

        The box matters for the vector layers. MapServer resolves a
        ``GetFeatureInfo`` on a vector layer against a search area derived from
        the map resolution, so a tight probe around a point returns nothing at
        all: verified live on 2026-08-30, a 0.2-degree box centred 0.7 degrees
        from the St. John's AQHI station returned zero features while one query
        over the whole Avalon core box returned three stations. Querying the box
        is therefore not a shortcut, it is the only form that answers.
        """
        pixels = self.probe_pixels
        if bounds is None:
            half = self.probe_half_span_degrees
            south, west = latitude - half, longitude - half
            north, east = latitude + half, longitude + half
        else:
            south, west = bounds["south"], bounds["west"]
            north, east = bounds["north"], bounds["east"]
        return {
            "crs": "EPSG:4326",
            # WMS 1.3.0 with EPSG:4326 orders the bbox latitude-first.
            "bbox": f"{south},{west},{north},{east}",
            "width": pixels,
            "height": pixels,
            "i": pixels // 2,
            "j": pixels // 2,
        }

    def feature_collection(
        self,
        layer: str,
        latitude: float,
        longitude: float,
        *,
        valid_time: datetime | None = None,
        resolve: bool = True,
        feature_count: int = 1,
        bounds: Mapping[str, float] | None = None,
    ) -> dict[str, Any]:
        """The raw GeoJSON ``GetFeatureInfo`` payload for one pixel.

        Vector layers (``Current-Alerts``, ``AQHI-OBS``) answer with real
        GeoJSON features rather than a single gridded value, so the alert and
        index adapters read this directly. The lightning layer answers a bare
        ``{}`` where it has no density, which is why the absent ``features`` key
        is tolerated here and read as absence by the caller.
        """
        stamp = self.resolve_time(layer, valid_time) if resolve else valid_time
        params = {
            "request": "GetFeatureInfo",
            "layers": layer,
            "query_layers": layer,
            "info_format": "application/json",
            "feature_count": feature_count,
            **self._probe_params(latitude, longitude, bounds),
        }
        if stamp is not None:
            params["TIME"] = _wms_time(stamp)
        text = self._http().get(self.url(params)).text
        problem = _service_exception(text)
        if problem:
            raise GeoMetServiceException(f"{layer}: {problem}")
        try:
            payload = json.loads(text)
        except ValueError as error:
            raise GeoMetError(f"{layer}: GetFeatureInfo returned a non-JSON body") from error
        if not isinstance(payload, Mapping):
            raise GeoMetError(f"{layer}: GetFeatureInfo returned {type(payload).__name__}, not an object")
        return dict(payload)

    def feature_info(
        self,
        layer: str,
        latitude: float,
        longitude: float,
        *,
        valid_time: datetime | None = None,
        resolve: bool = True,
    ) -> GeoMetSample | None:
        """One numeric reading, or ``None`` when the layer has no value there.

        ``None`` is a real answer — no echo, no flash density, outside a model
        domain — and is never replaced by a substituted value.
        """
        payload = self.feature_collection(
            layer, latitude, longitude, valid_time=valid_time, resolve=resolve, feature_count=1
        )
        features = payload.get("features") or []
        if not features:
            return None
        return self._sample_from_feature(layer, features[0], latitude, longitude)

    def _sample_from_feature(
        self,
        layer: str,
        feature: Mapping[str, Any],
        requested_latitude: float,
        requested_longitude: float,
    ) -> GeoMetSample | None:
        properties = feature.get("properties") or {}
        try:
            value = float(properties.get("value"))
        except (TypeError, ValueError):
            return None
        if math.isnan(value):
            return None
        title = str(properties.get("title_en", ""))
        units_raw, units, recognised = parse_title_units(title)
        coordinates = ((feature.get("geometry") or {}).get("coordinates")) or []
        latitude = longitude = None
        if isinstance(coordinates, Sequence) and len(coordinates) >= 2:
            try:
                longitude, latitude = float(coordinates[0]), float(coordinates[1])
            except (TypeError, ValueError):
                latitude = longitude = None
        return GeoMetSample(
            layer=layer,
            value=value,
            valid_time=parse_iso_instant(str(properties.get("time", ""))),
            reference_time=parse_iso_instant(str(properties.get("dim_reference_time", ""))),
            units_raw=units_raw,
            units=units,
            units_recognised=recognised,
            latitude=latitude,
            longitude=longitude,
            title=title,
            classification=None if properties.get("class") is None else str(properties["class"]),
            requested_latitude=requested_latitude,
            requested_longitude=requested_longitude,
        )

    # --------------------------------------------------------- rendered images

    def _cached_image(self, url: str) -> GeoMetImage | None:
        cached = self._images.get(url)
        fetched = self._images_fetched_at.get(url)
        if cached is None or fetched is None:
            return None
        if datetime.now(UTC).timestamp() - fetched >= self.cache_ttl_seconds:
            self._images.pop(url, None)
            self._images_fetched_at.pop(url, None)
            return None
        return cached

    def _remember_image(self, url: str, image: GeoMetImage) -> None:
        self._images[url] = image
        self._images_fetched_at[url] = datetime.now(UTC).timestamp()
        while len(self._images) > IMAGE_CACHE_MAX_ENTRIES:
            oldest = min(self._images_fetched_at, key=self._images_fetched_at.__getitem__)
            self._images.pop(oldest, None)
            self._images_fetched_at.pop(oldest, None)

    def _render(
        self,
        params: Mapping[str, Any],
        *,
        layer: str,
        image_format: str,
        style: str | None,
        valid_time: datetime | None,
        reference_time: datetime | None,
        width: int | None,
        height: int | None,
        bbox: tuple[float, float, float, float] | None,
        crs: str = "EPSG:4326",
    ) -> GeoMetImage:
        """Issue one render request and refuse anything that is not the image.

        This is the method the ``NoMatch`` trap exists for. An unadvertised
        ``TIME`` or ``DIM_REFERENCE_TIME`` is answered with **HTTP 200** and a
        ``text/xml`` ``ServiceExceptionReport`` body — verified live on
        2026-08-30 for both, 477 bytes each. A client that trusts the status
        code hands that XML to a PNG decoder, or worse publishes it as a tile.
        The body is therefore inspected for the OGC fault *before* the content
        type, so a mislabelled fault is caught too, and neither path can return
        bytes: they raise.
        """
        url = self.url(params)
        cached = self._cached_image(url)
        if cached is not None:
            return cached

        response = self._http().get(url)
        payload = response.content
        problem = _service_exception(payload[:4096].decode("utf-8", "replace"))
        if problem:
            raise GeoMetServiceException(f"{layer}: {problem}")
        declared = (response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if declared != image_format:
            raise GeoMetNotAnImage(
                f"{layer}: asked for {image_format} and the service answered "
                f"{declared or 'no content type'} ({len(payload)} bytes)"
            )
        if not payload:
            raise GeoMetNotAnImage(f"{layer}: the service answered {image_format} with an empty body")
        if len(payload) > IMAGE_MAX_BYTES:
            raise GeoMetError(f"{layer}: render of {len(payload)} bytes exceeds the {IMAGE_MAX_BYTES} byte ceiling")

        image = GeoMetImage(
            payload=payload,
            content_type=declared,
            layer=layer,
            url=url,
            style=style,
            valid_time=valid_time,
            reference_time=reference_time,
            width=width,
            height=height,
            bbox=bbox,
            crs=crs,
        )
        self._remember_image(url, image)
        return image

    def map_image(
        self,
        layer: str,
        bounds: Mapping[str, float],
        *,
        width: int = 256,
        height: int = 256,
        valid_time: datetime | None = None,
        resolve: bool = True,
        style: str | None = None,
        image_format: str = "image/png",
        transparent: bool = True,
        crs: str = "EPSG:4326",
    ) -> GeoMetImage:
        """Render one ``GetMap`` tile for ``bounds``, with its provenance attached.

        ``bounds`` is the same ``south/west/north/east`` mapping the rest of this
        module uses, in degrees, whatever the ``crs``. WMS 1.3.0 with EPSG:4326
        orders the bbox **latitude first**, so the wire form is
        ``miny,minx,maxy,maxx``; getting that backwards is the classic WMS bug and
        it fails silently — a transposed box was answered live with HTTP 200 and a
        96-byte PNG rather than an exception. With ``crs="EPSG:3857"`` the bounds
        are projected to spherical-mercator metres and sent ``minx,miny,maxx,maxy``
        (easting/northing) — the axis order EPSG:3857 defines — which yields a tile
        that corner-pins exactly onto a web-mercator canvas with no residual warp.

        ``TIME`` is resolved through :meth:`resolve_time`, which snaps onto the
        advertised extent and raises :class:`TimeOutsideExtent` client-side, so a
        frame the layer no longer advertises never reaches the service. The run is
        pinned with ``DIM_REFERENCE_TIME`` wherever the layer advertises one, which
        is what lets the returned image state which run it came from instead of
        inheriting whatever the service happened to default to.
        """
        if width < 1 or height < 1:
            raise ValueError("a rendered image needs at least one pixel in each dimension")
        if width * height > MAX_IMAGE_PIXELS:
            raise ValueError(f"{width}x{height} exceeds the {MAX_IMAGE_PIXELS} pixel ceiling")
        missing = {"south", "west", "north", "east"} - set(bounds)
        if missing:
            raise ValueError(f"bounds is missing {', '.join(sorted(missing))}")
        south, west, north, east = (
            float(bounds["south"]),
            float(bounds["west"]),
            float(bounds["north"]),
            float(bounds["east"]),
        )
        if south >= north or west >= east:
            raise ValueError(f"bounds {bounds!r} is not a south-west to north-east box")
        if crs not in SUPPORTED_GETMAP_CRS:
            raise ValueError(f"crs must be one of {', '.join(SUPPORTED_GETMAP_CRS)}, not {crs!r}")
        if crs == "EPSG:3857":
            # EPSG:3857 orders the bbox x,y (easting, northing), in metres.
            min_x, min_y = web_mercator_metres(south, west)
            max_x, max_y = web_mercator_metres(north, east)
            wire_bbox = f"{min_x},{min_y},{max_x},{max_y}"
        else:
            # WMS 1.3.0 with EPSG:4326 orders the bbox latitude-first.
            wire_bbox = f"{south},{west},{north},{east}"

        stamp = self.resolve_time(layer, valid_time) if resolve else valid_time
        reference = self.resolve_reference_time(layer) if resolve else None
        params: dict[str, Any] = {
            "request": "GetMap",
            "layers": layer,
            "styles": style,
            "crs": crs,
            "bbox": wire_bbox,
            "width": width,
            "height": height,
            "format": image_format,
            "transparent": "TRUE" if transparent else "FALSE",
        }
        if stamp is not None:
            params["TIME"] = _wms_time(stamp)
        if reference is not None:
            params["DIM_REFERENCE_TIME"] = _wms_time(reference)
        return self._render(
            params,
            layer=layer,
            image_format=image_format,
            style=style,
            valid_time=stamp,
            reference_time=reference,
            width=width,
            height=height,
            bbox=(south, west, north, east),
            crs=crs,
        )

    def legend_graphic(self, layer: str, *, style: str | None = None, image_format: str = "image/png") -> GeoMetImage:
        """Fetch ECCC's own colour ramp for a layer via ``GetLegendGraphic``.

        This exists so that nothing in this project ever invents a scale for a
        rendered field. The ramp that explains a radar tile has to be the ramp
        the radar tile was drawn with, and only the service can say what that is;
        a hand-written legend would be a fabricated key over real pixels.

        ``style`` is optional — the service renders the layer's default style
        when it is omitted (verified live 2026-08-30) — and an unknown style is
        refused with ``LayerNotDefined`` in an HTTP 200 ``text/xml`` body, which
        :meth:`_render` turns into an exception rather than bytes. The returned
        image carries no ``TIME``: a legend describes the layer's scale, not one
        frame of it.
        """
        # WMS 1.3.0 names the parameter ``LAYER``, singular, and its SLD profile
        # makes ``SLD_VERSION`` mandatory. GeoMet happens to accept ``LAYERS``
        # without ``SLD_VERSION`` for its raster layers, but its vector layers
        # answer ``LayerNotDefined`` ("Mandatory LAYER parameter missing") for
        # ``AQHI-OBS`` and ``MissingParameterValue`` (``SLD_VERSION``) for
        # ``Current-Alerts``; both verified live 2026-08-30.
        params: dict[str, Any] = {
            "request": "GetLegendGraphic",
            "LAYER": layer,
            "format": image_format,
            "SLD_VERSION": "1.1.0",
        }
        if style is not None:
            params["STYLE"] = style
        return self._render(
            params,
            layer=layer,
            image_format=image_format,
            style=style,
            valid_time=None,
            reference_time=None,
            # A legend states its own dimensions in its own bytes; declaring a
            # size we did not ask for and did not measure would be a guess.
            width=None,
            height=None,
            bbox=None,
        )


def _wms_time(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Pinned layers. Every identifier, title and unit below was read back from the
# live capabilities document on 2026-08-30; see docs/geomet-layers.md.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LayerBinding:
    """One canonical variable served by one GeoMet layer.

    ``published_units`` is what ``title_en`` states; ``stored_units`` is what
    the artifact carries after ``ingest.grib.normalize_units``. They differ only
    where that function performs a real conversion (Pa to hPa), and both are
    declared so the manifest checks the unit the artifact actually holds.
    """

    variable: str
    layer: str
    published_units: str
    level: str = "surface"
    stored_units: str | None = None

    @property
    def units_in_artifact(self) -> str:
        return self.stored_units or self.published_units


HRDPS_SURFACE = (
    LayerBinding("temperature_2m", "HRDPS.CONTINENTAL_TT", "degC", "2 m"),
    LayerBinding("dew_point_2m", "HRDPS.CONTINENTAL_TD", "degC", "2 m"),
    LayerBinding("relative_humidity_2m", "HRDPS.CONTINENTAL_HR", "percent", "2 m"),
    LayerBinding("mean_sea_level_pressure", "HRDPS.CONTINENTAL_PN-SLP", "Pa", "mean sea level", "hPa"),
    LayerBinding("total_cloud", "HRDPS.CONTINENTAL_NT", "percent", "entire atmosphere"),
)
HRDPS_WIND = (
    LayerBinding("wind_speed_10m", "HRDPS.CONTINENTAL_WSPD", "m s-1", "10 m"),
    LayerBinding("wind_direction_10m", "HRDPS.CONTINENTAL_WD", "degree", "10 m"),
)
HRDPS_PRECIP = LayerBinding("precipitation_accumulation", "HRDPS.CONTINENTAL.DIAG_PR_PT1H", "mm", "surface")
HRDPS_PROFILE_TEMPLATE = "HRDPS.CONTINENTAL.PRES_HR.{level}"

RDPS_SURFACE = (
    LayerBinding("temperature_2m", "RDPS_10km_AirTemp_2m", "degC", "2 m"),
    LayerBinding("dew_point_2m", "RDPS_10km_DewPoint_2m", "degC", "2 m"),
    LayerBinding("relative_humidity_2m", "RDPS_10km_RelativeHumidity_2m", "percent", "2 m"),
    LayerBinding("mean_sea_level_pressure", "RDPS_10km_Pressure_MSL", "Pa", "mean sea level", "hPa"),
    LayerBinding("total_cloud", "RDPS_10km_TotalCloudCover", "percent", "entire atmosphere"),
)
RDPS_WIND = (
    LayerBinding("wind_speed_10m", "RDPS_10km_WindSpeed_10m", "m s-1", "10 m"),
    LayerBinding("wind_direction_10m", "RDPS_10km_WindDir_10m", "degree", "10 m"),
)
RDPS_PRECIP = LayerBinding("precipitation_accumulation", "RDPS_10km_Precip-Accum1h", "mm", "surface")
RDPS_PROFILE_TEMPLATE = "RDPS_10km_RelativeHumidity_{level}mb"

# Every one of these levels was confirmed present for both templates on
# 2026-08-30. GeoMet advertises 28 HRDPS levels spanning 50..1015 mb;
# this is the subset a Skew-T actually needs, kept short because the profile
# costs one polite request per level.
PROFILE_LEVELS_HPA = (1000, 985, 970, 950, 925, 900, 875, 850, 800, 750, 700, 650, 600, 550, 500, 400, 300)

RADAR_RAIN_LAYER = "RADAR_1KM_RRAI"
RADAR_SNOW_LAYER = "RADAR_1KM_RSNO"
LIGHTNING_LAYER = "Lightning_2.5km_Density"
ALERTS_LAYER = "Current-Alerts"
AQHI_LAYER = "AQHI-OBS"

# The radar mosaic's own word for "I looked here and detected nothing". It
# arrives with ``"value": 0``, which is why it has to be recognised by name:
# treating that zero as a precipitation rate would publish "0 mm/h" — a
# measurement — where the truth is "no echo detected".
RADAR_UNDETECTED_CLASS = "undetected"


def wind_components(speed_ms: float, direction_deg: float) -> tuple[float, float]:
    """Meteorological convention: direction is the bearing the wind comes *from*.

    Mirrors ``ingest.adapters.eccc_ogc.parse_wind_uv`` and
    ``ingest.adapters.awc`` so every adapter in the project agrees. A northerly
    (000 deg) wind therefore yields ``v`` negative — it blows toward the south.
    """
    radians = math.radians(direction_deg)
    return round(-speed_ms * math.sin(radians), 4), round(-speed_ms * math.cos(radians), 4)


def _numpy():
    import numpy  # noqa: PLC0415

    return numpy


def _xarray():
    import xarray  # noqa: PLC0415

    return xarray


def _column(values: Sequence[float | None]):
    """A ``(time, 1, 1)`` array where absence stays NaN rather than becoming 0."""
    numpy = _numpy()
    array = numpy.full((len(values), 1, 1), numpy.nan, dtype="float64")
    for index, value in enumerate(values):
        if value is not None:
            array[index, 0, 0] = value
    return array


def _stamps(times: Sequence[datetime]):
    numpy = _numpy()
    return numpy.array([numpy.datetime64(moment.astimezone(UTC).replace(tzinfo=None), "ns") for moment in times])


def _times_in_window(extent: TimeExtent | None, window: FetchWindow, *, max_steps: int) -> tuple[datetime, ...]:
    """The advertised instants that fall inside the evidence window.

    Thinned rather than truncated when the layer advertises more steps than the
    request budget allows, because the newest step is the one the map shows and
    dropping the tail would silently make the artifact stale.
    """
    if extent is None:
        return ()
    inside = tuple(step for step in extent.steps() if window.covers(step))
    if len(inside) <= max_steps:
        return inside
    stride = math.ceil(len(inside) / max_steps)
    thinned = inside[::stride]
    if thinned and thinned[-1] != inside[-1]:
        thinned = thinned + (inside[-1],)
    return thinned


def _base_provenance(source_id: str, adapter_version: str, product: str, resolution: str) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "producer": "Environment and Climate Change Canada (MSC)",
        "product": product,
        "access": "MSC GeoMet WMS GetFeatureInfo",
        "endpoint": GEOMET_BASE_URL,
        "native_resolution": resolution,
        "native_crs": "EPSG:4326",
        "adapter_version": adapter_version,
        "licence": LICENCE,
        "attribution": ATTRIBUTION,
        # Every artifact built on this provenance holds values MSC published,
        # sampled by GetFeatureInfo and stored unmodified. One declaration
        # here rather than one per artifact, because they are all the same
        # kind of thing and a per-site copy is a place for one to drift.
        **declared_classes(["retrieved"]),
    }


@dataclass
class _SeriesResult:
    """One layer sampled at one point across several times.

    ``errors`` and ``notes`` are deliberately separate. An error means the query
    failed or the units were not what was pinned — a decode failure that must
    reach ``validate_run`` and stop publication. A note means the service
    answered and had no value there, which is information for provenance, not a
    fault.
    """

    values: list[float | None]
    classes: list[str | None]
    answered: list[bool]
    errors: list[str]
    notes: list[str]
    reference_times: set[datetime]
    units: str | None
    units_raw: str | None
    title: str

    @property
    def any_value(self) -> bool:
        return any(value is not None for value in self.values)


def _sample_series(
    client: GeoMetClient,
    layer: str,
    latitude: float,
    longitude: float,
    times: Sequence[datetime],
    *,
    expected_units: str,
) -> _SeriesResult:
    """Sample one layer at one point across ``times``, recording every gap."""
    result = _SeriesResult([], [], [], [], [], set(), None, None, "")
    for moment in times:
        try:
            sample = client.feature_info(layer, latitude, longitude, valid_time=moment)
        except GeoMetError as error:
            # Includes TimeOutsideExtent: a step the layer no longer advertises
            # is a failure to retrieve, not an absence of weather.
            result.values.append(None)
            result.classes.append(None)
            result.answered.append(False)
            result.errors.append(f"{layer}@{moment.isoformat()}: {error}")
            continue
        if sample is None:
            result.values.append(None)
            result.classes.append(None)
            result.answered.append(True)
            result.notes.append(f"{layer}@{moment.isoformat()}: the service answered with no value here")
            continue
        if sample.valid_time is not None and sample.valid_time != moment:
            result.errors.append(
                f"{layer}: requested {moment.isoformat()} but the service answered for "
                f"{sample.valid_time.isoformat()}"
            )
        if not sample.units_recognised:
            result.errors.append(f"{layer}: unrecognised units {sample.units_raw!r}; carried through unconverted")
        elif sample.units != expected_units:
            result.errors.append(f"{layer}: units {sample.units!r} differ from the pinned {expected_units!r}")
        result.values.append(sample.value)
        result.classes.append(sample.classification)
        result.answered.append(True)
        if sample.reference_time is not None:
            result.reference_times.add(sample.reference_time)
        result.units = sample.units or result.units
        result.units_raw = sample.units_raw or result.units_raw
        result.title = sample.title or result.title
    return result


def _layer_provenance(series: _SeriesResult, layer: str, variable: str, level: str, expected: str) -> dict[str, Any]:
    return {
        "variable": variable,
        "level": level,
        "title_en": series.title,
        "units": series.units,
        "units_as_published": series.units_raw,
        "expected_units": expected,
        "values_returned": sum(1 for value in series.values if value is not None),
        "queries_answered": sum(1 for answered in series.answered if answered),
        "queries_requested": len(series.values),
    }


class _GeoMetPointAdapter:
    """Shared plumbing for the adapters that sample one point over time."""

    source_id = ""
    adapter_version = ""
    product = ""
    max_time_steps = 24

    def __init__(
        self,
        client: GeoMetClient | None = None,
        *,
        point: tuple[float, float] = ST_JOHNS,
        max_time_steps: int | None = None,
    ) -> None:
        self._client = client
        self.point = point
        if max_time_steps is not None:
            self.max_time_steps = max_time_steps

    def _geomet(self, workdir: Path | None = None) -> GeoMetClient:
        if self._client is None:
            self._client = GeoMetClient(scratch_dir=workdir)
        elif workdir is not None and self._client.scratch_dir is None:
            self._client.scratch_dir = workdir
        return self._client

    def _candidate_times(self, candidate: RunCandidate, window: FetchWindow, anchor: str) -> tuple[datetime, ...]:
        times = tuple(
            moment
            for moment in (parse_iso_instant(value) for value in candidate.detail.get("valid_times", ()))
            if moment is not None
        )
        if not times:
            times = _times_in_window(self._geomet().capabilities(anchor).time, window, max_steps=self.max_time_steps)
        if not times:
            raise AdapterUnavailable(f"{self.source_id}: no advertised valid time falls inside the window")
        return times


# ---------------------------------------------------------------------------
# Radar
# ---------------------------------------------------------------------------


class ECCCRadarGeoMetAdapter(_GeoMetPointAdapter):
    """Radar precipitation rate, with echo semantics stated explicitly.

    The artifact's mandatory field is ``radar_echo``, not a rate. That inversion
    is the whole point: the mosaic always tells us whether it detected an echo,
    and only sometimes tells us a rate. Publishing a rate as the mandatory field
    would force "0 mm/h" into the artifact on every clear scan — a fabricated
    measurement — whereas an absent rate beside ``radar_echo = 0`` says exactly
    what happened. ``ingest.meteorology.radar_echo_semantics`` is the single
    place the wording is defined and it is imported rather than restated.
    """

    source_id = "eccc-radar"
    adapter_version = "eccc-geomet-radar-v1"
    product = "Canadian radar composite precipitation rate via GeoMet WMS"
    # The layer advertises three hours at PT6M, i.e. 31 scans.
    max_time_steps = 31

    def discover(self, window: FetchWindow) -> list[RunCandidate]:
        client = self._geomet()
        capability = client.capabilities(RADAR_RAIN_LAYER)
        if capability.time is None:
            raise AdapterUnavailable(f"{RADAR_RAIN_LAYER} advertises no time dimension")
        times = _times_in_window(capability.time, window, max_steps=self.max_time_steps)
        if not times:
            raise AdapterUnavailable(
                f"{RADAR_RAIN_LAYER} advertises {capability.time.start.isoformat()}.."
                f"{capability.time.end.isoformat()}, which does not intersect "
                f"{window.start.isoformat()}..{window.end.isoformat()}"
            )
        return [
            RunCandidate(
                provider_run_id=f"{self.source_id}-{times[-1].strftime('%Y%m%dT%H%M%SZ')}",
                run_time=times[-1],
                urls=[client.url({"request": "GetCapabilities", "LAYERS": RADAR_RAIN_LAYER})],
                detail={"valid_times": [moment.isoformat() for moment in times]},
            )
        ]

    def fetch(self, candidate: RunCandidate, window: FetchWindow, workdir: Path) -> RunResult:
        from ingest.meteorology import radar_echo_semantics  # noqa: PLC0415

        client = self._geomet(workdir)
        numpy, xarray = _numpy(), _xarray()
        latitude, longitude = self.point
        times = self._candidate_times(candidate, window, RADAR_RAIN_LAYER)

        rain = _sample_series(client, RADAR_RAIN_LAYER, latitude, longitude, times, expected_units="mm h-1")
        snow = _sample_series(client, RADAR_SNOW_LAYER, latitude, longitude, times, expected_units="cm h-1")

        echo: list[float | None] = []
        rain_rate: list[float | None] = []
        snow_rate: list[float | None] = []
        undetected = 0
        for index in range(len(times)):
            rain_value, snow_value = rain.values[index], snow.values[index]
            rain_class = (rain.classes[index] or "").strip().lower()
            rain_positive = rain_value is not None and rain_value > 0.0
            snow_positive = snow_value is not None and snow_value > 0.0
            if rain_class == RADAR_UNDETECTED_CLASS:
                undetected += 1
            if rain_positive or snow_positive:
                echo.append(1.0)
            elif rain.answered[index] and snow.answered[index]:
                # Both layers answered and neither reported a positive rate:
                # the mosaic looked and detected nothing. That is a real
                # observation, and it is 0 on the echo flag, not 0 mm/h.
                echo.append(0.0)
            else:
                echo.append(None)
            # A rate exists only where there is an echo to have a rate.
            rain_rate.append(rain_value if rain_positive else None)
            snow_rate.append(snow_value if snow_positive else None)

        dataset = xarray.Dataset(
            {
                "radar_echo": (
                    ("valid_time", "latitude", "longitude"),
                    _column(echo),
                    {
                        "units": "flag",
                        "flag_values": "0, 1",
                        "flag_meanings": "no_detected_precipitating_echo precipitating_echo_detected",
                        "geomet_layer": f"{RADAR_RAIN_LAYER} + {RADAR_SNOW_LAYER}",
                        "semantics": (
                            "0 means the mosaic scanned this cell and detected no precipitating echo; it does "
                            "not mean clear sky. Missing means the mosaic did not answer for this scan."
                        ),
                    },
                ),
                "precipitation_rate": (
                    ("valid_time", "latitude", "longitude"),
                    _column(rain_rate),
                    {
                        "units": rain.units or "mm h-1",
                        "original_units": rain.units_raw or "mm/h",
                        "geomet_layer": RADAR_RAIN_LAYER,
                        "long_name": rain.title,
                        "semantics": (
                            "instantaneous radar-derived rain rate, present only where an echo was detected; "
                            "absence means no detected precipitating echo, never a rate of zero"
                        ),
                    },
                ),
                "snow_rate": (
                    ("valid_time", "latitude", "longitude"),
                    _column(snow_rate),
                    {
                        "units": snow.units or "cm h-1",
                        "original_units": snow.units_raw or "cm/h",
                        "geomet_layer": RADAR_SNOW_LAYER,
                        "long_name": snow.title,
                        "semantics": (
                            "instantaneous radar-derived snow rate, present only where an echo was detected; "
                            "absence means no detected precipitating echo, never a rate of zero"
                        ),
                    },
                ),
            },
            coords={
                "valid_time": _stamps(times),
                "latitude": numpy.array([latitude], dtype="float64"),
                "longitude": numpy.array([longitude], dtype="float64"),
            },
            attrs={
                "source": self.product,
                "endpoint": GEOMET_BASE_URL,
                "echo_semantics": radar_echo_semantics(None),
            },
        )
        dataset = normalize_units(dataset)

        # The rate fields are declared to the manifest only when they carry a
        # value, because ``ingest.manifest.validate_run`` fails an all-missing
        # declared field with ``empty_field`` whether or not it is optional --
        # and a scan series with no echo anywhere is a complete, correct radar
        # answer, not an incomplete run.
        fields = [RequiredField("radar_echo", "flag", level="radar mosaic surface projection")]
        if any(value is not None for value in rain_rate):
            fields.append(
                RequiredField("precipitation_rate", "mm h-1", level="radar mosaic surface projection", optional=True)
            )
        if any(value is not None for value in snow_rate):
            fields.append(
                RequiredField("snow_rate", "cm h-1", level="radar mosaic surface projection", optional=True)
            )
        manifest = RunManifest(source_id=self.source_id, fields=tuple(fields), required_valid_times=times)
        validation = validate_run(manifest, dataset, window=window, decode_errors=[*rain.errors, *snow.errors])

        path = workdir / "eccc-radar.zarr.zip"
        write_zarr(dataset, path)

        provenance = _base_provenance(
            self.source_id, self.adapter_version, self.product, "1 km radar mosaic, sampled at points"
        )
        provenance.update(
            {
                "quality": validation.as_quality(),
                "coverage": validation.as_coverage(),
                "run_time": times[-1].isoformat(),
                "valid_times": [moment.isoformat() for moment in times],
                "echo_semantics": {
                    moment.isoformat(): radar_echo_semantics(None if state is None else state > 0.0)
                    for moment, state in zip(times, echo, strict=True)
                },
                "undetected_scans": undetected,
                "layers": {
                    RADAR_RAIN_LAYER: _layer_provenance(
                        rain, RADAR_RAIN_LAYER, "precipitation_rate", "surface", "mm h-1"
                    ),
                    RADAR_SNOW_LAYER: _layer_provenance(snow, RADAR_SNOW_LAYER, "snow_rate", "surface", "cm h-1"),
                },
                "sample_points": [{"latitude": latitude, "longitude": longitude}],
                "sampling": (
                    "WMS GetFeatureInfo answers one pixel at one time; the sample geometry is the single "
                    "declared point above, not a dense grid"
                ),
                "notes": [*rain.notes, *snow.notes],
                "flags": [*rain.errors, *snow.errors],
            }
        )
        return RunResult(
            source_id=self.source_id,
            provider_run_id=candidate.provider_run_id,
            run_time=times[-1],
            retrieved_at=datetime.now(UTC),
            complete=validation.complete,
            qc_passed=validation.qc_passed,
            artifacts=[Artifact("radar", MEDIA_ZARR, path, provenance)],
            native_crs="EPSG:4326",
            notes=(
                f"Sampled {len(times)} radar scans; {undetected} reported the mosaic's own "
                f"'Undetected' class. {validation.detail}"
            ),
        )


# ---------------------------------------------------------------------------
# Lightning
# ---------------------------------------------------------------------------


class ECCCLightningGeoMetAdapter(_GeoMetPointAdapter):
    """Gridded lightning flash density.

    ``Lightning_2.5km_Density`` answers a bare ``{}`` where the cell carries no
    density, verified live. For a Canada-wide gridded product covering the
    Avalon that means *no flashes in this cell over this interval*, which is
    recorded as ``lightning_observed = 0`` with the density itself absent — the
    same split as radar, for the same reason.
    """

    source_id = "eccc-lightning"
    adapter_version = "eccc-geomet-lightning-v1"
    product = "Lightning flash density 2.5 km via GeoMet WMS"
    # The layer advertises three hours at PT10M, i.e. 19 intervals.
    max_time_steps = 19

    def discover(self, window: FetchWindow) -> list[RunCandidate]:
        client = self._geomet()
        capability = client.capabilities(LIGHTNING_LAYER)
        if capability.time is None:
            raise AdapterUnavailable(f"{LIGHTNING_LAYER} advertises no time dimension")
        times = _times_in_window(capability.time, window, max_steps=self.max_time_steps)
        if not times:
            raise AdapterUnavailable(
                f"{LIGHTNING_LAYER} advertises {capability.time.start.isoformat()}.."
                f"{capability.time.end.isoformat()}, which does not intersect the window"
            )
        return [
            RunCandidate(
                provider_run_id=f"{self.source_id}-{times[-1].strftime('%Y%m%dT%H%M%SZ')}",
                run_time=times[-1],
                urls=[client.url({"request": "GetCapabilities", "LAYERS": LIGHTNING_LAYER})],
                detail={"valid_times": [moment.isoformat() for moment in times]},
            )
        ]

    def fetch(self, candidate: RunCandidate, window: FetchWindow, workdir: Path) -> RunResult:
        client = self._geomet(workdir)
        numpy, xarray = _numpy(), _xarray()
        latitude, longitude = self.point
        times = self._candidate_times(candidate, window, LIGHTNING_LAYER)

        series = _sample_series(
            client, LIGHTNING_LAYER, latitude, longitude, times, expected_units="flash km-2 min-1"
        )
        observed: list[float | None] = []
        for index in range(len(times)):
            if not series.answered[index]:
                observed.append(None)
            else:
                observed.append(1.0 if (series.values[index] or 0.0) > 0.0 else 0.0)

        dataset = xarray.Dataset(
            {
                "lightning_observed": (
                    ("valid_time", "latitude", "longitude"),
                    _column(observed),
                    {
                        "units": "flag",
                        "flag_values": "0, 1",
                        "flag_meanings": "no_flash_density_reported flash_density_reported",
                        "geomet_layer": LIGHTNING_LAYER,
                        "semantics": (
                            "0 means the density grid answered for this cell and interval and reported no "
                            "flashes; missing means the query did not answer at all"
                        ),
                    },
                ),
                "lightning_strike": (
                    ("valid_time", "latitude", "longitude"),
                    _column(series.values),
                    {
                        "units": series.units or "flash km-2 min-1",
                        "original_units": series.units_raw or "flash/km²/min",
                        "geomet_layer": LIGHTNING_LAYER,
                        "long_name": series.title,
                        "semantics": (
                            "gridded flash density over the advertised interval; absence means no density was "
                            "reported for this cell, not an absence of lightning elsewhere"
                        ),
                    },
                ),
            },
            coords={
                "valid_time": _stamps(times),
                "latitude": numpy.array([latitude], dtype="float64"),
                "longitude": numpy.array([longitude], dtype="float64"),
            },
            attrs={"source": self.product, "endpoint": GEOMET_BASE_URL},
        )
        dataset = normalize_units(dataset)

        # As with radar: an interval series with no flashes anywhere is a
        # complete answer, so the density is declared only when it has values.
        fields = [RequiredField("lightning_observed", "flag", level="10-minute gridded interval")]
        if series.any_value:
            fields.append(
                RequiredField(
                    "lightning_strike",
                    str(dataset["lightning_strike"].attrs.get("units", "")),
                    level="10-minute gridded interval",
                    optional=True,
                )
            )
        manifest = RunManifest(source_id=self.source_id, fields=tuple(fields), required_valid_times=times)
        validation = validate_run(manifest, dataset, window=window, decode_errors=series.errors)

        path = workdir / "eccc-lightning.zarr.zip"
        write_zarr(dataset, path)

        provenance = _base_provenance(
            self.source_id, self.adapter_version, self.product, "2.5 km gridded density, sampled at points"
        )
        provenance.update(
            {
                "quality": validation.as_quality(),
                "coverage": validation.as_coverage(),
                "run_time": times[-1].isoformat(),
                "valid_times": [moment.isoformat() for moment in times],
                "layers": {
                    LIGHTNING_LAYER: _layer_provenance(
                        series, LIGHTNING_LAYER, "lightning_strike", "surface", "flash km-2 min-1"
                    )
                },
                "sample_points": [{"latitude": latitude, "longitude": longitude}],
                "notes": series.notes,
                "flags": series.errors,
            }
        )
        return RunResult(
            source_id=self.source_id,
            provider_run_id=candidate.provider_run_id,
            run_time=times[-1],
            retrieved_at=datetime.now(UTC),
            complete=validation.complete,
            qc_passed=validation.qc_passed,
            artifacts=[Artifact("lightning", MEDIA_ZARR, path, provenance)],
            native_crs="EPSG:4326",
            notes=f"Sampled {len(times)} lightning density intervals. {validation.detail}",
        )


# ---------------------------------------------------------------------------
# Time-independent vector layers: CAP alerts and AQHI
# ---------------------------------------------------------------------------


def avalon_probe_boxes(rows: int = 1, columns: int = 1) -> tuple[dict[str, float], ...]:
    """Tile the Avalon core box into query boxes, one request each.

    A vector ``GetFeatureInfo`` is resolved against a search area derived from
    the map resolution, so the query has to be a box rather than a point: a
    tight probe around a lattice point returns nothing even when a station sits
    a third of a degree away (verified live 2026-08-30). One box covering the
    whole Avalon core is therefore the default, and subdividing it is available
    for a layer dense enough to hit the ``feature_count`` ceiling.
    """
    if rows < 1 or columns < 1:
        raise ValueError("the probe needs at least one row and one column")
    south, north = AVALON_CORE_BOUNDS["south"], AVALON_CORE_BOUNDS["north"]
    west, east = AVALON_CORE_BOUNDS["west"], AVALON_CORE_BOUNDS["east"]
    lat_step = (north - south) / rows
    lon_step = (east - west) / columns
    return tuple(
        {
            "south": round(south + lat_step * row, 6),
            "north": round(south + lat_step * (row + 1), 6),
            "west": round(west + lon_step * column, 6),
            "east": round(west + lon_step * (column + 1), 6),
        }
        for row in range(rows)
        for column in range(columns)
    )


def _box_centre(bounds: Mapping[str, float]) -> tuple[float, float]:
    return (
        round((bounds["south"] + bounds["north"]) / 2, 6),
        round((bounds["west"] + bounds["east"]) / 2, 6),
    )


class _GeoMetVectorAdapter:
    """Shared retrieval for the two time-independent GeoJSON layers.

    Neither ``Current-Alerts`` nor ``AQHI-OBS`` carries a time dimension --
    confirmed live, both advertise no ``Dimension`` element at all. They are
    "current" layers whose features state their own timestamps, so run identity
    comes from the features, falling back to the service's own
    ``updateSequence``, and never from our wall clock.
    """

    source_id = ""
    adapter_version = ""
    product = ""
    layer = ""
    logical_name = ""
    probe_rows = 1
    probe_columns = 1
    feature_count = 50

    def __init__(
        self,
        client: GeoMetClient | None = None,
        *,
        probe_boxes: Sequence[Mapping[str, float]] | None = None,
    ) -> None:
        self._client = client
        self.probe_boxes = tuple(probe_boxes or avalon_probe_boxes(self.probe_rows, self.probe_columns))
        centres = [_box_centre(box) for box in self.probe_boxes]
        self.latitudes = tuple(sorted({centre[0] for centre in centres}))
        self.longitudes = tuple(sorted({centre[1] for centre in centres}))

    def _geomet(self, workdir: Path | None = None) -> GeoMetClient:
        if self._client is None:
            self._client = GeoMetClient(scratch_dir=workdir)
        elif workdir is not None and self._client.scratch_dir is None:
            self._client.scratch_dir = workdir
        return self._client

    def _feature_time(self, properties: Mapping[str, Any]) -> datetime | None:
        raise NotImplementedError

    def _feature_key(self, feature: Mapping[str, Any]) -> str:
        properties = feature.get("properties") or {}
        for key in ("_id", "id", "identifier", "properties.identifier", "properties.id"):
            value = properties.get(key)
            if value:
                return str(value)
        if feature.get("id"):
            return str(feature["id"])
        return json.dumps(feature, sort_keys=True, default=str)

    def _collect(self, client: GeoMetClient) -> tuple[dict[str, dict[str, Any]], dict[tuple[int, int], int], list[str]]:
        """Query every declared probe box, returning merged features and counts.

        The per-box count is what makes the run judgeable: a box whose query
        failed has no count, and a partially queried Avalon must not be able to
        claim it knows the answer for the whole area.
        """
        merged: dict[str, dict[str, Any]] = {}
        counts: dict[tuple[int, int], int] = {}
        errors: list[str] = []
        for box in self.probe_boxes:
            latitude, longitude = _box_centre(box)
            cell = (self.latitudes.index(latitude), self.longitudes.index(longitude))
            try:
                payload = client.feature_collection(
                    self.layer, latitude, longitude, resolve=True, feature_count=self.feature_count, bounds=box
                )
            except GeoMetError as error:
                errors.append(f"{self.layer} over {box}: {error}")
                continue
            features = [item for item in (payload.get("features") or []) if isinstance(item, Mapping)]
            counts[cell] = counts.get(cell, 0) + len(features)
            for feature in features:
                merged[self._feature_key(feature)] = dict(feature)
        return merged, counts, errors

    def _run_time(self, features: Sequence[Mapping[str, Any]], update_sequence: str | None) -> datetime | None:
        stamps = [
            moment
            for moment in (self._feature_time(feature.get("properties") or {}) for feature in features)
            if moment is not None
        ]
        if stamps:
            return max(stamps)
        return parse_iso_instant(update_sequence or "")

    def discover(self, window: FetchWindow) -> list[RunCandidate]:
        client = self._geomet()
        capability = client.capabilities(self.layer)
        merged, counts, errors = self._collect(client)
        features = list(merged.values())
        run_time = self._run_time(features, capability.update_sequence)
        if run_time is None:
            raise AdapterUnavailable(
                f"{self.layer} returned no feature timestamp and no parseable updateSequence; "
                "the run cannot be identified without inventing a time"
            )
        return [
            RunCandidate(
                provider_run_id=f"{self.source_id}-{run_time.strftime('%Y%m%dT%H%M%SZ')}",
                run_time=run_time,
                urls=[client.url({"request": "GetCapabilities", "LAYERS": self.layer})],
                detail={
                    "features": features,
                    "counts": {f"{row},{column}": value for (row, column), value in counts.items()},
                    "errors": errors,
                    "update_sequence": capability.update_sequence,
                },
            )
        ]

    def _counts_from_detail(self, detail: Mapping[str, Any]) -> dict[tuple[int, int], int]:
        parsed: dict[tuple[int, int], int] = {}
        for key, value in (detail.get("counts") or {}).items():
            row, _, column = str(key).partition(",")
            try:
                parsed[(int(row), int(column))] = int(value)
            except ValueError:
                continue
        return parsed


class ECCCCapAlertsGeoMetAdapter(_GeoMetVectorAdapter):
    """Active CAP hazards over the Avalon.

    An empty result is a real, publishable answer: *no alert is in force*. That
    is why the validated field is a per-cell count rather than the alerts
    themselves — zero is a genuine measurement here, whereas a cell whose query
    failed carries no count at all and drops the run's coverage below its floor.
    The features are published verbatim beside it so no CAP property name is
    ever interpreted, invented or renamed by this adapter.
    """

    source_id = "eccc-cap-alerts"
    adapter_version = "eccc-geomet-alerts-v1"
    product = "MSC current public alerts (CAP) via GeoMet WMS"
    layer = ALERTS_LAYER
    logical_name = "alerts"

    def _feature_time(self, properties: Mapping[str, Any]) -> datetime | None:
        for key in (
            "properties.effective",
            "effective",
            "properties.sent",
            "sent",
            "properties.onset",
            "onset",
        ):
            moment = parse_iso_instant(str(properties.get(key, "")))
            if moment is not None:
                return moment
        return None

    def fetch(self, candidate: RunCandidate, window: FetchWindow, workdir: Path) -> RunResult:
        client = self._geomet(workdir)
        numpy, xarray = _numpy(), _xarray()
        features = list(candidate.detail.get("features") or [])
        counts = self._counts_from_detail(candidate.detail)
        errors = list(candidate.detail.get("errors") or ())
        if not counts and not errors:
            merged, counts, errors = self._collect(client)
            features = list(merged.values())

        run_time = candidate.run_time or self._run_time(features, candidate.detail.get("update_sequence"))
        if run_time is None:
            raise AdapterUnavailable(f"{self.source_id}: the run carries no identifiable time")

        grid = numpy.full((1, len(self.latitudes), len(self.longitudes)), numpy.nan, dtype="float64")
        for (row, column), value in counts.items():
            grid[0, row, column] = float(value)

        dataset = xarray.Dataset(
            {
                "alerts_in_force": (
                    ("valid_time", "latitude", "longitude"),
                    grid,
                    {
                        "units": "count",
                        "geomet_layer": ALERTS_LAYER,
                        "semantics": (
                            "number of CAP alert features the service returned for this query point; 0 means "
                            "no alert is in force there, missing means the point was not successfully queried"
                        ),
                    },
                )
            },
            coords={
                "valid_time": _stamps((run_time,)),
                "latitude": numpy.array(self.latitudes, dtype="float64"),
                "longitude": numpy.array(self.longitudes, dtype="float64"),
            },
            attrs={"source": self.product, "endpoint": GEOMET_BASE_URL},
        )
        manifest = RunManifest(
            source_id=self.source_id,
            fields=(RequiredField("alerts_in_force", "count", level="surface"),),
            required_valid_times=(run_time,),
        )
        validation = validate_run(manifest, dataset, window=window, decode_errors=errors)

        grid_path = workdir / "eccc-cap-alerts.zarr.zip"
        write_zarr(dataset, grid_path)

        geojson_path = workdir / "eccc-cap-alerts.geojson"
        geojson_path.parent.mkdir(parents=True, exist_ok=True)
        geojson_path.write_text(
            json.dumps(
                {
                    "type": "FeatureCollection",
                    "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
                    "features": features,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            "utf-8",
        )

        provenance = _base_provenance(
            self.source_id, self.adapter_version, self.product, "vector features as published"
        )
        provenance.update(
            {
                "quality": validation.as_quality(),
                "coverage": validation.as_coverage(),
                "layer": self.layer,
                "run_time": run_time.isoformat(),
                "alerts_in_force": len(features),
                "alert_ids": sorted(self._feature_key(feature) for feature in features)[:50],
                "queried_boxes": len(counts),
                "declared_boxes": len(self.probe_boxes),
                "sample_boxes": [dict(box) for box in self.probe_boxes],
                "sampling": (
                    "GetFeatureInfo was resolved against each declared query box and the features merged by "
                    "identifier; a point-sized probe returns nothing for these vector layers"
                ),
                "update_sequence": candidate.detail.get("update_sequence"),
                "flags": errors,
            }
        )
        return RunResult(
            source_id=self.source_id,
            provider_run_id=candidate.provider_run_id,
            run_time=run_time,
            retrieved_at=datetime.now(UTC),
            complete=validation.complete,
            qc_passed=validation.qc_passed,
            artifacts=[
                Artifact(self.logical_name, MEDIA_ZARR, grid_path, provenance),
                Artifact(f"{self.logical_name}_features", MEDIA_GEOJSON, geojson_path, dict(provenance)),
            ],
            native_crs="EPSG:4326",
            notes=(
                f"Queried {len(counts)} of {len(self.probe_boxes)} Avalon probe box(es); "
                f"{len(features)} distinct alert(s) in force. {validation.detail}"
            ),
        )


class ECCCAqhiGeoMetAdapter(_GeoMetVectorAdapter):
    """AQHI station observations.

    AQHI is a dimensionless health index. It is never interchangeable with
    PM2.5, aerosol optical depth or extinction, so it is published under its own
    name with its own unit and no conversion of any kind.
    """

    source_id = "eccc-aqhi"
    adapter_version = "eccc-geomet-aqhi-v1"
    product = "Air Quality Health Index observations via GeoMet WMS"
    layer = AQHI_LAYER
    logical_name = "aqhi"
    # One query over the Avalon core box returned Grand Falls-Windsor, Burin and
    # St. John's on 2026-08-30, so the default single box already covers the
    # stations this experiment answers for.

    def _feature_time(self, properties: Mapping[str, Any]) -> datetime | None:
        for key in ("properties.observation_datetime", "observation_datetime"):
            moment = parse_iso_instant(str(properties.get(key, "")))
            if moment is not None:
                return moment
        return None

    def _feature_index(self, properties: Mapping[str, Any]) -> float | None:
        raw = properties.get("properties.aqhi", properties.get("aqhi"))
        try:
            return float(str(raw))
        except (TypeError, ValueError):
            return None

    def fetch(self, candidate: RunCandidate, window: FetchWindow, workdir: Path) -> RunResult:
        client = self._geomet(workdir)
        numpy, xarray = _numpy(), _xarray()
        features = list(candidate.detail.get("features") or [])
        errors = list(candidate.detail.get("errors") or ())
        if not features and not errors:
            merged, _counts, errors = self._collect(client)
            features = list(merged.values())

        observations: dict[tuple[datetime, float, float], float] = {}
        stations: list[dict[str, Any]] = []
        for feature in features:
            properties = feature.get("properties") or {}
            key = self._feature_key(feature)
            coordinates = (feature.get("geometry") or {}).get("coordinates") or []
            if len(coordinates) < 2:
                errors.append(f"{self.layer}: feature {key} carries no point geometry")
                continue
            longitude, latitude = round(float(coordinates[0]), 6), round(float(coordinates[1]), 6)
            index = self._feature_index(properties)
            if index is None:
                errors.append(f"{self.layer}: feature {key} carries no numeric AQHI")
                continue
            moment = self._feature_time(properties)
            if moment is None:
                errors.append(f"{self.layer}: feature {key} carries no observation time")
                continue
            if not window.covers(moment):
                # Kept as an error, not dropped quietly: a station reporting
                # outside the evidence window is a staleness fact the run must
                # not publish over.
                errors.append(
                    f"{self.layer}: feature {key} observed {moment.isoformat()}, outside "
                    f"{window.start.isoformat()}..{window.end.isoformat()}"
                )
                continue
            observations[(moment, latitude, longitude)] = index
            stations.append(
                {
                    "id": key,
                    "name": str(properties.get("properties.location_name_en", "")) or None,
                    "latitude": latitude,
                    "longitude": longitude,
                    "observed_at": moment.isoformat(),
                    "air_quality_health_index": index,
                }
            )

        if not observations:
            raise AdapterUnavailable(
                f"{self.source_id}: {AQHI_LAYER} returned no AQHI observation inside the window"
            )

        times = tuple(sorted({moment for moment, _, _ in observations}))
        latitudes = tuple(sorted({latitude for _, latitude, _ in observations}))
        longitudes = tuple(sorted({longitude for _, _, longitude in observations}))
        time_index = {moment: position for position, moment in enumerate(times)}
        lat_index = {value: position for position, value in enumerate(latitudes)}
        lon_index = {value: position for position, value in enumerate(longitudes)}

        grid = numpy.full((len(times), len(latitudes), len(longitudes)), numpy.nan, dtype="float64")
        for (moment, latitude, longitude), index in observations.items():
            grid[time_index[moment], lat_index[latitude], lon_index[longitude]] = index

        dataset = xarray.Dataset(
            {
                "air_quality_health_index": (
                    ("valid_time", "latitude", "longitude"),
                    grid,
                    {
                        "units": "index",
                        "geomet_layer": AQHI_LAYER,
                        "semantics": (
                            "Air Quality Health Index, a dimensionless health scale; it is not PM2.5, aerosol "
                            "optical depth or extinction and must never be converted to one"
                        ),
                    },
                )
            },
            coords={
                "valid_time": _stamps(times),
                "latitude": numpy.array(latitudes, dtype="float64"),
                "longitude": numpy.array(longitudes, dtype="float64"),
            },
            attrs={"source": self.product, "endpoint": GEOMET_BASE_URL},
        )

        # Stations are scattered points laid out on a (time x lat x lon) outer
        # product, so a batch of N observations can only ever fill N cells.
        # Mirrors ``ingest.adapters.eccc_ogc._coverage_floor``: what the check
        # then measures is the fraction of received observations that carried a
        # number, which is the real failure mode.
        cells = len(times) * len(latitudes) * len(longitudes)
        floor = min(1.0, 0.9 * len(observations) / cells) if cells else 1.0
        manifest = RunManifest(
            source_id=self.source_id,
            fields=(RequiredField("air_quality_health_index", "index", level="station"),),
            required_valid_times=times,
            min_coverage_fraction=floor,
        )
        validation = validate_run(manifest, dataset, window=window, decode_errors=errors)

        path = workdir / "eccc-aqhi.zarr.zip"
        write_zarr(dataset, path)

        run_time = times[-1]
        provenance = _base_provenance(
            self.source_id, self.adapter_version, self.product, "station observations as published"
        )
        provenance.update(
            {
                "quality": {
                    **validation.as_quality(),
                    "quantity": "air_quality_health_index",
                    "units": "index",
                    "note": "AQHI is a health index and is not PM2.5, AOD or extinction",
                },
                "coverage": validation.as_coverage(),
                "layer": self.layer,
                "run_time": run_time.isoformat(),
                "valid_times": [moment.isoformat() for moment in times],
                "stations": sorted(stations, key=lambda item: item["id"])[:100],
                "station_count": len(stations),
                "features_returned": len(features),
                "sample_boxes": [dict(box) for box in self.probe_boxes],
                "update_sequence": candidate.detail.get("update_sequence"),
                "flags": errors,
            }
        )
        return RunResult(
            source_id=self.source_id,
            provider_run_id=candidate.provider_run_id,
            run_time=run_time,
            retrieved_at=datetime.now(UTC),
            complete=validation.complete,
            qc_passed=validation.qc_passed,
            artifacts=[Artifact(self.logical_name, MEDIA_ZARR, path, provenance)],
            native_crs="EPSG:4326",
            notes=f"Ingested {len(observations)} AQHI observations from {len(stations)} stations. {validation.detail}",
        )


# ---------------------------------------------------------------------------
# Deterministic NWP families. Kept as working code; see MODEL_SOURCE_OWNER at
# the foot of this module for why they are not registered by default.
# ---------------------------------------------------------------------------


_ACCUMULATION_INTERVAL = re.compile(r"(?:PT|Accum)(\d+)h?", re.IGNORECASE)


def accumulation_interval_hours(layer: str) -> float:
    """Read the accumulation interval out of the layer identifier.

    ``HRDPS.CONTINENTAL.DIAG_PR_PT1H`` and ``RDPS_10km_Precip-Accum1h`` both
    state their own interval, so the accumulation is tagged with the provider's
    number and never divided into a rate.
    """
    match = _ACCUMULATION_INTERVAL.search(layer)
    if not match:
        raise GeoMetError(f"{layer} does not state its accumulation interval")
    return float(match.group(1))


@dataclass(frozen=True)
class ProfileResult:
    """A pressure-level relative-humidity profile and how it was obtained."""

    dataset: Any
    levels_hpa: tuple[int, ...]
    levels_returned: tuple[int, ...]
    reference_times: tuple[datetime, ...]
    errors: tuple[str, ...]
    notes: tuple[str, ...]
    layer_template: str
    valid_time: datetime


def humidity_profile(
    client: GeoMetClient,
    template: str,
    levels: Sequence[int],
    moment: datetime,
    point: tuple[float, float] = ST_JOHNS,
) -> ProfileResult | None:
    """Sample a pressure-level relative-humidity column at one time.

    ``HRDPS.CONTINENTAL.PRES_HR.{level}`` is the only vertical humidity profile
    this project has access to — Datamart's HRDPS bundles do not carry it — so
    it is exposed as a standalone function rather than being locked inside an
    adapter that may or may not be registered. It costs one polite request per
    level, which is why it is taken at a single valid time.

    Returns ``None`` when no level answered: an empty profile is not a profile.
    """
    numpy, xarray = _numpy(), _xarray()
    latitude, longitude = point
    values: list[float | None] = []
    errors: list[str] = []
    notes: list[str] = []
    references: set[datetime] = set()
    title = ""
    units: str | None = None
    units_raw: str | None = None
    ordered = tuple(levels)
    for level in ordered:
        series = _sample_series(
            client, template.format(level=level), latitude, longitude, (moment,), expected_units="percent"
        )
        errors.extend(series.errors)
        notes.extend(series.notes)
        references.update(series.reference_times)
        values.append(series.values[0])
        title = series.title or title
        units = series.units or units
        units_raw = series.units_raw or units_raw

    returned = tuple(level for level, value in zip(ordered, values, strict=True) if value is not None)
    if not returned:
        return None

    array = numpy.full((1, len(ordered), 1, 1), numpy.nan, dtype="float64")
    for index, value in enumerate(values):
        if value is not None:
            array[0, index, 0, 0] = value

    dataset = xarray.Dataset(
        {
            "relative_humidity": (
                ("valid_time", "pressure", "latitude", "longitude"),
                array,
                {
                    "units": units or "percent",
                    "original_units": units_raw or "%",
                    "long_name": title,
                    "geomet_layer_template": template,
                },
            )
        },
        coords={
            "valid_time": _stamps((moment,)),
            "pressure": numpy.array(ordered, dtype="float64"),
            "latitude": numpy.array([latitude], dtype="float64"),
            "longitude": numpy.array([longitude], dtype="float64"),
        },
        attrs={"endpoint": GEOMET_BASE_URL, "access": "WMS GetFeatureInfo"},
    )
    dataset["pressure"].attrs["units"] = "hPa"
    dataset = normalize_units(dataset)
    return ProfileResult(
        dataset=dataset,
        levels_hpa=ordered,
        levels_returned=returned,
        reference_times=tuple(sorted(references)),
        errors=tuple(errors),
        notes=tuple(notes),
        layer_template=template,
        valid_time=moment,
    )


class _GeoMetModelAdapter(_GeoMetPointAdapter):
    """Shared discovery and retrieval for the deterministic NWP families.

    HRDPS and RDPS differ only in which layers they name, so sampling, wind
    reconstruction, accumulation tagging, profile assembly and validation all
    live here.
    """

    surface: tuple[LayerBinding, ...] = ()
    wind: tuple[LayerBinding, ...] = ()
    precipitation: LayerBinding | None = None
    profile_template = ""
    profile_levels: tuple[int, ...] = PROFILE_LEVELS_HPA
    anchor_layer = ""
    resolution = ""
    max_time_steps = 25

    def __init__(
        self,
        client: GeoMetClient | None = None,
        *,
        point: tuple[float, float] = ST_JOHNS,
        profile_levels: tuple[int, ...] | None = None,
        max_time_steps: int | None = None,
    ) -> None:
        super().__init__(client, point=point, max_time_steps=max_time_steps)
        if profile_levels is not None:
            self.profile_levels = profile_levels

    def discover(self, window: FetchWindow) -> list[RunCandidate]:
        client = self._geomet()
        capability = client.capabilities(self.anchor_layer)
        if capability.time is None:
            raise AdapterUnavailable(f"{self.anchor_layer} advertises no time dimension")
        if capability.reference_time is None:
            raise AdapterUnavailable(f"{self.anchor_layer} advertises no reference_time; the run is unidentifiable")
        run_time = capability.reference_time.default or capability.reference_time.end
        times = _times_in_window(capability.time, window, max_steps=self.max_time_steps)
        if not times:
            raise AdapterUnavailable(
                f"{self.anchor_layer} advertises {capability.time.start.isoformat()}.."
                f"{capability.time.end.isoformat()}, which does not intersect "
                f"{window.start.isoformat()}..{window.end.isoformat()}"
            )
        return [
            RunCandidate(
                provider_run_id=f"{self.source_id}-{run_time.strftime('%Y%m%dT%H%M%SZ')}",
                run_time=run_time,
                urls=[client.url({"request": "GetCapabilities", "LAYERS": self.anchor_layer})],
                detail={
                    "anchor_layer": self.anchor_layer,
                    "valid_times": [moment.isoformat() for moment in times],
                },
            )
        ]

    def fetch(self, candidate: RunCandidate, window: FetchWindow, workdir: Path) -> RunResult:
        client = self._geomet(workdir)
        numpy, xarray = _numpy(), _xarray()
        latitude, longitude = self.point
        times = self._candidate_times(candidate, window, self.anchor_layer)

        errors: list[str] = []
        notes: list[str] = []
        references: set[datetime] = set()
        variables: dict[str, Any] = {}
        layers: dict[str, Any] = {}
        fields: list[RequiredField] = []

        def record(series: _SeriesResult, binding: LayerBinding) -> None:
            errors.extend(series.errors)
            notes.extend(series.notes)
            references.update(series.reference_times)
            layers[binding.layer] = _layer_provenance(
                series, binding.layer, binding.variable, binding.level, binding.published_units
            )

        for binding in self.surface:
            series = _sample_series(
                client, binding.layer, latitude, longitude, times, expected_units=binding.published_units
            )
            record(series, binding)
            variables[binding.variable] = (
                ("valid_time", "latitude", "longitude"),
                _column(series.values),
                {
                    "units": series.units or binding.published_units,
                    "original_units": series.units_raw or binding.published_units,
                    "geomet_layer": binding.layer,
                    "level": binding.level,
                    "long_name": series.title,
                },
            )
            fields.append(RequiredField(binding.variable, binding.units_in_artifact, level=binding.level))

        speed_binding, direction_binding = self.wind
        speed = _sample_series(
            client, speed_binding.layer, latitude, longitude, times, expected_units=speed_binding.published_units
        )
        direction = _sample_series(
            client,
            direction_binding.layer,
            latitude,
            longitude,
            times,
            expected_units=direction_binding.published_units,
        )
        record(speed, speed_binding)
        record(direction, direction_binding)
        u_values: list[float | None] = []
        v_values: list[float | None] = []
        for speed_value, direction_value in zip(speed.values, direction.values, strict=True):
            if speed_value is None or direction_value is None:
                u_values.append(None)
                v_values.append(None)
                continue
            u_component, v_component = wind_components(speed_value, direction_value)
            u_values.append(u_component)
            v_values.append(v_component)
        wind_attrs = {
            "units": "m s-1",
            "original_units": f"{speed.units or 'm s-1'} + {direction.units or 'degree'}",
            "geomet_layer": f"{speed_binding.layer} + {direction_binding.layer}",
            "level": speed_binding.level,
            "semantics": "meteorological convention: direction is the bearing the wind comes from",
        }
        variables["wind_u_10m"] = (("valid_time", "latitude", "longitude"), _column(u_values), dict(wind_attrs))
        variables["wind_v_10m"] = (("valid_time", "latitude", "longitude"), _column(v_values), dict(wind_attrs))
        fields.append(RequiredField("wind_u_10m", "m s-1", level=speed_binding.level))
        fields.append(RequiredField("wind_v_10m", "m s-1", level=speed_binding.level))

        precip_interval: float | None = None
        if self.precipitation is not None:
            precip_interval = accumulation_interval_hours(self.precipitation.layer)
            series = _sample_series(
                client,
                self.precipitation.layer,
                latitude,
                longitude,
                times,
                expected_units=self.precipitation.published_units,
            )
            record(series, self.precipitation)
            variables[self.precipitation.variable] = (
                ("valid_time", "latitude", "longitude"),
                _column(series.values),
                {
                    "units": series.units or self.precipitation.published_units,
                    "original_units": series.units_raw or self.precipitation.published_units,
                    "geomet_layer": self.precipitation.layer,
                    "level": self.precipitation.level,
                    "long_name": series.title,
                },
            )
            fields.append(
                RequiredField(
                    self.precipitation.variable,
                    self.precipitation.units_in_artifact,
                    level=self.precipitation.level,
                )
            )

        dataset = xarray.Dataset(
            variables,
            coords={
                "valid_time": _stamps(times),
                "latitude": numpy.array([latitude], dtype="float64"),
                "longitude": numpy.array([longitude], dtype="float64"),
            },
            attrs={"source": self.product, "endpoint": GEOMET_BASE_URL, "access": "WMS GetFeatureInfo"},
        )
        dataset = normalize_units(dataset)
        if precip_interval is not None and self.precipitation is not None:
            dataset = normalize_precipitation(dataset, self.precipitation.variable, interval_hours=precip_interval)

        # The declared units are the bindings' own, taken from each layer's
        # published title and carried through normalize_units - never read back
        # out of the dataset, which would make the unit check tautological.
        manifest = RunManifest(source_id=self.source_id, fields=tuple(fields), required_valid_times=times)
        validation = validate_run(manifest, dataset, window=window, decode_errors=errors)

        surface_path = workdir / f"{self.source_id}-surface.zarr.zip"
        write_zarr(dataset, surface_path)

        run_time = max(references) if references else candidate.run_time
        provenance = _base_provenance(self.source_id, self.adapter_version, self.product, self.resolution)
        provenance.update(
            {
                "quality": validation.as_quality(),
                "coverage": validation.as_coverage(),
                "run_time": None if run_time is None else run_time.isoformat(),
                "valid_times": [moment.isoformat() for moment in times],
                "layers": layers,
                "sample_points": [{"latitude": latitude, "longitude": longitude}],
                "sampling": (
                    "WMS GetFeatureInfo answers one pixel at one time; the sample geometry is the single "
                    "declared point above, not a dense grid"
                ),
                "notes": notes,
                "flags": errors,
            }
        )
        artifacts = [Artifact("surface", MEDIA_ZARR, surface_path, provenance)]

        profile = self._profile_artifact(client, times[-1], window, workdir, run_time)
        if profile is not None:
            artifacts.append(profile)

        return RunResult(
            source_id=self.source_id,
            provider_run_id=candidate.provider_run_id,
            run_time=run_time,
            retrieved_at=datetime.now(UTC),
            complete=validation.complete,
            qc_passed=validation.qc_passed,
            artifacts=artifacts,
            native_crs="EPSG:4326",
            notes=(
                f"Sampled {len(dataset.data_vars)} variables over {len(times)} advertised valid times "
                f"from {len(layers)} GeoMet layers. {validation.detail}"
            ),
        )

    def _profile_artifact(
        self,
        client: GeoMetClient,
        moment: datetime,
        window: FetchWindow,
        workdir: Path,
        run_time: datetime | None,
    ) -> Artifact | None:
        if not self.profile_template or not self.profile_levels:
            return None
        profile = humidity_profile(client, self.profile_template, self.profile_levels, moment, self.point)
        if profile is None:
            return None
        manifest = RunManifest(
            source_id=self.source_id,
            fields=(RequiredField("relative_humidity", "percent", level="pressure levels"),),
            required_valid_times=(moment,),
        )
        validation = validate_run(manifest, profile.dataset, window=window, decode_errors=profile.errors)
        path = workdir / f"{self.source_id}-profile.zarr.zip"
        write_zarr(profile.dataset, path)
        provenance = _base_provenance(
            self.source_id,
            self.adapter_version,
            f"{self.product} pressure-level relative humidity",
            self.resolution,
        )
        provenance.update(
            {
                "quality": validation.as_quality(),
                "coverage": validation.as_coverage(),
                "run_time": (
                    profile.reference_times[-1].isoformat()
                    if profile.reference_times
                    else (None if run_time is None else run_time.isoformat())
                ),
                "valid_times": [moment.isoformat()],
                "levels_hpa": list(profile.levels_hpa),
                "levels_returned": list(profile.levels_returned),
                "layer_template": profile.layer_template,
                "sample_points": [{"latitude": self.point[0], "longitude": self.point[1]}],
                "notes": list(profile.notes),
                "flags": list(profile.errors),
            }
        )
        return Artifact("profile", MEDIA_ZARR, path, provenance)


class ECCCHrdpsGeoMetAdapter(_GeoMetModelAdapter):
    """HRDPS 2.5 km surface fields plus the pressure-level humidity profile."""

    source_id = "eccc-hrdps"
    adapter_version = "eccc-geomet-hrdps-v1"
    product = "HRDPS Continental 2.5 km via GeoMet WMS"
    resolution = "2.5 km continental grid, sampled at points"
    surface = HRDPS_SURFACE
    wind = HRDPS_WIND
    precipitation = HRDPS_PRECIP
    profile_template = HRDPS_PROFILE_TEMPLATE
    anchor_layer = "HRDPS.CONTINENTAL_TT"


class ECCCRdpsGeoMetAdapter(_GeoMetModelAdapter):
    """RDPS 10 km surface fields plus the pressure-level humidity profile."""

    source_id = "eccc-rdps"
    adapter_version = "eccc-geomet-rdps-v1"
    product = "RDPS 10 km via GeoMet WMS"
    resolution = "10 km regional grid, sampled at points"
    surface = RDPS_SURFACE
    wind = RDPS_WIND
    precipitation = RDPS_PRECIP
    profile_template = RDPS_PROFILE_TEMPLATE
    anchor_layer = "RDPS_10km_AirTemp_2m"


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

# Both this module and ``ingest.adapters.eccc_datamart`` can serve ``eccc-hrdps``
# and ``eccc-rdps``, and ``ingest.registry.register`` refuses a second adapter
# for the same id. The owner's decision is that Datamart keeps them: native
# GRIB2 gives strictly stronger provenance for a gridded forecast field - a real
# run time from the file's own stamp, native units, native CRS, real lead hours
# and a dense field - whereas GetFeatureInfo answers one pixel at one time, so
# the same field costs hundreds of polite requests and takes its provenance from
# a rendering service rather than from the source GRIB.
#
# The decision is one line, not a deletion: set this to "eccc_geomet" and the
# two model adapters register instead. It is deliberately NOT a try/except
# around ``register`` - a collision must stay loud.
MODEL_SOURCE_OWNER = "eccc_datamart"
_THIS_MODULE = "eccc_geomet"

RADAR_ADAPTER = register(ECCCRadarGeoMetAdapter())
LIGHTNING_ADAPTER = register(ECCCLightningGeoMetAdapter())
CAP_ALERTS_ADAPTER = register(ECCCCapAlertsGeoMetAdapter())
AQHI_ADAPTER = register(ECCCAqhiGeoMetAdapter())

HRDPS_ADAPTER = register(ECCCHrdpsGeoMetAdapter()) if MODEL_SOURCE_OWNER == _THIS_MODULE else None
RDPS_ADAPTER = register(ECCCRdpsGeoMetAdapter()) if MODEL_SOURCE_OWNER == _THIS_MODULE else None


__all__ = [
    "AQHI_LAYER",
    "ALERTS_LAYER",
    "CANONICAL_BY_GEOMET_UNIT",
    "ECCCAqhiGeoMetAdapter",
    "ECCCCapAlertsGeoMetAdapter",
    "ECCCHrdpsGeoMetAdapter",
    "ECCCLightningGeoMetAdapter",
    "ECCCRadarGeoMetAdapter",
    "ECCCRdpsGeoMetAdapter",
    "GeoMetClient",
    "GeoMetError",
    "GeoMetImage",
    "GeoMetNotAnImage",
    "GeoMetSample",
    "GeoMetServiceException",
    "HRDPS_PROFILE_TEMPLATE",
    "IMAGE_MAX_BYTES",
    "LIGHTNING_LAYER",
    "LayerBinding",
    "LayerCapability",
    "MAX_IMAGE_PIXELS",
    "MODEL_SOURCE_OWNER",
    "PROFILE_LEVELS_HPA",
    "ProfileResult",
    "RADAR_RAIN_LAYER",
    "RADAR_SNOW_LAYER",
    "RADAR_UNDETECTED_CLASS",
    "RDPS_PROFILE_TEMPLATE",
    "TimeExtent",
    "TimeOutsideExtent",
    "accumulation_interval_hours",
    "avalon_probe_boxes",
    "humidity_profile",
    "parse_capabilities",
    "parse_iso_duration",
    "parse_iso_instant",
    "parse_time_extent",
    "parse_title_units",
    "wind_components",
]
