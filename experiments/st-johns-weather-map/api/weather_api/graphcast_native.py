"""Isolated GraphCast published-output experiment; no API registration.

Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-006.
Requires h5py in an explicitly prepared proof environment, not the API image.
"""
from dataclasses import dataclass
from datetime import UTC, datetime
import math
import re

import numpy as np

from weather_api.aiwp_delivery import NativeObject, RangeReader, RangeRefused


@dataclass(frozen=True)
class GraphCastObject(NativeObject):
    def __post_init__(self):
        match = re.fullmatch(
            r"GRAP_v100_(GFS|IFS)/(\d{4})/(\d{4})/"
            r"GRAP_v100_\1_(\d{10})_f000_f240_06\.nc", self.key)
        if (not match or match[2] + match[3] != match[4][:8]
                or type(self.size) is not int or self.size <= 0
                or not re.fullmatch(r'"[a-f0-9]+(?:-\d+)?"', self.etag)):
            raise ValueError("Expected pinned publisher GRAP_v100 GFS/IFS object")
        datetime.strptime(match[4], "%Y%m%d%H")

    @property
    def initialization(self):
        return datetime.strptime(self.key.rsplit("/", 1)[1].split("_")[3], "%Y%m%d%H").replace(tzinfo=UTC)

    @property
    def initializer(self):
        return self.key.split("/")[0].rsplit("_", 1)[1]


@dataclass(frozen=True)
class GraphCastPoint:
    object_identity: str
    initializer: str
    native_version: str
    initialization: datetime
    valid_time: datetime
    latitude: float
    longitude: float
    # (native field name, native value or missing, native unit)
    values: tuple[tuple[str, float | None, str], ...]
    received_bytes: int
    requests: int
    receipts: tuple[dict, ...]


def _text(value):
    return value.decode("utf-8") if isinstance(value, bytes) else str(value)


def read_point(source: GraphCastObject, valid_time: datetime, latitude: float,
               longitude: float, *, fields=("t2", "msl"), transport=None) -> GraphCastPoint:
    """Read explicit native time; caller chooses the published revision.

    h5py closes before the range reader. No full-file staging or uncapped URL
    opening is permitted. This is a synchronous experimental decode, not an
    untrusted-input process boundary or a production freshness cache.
    """
    if (not isinstance(source, GraphCastObject) or valid_time.tzinfo is None
            or not math.isfinite(latitude) or not -90 <= latitude <= 90
            or not math.isfinite(longitude) or not -180 <= longitude <= 180
            or not fields or len(fields) > 2 or len(set(fields)) != len(fields)
            or any(field not in {"t2", "msl"} for field in fields)):
        raise RangeRefused("Unsupported GraphCast point selection")
    lead_seconds = (valid_time - source.initialization).total_seconds()
    if not 0 <= lead_seconds <= 240 * 3600 or lead_seconds % 21600:
        raise RangeRefused("Exact native six-hour time required")
    import h5py
    with RangeReader(source, max_bytes=8 * 1024**2, max_requests=128,
                     timeout_seconds=90, block_size=65536, transport=transport) as reader:
        try:
            with h5py.File(reader, "r", rdcc_nbytes=4 * 1024**2) as dataset:
                attrs = dataset.attrs
                expected = {"Conventions": "CF-1.8", "model_name": "graphcast",
                            "initialization_model": source.initializer,
                            "initialization_time": source.initialization.strftime("%Y-%m-%dT%H:%M:%S"),
                            "first_forecast_hour": "0", "last_forecast_hour": "240",
                            "forecast_hour_step": "6"}
                if any(_text(attrs.get(k, "")) != v for k, v in expected.items()):
                    raise RangeRefused("GraphCast native identity drift")
                version = _text(attrs.get("version", ""))
                if not version or len(version) > 100:
                    raise RangeRefused("Missing native publisher version")

                def variable(name, shape, dtype, unit):
                    if not isinstance(dataset.get(name, getlink=True), h5py.HardLink):
                        raise RangeRefused("External native link refused")
                    value = dataset[name]
                    if (not isinstance(value, h5py.Dataset) or value.shape != shape
                            or value.dtype != np.dtype(dtype) or value.is_virtual or value.external
                            or _text(value.attrs.get("units", "")) != unit
                            or any(k in value.attrs for k in ("scale_factor", "add_offset"))):
                        raise RangeRefused("Native dimensions, encoding or units drift")
                    chunk = shape if len(shape) == 1 else (1, 721, 1440)
                    if (value.chunks != chunk or value.compression != "gzip"
                            or value.scaleoffset is not None):
                        raise RangeRefused("Native chunk encoding drift")
                    return value

                time = variable("time", (41,), "int32", "seconds since 1970-1-1")
                if _text(time.attrs.get("calendar", "")) != "standard":
                    raise RangeRefused("Native time calendar drift")
                if not np.array_equal(time[:], source.initialization.timestamp() + np.arange(41) * 21600):
                    raise RangeRefused("Native time axis drift")
                lat = variable("latitude", (721,), "float32", "degree")[:]
                lon = variable("longitude", (1440,), "float32", "degree")[:]
                if (not np.array_equal(lat, 90 - np.arange(721) * .25)
                        or not np.array_equal(lon, np.arange(1440) * .25)):
                    raise RangeRefused("Native geographic grid drift")
                ti = int(lead_seconds // 21600)
                yi = int(np.argmin(abs(lat - latitude)))
                xi = int(np.argmin(abs((lon - longitude + 180) % 360 - 180)))
                values = []
                for field in fields:
                    unit = "K" if field == "t2" else "Pa"
                    value = variable(field, (41, 721, 1440), "float32", unit)
                    # NetCDF dimension scales establish ordering, not shape alone.
                    if [[scale.name for scale in dim.values()] for dim in value.dims] != [
                            ["/time"], ["/latitude"], ["/longitude"]]:
                        raise RangeRefused("Native dimension identity drift")
                    info = value.id.get_chunk_info_by_coord((ti, 0, 0))
                    if (info.byte_offset is None or info.size <= 0
                            or info.size > reader.max_bytes - reader.reserved_bytes):
                        raise RangeRefused("Missing or oversized native chunk")
                    raw = float(value[ti, yi, xi])
                    missing = not math.isfinite(raw)
                    for attr in ("_FillValue", "missing_value"):
                        if attr in value.attrs:
                            missing |= bool(np.any(np.asarray(value.attrs[attr], dtype="float32") == raw))
                    values.append((field, None if missing else raw, unit))
                if reader.clock() >= reader.deadline:
                    raise RangeRefused("Native decode deadline")
                return GraphCastPoint(source.identity, source.initializer, version,
                                      source.initialization, valid_time, float(lat[yi]),
                                      float((lon[xi] + 180) % 360 - 180), tuple(values),
                                      reader.received_bytes, reader.requests, tuple(reader.receipts))
        except (ValueError, KeyError, OSError, TypeError, RuntimeError) as exc:
            raise RangeRefused("GraphCast native metadata or range decoding refused") from exc
