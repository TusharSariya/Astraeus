"""Isolated FourCastNet NIM 1.0.0 SFNO delivery; no scientific admission.

Caller owns deployment, complete initial conditions and native channel semantics.
Returned archives are generated-here, unmapped artifacts, never cloud evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import math
import os
from pathlib import Path
import re
import struct
import tarfile
import tempfile
import time
from typing import BinaryIO
from urllib.parse import urlsplit

import httpx
import numpy as np

INPUT_SHAPE = (1, 1, 73, 721, 1440)
NATIVE_BYTES = math.prod(INPUT_SHAPE) * 4
MAX_NPY_BYTES = NATIVE_BYTES + 65536
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_TIME = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")


class DeliveryRefused(ValueError):
    """No complete native artifact was delivered; no fallback is permitted."""


@dataclass(frozen=True)
class Initialization:
    source: str
    run: str
    input_time: str
    transformations: tuple[str, ...]
    ordered_channel_contract_sha256: str


@dataclass(frozen=True)
class Deployment:
    endpoint: str
    container_sha256: str
    checkpoint_sha256: str
    runtime: str
    device: str
    profile: str = "SFNO ERA5 73ch"
    version: str = "1.0.0"


@dataclass(frozen=True)
class Limits:
    # Local policy deliberately narrower than the upstream maximum of 120 steps.
    max_steps: int = 4
    max_response_bytes: int = 1_600_000_000
    timeout_seconds: float = 180.0


@dataclass(frozen=True)
class NativeMember:
    name: str
    lead_hours: int
    batch_index: int
    valid_time: str
    size_bytes: int
    sha256: str
    array_shape: tuple[int, ...]


@dataclass(frozen=True)
class Delivery:
    archive: Path
    archive_sha256: str
    input_sha256: str
    initialization: Initialization
    deployment: Deployment
    members: tuple[NativeMember, ...]
    retrieved_at: str
    provenance_kind: str = "generated-here"
    scientific_status: str = "native-channels-unmapped"
    critical_cloud_eligible: bool = False
    centre_votes: int = 0
    seed: int = 0


def _text(value: str) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _time(value: str) -> datetime:
    if not isinstance(value, str) or not _TIME.fullmatch(value):
        raise DeliveryRefused("input_time must be an explicit UTC second timestamp")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DeliveryRefused("input_time is invalid") from exc


def _configuration(deployment: Deployment, initialization: Initialization,
                   steps: int, limits: Limits) -> datetime:
    if deployment.version != "1.0.0" or deployment.profile != "SFNO ERA5 73ch":
        raise DeliveryRefused("only the pinned NIM 1.0.0 SFNO 73-channel profile is supported")
    try:
        url = urlsplit(deployment.endpoint)
        port = url.port
    except ValueError as exc:
        raise DeliveryRefused("invalid deployed endpoint") from exc
    if (not url.hostname or url.username or url.password or url.query or url.fragment
            or url.path not in ("", "/") or url.scheme not in ("http", "https")
            or (url.scheme == "http" and url.hostname not in ("localhost", "127.0.0.1", "::1"))
            or port == 0):
        raise DeliveryRefused("supply a deployed service origin; HTTP is loopback-only")
    if url.hostname in ("climate.api.nvidia.com", "integrate.api.nvidia.com"):
        raise DeliveryRefused("hosted historical-example service is not this native endpoint")
    for digest in (deployment.container_sha256, deployment.checkpoint_sha256,
                   initialization.ordered_channel_contract_sha256):
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            raise DeliveryRefused("explicit container, checkpoint and ordered-channel SHA256 required")
    if not all(_text(v) for v in (deployment.runtime, deployment.device,
                                  initialization.source, initialization.run)):
        raise DeliveryRefused("deployment and initializer provenance must be explicit")
    if (not isinstance(initialization.transformations, tuple)
            or not initialization.transformations
            or not all(_text(v) for v in initialization.transformations)):
        raise DeliveryRefused("record initialization transformations, including identity if none")
    if (type(limits.max_steps) is not int or not 1 <= limits.max_steps <= 120
            or type(limits.max_response_bytes) is not int or limits.max_response_bytes < 10240
            or not math.isfinite(limits.timeout_seconds) or limits.timeout_seconds <= 0):
        raise DeliveryRefused("invalid execution limits")
    if type(steps) is not int or not 1 <= steps <= limits.max_steps:
        raise DeliveryRefused("simulation_length exceeds the explicit local step budget")
    if limits.max_response_bytes < (steps + 1) * (NATIVE_BYTES + 512):
        raise DeliveryRefused("response budget cannot hold the requested native trajectory")
    origin = _time(initialization.input_time)
    try:
        origin + timedelta(hours=steps * 6)
    except OverflowError as exc:
        raise DeliveryRefused("forecast valid time exceeds supported calendar") from exc
    return origin


def _npy_header(stream: BinaryIO) -> tuple[tuple[int, ...], int]:
    try:
        version = np.lib.format.read_magic(stream)
        length_position = stream.tell()
        length_width = {(1, 0): 2, (2, 0): 4}.get(version)
        if length_width is None:
            raise DeliveryRefused("unsupported NumPy file version")
        encoded_length = stream.read(length_width)
        if len(encoded_length) != length_width:
            raise DeliveryRefused("truncated NumPy header length")
        header_length = struct.unpack("<H" if length_width == 2 else "<I", encoded_length)[0]
        if header_length > 65536:
            raise DeliveryRefused("NumPy header exceeds the allocation budget")
        stream.seek(length_position)
        if version == (1, 0):
            shape, fortran, dtype = np.lib.format.read_array_header_1_0(stream, max_header_size=65536)
        elif version == (2, 0):
            shape, fortran, dtype = np.lib.format.read_array_header_2_0(stream, max_header_size=65536)
        else:
            raise DeliveryRefused("unsupported NumPy file version")
    except DeliveryRefused:
        raise
    except (ValueError, EOFError, OSError) as exc:
        raise DeliveryRefused("invalid NumPy header") from exc
    if dtype != np.dtype("float32") or fortran or not shape or any(type(d) is not int or d <= 0 for d in shape):
        raise DeliveryRefused("native NumPy must be C-order FP32 without object data")
    return shape, stream.tell()


def _copy_input(path: Path, destination: BinaryIO, deadline: float) -> str:
    # Snapshot the validated bytes: the caller's original cannot change mid-upload.
    digest = hashlib.sha256()
    with path.open("rb") as source:
        shape, offset = _npy_header(source)
        if shape != INPUT_SHAPE or os.fstat(source.fileno()).st_size != offset + NATIVE_BYTES:
            raise DeliveryRefused("initializer must contain the complete native (1,1,73,721,1440) tensor")
        source.seek(0)
        header = source.read(offset)
        destination.write(header)
        digest.update(header)
        remaining = NATIVE_BYTES
        while remaining:
            if time.monotonic() > deadline:
                raise DeliveryRefused("initializer validation deadline exceeded")
            chunk = source.read(min(1024 * 1024, remaining))
            if not chunk or len(chunk) % 4 or not np.isfinite(np.frombuffer(chunk, dtype=np.float32)).all():
                raise DeliveryRefused("initializer is truncated or contains non-finite values")
            destination.write(chunk)
            digest.update(chunk)
            remaining -= len(chunk)
        if source.read(1):
            raise DeliveryRefused("initializer changed size during validation")
    destination.seek(0)
    return digest.hexdigest()


def inspect_archive(path: Path, *, input_time: str, steps: int,
                    deadline: float) -> tuple[NativeMember, ...]:
    """Inspect without extracting; validate identities and bounded NPY envelopes.

    The shape is recorded, not mapped to channels or asserted as scientific proof.
    """
    if type(steps) is not int or not 1 <= steps <= 120:
        raise DeliveryRefused("invalid archive step count")
    origin = _time(input_time)
    expected = {f"{lead:03d}_000.npy": lead for lead in range(0, steps * 6 + 1, 6)}
    members: dict[str, NativeMember] = {}
    try:
        # Parse fixed TAR headers ourselves so PAX/long-name headers cannot cause
        # tarfile to allocate an attacker-controlled metadata body before limits.
        with path.open("rb") as archive:
            while True:
                if time.monotonic() > deadline:
                    raise DeliveryRefused("archive inspection deadline exceeded")
                header = archive.read(512)
                if len(header) != 512:
                    raise DeliveryRefused("truncated TAR header")
                if not any(header):
                    terminator = archive.read(512)
                    if len(terminator) != 512 or any(terminator):
                        raise DeliveryRefused("archive lacks the complete TAR terminator")
                    while chunk := archive.read(1024 * 1024):
                        if any(chunk) or time.monotonic() > deadline:
                            raise DeliveryRefused("archive has trailing content or exceeds deadline")
                    break
                member = tarfile.TarInfo.frombuf(header, encoding="utf-8", errors="strict")
                if (member.name not in expected or member.name in members
                        or member.type not in (tarfile.REGTYPE, tarfile.AREGTYPE)
                        or not 0 < member.size <= MAX_NPY_BYTES):
                    raise DeliveryRefused("unexpected, duplicate, unsafe or oversized TAR member")
                body_start = archive.tell()
                shape, body_header_end = _npy_header(archive)
                header_size = body_header_end - body_start
                if math.prod(shape) != math.prod(INPUT_SHAPE) or member.size != header_size + NATIVE_BYTES:
                    raise DeliveryRefused("output NumPy payload is incomplete or has unexpected cardinality")
                archive.seek(body_start)
                digest = hashlib.sha256()
                remaining = member.size
                while remaining:
                    if time.monotonic() > deadline:
                        raise DeliveryRefused("archive inspection deadline exceeded")
                    chunk = archive.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise DeliveryRefused("truncated archive member")
                    digest.update(chunk)
                    remaining -= len(chunk)
                padding = (-member.size) % 512
                pad = archive.read(padding)
                if len(pad) != padding or any(pad):
                    raise DeliveryRefused("invalid TAR member padding")
                lead = expected[member.name]
                members[member.name] = NativeMember(member.name, lead, 0,
                    (origin + timedelta(hours=lead)).isoformat().replace("+00:00", "Z"),
                    member.size, digest.hexdigest(), shape)
    except (tarfile.TarError, OSError, EOFError, UnicodeError) as exc:
        raise DeliveryRefused("invalid or truncated native TAR") from exc
    if members.keys() != expected.keys():
        raise DeliveryRefused("native trajectory is incomplete")
    return tuple(members[name] for name in expected)


class _DeadlineReader:
    """Check elapsed wall time on every multipart upload read."""

    def __init__(self, stream: BinaryIO, deadline: float):
        self.stream = stream
        self.deadline = deadline

    def read(self, size: int = -1) -> bytes:
        if time.monotonic() > self.deadline:
            raise DeliveryRefused("native upload deadline exceeded")
        value = self.stream.read(size)
        if time.monotonic() > self.deadline:
            raise DeliveryRefused("native upload deadline exceeded")
        return value

    def seek(self, offset: int, whence: int = 0) -> int:
        return self.stream.seek(offset, whence)

    def tell(self) -> int:
        return self.stream.tell()

    def fileno(self) -> int:
        return self.stream.fileno()


def infer(*, input_array: Path, initialization: Initialization, deployment: Deployment,
          simulation_length: int, output_archive: Path, limits: Limits = Limits(),
          transport: httpx.BaseTransport | None = None) -> Delivery:
    """Run one explicitly configured deployment, with no retry or substitution.

    Disk budget: one native initializer snapshot plus max_response_bytes. HTTP
    timeouts bound each I/O operation; the wall deadline is checked between chunks.
    Container/checkpoint identity is caller-attested, not remotely discovered.
    """
    _configuration(deployment, initialization, simulation_length, limits)
    if output_archive.exists():
        raise DeliveryRefused("output archive already exists")
    deadline = time.monotonic() + limits.timeout_seconds
    try:
        with tempfile.TemporaryDirectory(prefix="fcn-delivery-", dir=output_archive.parent) as temporary:
            native = Path(temporary) / "response.tar"
            with tempfile.TemporaryFile(dir=temporary) as snapshot:
                input_digest = _copy_input(input_array, snapshot, deadline)
                remaining_seconds = deadline - time.monotonic()
                if remaining_seconds <= 0:
                    raise DeliveryRefused("initializer exhausted the execution deadline")
                with httpx.Client(transport=transport, timeout=remaining_seconds,
                                  follow_redirects=False, trust_env=False) as client:
                    with client.stream("POST", deployment.endpoint.rstrip("/") + "/v1/infer",
                            files={"input_array": ("input.npy", _DeadlineReader(snapshot, deadline), "application/octet-stream")},
                            data={"input_time": initialization.input_time,
                                  "simulation_length": str(simulation_length), "seed": "0"},
                            headers={"accept": "application/x-tar", "accept-encoding": "identity"}) as response:
                        if response.status_code != 200:
                            raise DeliveryRefused(f"native inference HTTP {response.status_code}")
                        if (response.headers.get("content-type", "").split(";")[0].strip() != "application/x-tar"
                                or response.headers.get("content-encoding", "identity") != "identity"):
                            raise DeliveryRefused("expected uncompressed application/x-tar response")
                        declared = response.headers.get("content-length")
                        if declared is not None and (not declared.isdigit() or int(declared) > limits.max_response_bytes):
                            raise DeliveryRefused("invalid or over-budget response length")
                        total = 0
                        digest = hashlib.sha256()
                        with native.open("wb") as destination:
                            for chunk in response.iter_raw(chunk_size=1024 * 1024):
                                total += len(chunk)
                                if total > limits.max_response_bytes or time.monotonic() > deadline:
                                    raise DeliveryRefused("native response exceeded byte or wall-time budget")
                                destination.write(chunk)
                                digest.update(chunk)
                        if declared is not None and total != int(declared):
                            raise DeliveryRefused("response length mismatch")
            members = inspect_archive(native, input_time=initialization.input_time,
                                      steps=simulation_length, deadline=deadline)
            # Hard-link publishes only a complete checked archive and refuses races/overwrite.
            os.link(native, output_archive)
            return Delivery(output_archive, digest.hexdigest(), input_digest, initialization,
                            deployment, members, datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    except (httpx.HTTPError, OSError) as exc:
        raise DeliveryRefused("native delivery failed; no artifact published") from exc
