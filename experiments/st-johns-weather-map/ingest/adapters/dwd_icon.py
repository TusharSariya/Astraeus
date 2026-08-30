"""DWD ICON Global adapter - deliberately unresolved and non-publishing.

``opendata.dwd.de/weather/nwp/icon/grib/00/t_2m/`` is reachable (verified
2026-08-30), so the blocker is not availability but geometry. The files served
there are ``icon_global_icosahedral_single-level_*``: ICON's native grid is an
unstructured icosahedral mesh, not a lat/lon array. ``crop_to_bbox`` and every
point sample downstream assume rectilinear latitude and longitude coordinates,
so decoding an icosahedral file and sampling it as if it were a grid would
produce numbers that are not the values at the requested coordinate.

Doing this properly needs either the ``icon_global_lat-lon_*`` regular-grid
variant, if DWD publishes one for these fields, or DWD's own ICON grid
description plus a documented regridding step. Neither is resolved, and this
experiment does not invent a regrid. The registry record stays ``implementing``
and both entry points raise :class:`AdapterUnavailable`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

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

DWD_ICON_BASE = "https://opendata.dwd.de/weather/nwp/icon/grib"
MAX_LEAD_HOURS = 24

UNRESOLVED_REASON = (
    "DWD ICON Global is served on its native icosahedral mesh "
    "(icon_global_icosahedral_single-level_*), which this stack cannot crop to a bbox or "
    "sample at a coordinate without a regridding step. No regrid is invented here, so no "
    "ICON run is published until either a published lat-lon variant or DWD's grid "
    "description is pinned."
)

DWD_VARS = {
    "temperature_2m": "t_2m",
    "relative_humidity_2m": "relhum_2m",
    "wind_u_10m": "u_10m",
    "wind_v_10m": "v_10m",
    "mean_sea_level_pressure": "pmsl",
    "total_cloud": "clct",
    "precipitation_accumulation": "tot_prec",
}

DWD_GRIB_RENAME = {
    "t2m": "temperature_2m",
    "r2": "relative_humidity_2m",
    "u10": "wind_u_10m",
    "v10": "wind_v_10m",
    "prmsl": "mean_sea_level_pressure",
    "clct": "total_cloud",
    "tp": "precipitation_accumulation",
    "tot_prec": "precipitation_accumulation",
}


class DWDICONAdapter:
    """Registered so the source id is known; never yields data (see module docstring)."""

    source_id = "dwd-icon-global"
    adapter_version = "dwd-icon-v1"

    def __init__(
        self,
        *,
        base_url: str = DWD_ICON_BASE,
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


ICON_ADAPTER = register(DWDICONAdapter())
