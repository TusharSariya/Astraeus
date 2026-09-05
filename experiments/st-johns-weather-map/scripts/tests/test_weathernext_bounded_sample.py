import importlib.util
import json
from pathlib import Path
import sys
import subprocess
import time

import pytest


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


def test_request_cap_is_reserved_before_subprocess(monkeypatch):
    transport = sample.Transport(time.monotonic() + 10)
    transport.requests = contract.CAPS["object_requests"]

    def forbidden(*args, **kwargs):
        raise AssertionError("subprocess must not run after the request cap")

    monkeypatch.setattr(sample.subprocess, "run", forbidden)
    with pytest.raises(sample.ProbeError, match="would be exceeded"):
        transport._run(["objects", "describe", "gs://example/object"])
    assert transport.requests == contract.CAPS["object_requests"]


def test_failed_operation_is_counted_and_stderr_is_redacted(monkeypatch):
    transport = sample.Transport(time.monotonic() + 10)

    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(7, args[0], stderr=b"private@example.com")

    monkeypatch.setattr(sample.subprocess, "run", fail)
    with pytest.raises(sample.ProbeError) as caught:
        transport._run(["objects", "describe", "gs://example/object"])
    assert transport.requests == 1
    assert "exit code 7" in str(caught.value)
    assert "private@example.com" not in str(caught.value)


def test_sensitive_gcloud_overrides_are_forced_empty(monkeypatch):
    captured = {}

    def succeed(*args, **kwargs):
        captured.update(kwargs["env"])
        return subprocess.CompletedProcess(args[0], 0, stdout=b"{}", stderr=b"")

    for key in (
        "CLOUDSDK_BILLING_QUOTA_PROJECT",
        "GOOGLE_CLOUD_QUOTA_PROJECT",
        "CLOUDSDK_CORE_PROJECT",
        "CLOUDSDK_AUTH_IMPERSONATE_SERVICE_ACCOUNT",
        "CLOUDSDK_AUTH_ACCESS_TOKEN_FILE",
        "CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE",
    ):
        monkeypatch.setenv(key, "unexpected-sensitive-value")
    monkeypatch.setattr(sample.subprocess, "run", succeed)

    sample.Transport(time.monotonic() + 10)._run(["objects", "describe", "gs://example/object"])

    assert all(captured[key] == "" for key in (
        "CLOUDSDK_BILLING_QUOTA_PROJECT",
        "GOOGLE_CLOUD_QUOTA_PROJECT",
        "CLOUDSDK_CORE_PROJECT",
        "CLOUDSDK_AUTH_IMPERSONATE_SERVICE_ACCOUNT",
        "CLOUDSDK_AUTH_ACCESS_TOKEN_FILE",
        "CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE",
    ))
