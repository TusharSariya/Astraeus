"""Unregistered RAP awip32 selected-frame experiment; no aerosol substitution."""
from collections import OrderedDict
from concurrent.futures import Future
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import copy
import json
import math
import re
from pathlib import Path
import sys
import tempfile
import threading
import time

from ingest.grib import GribError, parse_idx
from ingest.isolation import ProcessAllocationLimits, run_bounded_process

BASE = "https://noaa-rap-pds.s3.amazonaws.com"
FIELDS = {"visibility": ("VIS", "surface", "vis", "surface", "m"),
          "total_cloud_geometric": ("TCDC", "entire atmosphere", "tcc", "atmosphere", "%")}
BOUNDS = {"south": 45., "north": 50.5, "west": -58., "east": -46.}
INDEX_BYTES = 512 * 1024
RECORD_BYTES = 2 * 1024**2
OUTPUT_BYTES = 2 * 1024**2
LIMITS = ProcessAllocationLimits(1024**3, OUTPUT_BYTES, 16384, 4096, 65536)


class RAPUnavailable(ValueError):
    pass


def selected_records(text, lead):
    # RAP indices contain multi-field wind messages numbered 7.1/7.2 at
    # one offset. Collapse only unselected shared offsets before using the
    # existing byte-range parser; selected multi-field messages fail closed.
    normalized, previous = [], None
    wanted = {(item[0], item[1]) for item in FIELDS.values()}
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split(":")
        if len(parts) < 6 or not re.fullmatch(r"\d+(?:\.\d+)?", parts[0]) or not parts[1].isdigit():
            raise RAPUnavailable("RAP malformed native index")
        offset = int(parts[1])
        if previous is not None and offset < previous:
            raise RAPUnavailable("RAP unordered native offsets")
        if "." in parts[0] and (parts[3], parts[4]) in wanted:
            raise RAPUnavailable("RAP selected field is a multi-field message")
        if offset == previous:
            continue
        previous = offset
        parts[0] = str(len(normalized)+1)
        normalized.append(":".join(parts))
    try:
        records = parse_idx("\n".join(normalized))
    except GribError:
        raise RAPUnavailable("RAP malformed native index") from None
    chosen = {}
    for field, (parameter, level, *_rest) in FIELDS.items():
        found = [r for r in records if (r.param, r.level) == (parameter, level)
                 and r.forecast == ("anl" if lead == 0 else f"{lead} hour fcst")]
        if len(found) != 1:
            raise RAPUnavailable("RAP exact instantaneous field is missing or ambiguous")
        row = found[0]
        if row.end is None or not 0 < row.end - row.offset + 1 <= RECORD_BYTES:
            raise RAPUnavailable("RAP selected record exceeds finite range bound")
        chosen[field] = (row.offset, row.end)
    return chosen


@dataclass(frozen=True)
class RAPEntry:
    run_time: datetime
    valid_time: datetime
    data: dict
    receipts: tuple[dict, ...]


class RAPQueryCoordinator:
    """At most two exact indices and two ranges; four fixed-expiry cropped entries."""
    def __init__(self, *, now=lambda: datetime.now(UTC), clock=time.monotonic,
                 transport_factory=None, decoder=None, workspace=Path("/tmp")):
        # Reuse bounded HTTPS mechanics only; RAP owns all scientific identity.
        from .ecmwf_query import ECMWFHTTP
        self.now, self.clock = now, clock
        self.transport_factory = transport_factory or ECMWFHTTP
        self.decoder = decoder or self._decode
        self.workspace = Path(workspace)
        self.lock = threading.RLock()
        self.entries = OrderedDict()
        self.failure = None
        self.pending_lock = threading.Lock()
        self.pending = None

    def query(self, selected, *, refresh=False):
        selection = (selected, refresh)
        while True:
            with self.pending_lock:
                pending = self.pending
                if pending is None:
                    future = Future()
                    self.pending = (selection, future)
                    break
            if pending[0] == selection:
                return copy.deepcopy(pending[1].result())
            try:
                pending[1].result()
            except Exception:
                pass
        try:
            entry = self._query(selected, refresh=refresh)
            future.set_result(entry)
            return copy.deepcopy(entry)
        except BaseException as error:
            future.set_exception(error)
            raise
        finally:
            with self.pending_lock:
                self.pending = None

    def _query(self, selected, *, refresh=False):
        if selected.tzinfo is None or selected.utcoffset() != timedelta(0):
            raise RAPUnavailable("RAP selected time must be aware UTC")
        if selected.minute or selected.second or selected.microsecond:
            raise RAPUnavailable("RAP requires an exact native hour")
        now = self.now().astimezone(UTC)
        if not now-timedelta(hours=24) <= selected <= now+timedelta(hours=51):
            raise RAPUnavailable("RAP selected time is outside the bounded horizon")
        with self.lock:
            cached = self.entries.get(selected)
            if cached and self.clock() < cached[0] and not refresh:
                return copy.deepcopy(cached[1])
            if self.failure and self.failure[0] == selected and self.clock() < self.failure[1]:
                raise RAPUnavailable("RAP selected frame is in failure backoff")
            try:
                result = self._acquire(selected, now)
                self.entries[selected] = (self.clock()+600, result)
                self.entries.move_to_end(selected)
                while len(self.entries) > 4:
                    self.entries.popitem(last=False)
                self.failure = None
                return copy.deepcopy(result)
            except Exception:
                self.failure = (selected, self.clock()+60)
                raise RAPUnavailable("RAP exact selected frame unavailable") from None

    def _acquire(self, selected, now):
        http = self.transport_factory()
        run = min(selected, now).replace(minute=0, second=0, microsecond=0)
        try:
            for offset in range(2):
                candidate = run-timedelta(hours=offset)
                lead = int((selected-candidate).total_seconds()/3600)
                if not 0 <= lead <= (51 if candidate.hour in (3, 9, 15, 21) else 21):
                    continue
                url = f"{BASE}/rap.{candidate:%Y%m%d}/rap.t{candidate:%H}z.awip32f{lead:02d}.grib2"
                try:
                    text = http.read(url+".idx", limit=INDEX_BYTES).decode("utf-8")
                    records = selected_records(text, lead)
                except Exception:
                    continue
                with tempfile.TemporaryDirectory(prefix="rap-native-", dir=self.workspace) as directory:
                    for field, byte_range in records.items():
                        body = http.read(url, limit=RECORD_BYTES, byte_range=byte_range)
                        (Path(directory)/f"{field}.grib2").write_bytes(body)
                    request = dict(directory=directory, run_time=candidate.isoformat(),
                                   valid_time=selected.isoformat(), lead=lead)
                    data = self.decoder(request)
                    if (data.get("source_id") != "noaa-rap" or data.get("product") != "awip32"
                            or data.get("run_time") != candidate.isoformat()
                            or data.get("valid_time") != selected.isoformat()
                            or set(data.get("fields", {})) != set(FIELDS)
                            or len(json.dumps(data, allow_nan=False).encode()) > OUTPUT_BYTES):
                        raise RAPUnavailable("RAP decoder returned incompatible identity")
                    return RAPEntry(candidate, selected, data, tuple(copy.deepcopy(http.receipts)))
            raise RAPUnavailable("RAP has no published exact frame in two-cycle discovery")
        finally:
            client = getattr(http, "client", None)
            if client is not None:
                client.close()

    def _decode(self, request):
        destination = Path(request["directory"])/"result.json"
        run_bounded_process(command=[sys.executable, "-m", "weather_api.rap_query_worker", "{output}"],
            stdin=json.dumps(request).encode(), destination=destination, limits=LIMITS, timeout_seconds=60)
        return json.loads(destination.read_bytes())

    def point_native(self, latitude, longitude, selected, *, refresh=False):
        """Return native samples for root's wire adapter, using the shared cell picker."""
        from .store import _nearest_curvilinear_cell, MAX_GRID_DISTANCE_DEGREES
        import numpy as np
        import xarray as xr
        if (not math.isfinite(latitude) or not math.isfinite(longitude)
                or not BOUNDS["south"] <= latitude <= BOUNDS["north"]
                or not BOUNDS["west"] <= longitude <= BOUNDS["east"]):
            raise RAPUnavailable("RAP requested location is outside the evidence box")
        entry = self.query(selected, refresh=refresh)
        data = entry.data
        dataset = xr.Dataset(coords={name: (("y", "x"), np.asarray(data[name], dtype=float))
                                     for name in ("latitude", "longitude")})
        cell = _nearest_curvilinear_cell(dataset, "latitude", "longitude", latitude, longitude)
        if cell is None or cell[3] > MAX_GRID_DISTANCE_DEGREES:
            raise RAPUnavailable("RAP has no applicable native cell")
        index, lat, lon, distance = cell
        return dict(source_id="noaa-rap", product="awip32", run_time=entry.run_time,
            valid_time=entry.valid_time, retrieved_at=entry.receipts[-1]["completed_at"],
            sampled_latitude=lat, sampled_longitude=lon, sample_distance_km=distance*111.195,
            sample_method="curvilinear_nearest_cell", operational=False, quality="unknown",
            fields={name: dict(value=values[index["y"]][index["x"]], native_units=FIELDS[name][-1])
                    for name, values in data["fields"].items()}, receipts=entry.receipts)
