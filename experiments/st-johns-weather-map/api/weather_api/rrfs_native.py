"""Isolated RRFSv1.0 parallel 13-km North America temperature experiment.

Only the indexed instantaneous 2-m temperature message is selected. This is
not RRFS 3-km output, REFS, an ensemble member, or a complete-model manifest.
No source registry, point route or operational admission is supplied here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import base64
import json
import math
from pathlib import Path
import sys
import tempfile

from ingest.grib import ByteRange, parse_idx
from ingest.isolation import ProcessAllocationLimits, run_bounded_process

BASE = "https://nomads.ncep.noaa.gov/pub/data/nccf/com/rrfs/para/"
PRODUCT = "rrfs-v1.0-parallel-13km-na-2dfld"
MAX_INDEX_BYTES = 65536
MAX_MESSAGE_BYTES = 2 * 1024**2
LIMITS = ProcessAllocationLimits(1024**3, 8192, 3 * 1024**2, 4096, 65536)
GRID = {
    "gridType": "rotated_ll", "gridDefinitionTemplateNumber": 1,
    "Ni": 1127, "Nj": 683, "numberOfPoints": 769741,
    "latitudeOfSouthernPoleInDegrees": -35., "longitudeOfSouthernPoleInDegrees": 247.,
    "angleOfRotationInDegrees": 0., "scanningMode": 64, "shapeOfTheEarth": 6,
    "latitudeOfFirstGridPointInDegrees": -36.9303, "longitudeOfFirstGridPointInDegrees": 299.,
    "latitudeOfLastGridPointInDegrees": 36.9303, "longitudeOfLastGridPointInDegrees": 60.9458,
    "iDirectionIncrementInDegrees": .1083, "jDirectionIncrementInDegrees": .1083,
}


@dataclass(frozen=True)
class RRFSRequest:
    run_time: datetime
    valid_time: datetime
    latitude: float
    longitude: float

    def validate(self):
        for value in (self.run_time, self.valid_time):
            if not isinstance(value, datetime) or value.utcoffset() is None:
                raise ValueError("RRFS times must be offset-aware")
            utc_value = value.astimezone(UTC)
            if utc_value.minute or utc_value.second or utc_value.microsecond:
                raise ValueError("RRFS selected run and valid time must be exact hours")
        lead = (self.valid_time - self.run_time).total_seconds() / 3600
        maximum = 84 if self.run_time.astimezone(UTC).hour % 6 == 0 else 18
        if lead != int(lead) or not 0 <= lead <= maximum:
            raise ValueError("RRFS selection is outside the documented cycle horizon")
        if not math.isfinite(self.latitude) or not math.isfinite(self.longitude) or not (45 <= self.latitude <= 50.5 and -58 <= self.longitude <= -46):
            raise ValueError("RRFS proof reader supports only the declared evidence box")

    @property
    def url(self):
        self.validate()
        run = self.run_time.astimezone(UTC)
        lead = int((self.valid_time - self.run_time).total_seconds() / 3600)
        return f"{BASE}rrfs.{run:%Y%m%d}/{run:%H}/rrfs.t{run:%H}z.2dfld.13km.f{lead:03d}.na.grib2"

    def as_dict(self):
        self.validate()
        return {"run_time": self.run_time.isoformat(), "valid_time": self.valid_time.isoformat(),
                "latitude": self.latitude, "longitude": self.longitude}


def temperature_range(index: bytes, request: RRFSRequest) -> ByteRange:
    request.validate()
    if not 0 < len(index) <= MAX_INDEX_BYTES:
        raise ValueError("RRFS index exceeds bounded metadata size")
    records = parse_idx(index.decode("ascii"))
    lead = int((request.valid_time - request.run_time).total_seconds() / 3600)
    expected = "anl" if lead == 0 else f"{lead} hour fcst"
    selected = [r for r in records if r.param == "TMP" and r.level == "2 m above ground"]
    if len(selected) != 1:
        raise ValueError("RRFS index must identify exactly one 2-m temperature")
    record = selected[0]
    if record.run_time != request.run_time or record.forecast != expected:
        raise ValueError("RRFS index differs from the exact requested run/lead")
    if record.offset < 0 or record.length is None or not 0 < record.length <= MAX_MESSAGE_BYTES:
        raise ValueError("RRFS temperature requires one finite bounded message range")
    return ByteRange(record.offset, record.end)


def decode_temperature(payload: bytes, request: RRFSRequest) -> dict:
    """Native ecCodes leaf; call through bounded_decode for untrusted bodies."""
    import eccodes as ec
    request.validate()
    if not 20 <= len(payload) <= MAX_MESSAGE_BYTES or payload[:4] != b"GRIB" or payload[-4:] != b"7777" or int.from_bytes(payload[8:16], "big") != len(payload):
        raise ValueError("RRFS requires one complete bounded GRIB2 message")
    handle = ec.codes_new_from_message(payload)
    try:
        expected = {**GRID, "edition": 2, "centre": "kwbc", "subCentre": 0,
            "generatingProcessIdentifier": 134, "typeOfGeneratingProcess": 2,
            "productDefinitionTemplateNumber": 0, "significanceOfReferenceTime": 1,
            "shortName": "2t", "units": "K", "typeOfLevel": "heightAboveGround", "level": 2,
            "stepType": "instant", "stepUnits": 1,
            "dataDate": int(request.run_time.astimezone(UTC).strftime("%Y%m%d")),
            "dataTime": request.run_time.astimezone(UTC).hour * 100,
            "validityDate": int(request.valid_time.astimezone(UTC).strftime("%Y%m%d")),
            "validityTime": request.valid_time.astimezone(UTC).hour * 100,
            "startStep": int((request.valid_time - request.run_time).total_seconds() / 3600),
            "endStep": int((request.valid_time - request.run_time).total_seconds() / 3600)}
        for name, wanted in expected.items():
            actual = ec.codes_get(handle, name)
            if actual != wanted:
                raise ValueError(f"RRFS native {name} differs from the selected product")
        sample = ec.codes_grib_find_nearest(handle, request.latitude, request.longitude)[0]
        if sample["distance"] > 20 or not all(math.isfinite(sample[k]) for k in ("distance", "lat", "lon")):
            raise ValueError("RRFS native grid does not support the requested coordinate")
        missing = bool(ec.codes_get(handle, "bitmapPresent")) and not bool(ec.codes_get_array(handle, "bitmap")[sample["index"]])
        value = None if missing else float(sample["value"])
        if value is not None and not math.isfinite(value):
            raise ValueError("RRFS temperature is non-finite without a native mask")
        return {"source_id": "noaa-rrfs", "product_id": PRODUCT, "variant": "deterministic",
            "run_time": request.run_time.astimezone(UTC).isoformat(),
            "valid_time": request.valid_time.astimezone(UTC).isoformat(),
            "native_field": "TMP", "level": "2 m above ground", "units": "K", "value": value,
            "sampled_latitude": sample["lat"], "sampled_longitude": sample["lon"],
            "sample_distance_km": sample["distance"], "native_index": sample["index"],
            "native_masked": missing, "producer_qc": "unknown", "operational": False,
            "grid": dict(GRID), "sha256": sha256(payload).hexdigest()}
    finally:
        ec.codes_release(handle)


def bounded_decode(payload: bytes, request: RRFSRequest, workspace: Path, *, runner=run_bounded_process) -> dict:
    request.validate()
    if len(payload) > MAX_MESSAGE_BYTES:
        raise ValueError("RRFS message exceeds decode bound")
    with tempfile.TemporaryDirectory(prefix="rrfs-native-", dir=workspace) as directory:
        output = Path(directory) / "result.json"
        runner(command=[sys.executable, "-m", "weather_api.rrfs_native_worker", "{output}"],
               stdin=json.dumps({"request": request.as_dict(), "payload": base64.b64encode(payload).decode()}).encode(),
               destination=output, limits=LIMITS, timeout_seconds=45)
        result = json.loads(output.read_bytes())
        if result.get("sha256") != sha256(payload).hexdigest() or result.get("product_id") != PRODUCT or result.get("operational") is not False:
            raise ValueError("RRFS child output changed native identity")
        return result
