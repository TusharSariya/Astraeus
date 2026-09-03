"""The seventeen real camera records: partnership-only, unretrieved, unadmitted.

The shape of a camera record is exercised in ``api/tests/test_camera_registry.py``
against synthetic fixtures; this file checks that the real registry actually
carries what task 4.3 committed to: every camera catalogued as
``partnership-only`` with its terms quoted from the camera inventory, Fort
Amherst as the sole recorded permission request, retrieval refused naming each
camera and its terms, and the three ledger records listing exactly their
camera ids with an unsatisfied ``admission_condition``.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REGISTRY_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REGISTRY_DIR))

import camera_audit  # noqa: E402
from source_data import registry  # noqa: E402

CCG_CAMERA_IDS = ["ccg-fort-amherst", "ccg-st-johns-base", "ccg-sir-humphrey-gilbert"]
CITY_CAMERA_IDS = [
    "city-new-gower-street",
    "city-middle-pond",
    "city-shea-heights",
    "city-thorburn-road",
    "city-windsor-lake",
    "city-kenmount-road",
]
NTV_CAMERA_IDS = [
    "ntv-st-johns-sky",
    "ntv-quidi-vidi-lake",
    "ntv-downtown",
    "ntv-george-street",
    "ntv-admirals-green",
    "ntv-logy-bay-road",
    "ntv-st-philips-bell-island",
    "ntv-port-de-grave",
]
ALL_CAMERA_IDS = CCG_CAMERA_IDS + CITY_CAMERA_IDS + NTV_CAMERA_IDS


def _by_id() -> dict[str, dict]:
    loaded = camera_audit.load_cameras()
    for camera_id, entry in loaded.items():
        if isinstance(entry, camera_audit.CameraError):
            raise AssertionError(str(entry))
    return loaded


def _sources_by_id() -> dict[str, dict]:
    return {source["id"]: source for source in registry()["sources"]}


class SeventeenCameraRecordsTests(unittest.TestCase):
    def test_seventeen_camera_files_load(self) -> None:
        cameras = _by_id()
        self.assertEqual(17, len(cameras))
        self.assertEqual(set(ALL_CAMERA_IDS), set(cameras))

    def test_every_camera_is_partnership_only_with_no_redistribution(self) -> None:
        cameras = _by_id()
        for camera_id, camera in cameras.items():
            record = camera.record
            with self.subTest(camera_id=camera_id):
                self.assertEqual("partnership-only", record["status"])
                self.assertFalse(record["terms"]["redistribution"])
                self.assertIsNone(record["terms"]["permission"]["granted_on"])

    def test_retrieval_is_refused_for_every_camera_naming_it_and_its_terms(self) -> None:
        cameras = _by_id()
        for camera_id, camera in cameras.items():
            with self.subTest(camera_id=camera_id):
                refusal = camera_audit.retrieval_allowed(camera)
                self.assertIsNotNone(refusal)
                self.assertEqual(camera_audit.REFUSAL_PARTNERSHIP_ONLY, refusal.code)
                self.assertEqual(camera_id, refusal.camera_id)
                self.assertIn(camera_id, refusal.detail)
                self.assertIn(camera.record["terms"]["text"], refusal.detail)

    def test_fort_amherst_is_the_only_ccg_camera_with_a_request_date(self) -> None:
        cameras = _by_id()
        fort_amherst = cameras["ccg-fort-amherst"].record
        self.assertEqual("2026-09-02", fort_amherst["terms"]["permission"]["requested_on"])
        self.assertEqual("Canadian Coast Guard", fort_amherst["terms"]["permission"]["requested_from"])

        for camera_id in ("ccg-st-johns-base", "ccg-sir-humphrey-gilbert"):
            permission = cameras[camera_id].record["terms"]["permission"]
            with self.subTest(camera_id=camera_id):
                self.assertIsNone(permission["requested_on"])
                self.assertIn("Fort Amherst", permission["requested_from"])

    def test_ledger_records_list_exactly_their_camera_ids(self) -> None:
        sources = _sources_by_id()
        expected = {
            "ccg-harbour-cameras": CCG_CAMERA_IDS,
            "city-st-johns-road-cameras": CITY_CAMERA_IDS,
            "ntv-cameras": NTV_CAMERA_IDS,
        }
        for source_id, camera_ids in expected.items():
            with self.subTest(source_id=source_id):
                source = sources[source_id]
                self.assertEqual(set(camera_ids), set(source["cameras"]))
                self.assertEqual("partnership-only", source["status"])

    def test_ledger_records_carry_an_unsatisfied_admission_condition(self) -> None:
        sources = _sources_by_id()
        for source_id in ("ccg-harbour-cameras", "city-st-johns-road-cameras", "ntv-cameras"):
            with self.subTest(source_id=source_id):
                condition = sources[source_id]["admission_condition"]
                self.assertFalse(condition["satisfied"])
                self.assertTrue(condition["condition"].strip())
                self.assertTrue(condition["satisfied_by"].strip())

    def test_camera_source_ids_point_at_a_real_ledger_record(self) -> None:
        cameras = _by_id()
        sources = _sources_by_id()
        for camera in cameras.values():
            with self.subTest(camera_id=camera.camera_id):
                self.assertIn(camera.record["source_id"], sources)

    def test_camera_audit_admits_none_of_the_seventeen(self) -> None:
        cameras = _by_id()
        for camera_id, camera in cameras.items():
            with self.subTest(camera_id=camera_id):
                verdict = camera_audit.audit_camera(camera)
                self.assertEqual("incomplete", verdict.status)
                self.assertEqual([], verdict.errors)


if __name__ == "__main__":
    unittest.main()
