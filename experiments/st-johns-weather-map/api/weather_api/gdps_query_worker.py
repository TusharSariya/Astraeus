"""One bounded GDPS selected-frame child; no retained publication."""
from __future__ import annotations

import json
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from ingest.adapters.eccc_datamart import ECCCDataMartAdapter, GDPS_DEMAND_VARS
from ingest.contract import RunCandidate


def main() -> None:
    output = Path(sys.argv[1])
    request = json.loads(sys.stdin.buffer.read())
    fields = tuple(request["fields"])
    adapter = ECCCDataMartAdapter(source_id="eccc-gdps", model_subpath="model_gdps/15km",
                                  grid_token="LatLon0.15", var_map=GDPS_DEMAND_VARS,
                                  bounds=request["bounds"], base_url=request["base_url"], adapter_version="gdps-demand-v1")
    adapter.demand_operation_bounds(len(fields))
    run, selected = datetime.fromisoformat(request["run_time"]), datetime.fromisoformat(request["selected_time"])
    candidate = RunCandidate(request["provider_run_id"], run, [], request["detail"])
    with tempfile.TemporaryDirectory(prefix="gdps-child-", dir=output.parent) as directory:
        result = adapter.fetch_selected(candidate, selected, Path(directory), fields=fields)
        artifact = result.artifacts[0]
        if not result.complete or not result.qc_passed:
            raise ValueError("GDPS selected native fields failed completeness/QC")
        if set(Path(directory).iterdir()) != {artifact.payload_path}:
            raise ValueError("GDPS decode left unexpected workspace files")
        info = {"source_id": result.source_id, "provider_run_id": result.provider_run_id,
                "run_time": run.isoformat(), "valid_time": selected.isoformat(),
                "retrieved_at": result.retrieved_at.isoformat(), "complete": result.complete,
                "qc_passed": result.qc_passed, "provenance": artifact.provenance}
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as bundle:
            bundle.writestr("result.json", json.dumps(info))
            bundle.write(artifact.payload_path, "surface.zarr.zip")


if __name__ == "__main__":
    main()
