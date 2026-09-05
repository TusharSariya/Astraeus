import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).parents[1]
sys.path.insert(0, str(SCRIPT_DIR))
spec = importlib.util.spec_from_file_location("weathernext_all_fields_sample", SCRIPT_DIR / "weathernext_all_fields_sample.py")
module = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(module)

PLAN = Path(__file__).parents[4] / "docs" / "research" / "evidence" / "weathernext-20260801-all-fields-lead6.json"


def test_known_plan_over_four_gib_is_refused_before_network(monkeypatch, tmp_path):
    plan = json.loads(PLAN.read_text())
    plan["field_objects"][0]["size"] += module.RECEIVED_CAP
    path = tmp_path / "over.json"
    path.write_text(json.dumps(plan))
    monkeypatch.setattr(module.Transport, "run", lambda *_: pytest.fail("network must not run"))
    with pytest.raises(module.SampleError, match="over the 4 GiB cap"):
        module.run(path, tmp_path / "result.json")


def test_transport_forces_empty_overrides_and_explicit_configuration(monkeypatch):
    captured = {}
    def fake_run(command, **kwargs):
        captured.update(command=command, env=kwargs["env"])
        return subprocess.CompletedProcess(command, 0, b"{}", b"")
    monkeypatch.setattr(module.subprocess, "run", fake_run)
    transport = module.Transport(time.monotonic() + 10)
    transport.run(["objects", "describe", "gs://example/object"])
    assert captured["command"][:3] == ["gcloud", "--configuration=astraeus", "storage"]
    for key in ("CLOUDSDK_BILLING_QUOTA_PROJECT", "GOOGLE_CLOUD_QUOTA_PROJECT",
                "CLOUDSDK_CORE_PROJECT", "CLOUDSDK_AUTH_IMPERSONATE_SERVICE_ACCOUNT",
                "CLOUDSDK_AUTH_ACCESS_TOKEN_FILE", "CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE"):
        assert captured["env"][key] == ""


def test_transport_redacts_provider_stderr(monkeypatch):
    def fail(*_args, **_kwargs):
        raise subprocess.CalledProcessError(1, ["gcloud"], stderr=b"sensitive upstream detail")
    monkeypatch.setattr(module.subprocess, "run", fail)
    with pytest.raises(module.SampleError, match="stderr redacted") as raised:
        module.Transport(time.monotonic() + 10).run(["objects", "describe", "gs://example/object"])
    assert "sensitive" not in str(raised.value)
