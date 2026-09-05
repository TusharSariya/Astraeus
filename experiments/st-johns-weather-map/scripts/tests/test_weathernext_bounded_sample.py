import importlib.util
import json
from pathlib import Path
import sys


SCRIPT_DIR = Path(__file__).parents[1]
MANIFEST_SPEC = importlib.util.spec_from_file_location(
    "weathernext_probe_manifest", SCRIPT_DIR / "weathernext_probe_manifest.py"
)
assert MANIFEST_SPEC and MANIFEST_SPEC.loader
contract = importlib.util.module_from_spec(MANIFEST_SPEC)
MANIFEST_SPEC.loader.exec_module(contract)
sys.modules["weathernext_probe_manifest"] = contract

SAMPLE_SPEC = importlib.util.spec_from_file_location(
    "weathernext_bounded_sample", SCRIPT_DIR / "weathernext_bounded_sample.py"
)
assert SAMPLE_SPEC and SAMPLE_SPEC.loader
sample = importlib.util.module_from_spec(SAMPLE_SPEC)
SAMPLE_SPEC.loader.exec_module(sample)


def test_success_manifest_serializes_validates_and_writes_exact_size(tmp_path):
    manifest = contract.template()
    manifest.update(result="success", blocker=None)
    for name in contract.SELECTED_FIELDS:
        manifest["fields"][name].update(
            status="retrieved",
            dtype="float32",
            fill_value="NaN",
            null_count=0,
            finite_min=0.1,
            finite_max=0.9,
        )
    manifest["usage"] = {key: 1 for key in contract.CAPS}
    manifest["times"].update(valid=contract.VALID_TIMES, retrieval="2026-09-05T12:00:00Z")
    manifest["coordinates"].update(
        dimensions={"lead_time": 360, "lat_0p1": 1801, "lon_0p1": 3600},
        selected_native_cell={"latitude": 47.5, "longitude": -52.7},
        coordinate_direction={"latitude": "descending", "longitude": "ascending"},
        chunk_or_shard_layout={"chunk_shape": [1, 1801, 3600], "sharded": False},
    )
    manifest["objects"] = [{"name": "known/object", "generation": "1", "size": 1}]
    manifest["decoder"] = {"name": "zarr", "version": "test"}
    output = tmp_path / "nested" / "sample.json"

    measured, digest = sample.write_validated_manifest(manifest, output)

    assert output.is_file()
    assert output.stat().st_size == measured == manifest["usage"]["output_bytes"]
    assert len(digest) == 64
    assert contract.validate(json.loads(output.read_text())) == []
