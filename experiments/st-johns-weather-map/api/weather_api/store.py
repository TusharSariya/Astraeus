"""Read published artifacts and sample them at an arbitrary coordinate.

The API never reaches upstream: it resolves ``current_artifacts``, opens the
bbox-cropped Zarr the worker published, and samples it. Sampling a stored grid
rather than a fixed station list is what lets any Avalon coordinate be asked
for. Anything missing surfaces as ``None`` with provenance saying so; nothing
is interpolated into existence.
"""

from __future__ import annotations

import hashlib
import logging
import os
import sys
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from collections import OrderedDict
from typing import Any, Sequence

UTC = timezone.utc
LOGGER = logging.getLogger(__name__)

# The one switch that decides whether this deployment may read live artifacts or
# may serve development fixtures. Anything else - unset, empty, misspelt - is a
# misconfiguration, and a misconfiguration must not be allowed to look like data.
DATA_MODE_ENV = "WEATHER_DATA_MODE"
LIVE_MODE = "live"
FIXTURE_MODE = "fixture"
UNAVAILABLE_MODE = "unavailable"

EXPERIMENT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(EXPERIMENT_ROOT) not in sys.path:  # ingest/ ships beside api/ in both images
    sys.path.insert(0, str(EXPERIMENT_ROOT))

# Canonical artifact variable -> API evidence field. Adapters write the left
# hand side (ingest.registry.DEFAULT_VARIABLES); the API speaks the right.
FIELD_BY_VARIABLE = {
    "temperature_2m": "temperature",
    "dew_point_2m": "dew_point",
    "relative_humidity_2m": "relative_humidity",
    "mean_sea_level_pressure": "mean_sea_level_pressure",
    "visibility": "visibility",
    "total_cloud": "total_cloud",
    "precipitation_accumulation": "precipitation_accumulation",
    "wind_u_10m": "wind_u",
    "wind_v_10m": "wind_v",
    # Provider-declared cloud strata (e.g. GFS LCDC/MCDC/HCDC at the
    # provider's own low/middle/high cloud layers). These are retrieved
    # fields served as stored, not derivations; see the layer note below.
    "cloud_low": "cloud_low",
    "cloud_middle": "cloud_middle",
    "cloud_high": "cloud_high",
    # Column total precipitable water, a retrieved provider value served as
    # stored. Its reading for transparency is caption text in the interface,
    # never a derived verdict here.
    "precipitable_water": "precipitable_water",
}

# METAR/TAF cloud layers, published per layer as retrieved (cover code, cover
# percent, base above ground) in provider order. Field name == variable name.
# They are deliberately not folded into low/middle/high strata here or
# anywhere: that would be a derived classification the owner has not approved.
# ``cloud_low``/``cloud_middle``/``cloud_high`` are served only where a
# provider itself declares the stratum (mapped above), never from layers.
MAX_CLOUD_LAYERS = 6
CLOUD_LAYER_VARIABLES = tuple(
    f"cloud_layer_{slot}_{suffix}" for slot in range(1, MAX_CLOUD_LAYERS + 1) for suffix in ("cover_code", "cover", "base")
)
FIELD_BY_VARIABLE.update({name: name for name in CLOUD_LAYER_VARIABLES})

# The upper-air wind components must pass the sampling filter to reach the
# derivation below, so they map to themselves here; DERIVATION_INPUTS then
# keeps them out of the served fields, exactly like the 10 m components.
FIELD_BY_VARIABLE.update({name: name for name in ("wind_u_200hPa", "wind_v_200hPa", "wind_u_300hPa", "wind_v_300hPa")})

# Levels stated per variable where the artifact-wide default ("surface") would
# be untrue. Explicit and short rather than inferred from GRIB attrs.
VARIABLE_LEVELS = {
    "wind_u_200hPa": "200 hPa",
    "wind_v_200hPa": "200 hPa",
    "wind_u_300hPa": "300 hPa",
    "wind_v_300hPa": "300 hPa",
    "precipitable_water": "entire atmosphere (column)",
}

# Sampled so they can be derived from, never served as readings: a reader asks
# for a wind speed and a direction, not the components a model stores. The
# derivation that consumes them discloses itself in the provenance it emits.
DERIVATION_INPUTS = frozenset({
    "wind_u_10m", "wind_v_10m",
    "wind_u_200hPa", "wind_v_200hPa", "wind_u_300hPa", "wind_v_300hPa",
})

# The u/v pairs the MetPy wind derivation consumes and the fields it emits.
# One disclosed derivation, three levels; a missing component yields nothing.
WIND_COMPONENT_PAIRS = (
    ("wind_u_10m", "wind_v_10m", "wind_speed", "wind_direction"),
    ("wind_u_200hPa", "wind_v_200hPa", "wind_speed_200hPa", "wind_direction_200hPa"),
    ("wind_u_300hPa", "wind_v_300hPa", "wind_speed_300hPa", "wind_direction_300hPa"),
)

# The present-weather flags the AWC adapter stores (FG, VCFG, BR as 0/1).
# Sampled so ``fog_state`` can be derived from them; never served raw, because
# a bare 0/1 under a name like ``weather_fog_code`` reads as a fog verdict
# rather than as one code from one report.
FOG_INPUTS = frozenset({"weather_fog_code", "weather_fog_vicinity_code", "weather_mist_code"})
FIELD_BY_VARIABLE.update({name: name for name in FOG_INPUTS})

FOG_DERIVATION = (
    "ingest.meteorology.fog_state from the METAR/TAF present-weather group: FG (incl. FZFG, MIFG, BCFG, PRFG) "
    "and VCFG count as fog evidence; BR is mist and does not; no provider fog diagnostic, so 'not_indicated' cannot be produced"
)
FOG_DERIVATION_VERSION = "fog-state-present-weather-v1"

TIME_COORDINATES = ("valid_time", "time")
LATITUDE_COORDINATES = ("latitude", "lat", "y")
LONGITUDE_COORDINATES = ("longitude", "lon", "x")
PRESSURE_COORDINATES = ("isobaricInhPa", "pressure", "level")

MAX_CACHED_DATASETS = 32
MAX_TIME_DISTANCE_SECONDS = 3600
MAX_GRID_DISTANCE_DEGREES = 0.75
#: Degrees of latitude per kilometre, for reporting how far the sampled cell
#: sits from the requested coordinate in a unit a reader can judge.
KM_PER_DEGREE = 111.19


class StoreUnavailable(RuntimeError):
    """No live store is configured or reachable; the caller reports unavailable."""


class ArtifactIntegrityError(RuntimeError):
    """Downloaded bytes do not match the size and digest recorded at publication."""


@dataclass(frozen=True)
class SkippedArtifact:
    """One artifact that could not be read, kept so the skip is reported.

    A skip must never be invisible: it is the difference between "no evidence
    exists" and "evidence exists and we failed to read it".
    """

    source_id: str
    revision_id: str
    reason: str


def _is_geojson(media_type: str) -> bool:
    return media_type.split(";")[0].strip() == "application/geo+json"


def _parse_iso(raw: Any) -> datetime | None:
    if isinstance(raw, datetime):
        return raw.astimezone(UTC) if raw.tzinfo else raw.replace(tzinfo=UTC)
    if not isinstance(raw, str):
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def layer_id_for(source_id: str, logical_name: str) -> str:
    """The one place a layer id is formed, so the API and store cannot disagree."""
    return f"{source_id}-{logical_name}"


def _modal_cadence_seconds(stamps: Sequence[datetime]) -> int | None:
    """The most common gap between consecutive frames, or None below two frames.

    Modal rather than mean: a run with a missing lead has one double-length gap,
    and averaging would report a cadence the layer never actually publishes at.
    """
    if len(stamps) < 2:
        return None
    gaps = [round((later - earlier).total_seconds()) for earlier, later in zip(stamps, stamps[1:])]
    gaps = [gap for gap in gaps if gap > 0]
    if not gaps:
        return None
    return max(set(gaps), key=gaps.count)


#: Above this a point artifact is treated as a field rather than enumerated as
#: sites. It is a rendering choice, not a claim: nothing is drawn from it.
MAX_ENUMERATED_SITES = 512

#: Below this on either axis an artifact is treated as sampled stations rather
#: than a field. The AQHI adapter samples three stations and stores them on a
#: 3x3 latitude/longitude outer product, so six of those nine cells are empty
#: placeholders that were never measured. A true field - HRDPS at 2.5 km across
#: the Avalon - is hundreds of cells on a side. Enumerating the small case as
#: sites is what lets the empty cells be dropped instead of drawn.
MIN_GRID_SIDE = 16


def _artifact_geometry(dataset: Any) -> tuple[list[tuple[float, float]], bool]:
    """The coordinates an artifact actually holds, and whether they form a field.

    A field needs latitude and longitude to vary over enough cells to have been
    sampled as an area. One of each is a single pixel - exactly what a GeoMet
    ``GetFeatureInfo`` adapter stores - and a handful of each is a station list
    on an outer product. Neither may be presented as an area of weather.
    """
    import numpy  # noqa: PLC0415

    lat_name = _coordinate_name(dataset, LATITUDE_COORDINATES)
    lon_name = _coordinate_name(dataset, LONGITUDE_COORDINATES)
    if lat_name is None or lon_name is None:
        return [], False
    latitudes = numpy.asarray(dataset[lat_name].values).ravel()
    longitudes = numpy.asarray(dataset[lon_name].values).ravel()
    if latitudes.size == 0 or longitudes.size == 0:
        return [], False
    if latitudes.size >= MIN_GRID_SIDE and longitudes.size >= MIN_GRID_SIDE:
        return [], True
    pairs = sorted({(round(float(lat), 6), round(float(lon), 6)) for lat in latitudes for lon in longitudes})
    if len(pairs) > MAX_ENUMERATED_SITES:
        return [], False
    return pairs, False


@dataclass(frozen=True)
class LayerCoverage:
    """The time axis and geometry one published artifact actually carries.

    ``times`` is exactly what was read from the artifact's own time coordinate -
    never a generated range - so a caller can distinguish a cadence from a gap.

    ``sites`` matters as much. Several adapters sample GeoMet by WMS
    ``GetFeatureInfo``, which answers one pixel at one time, so their artifact
    holds a point series and not a field. Drawing that as a raster would spread
    a single sampled pixel across the Avalon as though it had been measured
    everywhere. Geometry is read from the stored coordinates rather than assumed
    from the media type, and it is what decides how a layer may be drawn.
    """

    layer_id: str
    source_id: str
    logical_name: str
    times: list[datetime]
    cadence_seconds: int | None
    #: Distinct (latitude, longitude) pairs the artifact carries.
    sites: list[tuple[float, float]]
    #: True when latitude and longitude both vary, i.e. a real field.
    gridded: bool


@dataclass(frozen=True)
class Sample:
    """One value read from one published artifact, with its own lineage."""

    source_id: str
    logical_name: str
    variable: str
    #: A number as stored, or - for a CF flag-coded variable - the retrieved
    #: meaning string of the stored flag (``"OVC"``), never the bare integer.
    value: float | str | None
    units: str
    level: str
    valid_time: datetime
    run_time: datetime | None
    retrieved_at: datetime | None
    native_crs: str
    provenance: dict[str, Any] = field(default_factory=dict)
    #: The coordinate of the grid cell the value was actually read from - not
    #: the coordinate that was asked for. At HRDPS's 2.5 km spacing the two
    #: differ by a real distance, and reporting the request back would claim a
    #: precision the reading does not have.
    sampled_latitude: float | None = None
    sampled_longitude: float | None = None
    #: Great-circle-corrected distance from the requested coordinate to that
    #: cell, in kilometres.
    sample_distance_km: float | None = None
    #: ``rectilinear`` (selected by latitude/longitude label) or
    #: ``curvilinear_nearest_cell`` (selected by index on a 2-D coordinate
    #: grid). Never an interpolation: no value here is computed from more than
    #: one published cell.
    sample_method: str = "rectilinear"


def _coordinate_name(dataset: Any, candidates: Sequence[str]) -> str | None:
    for name in candidates:
        if name in dataset.coords or name in dataset.dims:
            return name
    return None


def _is_curvilinear(dataset: Any, lat_name: str, lon_name: str) -> bool:
    """True when latitude/longitude are 2-D fields rather than sliceable axes.

    HRDPS and RDPS are published on a rotated lat/lon grid, so the decoder
    returns ``latitude``/``longitude`` as ``(y, x)`` coordinates over anonymous
    dimensions. ``.sel`` by label is simply invalid there - xarray refuses to
    build an index - so the case has to be detected rather than attempted.

    The detection lives in ``ingest.grib`` beside the cropper that produces
    these grids; it is mirrored here only if that module cannot be imported, so
    the API still fails closed instead of raising on an ordinary request.
    """
    try:
        from ingest.grib import is_curvilinear  # noqa: PLC0415

        return bool(is_curvilinear(dataset, lat_name=lat_name, lon_name=lon_name))
    except Exception:
        axes = getattr(dataset, "dims", ())
        rectilinear = dataset[lat_name].ndim == 1 and dataset[lon_name].ndim == 1 and lat_name in axes and lon_name in axes
        return not rectilinear


def _corrected_distance_degrees(latitude: float, longitude: float, cell_latitude: float, cell_longitude: float) -> float:
    """Equirectangular distance in degrees of latitude.

    A degree of longitude is only ~0.68 of a degree of latitude at 47.5 N, so
    a raw Euclidean distance over degrees picks a cell too far east or west.
    Scaling the longitude difference by ``cos(latitude)`` is enough over a grid
    a few hundred kilometres across and keeps the ceiling below comparable to
    the rectilinear one.
    """
    import math  # noqa: PLC0415

    delta_lat = cell_latitude - latitude
    delta_lon = ((cell_longitude - longitude + 180.0) % 360.0) - 180.0
    return float(math.hypot(delta_lat, delta_lon * math.cos(math.radians(latitude))))


def _nearest_curvilinear_cell(
    dataset: Any, lat_name: str, lon_name: str, latitude: float, longitude: float
) -> tuple[dict[str, int], float, float, float] | None:
    """Index of the single nearest published cell on a 2-D coordinate grid.

    Nothing is interpolated or regridded: this returns positional indexers for
    exactly one cell, together with that cell's own coordinates and its
    distance from the request, so the caller can report what was really read.
    Returns ``None`` when the coordinates are not a usable 2-D grid.
    """
    import numpy  # noqa: PLC0415

    latitudes = numpy.asarray(dataset[lat_name].values, dtype="float64")
    longitudes = numpy.asarray(dataset[lon_name].values, dtype="float64")
    if latitudes.ndim != 2 or latitudes.shape != longitudes.shape or latitudes.size == 0:
        return None
    dimensions = tuple(dataset[lat_name].dims)
    if len(dimensions) != 2:
        return None

    import math  # noqa: PLC0415

    scale = math.cos(math.radians(latitude))
    delta_lat = latitudes - latitude
    delta_lon = (((longitudes - longitude + 180.0) % 360.0) - 180.0) * scale
    distance = numpy.hypot(delta_lat, delta_lon)
    if not numpy.isfinite(distance).any():
        return None
    flat = int(numpy.nanargmin(distance))
    row, column = (int(index) for index in numpy.unravel_index(flat, distance.shape))
    cell_latitude = float(latitudes[row, column])
    cell_longitude = float(((longitudes[row, column] + 180.0) % 360.0) - 180.0)
    return (
        {dimensions[0]: row, dimensions[1]: column},
        cell_latitude,
        cell_longitude,
        float(distance[row, column]),
    )


def _flag_meaning(attrs: Any, value: float) -> str | None:
    """The CF ``flag_meanings`` entry for a stored flag value, or None.

    A flag outside the declared table is not a reading with an unknown label;
    it is a value the artifact never defined, and it is served as None rather
    than as its integer, which would invite a reader to guess.
    """
    raw_values = attrs.get("flag_values")
    raw_meanings = attrs.get("flag_meanings")
    if raw_values is None or raw_meanings is None:
        return None
    try:
        values = [int(item) for item in list(raw_values)]
    except (TypeError, ValueError):
        return None
    meanings = raw_meanings.split() if isinstance(raw_meanings, str) else [str(item) for item in list(raw_meanings)]
    if len(values) != len(meanings) or value != int(value):
        return None
    try:
        return meanings[values.index(int(value))]
    except ValueError:
        return None


def _is_flag_coded(attrs: Any) -> bool:
    return attrs.get("flag_values") is not None and attrs.get("flag_meanings") is not None


def _nearest_time_index(dataset: Any, name: str, moment: datetime) -> Any:
    import numpy  # noqa: PLC0415

    target = numpy.datetime64(moment.astimezone(UTC).replace(tzinfo=None), "ns")
    values = dataset[name].values
    distance = abs(values - target)
    position = int(distance.argmin())
    if distance[position] / numpy.timedelta64(1, "s") > MAX_TIME_DISTANCE_SECONDS:
        raise LookupError("no published step within one hour of the requested time")
    return dataset[name].values[position]


class LiveStore:
    """Resolves and samples currently published artifacts."""

    def __init__(self, artifact_store: Any, cache_dir: Path) -> None:
        self._store = artifact_store
        self._cache_dir = cache_dir
        # Bounded: an unbounded cache keyed by revision id grows without limit
        # in a long-running API process, because every new run mints new ids.
        self._datasets: OrderedDict[str, Any] = OrderedDict()
        self.skipped: list[SkippedArtifact] = []

    # --- resolution ------------------------------------------------------
    def current(self) -> list[Any]:
        return self._store.current_artifacts()

    def assert_object_store_reachable(self) -> None:
        """Fail closed when the object store is unreachable.

        Postgres and MinIO fail independently, and ``current_artifacts`` only
        touches Postgres. Without this probe a cached dataset keeps answering
        from memory after MinIO goes away, so the SAME request returns live
        values in a long-running process and ``unavailable`` in a freshly
        started one. A truth boundary that depends on how long the process has
        been up is not a boundary.

        The sharper problem is not staleness. With the object store
        unreachable we cannot tell that a revision has been superseded, so the
        cached answer would be served as current when it is not - presenting
        withdrawn evidence as live.
        """
        try:
            self._store.s3.head_bucket(Bucket=self._store.config.bucket)
        except Exception as error:
            raise StoreUnavailable(f"object store is unreachable: {error}") from error

    def _forget_stale_datasets(self, current_revisions: set[str]) -> None:
        """Drop cached datasets whose revision is no longer published."""
        for revision_id in [key for key in self._datasets if key not in current_revisions]:
            self._datasets.pop(revision_id, None)

    def source_activity(self) -> dict[str, datetime]:
        return self._store.source_activity()

    def enqueue_job(self, source_ids: Sequence[str], *, detail: str) -> dict[str, Any]:
        return self._store.enqueue_job(source_ids, detail=detail)

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        return self._store.get_job(job_id)

    def _local_copy(self, artifact: Any) -> Path:
        """Cache the immutable object by revision id; revisions never change.

        The downloaded bytes are checked against the size and SHA-256 recorded
        when the revision was staged, before anything is cached or parsed. A
        truncated or substituted object is an outage, not a reading, so it is
        refused rather than served.
        """
        destination = self._cache_dir / f"{artifact.revision_id}.zarr.zip"
        if destination.exists():  # only ever written after verification below
            return destination
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(".part")
        digest = hashlib.sha256()
        size = 0
        try:
            with temporary.open("wb") as handle:
                self._store.s3.download_fileobj(self._store.config.bucket, artifact.object_key, handle)
            with temporary.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1 << 20), b""):
                    size += len(chunk)
                    digest.update(chunk)
            self._verify(artifact, size, digest.hexdigest())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
        temporary.replace(destination)
        return destination

    @staticmethod
    def _verify(artifact: Any, size: int, sha256: str) -> None:
        expected_size = getattr(artifact, "byte_size", None)
        expected_digest = (artifact.provenance or {}).get("sha256")
        if not expected_digest:
            raise ArtifactIntegrityError(f"{artifact.revision_id} has no recorded sha256; unverifiable bytes are treated as unavailable")
        if expected_size is not None and int(expected_size) != size:
            raise ArtifactIntegrityError(f"{artifact.revision_id} byte size {size} does not match the recorded {expected_size}")
        if expected_digest != sha256:
            raise ArtifactIntegrityError(f"{artifact.revision_id} sha256 {sha256} does not match the recorded {expected_digest}")

    def open(self, artifact: Any) -> Any:
        cached = self._datasets.get(artifact.revision_id)
        if cached is not None:
            self._datasets.move_to_end(artifact.revision_id)
            return cached
        import xarray  # noqa: PLC0415
        import zarr  # noqa: PLC0415

        path = self._local_copy(artifact)
        store = zarr.storage.ZipStore(str(path), mode="r")
        dataset = xarray.open_zarr(store, consolidated=False)
        self._datasets[artifact.revision_id] = dataset
        while len(self._datasets) > MAX_CACHED_DATASETS:
            self._datasets.popitem(last=False)
        return dataset

    # --- sampling --------------------------------------------------------
    def _record_skip(self, artifact: Any, error: BaseException) -> None:
        """A broken artifact must not remove other evidence, but the caller has
        to be told it was dropped rather than silently absent."""
        LOGGER.warning("skipping unreadable artifact %s from %s: %s", getattr(artifact, "revision_id", "?"), getattr(artifact, "source_id", "?"), error)
        self.skipped.append(SkippedArtifact(source_id=str(getattr(artifact, "source_id", "unknown")), revision_id=str(getattr(artifact, "revision_id", "unknown")), reason=f"{type(error).__name__}: {error}"))

    def _record_distant_cell(self, artifact: Any, latitude: float, longitude: float, cell_latitude: float, cell_longitude: float, distance: float) -> None:
        """Report a grid that was read but holds no cell near the request."""
        reason = (
            f"nearest published cell {cell_latitude:.4f},{cell_longitude:.4f} is "
            f"{distance * KM_PER_DEGREE:.1f} km from the requested {latitude:.4f},{longitude:.4f}; "
            "no value was taken"
        )
        LOGGER.warning("artifact %s: %s", getattr(artifact, "revision_id", "?"), reason)
        self.skipped.append(
            SkippedArtifact(
                source_id=str(getattr(artifact, "source_id", "unknown")),
                revision_id=str(getattr(artifact, "revision_id", "unknown")),
                reason=reason,
            )
        )

    def sample_point(self, latitude: float, longitude: float, valid_time: datetime) -> list[Sample]:
        """Nearest published grid value per source and variable."""
        self.skipped = []
        self.assert_object_store_reachable()
        artifacts = self.current()
        self._forget_stale_datasets({str(item.revision_id) for item in artifacts})
        samples: list[Sample] = []
        for artifact in artifacts:
            if _is_geojson(artifact.media_type):
                # A vector collection carries no gridded values to sample.
                # Opening it as a Zarr zip is not a failure worth reporting -
                # it is a category error, and reporting it as a skipped
                # artifact told every caller that evidence had been lost when
                # none had. Alerts are served by /layers/{id}/features.
                continue
            try:
                dataset = self.open(artifact)
            except Exception as error:
                self._record_skip(artifact, error)
                continue
            samples.extend(self._sample_dataset(dataset, artifact, latitude, longitude, valid_time))
        return samples

    def _sample_dataset(self, dataset: Any, artifact: Any, latitude: float, longitude: float, valid_time: datetime, *, pressure: int | None = None) -> list[Sample]:
        lat_name = _coordinate_name(dataset, LATITUDE_COORDINATES)
        lon_name = _coordinate_name(dataset, LONGITUDE_COORDINATES)
        if lat_name is None or lon_name is None:
            return []
        selection: dict[str, Any] = {lat_name: latitude, lon_name: longitude}
        time_name = _coordinate_name(dataset, TIME_COORDINATES)
        exact: dict[str, Any] = {}
        if time_name is not None:
            try:
                exact[time_name] = _nearest_time_index(dataset, time_name, valid_time)
            except LookupError:
                return []
        pressure_name = _coordinate_name(dataset, PRESSURE_COORDINATES)
        if pressure is not None:
            if pressure_name is None:
                return []
            selection[pressure_name] = pressure
        elif pressure_name is not None and pressure_name in dataset.dims:
            return []

        curvilinear = _is_curvilinear(dataset, lat_name, lon_name)
        if curvilinear:
            # A rotated-grid artifact carries latitude/longitude as 2-D fields.
            # ``.sel`` by label raises there, which is why every HRDPS and RDPS
            # artifact previously answered with nothing. Take the one nearest
            # published cell by index; do not regrid, and do not average.
            nearest = _nearest_curvilinear_cell(dataset, lat_name, lon_name, latitude, longitude)
            if nearest is None:
                return []
            indexers, cell_latitude, cell_longitude, distance = nearest
            if distance > MAX_GRID_DISTANCE_DEGREES:
                # Fail closed and say so. A cell this far away is not evidence
                # about the requested coordinate, and returning it silently
                # would relabel weather from somewhere else as local.
                self._record_distant_cell(artifact, latitude, longitude, cell_latitude, cell_longitude, distance)
                return []
            try:
                located = dataset.isel(indexers)
                if pressure is not None:
                    located = located.sel({pressure_name: pressure}, method="nearest")
                if exact:
                    located = located.sel(exact)
            except Exception:
                return []
            sample_method = "curvilinear_nearest_cell"
        else:
            try:
                located = dataset.sel(selection, method="nearest")
                if exact:
                    located = located.sel(exact)
            except Exception:
                return []
            if abs(float(located[lat_name]) - latitude) > MAX_GRID_DISTANCE_DEGREES or abs(float(located[lon_name]) - longitude) > MAX_GRID_DISTANCE_DEGREES:
                return []
            cell_latitude, cell_longitude = float(located[lat_name]), float(located[lon_name])
            distance = _corrected_distance_degrees(latitude, longitude, cell_latitude, cell_longitude)
            sample_method = "rectilinear"

        provenance = dict(artifact.provenance or {})
        level = provenance.get("vertical_level", "surface" if pressure is None else f"{pressure} hPa")
        samples: list[Sample] = []
        for variable in dataset.data_vars:
            name = str(variable)
            if name not in FIELD_BY_VARIABLE and pressure is None:
                continue
            raw = located[name].values
            value: float | str | None
            try:
                value = float(raw)
            except (TypeError, ValueError):
                value = None
            if value is not None and value != value:  # NaN is absence, not a reading
                value = None
            attrs = dataset[name].attrs
            if value is not None and _is_flag_coded(attrs):
                # A flag-coded variable is served as the meaning the artifact
                # declared for that flag, exactly as retrieved; a flag the
                # table does not define is None, never a bare integer.
                value = _flag_meaning(attrs, value)
            samples.append(
                Sample(
                    source_id=artifact.source_id,
                    logical_name=artifact.logical_name,
                    variable=name,
                    value=value,
                    units=str(dataset[name].attrs.get("units", "unknown")),
                    level=VARIABLE_LEVELS.get(name, str(level)),
                    valid_time=valid_time,
                    run_time=artifact.run_time,
                    retrieved_at=artifact.retrieved_at,
                    native_crs=artifact.native_crs or provenance.get("native_crs", "unknown"),
                    provenance=provenance,
                    sampled_latitude=cell_latitude,
                    sampled_longitude=cell_longitude,
                    sample_distance_km=round(distance * KM_PER_DEGREE, 3),
                    sample_method=sample_method,
                )
            )
        return samples

    def sample_profile(self, latitude: float, longitude: float, valid_time: datetime, pressures: Sequence[int]) -> dict[int, list[Sample]]:
        self.skipped = []
        self.assert_object_store_reachable()
        artifacts = self.current()
        self._forget_stale_datasets({str(item.revision_id) for item in artifacts})
        result: dict[int, list[Sample]] = {}
        for artifact in artifacts:
            if _is_geojson(artifact.media_type):
                continue  # see sample_point: no gridded values to sample
            try:
                dataset = self.open(artifact)
            except Exception as error:
                self._record_skip(artifact, error)
                continue
            for pressure in pressures:
                found = self._sample_dataset(dataset, artifact, latitude, longitude, valid_time, pressure=pressure)
                if found:
                    result.setdefault(pressure, []).extend(found)
        return result

    def published_layer_times(self) -> dict[str, LayerCoverage]:
        """The valid times each published artifact covers, keyed by layer.

        Every artifact carries its own time axis at its own cadence: radar is
        six-minutely, METAR hourly, a model run three-hourly. Collapsing them
        onto one shared hourly axis is what forced the interface to imply a
        layer had a frame at an hour it never published. Keeping them separate
        lets each layer be scrubbed at the resolution it actually has, and lets
        a gap be shown as a gap.
        """
        self.skipped = []
        self.assert_object_store_reachable()
        artifacts = self.current()
        self._forget_stale_datasets({str(item.revision_id) for item in artifacts})
        coverage: dict[str, LayerCoverage] = {}
        for artifact in artifacts:
            if _is_geojson(artifact.media_type):
                entry = self._geojson_coverage(artifact)
                if entry is not None:
                    coverage[entry.layer_id] = entry
                continue
            try:
                dataset = self.open(artifact)
            except Exception as error:
                self._record_skip(artifact, error)
                continue
            time_name = _coordinate_name(dataset, TIME_COORDINATES)
            if time_name is None:
                continue
            import pandas  # noqa: PLC0415

            stamps = sorted({pandas.Timestamp(value).to_pydatetime().replace(tzinfo=UTC) for value in dataset[time_name].values})
            if not stamps:
                continue
            sites, gridded = _artifact_geometry(dataset)
            identifier = layer_id_for(artifact.source_id, artifact.logical_name)
            coverage[identifier] = LayerCoverage(
                layer_id=identifier,
                source_id=artifact.source_id,
                logical_name=artifact.logical_name,
                times=stamps,
                cadence_seconds=_modal_cadence_seconds(stamps),
                sites=sites,
                gridded=gridded,
            )
        return coverage

    def _read_geojson(self, artifact: Any) -> dict[str, Any]:
        import json  # noqa: PLC0415

        return json.loads(self._local_copy(artifact).read_text())

    def _geojson_coverage(self, artifact: Any) -> LayerCoverage | None:
        """Time axis for a vector artifact, taken from its own provenance.

        A GeoJSON collection has no time coordinate to read, and an empty one -
        which is what "no alert is in effect" correctly looks like - carries no
        feature to read a time from either. The times the run declared are the
        only honest answer, and an artifact that declared none gets no frames
        rather than an invented one.
        """
        provenance = dict(artifact.provenance or {})
        stamps: list[datetime] = []
        for raw in provenance.get("valid_times") or []:
            parsed = _parse_iso(raw)
            if parsed is not None:
                stamps.append(parsed)
        if not stamps and artifact.run_time is not None:
            stamps = [artifact.run_time.astimezone(UTC)]
        if not stamps:
            return None
        stamps = sorted(set(stamps))
        identifier = layer_id_for(artifact.source_id, artifact.logical_name)
        return LayerCoverage(
            layer_id=identifier,
            source_id=artifact.source_id,
            logical_name=artifact.logical_name,
            times=stamps,
            cadence_seconds=_modal_cadence_seconds(stamps),
            sites=[],
            gridded=False,
        )

    def _geojson_features(self, artifact: Any, valid_time: datetime) -> list[dict[str, Any]]:
        """The stored features, stamped with the frame they were asked for.

        The geometry is passed through exactly as published; only provenance is
        added. An empty collection stays empty - for alerts that is the answer,
        not a failure.
        """
        try:
            document = self._read_geojson(artifact)
        except Exception as error:
            self._record_skip(artifact, error)
            return []
        collected: list[dict[str, Any]] = []
        for feature in document.get("features") or []:
            if not isinstance(feature, dict):
                continue
            properties = dict(feature.get("properties") or {})
            properties.update(
                {
                    "layer_id": layer_id_for(artifact.source_id, artifact.logical_name),
                    "source_id": artifact.source_id,
                    "valid_time": valid_time.isoformat(),
                    "run_time": artifact.run_time.isoformat() if artifact.run_time else None,
                }
            )
            collected.append({"type": "Feature", "geometry": feature.get("geometry"), "properties": properties})
        return collected

    def layer_features(self, layer_id: str, valid_time: datetime) -> tuple[list[dict[str, Any]], LayerCoverage | None]:
        """Every stored value for one layer at one time, as GeoJSON features.

        This reads what was published and nothing else. The frame is chosen by
        the caller against the layer's own declared times, so no nearest-match
        happens here: a time with no stored values yields no features, which is
        how an absence stays an absence.
        """
        import pandas  # noqa: PLC0415

        self.skipped = []
        self.assert_object_store_reachable()
        coverage = self.published_layer_times().get(layer_id)
        if coverage is None:
            return [], None
        artifacts = [item for item in self.current() if layer_id_for(item.source_id, item.logical_name) == layer_id]
        features: list[dict[str, Any]] = []
        for artifact in artifacts:
            if _is_geojson(artifact.media_type):
                features.extend(self._geojson_features(artifact, valid_time))
                continue
            try:
                dataset = self.open(artifact)
            except Exception as error:
                self._record_skip(artifact, error)
                continue
            time_name = _coordinate_name(dataset, TIME_COORDINATES)
            lat_name = _coordinate_name(dataset, LATITUDE_COORDINATES)
            lon_name = _coordinate_name(dataset, LONGITUDE_COORDINATES)
            if time_name is None or lat_name is None or lon_name is None:
                continue
            if _is_curvilinear(dataset, lat_name, lon_name):
                # A rotated grid has no latitude/longitude labels to select by,
                # and ``coverage.sites`` is empty for it in any case: such an
                # artifact is a field, served as a raster, never enumerated as
                # stations. Guarded explicitly so a future geometry change
                # cannot turn this into a raise on an ordinary request.
                continue
            frame = pandas.Timestamp(valid_time.astimezone(UTC).replace(tzinfo=None))
            try:
                located = dataset.sel({time_name: frame})
            except Exception:
                # The requested frame is not in this artifact. Absence, not error.
                continue
            provenance = dict(artifact.provenance or {})
            for latitude, longitude in coverage.sites:
                properties: dict[str, Any] = {}
                for variable in located.data_vars:
                    name = str(variable)
                    if name in FOG_INPUTS:
                        continue  # derivation inputs only; see live_point_fields
                    try:
                        raw = located[name].sel({lat_name: latitude, lon_name: longitude}).values
                        value: float | str | None = float(raw)
                    except Exception:
                        continue
                    if value != value:  # NaN is absence, not a reading
                        continue
                    attrs = located[name].attrs
                    if _is_flag_coded(attrs):
                        value = _flag_meaning(attrs, float(value))  # type: ignore[arg-type]
                    properties[name] = value
                    properties[f"{name}_units"] = str(located[name].attrs.get("units", "unknown"))
                if not properties:
                    continue
                features.append(
                    {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [longitude, latitude]},
                        "properties": {
                            **properties,
                            "layer_id": layer_id,
                            "source_id": artifact.source_id,
                            "valid_time": valid_time.isoformat(),
                            "product": provenance.get("product", artifact.source_id),
                            "run_time": artifact.run_time.isoformat() if artifact.run_time else None,
                        },
                    }
                )
        return features, coverage

    def published_products(self) -> dict[str, set[datetime]]:
        """Valid times each published *source* covers, for the timeline.

        The timeline answers a coarser question than the layer stack does -
        which hours hold any evidence at all - so it folds the per-layer axes
        back together by source.
        """
        folded: dict[str, set[datetime]] = {}
        for entry in self.published_layer_times().values():
            folded.setdefault(entry.source_id, set()).update(entry.times)
        return folded


_live_store: LiveStore | None = None
_probed = False
_data_mode: str | None = None


def configured_mode() -> str:
    """Read ``WEATHER_DATA_MODE`` once, failing closed.

    Only the two spelled-out values mean anything. Absent, blank or misspelt
    resolves to ``unavailable`` so a deployment mistake can never silently
    downgrade into serving development fixtures as if they were readings.
    """
    global _data_mode
    if _data_mode is None:
        raw = os.environ.get(DATA_MODE_ENV, "").strip().lower()
        if raw not in {LIVE_MODE, FIXTURE_MODE}:
            if raw:
                LOGGER.error("%s=%r is not %r or %r; failing closed to %s", DATA_MODE_ENV, raw, LIVE_MODE, FIXTURE_MODE, UNAVAILABLE_MODE)
            else:
                LOGGER.error("%s is unset; failing closed to %s", DATA_MODE_ENV, UNAVAILABLE_MODE)
            raw = UNAVAILABLE_MODE
        _data_mode = raw
    return _data_mode


def reset_data_mode() -> None:
    """Test seam: re-read the environment on the next call."""
    global _data_mode
    _data_mode = None


def live_store() -> LiveStore | None:
    """Return the live store, or ``None`` when there is none to read.

    Probing once keeps a missing database from costing every request a
    connection attempt; the worker publishing new data does not change whether
    the store exists. Outside live mode there is deliberately no store at all.
    """
    global _live_store, _probed
    if configured_mode() != LIVE_MODE:
        return None
    if _probed:
        return _live_store
    _probed = True
    try:
        from ingest.store import store_from_env  # noqa: PLC0415

        artifact_store = store_from_env()
        artifact_store.current_artifacts()
    except Exception:
        LOGGER.exception("live artifact store is unreachable; responses will report unavailable")
        _live_store = None
        return None
    _live_store = LiveStore(artifact_store, Path(os.environ.get("WEATHER_ARTIFACT_CACHE", "/tmp/weather-artifacts")))
    return _live_store


def reset_live_store() -> None:
    """Test seam: forget the probe result and the resolved mode."""
    global _live_store, _probed
    _live_store, _probed = None, False
    reset_data_mode()


# --- evidence assembly ---------------------------------------------------
# Samples become API evidence here so that every live value carries the same
# provenance shape as a fixture value, including when it is missing.

def _registry_config(source_id: str) -> Any | None:
    try:
        from ingest.registry import get_config  # noqa: PLC0415

        return get_config(source_id)
    except Exception:
        return None


def source_category(source_id: str) -> str | None:
    """The registry ``category`` of a source, or ``None`` when it has no record.

    Read from ``registry/source_data.py`` via the ingest config, never from
    the shape of an id: whether a field counts as an observation is a fact
    the registry states, not one this module infers.
    """
    config = _registry_config(source_id)
    return getattr(config, "category", None) if config is not None else None


def live_provenance(
    sample: Sample,
    *,
    field_name: str,
    reference: datetime,
    derivation: str | None = None,
    derivation_version: str | None = None,
    contributors: Sequence[str] = (),
) -> Any:
    from .models import ContributorProvenance, Coverage, DataMode, Freshness, Provenance, Quality  # noqa: PLC0415

    config = _registry_config(sample.source_id)
    provenance = sample.provenance
    threshold = (config.freshness_threshold_seconds if config and config.freshness_threshold_seconds else 21600)
    age = int((reference - sample.retrieved_at).total_seconds()) if sample.retrieved_at else None
    quality = provenance.get("quality") or {}
    coverage = provenance.get("coverage") or {}
    contributor_records = []
    for source_id in contributors:
        other = _registry_config(source_id)
        if other is not None:
            contributor_records.append(ContributorProvenance(source_id=source_id, provider=other.producer, product=other.product, licence=other.licence, attribution=other.attribution))
    return Provenance(
        data_mode=DataMode.LIVE,
        source_id=sample.source_id,
        provider=config.producer if config else sample.source_id,
        product=config.product if config else sample.logical_name,
        forecast_centre=provenance.get("forecast_centre", config.producer if config else "unknown"),
        run_time=sample.run_time,
        valid_time=sample.valid_time,
        retrieval_time=sample.retrieved_at or reference,
        member=provenance.get("member"),
        vertical_level=sample.level,
        original_units=str(provenance.get("original_units", {}).get(sample.variable, sample.units)) if isinstance(provenance.get("original_units"), dict) else sample.units,
        normalized_units=sample.units,
        native_resolution=str(provenance.get("native_resolution", "unknown")),
        native_crs=sample.native_crs,
        quality=Quality(status=quality.get("status", "unknown"), flags=list(quality.get("flags", []))),
        coverage=Coverage(status=coverage.get("status", "unknown"), fraction=coverage.get("fraction")),
        freshness=Freshness.evaluate(age, threshold),
        licence=config.licence if config else "see contributing provider",
        attribution=config.attribution if config else "see contributing provider",
        derivation=derivation,
        derivation_version=derivation_version,
        adapter_version=str(provenance.get("adapter_version", "unknown")),
        sampled_latitude=sample.sampled_latitude,
        sampled_longitude=sample.sampled_longitude,
        sample_distance_km=sample.sample_distance_km,
        sample_method=sample.sample_method,
        contributing_evidence=list(contributors),
        contributors=contributor_records,
    )


def _consensus_candidates(samples: Sequence[Sample]) -> list[Any]:
    from .science import ConsensusCandidate  # noqa: PLC0415

    candidates = []
    for sample in samples:
        if sample.variable != "temperature_2m" or sample.value is None:
            continue
        config = _registry_config(sample.source_id)
        if config is None or not config.may_enter_consensus:
            continue
        candidates.append(
            ConsensusCandidate(
                source_id=sample.source_id,
                forecast_centre=config.consensus_family or config.producer,
                family=config.category,
                value=sample.value,
                is_eccc_regional=config.consensus_family == "ECCC" and config.category == "deterministic_forecast",
                is_ensemble=config.category == "ensemble",
            )
        )
    return candidates


def _flag_is_present(sample: Sample | None) -> bool | None:
    """True/False for a sampled 0/1 present-weather flag, None when it was not read.

    The flag arrives either as the meaning string the sampler mapped it to
    (``"present"``/``"absent"``) or, from an artifact that declared no flag
    table, as the bare number. NaN was already turned into None upstream.
    """
    if sample is None or sample.value is None:
        return None
    if isinstance(sample.value, str):
        return {"present": True, "absent": False}.get(sample.value)
    return bool(sample.value)


def live_point_fields(store: LiveStore, latitude: float, longitude: float, valid_time: datetime) -> tuple[list[Any], Any, list[str]]:
    """Build live evidence fields, the consensus result, and the source ids used."""
    from .models import EvidenceField  # noqa: PLC0415
    from .science import WIND_DIRECTION_UNITS, WIND_SPEED_UNITS, build_consensus, fog_state, resolve_relative_humidity, resolve_wind  # noqa: PLC0415

    reference = datetime.now(UTC)
    samples = store.sample_point(latitude, longitude, valid_time)
    if not samples:
        return [], build_consensus([]), []

    consensus = build_consensus(_consensus_candidates(samples))
    fields: list[EvidenceField] = []
    if consensus.available:
        representative = next(sample for sample in samples if sample.source_id in consensus.contributors and sample.variable == "temperature_2m")
        fields.append(EvidenceField(field="temperature", value=consensus.value, provenance=live_provenance(representative, field_name="temperature", reference=reference, contributors=list(consensus.contributors))))

    seen: set[tuple[str, str]] = {("temperature", "consensus")} if consensus.available else set()
    for sample in samples:
        name = FIELD_BY_VARIABLE.get(sample.variable)
        if name is None or sample.variable in DERIVATION_INPUTS or sample.variable in FOG_INPUTS or (name == "temperature" and consensus.available):
            continue
        key = (name, sample.source_id)
        if key in seen:
            continue
        seen.add(key)
        fields.append(EvidenceField(field=name, value=sample.value, provenance=live_provenance(sample, field_name=name, reference=reference)))

    by_source: dict[str, dict[str, Sample]] = {}
    for sample in samples:
        by_source.setdefault(sample.source_id, {})[sample.variable] = sample
    # A derived field borrows the lineage of its inputs (source, run, cell,
    # freshness) but not their units: the provenance must state the units of
    # the number it sits beside, so the input sample is re-labelled before it
    # is turned into provenance.
    for source_id, variables in by_source.items():
        temperature, dewpoint = variables.get("temperature_2m"), variables.get("dew_point_2m")
        if "relative_humidity_2m" not in variables and temperature is not None and dewpoint is not None and temperature.value is not None and dewpoint.value is not None:
            value, derivation, version = resolve_relative_humidity(None, temperature.value, dewpoint.value)
            basis = replace(temperature, variable="relative_humidity", value=value, units="percent")
            fields.append(EvidenceField(field="relative_humidity", value=value, provenance=live_provenance(basis, field_name="relative_humidity", reference=reference, derivation=derivation, derivation_version=version)))

        # Fog from the present-weather group. No provider fog diagnostic exists
        # here (``provider_diagnostic=None``), so the only live values are
        # ``evidence_present`` and ``unknown``: an absent FG code is not a
        # finding of no fog, and ``not_indicated`` is never produced.
        fog, vicinity = variables.get("weather_fog_code"), variables.get("weather_fog_vicinity_code")
        if fog is not None or vicinity is not None:
            visibility = variables.get("visibility")
            fog_code = _flag_is_present(fog) is True or _flag_is_present(vicinity) is True
            state = fog_state(
                provider_diagnostic=None,
                visibility_m=visibility.value if visibility is not None and isinstance(visibility.value, float) else None,
                fog_code=fog_code,
            )
            basis = replace(fog if fog is not None else vicinity, variable="fog_state", value=None, units="category")
            fields.append(EvidenceField(field="fog_state", value=state, provenance=live_provenance(basis, field_name="fog_state", reference=reference, derivation=FOG_DERIVATION, derivation_version=FOG_DERIVATION_VERSION)))

        for u_name, v_name, speed_field, direction_field in WIND_COMPONENT_PAIRS:
            u, v = variables.get(u_name), variables.get(v_name)
            if u is None or v is None or u.value is None or v.value is None:
                continue
            speed, direction, derivation, version = resolve_wind(u.value, v.value)
            for name, value, units in ((speed_field, speed, WIND_SPEED_UNITS), (direction_field, direction, WIND_DIRECTION_UNITS)):
                basis = replace(u, variable=name, value=value, units=units)
                fields.append(EvidenceField(field=name, value=value, provenance=live_provenance(basis, field_name=name, reference=reference, derivation=derivation, derivation_version=version)))

    return fields, consensus, sorted(by_source)


def live_profile_levels(store: LiveStore, latitude: float, longitude: float, valid_time: datetime, pressures: Sequence[int]) -> list[Any]:
    from .models import EvidenceField, ProfileLevel  # noqa: PLC0415

    reference = datetime.now(UTC)
    levels: list[ProfileLevel] = []
    for pressure, samples in sorted(store.sample_profile(latitude, longitude, valid_time, pressures).items(), key=lambda item: -item[0]):
        fields = [
            EvidenceField(field=FIELD_BY_VARIABLE.get(sample.variable, sample.variable), value=sample.value, provenance=live_provenance(sample, field_name=sample.variable, reference=reference))
            for sample in samples
        ]
        if fields:
            levels.append(ProfileLevel(pressure_hpa=pressure, fields=fields))
    return levels


# --- registry catalogue --------------------------------------------------
# ``registry/source_data.py`` is the only catalogue of record. It is a
# checked-in declaration of what may be retrieved, not retrieved evidence, so
# serving it is honest in every mode; what it must never do is claim a source is
# ``active`` or fresh on the strength of being declared.

_REGISTRY_STATE_CEILING = {
    "implementing": "implementing",
    "credential_required": "credential_required",
    "licence_review": "licence_review",
    "unavailable": "unavailable",
    "duplicate_evidence": "duplicate_evidence",
    "unsupported_field": "unsupported_field",
    "retired": "retired",
    "rejected": "rejected",
}


def _registry_records() -> list[dict[str, Any]]:
    from registry.source_data import registry  # noqa: PLC0415

    return list(registry()["sources"])


def registry_source_records() -> list[Any]:
    """Every registry record as a catalogue entry, in registry order."""
    from .models import SourceRecord, SourceState  # noqa: PLC0415

    from ingest.registry import ingest_configs  # noqa: PLC0415

    configs = ingest_configs()
    records: list[SourceRecord] = []
    for record in _registry_records():
        source_id = str(record["id"])
        config = configs.get(source_id)
        variables = record["variables"][0] if record["variables"] else {"names": [], "levels": []}
        records.append(
            SourceRecord(
                id=source_id,
                category=str(record["category"]),
                producer=str(record["producer"]),
                product=str(record["product"]),
                state=SourceState(_REGISTRY_STATE_CEILING.get(str(record["status"]), "unavailable")),
                status_reason=str(record["reason"]),
                role=str(record["poc_role"]),
                may_enter_consensus=bool(record.get("consensus", {}).get("eligible", False)),
                exact_variables=[str(name) for name in variables.get("names", [])],
                levels=[str(level) for level in variables.get("levels", [])],
                geographic_coverage=str(record["coverage"]),
                cadence=str(record["cadence"]),
                forecast_horizon=str(record["forecast_horizon"]),
                authentication=str(record["authentication"]["mechanism"]),
                licence=str(record["licence"]["name"]),
                attribution=str(record["attribution"]),
                caching=str(record["caching"]),
                archival=str(record["archival"]),
                redistribution=str(record["redistribution"]),
                schema_version=str(record["schema_version"]),
                freshness_threshold_seconds=config.freshness_threshold_seconds if config else None,
                documentation_url=str((record.get("documentation_urls") or ["unavailable"])[0]),
                access_endpoint=str((record.get("access_endpoints") or ["unavailable"])[0]),
                integration=f"{record['integration']['kind']}: {record['integration']['client']}",
                schedulable=bool(config.ingestible) if config else False,
                fixture_status=str(record["fixture_status"]),
                live_smoke_status=str(record["live_smoke_test_status"]),
            )
        )
    return records


def schedulable_source_ids() -> set[str]:
    """Registry ids a refresh may legitimately name."""
    from ingest.registry import ingest_configs  # noqa: PLC0415

    return {source_id for source_id, config in ingest_configs().items() if config.ingestible}


def known_source_ids() -> set[str]:
    from ingest.registry import ingest_configs  # noqa: PLC0415

    return set(ingest_configs())


def registry_source_statuses(activity: dict[str, datetime] | None = None, *, reference: datetime | None = None) -> list[Any]:
    """Registry state per source, promoted only by recorded live retrieval.

    The registry's own ``status`` is the ceiling: recording a retrieval makes a
    source's freshness measurable, it does not make the source active. Nothing
    here ever emits ``active``.
    """
    from .models import DataMode, Freshness, SourceStatus  # noqa: PLC0415

    from ingest.registry import ingest_configs  # noqa: PLC0415

    configs = ingest_configs()
    moment = reference or datetime.now(UTC)
    retrievals = activity or {}
    statuses: list[SourceStatus] = []
    for record in registry_source_records():
        config = configs.get(record.id)
        threshold = config.freshness_threshold_seconds if config else None
        retrieved = retrievals.get(record.id)
        age = int((moment - retrieved).total_seconds()) if retrieved is not None else None
        statuses.append(
            SourceStatus(
                source_id=record.id,
                state=record.state,
                data_mode=DataMode.LIVE if retrieved is not None else DataMode.UNAVAILABLE,
                last_retrieval=retrieved,
                freshness=Freshness.evaluate(age, threshold),
                detail="live retrieval recorded by the ingestion worker" if retrieved is not None else f"no live retrieval recorded; {record.status_reason}",
            )
        )
    return statuses


# --- unavailable evidence ------------------------------------------------
# The shape a response takes when nothing was retrieved. Every field is present
# and null, and every provenance says unknown, so a caller can tell absence from
# a reading without having to interpret an HTTP status code.
#
# The per-layer ``cloud_layer_{n}_*`` fields are deliberately not listed: they
# exist only where a report carried that layer, and an empty response
# enumerating six null layers would assert a slot structure nothing retrieved.

UNAVAILABLE_POINT_FIELDS: tuple[tuple[str, str], ...] = (
    ("temperature", "degC"),
    ("relative_humidity", "percent"),
    ("dew_point", "degC"),
    ("wind_speed", "m s-1"),
    ("wind_direction", "degree"),
    ("wind_gust", "m s-1"),
    ("visibility", "km"),
    ("cloud_low", "percent"),
    ("cloud_middle", "percent"),
    ("cloud_high", "percent"),
    ("total_cloud", "percent"),
    ("fog_state", "category"),
    ("radar_echo", "category"),
)

UNAVAILABLE_PROFILE_FIELDS: tuple[tuple[str, str], ...] = (
    ("temperature", "degC"),
    ("dew_point", "degC"),
    ("relative_humidity", "percent"),
    ("wind_speed", "m s-1"),
)


def unavailable_provenance(valid_time: datetime, *, units: str, flags: Sequence[str], source_id: str = "unavailable", product: str = "unavailable", level: str = "unavailable", reference: datetime | None = None) -> Any:
    from .models import Coverage, DataMode, Freshness, Provenance, Quality  # noqa: PLC0415

    moment = reference or datetime.now(UTC)
    return Provenance(
        data_mode=DataMode.UNAVAILABLE,
        source_id=source_id,
        provider="unavailable",
        product=product,
        forecast_centre="unavailable",
        run_time=None,
        valid_time=valid_time,
        # The moment the retrieval was attempted and produced nothing; the
        # ``no_retrieval`` flag and the null value say what actually happened.
        retrieval_time=moment,
        vertical_level=level,
        original_units=units,
        normalized_units=units,
        native_resolution="unavailable",
        native_crs="unavailable",
        quality=Quality(status="unknown", flags=["no_retrieval", *flags]),
        coverage=Coverage(status="unknown", fraction=None),
        freshness=Freshness.evaluate(None, None),
        licence="unavailable",
        attribution="unavailable",
        adapter_version="unavailable",
    )


def unavailable_point_fields(valid_time: datetime, *, flags: Sequence[str], source_id: str = "unavailable", product: str = "unavailable") -> list[Any]:
    from .models import EvidenceField  # noqa: PLC0415

    reference = datetime.now(UTC)
    return [
        EvidenceField(field=name, value=None, provenance=unavailable_provenance(valid_time, units=units, flags=flags, source_id=source_id, product=product, reference=reference))
        for name, units in UNAVAILABLE_POINT_FIELDS
    ]


def unavailable_profile_levels(valid_time: datetime, pressures: Sequence[int], *, flags: Sequence[str]) -> list[Any]:
    from .models import EvidenceField, ProfileLevel  # noqa: PLC0415

    reference = datetime.now(UTC)
    return [
        ProfileLevel(
            pressure_hpa=pressure,
            fields=[
                EvidenceField(field=name, value=None, provenance=unavailable_provenance(valid_time, units=units, flags=flags, level=f"{pressure} hPa", reference=reference))
                for name, units in UNAVAILABLE_PROFILE_FIELDS
            ],
        )
        for pressure in pressures
    ]
