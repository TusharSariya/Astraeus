"""ECMWF Open Data IFS adapter - deliberately unresolved and non-publishing.

The ``.index`` sidecar parser below is real and tested, but discovery is not
resolved, so this adapter refuses rather than publishes.

Verified 2026-08-30: ``data.ecmwf.int/forecasts/`` lists only the last four
dates and ``/forecasts/20260830/`` is a 404, so the run this window needs cannot
be addressed by the dated path this adapter assumed. Until the real listing
contract is pinned - which dates exist, when a cycle appears, and how a lead's
``.index`` maps onto its ``.grib2`` - any run it returned would be a guess about
which cycle the numbers came from.

The registry record stays ``implementing``. Publishing a partial or mislabelled
IFS run is exactly the failure this experiment exists to rule out, so
:meth:`ECMWFIFSAdapter.discover` raises :class:`AdapterUnavailable` with that
reason and :meth:`fetch` cannot be reached.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from ingest.contract import (
    ATLANTIC_CONTEXT_BOUNDS,
    Adapter,
    AdapterUnavailable,
    FetchWindow,
    RunCandidate,
    RunResult,
)
from ingest.http import PoliteClient
from ingest.registry import register

ECMWF_OPEN_DATA_BASE = "https://data.ecmwf.int/forecasts"
MAX_LEAD_HOURS = 24

UNRESOLVED_REASON = (
    "ECMWF Open Data discovery is unresolved: data.ecmwf.int/forecasts/ lists only the last "
    "four dates and the current date returned 404 on 2026-08-30, so the dated cycle path this "
    "adapter assumed cannot address a run in the window. No IFS run is published until the "
    "listing contract is pinned; a guessed cycle would mislabel every value."
)

# ECMWF parameter name -> canonical variable name
ECMWF_PARAM_MAP = {
    "2t": "temperature_2m",
    "2d": "dew_point_2m",
    "10u": "wind_u_10m",
    "10v": "wind_v_10m",
    "msl": "mean_sea_level_pressure",
    "tp": "precipitation_accumulation",
    "tcc": "total_cloud",
}

# GRIB short names produced by cfgrib for ECMWF
ECMWF_GRIB_RENAME = {
    "t2m": "temperature_2m",
    "d2m": "dew_point_2m",
    "u10": "wind_u_10m",
    "v10": "wind_v_10m",
    "msl": "mean_sea_level_pressure",
    "tp": "precipitation_accumulation",
    "tcc": "total_cloud",
}


def parse_ecmwf_index(text: str, target_params: set[str]) -> list[tuple[int, int]]:
    """Parse ECMWF JSON-lines .index and return sorted (start, end) byte ranges."""
    selected_ranges: list[tuple[int, int]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except Exception:
            continue
        param = str(entry.get("param", "")).lower()
        if param in target_params:
            offset = entry.get("_offset")
            length = entry.get("_length")
            if offset is not None and length is not None:
                selected_ranges.append((int(offset), int(offset) + int(length) - 1))
    return sorted(selected_ranges, key=lambda item: item[0])


class ECMWFIFSAdapter:
    """Registered so the source id is known; never yields data (see module docstring)."""

    source_id = "ecmwf-ifs"
    adapter_version = "ecmwf-ifs-v1"

    def __init__(
        self,
        *,
        base_url: str = ECMWF_OPEN_DATA_BASE,
        bounds: Mapping[str, float] = ATLANTIC_CONTEXT_BOUNDS,
        client: PoliteClient | None = None,
    ) -> None:
        self._base_url = base_url
        self._bounds = dict(bounds)
        self._client = client

    def _get_client(self) -> PoliteClient:
        return self._client or PoliteClient()

    def discover(self, window: FetchWindow) -> list[RunCandidate]:
        raise AdapterUnavailable(UNRESOLVED_REASON)

    def fetch(self, candidate: RunCandidate, window: FetchWindow, workdir: Path) -> RunResult:
        raise AdapterUnavailable(UNRESOLVED_REASON)


IFS_ADAPTER = register(ECMWFIFSAdapter())
