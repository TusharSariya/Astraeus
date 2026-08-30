"""HTTP surface for the St. John's weather evidence experiment.

The one rule this module exists to enforce: nothing is returned that was not
actually retrieved. There are exactly three data modes, decided once at startup
by ``WEATHER_DATA_MODE``:

``live``
    Read published artifacts. A store error, an unreadable artifact or an empty
    artifact set produces ``data_mode=unavailable`` with null values and
    provenance saying so. It never produces a number.
``fixture``
    Serve ``fixtures.py`` - deliberately synthetic weather, retained for
    development - with ``data_mode=fixture`` stamped on every single field.
``unavailable``
    What a missing or malformed ``WEATHER_DATA_MODE`` resolves to. Fail closed:
    a configuration mistake must never silently become fixture numbers.

There is deliberately no path from a live failure to a fixture value.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Response, status

from .fixtures import (
    AVALON_CORE_BOUNDS,
    BACK_HOURS,
    FORWARD_HOURS,
    LAYERS,
    NEWFOUNDLAND,
    SOURCES,
    now,
    point_fields,
    profile_levels,
    selected_forecast_fields,
    timeline,
    unavailable_forecast_fields,
    window_end,
    window_start,
)
from ingest.contract import MEDIA_COG, MEDIA_GEOJSON, MEDIA_PARQUET, MEDIA_ZARR

from .jobs import job_store
from .models import (
    CatalogResponse,
    CrossSectionRequest,
    CrossSectionResponse,
    DataMode,
    ErrorResponse,
    HealthResponse,
    Job,
    JobState,
    Layer,
    LayersResponse,
    PointResponse,
    ProfileResponse,
    ReadyResponse,
    RefreshRequest,
    Selection,
    SourceStatusResponse,
    TimelineItem,
    TimelineResponse,
)
from .science import select_fallback
from . import wms
from .store import (
    FIXTURE_MODE,
    LIVE_MODE,
    configured_mode,
    known_source_ids,
    LayerCoverage,
    layer_id_for,
    live_point_fields,
    live_profile_levels,
    live_store,
    registry_source_records,
    registry_source_statuses,
    schedulable_source_ids,
    source_category,
    unavailable_point_fields,
    unavailable_profile_levels,
)

LOGGER = logging.getLogger(__name__)

PREFIX = "/api/experiments/weather/v0"
PROFILE_PRESSURES = (1000, 850, 700, 500, 300)

# Product controls name registry sources, so selecting one can be checked
# against what is actually published rather than against a fixture table.
PRODUCT_SOURCE_IDS = {
    "HRDPS": "eccc-hrdps",
    "RDPS": "eccc-rdps",
    "REPS": "eccc-reps",
    "GFS": "noaa-gfs",
    "NOAA": "noaa-gfs",
    "IFS": "ecmwf-ifs",
    "ECMWF": "ecmwf-ifs",
    "ICON": "dwd-icon-global",
    "DWD": "dwd-icon-global",
}
CONSENSUS_PRODUCTS = {"consensus", "multi-centre"}
OBSERVATION_FIELDS = {"fog_state", "radar_echo", "visibility", "cloud_low", "cloud_middle", "cloud_high", "total_cloud", "wind_speed", "wind_gust"}
# Registry categories whose fields stay in a live ``/point`` response when a
# product is selected. A selected model never borrows another *model's* values,
# but an observation is not a competing model: a METAR visibility under an
# HRDPS header is still labelled ``awc-metar-speci`` on every field, so nothing
# is claimed for HRDPS that HRDPS did not publish. Read from the registry via
# ``source_category``, never from the shape of a source id.
#
# ``aviation`` is here because the registry files CYYT METAR/SPECI - the very
# cloud-layer, fog and visibility reports this exists to keep - under that
# category, not ``surface_observation``; the registry keeps ``aviation`` outside
# its own ``FORECAST_CATEGORIES``. Any field from an aviation source still
# carries that source's id, so a TAF-derived value could never read as METAR's.
OBSERVATION_CATEGORIES = frozenset({"surface_observation", "marine_observation", "optional_observation", "aviation", "radar", "satellite"})

# The registry files every AviationWeather.gov product under ``aviation``,
# including TAF, which is a forecast issued for an aerodrome, not a report of
# what was observed. A TAF value beside a selected model would be a second
# forecast presented as an observation, so it is excluded by name here. This
# is a registry smell (an ``aviation_forecast`` category would remove it) and
# the registry is owner-only, so the exclusion lives here and is tested.
FORECASTS_FILED_AS_OBSERVATIONS = frozenset({"awc-taf"})

app = FastAPI(title="St. John's Weather Evidence Experiment", version="0.1.0")


def response_mode() -> DataMode:
    """The default data mode for this deployment, before any retrieval."""
    mode = configured_mode()
    if mode == LIVE_MODE:
        return DataMode.LIVE
    if mode == FIXTURE_MODE:
        return DataMode.FIXTURE
    return DataMode.UNAVAILABLE


def fixture_mode() -> bool:
    return configured_mode() == FIXTURE_MODE


def unavailable_selection(reason: str) -> Selection:
    return Selection(mode="evidence_only", selected_source_id=None, selected_product_id=None, badge="evidence unavailable", reason=reason)


def skip_notices(store: object) -> list[str]:
    """Report artifacts that were dropped rather than letting them vanish."""
    return [f"artifact from {item.source_id} (revision {item.revision_id}) was skipped: {item.reason}" for item in getattr(store, "skipped", [])]


def requested_time(value: datetime | None) -> datetime:
    reference = now()
    if value is None:
        return reference
    if value.tzinfo is None:
        raise HTTPException(status_code=422, detail="valid_time must include a UTC offset")
    utc_value = value.astimezone(timezone.utc)
    start, end = window_start(reference), window_end(reference)
    if not start <= utc_value <= end:
        raise HTTPException(status_code=422, detail=f"valid_time is outside the available window {start.isoformat()} through {end.isoformat()}")
    return utc_value


def require_core_coverage(latitude: float, longitude: float) -> None:
    bounds = AVALON_CORE_BOUNDS
    if not (bounds["south"] <= latitude <= bounds["north"] and bounds["west"] <= longitude <= bounds["east"]):
        raise HTTPException(status_code=422, detail="coordinate is outside the Avalon core coverage")


@app.get(f"{PREFIX}/catalog", response_model=CatalogResponse)
def get_catalog() -> CatalogResponse:
    """The registry is the catalogue in every mode; it declares what may be
    retrieved, which is true independently of what has been."""
    return CatalogResponse(data_mode=response_mode(), generated_at=now(), sources=registry_source_records())


def _floor_to_hour(moment: datetime) -> datetime:
    """The hour bucket a frame belongs to, in UTC."""
    return moment.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)


def _window_items(reference: datetime, products_at: dict[datetime, list[str]] | None = None) -> list[TimelineItem]:
    """The 28 hourly steps, carrying only the products given for each hour."""
    start = window_start(reference)
    items: list[TimelineItem] = []
    for index in range(BACK_HOURS + FORWARD_HOURS + 1):
        valid_time = start + timedelta(hours=index)
        items.append(
            TimelineItem(
                valid_time_utc=valid_time,
                valid_time_newfoundland=valid_time.astimezone(NEWFOUNDLAND),
                available_products=sorted((products_at or {}).get(valid_time, [])),
            )
        )
    return items


@app.get(f"{PREFIX}/timeline", response_model=TimelineResponse)
def get_timeline() -> TimelineResponse:
    reference = now()
    start, end = window_start(reference), window_end(reference)
    if fixture_mode():
        return TimelineResponse(data_mode=DataMode.FIXTURE, start=start, end=end, items=timeline(reference))

    store = live_store()
    if store is None:
        return TimelineResponse(data_mode=DataMode.UNAVAILABLE, start=start, end=end, items=_window_items(reference), notices=["no live artifact store is reachable; no hour can be said to have a published product"])
    try:
        coverage = store.published_products()
    except Exception:
        LOGGER.exception("published product coverage could not be read")
        return TimelineResponse(data_mode=DataMode.UNAVAILABLE, start=start, end=end, items=_window_items(reference), notices=["the live artifact store raised while resolving published coverage"])

    notices = skip_notices(store)
    if not coverage:
        return TimelineResponse(data_mode=DataMode.UNAVAILABLE, start=start, end=end, items=_window_items(reference), notices=[*notices, "no artifacts are currently published for this window"])
    products_at: dict[datetime, list[str]] = {}
    for source_id, stamps in coverage.items():
        for stamp in stamps:
            # The timeline is an hourly index; artifacts land wherever their
            # own cadence puts them (radar at :18, lightning at :12). Keying on
            # the exact stamp meant only a frame that happened to fall on the
            # hour was ever counted, so an hour that genuinely holds evidence
            # read as empty. Floor to the hour the frame belongs to. This says
            # "this hour holds a published frame", not "the frame is at :00" -
            # the frame's own time stays exact in /layers.
            hour = _floor_to_hour(stamp)
            bucket = products_at.setdefault(hour, [])
            if source_id not in bucket:
                bucket.append(source_id)
    return TimelineResponse(data_mode=DataMode.LIVE, start=start, end=end, items=_window_items(reference, products_at), notices=notices)


#: Media types this API knows how to represent at all. A type absent here has
#: no map representation, and the layer index omits it with a notice rather than
#: guessing - an unrecognised artifact drawn as a raster would be invented weather.
RENDERABLE_MEDIA_TYPES = frozenset({MEDIA_ZARR, MEDIA_COG, MEDIA_GEOJSON, MEDIA_PARQUET})

#: Draw order. Observations sit above fields so a station reading is never
#: hidden beneath a raster it disagrees with.
Z_INDEX_BY_KIND = {"raster": 0, "mask": 10, "line": 20, "alert": 30, "point": 40}

#: What a layer may claim when its cadence cannot be derived - a single frame,
#: or an irregular one. It still needs a bound; without one a lone frame would
#: answer for the whole 28-hour window.
UNKNOWN_CADENCE_TOLERANCE_SECONDS = 900

#: A floor so a very fast layer does not become unresolvable between frames.
MIN_STALENESS_TOLERANCE_SECONDS = 60


def layer_kind(media_type: str, coverage: LayerCoverage | None) -> str | None:
    """How a published artifact may be drawn, or None if it may not be.

    The media type only says whether this API can read the artifact at all. What
    decides the representation is the geometry the artifact actually carries.
    Several adapters sample GeoMet by ``GetFeatureInfo``, which answers a single
    pixel; their artifact is a Zarr, but it holds a point series. Keying on the
    container would draw one sampled pixel as an area of weather, so geometry
    wins here and an artifact whose geometry is unknown is not offered.
    """
    normalized = media_type.split(";")[0].strip()
    if normalized not in RENDERABLE_MEDIA_TYPES and media_type not in RENDERABLE_MEDIA_TYPES:
        return None
    if normalized == MEDIA_GEOJSON or media_type == MEDIA_GEOJSON:
        return "alert"
    if coverage is None:
        return None
    return "raster" if coverage.gridded else ("point" if coverage.sites else None)


#: How a layer's geometry reads in a title. Keyed by the kind the artifact's
#: own coordinates decided, so the qualifier can never claim a geometry the
#: artifact does not hold.
_KIND_QUALIFIER = {"raster": "published grid", "point": "sampled points", "alert": "alert features", "line": "lines", "mask": "mask"}


def published_layer_title(artifact: Any, kind: str) -> str:
    """A title composed from what the adapter recorded, or the id when it recorded nothing.

    The grammar matches the proxied layers - product, then field, then a
    qualifier in brackets - so the two kinds of layer read alike. There is no
    prose table keyed by layer id: an artifact that recorded no ``product``
    keeps ``source_id logical_name`` rather than being given a nicer name it
    did not earn.
    """
    product = artifact.provenance.get("product")
    field = str(artifact.provenance.get("field", artifact.logical_name)).replace("_", " ")
    head = f"{product} {field}" if product else f"{artifact.source_id} {artifact.logical_name}"
    return f"{head} ({_KIND_QUALIFIER[kind]})"


def layer_source_id(layer_id: str, artifacts: list[Any]) -> str | None:
    """The source that published a layer, by the same id rule that named it."""
    for artifact in artifacts:
        if layer_id_for(artifact.source_id, artifact.logical_name) == layer_id:
            return artifact.source_id
    return None


def layer_group(evidence_basis: str, kind: str, group: str | None = None) -> str:
    """``forecast_proxy`` | ``published_model`` | ``observation`` | ``alert`` | ``satellite``, from basis and geometry.

    ``group`` is a proxied spec's own filing (``satellite`` for observed
    imagery), which overrides the default ``forecast_proxy`` for a live proxy
    that is not a forecast.
    """
    if evidence_basis == wms.LIVE_PROXY:
        return group or "forecast_proxy"
    if kind == "alert":
        return "alert"
    return "published_model" if kind == "raster" else "observation"


def staleness_tolerance_seconds(cadence_seconds: int | None) -> int:
    """How stale a frame may be before the layer must report unavailable.

    Half a cadence: within that, the requested time is genuinely nearer this
    frame than the next, which is what "nearest" is allowed to mean. Beyond it
    the client renders nothing rather than misdating an older frame as current.
    """
    if cadence_seconds is None or cadence_seconds <= 0:
        return UNKNOWN_CADENCE_TOLERANCE_SECONDS
    return max(MIN_STALENESS_TOLERANCE_SECONDS, cadence_seconds // 2)


#: The one upstream this API proxies imagery from.
GEOMET_ENDPOINT = "https://geo.weather.gc.ca/geomet/"

#: Proxied forecast imagery sits under the published rasters and above nothing.
#: It is drawn first so a stored artifact is never hidden beneath a live tile.
PROXY_Z_INDEX = -10


def _proxied_forecast_layers() -> tuple[list[Layer], list[str]]:
    """The GeoMet forecast fields offered as live-proxied imagery, with their real axes.

    This is the owner-approved deviation from the ingest spine, and the terms
    of it are enforced here: every layer is stamped ``live_proxy``, its
    semantics say in words that it is not a published artifact, and its frames
    are exactly what ``GetCapabilities`` advertised. A layer whose capabilities
    could not be read is offered with **no** frames and a notice - a generated
    hourly range would scrub into ``NoMatch`` and look like an outage.

    Nothing here is stored, and nothing here reaches ``/point``, ``/profile``
    or ``/timeline``: those read the artifact store and this never enters it.

    The satellite specs ride the same mechanism. Their frames are all in the
    past because the service advertises only scans already received; nothing
    here has to (or does) special-case that - the window intersection simply
    yields no forward frame, and the drawer says "no frame here".
    """
    layers: list[Layer] = []
    notices: list[str] = []
    reference = now()
    start, end = window_start(reference), window_end(reference)
    try:
        with wms.budgeted():
            coverages = [wms.forecast_coverage(spec) for spec in wms.PROXIED_LAYERS]
    except wms.UpstreamBudgetExhausted as error:
        return [], [f"live-proxied forecast layers were not resolved: {error}"]
    except Exception as error:  # the proxy must never take the layer index down
        LOGGER.exception("live-proxied forecast layers could not be resolved")
        return [], [f"live-proxied forecast layers are unavailable: {type(error).__name__}: {error}"]

    for coverage in coverages:
        if coverage.notice:
            notices.append(coverage.notice)
        # The advertised extent runs further forward than this experiment's
        # 28-hour window. Offering frames the rest of the API refuses would
        # scrub the client into 422s, so the layer carries the intersection and
        # the full extent is stated rather than quietly dropped.
        frames = [stamp for stamp in coverage.times if start <= stamp <= end]
        if coverage.times and len(frames) != len(coverage.times):
            notices.append(
                f"{coverage.spec.layer_id}: {coverage.spec.wms_layer} advertises "
                f"{coverage.times[0].isoformat()} through {coverage.times[-1].isoformat()}; "
                f"{len(frames)} of {len(coverage.times)} frames fall inside this experiment's window "
                f"{start.isoformat()}..{end.isoformat()} and only those are offered"
            )
        # ECCC's own "[experimental]" flag is shown, labelled, rather than
        # hidden: a reader must see that the provider itself has not made the
        # product operational.
        title = f"[experimental] {coverage.spec.title}" if coverage.experimental else coverage.spec.title
        layers.append(
            Layer(
                id=coverage.spec.layer_id,
                title=title,
                kind="raster",
                field=coverage.spec.field,
                product=coverage.spec.product,
                units=coverage.units,
                semantics=coverage.spec.semantics or wms.LIVE_PROXY_SEMANTICS,
                times=frames,
                cadence_seconds=coverage.cadence_seconds,
                staleness_tolerance_seconds=staleness_tolerance_seconds(coverage.cadence_seconds),
                z_index=PROXY_Z_INDEX,
                evidence_basis=wms.LIVE_PROXY,
                group=layer_group(wms.LIVE_PROXY, "raster", coverage.spec.group),
                raster_available=bool(frames),
                # A probed fact recorded on the spec, not an assumption that
                # every upstream layer has a colour ramp.
                legend_available=coverage.spec.legend,
                upstream_wms_layer=coverage.spec.wms_layer,
                upstream_endpoint=GEOMET_ENDPOINT,
            )
        )
    if any(layer.times for layer in layers):
        notices.append(
            "layers marked evidence_basis=live_proxy are rendered by ECCC GeoMet at request time. "
            "They did not pass this experiment's ingest manifest, QC or atomic publication, they are "
            "not stored, and they are absent from /timeline and /point. Present them as display "
            "evidence only."
        )
    return layers, notices


@app.get(f"{PREFIX}/layers", response_model=LayersResponse)
def get_layers() -> LayersResponse:
    if fixture_mode():
        return LayersResponse(data_mode=DataMode.FIXTURE, layers=LAYERS)

    store = live_store()
    if store is None:
        return LayersResponse(data_mode=DataMode.UNAVAILABLE, layers=[], notices=["no live artifact store is reachable; no layer can be offered"])
    try:
        artifacts = store.current()
    except Exception:
        LOGGER.exception("published artifacts could not be listed for the layer index")
        return LayersResponse(data_mode=DataMode.UNAVAILABLE, layers=[], notices=["the live artifact store raised while listing published artifacts"])
    if not artifacts:
        # Nothing is published, but the forward window can still be shown as
        # live-proxied imagery. It is offered here only because every one of
        # those layers announces itself as unpublished, unstored and un-QC'd.
        proxied, proxy_notices = _proxied_forecast_layers()
        notices = ["no artifacts are currently published", *proxy_notices]
        if not proxied:
            return LayersResponse(data_mode=DataMode.UNAVAILABLE, layers=[], notices=notices)
        return LayersResponse(data_mode=DataMode.LIVE, layers=sorted(proxied, key=lambda item: (item.z_index, item.id)), notices=notices)

    try:
        coverage = store.published_layer_times()
    except Exception:
        LOGGER.exception("published layer coverage could not be read")
        return LayersResponse(data_mode=DataMode.UNAVAILABLE, layers=[], notices=["the live artifact store raised while reading layer time coverage"])

    notices = skip_notices(store)
    layers: list[Layer] = []
    for artifact in artifacts:
        identifier = layer_id_for(artifact.source_id, artifact.logical_name)
        entry = coverage.get(identifier)
        kind = layer_kind(artifact.media_type, entry)
        if kind is None:
            # Better to offer nothing than to draw an artifact whose geometry
            # this API cannot vouch for.
            notices.append(f"{identifier} ({artifact.media_type}) has no map representation this API can vouch for; it is not offered as a layer")
            continue
        # The WMS layer imagery may be drawn from comes from the artifact's own
        # recorded provenance, or not at all. There is deliberately no fallback
        # table: guessing a layer name would attach a picture of the wrong
        # field to a real reading.
        binding = wms.binding_from_provenance(artifact.provenance)
        if binding is not None and binding.combined:
            notices.append(
                f"{identifier} records {binding.recorded!r}, which names {len(binding.alternatives)} WMS layers "
                f"and is not a valid LAYERS value; imagery is drawn from {binding.wms_layer} alone"
            )
        layers.append(
            Layer(
                id=identifier,
                title=published_layer_title(artifact, kind),
                kind=kind,
                field=str(artifact.provenance.get("field", artifact.logical_name)),
                product=str(artifact.provenance.get("product", artifact.source_id)),
                units=str(artifact.provenance.get("units", "mixed")),
                semantics=str(artifact.provenance.get("semantics", "published artifact; see field provenance")),
                times=list(entry.times) if entry else [],
                cadence_seconds=entry.cadence_seconds if entry else None,
                staleness_tolerance_seconds=staleness_tolerance_seconds(entry.cadence_seconds if entry else None),
                z_index=Z_INDEX_BY_KIND[kind],
                evidence_basis=wms.PUBLISHED_ARTIFACT,
                group=layer_group(wms.PUBLISHED_ARTIFACT, kind),
                raster_available=binding is not None,
                legend_available=binding is not None,
                upstream_wms_layer=binding.wms_layer if binding else None,
                upstream_endpoint=GEOMET_ENDPOINT if binding else None,
            )
        )

    # An adapter that published alert features alongside a sampled count of
    # them is one alert source, and both of its layers belong together. This
    # is read from what was published, not from the shape of an id.
    alert_sources = {artifact.source_id for artifact in artifacts if artifact.media_type.split(";")[0].strip() == MEDIA_GEOJSON}
    layers = [
        item.model_copy(update={"group": "alert"}) if item.group == "observation" and layer_source_id(item.id, artifacts) in alert_sources else item
        for item in layers
    ]

    proxied, proxy_notices = _proxied_forecast_layers()
    notices.extend(proxy_notices)
    layers.extend(proxied)

    if not layers:
        return LayersResponse(data_mode=DataMode.UNAVAILABLE, layers=[], notices=[*notices, "no published artifact has a known map representation"])
    layers.sort(key=lambda item: (item.z_index, item.id))
    return LayersResponse(data_mode=DataMode.LIVE, layers=layers, notices=notices)


def _unavailable_point(latitude: float, longitude: float, time: datetime, *, reason: str, flags: list[str], notices: list[str], source_id: str = "unavailable", product: str = "unavailable") -> PointResponse:
    return PointResponse(
        data_mode=DataMode.UNAVAILABLE,
        latitude=latitude,
        longitude=longitude,
        valid_time=time,
        selection=unavailable_selection(reason),
        fields=unavailable_point_fields(time, flags=flags, source_id=source_id, product=product),
        notices=notices,
    )


def _live_point(latitude: float, longitude: float, time: datetime, product: str | None) -> PointResponse:
    store = live_store()
    if store is None:
        return _unavailable_point(latitude, longitude, time, reason="no live artifact store is reachable", flags=["live_store_unreachable"], notices=["no live artifact store is reachable"])
    try:
        fields, consensus, sources = live_point_fields(store, latitude, longitude, time)
    except Exception:
        LOGGER.exception("live point sampling failed at %s,%s for %s", latitude, longitude, time.isoformat())
        return _unavailable_point(latitude, longitude, time, reason="the live artifact store raised while sampling", flags=["live_store_error"], notices=["the live artifact store raised while sampling published artifacts"])

    notices = skip_notices(store)
    if product and product.lower() not in CONSENSUS_PRODUCTS:
        selected = product.upper()
        source_id = PRODUCT_SOURCE_IDS.get(selected)
        if source_id is None:
            raise HTTPException(status_code=422, detail=f"unknown product: {product}")
        # A product control must never borrow another source's values. It is
        # checked before the generic "nothing stored" case so the reason names
        # the product the reader asked about even at the edge of the window,
        # where no source at all has an artifact.
        product_fields = [item for item in fields if item.provenance.source_id == source_id]
        if not product_fields:
            return _unavailable_point(
                latitude, longitude, time,
                reason=f"{selected} has no published artifact covering this coordinate and time",
                flags=[f"no_published_artifact:{source_id}"],
                notices=[*notices, f"{selected} ({source_id}) has no published artifact covering this coordinate and time"],
                source_id=source_id, product=selected,
            )
        # Observations are kept beside the selected model. They are not another
        # model's values: each field still carries its own source id, so a
        # METAR cloud layer under an HRDPS header is labelled awc-metar-speci,
        # never claimed for HRDPS. Other models (RDPS under HRDPS) stay out.
        observation_fields = [
            item for item in fields
            if item.provenance.source_id != source_id
            and item.provenance.source_id not in FORECASTS_FILED_AS_OBSERVATIONS
            and source_category(item.provenance.source_id) in OBSERVATION_CATEGORIES
        ]
        if observation_fields:
            observed_ids = sorted({item.provenance.source_id for item in observation_fields})
            notices = [*notices, f"observations from {', '.join(observed_ids)} are shown alongside {selected}; each carries its own source"]
        return PointResponse(
            data_mode=DataMode.LIVE, latitude=latitude, longitude=longitude, valid_time=time,
            selection=Selection(mode="fallback", selected_source_id=source_id, selected_product_id=selected.lower(), badge=f"{selected} selected model", reason=f"Selected model: {selected}"),
            fields=product_fields + observation_fields, notices=notices,
        )

    if not fields:
        return _unavailable_point(latitude, longitude, time, reason="no published artifact covers this coordinate and time", flags=["no_published_artifact"], notices=[*notices, "no published artifact covers this coordinate and time"])

    live_hrdps = "eccc-hrdps" in sources
    live_rdps = "eccc-rdps" in sources
    mode, badge, reason = select_fallback(consensus.available, hrdps_fresh=live_hrdps, rdps_fresh=live_rdps)
    if mode == "consensus":
        selected_source_id, selected_product_id = "multi-centre", "experimental-consensus"
    elif live_hrdps:
        selected_source_id, selected_product_id = "eccc-hrdps", "hrdps"
    elif live_rdps:
        selected_source_id, selected_product_id = "eccc-rdps", "rdps"
    else:
        selected_source_id, selected_product_id = None, None
    return PointResponse(
        data_mode=DataMode.LIVE, latitude=latitude, longitude=longitude, valid_time=time,
        selection=Selection(mode=mode, selected_source_id=selected_source_id, selected_product_id=selected_product_id, badge=badge, reason=reason),
        fields=fields, notices=notices,
    )


def _fixture_point(latitude: float, longitude: float, time: datetime, product: str | None, *, hrdps_fresh: bool, rdps_fresh: bool, consensus_evidence: bool) -> PointResponse:
    fields, consensus = point_fields(time)
    mode, badge, reason = select_fallback(consensus.available and consensus_evidence, hrdps_fresh=hrdps_fresh, rdps_fresh=rdps_fresh)
    observations = [item for item in fields if item.field in OBSERVATION_FIELDS]

    if product and product.lower() not in CONSENSUS_PRODUCTS:
        selected = product.upper()
        if selected not in PRODUCT_SOURCE_IDS:
            raise HTTPException(status_code=422, detail=f"unknown product: {product}")
        return PointResponse(
            data_mode=DataMode.FIXTURE, latitude=latitude, longitude=longitude, valid_time=time,
            selection=Selection(mode="fallback", selected_source_id=f"model-{selected.lower()}", selected_product_id=selected.lower(), badge=f"{selected} selected model", reason=f"Selected model: {selected}"),
            fields=selected_forecast_fields(time, selected) + observations,
        )

    if mode == "consensus":
        selected_source_id, selected_product_id = "multi-centre", "experimental-consensus"
    elif hrdps_fresh:
        fields = selected_forecast_fields(time, "HRDPS") + observations
        selected_source_id, selected_product_id = "eccc-hrdps", "hrdps"
    elif rdps_fresh:
        fields = selected_forecast_fields(time, "RDPS") + observations
        selected_source_id, selected_product_id = "eccc-rdps", "rdps"
    else:
        fields = unavailable_forecast_fields(time) + observations
        selected_source_id, selected_product_id = None, None
    return PointResponse(
        data_mode=DataMode.FIXTURE, latitude=latitude, longitude=longitude, valid_time=time,
        selection=Selection(mode=mode, selected_source_id=selected_source_id, selected_product_id=selected_product_id, badge=badge, reason=reason),
        fields=fields,
    )


@app.get(f"{PREFIX}/layers/{{layer_id}}/features")
def get_layer_features(
    layer_id: str,
    valid_time: datetime | None = Query(default=None, description="UTC instant; must be one the layer declares in /layers"),
) -> dict[str, object]:
    """Stored values for one layer at one frame, as GeoJSON.

    The client picks the frame from the layer's own declared times, so this
    endpoint does not snap: an exact time with nothing stored returns an empty
    collection and says why, rather than reaching for a neighbouring frame.
    """
    moment = requested_time(valid_time)
    if fixture_mode():
        return {"type": "FeatureCollection", "data_mode": DataMode.FIXTURE.value, "operational": False, "features": [], "notices": ["fixture mode publishes no stored features"]}

    store = live_store()
    if store is None:
        return {"type": "FeatureCollection", "data_mode": DataMode.UNAVAILABLE.value, "operational": False, "features": [], "notices": ["no live artifact store is reachable"]}
    try:
        features, coverage = store.layer_features(layer_id, moment)
    except Exception:
        LOGGER.exception("layer features could not be read for %s", layer_id)
        return {"type": "FeatureCollection", "data_mode": DataMode.UNAVAILABLE.value, "operational": False, "features": [], "notices": ["the live artifact store raised while reading this layer"]}

    notices = skip_notices(store)
    if coverage is None:
        raise HTTPException(status_code=404, detail=f"no layer {layer_id!r} is currently published")
    if not features:
        notices.append(f"{layer_id} publishes no stored value at {moment.isoformat()}; nothing has been substituted")
    return {
        "type": "FeatureCollection",
        "data_mode": (DataMode.LIVE if features else DataMode.UNAVAILABLE).value,
        "operational": False,
        "features": features,
        "notices": notices,
    }


#: The 501 a layer with no upstream imagery keeps. Unchanged in substance from
#: when nothing at all could be rendered: no gridded artifact carries an image,
#: and nothing is drawn from point samples.
NO_IMAGERY_DETAIL = (
    "{layer_id} has no published map image and records no upstream WMS layer to draw one from. "
    "No gridded artifact is available to render, no image is generated from point samples, and no "
    "layer name is guessed. Use /features for point and alert layers."
)


def _resolve_imagery(layer_id: str) -> tuple[str, str, str | None]:
    """The WMS layer for ``layer_id``: ``(wms_layer, evidence_basis, notice)``.

    Raises 404 when no such layer is published or proxied, and 501 when the
    layer exists but records nothing to draw from. The layer name is only ever
    taken from a proxied layer's own declaration or from a published artifact's
    recorded ``geomet_layer`` - never inferred from the id.
    """
    spec = wms.forecast_spec(layer_id)
    if spec is not None:
        return spec.wms_layer, wms.LIVE_PROXY, None

    store = live_store()
    if store is None:
        raise HTTPException(status_code=503, detail="no live artifact store is reachable; no layer can be resolved")
    try:
        artifacts = [item for item in store.current() if layer_id_for(item.source_id, item.logical_name) == layer_id]
    except Exception as error:
        LOGGER.exception("published artifacts could not be listed while resolving %s", layer_id)
        raise HTTPException(status_code=503, detail="the live artifact store raised while resolving this layer") from error
    if not artifacts:
        raise HTTPException(status_code=404, detail=f"no layer {layer_id!r} is currently published")

    for artifact in artifacts:
        binding = wms.binding_from_provenance(artifact.provenance)
        if binding is None:
            continue
        notice = None
        if binding.combined:
            # The radar adapter records "RADAR_1KM_RRAI + RADAR_1KM_RSNO" for
            # the combined field. That string is not a LAYERS value; passing it
            # through would be refused upstream as LayerNotDefined.
            notice = (
                f"the artifact records {binding.recorded!r}, which names {len(binding.alternatives)} WMS layers; "
                f"this image is {binding.wms_layer} alone"
            )
        return binding.wms_layer, wms.PUBLISHED_ARTIFACT, notice

    raise HTTPException(status_code=501, detail=NO_IMAGERY_DETAIL.format(layer_id=layer_id))


def _image_response(image: wms.ProxiedImage, *, layer_id: str, notice: str | None) -> Response:
    # A satellite frame is *observed* at its instant, not valid then the way
    # a forecast field is; the header says which, from the spec's own filing.
    spec = wms.forecast_spec(layer_id)
    time_semantics = wms.SATELLITE_TIME_SEMANTICS if spec is not None and spec.group == "satellite" else None
    headers = image.headers(layer_id=layer_id, time_semantics=time_semantics)
    if notice:
        headers["X-Weather-Wms-Layer-Notice"] = notice
    return Response(content=image.payload, media_type=image.content_type, headers=headers)


@app.get(f"{PREFIX}/layers/{{layer_id}}/raster", responses={501: {"model": ErrorResponse}})
def get_layer_raster(
    layer_id: str,
    valid_time: datetime | None = Query(default=None, description="UTC instant; snapped onto the frames the upstream layer advertises"),
    width: int = Query(default=512, ge=1, le=wms.MAX_RENDER_PIXELS),
    height: int = Query(default=512, ge=1, le=wms.MAX_RENDER_PIXELS),
    south: float = Query(default=AVALON_CORE_BOUNDS["south"], ge=-90, le=90),
    west: float = Query(default=AVALON_CORE_BOUNDS["west"], ge=-180, le=180),
    north: float = Query(default=AVALON_CORE_BOUNDS["north"], ge=-90, le=90),
    east: float = Query(default=AVALON_CORE_BOUNDS["east"], ge=-180, le=180),
    style: str | None = Query(default=None, description="an upstream style name; omitted means the layer's own default"),
) -> Response:
    """One map image, rendered upstream, with its provenance on the response.

    The image bytes are always live-proxied: no artifact in this experiment
    contains an image, so ``X-Weather-Image-Basis`` is always ``live_proxy``
    even when the *layer* is backed by a published artifact. What the layer's
    own evidence rests on is reported separately as ``X-Weather-Evidence-Basis``.

    The one thing this endpoint will not do is call an image an outage. A
    fully transparent PNG - radar with nothing to show, about 334 bytes - is a
    reading, and it is returned 200 with ``X-Weather-Retrieval-Status:
    retrieved`` like any other. Only a failure to retrieve produces an error
    status, and it says which failure.
    """
    moment = requested_time(valid_time)
    wms_layer, basis, notice = _resolve_imagery(layer_id)
    if south >= north or west >= east:
        raise HTTPException(status_code=422, detail="bounds must be a south-west to north-east box")
    try:
        with wms.budgeted():
            image = wms.render(
                wms_layer,
                evidence_basis=basis,
                bounds={"south": south, "west": west, "north": north, "east": east},
                valid_time=moment,
                width=width,
                height=height,
                style=style,
            )
    except wms.TimeNotAdvertised as error:
        raise HTTPException(status_code=422, detail=f"{layer_id}: {error}") from error
    except wms.UpstreamBudgetExhausted as error:
        raise HTTPException(status_code=429, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except wms.WmsUnavailable as error:
        # Nothing was retrieved, and nothing is substituted for it.
        raise HTTPException(status_code=502, detail=f"{layer_id}: no image was retrieved upstream: {error}") from error
    return _image_response(image, layer_id=layer_id, notice=notice)


@app.get(f"{PREFIX}/layers/{{layer_id}}/legend", responses={501: {"model": ErrorResponse}})
def get_layer_legend(
    layer_id: str,
    style: str | None = Query(default=None, description="an upstream style name; omitted means the layer's own default"),
) -> Response:
    """The upstream colour ramp for a layer, fetched rather than synthesised.

    A hand-written key over real pixels would be a fabricated legend, so the
    only ramp served is the one ECCC draws the layer with.
    """
    wms_layer, basis, notice = _resolve_imagery(layer_id)
    try:
        with wms.budgeted():
            image = wms.legend(wms_layer, evidence_basis=basis, style=style)
    except wms.UpstreamBudgetExhausted as error:
        raise HTTPException(status_code=429, detail=str(error)) from error
    except wms.WmsUnavailable as error:
        raise HTTPException(status_code=502, detail=f"{layer_id}: no legend was retrieved upstream: {error}") from error
    return _image_response(image, layer_id=layer_id, notice=notice)


@app.get(f"{PREFIX}/point", response_model=PointResponse)
def get_point(
    latitude: float = Query(default=47.5615, ge=-90, le=90),
    longitude: float = Query(default=-52.7126, ge=-180, le=180),
    valid_time: datetime | None = None,
    product: str | None = None,
    hrdps_fresh: bool = True,
    rdps_fresh: bool = True,
    consensus_evidence: bool = True,
) -> PointResponse:
    require_core_coverage(latitude, longitude)
    time = requested_time(valid_time)
    mode = configured_mode()
    if mode == FIXTURE_MODE:
        return _fixture_point(latitude, longitude, time, product, hrdps_fresh=hrdps_fresh, rdps_fresh=rdps_fresh, consensus_evidence=consensus_evidence)
    if mode == LIVE_MODE:
        return _live_point(latitude, longitude, time, product)
    return _unavailable_point(latitude, longitude, time, reason="WEATHER_DATA_MODE is not set to live or fixture", flags=["data_mode_unconfigured"], notices=["WEATHER_DATA_MODE is missing or malformed; this deployment fails closed"])


@app.get(f"{PREFIX}/profile", response_model=ProfileResponse)
def get_profile(
    latitude: float = Query(default=47.5615, ge=-90, le=90),
    longitude: float = Query(default=-52.7126, ge=-180, le=180),
    valid_time: datetime | None = None,
) -> ProfileResponse:
    require_core_coverage(latitude, longitude)
    time = requested_time(valid_time)
    if fixture_mode():
        return ProfileResponse(data_mode=DataMode.FIXTURE, latitude=latitude, longitude=longitude, valid_time=time, levels=profile_levels(time))

    def unavailable(reason: str, flag: str, notices: list[str]) -> ProfileResponse:
        return ProfileResponse(
            data_mode=DataMode.UNAVAILABLE, latitude=latitude, longitude=longitude, valid_time=time,
            levels=unavailable_profile_levels(time, PROFILE_PRESSURES, flags=[flag]), notices=[*notices, reason],
        )

    store = live_store()
    if store is None:
        reason = "no live artifact store is reachable" if configured_mode() == LIVE_MODE else "WEATHER_DATA_MODE is missing or malformed; this deployment fails closed"
        return unavailable(reason, "live_store_unreachable" if configured_mode() == LIVE_MODE else "data_mode_unconfigured", [])
    try:
        levels = live_profile_levels(store, latitude, longitude, time, PROFILE_PRESSURES)
    except Exception:
        LOGGER.exception("live profile sampling failed at %s,%s for %s", latitude, longitude, time.isoformat())
        return unavailable("the live artifact store raised while sampling published artifacts", "live_store_error", [])
    notices = skip_notices(store)
    if not levels:
        return unavailable("no published artifact carries a pressure-level profile here", "no_published_artifact", notices)
    return ProfileResponse(data_mode=DataMode.LIVE, latitude=latitude, longitude=longitude, valid_time=time, levels=levels, notices=notices)


@app.post(f"{PREFIX}/cross-section", response_model=CrossSectionResponse, responses={501: {"model": ErrorResponse}})
def cross_section(request: CrossSectionRequest) -> CrossSectionResponse:
    requested_time(request.valid_time)
    for coordinate in request.path:
        require_core_coverage(coordinate.latitude, coordinate.longitude)
    supported_fields = {"temperature", "dew_point", "relative_humidity", "wind_speed"}
    unknown_fields = set(request.fields) - supported_fields
    if unknown_fields:
        raise HTTPException(status_code=422, detail=f"unsupported profile fields: {', '.join(sorted(unknown_fields))}")
    raise HTTPException(status_code=501, detail="cross-section unavailable until normalized spatial arrays are implemented")


@app.get(f"{PREFIX}/sources/status", response_model=SourceStatusResponse)
def get_source_status() -> SourceStatusResponse:
    """Registry state per source. Recorded retrieval makes freshness measurable;
    it never promotes a source past the state the registry declares."""
    activity: dict[str, datetime] = {}
    notices: list[str] = []
    store = live_store()
    if store is not None:
        try:
            activity = store.source_activity()
        except Exception:
            LOGGER.exception("source activity could not be read")
            notices.append("the live artifact store raised while reading recorded retrievals")
    elif configured_mode() == LIVE_MODE:
        notices.append("no live artifact store is reachable; no retrieval can be reported")

    statuses = registry_source_statuses(activity)
    if fixture_mode():
        return SourceStatusResponse(data_mode=DataMode.FIXTURE, statuses=statuses, notices=["fixture deployment; registry state is reported without any live retrieval"])
    if not activity:
        return SourceStatusResponse(data_mode=DataMode.UNAVAILABLE, statuses=statuses, notices=notices or ["no live retrieval has been recorded for any source"])
    mode = DataMode.LIVE if all(item.data_mode == DataMode.LIVE for item in statuses) else DataMode.MIXED
    return SourceStatusResponse(data_mode=mode, statuses=statuses, notices=notices)


@app.post(f"{PREFIX}/refresh", response_model=Job, status_code=status.HTTP_202_ACCEPTED)
def refresh(request: RefreshRequest) -> Job:
    known = known_source_ids()
    unknown = set(request.source_ids) - known
    if unknown:
        raise HTTPException(status_code=422, detail=f"unknown source ids: {', '.join(sorted(unknown))}")
    schedulable = schedulable_source_ids()
    # A credential-required, retired or licence-review source cannot be
    # scheduled; accepting a job for one would promise work that cannot happen.
    rejected = set(request.source_ids) - schedulable
    if rejected:
        raise HTTPException(status_code=422, detail=f"source ids are not schedulable: {', '.join(sorted(rejected))}")
    source_ids = request.source_ids or sorted(schedulable)
    if not source_ids:
        raise HTTPException(status_code=422, detail="no schedulable source ids are available")

    if configured_mode() == LIVE_MODE:
        store = live_store()
        if store is None:
            raise HTTPException(status_code=503, detail="no live artifact store is reachable; a refresh cannot be queued")
        try:
            return _job_from_row(store.enqueue_job(source_ids, detail="refresh requested through the experiment API"))
        except Exception as error:
            LOGGER.exception("refresh could not be queued in the live store")
            raise HTTPException(status_code=503, detail="the live artifact store raised while queueing the refresh") from error
    if fixture_mode():
        return job_store.enqueue(source_ids)
    raise HTTPException(status_code=503, detail="WEATHER_DATA_MODE is missing or malformed; this deployment fails closed")


def _job_from_row(row: dict) -> Job:
    return Job(
        id=row["id"], state=JobState(row["state"]), created_at=row["created_at"], updated_at=row["updated_at"],
        source_ids=row["source_ids"], detail=row["detail"],
    )


@app.get(f"{PREFIX}/jobs/{{job_id}}", response_model=Job, responses={404: {"model": ErrorResponse}})
def get_job(job_id: str) -> Job:
    if configured_mode() == LIVE_MODE:
        store = live_store()
        if store is None:
            raise HTTPException(status_code=503, detail="no live artifact store is reachable; job state cannot be read")
        try:
            row = store.get_job(job_id)
        except Exception as error:
            LOGGER.exception("job %s could not be read from the live store", job_id)
            raise HTTPException(status_code=503, detail="the live artifact store raised while reading the job") from error
        if row is None:
            raise HTTPException(status_code=404, detail="job not found")
        return _job_from_row(row)
    job = job_store.get(job_id) if fixture_mode() else None
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@app.get(f"{PREFIX}/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", data_mode=response_mode(), time=datetime.now(timezone.utc))


def _evidence_boundary(store: object, reference: datetime) -> bool:
    """True when published artifacts actually cover the requested window."""
    try:
        coverage = store.published_products()
    except Exception:
        LOGGER.exception("evidence boundary could not be resolved for readiness")
        return False
    start, end = window_start(reference), window_end(reference)
    return any(start <= stamp <= end for stamps in coverage.values() for stamp in stamps)


@app.get(f"{PREFIX}/ready", response_model=ReadyResponse)
def ready() -> ReadyResponse:
    mode = configured_mode()
    if mode == FIXTURE_MODE:
        checks = {"data_mode_configured": True, "fixture_catalog": bool(SOURCES), "fixture_layers": bool(LAYERS), "job_store": True, "live_store": False}
        return ReadyResponse(data_mode=DataMode.FIXTURE, ready=True, checks=checks)
    if mode == LIVE_MODE:
        store = live_store()
        boundary = store is not None and _evidence_boundary(store, now())
        # Live readiness means evidence can actually be served: a reachable
        # store with published artifacts covering the window. Anything less is
        # not ready, however healthy the process is.
        checks = {"data_mode_configured": True, "registry_catalog": bool(registry_source_records()), "job_store": True, "live_store": store is not None, "evidence_boundary": boundary}
        ready_now = all(checks.values())
        return ReadyResponse(data_mode=DataMode.LIVE if ready_now else DataMode.UNAVAILABLE, ready=ready_now, checks=checks)
    return ReadyResponse(data_mode=DataMode.UNAVAILABLE, ready=False, checks={"data_mode_configured": False, "registry_catalog": bool(registry_source_records()), "job_store": True, "live_store": False, "evidence_boundary": False})
