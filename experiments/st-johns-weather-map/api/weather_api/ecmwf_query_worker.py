"""Bounded native GRIB validation/normalization for the unregistered ECMWF query."""
from __future__ import annotations
import json
from pathlib import Path
import sys
import shutil
import zipfile
from datetime import datetime


def decode(request, destination):
    import eccodes
    import numpy as np
    import xarray as xr
    from ingest.adapters.ecmwf_opendata import _refusing_reader, _assert_exact_grid_and_bounds
    from ingest.grib import write_zarr
    from ingest.contract import FetchWindow
    from ingest.manifest import RequiredField, RunManifest, validate_run
    from .ecmwf_query import FIELDS, MAX_MEMBER_BYTES, MAX_OUTPUT_BYTES, MAX_WORKSPACE_BYTES

    if shutil.disk_usage(destination.parent).free < MAX_WORKSPACE_BYTES:
        raise ValueError("ECMWF decoder lacks its finite workspace allowance")

    source = request["source_id"]
    run, valid = datetime.fromisoformat(request["run_time"]), datetime.fromisoformat(request["valid_time"])
    root = Path(request["directory"])
    bounds = request["bounds"]
    fields, metadata = {}, []
    for row in request["records"]:
        param = row["param"]
        path = root / f"{param}.grib2"
        if path.stat().st_size != row["_length"] or path.stat().st_size > MAX_MEMBER_BYTES:
            raise ValueError("ECMWF native record size mismatch")
        with path.open("rb") as handle:
            gid = eccodes.codes_grib_new_from_file(handle)
            if gid is None:
                raise ValueError("ECMWF native record contains no GRIB message")
            try:
                keys = ("shortName", "typeOfLevel", "level", "units", "stepType", "startStep", "endStep",
                    "dataDate", "dataTime", "validityDate", "validityTime", "marsStream", "marsClass", "dataType",
                    "gridType", "iDirectionIncrementInDegrees", "jDirectionIncrementInDegrees")
                identity = {key: eccodes.codes_get(gid, key) for key in keys}
                expected = {"shortName": param, "stepType": "instant", "startStep": request["lead"], "endStep": request["lead"],
                    "dataDate": int(run.strftime("%Y%m%d")), "dataTime": int(run.strftime("%H%M")),
                    "validityDate": int(valid.strftime("%Y%m%d")), "validityTime": int(valid.strftime("%H%M")),
                    "marsStream": "oper", "marsClass": "od" if source == "ecmwf-ifs" else "ai", "dataType": "fc",
                    "gridType": "regular_ll", "iDirectionIncrementInDegrees": 0.25, "jDirectionIncrementInDegrees": 0.25}
                kind, level, units = ("heightAboveGround", 2, "K") if param in ("2t", "2d") else (
                    ("meanSea", 0, "Pa") if param == "msl" else ("entireAtmosphere", 0, "(0 - 1)" if source == "ecmwf-ifs" else "%"))
                expected.update(typeOfLevel=kind, level=level, units=units)
                if any(identity[key] != wanted for key, wanted in expected.items()):
                    raise ValueError("ECMWF GRIB native field/product/time/grid/unit identity mismatch")
            finally:
                eccodes.codes_release(gid)
            extra = eccodes.codes_grib_new_from_file(handle)
            if extra is not None:
                eccodes.codes_release(extra)
                raise ValueError("ECMWF selected range contains multiple messages")
        field = _refusing_reader(path, param=param, member="deterministic", bounds=bounds, read_identity=True)
        if np.isinf(field.values).any():
            raise ValueError("ECMWF native field has infinite values")
        if param == "tcc" and np.any(np.isfinite(field.values) & ((field.values < 0) | (field.values > 100))):
            raise ValueError("ECMWF cloud percentage is outside its native domain")
        fields[param] = field
        metadata.append(identity)
    _assert_exact_grid_and_bounds({"deterministic": fields}, bounds)
    dataset = xr.Dataset({FIELDS[param][0]: field for param, field in fields.items()})
    dataset = dataset.expand_dims(valid_time=[valid.replace(tzinfo=None)])
    manifest = RunManifest(source, tuple(RequiredField(name, units) for name, units in FIELDS.values()),
        required_valid_times=(valid,), bounds=bounds)
    validation = validate_run(manifest, dataset, window=FetchWindow(now=valid, back_hours=0, forward_hours=0))
    payload = root / "surface.zarr.zip"
    write_zarr(dataset, payload)
    result = {"source_id": source, "run_time": run.isoformat(), "valid_time": valid.isoformat(),
        "fields": list(dataset.data_vars), "complete": validation.complete, "qc_passed": validation.qc_passed,
        "quality": validation.as_quality(), "coverage": validation.as_coverage(), "native_records": metadata,
        **manifest.as_manifest_block()}
    if payload.stat().st_size + len(json.dumps(result).encode()) > MAX_OUTPUT_BYTES:
        raise ValueError("ECMWF normalized decoder output exceeds bound")
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_STORED) as bundle:
        bundle.writestr("manifest.json", json.dumps(result))
        bundle.write(payload, "surface.zarr.zip")


if __name__ == "__main__":
    decode(json.loads(sys.stdin.buffer.read()), Path(sys.argv[1]))
