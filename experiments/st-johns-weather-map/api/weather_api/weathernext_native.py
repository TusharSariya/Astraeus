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
from weather_api.weathernext_query import WeatherNextSelection, WeatherNextValue

from .weathernext_scope import HISTORICAL, validate_scope

BUCKET = "weathernext3_statistics_spatial"


class NativeUnavailable(RuntimeError):
    pass


class NativeBudgetExceeded(ValueError):
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
    grid: dict | None = None
    native_times: tuple[str, ...] | None = None
    unavailable_fields: tuple[str, ...] = ()
    unread_objects: tuple[ObjectIdentity, ...] = ()


class NativeStatisticsReader:
    def __init__(self, transport: ObjectTransport, *, limits: NativeLimits = NativeLimits()):
        self.transport, self.limits = transport, limits

    def read_grid(self, selection: WeatherNextSelection, *, now: datetime, acquisition_scope: str = HISTORICAL, region: str = "avalon") -> NativeReading:
        if selection.fields != ("total_cloud_cover_mean",):
            raise NativeUnavailable("Only total cloud mean supports grid delivery")
        return self.read_point(selection, now=now, acquisition_scope=acquisition_scope, regional=region)

    def read_point(self, selection: WeatherNextSelection, *, now: datetime, acquisition_scope: str = HISTORICAL, regional: bool = False, inventory: bool = False) -> NativeReading:
        import time
        try:
            validate_scope(selection, now, acquisition_scope)
        except ValueError as error:
            raise NativeUnavailable(str(error)) from None
        started = time.monotonic()
        operations = received = 0
        identities = []
        prefix = _run_object_prefix(selection.initialization.isoformat())

        def remaining():
            value = self.limits.seconds - (time.monotonic() - started)
            if value <= 0:
                raise ValueError("deadline")
            return value

        unread_objects = []
        unavailable_fields = []

        def fetch(relative, cap):
            nonlocal operations, received
            if operations + 2 > self.limits.operations:
                raise NativeBudgetExceeded("operation budget")
            operations += 2
            name = f"{prefix}/{relative}"
            item = self.transport.describe(BUCKET, name, timeout=remaining())
            if (item.bucket != BUCKET or item.name != name or not item.generation.isdecimal()
                    or not item.etag or type(item.size) is not int or item.size <= 0):
                raise ValueError("object identity")
            if item.size > cap or received + item.size > self.limits.received_bytes:
                unread_objects.append(item)
                raise NativeBudgetExceeded("native acquisition byte limit")
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
                for field in (() if inventory else selection.fields):
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
                if (len(leads) > 360 or len(leads) == 0 or np.any(leads < 1) or np.any(leads > 360)
                        or np.any(leads != np.floor(leads)) or np.any(np.diff(leads) != 1)):
                    raise ValueError("nonhourly lead axis")
                if inventory:
                    for field in selection.fields:
                        grid = _expected_grid(field)
                        value = node(field, ["lead_time", f"lat_{grid}", f"lon_{grid}"])
                        if value["shape"][0] != len(leads) or value["attributes"]["units"] != _expected_unit(field):
                            raise ValueError("inventory field identity")
                    times = tuple((initialization + timedelta(hours=float(h))).isoformat() for h in leads)
                    return NativeReading(initialization, selection.valid_time, (), tuple(identities), received, native_times=times)
                matches = np.flatnonzero(leads == lead)
                if len(matches) != 1:
                    raise ValueError("exact lead missing")
                ti = int(matches[0])
                output = []
                regional_grid = None
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
                    if regional:
                        # Midpoints use the complete native axes, before clipping or
                        # selecting cells. Preserve latitude order and native precision.
                        normalized = (lon.astype("float64") + 180) % 360 - 180
                        def region_axis(axis, low, high):
                            axis = axis.astype("float64")
                            if len(axis) < 2 or not np.allclose(abs(np.diff(axis)), .1, atol=.00005, rtol=0):
                                raise ValueError("native 0.1 degree spacing")
                            edges = np.concatenate(([axis[0] + (axis[0]-axis[1])/2],
                                (axis[:-1]+axis[1:])/2, [axis[-1]+(axis[-1]-axis[-2])/2]))
                            indices = np.flatnonzero((np.maximum(edges[:-1],edges[1:]) > low) &
                                                    (np.minimum(edges[:-1],edges[1:]) < high))
                            if not 1 < len(indices) <= 302 or np.any(np.diff(indices) != 1):
                                raise ValueError("regional axis coverage")
                            selected_edges = edges[indices[0]:indices[-1]+2]
                            if min(selected_edges)>low or max(selected_edges)<high:
                                raise ValueError("incomplete regional coverage")
                            return indices, selected_edges
                        if regional not in (True, "avalon", "atlantic"): raise ValueError("unsupported grid region")
                        west,south,east,north = (-70,40,-40,55) if regional=="atlantic" else (-55,46.5,-51,48.5)
                        ys, yedges = region_axis(lat, south, north)
                        xs, xedges = region_axis(lon, west % 360, east % 360)
                        xedges = (xedges + 180) % 360 - 180
                        matrix = np.empty((len(ys),len(xs)), dtype="float32")
                        # Intersect each needed native chunk once; never one RPC per cell.
                        for yc in sorted(set(int(y)//chunks[1] for y in ys)):
                            ypart = ys[ys//chunks[1] == yc]
                            for xc in sorted(set(int(x)//chunks[2] for x in xs)):
                                xpart = xs[xs//chunks[2] == xc]
                                path = f"{field}/c/{ti//chunks[0]}/{yc}/{xc}"
                                block = decode(field,value,path,(ti,slice(int(ypart[0]),int(ypart[-1])+1),slice(int(xpart[0]),int(xpart[-1])+1)))
                                matrix[np.ix_(ypart-ys[0],xpart-xs[0])] = block
                        fill = value.get("fill_value")
                        fill = None if fill is None else float(np.asarray(fill,dtype="float32"))
                        valid = np.isfinite(matrix) & (matrix != fill if fill is not None else True)
                        if np.any((matrix[valid]<0)|(matrix[valid]>1)):
                            raise ValueError("cloud range")
                        regional_grid = {"latitudes":lat[ys].astype(float).tolist(), "longitudes":normalized[xs].tolist(),
                            "latitude_edges":yedges.tolist(), "longitude_edges":xedges.tolist(),
                            "percentages":[[float(v)*100 if ok else None for v,ok in zip(row,mask)] for row,mask in zip(matrix,valid)]}
                        # The representative point only supplies shared typed provenance.
                        raw = float(matrix[yi-ys[0],xi-xs[0]])
                    else:
                        try:
                            raw = float(decode(field, value, relative, index))
                        except NativeBudgetExceeded:
                            if len(selection.fields) == 1:
                                raise
                            unavailable_fields.append(field)
                            continue
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
                return NativeReading(initialization, selection.valid_time, tuple(output), tuple(identities), received, grid=regional_grid, unavailable_fields=tuple(unavailable_fields), unread_objects=tuple(unread_objects))
        except Exception:
            raise NativeUnavailable("WeatherNext native metadata, object, or decoding failed") from None
