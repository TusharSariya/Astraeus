from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path

from weather_api.swob_query import SWOBStationObservation
from weather_api.swob_query_worker import normalize
from weather_api.swpc_plasma_worker import validated


SCRIPT = Path(__file__).parents[1] / "scripts" / "prove_source_cache.py"
SPEC = importlib.util.spec_from_file_location("prove_source_cache", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
proof = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(proof)


def _swob_decode(body: bytes) -> tuple[SWOBStationObservation, ...]:
    return tuple(
        SWOBStationObservation(
            station_id=item["station_id"],
            station_name=item.get("station_name"),
            observation_time=datetime.fromisoformat(item["observation_time"]),
            latitude=item["latitude"],
            longitude=item["longitude"],
            dataset=item["dataset"],
            provider_report_id=item.get("provider_report_id"),
            field_quality_tokens=item["field_quality_tokens"],
            station_metadata=item["station_metadata"],
            values=item["values"],
        )
        for item in normalize(json.loads(body))
    )


def _plasma_decode(body: bytes, at: datetime | None) -> dict[str, object]:
    rows = validated(body)
    if at is None:
        return {"rows": len(rows)}
    candidates = []
    for row in rows:
        stamp = datetime.fromisoformat(row["time_tag"]).replace(tzinfo=UTC)
        if stamp <= at:
            candidates.append((stamp, row["source"], row))
    newest = max(stamp for stamp, _source, _row in candidates)
    choices = [(source, row) for stamp, source, row in candidates if stamp == newest]
    active = [item for item in choices if item[1]["active"] is True]
    source, row = sorted(active if len(active) == 1 else choices, key=lambda item: item[0])[0]
    return {"time": newest.isoformat(), "source": source, "row": row, "active_count": len(active)}


def test_swob_proof_uses_one_fixture_request_and_reuses_typed_cache():
    result = proof.prove_swob(decode=_swob_decode)

    assert result["provider_network_requests"] == 0
    assert result["fixture_transport_requests"] == 1
    assert result["cache_reused"] is True
    assert result["values"] == {
        "temperature_2m": 12.4,
        "dew_point_2m": 8.2,
        "relative_humidity_2m": 76.0,
        "mean_sea_level_pressure": 1013.4,
        "wind_speed_10m": 4.5,
        "wind_direction_10m": 210.0,
    }
    assert len(result["acquisition_sha256"]) == 64


def test_plasma_proof_uses_one_fixture_request_and_reuses_typed_cache():
    result = proof.prove_plasma(bounded_decode=_plasma_decode)

    assert result["provider_network_requests"] == 0
    assert result["fixture_transport_requests"] == 1
    assert result["cache_reused"] is True
    assert result["native_spacecraft"] == "SOLAR1"
    assert result["measured_at"] == "2026-09-05T17:57:00+00:00"
    assert result["values"] == {
        "solar_wind_density": 3.63,
        "solar_wind_speed": 339.2,
        "solar_wind_temperature": 86894.0,
    }
    assert len(result["acquisition_sha256"]) == 64
