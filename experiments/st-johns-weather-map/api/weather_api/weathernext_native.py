"""Isolated native statistics Zarr reader. No default transport or registration.

Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-006.
Classification: experiment (weathernext3-statistics-experiment).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
import math
from pathlib import Path
import tempfile
from typing import Protocol

import numpy as np
import zarr

from ingest.adapters.weathernext3_statistics import _expected_grid, _expected_unit, _run_object_prefix
from weather_api.weathernext_query import HISTORICAL_DELAY, WeatherNextSelection, WeatherNextValue

BUCKET = "weathernext3_statistics_spatial"


class NativeUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class ObjectIdentity:
    bucket: str
    name: str
    generation: str
    etag: str
    size: int


class ObjectTransport(Protocol):
    """Implementations must enforce max_bytes during reception, and timeout.

    read must request the supplied generation, never the current object. These
    requirements are an injection contract, not proof of remote authentication.
    """
    def describe(self, bucket: str, name: str, *, timeout: float) -> ObjectIdentity: ...
    def read(self, identity: ObjectIdentity, *, max_bytes: int, timeout: float) -> bytes: ...


@dataclass(frozen=True)
class NativeLimits:
    metadata_bytes: int = 4 * 1024**2
    received_bytes: int = 512 * 1024**2
    decoded_chunk_bytes: int = 128 * 1024**2
    operations: int = 270
    seconds: float = 60


@dataclass(frozen=True)
class NativeReading:
    initialization: datetime
    valid_time: datetime
    values: tuple[WeatherNextValue, ...]
    objects: tuple[ObjectIdentity, ...]
    received_bytes: int
    # Statistics are surface arrays; no pressure-level/member axis exists.
    pressure_level: None = None
    member: None = None


class NativeStatisticsReader:
    def __init__(self, transport: ObjectTransport, *, limits: NativeLimits = NativeLimits()):
        self.transport, self.limits = transport, limits

    def read_point(self, selection: WeatherNextSelection, *, now: datetime) -> NativeReading:
        import time
        if now.tzinfo is None or selection.valid_time >= now - HISTORICAL_DELAY:
            raise NativeUnavailable("WeatherNext historical permission boundary")
        started = time.monotonic()
        operations = received = 0
        identities = []
        prefix = _run_object_prefix(selection.initialization.isoformat())

        def remaining():
            value = self.limits.seconds - (time.monotonic() - started)
            if value <= 0:
                raise ValueError("deadline")
            return value

        def fetch(relative, cap):
            nonlocal operations, received
            if operations + 2 > self.limits.operations:
                raise ValueError("operation budget")
            operations += 2
            name = f"{prefix}/{relative}"
            item = self.transport.describe(BUCKET, name, timeout=remaining())
            if (item.bucket != BUCKET or item.name != name or not item.generation.isdecimal()
                    or not item.etag or type(item.size) is not int or not 0 < item.size <= cap
                    or received + item.size > self.limits.received_bytes):
                raise ValueError("object identity or byte budget")
            body = self.transport.read(item, max_bytes=item.size, timeout=remaining())
            remaining()
            if not isinstance(body, bytes) or len(body) != item.size:
                raise ValueError("object size")
            received += len(body)
            identities.append(item)
            return body

        try:
            root = json.loads(fetch("zarr.json", self.limits.metadata_bytes))
            if root.get("zarr_format") != 3 or root.get("node_type") != "group":
                raise ValueError("root")
            nodes = root["consolidated_metadata"]["metadata"]
            if not isinstance(nodes, dict) or len(nodes) > 256:
                raise ValueError("metadata nodes")

            def node(name, dimensions):
                value = nodes[name]
                shape = value["shape"]
                chunk = value["chunk_grid"]["configuration"]["chunk_shape"]
                if (value.get("zarr_format") != 3 or value.get("node_type") != "array"
                        or (value.get("dimension_names") or []) != dimensions
                        or len(shape) != len(dimensions) or len(chunk) != len(shape)
                        or any(type(n) is not int or n <= 0 for n in shape + chunk)
                        or value["chunk_grid"]["name"] != "regular"
                        or value["chunk_key_encoding"] != {"name": "default", "configuration": {"separator": "/"}}):
                    raise ValueError("native dimensions or chunks")
                dtype = np.dtype(value["data_type"])
                if dtype.kind not in "if" or dtype.itemsize > 8:
                    raise ValueError("dtype")
                if math.prod(chunk) * dtype.itemsize > self.limits.decoded_chunk_bytes:
                    raise ValueError("decoded chunk budget")
                codecs = value["codecs"]
                if not codecs or any(c["name"] not in {"bytes", "zstd", "blosc"} for c in codecs):
                    raise ValueError("unsupported codec")
                return value

            with tempfile.TemporaryDirectory(prefix="weathernext-native-") as directory:
                local = Path(directory)

                def decode(name, value, relative, index):
                    body = fetch(relative, self.limits.received_bytes)
                    target = local / name
                    target.mkdir(exist_ok=True)
                    (target / "zarr.json").write_text(json.dumps(value))
                    chunk_path = local / relative
                    chunk_path.parent.mkdir(parents=True, exist_ok=True)
                    chunk_path.write_bytes(body)
                    result = np.asarray(zarr.open_array(target, mode="r")[index])
                    chunk_path.unlink()
                    return result

                coordinates = {}
                names = {"init_time", "lead_time"}
                for field in selection.fields:
                    grid = _expected_grid(field)
                    names.update((f"lat_{grid}", f"lon_{grid}"))
                for name in sorted(names):
                    dimensions = [] if name == "init_time" else [name]
                    value = node(name, dimensions)
                    coordinate_unit = ("degrees_north" if name.startswith("lat_") else
                                       "degrees_east" if name.startswith("lon_") else None)
                    attributes = value.get("attributes", {})
                    # The provider uses plain degrees for true longitude. CF's
                    # standard_name distinguishes it from rotated grid_longitude;
                    # degrees alone cannot establish a geographic coordinate.
                    explicit_longitude = (name.startswith("lon_")
                                          and attributes.get("units") == "degrees"
                                          and attributes.get("standard_name") == "longitude")
                    if (coordinate_unit and attributes.get("units") != coordinate_unit
                            and not explicit_longitude):
                        raise ValueError("native geographic coordinate unit")
                    if value["shape"] != value["chunk_grid"]["configuration"]["chunk_shape"]:
                        raise ValueError("coordinate requires multiple chunks")
                    if math.prod(value["shape"]) > 10000:
                        raise ValueError("coordinate bound")
                    relative = name + ("/c" if not dimensions else "/c/0")
                    coordinates[name] = decode(name, value, relative, () if not dimensions else slice(None))
                    if not np.isfinite(coordinates[name]).all():
                        raise ValueError("nonfinite coordinate")
                units = nodes["init_time"]["attributes"]["units"]
                scale, epoch = units.split(" since ", 1)
                scales = {"days": 86400, "hours": 3600, "seconds": 1}
                origin = datetime.fromisoformat(epoch.replace("Z", "+00:00"))
                if origin.tzinfo is None:
                    origin = origin.replace(tzinfo=UTC)  # CF UTC epoch convention
                initialization = origin + timedelta(seconds=float(coordinates["init_time"]) * scales[scale])
                if initialization != selection.initialization or nodes["lead_time"]["attributes"]["units"] != "hours":
                    raise ValueError("native time units or initialization")
                lead = (selection.valid_time - initialization).total_seconds() / 3600
                leads = coordinates["lead_time"]
                if np.any(np.diff(leads) != 1):
                    raise ValueError("nonhourly lead axis")
                matches = np.flatnonzero(leads == lead)
                if len(matches) != 1:
                    raise ValueError("exact lead missing")
                ti = int(matches[0])
                output = []
                for field in selection.fields:
                    grid = _expected_grid(field)
                    dimensions = ["lead_time", f"lat_{grid}", f"lon_{grid}"]
                    value = node(field, dimensions)
                    lat, lon = (coordinates[n] for n in dimensions[1:])
                    for axis, maximum in ((lat, 90), (lon, 360)):
                        if len(axis) > 1 and not (np.all(np.diff(axis) > 0) or np.all(np.diff(axis) < 0)):
                            raise ValueError("ambiguous coordinate axis")
                        if np.any(np.abs(axis) > maximum):
                            raise ValueError("coordinate range")
                    if np.any(lon < 0) or np.any(lon >= 360):
                        raise ValueError("longitude convention")
                    if value["shape"] != [len(leads), len(lat), len(lon)] or value["data_type"] != "float32":
                        raise ValueError("field shape")
                    unit = value["attributes"]["units"]
                    if unit != _expected_unit(field):
                        raise ValueError("native unit")
                    yi = int(np.argmin(abs(lat - selection.latitude)))
                    distance = abs((lon - selection.longitude + 180) % 360 - 180)
                    xi = int(np.argmin(distance))
                    tolerance = (0.05 if grid == "0p1" else 0.025) + 0.00005
                    if abs(float(lat[yi]) - selection.latitude) > tolerance or distance[xi] > tolerance:
                        raise ValueError("point outside native footprint")
                    index = (ti, yi, xi)
                    chunks = value["chunk_grid"]["configuration"]["chunk_shape"]
                    relative = field + "/c/" + "/".join(str(i // c) for i, c in zip(index, chunks))
                    raw = float(decode(field, value, relative, index))
                    fill = value.get("fill_value")
                    if fill is not None:
                        # JSON decimals must be compared at the native precision.
                        fill = float(np.asarray(fill, dtype=value["data_type"]))
                    result = None if not math.isfinite(raw) or raw == fill else raw
                    if result is not None and "cloud_cover" in field and not 0 <= result <= 1:
                        raise ValueError("cloud range")
                    output.append(WeatherNextValue(field, result, unit, field.rsplit("_", 1)[1], grid,
                                                  float(lat[yi]), float((lon[xi] + 180) % 360 - 180)))
                remaining()
                return NativeReading(initialization, selection.valid_time, tuple(output), tuple(identities), received)
        except Exception:
            raise NativeUnavailable("WeatherNext native metadata, object, or decoding failed") from None
