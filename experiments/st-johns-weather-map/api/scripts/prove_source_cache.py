#!/usr/bin/env python3
"""Run deterministic, network-free cache proofs through existing source services.

Run from ``experiments/st-johns-weather-map/api`` in an exact-head Linux
environment whose dependencies are already installed. The services use their
real bounded worker commands; HTTP is replaced with an exact-URL fixture
transport, so this command cannot contact a provider.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable

import httpx

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ingest.adapters.swpc import RTSW_WIND_URL  # noqa: E402
from weather_api.swob_query import SWOBQueryService, _request_url  # noqa: E402
from weather_api.swpc_plasma_query import SWPCPlasmaQueryService  # noqa: E402


FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
SWOB_FIXTURE = FIXTURES / "source_proof" / "swob_msc.json"
PLASMA_FIXTURE = FIXTURES / "space_weather" / "rtsw_wind_1m.json"
SWOB_SELECTED = datetime(2026, 9, 7, 3, 0, tzinfo=UTC)
PLASMA_SELECTED = datetime(2026, 9, 5, 17, 57, 30, tzinfo=UTC)
LATITUDE = 47.5615
LONGITUDE = -52.7126
SWOB_EXPECTED_VALUES = {
    "temperature_2m": 12.4,
    "dew_point_2m": 8.2,
    "relative_humidity_2m": 76.0,
    "mean_sea_level_pressure": 1013.4,
    "wind_speed_10m": 4.5,
    "wind_direction_10m": 210.0,
}
PLASMA_EXPECTED_VALUES = {
    "solar_wind_density": 3.63,
    "solar_wind_speed": 339.2,
    "solar_wind_temperature": 86894.0,
}


def _fixture_transport(expected_url: str, body: bytes) -> tuple[httpx.Client, list[str]]:
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        actual = str(request.url)
        if actual != expected_url:
            raise AssertionError(f"fixture transport refused unexpected URL: {actual}")
        requests.append(actual)
        return httpx.Response(
            200,
            content=body,
            headers={"cache-control": "max-age=60", "content-type": "application/json"},
            request=request,
        )

    return httpx.Client(transport=httpx.MockTransport(handler)), requests


def prove_swob(
    *, decode: Callable[[bytes], tuple[object, ...]] | None = None,
) -> dict[str, object]:
    expected_url = _request_url(LATITUDE, LONGITUDE, SWOB_SELECTED)
    client, requests = _fixture_transport(expected_url, SWOB_FIXTURE.read_bytes())
    kwargs: dict[str, object] = {
        "client": client,
        "clock": lambda: 100.0,
        "utcnow": lambda: SWOB_SELECTED,
    }
    if decode is not None:
        kwargs["decode"] = decode
    service = SWOBQueryService(**kwargs)

    first = service.point_fields(LATITUDE, LONGITUDE, SWOB_SELECTED)
    second = service.point_fields(LATITUDE, LONGITUDE, SWOB_SELECTED)
    first_receipt = first[0].provenance.swob_acquisition
    second_receipt = second[0].provenance.swob_acquisition
    if first_receipt is None or second_receipt is None:
        raise AssertionError("SWOB proof did not retain its typed acquisition")
    if len(requests) != 1 or first_receipt.body_sha256 != second_receipt.body_sha256:
        raise AssertionError("SWOB repeat query did not reuse one cache identity")
    values = {field.field: field.value for field in first}
    if values != SWOB_EXPECTED_VALUES:
        raise AssertionError(f"SWOB default worker returned unexpected fixture values: {values}")
    if any(field.provenance.valid_time != SWOB_SELECTED for field in first):
        raise AssertionError("SWOB default worker returned an unexpected native time")

    return {
        "source_id": "eccc-swob",
        "selected_time": SWOB_SELECTED.isoformat(),
        "fixture": str(SWOB_FIXTURE.relative_to(Path.cwd())),
        "fixture_transport_requests": len(requests),
        "provider_network_requests": 0,
        "cache_reused": True,
        "acquisition_sha256": first_receipt.body_sha256,
        "values": values,
    }


def prove_plasma(
    *, bounded_decode: Callable[[bytes, datetime | None], dict[str, object]] | None = None,
) -> dict[str, object]:
    client, requests = _fixture_transport(RTSW_WIND_URL, PLASMA_FIXTURE.read_bytes())
    kwargs: dict[str, object] = {
        "client": client,
        "clock": lambda: 100.0,
        "utcnow": lambda: PLASMA_SELECTED,
    }
    if bounded_decode is not None:
        kwargs["bounded_decode"] = bounded_decode
    service = SWPCPlasmaQueryService(**kwargs)

    first = service.latest(PLASMA_SELECTED)
    second = service.latest(PLASMA_SELECTED)
    if len(requests) != 1 or first.acquisition.body_sha256 != second.acquisition.body_sha256:
        raise AssertionError("plasma repeat query did not reuse one cache identity")
    values = {
        "solar_wind_density": first.proton_density_cm3,
        "solar_wind_speed": first.proton_speed_km_s,
        "solar_wind_temperature": first.proton_temperature_k,
    }
    if values != PLASMA_EXPECTED_VALUES:
        raise AssertionError(f"plasma default worker returned unexpected fixture values: {values}")
    if first.feed_declared_spacecraft != "SOLAR1" or first.measured_at != datetime(2026, 9, 5, 17, 57, tzinfo=UTC):
        raise AssertionError("plasma default worker returned an unexpected native identity")

    return {
        "source_id": "noaa-swpc-plasma",
        "selected_time": PLASMA_SELECTED.isoformat(),
        "fixture": str(PLASMA_FIXTURE.relative_to(Path.cwd())),
        "fixture_transport_requests": len(requests),
        "provider_network_requests": 0,
        "cache_reused": True,
        "acquisition_sha256": first.acquisition.body_sha256,
        "native_spacecraft": first.feed_declared_spacecraft,
        "measured_at": first.measured_at.isoformat(),
        "values": values,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=("all", "swob", "plasma"), default="all")
    args = parser.parse_args()
    proofs = []
    if args.source in ("all", "swob"):
        proofs.append(prove_swob())
    if args.source in ("all", "plasma"):
        proofs.append(prove_plasma())
    print(json.dumps({"proofs": proofs}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
