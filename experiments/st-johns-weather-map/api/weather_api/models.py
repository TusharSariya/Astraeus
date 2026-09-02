from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DataMode(StrEnum):
    """How a response was produced. ``operational`` stays False regardless.

    ``UNAVAILABLE`` is the fail-closed value: it means nothing was retrieved and
    nothing was invented. It exists so a caller can never mistake an outage for
    a reading, which is what a silent fixture fallthrough used to do.
    """

    LIVE = "live"
    FIXTURE = "fixture"
    MIXED = "mixed"
    UNAVAILABLE = "unavailable"


class SourceState(StrEnum):
    ACTIVE = "active"
    IMPLEMENTING = "implementing"
    CREDENTIAL_REQUIRED = "credential_required"
    LICENCE_REVIEW = "licence_review"
    UNAVAILABLE = "unavailable"
    DUPLICATE_EVIDENCE = "duplicate_evidence"
    UNSUPPORTED_FIELD = "unsupported_field"
    RETIRED = "retired"
    REJECTED = "rejected"


class Quality(StrictModel):
    status: Literal["passed", "suspect", "failed", "unknown"]
    flags: list[str] = Field(default_factory=list)


class Coverage(StrictModel):
    status: Literal["complete", "partial", "outside", "unknown"]
    fraction: float | None = Field(default=None, ge=0, le=1)


class Freshness(StrictModel):
    status: Literal["fresh", "stale", "unknown"]
    age_seconds: int | None = Field(default=None, ge=0)
    # Some registry records state no resolvable freshness promise at all. A
    # missing threshold must stay missing rather than borrow a default, or the
    # response would assert a promise the provider never made.
    threshold_seconds: Annotated[int, Field(gt=0)] | None = None

    @classmethod
    def evaluate(cls, age_seconds: int | None, threshold_seconds: int | None) -> Freshness:
        """Unknown age stays unknown; an unmeasured source is never called fresh."""
        if age_seconds is None or threshold_seconds is None:
            return cls(status="unknown", age_seconds=None if age_seconds is None else max(0, int(age_seconds)), threshold_seconds=threshold_seconds)
        age = max(0, int(age_seconds))
        return cls(status="fresh" if age <= threshold_seconds else "stale", age_seconds=age, threshold_seconds=threshold_seconds)


class ContributorProvenance(StrictModel):
    source_id: str
    provider: str
    product: str
    licence: str
    attribution: str


class Provenance(StrictModel):
    data_mode: DataMode = DataMode.FIXTURE
    operational: Literal[False] = False
    source_id: str
    provider: str
    product: str
    forecast_centre: str
    run_time: datetime | None
    valid_time: datetime
    retrieval_time: datetime
    member: str | None = None
    vertical_level: str
    original_units: str
    normalized_units: str
    native_resolution: str
    native_crs: str
    quality: Quality
    coverage: Coverage
    freshness: Freshness
    licence: str
    attribution: str
    derivation: str | None = None
    derivation_version: str | None = None
    adapter_version: str
    #: The coordinate of the grid cell the value was actually read from. On a
    #: 2.5 km rotated grid this is not the coordinate that was requested, and
    #: echoing the request back would overstate where the reading came from.
    sampled_latitude: float | None = None
    sampled_longitude: float | None = None
    #: Distance from the requested coordinate to that cell, in kilometres.
    sample_distance_km: float | None = None
    #: How the cell was chosen: ``rectilinear`` label selection, or
    #: ``curvilinear_nearest_cell`` index selection on a 2-D coordinate grid.
    #: Never an interpolation - one published cell, unmodified.
    sample_method: str | None = None
    contributing_evidence: list[str] = Field(default_factory=list)
    contributors: list[ContributorProvenance] = Field(default_factory=list)

    @field_validator("run_time", "valid_time", "retrieval_time")
    @classmethod
    def require_aware_time(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("timestamps must include an offset")
        return value


FieldValue = float | int | str | bool | list[float] | list[str] | None


class EvidenceField(StrictModel):
    field: str
    value: FieldValue
    provenance: Provenance


class SourceRecord(StrictModel):
    """One catalogue entry. Derived from ``registry/source_data.py`` in every
    mode: the registry is a checked-in declaration of what may be retrieved, not
    retrieved evidence, so publishing it is honest regardless of data mode."""

    id: str
    category: str
    producer: str
    product: str
    state: SourceState
    status_reason: str
    role: str
    may_enter_consensus: bool
    exact_variables: list[str]
    levels: list[str]
    geographic_coverage: str
    cadence: str
    forecast_horizon: str
    authentication: str
    licence: str
    attribution: str
    caching: str
    archival: str
    redistribution: str
    schema_version: str
    freshness_threshold_seconds: Annotated[int, Field(gt=0)] | None = None
    documentation_url: str
    access_endpoint: str
    integration: str
    schedulable: bool
    fixture_status: Literal["passing", "missing", "not_applicable", "planned", "blocked"]
    live_smoke_status: Literal["not_run", "passing", "failing", "credential_required", "planned", "blocked", "not_applicable"]


class CatalogResponse(StrictModel):
    experimental: Literal[True] = True
    data_mode: DataMode = DataMode.FIXTURE
    operational: Literal[False] = False
    generated_at: datetime
    sources: list[SourceRecord]


class TimelineItem(StrictModel):
    valid_time_utc: datetime
    valid_time_newfoundland: datetime
    available_products: list[str]


class TimelineResponse(StrictModel):
    data_mode: DataMode = DataMode.FIXTURE
    operational: Literal[False] = False
    start: datetime
    end: datetime
    items: list[TimelineItem]
    notices: list[str] = Field(default_factory=list)


class Layer(StrictModel):
    id: str
    title: str
    kind: Literal["raster", "point", "line", "alert", "mask"]
    field: str
    product: str
    units: str
    semantics: str
    #: Exactly the valid times this layer published, at its own cadence. Empty
    #: means the artifact carries no time coordinate, never that it covers all
    #: hours: a client must not synthesise frames for a layer that declared none.
    times: list[datetime] = Field(default_factory=list)
    #: Modal gap between consecutive frames. ``None`` below two frames.
    cadence_seconds: int | None = None
    #: How far a requested time may sit from the nearest published frame before
    #: the layer must report unavailable. Beyond this a client renders nothing;
    #: quietly showing the nearest older frame would misdate the evidence.
    staleness_tolerance_seconds: int
    default_opacity: float = 0.85
    #: Draw order within the stack, low to high. Observations sit above fields
    #: so a station reading is never hidden under a raster.
    z_index: int = 0
    #: Where this layer's evidence comes from, and the single field a client
    #: must read before presenting it as evidence.
    #:
    #: ``published_artifact``
    #:     Times and values were read from an artifact the worker fetched,
    #:     validated against a manifest, QC-gated and published atomically.
    #: ``live_proxy``
    #:     Times were read from the upstream service at request time and the
    #:     imagery is rendered upstream on demand. Nothing is stored, nothing
    #:     passed ingest QC, and no value from it is sampled by ``/point`` or
    #:     counted in ``/timeline``. Display evidence, not audited evidence, and
    #:     an interface must say so where a reader can see it.
    evidence_basis: Literal["published_artifact", "live_proxy"] = "published_artifact"
    #: Where a layer index should file this layer. Derived here from
    #: ``evidence_basis`` and ``kind`` so a client never has to infer it from
    #: the shape of an id. ``satellite`` is observed imagery relayed live:
    #: frames exist only for the past and it is never a forecast.
    #: ``rendered_grid`` is a published-model forecast raster rendered by this
    #: experiment itself from a retrieved grid artifact - stored values at
    #: their native cells, nearest-neighbor, never smoothed - as opposed to
    #: imagery rendered upstream by a provider.
    group: Literal["forecast_proxy", "published_model", "observation", "alert", "satellite", "rendered_grid"] = "published_model"
    #: True when ``/layers/{id}/raster`` will serve an image for this layer.
    #: False means the 501 stands, with its reason.
    raster_available: bool = False
    #: True when ``/layers/{id}/legend`` will serve the upstream colour ramp.
    legend_available: bool = False
    #: The upstream WMS layer imagery is drawn from, when there is one. Read
    #: from the artifact's own recorded provenance or from the proxied layer's
    #: declaration; never guessed.
    upstream_wms_layer: str | None = None
    upstream_endpoint: str | None = None


class LayersResponse(StrictModel):
    data_mode: DataMode = DataMode.FIXTURE
    operational: Literal[False] = False
    layers: list[Layer]
    notices: list[str] = Field(default_factory=list)


class MethodScore(StrictModel):
    """One method's measured skill for one layer's variable, as published.

    Every field here is read out of a motion artifact's provenance. A score
    that was not measured is absent, never a zero - a method with no scores
    has not been derived against real frames yet, which is a different fact
    from a method that was measured and lost.
    """

    layer_id: str
    source_id: str
    variable: str
    held_out_frames: int
    #: Improvement over the same construction with its motion reversed. Kept
    #: as the motion veto's own number; it cannot rank methods against each
    #: other because the control moves with the method.
    improvement_over_reversed_flow: float
    #: Fixed-control skill: improvement over a plain crossfade of the same
    #: two frames, and over plain linear advection of them. These rank
    #: methods, because the control does not move with the method.
    improvement_over_crossfade: float
    improvement_over_advection: float | None = None
    midpoint_mae_percent: float
    midpoint_ssim: float | None = None
    #: Structure scores at the midpoint: sharpness relative to the real frame
    #: (1.0 = as sharp as real; pointwise error alone rewards blur) and the
    #: radial power-spectrum log-ratio error against it.
    midpoint_sharpness_ratio: float | None = None
    midpoint_spectral_ratio_error: float | None = None
    #: Midpoint error stratified by what the cell did between the frames.
    midpoint_mae_grew: float | None = None
    midpoint_mae_decayed: float | None = None
    advect_weight_median: float | None = None
    derivation_version: str | None = None
    #: Which of the method's measured options the derive actually applied on
    #: this layer, by option name. Every False here is a switch the harness
    #: refused on this variable's own held-out frames.
    applied: dict[str, bool] = Field(default_factory=dict)
    #: True where this method drew the default construction on this layer -
    #: an unmet requirement, or every option refused - so a reader who picks
    #: it is told rather than left to wonder whether the control did anything.
    reduced_to_default: bool = False


class MethodRequirement(StrictModel):
    """One thing a method needs before it can differ from the baseline.

    A method whose ingredient this deployment lacks is not broken - it
    reduces to another construction by design. But a reader who selects it
    and sees no change is owed the reason, because a control that appears to
    do something must do it.
    """

    name: str
    met: bool
    detail: str = ""
    #: The per-method provenance diagnostic the API read `met` from, when it
    #: had one. Empty where the method answered for itself.
    diagnostic: str = ""


class InterpolationMethodItem(StrictModel):
    """One entry in the interpolation bench."""

    id: str
    title: str
    summary: str
    #: The client construction these fields are meant for.
    shader: str
    enabled: bool
    #: True where the disclosure must say the pixels were generated rather
    #: than retrieved. Never true without an owner-approved carve-out.
    generative: bool = False
    #: Reader-facing copy, server-supplied so the menu never paraphrases a
    #: construction: one plain sentence, one sentence on what it cannot show,
    #: and the cited science behind it.
    plain: str = ""
    gap: str = ""
    notes: str = ""
    #: True when this deployment's kill switch (WEATHER_GENERATED_DISPLAY=off)
    #: refuses this generative method, so it is neither derived nor offered.
    generation_disabled: bool = False
    #: Whether any currently published motion artifact carries this method.
    published: bool = False
    #: Unmet requirements are why a selected method may draw the same picture
    #: the baseline does. Empty means it works with what it is handed.
    requirements: list[MethodRequirement] = Field(default_factory=list)
    scores: list[MethodScore] = Field(default_factory=list)


class MethodsResponse(StrictModel):
    data_mode: DataMode = DataMode.FIXTURE
    operational: Literal[False] = False
    default_method: str
    methods: list[InterpolationMethodItem]
    notices: list[str] = Field(default_factory=list)


class Selection(StrictModel):
    mode: Literal["consensus", "fallback", "evidence_only"]
    selected_source_id: str | None
    selected_product_id: str | None
    badge: str
    reason: str


class PointResponse(StrictModel):
    data_mode: DataMode = DataMode.FIXTURE
    operational: Literal[False] = False
    latitude: float
    longitude: float
    valid_time: datetime
    selection: Selection
    fields: list[EvidenceField]
    notices: list[str] = Field(default_factory=list)


class ProfileLevel(StrictModel):
    pressure_hpa: int
    fields: list[EvidenceField]


class ProfileResponse(StrictModel):
    data_mode: DataMode = DataMode.FIXTURE
    operational: Literal[False] = False
    latitude: float
    longitude: float
    valid_time: datetime
    levels: list[ProfileLevel]
    notices: list[str] = Field(default_factory=list)


class Coordinate(StrictModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class CrossSectionRequest(StrictModel):
    path: Annotated[list[Coordinate], Field(min_length=2, max_length=100)]
    valid_time: datetime | None = None
    fields: list[str] = Field(default_factory=lambda: ["temperature", "relative_humidity", "wind_speed"])


class CrossSectionSample(StrictModel):
    coordinate: Coordinate
    distance_km: float
    levels: list[ProfileLevel]


class CrossSectionResponse(StrictModel):
    data_mode: DataMode = DataMode.FIXTURE
    operational: Literal[False] = False
    valid_time: datetime
    samples: list[CrossSectionSample]


class SourceStatus(StrictModel):
    source_id: str
    state: SourceState
    data_mode: DataMode = DataMode.FIXTURE
    operational: Literal[False] = False
    last_retrieval: datetime | None
    freshness: Freshness
    detail: str


class SourceStatusResponse(StrictModel):
    data_mode: DataMode = DataMode.FIXTURE
    operational: Literal[False] = False
    statuses: list[SourceStatus]
    notices: list[str] = Field(default_factory=list)


class RefreshRequest(StrictModel):
    source_ids: list[str] = Field(default_factory=list)


class JobState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class Job(StrictModel):
    id: str
    state: JobState
    created_at: datetime
    updated_at: datetime
    source_ids: list[str]
    detail: str
    operational_ingestion: Literal[False] = False


class HealthResponse(StrictModel):
    status: Literal["ok"]
    experimental: Literal[True] = True
    data_mode: DataMode = DataMode.FIXTURE
    operational: Literal[False] = False
    time: datetime


class ReadyResponse(StrictModel):
    data_mode: DataMode = DataMode.FIXTURE
    operational: Literal[False] = False
    ready: bool
    checks: dict[str, bool]


class ErrorResponse(StrictModel):
    detail: str


# --- space weather --------------------------------------------------------
# Planetary quantities: served with times, ages and provider statuses, never
# with a coordinate, a sample distance, or an invented value. An absent feed is
# an absent series with a notice; a stale feed says so with its age.


class SpaceWeatherReading(StrictModel):
    """One retrieved series value at the feed's own instant.

    ``status`` is the provider's own per-value label (``observed`` |
    ``estimated`` | ``predicted``) on the Kp forecast series, exactly as the
    feed declared it; ``None`` everywhere the provider declared none. A null
    ``value`` is a gap in the feed, never zero.
    """

    time: datetime
    value: float | None
    status: str | None = None


class SpaceWeatherSeries(StrictModel):
    """A planetary index series, or its honest absence."""

    available: bool
    source_id: str
    product: str
    readings: list[SpaceWeatherReading] = Field(default_factory=list)
    freshness: Freshness
    notices: list[str] = Field(default_factory=list)


class SolarWindLatest(StrictModel):
    """The newest retrieved solar-wind magnetometer reading, with its instant.

    ``measured_at`` is the instant the served ``bz_gsm_nt`` was measured -
    the newest record carrying a finite Bz, never a gap filled with zero.
    ``feed_declared_spacecraft`` is whatever the feed's own source field said,
    verbatim; no spacecraft is ever named beyond that.
    """

    available: bool
    source_id: str
    product: str
    bz_gsm_nt: float | None
    bt_nt: float | None
    measured_at: datetime | None
    feed_declared_spacecraft: str | None
    freshness: Freshness
    notices: list[str] = Field(default_factory=list)


class SpaceWeatherResponse(StrictModel):
    data_mode: DataMode
    operational: Literal[False] = False
    generated_at: datetime
    kp_observed: SpaceWeatherSeries
    kp_forecast: SpaceWeatherSeries
    solar_wind: SolarWindLatest
    notices: list[str] = Field(default_factory=list)


# --- astronomy ------------------------------------------------------------


class AstronomyInterval(StrictModel):
    """One labelled interval over the evidence window."""

    kind: str
    start: datetime
    end: datetime


class AstronomyMoon(StrictModel):
    rise: datetime | None
    set: datetime | None
    above_horizon: list[AstronomyInterval]
    phase_deg: float
    illuminated_fraction: float


class AstronomyCoreWindow(StrictModel):
    """The geometric Milky Way core window: geometry only, never blended."""

    windows: list[AstronomyInterval]
    max_altitude_deg: float
    caption: str


class AstronomyProvenance(StrictModel):
    source_id: str
    kernel_id: str
    kernel_sha256: str
    derivation: str
    derivation_version: str
    operational: Literal[False] = False


class AstronomyResponse(StrictModel):
    data_mode: DataMode
    operational: Literal[False] = False
    latitude: float
    longitude: float
    window_start: datetime
    window_end: datetime
    valid_time: datetime
    sun_altitude_deg: float
    moon_altitude_deg: float
    core_altitude_deg: float
    twilight_bands: list[AstronomyInterval]
    moon: AstronomyMoon
    milky_way_core: AstronomyCoreWindow
    provenance: AstronomyProvenance | None
    notices: list[str]
