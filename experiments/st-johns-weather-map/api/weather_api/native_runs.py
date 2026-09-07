"""Finite latest/previous discovery over an existing bounded source adapter.

This retains two directory candidates, not provider grids. A named run is
resolved before a source cache read and cannot silently advance to another run.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import threading
from typing import Callable

from ingest.contract import FetchWindow, RunCandidate


class RunUnavailable(ValueError):
    pass


class NativeRunInventory:
    def __init__(self, discover: Callable[[FetchWindow], list[RunCandidate]], *, now: Callable[[], datetime], clock: Callable[[], float], ttl: float):
        self._discover, self._now, self._clock, self._ttl = discover, now, clock, ttl
        self._lock = threading.Lock()
        self._cached: tuple[float, tuple[RunCandidate, ...]] | None = None

    def candidates(self) -> tuple[RunCandidate, ...]:
        with self._lock:
            elapsed = self._clock()
            if self._cached is not None and elapsed < self._cached[0]:
                return deepcopy(self._cached[1])
            reference = self._now()
            declared = self._discover(FetchWindow(now=reference, back_hours=24, forward_hours=0))
            by_id = {}
            for candidate in declared:
                if candidate.run_time is not None and candidate.run_time <= reference:
                    if candidate.provider_run_id in by_id and by_id[candidate.provider_run_id] != candidate:
                        raise ValueError('Conflicting native run identities')
                    by_id[candidate.provider_run_id] = candidate
            candidates = tuple(sorted(by_id.values(), key=lambda item: item.run_time, reverse=True)[:2])
            self._cached = (self._clock() + self._ttl, candidates)
            return deepcopy(candidates)

    def resolve(self, run_id: str) -> RunCandidate:
        for candidate in self.candidates():
            if candidate.provider_run_id == run_id:
                return candidate
        raise RunUnavailable('Run no longer available in the bounded latest/previous inventory')
