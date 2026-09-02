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
from collections.abc import Sequence
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
from .ephemeris import EPHEMERIS_ID, EPHEMERIS_SHA256
from .models import (
    CatalogResponse,
    CrossSectionRequest,
    CrossSectionResponse,
    DataMode,
    ErrorResponse,
    HealthResponse,
    Job,
    JobState,
    InterpolationMethodItem,
    MethodRequirement,
    Layer,
    LayerFrame,
    LayerRunSummary,
    LayersResponse,
    MethodScore,
    MethodsResponse,
    PointResponse,
    ProfileResponse,
    ReadyResponse,
    RefreshRequest,
    Selection,
    SourceStatusResponse,
    CoverageEntry,
    HorizonTier,
    TimelineItem,
    TimelineResponse,
    AstronomyCoreWindow,
    AstronomyInterval,
    AstronomyMoon,
    AstronomyProvenance,
    AstronomyResponse,
)
from .models import (
    SolarWindLatest,
    SpaceWeatherReading,
    SpaceWeatherResponse,
    SpaceWeatherSeries,
    Freshness,
)
from .science import select_fallback
from . import astronomy, aurora, grids, satellite as goes_satellite, wms
from .config import WINDOW_BACK, WINDOW_STEPS, sliding_window
from .store import (
    FIXTURE_MODE,
    LIVE_MODE,
    SeriesData,
    StoreUnavailable,
    absence_state,
    configured_mode,
    last_valid_times,
    known_source_ids,
    LayerCoverage,
    layer_id_for,
    NO_RUN_CONCEPT_REASON,
    NO_RUN_TIME_REASON,
    live_point_fields,
    live_profile_levels,
    live_store,
    registry_source_records,
    registry_source_statuses,
    retained_layer_runs,
    retained_runs,
    run_stale_verdict,
    schedulable_source_ids,
    source_category,
    source_reach,
    source_has_run_concept,
    source_run_cadence_seconds,
    source_run_staleness,
    unavailable_point_fields,
    unavailable_profile_levels,
)
from .models import AGED_OUT_FLAG

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
OBSERVATION_FIELDS = {"fog_state", "radar_echo", "visibility", "cloud_low", "cloud_middle", "cloud_high", "total_cloud_opacity", "wind_speed", "wind_gust"}
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


def tier_boundary(reference: datetime) -> datetime:
    """Where the core tier ends and the planning tier begins.

    The core tier reaches exactly as far ahead as the evidence window reaches
    back, so this is ``WINDOW_BACK`` read forwards rather than a second
    24-hour constant written down here. The bound has one definition
    (``config.py``) and this is a use of it, not a restatement.
    """
    return reference + WINDOW_BACK


def horizon_tiers(reference: datetime) -> list[HorizonTier]:
    """The two tiers as valid-time ranges, core first.

    A tier names no source. Together they cover the window exactly, which is
    why an instant in neither tier is also an instant outside the window: one
    refusal, stated in both vocabularies.
    """
    boundary = tier_boundary(reference)
    return [
        HorizonTier(id="core", start=window_start(reference), end=boundary),
        HorizonTier(id="planning", start=boundary, end=window_end(reference)),
    ]


def tier_of(moment: datetime, reference: datetime) -> str | None:
    """Which tier an instant falls in, or ``None`` when it falls in neither.

    The boundary instant itself belongs to the core tier: it is served, and
    serving it twice would put the same hour in two ranges.
    """
    for tier in horizon_tiers(reference):
        if tier.start <= moment <= tier.end:
            return tier.id
    return None


def _outside_both_tiers_detail(reference: datetime) -> str:
    core, planning = horizon_tiers(reference)
    return (
        f"valid_time is outside the available window {core.start.isoformat()} through {planning.end.isoformat()}: "
        f"it falls in neither the core tier ({core.start.isoformat()} through {core.end.isoformat()}) "
        f"nor the planning tier ({planning.start.isoformat()} through {planning.end.isoformat()}), "
        "and nothing from the nearest covered instant is substituted for it"
    )


def requested_time(value: datetime | None) -> datetime:
    reference = now()
    if value is None:
        return reference
    if value.tzinfo is None:
        raise HTTPException(status_code=422, detail="valid_time must include a UTC offset")
    utc_value = value.astimezone(timezone.utc)
    if tier_of(utc_value, reference) is None:
        raise HTTPException(status_code=422, detail=_outside_both_tiers_detail(reference))
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


def _aged_out_sources(store: object) -> tuple[dict[str, datetime], list[str]]:
    """Sources this deployment held and purged, with the last valid time each reached.

    An empty mapping with no notice means the store answered and holds no such
    record: every absence is then ``null``. An empty mapping WITH a notice
    means the record could not be read, and the caller must not present either
    absence state as if it knew which applied.

    A store that has no last-valid-time record at all - an older deployment,
    or one whose retention migration has not run - is treated as "nothing was
    ever held", which is the fail-closed answer: it under-claims rather than
    inventing evidence this deployment cannot show was here.
    """
    try:
        return last_valid_times(store), []
    except StoreUnavailable as error:
        LOGGER.warning("the last valid time record could not be read: %s", error)
        return {}, [f"the last valid time record could not be read, so no absence is reported as aged out: {error}"]
    except Exception as error:  # noqa: BLE001 - a missing table must not take the timeline down
        LOGGER.exception("the last valid time record could not be read")
        return {}, [f"the last valid time record could not be read, so no absence is reported as aged out: {type(error).__name__}: {error}"]


#: What is said about an instant no retained run covers, when the store did
#: answer. Never used for a store that could not be read: "nothing covers it"
#: is a statement about the evidence, not about the query.
NOTHING_COVERS = "nothing covers this instant"


def _coverage_entry(run: Any, reference: datetime) -> CoverageEntry:
    """One covering run, with its run age and staleness verdict.

    ``run_stale`` is only ever a verdict where both halves of the comparison
    are known: the adapter's own run time and the producer's declared run
    cadence. Either missing gives ``null`` with the reason, because ``false``
    would report an unmeasurable run as current.
    """
    cadence = source_run_cadence_seconds(run.source_id)
    age, stale, reason = run_stale_verdict(run.run_time, cadence, reference)
    return CoverageEntry(
        source_id=run.source_id,
        provider_run_id=run.provider_run_id,
        run_time=run.run_time,
        run_cadence_seconds=cadence,
        run_age_seconds=age,
        run_stale=stale,
        run_stale_reason=reason,
    )


def _coverage_index(runs: Sequence[Any], reference: datetime) -> dict[datetime, list[CoverageEntry]]:
    """Which retained runs cover each hour of the window.

    Two conditions, both required. The declared reach says how far the run was
    meant to carry, and the frames it actually published say how far it did.
    A reach with nothing retrieved behind it contributes nothing, and a run
    that published beyond its declared reach is not credited past the promise
    either.

    A run whose adapter declared no run time cannot be tested against a reach
    at all - the reach is stated relative to the run time - so such a run is
    credited only where it demonstrably published frames. That is narrower
    than the reach test, never wider, and it keeps the retrieval instant
    stamped on the run out of the containment test.
    """
    start = window_start(reference)
    index: dict[datetime, list[CoverageEntry]] = {}
    for run in runs:
        reach = source_reach(run.source_id)
        if reach is None:
            # No declared reach means not schedulable and served to nobody.
            continue
        if run.frame_start is None or run.frame_end is None:
            continue
        low, high = run.frame_start, run.frame_end
        if run.run_time is not None:
            reach_start, reach_end = reach.span(run.run_time)
            low, high = max(low, reach_start), min(high, reach_end)
        if low > high:
            continue
        entry = _coverage_entry(run, reference)
        for step in range(WINDOW_STEPS):
            hour = start + timedelta(hours=step)
            if low <= hour <= high:
                index.setdefault(hour, []).append(entry)
    return {
        hour: sorted(entries, key=lambda item: (item.source_id, item.run_time or datetime.min.replace(tzinfo=timezone.utc), item.provider_run_id))
        for hour, entries in index.items()
    }


def _window_items(
    reference: datetime,
    products_at: dict[datetime, list[str]] | None = None,
    *,
    aged_out: dict[str, datetime] | None = None,
    coverage_at: dict[datetime, list[CoverageEntry]] | None = None,
    coverage_resolved: bool = False,
) -> list[TimelineItem]:
    """The hourly steps of the sliding window, with only what each hour holds.

    ``aged_out`` names the sources whose frames this deployment held and
    purged, with the last valid time each reached. An hour that lists no
    product and names no aged-out source is an hour nothing ever covered; the
    two must stay distinguishable, or an emptied hour at the back edge reads
    as one that was never populated.
    """
    start = window_start(reference)
    stated = dict(sorted((aged_out or {}).items()))
    items: list[TimelineItem] = []
    for index in range(WINDOW_STEPS):
        valid_time = start + timedelta(hours=index)
        products = sorted((products_at or {}).get(valid_time, []))
        covering = (coverage_at or {}).get(valid_time, [])
        items.append(
            TimelineItem(
                valid_time_utc=valid_time,
                valid_time_newfoundland=valid_time.astimezone(NEWFOUNDLAND),
                available_products=products,
                # Stated per hour rather than once per response: an hour that
                # holds a product is not aged out, and one that holds nothing
                # needs the reason beside it, not in a footnote.
                aged_out_sources={} if products else stated,
                tier=tier_of(valid_time, reference),
                coverage=covering,
                # Only a store that answered can say nothing covers an hour.
                # With coverage unresolved the list is empty and silent, and
                # the response notices carry the failure instead.
                coverage_notice=NOTHING_COVERS if coverage_resolved and not covering else None,
            )
        )
    return items


def _resolved_coverage(store: object, reference: datetime) -> tuple[dict[datetime, list[CoverageEntry]], bool, list[str]]:
    """Per-hour coverage from declared reach against runs actually retrieved.

    Returns the index, whether the store answered at all, and any notice. An
    unreachable store gives an empty index with ``False``: no instant is then
    said to be covered, and none is said to be uncovered either.
    """
    try:
        runs = retained_runs(store)
    except StoreUnavailable as error:
        LOGGER.warning("retained runs could not be read: %s", error)
        return {}, False, [f"coverage could not be resolved, so no instant is reported as covered or uncovered: {error}"]
    except Exception as error:  # noqa: BLE001 - any failure is the same answer
        LOGGER.exception("retained runs could not be read")
        return {}, False, [f"coverage could not be resolved, so no instant is reported as covered or uncovered: {type(error).__name__}: {error}"]
    return _coverage_index(runs, reference), True, []


@app.get(f"{PREFIX}/timeline", response_model=TimelineResponse)
def get_timeline() -> TimelineResponse:
    reference = now()
    start, end = window_start(reference), window_end(reference)
    tiers = horizon_tiers(reference)
    boundary = tier_boundary(reference)
    if fixture_mode():
        # The tier is a property of the instant, so a fixture hour carries it
        # too. Its coverage stays empty: fixtures name products, and a fixture
        # has no retrieved run to be covered by.
        fixture_items = [item.model_copy(update={"tier": tier_of(item.valid_time_utc, reference)}) for item in timeline(reference)]
        return TimelineResponse(data_mode=DataMode.FIXTURE, start=start, end=end, items=fixture_items, boundary=boundary, tiers=tiers)

    store = live_store()
    if store is None:
        return TimelineResponse(data_mode=DataMode.UNAVAILABLE, start=start, end=end, items=_window_items(reference), boundary=boundary, tiers=tiers, notices=["no live artifact store is reachable; no hour can be said to have a published product"])
    try:
        coverage = store.published_products()
    except Exception:
        LOGGER.exception("published product coverage could not be read")
        # No hour is said to hold a product AND no hour is said to have aged
        # out: with the store unreadable, either claim would be a guess.
        return TimelineResponse(data_mode=DataMode.UNAVAILABLE, start=start, end=end, items=_window_items(reference), boundary=boundary, tiers=tiers, notices=["the live artifact store raised while resolving published coverage"])

    notices = skip_notices(store)
    aged_out, aged_out_notices = _aged_out_sources(store)
    notices.extend(aged_out_notices)
    coverage_at, coverage_resolved, coverage_notices = _resolved_coverage(store, reference)
    notices.extend(coverage_notices)
    if not coverage:
        return TimelineResponse(
            data_mode=DataMode.UNAVAILABLE, start=start, end=end,
            items=_window_items(reference, aged_out=aged_out, coverage_at=coverage_at, coverage_resolved=coverage_resolved),
            boundary=boundary, tiers=tiers,
            notices=[*notices, "no artifacts are currently published for this window"],
        )
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
    # A source with coverage is not aged out, whatever the record says it once
    # held: the record is the high-water mark, not a claim about now.
    still_held = {source_id for source_id, stamps in coverage.items() if stamps}
    return TimelineResponse(
        data_mode=DataMode.LIVE, start=start, end=end,
        items=_window_items(
            reference, products_at,
            aged_out={k: v for k, v in aged_out.items() if k not in still_held},
            coverage_at=coverage_at, coverage_resolved=coverage_resolved,
        ),
        boundary=boundary, tiers=tiers,
        notices=notices,
    )


#: Media types this API knows how to represent at all. A type absent here has
#: no map representation, and the layer index omits it with a notice rather than
#: guessing - an unrecognised artifact drawn as a raster would be invented weather.
RENDERABLE_MEDIA_TYPES = frozenset({MEDIA_ZARR, MEDIA_COG, MEDIA_GEOJSON, MEDIA_PARQUET})

#: Draw order. Observations sit above fields so a station reading is never
#: hidden beneath a raster it disagrees with.
Z_INDEX_BY_KIND = {"raster": 0, "mask": 10, "line": 20, "alert": 30, "point": 40}

#: What a layer may claim when its cadence cannot be derived - a single frame,
#: or an irregular one. It still needs a bound; without one a lone frame would
#: answer for the whole evidence window.
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

    One native interval of the layer itself: within its own resolution there is
    a frame that genuinely belongs to the requested instant, so a six-minute
    radar layer tolerates six minutes and a three-hourly planning layer three
    hours. Half a cadence answered a different question and refused frames a
    layer's own resolution says are the right ones. Beyond one interval the
    frame is still drawable, but only as a disclosed fallback naming its real
    time, never quietly as the requested instant.
    """
    if cadence_seconds is None or cadence_seconds <= 0:
        return UNKNOWN_CADENCE_TOLERANCE_SECONDS
    return max(MIN_STALENESS_TOLERANCE_SECONDS, cadence_seconds)


#: Said of a layer whose imagery is rendered upstream at request time. There is
#: a run behind it at the provider, but nothing is retained here to read a run
#: time from, so the verdict is unknown rather than false.
LIVE_PROXY_RUN_REASON = (
    "live-proxied layer: its frames are rendered upstream at request time and no run is retained here to date"
)

#: Said of every layer when the retained-run read itself failed. Unknown
#: retention is not an empty one, and every frame is still served.
RUNS_UNREADABLE_REASON = "retained runs could not be read, so no run staleness can be reported for this layer"

#: Said of a fixture layer. Fixtures name products; no run stands behind one,
#: and none is invented for it.
FIXTURE_RUN_REASON = "fixture layer: no run is retained behind it"


def _unattributed_layer(layer: Layer, reason: str) -> Layer:
    """Every frame served, none attributed to a run, with the reason said once.

    The frames list is still one entry per entry of ``times``, in the same
    order, so a client reads run attribution the same way for every layer and
    never has to infer an absent list means anything.
    """
    return layer.model_copy(
        update={
            "run_time": None,
            "run_stale": None,
            "run_stale_reason": reason,
            "run_cadence_seconds": None,
            "frames": [LayerFrame(valid_time=stamp) for stamp in layer.times],
            "runs": [],
        }
    )


def _attributed_layer(layer: Layer, source_id: str, runs: Sequence[Any], reference: datetime) -> Layer:
    """One layer's frames, each carrying the run that produced it.

    ``runs`` arrives newest first, so a frame both runs published is credited to
    the newer one and the previous run keeps exactly the leads the newer run
    does not reach. That is the short-cycle rule: the two runs are shown as two,
    the layer's ``times`` is their union, and no value is blended across the
    join or extrapolated past either run.

    A run-stale frame is served like any other. The flag travels with it so a
    reader can see the evidence is from a superseded run; withholding it would
    leave the instant answered by nothing at all.
    """
    verdicts: dict[str, tuple[bool | None, str | None, int | None]] = {}
    claimed: dict[datetime, Any] = {}
    for run in runs:
        _age, stale, reason, cadence = source_run_staleness(source_id, run.run_time, reference)
        verdicts[run.provider_run_id] = (stale, reason, cadence)
        for stamp in run.times:
            claimed.setdefault(stamp, run)

    times = sorted(set(layer.times) | set(claimed))
    frames: list[LayerFrame] = []
    counts: dict[str, int] = {}
    for stamp in times:
        run = claimed.get(stamp)
        if run is None:
            frames.append(LayerFrame(valid_time=stamp))
            continue
        stale, _reason, _cadence = verdicts[run.provider_run_id]
        frames.append(
            LayerFrame(valid_time=stamp, run_time=run.run_time, provider_run_id=run.provider_run_id, run_stale=stale)
        )
        counts[run.provider_run_id] = counts.get(run.provider_run_id, 0) + 1

    summaries = [
        LayerRunSummary(
            provider_run_id=run.provider_run_id,
            run_time=run.run_time,
            run_stale=verdicts[run.provider_run_id][0],
            frame_count=counts[run.provider_run_id],
        )
        for run in runs
        if counts.get(run.provider_run_id)
    ]
    if not summaries:
        # Nothing retained answers for this layer's frames. The layer is still
        # offered with every frame it published; only the attribution is absent.
        return _unattributed_layer(layer, NO_RUN_TIME_REASON)

    newest = summaries[0]
    stale, reason, cadence = verdicts[newest.provider_run_id]
    return layer.model_copy(
        update={
            "times": times,
            "run_time": newest.run_time,
            "run_stale": stale,
            "run_stale_reason": reason,
            "run_cadence_seconds": cadence,
            "frames": frames,
            "runs": summaries,
        }
    )


def _layer_artifact_key(layer: Layer, artifacts: Sequence[Any]) -> tuple[str, str] | None:
    """The ``(source_id, logical_name)`` of the artifact a layer is drawn from.

    A rendered grid, the cloud mask and the aurora oval carry ids of their own -
    one artifact can stand behind several rendered layers - so the mapping is
    read from the module that offered the layer rather than parsed back out of
    the id. Anything else is a generic published layer, whose id was formed by
    :func:`layer_id_for` and can be matched against the artifacts directly.
    """
    spec = grids.rendered_grid_spec(layer.id)
    if spec is not None:
        return spec.source_id, spec.logical_name
    if layer.id == goes_satellite.LAYER_ID:
        return goes_satellite.SOURCE_ID, goes_satellite.LOGICAL_NAME
    if layer.id == aurora.LAYER_ID:
        return aurora.SOURCE_ID, aurora.LOGICAL_NAME
    for artifact in artifacts:
        if layer_id_for(artifact.source_id, artifact.logical_name) == layer.id:
            return artifact.source_id, artifact.logical_name
    return None


def _with_run_attribution(
    layers: Sequence[Layer], artifacts: Sequence[Any], layer_runs: dict[str, list[Any]] | None, reason: str | None, reference: datetime
) -> list[Layer]:
    """Every layer, with its frames attributed to the runs that produced them.

    Applied in one pass over the assembled index so a layer offered by the
    satellite, aurora or rendered-grid modules carries run attribution on the
    same terms as a generic one, and no constructor has to remember to.
    """
    attributed: list[Layer] = []
    for layer in layers:
        if layer.evidence_basis == wms.LIVE_PROXY:
            attributed.append(_unattributed_layer(layer, LIVE_PROXY_RUN_REASON))
            continue
        if reason is not None:
            attributed.append(_unattributed_layer(layer, reason))
            continue
        key = _layer_artifact_key(layer, artifacts)
        if key is None:
            attributed.append(_unattributed_layer(layer, NO_RUN_TIME_REASON))
            continue
        source_id, logical_name = key
        if not source_has_run_concept(source_id):
            attributed.append(_unattributed_layer(layer, NO_RUN_CONCEPT_REASON))
            continue
        runs = (layer_runs or {}).get(layer_id_for(source_id, logical_name), [])
        attributed.append(_attributed_layer(layer, source_id, runs, reference))
    return attributed


def _layer_runs_or_reason(store: object) -> tuple[dict[str, list[Any]], str | None, list[str]]:
    """The retained runs per layer, or the reason there are none to report."""
    try:
        return retained_layer_runs(store), None, []
    except StoreUnavailable as error:
        LOGGER.warning("retained runs could not be read for the layer index: %s", error)
        return {}, RUNS_UNREADABLE_REASON, [f"{RUNS_UNREADABLE_REASON}: {error}"]
    except Exception as error:  # noqa: BLE001 - run attribution must not take the index down
        LOGGER.exception("retained runs could not be read for the layer index")
        return {}, RUNS_UNREADABLE_REASON, [f"{RUNS_UNREADABLE_REASON}: {type(error).__name__}: {error}"]


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
        # The advertised extent can run further than this experiment's
        # sliding window. Offering frames the rest of the API refuses would
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
        return LayersResponse(
            data_mode=DataMode.FIXTURE,
            layers=[_unattributed_layer(layer, FIXTURE_RUN_REASON) for layer in LAYERS],
        )

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
        aged_out, aged_notices = _aged_out_sources(store)
        notices = ["no artifacts are currently published", *proxy_notices, *aged_notices]
        # The aged-out names travel on both branches: a proxied layer is not
        # this deployment's stored evidence, so its presence says nothing about
        # whether the stored evidence aged out.
        if not proxied:
            return LayersResponse(data_mode=DataMode.UNAVAILABLE, layers=[], notices=notices, aged_out_sources=aged_out)
        proxied = _with_run_attribution(proxied, [], {}, None, now())
        return LayersResponse(data_mode=DataMode.LIVE, layers=sorted(proxied, key=lambda item: (item.z_index, item.id)), notices=notices, aged_out_sources=aged_out)

    try:
        coverage = store.published_layer_times()
    except Exception:
        LOGGER.exception("published layer coverage could not be read")
        return LayersResponse(data_mode=DataMode.UNAVAILABLE, layers=[], notices=["the live artifact store raised while reading layer time coverage"])

    notices = skip_notices(store)
    layers: list[Layer] = []
    for artifact in artifacts:
        if goes_satellite.claims(artifact):
            # The cloud-mask artifact is offered once, by the satellite
            # module below, with its real semantics; the generic entry would
            # duplicate it as an un-renderable published_model layer.
            continue
        if aurora.claims(artifact):
            # Same rule for the OVATION aurora grid: the aurora module below
            # lists it once, rendered, with its model disclosure.
            continue
        if grids.is_cloud_motion_logical_name(artifact.logical_name):
            # Derived display-support material (cloud motion for the
            # interpolation shader, for the retrieved grid and for each derived
            # one). It is not a layer, not evidence, and is served only through
            # /layers/{id}/flow with its derivation.
            continue
        if artifact.logical_name in grids.DERIVED_GRID_LOGICAL_NAMES:
            # A grid this experiment derived (today: the WEonG low-cloud
            # repair). It IS a layer, but it is offered below by
            # `rendered_grid_layers`, which is the only path that carries its
            # generated disclosure; the generic entry here would offer the same
            # grid a second time with no disclosure at all and no way to draw
            # it.
            continue
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

    # Cloud-strata grids rendered by this experiment from the stored GFS
    # artifact. Offered only where the artifact, the variable and its time
    # axis actually exist; a gap is a notice, never an invented layer.
    try:
        grid_layers, grid_notices = grids.rendered_grid_layers(store, Layer, z_index=Z_INDEX_BY_KIND["raster"], staleness=staleness_tolerance_seconds)
    except Exception as error:  # the grids must never take the layer index down
        LOGGER.exception("rendered-grid layers could not be resolved")
        grid_layers, grid_notices = [], [f"rendered-grid layers are unavailable: {type(error).__name__}: {error}"]
    layers.extend(grid_layers)
    notices.extend(grid_notices)

    # The GOES-19 cloud mask rendered by this experiment from the published
    # artifact. Same satellite group as the four proxied composites so the
    # processed and unprocessed views stand side by side; fail-closed
    # staleness so a feed gap is never shown as a clear sky.
    try:
        satellite_layers, satellite_notices = goes_satellite.satellite_layers(store, Layer, z_index=Z_INDEX_BY_KIND["raster"])
    except Exception as error:  # the cloud mask must never take the layer index down
        LOGGER.exception("the satellite cloud-mask layer could not be resolved")
        satellite_layers, satellite_notices = [], [f"the satellite cloud-mask layer is unavailable: {type(error).__name__}: {error}"]
    layers.extend(satellite_layers)
    notices.extend(satellite_notices)

    # The aurora oval rendered by this experiment from the stored OVATION
    # nowcast grid, filed with the other rendered grids. Fail-closed both
    # ways: an absent or stale grid removes the layer with a notice - a feed
    # gap is never rendered as absence of aurora.
    try:
        aurora_layer_list, aurora_notices = aurora.aurora_layers(store, Layer, z_index=Z_INDEX_BY_KIND["raster"])
    except Exception as error:  # the aurora layer must never take the layer index down
        LOGGER.exception("the aurora layer could not be resolved")
        aurora_layer_list, aurora_notices = [], [f"the aurora layer is unavailable: {type(error).__name__}: {error}"]
    layers.extend(aurora_layer_list)
    notices.extend(aurora_notices)

    proxied, proxy_notices = _proxied_forecast_layers()
    notices.extend(proxy_notices)
    layers.extend(proxied)

    if not layers:
        aged_out, aged_notices = _aged_out_sources(store)
        return LayersResponse(
            data_mode=DataMode.UNAVAILABLE, layers=[],
            notices=[*notices, *aged_notices, "no published artifact has a known map representation"],
            aged_out_sources=aged_out,
        )

    # Which run produced each frame, read from the same retained revisions the
    # timeline's coverage reads. A store that cannot answer costs the
    # attribution, never the frames: every layer is still offered, with the
    # reason its run staleness is unknown.
    layer_runs, runs_reason, run_notices = _layer_runs_or_reason(store)
    notices.extend(run_notices)
    layers = _with_run_attribution(layers, artifacts, layer_runs, runs_reason, now())

    layers.sort(key=lambda item: (item.z_index, item.id))
    return LayersResponse(data_mode=DataMode.LIVE, layers=layers, notices=notices)


def _unavailable_point(latitude: float, longitude: float, time: datetime, *, reason: str, flags: list[str], notices: list[str], source_id: str = "unavailable", product: str = "unavailable", last_valid_time: datetime | None = None) -> PointResponse:
    return PointResponse(
        data_mode=DataMode.UNAVAILABLE,
        latitude=latitude,
        longitude=longitude,
        valid_time=time,
        selection=unavailable_selection(reason),
        fields=unavailable_point_fields(time, flags=flags, source_id=source_id, product=product, last_valid_time=last_valid_time),
        notices=notices,
    )


def _aged_out_absence(store: object, source_ids: Sequence[str]) -> tuple[datetime | None, list[str], list[str]]:
    """Whether an absence over these sources is aged out, and how to say it.

    Returns the last valid time to carry (``None`` where nothing was ever
    held, which is the ``null`` absence), the QC flags, and notices. A store
    that cannot answer yields no flag at all: the response then reports plain
    ``unavailable``, because choosing between aged out and null on a guess
    would state a fact about this deployment's history that nobody knows.
    """
    held, notices = _aged_out_sources(store)
    recorded = {source_id: held[source_id] for source_id in source_ids if source_id in held}
    if not recorded:
        return None, [], notices
    latest = max(recorded.values())
    flags = [AGED_OUT_FLAG, *(f"{AGED_OUT_FLAG}:{source_id}" for source_id in sorted(recorded))]
    stated = ", ".join(f"{source_id} to {moment.isoformat()}" for source_id, moment in sorted(recorded.items()))
    return latest, flags, [*notices, f"held here and purged when it left the evidence window: {stated}"]


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
            # Which absence this is depends on whether the store ever held
            # frames for this source. "No published artifact" was one message
            # for two different facts; a reader could not tell a source that
            # aged out from one that was never retrieved.
            aged_at, aged_flags, aged_notices = _aged_out_absence(store, [source_id])
            reason = (
                f"{selected} aged out at {aged_at.isoformat()}: the frames this deployment held left the evidence window"
                if aged_at is not None
                else f"{selected} has no published artifact covering this coordinate and time"
            )
            return _unavailable_point(
                latitude, longitude, time,
                reason=reason,
                flags=[f"no_published_artifact:{source_id}", *aged_flags],
                notices=[*notices, *aged_notices, f"{selected} ({source_id}) has no published artifact covering this coordinate and time"],
                source_id=source_id, product=selected, last_valid_time=aged_at,
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
        aged_at, aged_flags, aged_notices = _aged_out_absence(store, sorted(known_source_ids()))
        reason = (
            f"aged out at {aged_at.isoformat()}: every frame this deployment held has left the evidence window"
            if aged_at is not None
            else "no published artifact covers this coordinate and time"
        )
        return _unavailable_point(
            latitude, longitude, time, reason=reason,
            flags=["no_published_artifact", *aged_flags],
            notices=[*notices, *aged_notices, "no published artifact covers this coordinate and time"],
            last_valid_time=aged_at,
        )

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


#: Rendered map imagery may be asked for in either CRS. EPSG:4326 stays the
#: default for compatibility; EPSG:3857 is what a web-mercator canvas shows,
#: and a tile requested in it corner-pins exactly with no client-side warp.
SUPPORTED_RASTER_CRS = wms.SUPPORTED_RENDER_CRS


def _validated_crs(crs: str) -> str:
    if crs not in SUPPORTED_RASTER_CRS:
        raise HTTPException(status_code=422, detail=f"crs must be one of {', '.join(SUPPORTED_RASTER_CRS)}, not {crs!r}")
    return crs


def _rendered_grid_raster(spec, *, moment, bounds, width, height, crs) -> Response:
    """A raster drawn here from the stored grid, with its provenance attached."""
    store = live_store()
    if store is None:
        raise HTTPException(status_code=503, detail="no live artifact store is reachable; the stored grid cannot be read")
    try:
        image = grids.render_grid(store, spec, bounds=bounds, width=width, height=height, crs=crs, valid_time=moment)
    except grids.GridNotPublished as error:
        raise HTTPException(status_code=404, detail=f"{spec.layer_id}: {error}") from error
    except grids.FrameNotStored as error:
        raise HTTPException(status_code=422, detail=f"{spec.layer_id}: {error}") from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except grids.GridUnavailable as error:
        # Nothing was read, and nothing is substituted for it.
        raise HTTPException(status_code=502, detail=f"{spec.layer_id}: no grid was read: {error}") from error
    return Response(content=image.payload, media_type=image.content_type, headers=image.headers(layer_id=spec.layer_id))


def _satellite_raster(*, moment, bounds, width, height, crs) -> Response:
    """The cloud-mask frame drawn here from the published artifact."""
    store = live_store()
    if store is None:
        raise HTTPException(status_code=503, detail="no live artifact store is reachable; the stored cloud mask cannot be read")
    try:
        image = goes_satellite.render_satellite(store, bounds=bounds, width=width, height=height, crs=crs, valid_time=moment)
    except grids.GridNotPublished as error:
        raise HTTPException(status_code=404, detail=f"{goes_satellite.LAYER_ID}: {error}") from error
    except grids.FrameNotStored as error:
        raise HTTPException(status_code=422, detail=f"{goes_satellite.LAYER_ID}: {error}") from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except grids.GridUnavailable as error:
        # Nothing was read, and nothing is substituted for it.
        raise HTTPException(status_code=502, detail=f"{goes_satellite.LAYER_ID}: no cloud-mask grid was read: {error}") from error
    return Response(content=image.payload, media_type=image.content_type, headers=image.headers())


def _aurora_raster(*, moment, bounds, width, height, crs) -> Response:
    """The aurora frame drawn here from the published OVATION artifact."""
    store = live_store()
    if store is None:
        raise HTTPException(status_code=503, detail="no live artifact store is reachable; the stored aurora grid cannot be read")
    try:
        image = aurora.render_aurora(store, bounds=bounds, width=width, height=height, crs=crs, valid_time=moment)
    except grids.GridNotPublished as error:
        raise HTTPException(status_code=404, detail=f"{aurora.LAYER_ID}: {error}") from error
    except grids.FrameNotStored as error:
        raise HTTPException(status_code=422, detail=f"{aurora.LAYER_ID}: {error}") from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except grids.GridUnavailable as error:
        # Nothing was read, and nothing is substituted for it.
        raise HTTPException(status_code=502, detail=f"{aurora.LAYER_ID}: no aurora grid was read: {error}") from error
    return Response(content=image.payload, media_type=image.content_type, headers=image.headers())


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
    crs: str = Query(default="EPSG:4326", description="EPSG:4326 (default) or EPSG:3857; the image is rendered in this projection"),
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
    requested_crs = _validated_crs(crs)
    if south >= north or west >= east:
        raise HTTPException(status_code=422, detail="bounds must be a south-west to north-east box")
    bounds = {"south": south, "west": west, "north": north, "east": east}

    grid_spec = grids.rendered_grid_spec(layer_id)
    if grid_spec is not None:
        return _rendered_grid_raster(grid_spec, moment=moment, bounds=bounds, width=width, height=height, crs=requested_crs)

    if layer_id == goes_satellite.LAYER_ID:
        return _satellite_raster(moment=moment, bounds=bounds, width=width, height=height, crs=requested_crs)

    if layer_id == aurora.LAYER_ID:
        return _aurora_raster(moment=moment, bounds=bounds, width=width, height=height, crs=requested_crs)

    wms_layer, basis, notice = _resolve_imagery(layer_id)
    # The four GOES-East satellite proxies are opaque imagery: JPEG carries the
    # same picture at roughly a third the bytes, and there is no transparency
    # to lose. Every other layer keeps transparent PNG, where "fully
    # transparent" is itself a reading. The content type on the response is
    # whatever the upstream actually declared - the client refuses a mismatch.
    spec = wms.forecast_spec(layer_id)
    satellite = spec is not None and spec.group == "satellite"
    try:
        with wms.budgeted():
            image = wms.render(
                wms_layer,
                evidence_basis=basis,
                bounds=bounds,
                valid_time=moment,
                width=width,
                height=height,
                style=style,
                crs=requested_crs,
                image_format="image/jpeg" if satellite else "image/png",
                transparent=not satellite,
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


@app.get(f"{PREFIX}/layers/{{layer_id}}/flow", responses={404: {"model": ErrorResponse}})
def get_layer_flow(
    layer_id: str,
    frame_from: datetime = Query(alias="from", description="the earlier published frame instant, exactly"),
    frame_to: datetime = Query(alias="to", description="the later published frame instant, exactly"),
    width: int = Query(default=512, ge=1, le=wms.MAX_RENDER_PIXELS),
    height: int = Query(default=512, ge=1, le=wms.MAX_RENDER_PIXELS),
    south: float = Query(default=AVALON_CORE_BOUNDS["south"], ge=-90, le=90),
    west: float = Query(default=AVALON_CORE_BOUNDS["west"], ge=-180, le=180),
    north: float = Query(default=AVALON_CORE_BOUNDS["north"], ge=-90, le=90),
    east: float = Query(default=AVALON_CORE_BOUNDS["east"], ge=-180, le=180),
    crs: str = Query(default="EPSG:4326", description="EPSG:4326 (default) or EPSG:3857; must match the frame rasters it will warp"),
    texture: str = Query(default="motion", description="'motion' (pairwise flow + display weight), 'tangents' (the pair's Hermite knot velocities), 'visibility' (the pair's per-frame fusion weights; only for a method whose shader is 'visibility') or 'residual' (the pair's per-cell envelope coefficients a, b of the computed advection residual; only for a method whose shader is 'residual-advection')"),
    method: str = Query(default=grids.DEFAULT_FLOW_METHOD, description="which interpolation method's fields to serve; see /methods"),
) -> Response:
    """The derived motion field between two adjacent published frames.

    Display-support material for the opt-in interpolation shader: a texture of
    per-pixel motion vectors computed offline between the two named frames
    (method and version in the headers), aligned pixel-for-pixel with the
    frame raster of the same bounds and size. `texture=tangents` adds the
    pair's cubic Hermite knot velocities so displayed motion is C1 across
    real frames; `texture=visibility` adds the pair's per-frame fusion
    weights, for a construction that lets the reliable warp carry a pixel
    instead of averaging it with an unreliable one; and `texture=residual`
    adds the pair's per-cell envelope coefficients (a, b in cloud percent,
    signed, scale fitted per request in `X-Weather-Flow-Scale`) for the
    construction that adds `t(1-t)(a + b t)` after the advection mix - the
    computed advection residual on an envelope that is zero at both real
    frames. Each per-shader texture is refused by name for a method whose
    registry shader does not evaluate it (`X-Weather-Flow-Shader` names the
    shader every served texture is meant for).
    It is a derivation, disclosed as such; it is never sampled,
    never a reading, and its absence is answered 404 - the client then falls
    back one honest rung (linear advection, then crossfade) and says so.
    """
    requested_crs = _validated_crs(crs)
    if south >= north or west >= east:
        raise HTTPException(status_code=422, detail="bounds must be a south-west to north-east box")
    grid_spec = grids.rendered_grid_spec(layer_id)
    if grid_spec is None:
        raise HTTPException(status_code=404, detail=f"{layer_id}: derived motion exists only for rendered-grid layers")
    store = live_store()
    if store is None:
        raise HTTPException(status_code=503, detail="no live artifact store is reachable; the derived motion cannot be read")
    try:
        image = grids.render_flow(
            store, grid_spec,
            frame_from=frame_from, frame_to=frame_to,
            bounds={"south": south, "west": west, "north": north, "east": east},
            width=width, height=height, crs=requested_crs, texture=texture, method=method,
        )
    except grids.FlowNotAvailable as error:
        raise HTTPException(status_code=404, detail=f"{layer_id}: {error}") from error
    except grids.GridNotPublished as error:
        raise HTTPException(status_code=404, detail=f"{layer_id}: {error}") from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except grids.GridUnavailable as error:
        raise HTTPException(status_code=502, detail=f"{layer_id}: no motion field was read: {error}") from error
    return Response(content=image.payload, media_type=image.content_type, headers=image.headers(layer_id=layer_id))


GENERATED_DISPLAY_OFF_NOTICE = "WEATHER_GENERATED_DISPLAY=off: generative constructions are not derived or offered"


def _generated_display_enabled() -> bool:
    """The deployment kill switch, read from the ingest package that honours it.

    Imported lazily like every other ingest symbol; a package that predates
    the switch is read as "on", which is the only value it could have had.
    """
    try:
        from ingest.derive.methods import generated_display_enabled  # noqa: PLC0415
    except Exception:  # noqa: BLE001 - an older or absent bench has no switch
        return True
    try:
        return bool(generated_display_enabled())
    except Exception:  # noqa: BLE001
        return True


def _optional_float(value: object) -> float | None:
    """A measured number, or None where nothing was measured - never a zero."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _applied_options(options: object) -> dict[str, bool]:
    """Which of a method's published options the derive actually applied.

    A method publishes every number it settled under ``options``; the
    switches among them are the key ``applied`` and every key ending
    ``_applied``. Anything else there is a measurement, not a switch.
    """
    if not isinstance(options, dict):
        return {}
    return {
        str(key): bool(value)
        for key, value in options.items()
        if (key == "applied" or str(key).endswith("_applied")) and isinstance(value, (bool, int, float))
    }


def _reduced_to_default(item: InterpolationMethodItem, applied: dict[str, bool]) -> bool:
    """Whether this method drew the default construction on this layer.

    True when an ingredient it needs is missing from the deployment, or when
    every switch it measured was refused: a hermite-shader method other than
    the baseline with nothing applied IS the baseline, and a method whose
    shader is another construction with nothing applied has fields the
    shader reduces to the plain advection mix.
    """
    if any(not requirement.met for requirement in item.requirements):
        return True
    if item.id == grids.DEFAULT_FLOW_METHOD:
        return False
    # Which switches are THIS method's own. Every method inherits the
    # baseline's steering-prior decision, published as the bare `applied`
    # (or `prior_applied` where a method renames it), and a prior that filled
    # a few unsupported cells does not make an error-variance fusion or a
    # residual "applied": on the live cycle of 2026-09-01 that inherited
    # flag was the only true one on every GFS layer while every method's own
    # term had been refused, and reading it as the method's own would have
    # told the map nothing had reduced. A method that publishes its own
    # `<term>_applied` switches is judged on those alone; one that publishes
    # only `applied` (the prior IS its term, as for the cloud-top steering
    # and the GOES transfer) is judged on that.
    own = {key: value for key, value in applied.items() if key.endswith("_applied") and key != "prior_applied"}
    if own:
        return not any(own.values())
    return not bool(applied.get("applied", False))


@app.get(f"{PREFIX}/methods", response_model=MethodsResponse)
def get_interpolation_methods() -> MethodsResponse:
    """The interpolation bench: what the map can be switched between, and how each scores.

    The registry is the server's, so the menu can never offer a method the
    derivation does not publish. Scores are read from the motion artifacts'
    own provenance - every enabled method is derived on the same held-out
    frames of the same cycle, which is what makes them comparable. A method
    with no scores has not met real frames yet; that is stated by an empty
    list rather than by a zero.
    """
    catalogue = grids.flow_method_catalogue()
    if not catalogue:
        return MethodsResponse(
            data_mode=DataMode.UNAVAILABLE,
            default_method=grids.DEFAULT_FLOW_METHOD,
            methods=[],
            notices=["the interpolation method registry could not be read; the map falls back to the default construction"],
        )
    # Only the keys this API models cross; a registry key added ahead of the
    # model is left for the next release rather than refusing every request.
    modelled = set(InterpolationMethodItem.model_fields) - {"requirements", "published", "scores"}
    items = {
        entry["id"]: InterpolationMethodItem(
            **{key: value for key, value in entry.items() if key in modelled},
            requirements=[MethodRequirement(**item) for item in entry.get("requirements", [])],
            published=False,
            scores=[],
        )
        for entry in catalogue
    }
    # The deployment kill switch is a fact about every branch below, so it
    # is said whether or not a score could be read.
    notices: list[str] = [] if _generated_display_enabled() else [GENERATED_DISPLAY_OFF_NOTICE]
    if fixture_mode():
        return MethodsResponse(
            data_mode=DataMode.FIXTURE,
            default_method=grids.DEFAULT_FLOW_METHOD,
            methods=list(items.values()),
            notices=[*notices, "fixture mode: no motion artifact has been scored"],
        )
    store = live_store()
    if store is None:
        return MethodsResponse(
            data_mode=DataMode.UNAVAILABLE,
            default_method=grids.DEFAULT_FLOW_METHOD,
            methods=list(items.values()),
            notices=[*notices, "no live artifact store is reachable; no method can report a measured score"],
        )
    try:
        artifacts = [
            artifact for artifact in store.current()
            # Every motion artifact, whichever grid it derives from: the bench
            # scores the derived WEonG layer exactly as it scores the retrieved
            # one, and the layer each score belongs to is settled by the
            # variable name below, not by the artifact's.
            if grids.is_cloud_motion_logical_name(artifact.logical_name)
        ]
    except Exception:
        LOGGER.exception("published motion artifacts could not be listed for the method bench")
        return MethodsResponse(
            data_mode=DataMode.UNAVAILABLE,
            default_method=grids.DEFAULT_FLOW_METHOD,
            methods=list(items.values()),
            notices=[*notices, "the live artifact store raised while listing published motion artifacts"],
        )
    for artifact in artifacts:
        provenance = artifact.provenance or {}
        version = provenance.get("derivation_version")
        per_variable = ((provenance.get("quality") or {}).get("per_variable") or {})
        for variable, block in per_variable.items():
            spec = next(
                (item for item in grids.RENDERED_GRID_SPECS
                 if item.source_id == artifact.source_id and item.variable == variable),
                None,
            )
            for method_id, measured in (block.get("per_method") or {}).items():
                item = items.get(method_id)
                if item is None:
                    # Published by a derivation this API does not know. Said
                    # out loud rather than dropped: the two are out of step.
                    notices.append(f"{artifact.source_id} publishes an unknown interpolation method {method_id!r}")
                    continue
                item.published = True
                # A requirement that named a diagnostic is answered by what the
                # derive actually found, not by the placeholder the method
                # carries for the case where no cycle has reported yet. Any
                # variable reaching the ingredient settles it: the menu is a
                # per-deployment statement, and "some strata have it" is the
                # honest reading of a per-variable fact shown in one line.
                for requirement in item.requirements:
                    if not requirement.diagnostic or requirement.met:
                        continue
                    reached = measured.get(requirement.diagnostic)
                    if isinstance(reached, (int, float)) and float(reached) > 0.0:
                        requirement.met = True
                        requirement.detail = (
                            f"read by the last cycle ({requirement.diagnostic}="
                            f"{float(reached):.2f} on {artifact.source_id} {variable})"
                        )
                skill = measured.get("leave_one_out")
                if not skill:
                    continue
                applied = _applied_options(measured.get("options"))
                item.scores.append(MethodScore(
                    layer_id=spec.layer_id if spec else f"{artifact.source_id}:{variable}",
                    source_id=artifact.source_id,
                    variable=variable,
                    held_out_frames=int(skill.get("held_out_frames", 0)),
                    improvement_over_reversed_flow=float(skill.get("improvement_over_reversed_flow", 0.0)),
                    improvement_over_crossfade=float(skill.get("improvement_over_crossfade", 0.0)),
                    improvement_over_advection=_optional_float(skill.get("improvement_over_advection")),
                    midpoint_mae_percent=float(skill.get("midpoint_mae_percent", 0.0)),
                    midpoint_ssim=_optional_float(skill.get("midpoint_ssim")),
                    midpoint_sharpness_ratio=_optional_float(skill.get("midpoint_sharpness_ratio")),
                    midpoint_spectral_ratio_error=_optional_float(skill.get("midpoint_spectral_ratio_error")),
                    midpoint_mae_grew=_optional_float(skill.get("midpoint_mae_grew")),
                    midpoint_mae_decayed=_optional_float(skill.get("midpoint_mae_decayed")),
                    advect_weight_median=_optional_float(measured.get("advect_weight_median")),
                    derivation_version=str(version) if version else None,
                    applied=applied,
                    reduced_to_default=_reduced_to_default(item, applied),
                ))
    if not artifacts:
        notices.append("no cloud-motion artifact is currently published; no method has been scored")
    return MethodsResponse(
        data_mode=DataMode.LIVE if artifacts else DataMode.UNAVAILABLE,
        default_method=grids.DEFAULT_FLOW_METHOD,
        methods=list(items.values()),
        notices=notices,
    )


@app.get(f"{PREFIX}/layers/{{layer_id}}/legend", responses={501: {"model": ErrorResponse}})
def get_layer_legend(
    layer_id: str,
    style: str | None = Query(default=None, description="an upstream style name; omitted means the layer's own default"),
) -> Response:
    """The upstream colour ramp for a layer, fetched rather than synthesised.

    A hand-written key over real pixels would be a fabricated legend, so the
    only ramp served is the one ECCC draws the layer with. The one exception
    is a rendered-grid layer, whose pixels this experiment itself drew: its
    legend is the renderer's own declared colormap - the ramp the pixels were
    actually drawn with - and the headers say so.
    """
    if layer_id == goes_satellite.LAYER_ID:
        return Response(content=goes_satellite.legend_png(), media_type="image/png", headers=goes_satellite.legend_headers())

    if layer_id == aurora.LAYER_ID:
        return Response(content=aurora.legend_png(), media_type="image/png", headers=aurora.legend_headers())

    grid_spec = grids.rendered_grid_spec(layer_id)
    if grid_spec is not None:
        return Response(
            content=grids.legend_png(),
            media_type="image/png",
            headers={
                "Cache-Control": "public, max-age=3600",
                "X-Weather-Layer-Id": grid_spec.layer_id,
                "X-Weather-Operational": "false",
                "X-Weather-Image-Basis": "rendered_grid",
                "X-Weather-Legend-Basis": "renderer_colormap",
                "X-Weather-Colormap": grids.COLORMAP_DOC,
                "X-Weather-Legend-Semantics": (
                    "this is the colormap this experiment renders the layer with, left 0 percent to "
                    "right 100 percent; it is presentation, not provider data, and it is the exact "
                    "mapping applied to the stored values. The ramp is a transparency ramp, so this "
                    "graphic shows it composited over a neutral grey backdrop; the backdrop is not "
                    "part of the mapping"
                ),
            },
        )

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


@app.get(f"{PREFIX}/astronomy", response_model=AstronomyResponse)
def get_astronomy(
    latitude: float = Query(default=47.5615, ge=-90, le=90),
    longitude: float = Query(default=-52.7126, ge=-180, le=180),
    valid_time: datetime | None = None,
) -> AstronomyResponse:
    """Astronomical darkness geometry over the evidence window.

    Everything here is computed from the pinned, checksum-verified DE442
    kernel - never retrieved per request, never blended with weather
    evidence. The kernel failing verification makes this capability alone
    answer unavailable; the rest of the API is untouched.
    """
    require_core_coverage(latitude, longitude)
    time = requested_time(valid_time)
    reference = now()
    start, end = window_start(reference), window_end(reference)

    def unavailable(reason: str) -> AstronomyResponse:
        return AstronomyResponse(
            data_mode=DataMode.UNAVAILABLE,
            latitude=latitude,
            longitude=longitude,
            window_start=start,
            window_end=end,
            valid_time=time,
            sun_altitude_deg=0.0,
            moon_altitude_deg=0.0,
            core_altitude_deg=0.0,
            twilight_bands=[],
            moon=AstronomyMoon(rise=None, set=None, above_horizon=[], phase_deg=0.0, illuminated_fraction=0.0),
            milky_way_core=AstronomyCoreWindow(windows=[], max_altitude_deg=0.0, caption=astronomy.CORE_CAPTION),
            provenance=None,
            notices=[reason, "No astronomical value is computed from an unverified ephemeris; nothing is substituted."],
        )

    try:
        geometry = astronomy.sky_geometry(latitude, longitude, start, end, time)
    except astronomy.AstronomyUnavailable as error:
        return unavailable(str(error))

    def intervals(items) -> list[AstronomyInterval]:
        return [AstronomyInterval(kind=item.kind, start=item.start, end=item.end) for item in items]

    return AstronomyResponse(
        data_mode=DataMode.LIVE,
        latitude=latitude,
        longitude=longitude,
        window_start=start,
        window_end=end,
        valid_time=time,
        sun_altitude_deg=geometry.sun_altitude_deg,
        moon_altitude_deg=geometry.moon_altitude_deg,
        core_altitude_deg=geometry.core_altitude_deg,
        twilight_bands=intervals(geometry.twilight_bands),
        moon=AstronomyMoon(
            rise=geometry.moon.rise,
            set=geometry.moon.set,
            above_horizon=intervals(geometry.moon.above_horizon),
            phase_deg=geometry.moon.phase_deg,
            illuminated_fraction=geometry.moon.illuminated_fraction,
        ),
        milky_way_core=AstronomyCoreWindow(
            windows=intervals(geometry.core.windows),
            max_altitude_deg=geometry.core.max_altitude_deg,
            caption=astronomy.CORE_CAPTION,
        ),
        provenance=AstronomyProvenance(
            source_id=astronomy.SOURCE_ID,
            kernel_id=EPHEMERIS_ID,
            kernel_sha256=EPHEMERIS_SHA256,
            derivation=astronomy.derivation(),
            derivation_version=astronomy.DERIVATION_VERSION,
        ),
        notices=[],
    )


# --- space weather --------------------------------------------------------
# Planetary evidence for the night-sky audience: the observed and forecast Kp
# series (kept separate, the forecast carrying the provider's own per-value
# status) and the latest solar-wind Bz with the instant it was measured. None
# of it is localized - these series are stored with no coordinates and never
# reach /point - and every absence or staleness is said out loud.

SWPC_KP_SOURCE = "noaa-swpc-kp"
SWPC_RTSW_SOURCE = "noaa-swpc-rtsw"


def _swpc_threshold(source_id: str) -> int | None:
    """The registry freshness threshold, or None when it cannot be read."""
    try:
        from ingest.registry import get_config  # noqa: PLC0415

        config = get_config(source_id)
        return config.freshness_threshold_seconds if config else None
    except Exception:  # pragma: no cover - registry read is best effort here
        LOGGER.debug("registry threshold unavailable for %s", source_id, exc_info=True)
        return None


def _absent_series(source_id: str, notice: str) -> SpaceWeatherSeries:
    return SpaceWeatherSeries(
        available=False, source_id=source_id, product="unavailable", readings=[],
        freshness=Freshness.evaluate(None, _swpc_threshold(source_id)), notices=[notice],
    )


def _absent_solar_wind(notice: str) -> SolarWindLatest:
    return SolarWindLatest(
        available=False, source_id=SWPC_RTSW_SOURCE, product="unavailable",
        bz_gsm_nt=None, bt_nt=None, measured_at=None, feed_declared_spacecraft=None,
        freshness=Freshness.evaluate(None, _swpc_threshold(SWPC_RTSW_SOURCE)), notices=[notice],
    )


def _unavailable_space_weather(reference: datetime, reason: str, *, extra_notices: list[str] | None = None) -> SpaceWeatherResponse:
    return SpaceWeatherResponse(
        data_mode=DataMode.UNAVAILABLE,
        generated_at=reference,
        kp_observed=_absent_series(SWPC_KP_SOURCE, reason),
        kp_forecast=_absent_series(SWPC_KP_SOURCE, reason),
        solar_wind=_absent_solar_wind(reason),
        notices=[reason, *(extra_notices or [])],
    )


def _kp_series(series: SeriesData | None, reference: datetime, *, with_status: bool, name: str) -> SpaceWeatherSeries:
    """One Kp series as retrieved, with per-feed freshness against the registry.

    ``with_status`` marks the forecast series: each reading carries the
    provider's own ``observed|estimated|predicted`` label, and no lead hours
    exist anywhere. Freshness is judged from the feed's own newest reference
    instant - for the observed series the newest record, for the forecast the
    run time the adapter took from the feed's newest observed record.
    """
    if series is None:
        return _absent_series(SWPC_KP_SOURCE, f"no {name} artifact is currently published; the series is absent, and nothing is substituted for it")
    kp = series.variables.get("kp_index")
    if kp is None:
        return _absent_series(SWPC_KP_SOURCE, f"the published {name} artifact does not carry kp_index; the series is absent")
    statuses = series.variables.get("kp_status") if with_status else None
    readings: list[SpaceWeatherReading] = []
    for index, stamp in enumerate(series.times):
        raw = kp.values[index]
        value = raw if isinstance(raw, float) else None
        status = None
        if statuses is not None:
            declared = statuses.values[index]
            status = declared if isinstance(declared, str) else None
        readings.append(SpaceWeatherReading(time=stamp, value=value, status=status))

    threshold = _swpc_threshold(SWPC_KP_SOURCE)
    if with_status:
        anchor = series.run_time or max((stamp for stamp in series.times if stamp <= reference), default=None)
    else:
        anchor = max(series.times) if series.times else None
    age = int((reference - anchor).total_seconds()) if anchor is not None else None
    freshness = Freshness.evaluate(age, threshold)
    notices: list[str] = []
    if freshness.status == "stale":
        notices.append(f"{name}: the newest record is {age} s old, past the {threshold} s freshness threshold; the series is stale, not current")
    return SpaceWeatherSeries(
        available=True,
        source_id=series.source_id,
        product=str(series.provenance.get("product", series.logical_name)),
        readings=readings,
        freshness=freshness,
        notices=notices,
    )


def _solar_wind_latest(series: SeriesData | None, reference: datetime) -> SolarWindLatest:
    """The newest finite Bz with the instant it was measured. A gap stays a gap."""
    if series is None:
        return _absent_solar_wind("no solar_wind artifact is currently published; the latest Bz is absent, and nothing is substituted for it")
    bz = series.variables.get("bz_gsm")
    if bz is None:
        return _absent_solar_wind("the published solar_wind artifact does not carry bz_gsm; the latest Bz is absent")
    finite = [(stamp, index) for index, stamp in enumerate(series.times) if isinstance(bz.values[index], float)]
    spacecraft_raw = series.attrs.get("feed_declared_spacecraft") or series.provenance.get("feed_declared_spacecraft")
    spacecraft = str(spacecraft_raw) if spacecraft_raw else None
    threshold = _swpc_threshold(SWPC_RTSW_SOURCE)
    if not finite:
        return _absent_solar_wind("the stored solar-wind series carries no finite Bz record; a gap in the feed is a gap, never zero")
    measured_at, index = max(finite)
    bt = series.variables.get("bt")
    bt_value = bt.values[index] if bt is not None and isinstance(bt.values[index], float) else None
    age = int((reference - measured_at).total_seconds())
    freshness = Freshness.evaluate(age, threshold)
    notices: list[str] = []
    if freshness.status == "stale":
        notices.append(f"solar_wind: the newest Bz record is {age} s old, past the {threshold} s freshness threshold; it is served stale, not as current")
    return SolarWindLatest(
        available=True,
        source_id=series.source_id,
        product=str(series.provenance.get("product", series.logical_name)),
        bz_gsm_nt=bz.values[index] if isinstance(bz.values[index], float) else None,
        bt_nt=bt_value,
        measured_at=measured_at,
        feed_declared_spacecraft=spacecraft,
        freshness=freshness,
        notices=notices,
    )


@app.get(f"{PREFIX}/space-weather", response_model=SpaceWeatherResponse)
def get_space_weather() -> SpaceWeatherResponse:
    """Latest Bz, the observed Kp series, and the provider's Kp outlook.

    Every value is read from the published SWPC artifacts through the same
    integrity-checked path ``/point`` uses, minus any spatial claim. Fixture
    mode fails closed: no fixture space weather exists, and none is invented.
    """
    reference = datetime.now(timezone.utc)
    mode = configured_mode()
    if mode == FIXTURE_MODE:
        return _unavailable_space_weather(reference, "no fixture space weather exists; fixture mode answers unavailable rather than inventing planetary indices")
    if mode != LIVE_MODE:
        return _unavailable_space_weather(reference, "WEATHER_DATA_MODE is missing or malformed; this deployment fails closed")

    store = live_store()
    if store is None:
        return _unavailable_space_weather(reference, "no live artifact store is reachable; no space-weather series can be read")
    store.skipped = []
    try:
        kp_observed_data = store.read_series(SWPC_KP_SOURCE, "kp_observed")
        kp_forecast_data = store.read_series(SWPC_KP_SOURCE, "kp_forecast")
        solar_wind_data = store.read_series(SWPC_RTSW_SOURCE, "solar_wind")
    except StoreUnavailable as error:
        return _unavailable_space_weather(reference, f"the object store is unreachable: {error}")
    except Exception:
        LOGGER.exception("space-weather series could not be read")
        return _unavailable_space_weather(reference, "the live artifact store raised while reading the space-weather series")

    kp_observed = _kp_series(kp_observed_data, reference, with_status=False, name="kp_observed")
    kp_forecast = _kp_series(kp_forecast_data, reference, with_status=True, name="kp_forecast")
    solar_wind = _solar_wind_latest(solar_wind_data, reference)
    available = kp_observed.available or kp_forecast.available or solar_wind.available
    return SpaceWeatherResponse(
        data_mode=DataMode.LIVE if available else DataMode.UNAVAILABLE,
        generated_at=reference,
        kp_observed=kp_observed,
        kp_forecast=kp_forecast,
        solar_wind=solar_wind,
        notices=skip_notices(store) if available else [*skip_notices(store), "no SWPC space-weather artifact is currently published; every series is absent and nothing is invented"],
    )


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

    def unavailable(reason: str, flag: str, notices: list[str], *, flags: Sequence[str] = (), last_valid_time: datetime | None = None) -> ProfileResponse:
        return ProfileResponse(
            data_mode=DataMode.UNAVAILABLE, latitude=latitude, longitude=longitude, valid_time=time,
            levels=unavailable_profile_levels(time, PROFILE_PRESSURES, flags=[flag, *flags], last_valid_time=last_valid_time),
            notices=[*notices, reason],
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
        aged_at, aged_flags, aged_notices = _aged_out_absence(store, sorted(known_source_ids()))
        reason = (
            f"aged out at {aged_at.isoformat()}: the profile frames this deployment held have left the evidence window"
            if aged_at is not None
            else "no published artifact carries a pressure-level profile here"
        )
        return unavailable(reason, "no_published_artifact", [*notices, *aged_notices], flags=aged_flags, last_valid_time=aged_at)
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
    """True when retained frames actually fall inside the sliding window.

    Judged against ``sliding_window`` rather than against a second pair of
    literals: readiness that answered on a different window from the one
    ``/point`` accepts would report ready for instants nothing can serve.
    """
    try:
        coverage = store.published_products()
    except Exception:
        LOGGER.exception("evidence boundary could not be resolved for readiness")
        return False
    start, end = sliding_window(reference)
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
        # store with retained frames inside the sliding window. Anything less
        # is not ready, however healthy the process is.
        checks = {"data_mode_configured": True, "registry_catalog": bool(registry_source_records()), "job_store": True, "live_store": store is not None, "evidence_boundary": boundary}
        ready_now = all(checks.values())
        # A store holding only aged-out frames reports not ready AND says why.
        # Reported only when the boundary is false: a ready deployment naming
        # aged-out sources would read as a warning about evidence it is
        # currently serving.
        aged_out, notices = ({}, []) if boundary or store is None else _aged_out_sources(store)
        return ReadyResponse(
            data_mode=DataMode.LIVE if ready_now else DataMode.UNAVAILABLE,
            ready=ready_now, checks=checks, aged_out_sources=aged_out, notices=notices,
        )
    return ReadyResponse(data_mode=DataMode.UNAVAILABLE, ready=False, checks={"data_mode_configured": False, "registry_catalog": bool(registry_source_records()), "job_store": True, "live_store": False, "evidence_boundary": False})
