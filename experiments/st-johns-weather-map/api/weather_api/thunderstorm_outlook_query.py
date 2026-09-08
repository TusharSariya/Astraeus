"""Bounded native ECCC outlook report snapshots; no hazard interpretation."""
from __future__ import annotations

import hashlib
import json
import threading
import time
from concurrent.futures import Future
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Callable

from ingest.adapters.eccc_hazards import ECCCThunderstormOutlookAdapter, MAX_COLLECTION_BYTES
from ingest.contract import FetchWindow
from ingest.http import PoliteClient

RETENTION_SECONDS = 60
COLLECTION = "thunderstorm_outlook"


class OutlookUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class OutlookSnapshot:
    revision: str
    body: bytes
    receipt_json: bytes
    retrieved_at: datetime
    retained_until: datetime
    cache_status: str = "miss"
    source_id: str = "eccc-thunderstorm-outlooks"
    operational: bool = False
    primary: bool = False
    scientific_freshness: str = "unknown"

    def metadata(self) -> dict:
        document = json.loads(self.body)
        present = {key for feature in document["features"] for key in feature["properties"]}
        fields = ECCCThunderstormOutlookAdapter.advertised_fields
        return {
            "native_crs": "OGC:CRS84", "source_quality": "unknown",
            "field_dispositions": {field: "observed-empty" if not document["features"] else "retrieved" if field in present else "missing-in-snapshot" for field in fields},
            "uncontracted_properties": sorted(present.difference(fields)),
            "source_id": self.source_id, "revision": self.revision,
            "operational": False, "primary": False, "scientific_freshness": "unknown",
            "retrieved_at": self.retrieved_at.isoformat(), "retained_until": self.retained_until.isoformat(),
            "cache_status": self.cache_status, "collection": COLLECTION,
            "observed_empty": not document["features"],
            "empty_means": "empty native collection in requested box; not a safety all-clear",
            "acquisition": json.loads(self.receipt_json),
            "reports": [{"feature_id": feature.get("id"),
                         "publication_datetime": feature["properties"].get("publication_datetime"),
                         "validity_datetime": feature["properties"].get("validity_datetime"),
                         "expiration_datetime": feature["properties"].get("expiration_datetime"),
                         "file_id": feature["properties"].get("file_id"),
                         "amendment": feature["properties"].get("amendment")}
                        for feature in document["features"]],
        }


class ThunderstormOutlookQuery:
    """One immutable revision, explicit refresh and exact cache-only report reads."""
    def __init__(self, *, adapter: ECCCThunderstormOutlookAdapter | None = None,
                 clock: Callable[[], datetime] = lambda: datetime.now(UTC),
                 monotonic: Callable[[], float] = time.monotonic):
        self.adapter = adapter or ECCCThunderstormOutlookAdapter(PoliteClient(attempts=1))
        self.clock, self.monotonic = clock, monotonic
        self._lock = threading.Lock()
        self._entry: OutlookSnapshot | None = None
        self._deadline = 0.0
        self._flight: Future | None = None

    def _valid(self):
        return self._entry is not None and self.clock() < self._entry.retained_until and self.monotonic() < self._deadline

    def snapshot(self, *, refresh: bool = False) -> OutlookSnapshot:
        with self._lock:
            if not self._valid():
                self._entry = None
            if self._entry is not None and not refresh:
                return replace(self._entry, cache_status="hit")
            leader = self._flight is None
            if leader:
                self._flight = Future()
            future = self._flight
        assert future is not None
        if not leader:
            return replace(future.result(), cache_status="hit")
        try:
            deadline = self.monotonic() + RETENTION_SECONDS
            started = self.clock()
            candidate = self.adapter.discover(FetchWindow(started))[0]
            document = candidate.detail["documents"][COLLECTION]
            features = document["features"]
            if len(features) > 1000 or any(link.get("rel") == "next" for link in document.get("links", [])):
                raise OutlookUnavailable("outlook collection is paginated or oversized")
            if "numberMatched" in document and document["numberMatched"] != len(features):
                raise OutlookUnavailable("outlook collection is incomplete")
            ids = [feature.get("id") for feature in features]
            if any(not isinstance(value, (str, int)) or isinstance(value, bool) for value in ids) or len({str(value) for value in ids}) != len(ids):
                raise OutlookUnavailable("outlook native report identifiers are absent or duplicated")
            body = json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
            receipt = json.dumps(candidate.detail["receipts"][COLLECTION], sort_keys=True).encode()
            if len(body) + len(receipt) > MAX_COLLECTION_BYTES:
                raise OutlookUnavailable("outlook normalized cache exceeds byte ceiling")
            if self.monotonic() >= deadline or self.clock() >= started + timedelta(seconds=RETENTION_SECONDS):
                raise OutlookUnavailable("outlook acquisition exceeded retention")
            completed = datetime.fromisoformat(candidate.detail["receipts"][COLLECTION]["completed_at"])
            entry = OutlookSnapshot(hashlib.sha256(body).hexdigest(), body, receipt, completed,
                                    started + timedelta(seconds=RETENTION_SECONDS), "refresh" if refresh else "miss")
            with self._lock:
                self._entry, self._deadline = entry, deadline
                future.set_result(entry)
                self._flight = None
            return entry
        except Exception as cause:
            error = OutlookUnavailable("native outlook snapshot unavailable")
            with self._lock:
                if not self._valid():
                    self._entry = None
                future.set_exception(error)
                self._flight = None
            raise error from cause

    def retained(self, revision: str) -> OutlookSnapshot:
        with self._lock:
            if not self._valid():
                self._entry = None
            if self._entry is None or self._entry.revision != revision:
                raise OutlookUnavailable("exact outlook revision is not retained")
            return replace(self._entry, cache_status="hit")

    def report(self, *, revision: str, feature_id: str, publication_time: datetime) -> dict:
        """Preserve full native feature; no interval filtering or point/scoring claim."""
        if publication_time.tzinfo is None:
            raise ValueError("publication time must be timezone-aware")
        snapshot = self.retained(revision)
        for feature in json.loads(snapshot.body)["features"]:
            if str(feature["id"]) != feature_id:
                continue
            raw = feature["properties"].get("publication_datetime")
            try:
                native = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            except ValueError:
                raise OutlookUnavailable("native publication time unavailable") from None
            if native.tzinfo is None or native != publication_time:
                raise OutlookUnavailable("exact native publication time does not match")
            return feature
        raise OutlookUnavailable("exact native report is not retained")
