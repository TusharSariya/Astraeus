"""Point-only SWOB delivery over the existing finite exact-time coordinator.

Owning experiment contracts: api-first-source-delivery and swob-demand-query.
The shared catalogue owns descriptors and registration. Cached report times are
not an archive inventory and cannot establish native Series range coverage.
"""
from __future__ import annotations

from datetime import datetime
from typing import Callable

from .models import EvidenceField
from .native_runs import RunUnavailable
from .source_status import observed_read
from .swob_query import SWOBQueryService


class SWOBPointReader:
    source_id = "eccc-swob"
    product_id = "swob-observations"

    def __init__(self, factory: Callable[[], SWOBQueryService]):
        self.factory = factory

    @observed_read
    def read_point(self, latitude: float, longitude: float, selected: datetime, *,
                   run: str = "latest", refresh: bool = False) -> tuple[EvidenceField, ...]:
        if run != "latest":
            raise RunUnavailable("SWOB station observations have no forecast run selection")
        return tuple(field.model_copy(deep=True) for field in self.factory().point_fields(
            latitude, longitude, selected, refresh=refresh))

    def plan_series(self, start: datetime, end: datetime, *, run: str = "latest") -> None:
        """Unsupported: bounded realtime point snapshots do not promise history.

        Do not enumerate cached times into Series frames: ordinary Series point
        reads could reacquire expired snapshots or an absent report, silently
        turning a cache inventory into an unapproved archive acquisition rule.
        """
        return None
