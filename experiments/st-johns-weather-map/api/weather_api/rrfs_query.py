"""Finite selected RRFS parallel temperature acquisition; not publicly routed."""
import copy
from concurrent.futures import Future
from datetime import UTC, datetime
from hashlib import sha256
import json
import re
import threading
import time

import httpx

from .rrfs_native import MAX_INDEX_BYTES, RRFSRequest, bounded_decode, temperature_range


class RRFSQueryService:
    """One cached point, one in-flight request and fixed five-minute validity."""
    def __init__(self, workspace, *, transport=None, clock=time.monotonic, decoder=bounded_decode):
        self.workspace, self.transport, self.clock, self.decoder = workspace, transport, clock, decoder
        self.lock = threading.Lock()
        self.cached = self.inflight = self.failure = None

    def _load(self, request):
        receipts = []
        deadline = time.monotonic() + 30
        with httpx.Client(transport=self.transport, trust_env=False, follow_redirects=False, timeout=15) as client:
            def read(url, maximum, span=None):
                headers = {"Accept-Encoding": "identity"}
                if span is not None:
                    headers["Range"] = span.header
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RuntimeError("RRFS acquisition deadline exceeded")
                with client.stream("GET", url, headers=headers, timeout=min(15, remaining)) as response:
                    if response.status_code != (206 if span else 200):
                        raise RuntimeError("RRFS selected data request failed")
                    if response.headers.get("content-encoding", "identity") != "identity":
                        raise RuntimeError("RRFS encoded range response refused")
                    if span is not None:
                        match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", response.headers.get("content-range", ""))
                        if not match or (int(match[1]), int(match[2])) != span.as_tuple() or int(match[3]) <= span.end:
                            raise RuntimeError("RRFS server did not honor exact bounded range")
                    declared = response.headers.get("content-length")
                    if declared is not None and (not declared.isdecimal() or int(declared) > maximum):
                        raise RuntimeError("RRFS declared response exceeds receive bound")
                    payload = bytearray()
                    for chunk in response.iter_raw():
                        if time.monotonic() > deadline:
                            raise RuntimeError("RRFS acquisition deadline exceeded")
                        if len(payload) + len(chunk) > maximum:
                            raise RuntimeError("RRFS response exceeds receive bound")
                        payload.extend(chunk)
                    if not payload or (span is not None and len(payload) != span.length):
                        raise RuntimeError("RRFS response length differs from selection")
                    body = bytes(payload)
                    receipts.append({"url": url, "http_status": response.status_code,
                        "range": None if span is None else span.header,
                        "byte_size": len(body), "sha256": sha256(body).hexdigest(),
                        "completed_at": datetime.now(UTC).isoformat()})
                    return body
            index = read(request.url + ".idx", MAX_INDEX_BYTES)
            span = temperature_range(index, request)
            payload = read(request.url, span.length, span)
        result = self.decoder(payload, request, self.workspace)
        result["transport_receipts"] = receipts
        if len(json.dumps(result).encode()) > 8192:
            raise RuntimeError("RRFS normalized point exceeds cache bound")
        return result

    def query(self, request: RRFSRequest, *, refresh=False):
        request.validate()
        with self.lock:
            now = self.clock()
            if self.cached is not None:
                deadline, key, result = self.cached
                if not refresh and key == request and now < deadline:
                    return copy.deepcopy(result)
            if self.inflight is not None:
                key, future = self.inflight
                if key != request:
                    raise RuntimeError("RRFS acquisition capacity occupied")
                owner = False
            else:
                if self.failure is not None and self.failure[0] > now and self.failure[1] == request:
                    raise RuntimeError("RRFS selected acquisition failed; bounded retry delay active")
                future = Future()
                self.inflight = (request, future)
                owner = True
        if not owner:
            return copy.deepcopy(future.result())
        try:
            result = self._load(request)
            with self.lock:
                self.cached = (self.clock() + 300, request, copy.deepcopy(result))
                self.failure = None
            future.set_result(result)
            return copy.deepcopy(result)
        except BaseException as error:
            with self.lock:
                self.failure = (self.clock() + 30, request)
            future.set_exception(error)
            raise
        finally:
            with self.lock:
                self.inflight = None
