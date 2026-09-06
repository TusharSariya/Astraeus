from datetime import datetime
import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator, FormatChecker, ValidationError


SCHEMA = json.loads(Path(__file__).with_name("live-query.schema.json").read_text())


def validator(name: str) -> Draft202012Validator:
    return Draft202012Validator(
        {"$ref": f"#/$defs/{name}", "$defs": SCHEMA["$defs"]},
        format_checker=FormatChecker(),
    )


SELECTION = {
    "latitude": 47.5615,
    "longitude": -52.7126,
    "valid_time": "2026-09-06T12:00:00Z",
    "window_start": "2026-09-05T12:00:00Z",
    "window_end": "2026-09-20T12:00:00Z",
    "product": "HRDPS",
    "layer_ids": ["hrdps-total-cloud", "eccc-radar"],
    "field_selectors": ["total_cloud_opacity", "radar_reflectivity"],
}


def parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def validate_time_invariants(snapshot: dict) -> None:
    selection = snapshot["selection"]
    if (parse(snapshot["expires_at"]) - parse(snapshot["selected_at"])).total_seconds() != 900:
        raise ValueError("snapshot lifetime must be exactly 15 minutes")
    if (parse(snapshot["selected_at"]) - parse(selection["window_start"])).total_seconds() != 24 * 3600:
        raise ValueError("window start must be selected_at minus 24 hours")
    if (parse(selection["window_end"]) - parse(snapshot["selected_at"])).total_seconds() != 14 * 24 * 3600:
        raise ValueError("window end must be selected_at plus 14 days")


def validate_fragment_invariants(fragment: dict) -> None:
    fields = [item["key"] for item in fragment["fields"]]
    if len(fields) != len(set(fields)):
        raise ValueError("fragment field keys must be unique")
    interval = fragment["valid_time_or_interval"]
    if isinstance(interval, dict) and parse(interval["end"]) <= parse(interval["start"]):
        raise ValueError("fragment interval end must follow start")
    bounds = fragment["geography"]["bounds"]
    if bounds["west"] >= bounds["east"] or bounds["south"] >= bounds["north"]:
        raise ValueError("fragment geography bounds must have positive extent")


def resolve_map_frame(times: list[str], selected: str) -> str | None:
    instant = parse(selected)
    earlier = [parse(value) for value in times if parse(value) <= instant]
    if not earlier:
        return None
    chosen = max(earlier)
    return chosen.isoformat().replace("+00:00", "Z") if (instant - chosen).total_seconds() < 3600 else None


def validate_atomic_replacement(bundle: dict) -> None:
    validator("replacement_bundle").validate(bundle)
    if len(set(bundle.values())) != 1:
        raise ValueError("timeline, layers and point must name one replacement snapshot")


class LiveQueryContractTests(unittest.TestCase):
    def test_snapshot_closes_every_revision_axis_for_the_selection(self) -> None:
        snapshot = {
            "snapshot_id": "snap-1",
            "selection": SELECTION,
            "selected_at": "2026-09-06T12:00:00Z",
            "expires_at": "2026-09-06T12:15:00Z",
            "state": "current",
            "operation_id": "12345678-1234-5678-9234-567812345678", "fencing_token": 4, "reservation_state": "active", "reserved_bytes": 4096,
            "revision_set": {
                "manifest_revisions": [{"source_id": "eccc-hrdps", "logical_stream": "surface", "revision_id": "rev-7"}],
                "registry_revision": "registry-3",
                "field_catalogue_revision": "fields-4",
                "derivation_versions": {"liquid_fog_state": "1"},
                "inventory_revision": "inventory-9",
            },
        }
        validator("snapshot").validate(snapshot)
        validate_time_invariants(snapshot)

    def test_snapshot_rejects_wrong_lifetime_and_window(self) -> None:
        base = {
            "snapshot_id": "snap-1", "selection": SELECTION, "selected_at": "2026-09-06T12:00:00Z",
            "expires_at": "2026-09-06T12:15:01Z", "state": "current", "operation_id": "12345678-1234-5678-9234-567812345678", "fencing_token": 4, "reservation_state": "active", "reserved_bytes": 4096,
            "revision_set": {"manifest_revisions": [], "registry_revision": "r", "field_catalogue_revision": "f", "derivation_versions": {}, "inventory_revision": "i"},
        }
        validator("snapshot").validate(base)
        with self.assertRaisesRegex(ValueError, "15 minutes"):
            validate_time_invariants(base)
        base["expires_at"] = "2026-09-06T12:15:00Z"
        base["selection"] = {**SELECTION, "window_start": "2026-09-05T13:00:00Z"}
        with self.assertRaisesRegex(ValueError, "minus 24 hours"):
            validate_time_invariants(base)

    def test_snapshot_cannot_hide_revision_axes_or_add_mutable_fields(self) -> None:
        incomplete = {
            "snapshot_id": "snap-1", "selection": SELECTION,
            "selected_at": "2026-09-06T12:00:00Z", "expires_at": "2026-09-06T12:15:00Z",
            "state": "current", "operation_id": "12345678-1234-5678-9234-567812345678", "fencing_token": 4, "reservation_state": "active", "reserved_bytes": 4096, "revision_set": {"manifest_revisions": []},
        }
        with self.assertRaises(ValidationError):
            validator("snapshot").validate(incomplete)

    def test_selection_refresh_is_bound_to_the_baseline(self) -> None:
        request = {"baseline_snapshot_id": "snap-1", "selection": SELECTION, "requested_source_ids": ["eccc-hrdps"], "canonical_selection_digest": "sha256:" + "a" * 64}
        validator("refresh_request").validate(request)
        with self.assertRaises(ValidationError):
            validator("refresh_request").validate({**request, "requested_source_ids": []})

    def test_expected_fragment_requires_identity_shape_and_bounds(self) -> None:
        fragment = {"source_id": "eccc-hrdps", "provider_run_id": "2026090612", "logical_artifact": "surface", "valid_time_or_interval": "2026-09-06T12:00:00Z", "field_group": "cloud", "member_group": "deterministic", "fields": [{"key": "total_cloud_opacity", "units": "%", "level": "entire_atmosphere"}], "geography": {"crs": "EPSG:4326", "bounds": {"west": -54, "south": 46, "east": -51, "north": 49}}, "max_received_bytes": 1000000, "max_staged_bytes": 2000000}
        validator("expected_fragment").validate(fragment)
        validate_fragment_invariants(fragment)
        with self.assertRaises(ValidationError):
            validator("expected_fragment").validate({**fragment, "fields": []})
        with self.assertRaises(ValidationError):
            validator("expected_fragment").validate({**fragment, "max_received_bytes": 0})
        duplicate = {**fragment, "fields": [fragment["fields"][0], fragment["fields"][0]]}
        with self.assertRaisesRegex(ValueError, "unique"):
            validate_fragment_invariants(duplicate)
        reversed_interval = {**fragment, "valid_time_or_interval": {"start": "2026-09-06T13:00:00Z", "end": "2026-09-06T12:00:00Z"}}
        validator("expected_fragment").validate(reversed_interval)
        with self.assertRaisesRegex(ValueError, "follow start"):
            validate_fragment_invariants(reversed_interval)
        reversed_bounds = {**fragment, "geography": {"crs": "EPSG:4326", "bounds": {"west": -51, "south": 49, "east": -54, "north": 46}}}
        validator("expected_fragment").validate(reversed_bounds)
        with self.assertRaisesRegex(ValueError, "positive extent"):
            validate_fragment_invariants(reversed_bounds)

    def test_expired_snapshot_can_remain_charged_while_revoking(self) -> None:
        snapshot = {"snapshot_id": "snap-old", "selection": SELECTION, "selected_at": "2026-09-06T12:00:00Z", "expires_at": "2026-09-06T12:15:00Z", "state": "expired", "operation_id": "12345678-1234-5678-9234-567812345678", "fencing_token": 4, "reservation_state": "revoking", "reserved_bytes": 8192, "revision_set": {"manifest_revisions": [], "registry_revision": "r", "field_catalogue_revision": "f", "derivation_versions": {}, "inventory_revision": "i"}}
        validator("snapshot").validate(snapshot)
        validate_time_invariants(snapshot)
        self.assertGreater(snapshot["reserved_bytes"], 0)

    def test_partial_job_names_each_fragment_outcome(self) -> None:
        job = {
            "job_id": "job-1", "idempotency_key": "sha256:" + "c" * 64, "baseline_snapshot_id": "snap-1", "canonical_selection_digest": "sha256:" + "a" * 64,
            "operation_id": "12345678-1234-5678-9234-567812345678", "fencing_token": 7, "reservation_state": "active", "state": "partial", "provider_payload_requests": 1, "received_bytes": 2048,
            "source_outcomes": [
                {"source_id": "eccc-hrdps", "state": "succeeded", "manifest_revision": "rev-8", "fragment_outcomes": [{"source_id": "eccc-hrdps", "fragment_key": "surface/12Z/cloud", "outcome": "published", "manifest_revision": "rev-8"}]},
                {"source_id": "eccc-radar", "state": "failed", "manifest_revision": None, "fragment_outcomes": [{"source_id": "eccc-radar", "fragment_key": "rain/1210Z", "outcome": "retrieval_failed", "manifest_revision": None}]},
            ],
        }
        validator("refresh_job").validate(job)

    def test_full_cache_hit_has_zero_provider_payload(self) -> None:
        job = {"job_id": "job-hit", "idempotency_key": "sha256:" + "d" * 64, "baseline_snapshot_id": "snap-1", "canonical_selection_digest": "sha256:" + "b" * 64, "operation_id": "12345678-1234-5678-9234-567812345678", "fencing_token": 8, "reservation_state": "releasable", "state": "succeeded", "provider_payload_requests": 0, "received_bytes": 0, "source_outcomes": [{"source_id": "eccc-hrdps", "state": "succeeded", "manifest_revision": "rev-7", "fragment_outcomes": [{"source_id": "eccc-hrdps", "fragment_key": "surface/12Z/cloud", "outcome": "cache_hit", "manifest_revision": "rev-7"}]}]}
        validator("refresh_job").validate(job)
        self.assertTrue(all(f["outcome"] == "cache_hit" for s in job["source_outcomes"] for f in s["fragment_outcomes"]))
        self.assertEqual((job["provider_payload_requests"], job["received_bytes"]), (0, 0))

    def test_live_proxy_receipt_and_map_cutoff(self) -> None:
        validator("live_proxy_raster").validate({"evidence_basis": "live_proxy", "requested_time": "2026-09-06T12:00:00Z", "served_valid_time": "2026-09-06T11:30:00Z", "served_reference_time": None, "retrieval_completed_at": "2026-09-06T12:00:03Z", "cache_status": "miss"})
        self.assertEqual(resolve_map_frame(["2026-09-06T11:30:00Z", "2026-09-06T12:10:00Z"], "2026-09-06T12:00:00Z"), "2026-09-06T11:30:00Z")
        self.assertIsNone(resolve_map_frame(["2026-09-06T11:00:00Z"], "2026-09-06T12:00:00Z"))
        self.assertIsNone(resolve_map_frame(["2026-09-06T12:01:00Z"], "2026-09-06T12:00:00Z"))

    def test_atomic_replacement_requires_three_matching_reads(self) -> None:
        good = {"snapshot_id": "snap-2", "timeline_snapshot_id": "snap-2", "layers_snapshot_id": "snap-2", "point_snapshot_id": "snap-2"}
        validate_atomic_replacement(good)
        mixed = {**good, "point_snapshot_id": "snap-3"}
        with self.assertRaisesRegex(ValueError, "one replacement snapshot"):
            validate_atomic_replacement(mixed)


if __name__ == "__main__":
    unittest.main()
