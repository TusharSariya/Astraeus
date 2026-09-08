"""Source-local delivery over the accepted CYYT METAR and native TAF readers.

Owning contracts: api-first-source-delivery, awc-metar-demand-query,
awc-taf-app-vertical and timestamp-demand-query-cache. No new acquisition,
forecast-group composition, station selection or cache policy lives here.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Callable

from .models import EvidenceField
from .native_runs import RunUnavailable
from .source_contract import SourceCapability, SourceVariant
from .source_status import observed_read

METAR_FIELDS = (
    "temperature_2m", "dew_point_2m", "relative_humidity_2m",
    "mean_sea_level_pressure", "visibility", "total_cloud_okta",
    "wind_speed_10m", "wind_direction_10m", "wind_gust_10m",
    *(f"cloud_layer_{slot}_{suffix}" for slot in range(1, 7)
      for suffix in ("cover_code", "cover", "base")),
)


def _selection(selected: datetime, run: str, refresh: bool) -> datetime:
    if run != "latest":
        raise RunUnavailable("The CYYT aviation reader does not expose selectable runs")
    if refresh:
        raise RunUnavailable("The CYYT aviation reader uses its finite provider cache and does not support forced refresh")
    if selected.tzinfo is None or selected.utcoffset() is None:
        raise ValueError("Aviation selected time must include an offset")
    return selected.astimezone(UTC)


class METARSource:
    source_id = "awc-metar-speci"
    product_id = "metar"

    def __init__(self, factory: Callable | None = None):
        if factory is None:
            from .metar_query import metar_query_service
            factory = metar_query_service
        self.factory = factory

    def descriptors(self) -> tuple[SourceCapability, ...]:
        from registry import fields as catalogue
        return tuple(SourceCapability(
            source_id=self.source_id, product_id=self.product_id, field=key,
            variants=[SourceVariant(kind="observation")],
            levels=[str(catalogue.field(key).level)], point=True, point_product="METAR",
            native_series=False, run_selection="not_applicable",
            time_semantics="Latest CYYT native observation at or before selection, strictly less than one hour old",
            coverage_description="Existing CYYT station sampling and distance bounds; native report identity, QC and missingness remain",
        ) for key in METAR_FIELDS)

    @observed_read
    def read_point(self, latitude: float, longitude: float, selected: datetime,
                   *, run: str = "latest", refresh: bool = False) -> tuple[EvidenceField, ...]:
        selected = _selection(selected, run, refresh)
        fields, _observed, _entry = self.factory().point_fields(latitude, longitude, selected)
        return tuple(field.model_copy(deep=True) for field in fields)

    def plan_series(self, start, end, *, run="latest"):
        return None


class TAFDelivery:
    """Native report delivery, deliberately separate from scalar point readers.

    Overlapping conditional groups cannot be represented by one EvidenceField.
    The existing /aviation/taf endpoint remains the read path. Its descriptor
    therefore declares no generic point token or synthetic native Series path.
    """
    source_id = "awc-taf"
    product_id = "taf"

    def __init__(self, factory: Callable | None = None):
        if factory is None:
            from .taf_query import taf_query_service
            factory = taf_query_service
        self.factory = factory

    def descriptors(self) -> tuple[SourceCapability, ...]:
        return (SourceCapability(
            source_id=self.source_id, product_id=self.product_id, field="raw_report",
            variants=[SourceVariant(kind="deterministic")], levels=["station"],
            point=False, native_series=False, run_selection="latest",
            time_semantics="All native half-open TAF groups containing selection, in provider order; issue and interval identity preserved",
            coverage_description="CYYT native report through /aviation/taf?station=CYYT&at=<instant>; overlapping groups remain uncomposed",
        ),)

    @observed_read
    def read_report(self, station: str, selected: datetime, *, run: str = "latest",
                    refresh: bool = False) -> dict:
        selected = _selection(selected, run, refresh)
        if station.upper() != "CYYT":
            raise ValueError("only the contracted CYYT TAF is available")
        return deepcopy(self.factory().query(station, selected))

    def plan_series(self, start, end, *, run="latest"):
        return None
