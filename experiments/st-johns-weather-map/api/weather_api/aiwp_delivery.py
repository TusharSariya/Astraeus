"""Experimental anonymous AIWP native byte transport; no field admission.

The caller supplies a publisher object and ETag from bounded discovery. Each
reader owns a finite, revision-bound cache. No credentials or inference occur.
"""
from dataclasses import dataclass
from hashlib import sha256
from io import RawIOBase
from math import isfinite
import re
from time import monotonic

import httpx


class RangeRefused(OSError):
    """Identity, server response, or acquisition budget was not satisfied."""


@dataclass(frozen=True)
class NativeObject:
    key: str
    size: int
    etag: str

    def __post_init__(self):
        match = re.fullmatch(
            r"AURO_v100_(GFS|IFS)/(\d{4})/(\d{4})/"
            r"AURO_v100_\1_(\d{10})_f000_f240_06\.nc", self.key
        )
        if (not match or match[2] + match[3] != match[4][:8]
                or self.size <= 0 or not re.fullmatch(r'"[a-f0-9]+(?:-\d+)?"', self.etag)):
            raise ValueError("Expected pinned publisher AURO_v100 GFS/IFS object")

    @property
    def url(self):
        return "https://noaa-oar-mlwp-data.s3.amazonaws.com/" + self.key

    @property
    def identity(self):
        return sha256(f"{self.url}\n{self.size}\n{self.etag}".encode()).hexdigest()


class RangeReader(RawIOBase):
    """Seekable native file with finite byte, request, time and memory budgets.

    No unbounded read is allowed, including decoder attempts to read the whole
    object. Block caching is private to this exact object revision. Production
    network uses an anonymous httpx client with redirects/retries disabled.
    This experiment is synchronous and is not safe for concurrent callers.
    """

    def __init__(self, source: NativeObject, *, max_bytes=4 * 1024 * 1024,
                 max_requests=12, timeout_seconds=90.0, block_size=262144,
                 transport=None, clock=monotonic):
        super().__init__()
        if (any(type(value) is not int or value <= 0
                for value in (max_bytes, max_requests, block_size))
                or not isfinite(timeout_seconds) or timeout_seconds <= 0):
            raise ValueError("Budgets must be positive finite values; byte/count limits are integers")
        self.source = source
        self.max_bytes, self.max_requests = max_bytes, max_requests
        self.block_size = block_size
        self.clock, self.deadline = clock, clock() + timeout_seconds
        self.requests = self.received_bytes = self.reserved_bytes = 0
        self.receipts = []
        self._position, self._cache = 0, {}
        self._client = httpx.Client(transport=transport or httpx.HTTPTransport(retries=0),
                                    follow_redirects=False, trust_env=False, auth=None)

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self._position

    def seek(self, offset, whence=0):
        self._checkClosed()
        if whence not in (0, 1, 2):
            raise ValueError("Invalid whence")
        target = offset + (0 if whence == 0 else self._position if whence == 1 else self.source.size)
        if target < 0:
            raise ValueError("Negative seek")
        self._position = target
        return target

    def _block(self, start):
        if start in self._cache:
            return self._cache[start]
        end = min(start + self.block_size, self.source.size) - 1
        count = end - start + 1
        remaining = self.deadline - self.clock()
        if (remaining <= 0 or self.requests >= self.max_requests
                or self.reserved_bytes + count > self.max_bytes):
            raise RangeRefused("Native range acquisition budget exhausted")
        # Reserve attempted bytes too: failed responses cannot reset the cap.
        self.requests += 1
        self.reserved_bytes += count
        headers = {"Range": f"bytes={start}-{end}", "If-Match": self.source.etag,
                   "Accept-Encoding": "identity"}
        self._client.cookies.clear()
        with self._client.stream("GET", self.source.url, headers=headers,
                                 timeout=min(remaining, 10.0)) as response:
            if (response.status_code != 206
                    or response.headers.get("content-range") != f"bytes {start}-{end}/{self.source.size}"
                    or response.headers.get("etag") != self.source.etag
                    or response.headers.get("content-encoding", "identity") != "identity"
                    or response.headers.get("content-length") != str(count)):
                raise RangeRefused("Server refused exact pinned byte range")
            body = bytearray()
            for chunk in response.iter_raw():
                self.received_bytes += len(chunk)
                if len(body) + len(chunk) > count or self.clock() >= self.deadline:
                    raise RangeRefused("Native range response exceeded bounds")
                body.extend(chunk)
            if len(body) != count:
                raise RangeRefused("Truncated native range response")
        result = bytes(body)
        self._cache[start] = result
        self.receipts.append({"object_identity": self.source.identity,
                              "range": headers["Range"], "bytes": count,
                              "sha256": sha256(result).hexdigest()})
        return result

    def read(self, size=-1):
        self._checkClosed()
        if size is None or size < 0:
            raise RangeRefused("Unbounded native read refused")
        size = min(size, max(0, self.source.size - self._position))
        if size > self.max_bytes:
            raise RangeRefused("Native read exceeds memory budget")
        chunks = []
        position, left = self._position, size
        while left:
            start = position // self.block_size * self.block_size
            block = self._block(start)
            offset = position - start
            chunk = block[offset:offset + left]
            chunks.append(chunk)
            position += len(chunk)
            left -= len(chunk)
        self._position = position
        return b"".join(chunks)

    def readinto(self, buffer):
        data = self.read(len(buffer))
        buffer[:len(data)] = data
        return len(data)

    def close(self):
        if hasattr(self, "_client"):
            self._client.close()
        if hasattr(self, "_cache"):
            self._cache.clear()
        super().close()
