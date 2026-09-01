"""Scheduler-facing view of ``registry/source_data.py``.

The registry stays the single source of truth for policy, licence, cadence and
implementation state. This module only derives the numbers a scheduler needs
(seconds, allowlists, bboxes) and holds the adapter registration table, so an
adapter author never edits the scheduler.
"""

from __future__ import annotations

import importlib
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Mapping

from .contract import ATLANTIC_CONTEXT_BOUNDS, AVALON_CORE_BOUNDS, Adapter

EXPERIMENT_ROOT = Path(__file__).resolve().parent.parent

MIN_POLL_SECONDS = 300
MAX_POLL_SECONDS = 1800
DEFAULT_CYCLE_SECONDS = 21600
DEFAULT_FRESHNESS_SECONDS = 2 * DEFAULT_CYCLE_SECONDS
FORWARD_HOURS = 24

# Core evidence vocabulary for this experiment. Adapters may narrow it, never
# widen it: unrequested variables are what blow the storage cap.
DEFAULT_VARIABLES = (
    "temperature_2m",
    "dew_point_2m",
    "relative_humidity_2m",
    "wind_u_10m",
    "wind_v_10m",
    "mean_sea_level_pressure",
    "precipitation_accumulation",
    "total_cloud",
    "visibility",
)

#: The cloud steering levels the motion derivation reads (display only).
STEERING_WIND_VARIABLES = (
    "wind_u_850hPa", "wind_v_850hPa", "wind_u_700hPa", "wind_v_700hPa", "wind_u_500hPa", "wind_v_500hPa",
)

#: Vertical velocity (omega, Pa s-1) at the same three steering levels, read
#: by the `development-residual` interpolation method to decide WHEN inside an
#: interval the model made or destroyed cloud. Display only, exactly as the
#: steering winds are, and declared at all three levels for the same reason
#: they are: the level a cloud stratum steers on is a display-derivation
#: table that may change, and the retrieval should not have to change with it.
VERTICAL_VELOCITY_VARIABLES = ("omega_850hPa", "omega_700hPa", "omega_500hPa")

VARIABLE_OVERRIDES: dict[str, tuple[str, ...]] = {
    # What the GFS adapter actually stores: the surface set plus the
    # provider-declared cloud strata, the jet-level winds and column water.
    # Stated so run metadata does not inherit a default that no longer
    # matches (precipitation_accumulation is deliberately not retrieved).
    "noaa-gfs": (
        "temperature_2m", "dew_point_2m", "relative_humidity_2m",
        "wind_u_10m", "wind_v_10m", "mean_sea_level_pressure", "visibility",
        "total_cloud", "cloud_low", "cloud_middle", "cloud_high",
        "wind_u_200hPa", "wind_v_200hPa", "wind_u_300hPa", "wind_v_300hPa",
        "wind_u_850hPa", "wind_v_850hPa", "wind_u_700hPa", "wind_v_700hPa",
        "wind_u_500hPa", "wind_v_500hPa",
        "omega_850hPa", "omega_700hPa", "omega_500hPa",
        "precipitable_water",
    ),
    "noaa-swpc-kp": ("kp_index", "a_running", "kp_status"),
    "noaa-swpc-rtsw": ("bz_gsm", "bt"),
    "noaa-swpc-ovation": ("aurora_probability",),
    # HRDPS and RDPS carry the default surface set plus the cloud steering
    # winds and the vertical velocity at the same levels; all are declared
    # optional in the adapter manifest, so a level a cycle omits costs the
    # display prior or the development residual and nothing else.
    "eccc-hrdps": DEFAULT_VARIABLES + STEERING_WIND_VARIABLES + VERTICAL_VELOCITY_VARIABLES,
    "eccc-rdps": DEFAULT_VARIABLES + STEERING_WIND_VARIABLES + VERTICAL_VELOCITY_VARIABLES,
    "eccc-radar": ("precipitation_rate", "precipitation_type"),
    "eccc-lightning": ("lightning_strike",),
    "awc-metar-speci": ("temperature", "dew_point", "visibility", "cloud_layers", "weather_codes", "wind_u_10m", "wind_v_10m"),
    "awc-taf": ("forecast_text",),
    "eccc-swob": ("temperature", "dew_point", "relative_humidity", "wind_u_10m", "wind_v_10m", "mean_sea_level_pressure", "visibility"),
    "eccc-radiosonde": ("temperature", "dew_point", "wind_u", "wind_v", "geopotential_height"),
    "eccc-hrdpa": ("precipitation_accumulation",),
    "eccc-rdpa": ("precipitation_accumulation",),
}

# Sources whose native grid is global or continental are stored at the coarser
# context box; anything intended for the Avalon map is cropped hard.
CONTEXT_BOX_SOURCES = frozenset({
    "noaa-gfs", "noaa-gefs", "ecmwf-ifs", "ecmwf-ens", "ecmwf-aifs-single",
    "ecmwf-aifs-ens", "dwd-icon-global", "eccc-gdps", "eccc-geps", "noaa-goes-east", "noaa-swpc-ovation",
})

# Only categories where *every* member carries forecast lead times get
# ``lead_hours``. This list is stated deliberately rather than inherited:
# ``hydrology`` and ``air_quality`` were previously here, but the hydrometric
# records are real-time station observations and the air-quality group mixes the
# RAQDPS forecast with AQHI observations and wildfire hotspots, so both handed
# lead hours to products that have none. ``analysis`` (HRDPA/RDPA/HREPA/CaLDAS)
# is excluded for the same reason: an analysis is valid at one time only.
# ``aviation`` is excluded because it mixes TAF with METAR and PIREP.
FORECAST_CATEGORIES = frozenset({
    "deterministic_forecast",
    "ensemble",
    "postprocessed_forecast",
    "nowcasting",
    "land_surface_forecast",
    "ocean",
    "wave",
    "surge",
    "marine",
})

_RUNS_PER_DAY = re.compile(r"(\d+)\s*(?:runs|analyses|cycles)\s*/?\s*day")
_EVERY_HOURS = re.compile(r"every\s+(\d+)\s*h")
_MINUTES = re.compile(r"(\d+)(?:\s*-\s*(\d+))?\s*(?:minutes?|mins?)\b")
_HOURS = re.compile(r"(\d+(?:\.\d+)?)\s*(?:h\b|hours?\b)")
_UTC_CYCLES = re.compile(r"\b\d{2}(?:/\d{2})+\s*UTC")


def parse_cadence_seconds(text: str) -> int | None:
    """Best-effort nominal cycle length from the registry's prose cadence."""
    lowered = text.lower()
    match = _RUNS_PER_DAY.search(lowered)
    if match and int(match.group(1)) > 0:
        return 86400 // int(match.group(1))
    cycles = _UTC_CYCLES.search(text)
    if cycles:
        return 86400 // (cycles.group(0).count("/") + 1)
    match = _EVERY_HOURS.search(lowered)
    if match:
        return int(match.group(1)) * 3600
    if "hourly" in lowered or lowered.strip() == "1 h":
        return 3600
    match = _MINUTES.search(lowered)
    if match:
        return int(match.group(1)) * 60
    match = _HOURS.search(lowered)
    if match:
        return int(float(match.group(1)) * 3600)
    return None


def parse_freshness_seconds(text: str, cycle_seconds: int) -> int | None:
    """Resolve the registry's freshness prose, including 'two nominal cycles'."""
    lowered = text.lower()
    if "not applicable" in lowered or "unknown" in lowered or "to be established" in lowered:
        return None
    # An explicit duration always wins over prose such as "one issue cycle";
    # several records state both and the number is the tighter promise.
    match = _MINUTES.search(lowered)
    if match:
        return int(match.group(1)) * 60
    match = _HOURS.search(lowered)
    if match:
        return int(float(match.group(1)) * 3600)
    return 2 * cycle_seconds


def _poll_seconds(cycle_seconds: int) -> int:
    """Poll several times per cycle so a new run is noticed promptly, but never
    faster than a provider should be asked."""
    return max(MIN_POLL_SECONDS, min(MAX_POLL_SECONDS, cycle_seconds // 4))


@dataclass(frozen=True)
class IngestConfig:
    """Everything the scheduler and an adapter need, derived from the registry."""

    source_id: str
    producer: str
    product: str
    category: str
    registry_status: str
    cadence_seconds: int
    cycle_seconds: int
    freshness_threshold_seconds: int | None
    variables: tuple[str, ...]
    levels: tuple[str, ...]
    lead_hours: tuple[int, ...]
    bounds: Mapping[str, float]
    bounds_name: str
    access_endpoints: tuple[str, ...]
    licence: str
    attribution: str
    may_enter_consensus: bool
    consensus_family: str | None
    documentation_urls: tuple[str, ...] = ()

    @property
    def ingestible(self) -> bool:
        """Only catalogued, non-credential sources may be scheduled here."""
        return self.registry_status == "implementing" and self.freshness_threshold_seconds is not None


def _load_registry() -> dict[str, Any]:
    if str(EXPERIMENT_ROOT) not in sys.path:
        sys.path.insert(0, str(EXPERIMENT_ROOT))
    module = importlib.import_module("registry.source_data")
    return module.registry()


def _config_from_record(record: Mapping[str, Any]) -> IngestConfig:
    cycle = parse_cadence_seconds(str(record["cadence"])) or DEFAULT_CYCLE_SECONDS
    freshness = parse_freshness_seconds(str(record["freshness_threshold"]), cycle)
    variable_block = record["variables"][0] if record["variables"] else {"names": [], "levels": []}
    source_id = str(record["id"])
    context = source_id in CONTEXT_BOX_SOURCES
    forecast = record["category"] in FORECAST_CATEGORIES
    consensus = record.get("consensus", {})
    # Never poll slower than half the freshness promise, or a source would be
    # reported stale before we had a chance to look for a newer run.
    poll = _poll_seconds(cycle)
    if freshness is not None:
        poll = min(poll, max(MIN_POLL_SECONDS, freshness // 2))
    return IngestConfig(
        source_id=source_id,
        producer=str(record["producer"]),
        product=str(record["product"]),
        category=str(record["category"]),
        registry_status=str(record["status"]),
        cadence_seconds=poll,
        cycle_seconds=cycle,
        freshness_threshold_seconds=freshness,
        variables=VARIABLE_OVERRIDES.get(source_id, DEFAULT_VARIABLES),
        levels=tuple(variable_block.get("levels", ())),
        lead_hours=tuple(range(FORWARD_HOURS + 1)) if forecast else (),
        bounds=ATLANTIC_CONTEXT_BOUNDS if context else AVALON_CORE_BOUNDS,
        bounds_name="atlantic_context" if context else "avalon_core",
        access_endpoints=tuple(record.get("access_endpoints", ())),
        licence=str(record["licence"]["name"]),
        attribution=str(record["attribution"]),
        may_enter_consensus=bool(consensus.get("eligible", False)),
        consensus_family=consensus.get("family"),
        documentation_urls=tuple(record.get("documentation_urls", ())),
    )


_configs: dict[str, IngestConfig] | None = None


def ingest_configs() -> dict[str, IngestConfig]:
    global _configs
    if _configs is None:
        _configs = {record["id"]: _config_from_record(record) for record in _load_registry()["sources"]}
    return _configs


def get_config(source_id: str) -> IngestConfig:
    try:
        return ingest_configs()[source_id]
    except KeyError as error:
        raise KeyError(f"{source_id} is not in the source registry") from error


_adapters: dict[str, Adapter] = {}


def register(adapter: Adapter) -> Adapter:
    """Register one adapter against its registry source id.

    Usable as a decorator on the adapter class' instantiation site; returns the
    adapter so ``ADAPTER = register(MyAdapter())`` reads naturally.
    """
    source_id = getattr(adapter, "source_id", None)
    if not source_id:
        raise ValueError("an adapter must declare source_id")
    if source_id not in ingest_configs():
        raise KeyError(f"{source_id} is not in the source registry; add it there first")
    if source_id in _adapters:
        if type(_adapters[source_id]).__name__ == type(adapter).__name__:
            _adapters[source_id] = adapter
            return adapter
        raise ValueError(f"{source_id} already has a registered adapter")
    _adapters[source_id] = adapter
    return adapter


def get_adapter(source_id: str) -> Adapter | None:
    return _adapters.get(source_id)


def registered_adapters() -> dict[str, Adapter]:
    return dict(_adapters)


def scheduled() -> Iterator[tuple[Adapter, IngestConfig]]:
    """Registered adapters whose registry record permits live ingestion."""
    for source_id, adapter in sorted(_adapters.items()):
        config = get_config(source_id)
        if config.ingestible:
            yield adapter, config


def load_adapters(module_names: tuple[str, ...] = ("ingest.adapters",)) -> list[str]:
    """Import adapter modules for their registration side effects.

    Missing modules are not an error: adapter families land independently and
    the worker must start with whatever exists today.
    """
    loaded: list[str] = []
    for name in module_names:
        try:
            importlib.import_module(name)
        except ModuleNotFoundError:
            continue
        loaded.append(name)
    return loaded
