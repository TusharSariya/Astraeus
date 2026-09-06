"""Bounded child entry point for one selected NOAA GFS native timestep."""

from __future__ import annotations

import json
import sys
import tempfile
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

from ingest.adapters.noaa_s3 import NOAAS3Adapter
from ingest.contract import RunCandidate
from .gfs_query import GFS_DEMAND_WORKSPACE_BYTES


def _json(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(type(value).__name__)


def main() -> None:
    output = Path(sys.argv[1])
    if shutil.disk_usage(output.parent).free < GFS_DEMAND_WORKSPACE_BYTES:
        raise RuntimeError("GFS demand child lacks its finite workspace allowance")
    request = json.loads(sys.stdin.buffer.read())
    run_time = datetime.fromisoformat(request["run_time"])
    selected_time = datetime.fromisoformat(request["selected_time"])
    detail = dict(request["detail"])
    retained = detail.get("idx_text_by_lead") or {}
    detail["idx_text_by_lead"] = {int(key): value for key, value in retained.items()}
    candidate = RunCandidate(request["provider_run_id"], run_time, list(request["urls"]), detail)
    with tempfile.TemporaryDirectory(prefix="gfs-demand-child-", dir=output.parent) as directory:
        result = NOAAS3Adapter(base_url=request["base_url"], bounds=request["bounds"]).fetch_selected(
            candidate, selected_time, Path(directory)
        )
        artifact_paths = {artifact.payload_path.resolve() for artifact in result.artifacts}
        actual_paths = {path.resolve() for path in Path(directory).iterdir() if path.is_file()}
        if actual_paths != artifact_paths or len(artifact_paths) > 2:
            raise RuntimeError("GFS demand decode left an unexpected workspace shape")
        if sum(path.stat().st_size for path in artifact_paths) > GFS_DEMAND_WORKSPACE_BYTES - 64 * 1024 * 1024:
            raise RuntimeError("GFS normalized artifacts exceed the finite workspace allowance")
        manifest = {
            "source_id": result.source_id,
            "provider_run_id": result.provider_run_id,
            "run_time": result.run_time,
            "retrieved_at": result.retrieved_at,
            "valid_time": selected_time,
            "complete": result.complete,
            "qc_passed": result.qc_passed,
            "artifacts": [
                {"logical_name": artifact.logical_name, "provenance": artifact.provenance, "name": artifact.payload_path.name}
                for artifact in result.artifacts
            ],
        }
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as bundle:
            bundle.writestr("result.json", json.dumps(manifest, default=_json, sort_keys=True))
            for artifact in result.artifacts:
                bundle.write(artifact.payload_path, f"artifacts/{artifact.payload_path.name}")


if __name__ == "__main__":
    main()
