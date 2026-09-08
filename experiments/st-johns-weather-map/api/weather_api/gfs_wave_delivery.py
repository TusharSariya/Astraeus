"""Point-only wrapper; api-first-source-delivery/openmeteo-gfs-wave-demand.

The existing intermediary query owns acquisition, nulls, units and finite cache.
"""
from __future__ import annotations

from datetime import datetime
from typing import Callable

from registry import fields as catalogue

from .models import EvidenceField
from .native_runs import RunUnavailable
from .openmeteo_gfs_wave_query import OPEN_METEO_GFS_WAVE_API_FIELDS, OPEN_METEO_GFS_WAVE_MODEL, OpenMeteoGfsWaveQueryService
from .source_contract import SourceCapability, SourceVariant
from .source_status import observed_read


class GFSWaveSource:
    source_id = "openmeteo-gfs-wave"
    product_id = OPEN_METEO_GFS_WAVE_MODEL

    def __init__(self, factory: Callable[[], OpenMeteoGfsWaveQueryService]):
        self.factory = factory

    def descriptors(self) -> tuple[SourceCapability, ...]:
        return tuple(SourceCapability(
            source_id=self.source_id, product_id=self.product_id, field=key,
            variants=[SourceVariant(kind="deterministic")],
            levels=[str(catalogue.field(key).level)], point=True,
            point_product="GFS Wave", native_series=False, run_selection="not_applicable",
            time_semantics=("Exact selected hourly timestamp returned by Open-Meteo; "
                            "the intermediary response does not identify a producer run"),
            coverage_description=("Selected returned sea cell only; native nulls and wave units remain. "
                                  "Reprocessed non-primary evidence, never a derivation input; "
                                  "no native Series inventory is established"),
        ) for _api_field, key in OPEN_METEO_GFS_WAVE_API_FIELDS.values())

    @observed_read
    def read_point(self, latitude: float, longitude: float, selected: datetime, *,
                   run: str = "latest", refresh: bool = False) -> tuple[EvidenceField, ...]:
        if run != "latest":
            raise RunUnavailable("GFS-Wave intermediary values do not expose selectable producer runs")
        if refresh:
            raise ValueError("GFS-Wave does not support explicit refresh of its fixed-lifetime point cache")
        return tuple(field.model_copy(deep=True) for field in self.factory().point_fields(
            latitude, longitude, selected))

    def plan_series(self, start: datetime, end: datetime, *, run: str = "latest") -> None:
        """A selected intermediary hour does not establish a native run timeline."""
        return None
