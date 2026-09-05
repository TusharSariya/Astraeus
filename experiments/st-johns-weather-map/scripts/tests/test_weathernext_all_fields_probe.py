import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

SCRIPT_DIR = Path(__file__).parents[1]
sys.path.insert(0, str(SCRIPT_DIR))
spec = importlib.util.spec_from_file_location("weathernext_all_fields_probe", SCRIPT_DIR / "weathernext_all_fields_probe.py")
module = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(module)


def test_probe_describes_every_field_without_downloading(monkeypatch, tmp_path):
    calls = []
    class FakeTransport:
        def __init__(self, _deadline):
            self.requests = 0
            self.received_bytes = 0
        def _run(self, args):
            self.requests += 1
            return SimpleNamespace(stdout=json.dumps({}).encode())
        def describe(self, uri):
            self.requests += 1
            calls.append(uri)
            return {"generation": "1", "etag": "tag", "size": 10, "updateTime": "2026-09-05T00:00:00Z"}
    monkeypatch.setattr(module, "Transport", FakeTransport)
    output = tmp_path / "proof.json"
    result = module.run(output)
    assert result["field_count"] == 126
    assert result["forecast_bytes_not_downloaded"] == 1260
    assert result["received_forecast_bytes"] == 0
    assert len(calls) == 126 and output.exists()


def test_probe_refuses_requester_paid_bucket(monkeypatch, tmp_path):
    class FakeTransport:
        def __init__(self, _deadline):
            self.requests = self.received_bytes = 0
        def _run(self, _args):
            return SimpleNamespace(stdout=json.dumps({"billing": {"requesterPays": True}}).encode())
    monkeypatch.setattr(module, "Transport", FakeTransport)
    try:
        module.run(tmp_path / "proof.json")
    except RuntimeError as error:
        assert "requester-pays" in str(error)
    else:
        raise AssertionError("requester-paid bucket was accepted")
