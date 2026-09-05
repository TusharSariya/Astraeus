import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "weathernext_probe_manifest.py"
SPEC = importlib.util.spec_from_file_location("weathernext_probe_manifest", SCRIPT)
assert SPEC and SPEC.loader
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


def test_template_inventory_covers_every_documented_statistics_surface_field():
    manifest = probe.template()
    assert len(manifest["fields"]) == 126
    assert set(manifest["fields"]) == set(probe.EXPECTED_FIELDS)
    assert all(item["status"] == "deferred" for item in manifest["fields"].values())
    assert manifest["request"]["requester_billing_identity"] is None
    assert probe.validate(manifest) == []


def test_success_cannot_be_claimed_from_a_partial_small_sample():
    manifest = probe.template()
    manifest["result"] = "success"
    errors = probe.validate(manifest)
    assert any("selected field" in error for error in errors)
    assert "success requires every usage counter" in errors
    assert "success requires source object identities" in errors


def test_requester_billing_identity_and_over_budget_usage_fail_closed():
    manifest = probe.template()
    manifest["request"]["requester_billing_identity"] = "forbidden-project"
    manifest["usage"]["received_bytes"] = probe.CAPS["received_bytes"] + 1
    errors = probe.validate(manifest)
    assert "requester_billing_identity must be null" in errors
    assert any("received_bytes" in error for error in errors)


def test_boolean_usage_and_malformed_field_evidence_fail_closed():
    manifest = probe.template()
    manifest["usage"]["object_requests"] = True
    manifest["fields"]["total_cloud_cover_mean"] = "observed"
    errors = probe.validate(manifest)
    assert any("object_requests" in error for error in errors)
    assert any("field evidence must be an object" in error for error in errors)


def test_success_requires_exact_time_coordinate_object_and_decoder_evidence():
    manifest = probe.template()
    manifest["result"] = "success"
    manifest["blocker"] = None
    for name in probe.SELECTED_FIELDS:
        manifest["fields"][name].update(
            status="retrieved", dtype="float32", null_count=0, finite_min=0.1, finite_max=0.9
        )
    manifest["usage"] = {key: 0 for key in probe.CAPS}
    manifest["times"]["valid"] = ["arbitrary", "three", "times"]
    manifest["objects"] = [{"name": "chunk"}]
    errors = probe.validate(manifest)
    assert "success requires the exact valid times for leads 6, 12 and 24" in errors
    assert "success requires numeric selected native-cell coordinates" in errors
    assert "each source object requires name, generation/etag and byte size" in errors
    assert "success requires decoder name and version" in errors


def test_retrieved_cloud_ranges_must_be_finite_and_bounded():
    manifest = probe.template()
    item = manifest["fields"]["total_cloud_cover_mean"]
    item.update(status="retrieved", finite_min=-0.01, finite_max=0.8)
    assert any("outside [0,1]" in error for error in probe.validate(manifest))
