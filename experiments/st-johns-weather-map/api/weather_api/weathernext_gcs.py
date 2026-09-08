"""Opt-in authenticated transport for the isolated WeatherNext native reader.

No ADC discovery, registration, billing headers, retries, or raw-member access.
Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-006 (experiment).
"""
from __future__ import annotations

import json
import re
import subprocess
import time
from typing import Callable
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from weather_api.weathernext_native import BUCKET, ObjectIdentity

METADATA_CAP = 64 * 1024
PAYLOAD_CAP = 512 * 1024 * 1024
OBJECT = re.compile(
    r"weathernext_3_0_0_statistics/zarr/2026_to_present/"
    r"[0-9]{8}_[0-9]{2}hr_01_preds/predictions\.zarr/"
    r"(?:zarr\.json|[a-z][a-z0-9_]*/c(?:/[0-9]+)*)\Z"
)


class GCSUnavailable(RuntimeError):
    """Safe error category; never includes token, URL query, or provider body."""
    def __init__(self, category: str, http_status: int | None = None):
        super().__init__(f"WeatherNext GCS {category}")
        self.category, self.http_status = category, http_status


class GcloudProfileToken:
    """Use an explicitly selected existing gcloud profile at invocation time.

    Token output is captured in subprocess memory only. No login or ADC changes.
    Nothing is cached or logged. The caller must not print this callable's result.
    """
    def __init__(self, profile: str = "astraeus"):
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,62}", profile):
            raise ValueError("invalid gcloud profile name")
        self.profile = profile

    def __call__(self, *, timeout: float) -> str:
        try:
            result = subprocess.run(
                ["gcloud", "--configuration", self.profile, "--quiet", "auth", "print-access-token"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=min(timeout, 30), check=False,
            )
            if result.returncode or not 0 < len(result.stdout) <= 16384:
                raise ValueError("runtime authentication")
            token = result.stdout.decode("ascii").strip()
            if not token or any(c.isspace() for c in token):
                raise ValueError("invalid runtime token")
            return token
        except Exception:
            raise GCSUnavailable("authentication unavailable") from None


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class WeatherNextGCSTransport:
    """Generation-pinned JSON API with bounded reception and no implicit auth.

    Construct explicitly with GcloudProfileToken() for the owner-authorized
    profile, or inject a runtime token provider. Tests inject both token and HTTP
    opener. A bounded process must enclose live native decoding separately.
    """
    def __init__(self, *, token_provider: Callable[..., str], opener=None,
                 clock: Callable[[], float] = time.monotonic):
        self._token_provider = token_provider
        self._opener = opener if opener is not None else build_opener(_NoRedirect)
        self._clock = clock

    @staticmethod
    def _validate(bucket: str, name: str):
        if bucket != BUCKET or not OBJECT.fullmatch(name):
            raise GCSUnavailable("unsupported object identity")

    def _get(self, name: str, params: dict, *, cap: int, timeout: float,
             expected: ObjectIdentity | None = None) -> bytes:
        if type(cap) is not int or not 0 < cap <= PAYLOAD_CAP or not 0 < timeout <= 300:
            raise GCSUnavailable("invalid request bounds")
        deadline = self._clock() + timeout
        def remaining():
            value = deadline - self._clock()
            if value <= 0:
                raise GCSUnavailable("deadline exceeded")
            return value
        try:
            token = self._token_provider(timeout=remaining())
            if not isinstance(token, str) or not 0 < len(token) <= 16384 or any(c.isspace() for c in token):
                raise GCSUnavailable("authentication unavailable")
            url = f"https://storage.googleapis.com/storage/v1/b/{BUCKET}/o/{quote(name, safe='')}?{urlencode(params)}"
            request = Request(url, headers={"Authorization": "Bearer " + token, "Accept-Encoding": "identity"})
            try:
                response = self._opener.open(request, timeout=remaining())
            except HTTPError as error:
                response = error
            with response:
                status = response.status
                if status != 200:
                    category = {401: "authentication refused", 403: "access denied", 404: "object absent",
                                412: "object changed", 429: "rate limited"}.get(status, "HTTP failure")
                    raise GCSUnavailable(category, status)
                encoding = response.headers.get("Content-Encoding", "identity")
                if encoding != "identity":
                    raise GCSUnavailable("unexpected content encoding")
                length = response.headers.get("Content-Length")
                if length is not None and (not length.isdecimal() or not 0 < int(length) <= cap):
                    raise GCSUnavailable("response byte bound exceeded")
                if expected is not None:
                    if (response.headers.get("x-goog-generation") != expected.generation
                            or response.headers.get("ETag", "").strip('"') != expected.etag.strip('"')
                            or (length is not None and int(length) != expected.size)):
                        raise GCSUnavailable("object identity mismatch")
                body = bytearray()
                while len(body) < cap:
                    remaining()
                    part = response.read(min(65536, cap - len(body)))
                    remaining()
                    if not isinstance(part, bytes) or len(part) > cap - len(body):
                        raise GCSUnavailable("response byte bound exceeded")
                    if not part:
                        break
                    body.extend(part)
                if (length is not None and len(body) != int(length)) or (expected is not None and len(body) != expected.size):
                    raise GCSUnavailable("truncated object")
                if length is None and len(body) == cap:
                    # No extra byte is received just to test for overflow.
                    raise GCSUnavailable("unconfirmed response boundary")
                return bytes(body)
        except GCSUnavailable:
            raise
        except Exception:
            raise GCSUnavailable("bounded request failed") from None

    def describe(self, bucket: str, name: str, *, timeout: float) -> ObjectIdentity:
        self._validate(bucket, name)
        body = self._get(name, {"fields": "bucket,name,generation,etag,size"}, cap=METADATA_CAP, timeout=timeout)
        try:
            item = json.loads(body)
            size = item["size"]
            if not isinstance(size, str) or not size.isdecimal():
                raise ValueError("size")
            identity = ObjectIdentity(item["bucket"], item["name"], item["generation"], item["etag"], int(size))
            if (identity.bucket != bucket or identity.name != name or not isinstance(identity.generation, str)
                    or not identity.generation.isdecimal() or not isinstance(identity.etag, str) or not identity.etag
                    or not 0 < identity.size <= PAYLOAD_CAP):
                raise ValueError("identity")
            return identity
        except Exception:
            raise GCSUnavailable("invalid object metadata") from None

    def read(self, identity: ObjectIdentity, *, max_bytes: int, timeout: float) -> bytes:
        self._validate(identity.bucket, identity.name)
        if (not isinstance(identity.generation, str) or not identity.generation.isdecimal()
                or not identity.etag or type(identity.size) is not int or identity.size != max_bytes):
            raise GCSUnavailable("invalid pinned identity")
        return self._get(identity.name, {"alt": "media", "generation": identity.generation},
                         cap=max_bytes, timeout=timeout, expected=identity)
