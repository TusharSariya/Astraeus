"""Finite safe read dispositions; no credentials, acquisition or coverage cache."""
from collections import OrderedDict
from datetime import UTC, datetime
from functools import wraps
import threading
import time

import httpx

from .source_contract import SourceConfiguration

STATUS_SECONDS = 300
MAX_STATUS_ENTRIES = 128
_lock = threading.Lock()
_latest: OrderedDict[str, tuple[float, SourceConfiguration]] = OrderedDict()


def _record(source_id: str, state: str, reason: str) -> None:
    outcome = SourceConfiguration(state=state, reason=reason, checked_at=datetime.now(UTC))
    with _lock:
        _latest[source_id] = time.monotonic() + STATUS_SECONDS, outcome
        _latest.move_to_end(source_id)
        while len(_latest) > MAX_STATUS_ENTRIES:
            _latest.popitem(last=False)


def latest_configuration(source_id: str) -> SourceConfiguration | None:
    with _lock:
        entry = _latest.get(source_id)
        if entry is None:
            return None
        if time.monotonic() >= entry[0]:
            del _latest[source_id]
            return None
        return entry[1]


def observed_read(method):
    """Record only fixed safe reasons; propagate source-local failures unchanged."""
    @wraps(method)
    def call(self, *args, **kwargs):
        try:
            value = method(self, *args, **kwargs)
        except Exception as error:
            from .native_runs import RunUnavailable
            state, reason = "acquisition_failed", "The most recent bounded source read failed; current coverage is not established"
            if isinstance(error, RunUnavailable):
                state, reason = "product_unavailable", "The requested native product or run was unavailable in its bounded inventory"
            cause = error
            # Wrapped HTTP failures keep their status without exposing URLs,
            # headers, exception text or any authentication material.
            for _ in range(8):
                if isinstance(cause, httpx.HTTPStatusError) and cause.response.status_code in (401, 403):
                    state, reason = "access_denied", "The provider denied the most recent bounded source read"
                    break
                cause = cause.__cause__
                if cause is None:
                    break
            _record(self.source_id, state, reason)
            raise
        _record(self.source_id, "ready", "The most recent bounded source read completed; actual field and time coverage are reported separately")
        return value
    return call
