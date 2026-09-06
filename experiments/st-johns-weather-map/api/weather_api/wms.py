"""Live-proxied map imagery from ECCC GeoMet, and the honesty rules around it.

Everything else this API serves is a *published artifact*: fetched by the
worker, validated against a manifest, QC-gated, written atomically and read back
from the store. The imagery here is not. A ``GetMap`` tile is rendered by
GeoMet at the moment the browser asks for it, and nothing about it passes
through the ingest spine.

That is a deliberate, owner-approved deviation, and it is only defensible while
the difference is *visible*. Two rules follow, and this module exists to keep
them:

1. Every layer and every response that comes from here is stamped
   ``evidence_basis`` = :data:`LIVE_PROXY`. A published artifact is stamped
   :data:`PUBLISHED_ARTIFACT`. A client can therefore refuse to treat a
   proxied frame as audited evidence, and can say so to the reader.
2. Nothing here is ever written into the store, counted in ``/timeline``,
   sampled by ``/point``, or allowed to promote a registry source to
   ``active``. ``operational`` stays false throughout.

Three further things this module refuses to do:

* **Invent a layer name.** The WMS layer for a published artifact is read from
  that artifact's own recorded provenance (``geomet_layer``). A layer with no
  recorded backing gets no imagery, not a guess.
* **Invent a time axis.** The forecast layers' frames come from
  ``GetCapabilities`` at request time. If capabilities cannot be read, the
  layer is offered with no frames and a notice, never with a generated range.
* **Invent a colour scale.** Legends are ECCC's own ``GetLegendGraphic``.

And one thing it insists on: a fully transparent PNG is a *reading*. Radar with
no echo answers about 334 bytes of nothing, and that means "retrieved, nothing
detected". It is not an outage and must never be reported as one.
"""

from __future__ import annotations

import logging
import contextvars
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from .store import EXPERIMENT_ROOT  # noqa: F401  (ensures ingest/ is importable)

LOGGER = logging.getLogger(__name__)

#: The two values ``evidence_basis`` may take, anywhere in this API.
PUBLISHED_ARTIFACT = "published_artifact"
LIVE_PROXY = "live_proxy"

#: Upstream requests one HTTP request to this API may cause. Scrubbing 28 hours
#: must not become hundreds of GeoMet calls, so the ceiling is enforced per
#: request as well as per minute. A cold ``/layers`` costs one capabilities
#: fetch per proxied spec (17 today); 32 leaves headroom for one more batch
#: without a cold request exhausting the budget and offering no proxies at all.
MAX_UPSTREAM_CALLS_PER_REQUEST = 32
#: Upstream requests this process may make in any rolling window.
PROCESS_BUDGET_CALLS = 240
PROCESS_BUDGET_WINDOW_SECONDS = 60.0

#: The rendered extent when the caller does not name one. The Avalon core box,
#: identical to the one the adapters probe.
DEFAULT_BOUNDS = {"south": 46.5, "west": -55.0, "north": 48.5, "east": -51.0}

#: Render size ceiling for a proxied tile. Above this one scrub of the timeline
#: would move tens of megabytes for no added legibility.
MAX_RENDER_PIXELS = 2048


class UpstreamBudgetExhausted(RuntimeError):
    """The bounded number of upstream calls for this request is spent."""


class WmsUnavailable(RuntimeError):
    """GeoMet could not be reached, or answered something that is not an image."""


class TimeNotAdvertised(WmsUnavailable):
    """The requested frame is outside what the layer advertises.

    Refused client-side, before any request. The service answers an
    unadvertised ``TIME`` with an HTTP 200 ``ServiceException``, so this is a
    "you asked for a frame that does not exist", not an outage - and the two
    must not be reported to the reader in the same way.
    """


class _CountingClient:
    """A ``PoliteClient`` that charges every real upstream call to a budget.

    Wrapping the transport rather than the OGC client is what makes the count
    honest: ``GeoMetClient`` serves capabilities and renders from its own TTL
    caches, and those cost nothing upstream. Only calls that actually leave the
    process reach here.
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def _charge(self) -> None:
        _spend_process_budget()
        budget = _active_budget.get()
        if budget is not None:
            budget.spend()

    def get(self, url: str, **kwargs: Any) -> Any:
        self._charge()
        return self._inner.get(url, **kwargs)

    def get_text(self, url: str) -> str:
        self._charge()
        return self._inner.get_text(url)

    def get_range(self, url: str, start: int, end: int | None = None) -> bytes:
        self._charge()
        return self._inner.get_range(url, start, end)

    def download(self, url: str, destination: Any, **kwargs: Any) -> Any:
        self._charge()
        return self._inner.download(url, destination, **kwargs)

    def close(self) -> None:
        self._inner.close()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


class _Budget:
    """A countdown of upstream calls one request may cause."""

    def __init__(self, limit: int = MAX_UPSTREAM_CALLS_PER_REQUEST) -> None:
        self.limit = limit
        self.spent = 0

    def spend(self) -> None:
        self.spent += 1
        if self.spent > self.limit:
            raise UpstreamBudgetExhausted(
                f"this request has already made {self.limit} upstream GeoMet calls; "
                "the rest is refused rather than fanned out"
            )


_process_calls: deque[float] = deque()
_process_lock = threading.Lock()


def _spend_process_budget() -> None:
    moment = time.monotonic()
    with _process_lock:
        while _process_calls and moment - _process_calls[0] > PROCESS_BUDGET_WINDOW_SECONDS:
            _process_calls.popleft()
        if len(_process_calls) >= PROCESS_BUDGET_CALLS:
            raise UpstreamBudgetExhausted(
                f"this process has made {PROCESS_BUDGET_CALLS} upstream GeoMet calls in the last "
                f"{int(PROCESS_BUDGET_WINDOW_SECONDS)} s; further calls are refused"
            )
        _process_calls.append(moment)


def reset_process_budget() -> None:
    """Test seam."""
    with _process_lock:
        _process_calls.clear()


# --------------------------------------------------------------- the client

_client: Any = None
_counting: _CountingClient | None = None
_client_lock = threading.Lock()

#: The budget charged by upstream calls made while handling *this* request.
#: A ContextVar, not a bound attribute: the counting client is shared by every
#: request in the process, and a plain attribute made concurrent requests
#: charge whichever budget was bound last - and unbind each other on exit - so
#: a burst of /raster fetches could exhaust /layers' budget and drop layers.
_active_budget: contextvars.ContextVar["_Budget | None"] = contextvars.ContextVar("geomet_request_budget", default=None)


def geomet_client() -> Any:
    """The one shared GeoMet client for this process.

    Shared deliberately: its capabilities and image caches are what stop a
    28-hour scrub from re-asking GeoMet the same question, and a per-request
    client would have neither.
    """
    global _client, _counting
    with _client_lock:
        if _client is None:
            from ingest.adapters.eccc_geomet import GeoMetClient  # noqa: PLC0415
            from ingest.http import PoliteClient  # noqa: PLC0415

            _counting = _CountingClient(PoliteClient())
            _client = GeoMetClient(client=_counting)
        return _client


def reset_client() -> None:
    """Test seam: drop the shared client and its caches."""
    global _client, _counting
    with _client_lock:
        if _client is not None:
            try:
                _client.close()
            except Exception:  # pragma: no cover - close is best effort
                LOGGER.debug("GeoMet client close failed", exc_info=True)
        _client, _counting = None, None
    reset_process_budget()


class budgeted:
    """Bind a per-request upstream budget for the duration of a block."""

    def __init__(self, limit: int = MAX_UPSTREAM_CALLS_PER_REQUEST) -> None:
        self.budget = _Budget(limit)

    def __enter__(self) -> _Budget:
        geomet_client()
        self._token = _active_budget.set(self.budget)
        return self.budget

    def __exit__(self, *_exc: object) -> None:
        _active_budget.reset(self._token)


# ------------------------------------------------- proxied forecast layers

@dataclass(frozen=True)
class ForecastLayerSpec:
    """One GeoMet forecast field offered as live-proxied imagery.

    Only the identity of the field is declared here. Its time axis, its units
    and its bounds are read from ``GetCapabilities`` - they are retrieved
    facts, and a hard-coded copy of them would go stale silently.

    ``product`` is the provider's product name as published in ``/layers``;
    ``semantics`` overrides :data:`LIVE_PROXY_SEMANTICS` for a layer that needs
    to say more about itself (a post-processed diagnostic is not a raw field).
    ``group`` overrides the ``forecast_proxy`` filing for a layer that is not a
    forecast at all (observed satellite imagery). ``legend`` records whether a
    live ``GetLegendGraphic`` probe answered ``image/png``; it is a retrieved
    fact and never assumed. The defaults keep the original HRDPS specs
    unchanged.
    """

    layer_id: str
    wms_layer: str
    field: str
    title: str
    product: str = "HRDPS"
    semantics: str | None = None
    group: str | None = None
    legend: bool = True


#: What a proxied layer says about itself, verbatim, in ``semantics``.
LIVE_PROXY_SEMANTICS = (
    "live-proxied imagery: rendered by ECCC GeoMet at request time. It is NOT a "
    "published artifact - it has not passed this experiment's ingest manifest, QC "
    "or atomic publication, and it is not sampled by /point or counted in "
    "/timeline. Display evidence only."
)

#: What the WEonG fog-visibility proxies say in addition. They are ECCC's
#: post-processed Weather Elements on Grid diagnostic, not a model field, and
#: nothing numeric is ever read off them: ``fog_state`` in ``/point`` is derived
#: from METAR/TAF present weather alone and never from these pixels.
WEONG_FOG_SEMANTICS = LIVE_PROXY_SEMANTICS + (
    " This is an ECCC Weather Elements on Grid (WEonG) post-processed fog "
    "diagnostic (visibility through fog, metres), not a raw model field: it is "
    "display evidence only, is not sampled by /point, and does not feed fog_state. "
    "HRDPS-WEonG corresponds to registry record eccc-hrdps-weg-prognos; RDPS-WEonG "
    "has no registry record."
)

#: Nine HRDPS continental fields, each verified rendering ``image/png`` against
#: the live service on 2026-08-30. ``HRDPS.CONTINENTAL_RT`` is deliberately
#: absent: its render came back 96 bytes and was not confirmed to carry a field,
#: and an unverified layer is not offered.
#:
#: Plus four WEonG fog-visibility diagnostics (HRDPS-WEonG 2.5 km and RDPS-WEonG
#: 10 km, liquid and ice fog), probed live on 2026-08-30: capabilities answered
#: with ``[m]`` titles and hourly extents, ``GetLegendGraphic`` answered
#: ``image/png``, and ``GetMap`` over the Avalon box answered ``image/png`` of
#: 390-531 bytes - a near-empty tile, which is a reading ("no fog rendered
#: here at that hour"), not an outage. ECCC marks the RDPS pair
#: ``[experimental]``; that flag is disclosed on the layer, never read as a
#: unit. Thirteen specs cost thirteen capability fetches on a cold cache,
#: inside :data:`MAX_UPSTREAM_CALLS_PER_REQUEST`.
FORECAST_LAYERS: tuple[ForecastLayerSpec, ...] = (
    ForecastLayerSpec("geomet-live-hrdps-tt", "HRDPS.CONTINENTAL_TT", "temperature", "HRDPS air temperature (live proxy)"),
    ForecastLayerSpec("geomet-live-hrdps-td", "HRDPS.CONTINENTAL_TD", "dew_point", "HRDPS dew point (live proxy)"),
    ForecastLayerSpec("geomet-live-hrdps-hr", "HRDPS.CONTINENTAL_HR", "relative_humidity", "HRDPS relative humidity (live proxy)"),
    ForecastLayerSpec("geomet-live-hrdps-wspd", "HRDPS.CONTINENTAL_WSPD", "wind_speed", "HRDPS wind speed (live proxy)"),
    ForecastLayerSpec("geomet-live-hrdps-wd", "HRDPS.CONTINENTAL_WD", "wind_direction", "HRDPS wind direction (live proxy)"),
    ForecastLayerSpec("geomet-live-hrdps-uu", "HRDPS.CONTINENTAL_UU", "wind_u", "HRDPS wind, u component (live proxy)"),
    ForecastLayerSpec("geomet-live-hrdps-pr", "HRDPS.CONTINENTAL_PR", "precipitation_accumulation", "HRDPS precipitation (live proxy)"),
    ForecastLayerSpec("geomet-live-hrdps-pn", "HRDPS.CONTINENTAL_PN", "mean_sea_level_pressure", "HRDPS mean sea level pressure (live proxy)"),
    ForecastLayerSpec("geomet-live-hrdps-nt", "HRDPS.CONTINENTAL_NT", "total_cloud_opacity", "HRDPS total cloud (live proxy)"),
    ForecastLayerSpec(
        "geomet-live-hrdps-weong-fog-liquid",
        "HRDPS-WEonG_2.5km_LiquidFogVisibility",
        "visibility_through_liquid_fog",
        "HRDPS-WEonG visibility through liquid fog (live proxy)",
        product="HRDPS-WEonG",
        semantics=WEONG_FOG_SEMANTICS,
    ),
    ForecastLayerSpec(
        "geomet-live-hrdps-weong-fog-ice",
        "HRDPS-WEonG_2.5km_IceFogVisibility",
        "visibility_through_ice_fog",
        "HRDPS-WEonG visibility through ice fog (live proxy)",
        product="HRDPS-WEonG",
        semantics=WEONG_FOG_SEMANTICS,
    ),
    ForecastLayerSpec(
        "geomet-live-rdps-weong-fog-liquid",
        "RDPS-WEonG_10km_LiquidFogVisibility",
        "visibility_through_liquid_fog",
        "RDPS-WEonG visibility through liquid fog (live proxy)",
        product="RDPS-WEonG",
        semantics=WEONG_FOG_SEMANTICS,
    ),
    ForecastLayerSpec(
        "geomet-live-rdps-weong-fog-ice",
        "RDPS-WEonG_10km_IceFogVisibility",
        "visibility_through_ice_fog",
        "RDPS-WEonG visibility through ice fog (live proxy)",
        product="RDPS-WEonG",
        semantics=WEONG_FOG_SEMANTICS,
    ),
)

#: What the GOES-East satellite proxies say about themselves. They are the one
#: proxied family that is *observed*: every frame is a picture the satellite
#: already took, so the layer can never fill the forward window and a client
#: must not scrub into the future expecting one.
SATELLITE_SEMANTICS = LIVE_PROXY_SEMANTICS + (
    " This is observed satellite imagery: NOAA GOES-East, relayed by ECCC GeoMet. "
    "Frames exist only for the past (the advertised extent ends at the latest "
    "received scan, about 15 minutes behind now); it is never forecast and no "
    "frame is offered forward of now. No value is read off the pixels: it is not "
    "sampled by /point and does not feed any field. The closest registry record "
    "is noaa-goes-east (category satellite); GeoMet serves ECCC's copy of that "
    "NOAA product."
)

#: Four GOES-East imagery layers, probed live on 2026-08-30 18:32Z (see
#: docs/geomet-layers.md): capabilities advertised ``<now-54h>/<now-~22min>/PT10M``
#: with titles ending ``[1 km]`` / ``[2 km]`` (a resolution, read separately and
#: never as a unit); ``GetMap`` over the Avalon box at the latest instant and at
#: now-2h answered ``image/png`` of 30-111 kB; ``GetLegendGraphic`` answered
#: ``image/png`` (an 82-byte, 35x5 strip), so ``legend`` stays True. The frames
#: are all in the past, which is the point: this family is observed, not forecast.
SATELLITE_LAYERS: tuple[ForecastLayerSpec, ...] = (
    ForecastLayerSpec(
        "geomet-live-goes-east-dayvis-nightir",
        "GOES-East_1km_DayVis-NightIR",
        "satellite_day_visible_night_ir",
        "GOES-East day visible / night IR (1 km, live proxy)",
        product="GOES-East",
        semantics=SATELLITE_SEMANTICS,
        group="satellite",
    ),
    ForecastLayerSpec(
        "geomet-live-goes-east-snowfog-nightmicro",
        "GOES-East_1km_SnowFog-NightMicrophysics",
        "satellite_snow_fog_night_microphysics",
        "GOES-East snow-fog / night microphysics (1 km, live proxy)",
        product="GOES-East",
        semantics=SATELLITE_SEMANTICS,
        group="satellite",
    ),
    ForecastLayerSpec(
        "geomet-live-goes-east-naturalcolor",
        "GOES-East_1km_NaturalColor",
        "satellite_natural_color",
        "GOES-East natural colour (1 km, live proxy)",
        product="GOES-East",
        semantics=SATELLITE_SEMANTICS,
        group="satellite",
    ),
    ForecastLayerSpec(
        "geomet-live-goes-east-nightir-2km",
        "GOES-East_2km_NightIR",
        "satellite_night_ir",
        "GOES-East night IR (2 km, live proxy)",
        product="GOES-East",
        semantics=SATELLITE_SEMANTICS,
        group="satellite",
    ),
)

#: Every spec offered as live-proxied imagery, in the order ``/layers`` resolves
#: them. Enumerate this, not :data:`FORECAST_LAYERS`, wherever "all proxies" is
#: meant; ``FORECAST_LAYERS`` keeps its name because those thirteen *are* forecasts.
PROXIED_LAYERS: tuple[ForecastLayerSpec, ...] = FORECAST_LAYERS + SATELLITE_LAYERS

_FORECAST_BY_ID = {spec.layer_id: spec for spec in PROXIED_LAYERS}

#: The ``X-Weather-Time-Semantics`` a satellite frame carries: the picture was
#: taken at that instant, as opposed to a forecast field being *valid* then.
SATELLITE_TIME_SEMANTICS = "observed at the instant in X-Weather-Valid-Time"


def forecast_spec(layer_id: str) -> ForecastLayerSpec | None:
    return _FORECAST_BY_ID.get(layer_id)


@dataclass(frozen=True)
class ForecastCoverage:
    """What ``GetCapabilities`` actually said about one proxied layer."""

    spec: ForecastLayerSpec
    times: tuple[datetime, ...]
    units: str
    cadence_seconds: int | None
    notice: str | None = None
    #: ECCC's own ``[experimental]`` flag on the capabilities title. Retrieved,
    #: disclosed, and never confused with the unit that precedes it.
    experimental: bool = False
    #: The pixel resolution ECCC states in a trailing ``[1 km]`` bracket, when
    #: it states one. Retrieved and disclosed in a notice; never a unit.
    resolution: str | None = None


def forecast_coverage(spec: ForecastLayerSpec) -> ForecastCoverage:
    """Read one proxied layer's real time axis and units from the service.

    Failure is reported as a layer with no frames and a notice. It is never a
    generated hourly range: a frame the service did not advertise is answered
    with ``NoMatch``, and offering one would make the client scrub into nothing.
    """
    client = geomet_client()
    try:
        capability = client.capabilities(spec.wms_layer)
    except Exception as error:
        LOGGER.warning("GeoMet capabilities unavailable for %s: %s", spec.wms_layer, error)
        return ForecastCoverage(
            spec=spec,
            times=(),
            units="unknown",
            cadence_seconds=None,
            notice=f"{spec.layer_id}: GeoMet did not answer capabilities for {spec.wms_layer}, so its frames are unknown ({error})",
        )
    from ingest.adapters.eccc_geomet import is_experimental, parse_title_resolution  # noqa: PLC0415

    extent = capability.time
    times = tuple(extent.steps()) if extent is not None else ()
    _raw, units, _recognised = capability.units
    cadence = None
    if extent is not None and extent.period is not None:
        cadence = int(extent.period.total_seconds())
    elif len(times) >= 2:
        cadence = int((times[1] - times[0]).total_seconds())
    title = getattr(capability, "title", None)
    experimental = is_experimental(title)
    # A ``[1 km]`` bracket is the imagery's pixel resolution. It is disclosed
    # as such; the unit stays whatever the title declared *besides* it, which
    # for satellite imagery is nothing, so ``units`` reads "unknown" rather
    # than a distance.
    resolution = parse_title_resolution(title)
    notices = []
    if experimental:
        notices.append(f"{spec.layer_id}: ECCC marks {spec.wms_layer} '[experimental]' in its capabilities title")
    if resolution:
        notices.append(f"{spec.layer_id}: ECCC advertises {resolution} pixel resolution for {spec.wms_layer}; that is not a unit")
    return ForecastCoverage(
        spec=spec,
        times=times,
        units=units or "unknown",
        cadence_seconds=cadence,
        notice="; ".join(notices) if notices else None,
        experimental=experimental,
        resolution=resolution,
    )


# ------------------------------------------------- artifact-backed layers

#: A recorded ``geomet_layer`` that names more than one WMS layer. The radar
#: adapter combines rain and snow into one artifact and records the pair as a
#: single string; that string is NOT a valid ``LAYERS`` value, and passing it
#: through would be answered with ``LayerNotDefined``. The pair is split and the
#: caller is told which member is being drawn rather than being handed a
#: composite that does not exist.
_COMBINED_SEPARATOR = " + "


def split_recorded_layers(recorded: str) -> list[str]:
    """The individual WMS layer names inside one recorded ``geomet_layer``."""
    return [piece.strip() for piece in recorded.split(_COMBINED_SEPARATOR) if piece.strip()]


@dataclass(frozen=True)
class ArtifactWmsBinding:
    """The WMS layer a published artifact was actually built from."""

    wms_layer: str
    recorded: str
    #: Every name the artifact recorded, in order, when it recorded more than
    #: one. The first is what gets drawn.
    alternatives: tuple[str, ...]

    @property
    def combined(self) -> bool:
        return len(self.alternatives) > 1


#: The keys an adapter may have recorded the WMS layer under, in the order they
#: are trusted. All three are *retrieved* provenance written at publication:
#: ``geomet_layer`` by the field-level records, ``layer`` by the single-layer
#: vector adapters, and ``layers`` by the adapters that queried more than one.
#: There is no fourth key and no fallback table - an artifact that recorded
#: none of these does not get imagery.
_LAYER_KEYS = ("geomet_layer", "layer", "layers")


def _recorded_names(provenance: Mapping[str, Any]) -> tuple[str, str] | None:
    """``(recorded, joined)`` - what was written, and the names inside it."""
    for key in _LAYER_KEYS:
        value = provenance.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip(), value.strip()
        if isinstance(value, Mapping) and value:
            names = [str(name).strip() for name in value if str(name).strip()]
            if names:
                return f"{key}={list(value)!r}", _COMBINED_SEPARATOR.join(names)
        if isinstance(value, (list, tuple)) and value:
            names = [str(name).strip() for name in value if str(name).strip()]
            if names:
                return f"{key}={list(value)!r}", _COMBINED_SEPARATOR.join(names)
    return None


def binding_from_provenance(provenance: Mapping[str, Any] | None) -> ArtifactWmsBinding | None:
    """Resolve the WMS layer from an artifact's own recorded provenance.

    Retrieved provenance only - there is no fallback map, and nothing is
    inferred from the layer id. An artifact that did not record where its
    numbers came from does not get imagery attached to it.
    """
    if not provenance:
        return None
    found = _recorded_names(provenance)
    if found is None:
        return None
    recorded, joined = found
    names = split_recorded_layers(joined)
    if not names:
        return None
    return ArtifactWmsBinding(wms_layer=names[0], recorded=recorded, alternatives=tuple(names))


# ----------------------------------------------------------------- renders

@dataclass(frozen=True)
class ProxiedImage:
    """One rendered image plus everything needed to say what it shows."""

    payload: bytes
    content_type: str
    wms_layer: str
    url: str
    style: str | None
    valid_time: datetime | None
    reference_time: datetime | None
    byte_size: int
    evidence_basis: str
    #: The CRS the tile was rendered in, read back from the request that made
    #: it; disclosed so a client can place the pixels in the right projection.
    crs: str = "EPSG:4326"

    def headers(self, *, layer_id: str, time_semantics: str | None = None) -> dict[str, str]:
        """Provenance a browser can read off the response itself.

        Every one of these is a retrieved fact. ``X-Weather-Retrieval-Status``
        is always ``retrieved`` here, because this object only exists when
        GeoMet answered with an image - which is exactly what distinguishes a
        transparent no-echo tile from an outage. An outage never reaches this
        function; it becomes a 502 with a reason.

        ``time_semantics`` lets a timed image say what its instant *means*
        (a satellite scan is observed then, a forecast field is valid then).
        It is ignored for an untimed image, which has its own statement.
        """
        headers = {
            "Cache-Control": "public, max-age=60",
            "X-Weather-Layer-Id": layer_id,
            "X-Weather-Data-Mode": "live",
            "X-Weather-Operational": "false",
            "X-Weather-Evidence-Basis": self.evidence_basis,
            # The bytes themselves are never a stored artifact: no artifact in
            # this experiment contains an image. Stated separately so a client
            # cannot read a published-artifact layer as having a published tile.
            "X-Weather-Image-Basis": LIVE_PROXY,
            "X-Weather-Retrieval-Status": "retrieved",
            "X-Weather-Render-Semantics": (
                "a fully transparent image means retrieved and nothing detected, not unavailable"
            ),
            "X-Weather-Wms-Layer": self.wms_layer,
            "X-Weather-Crs": self.crs,
            "X-Weather-Upstream-Url": self.url,
            "X-Weather-Byte-Size": str(self.byte_size),
            "X-Weather-Licence": "Environment and Climate Change Canada Data Servers End-use Licence",
            "X-Weather-Attribution": "Environment and Climate Change Canada - MSC GeoMet",
        }
        headers["X-Weather-Valid-Time"] = self.valid_time.isoformat() if self.valid_time else "none"
        # An image rendered without TIME (``Current-Alerts`` has no time
        # dimension) shows what the service holds *now*. Saying so here keeps a
        # client from stamping whatever instant it happened to be scrubbed to
        # onto a picture that was never indexed by time.
        headers["X-Weather-Time-Semantics"] = (
            (time_semantics or "valid at the instant in X-Weather-Valid-Time")
            if self.valid_time
            else "current image, not time-indexed: rendered without TIME from a layer that has no time dimension; it reflects the service at request time, not the requested instant"
        )
        headers["X-Weather-Reference-Time"] = self.reference_time.isoformat() if self.reference_time else "none"
        if self.style:
            headers["X-Weather-Style"] = self.style
        return headers


def _as_proxied(image: Any, *, evidence_basis: str) -> ProxiedImage:
    return ProxiedImage(
        payload=image.payload,
        content_type=image.content_type,
        wms_layer=image.layer,
        url=image.url,
        style=image.style,
        valid_time=image.valid_time,
        reference_time=image.reference_time,
        byte_size=image.byte_size,
        evidence_basis=evidence_basis,
        crs=getattr(image, "crs", "EPSG:4326"),
    )


#: The two CRS a proxied render may be asked for. Mirrors the client's own
#: ``SUPPORTED_GETMAP_CRS``; validated here as well so an unsupported value is
#: a 422 at the API boundary rather than a ValueError from deep inside.
SUPPORTED_RENDER_CRS = ("EPSG:4326", "EPSG:3857")


def render(
    wms_layer: str,
    *,
    evidence_basis: str,
    bounds: Mapping[str, float] | None = None,
    valid_time: datetime | None = None,
    width: int = 512,
    height: int = 512,
    style: str | None = None,
    crs: str = "EPSG:4326",
    image_format: str = "image/png",
    transparent: bool = True,
) -> ProxiedImage:
    """Render one tile, or raise with a reason that names what went wrong.

    Every failure mode of the client is turned into :class:`WmsUnavailable`
    carrying the upstream reason, so the endpoint can report *why* nothing was
    retrieved instead of a bare 500. The one thing that is not a failure is a
    small or empty image; that is returned like any other.
    """
    if width < 1 or height < 1 or width > MAX_RENDER_PIXELS or height > MAX_RENDER_PIXELS:
        raise ValueError(f"width and height must be between 1 and {MAX_RENDER_PIXELS}")
    if crs not in SUPPORTED_RENDER_CRS:
        raise ValueError(f"crs must be one of {', '.join(SUPPORTED_RENDER_CRS)}, not {crs!r}")
    client = geomet_client()
    try:
        image = client.map_image(
            wms_layer,
            dict(bounds or DEFAULT_BOUNDS),
            width=width,
            height=height,
            valid_time=valid_time,
            style=style,
            crs=crs,
            image_format=image_format,
            transparent=transparent,
        )
    except UpstreamBudgetExhausted:
        raise
    except ValueError:
        raise
    except Exception as error:
        from ingest.adapters.eccc_geomet import TimeOutsideExtent  # noqa: PLC0415

        if isinstance(error, TimeOutsideExtent):
            raise TimeNotAdvertised(f"{wms_layer}: {error}") from error
        raise WmsUnavailable(f"{wms_layer}: {type(error).__name__}: {error}") from error
    return _as_proxied(image, evidence_basis=evidence_basis)


def legend(wms_layer: str, *, evidence_basis: str, style: str | None = None) -> ProxiedImage:
    """ECCC's own colour ramp for a layer. Never a ramp of our own."""
    client = geomet_client()
    try:
        image = client.legend_graphic(wms_layer, style=style)
    except UpstreamBudgetExhausted:
        raise
    except Exception as error:
        raise WmsUnavailable(f"{wms_layer}: {type(error).__name__}: {error}") from error
    return _as_proxied(image, evidence_basis=evidence_basis)
