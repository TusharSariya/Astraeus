"""API-facing science: consensus policy, display fallback and quantity checks.

The meteorological derivations themselves live in ``ingest.meteorology`` so the
worker image — which does not ship this package — can use them too. They are
re-exported here verbatim, so this module's public surface is unchanged for
every existing caller.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Literal
from zoneinfo import ZoneInfo

# ``ingest`` ships beside ``api`` in the repository and in both images, the same
# way ``weather_api.store`` and ``ingest.registry`` resolve it.
EXPERIMENT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(EXPERIMENT_ROOT) not in sys.path:
    sys.path.insert(0, str(EXPERIMENT_ROOT))

from ingest.meteorology import (  # noqa: E402, F401
    HUMIDITY_DERIVATION,
    HUMIDITY_DERIVATION_VERSION,
    WIND_DERIVATION,
    WIND_DERIVATION_VERSION,
    WIND_DIRECTION_UNITS,
    WIND_SPEED_UNITS,
    fog_state,
    haversine_km,
    interpolate_wind,
    precipitation_interval_hours,
    radar_echo_semantics,
    relative_humidity_from_dewpoint,
    resolve_relative_humidity,
    resolve_wind,
)


@dataclass(frozen=True)
class ConsensusCandidate:
    source_id: str
    forecast_centre: str
    family: str
    value: float
    fresh: bool = True
    quality_passed: bool = True
    is_eccc_regional: bool = False
    is_ensemble: bool = False


@dataclass(frozen=True)
class ConsensusResult:
    available: bool
    value: float | None
    centre_range: tuple[float, float] | None
    contributors: tuple[str, ...]
    reason: str


def build_consensus(candidates: Iterable[ConsensusCandidate]) -> ConsensusResult:
    eligible = [item for item in candidates if item.fresh and item.quality_passed]
    has_eccc = any(item.is_eccc_regional for item in eligible)
    has_independent = any(item.forecast_centre != "ECCC" and not item.is_ensemble for item in eligible)
    has_ensemble = any(item.is_ensemble for item in eligible)
    if not (has_eccc and has_independent and has_ensemble):
        return ConsensusResult(False, None, None, (), "minimum evidence not met")

    # One representative per centre/family. Ensembles prove minimum evidence but
    # remain distributions and are not averaged into the deterministic centre mean.
    representatives: dict[str, ConsensusCandidate] = {}
    for item in eligible:
        if not item.is_ensemble:
            representatives.setdefault(item.forecast_centre, item)
    values = [item.value for item in representatives.values()]
    if len({item.forecast_centre for item in representatives.values()}) < 2:
        return ConsensusResult(False, None, None, (), "fewer than two independent centres")
    contributors = tuple(item.source_id for item in representatives.values())
    return ConsensusResult(True, round(sum(values) / len(values), 2), (min(values), max(values)), contributors, "minimum evidence met")


def select_fallback(
    consensus_available: bool,
    *,
    hrdps_fresh: bool,
    rdps_fresh: bool,
) -> tuple[Literal["consensus", "fallback", "evidence_only"], str, str]:
    if consensus_available:
        return "consensus", "Experimental consensus", "minimum evidence passes"
    if hrdps_fresh:
        return "fallback", "HRDPS primary - consensus unavailable", "minimum consensus evidence not met"
    if rdps_fresh:
        return "fallback", "RDPS fallback", "consensus and fresh HRDPS unavailable"
    return "evidence_only", "forecast unavailable", "no fresh consensus, HRDPS, or RDPS forecast"


def to_newfoundland(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamp must include an offset")
    return value.astimezone(ZoneInfo("America/St_Johns"))


def validate_distinct_environmental_quantity(quantity: str, units_name: str) -> None:
    expected = {
        "aqhi": "index",
        "pm2_5": "ug m-3",
        "aerosol_optical_depth": "1",
        "extinction": "m-1",
        "tide_prediction": "m",
        "observed_water_level": "m",
        "storm_surge": "m",
    }
    if quantity not in expected or expected[quantity] != units_name:
        raise ValueError("quantity and units are not a recognized distinct environmental field")
