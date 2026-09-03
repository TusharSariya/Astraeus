"""Landmark reprojection and the terrain-horizon check refuse together.

A camera geometry is accepted only when both checks pass, refused outright
when either fails, and left ``not_run`` when a check cannot be run at all.
Nothing in between exists: these tests also pin the absence of a degraded or
partial-credit path.

Spec-Refs: openspec/changes/activity-profiles-sites-and-cameras/specs/camera-evidence/spec.md
"""

from __future__ import annotations

import math
from typing import Literal, get_args

import pytest

from ingest.cameras.geometry import (
    ACCEPTED,
    GEOMETRY_FAILED,
    GEOMETRY_UNVALIDATED,
    LANDMARK_REPROJECTION,
    NOT_RUN,
    REFUSED,
    TERRAIN_HORIZON,
    CameraGeometry,
    GeometryStatus,
    Landmark,
    derivation_refusal,
    on_camera_moved,
    project_landmark,
    refusal_messages,
    validate_geometry,
    validate_state,
)

TOLERANCE_PX = 3.0
TOLERANCE_DEG = 0.5


def a_geometry(**overrides: float) -> CameraGeometry:
    """A plausible harbour camera on Signal Hill, pointing east."""

    values: dict = {
        "latitude": 47.5706,
        "longitude": -52.6811,
        "elevation_m": 140.0,
        "bearing_deg": 90.0,
        "hfov_deg": 60.0,
        "vfov_deg": 34.0,
        "roll_deg": 2.0,
        "width_px": 1920,
        "height_px": 1080,
    }
    values.update(overrides)
    return CameraGeometry(**values)


def landmarks_projected_by(geometry: CameraGeometry) -> list[Landmark]:
    """Landmarks whose recorded pixels are exactly where the model puts them."""

    placed = [
        Landmark("fort-amherst", 70.0, 2400.0, 0.0, 0.0),
        Landmark("cabot-tower", 95.0, 900.0, 0.0, 0.0),
        Landmark("south-head", 112.0, 3100.0, 0.0, 0.0),
    ]
    projected = []
    for landmark in placed:
        pixel_x, pixel_y = project_landmark(geometry, landmark)
        projected.append(
            Landmark(landmark.name, landmark.bearing_deg, landmark.distance_m, pixel_x, pixel_y)
        )
    return projected


def a_horizon(count: int = 24, value: float = -1.2) -> list[float]:
    return [value] * count


def test_accepted_geometry_round_trips_its_landmarks() -> None:
    """Project the landmarks, feed the projected pixels back, and accept."""

    geometry = a_geometry()
    landmarks = landmarks_projected_by(geometry)
    terrain = a_horizon()

    verdict = validate_geometry(
        geometry,
        landmarks,
        terrain_horizon=terrain,
        skyline=[angle + 0.2 for angle in terrain],
        reprojection_tolerance_px=TOLERANCE_PX,
        skyline_tolerance_deg=TOLERANCE_DEG,
    )

    assert verdict.status == ACCEPTED
    assert verdict.reprojection_errors == []
    assert verdict.skyline_disagreements == []
    assert verdict.unrun_check is None

    for landmark in landmarks:
        pixel_x, pixel_y = project_landmark(geometry, landmark)
        assert math.isclose(pixel_x, landmark.pixel_x, abs_tol=1e-9)
        assert math.isclose(pixel_y, landmark.pixel_y, abs_tol=1e-9)


def test_reprojection_failed_names_each_landmark_and_its_pixel_error() -> None:
    geometry = a_geometry()
    landmarks = landmarks_projected_by(geometry)
    moved = [
        landmarks[0],
        Landmark(
            landmarks[1].name,
            landmarks[1].bearing_deg,
            landmarks[1].distance_m,
            landmarks[1].pixel_x + 40.0,
            landmarks[1].pixel_y - 30.0,
        ),
        landmarks[2],
    ]
    terrain = a_horizon()

    verdict = validate_geometry(
        geometry,
        moved,
        terrain_horizon=terrain,
        skyline=list(terrain),
        reprojection_tolerance_px=TOLERANCE_PX,
        skyline_tolerance_deg=TOLERANCE_DEG,
    )

    assert verdict.status == REFUSED
    assert [name for name, _ in verdict.reprojection_errors] == ["cabot-tower"]
    error = verdict.reprojection_errors[0][1]
    assert math.isclose(error, 50.0, abs_tol=1e-6)
    assert any("cabot-tower" in message and "50.00 px" in message for message in refusal_messages(verdict))


def test_reprojection_failed_refuses_every_derivation_with_no_partial_credit() -> None:
    """A refused verdict yields no derivation at all, degraded or otherwise."""

    geometry = a_geometry()
    landmarks = landmarks_projected_by(geometry)
    wrong = [
        Landmark(landmark.name, landmark.bearing_deg, landmark.distance_m, 5.0, 5.0)
        for landmark in landmarks
    ]
    terrain = a_horizon()

    state = validate_state(
        geometry,
        wrong,
        terrain_horizon=terrain,
        skyline=list(terrain),
        reprojection_tolerance_px=TOLERANCE_PX,
        skyline_tolerance_deg=TOLERANCE_DEG,
    )

    assert state.verdict.status == REFUSED
    assert state.validated is False
    assert derivation_refusal(state) == GEOMETRY_FAILED

    # No status between accepted and refused exists, and this module carries
    # no cloud-fraction or otherwise partial derivation path.
    assert set(get_args(GeometryStatus)) == {"accepted", "refused", "not_run"}
    assert "degraded" not in {status.lower() for status in get_args(GeometryStatus)}

    from ingest.cameras import geometry as geometry_module

    names = " ".join(dir(geometry_module)).lower()
    assert "degraded" not in names
    assert "cloud" not in names
    assert "partial" not in names


def test_skyline_mismatch_names_each_bearing_with_both_angles() -> None:
    geometry = a_geometry()
    landmarks = landmarks_projected_by(geometry)
    terrain = a_horizon(count=12, value=-1.0)
    skyline = list(terrain)
    skyline[3] = 4.0

    verdict = validate_geometry(
        geometry,
        landmarks,
        terrain_horizon=terrain,
        skyline=skyline,
        reprojection_tolerance_px=TOLERANCE_PX,
        skyline_tolerance_deg=TOLERANCE_DEG,
    )

    assert verdict.status == REFUSED
    assert verdict.reprojection_errors == []
    assert len(verdict.skyline_disagreements) == 1
    bearing, terrain_deg, skyline_deg = verdict.skyline_disagreements[0]
    # Sample 3 of 12 across a 60 degree field centred on 90 degrees.
    assert math.isclose(bearing, 60.0 + 3.5 * 5.0, abs_tol=1e-9)
    assert (terrain_deg, skyline_deg) == (-1.0, 4.0)
    message = refusal_messages(verdict)[0]
    assert "-1.00" in message and "4.00" in message


def test_skyline_mismatch_leaves_no_derivation_running() -> None:
    geometry = a_geometry()
    landmarks = landmarks_projected_by(geometry)
    terrain = a_horizon(count=8, value=0.0)
    skyline = [0.0, 0.0, 9.0, 0.0, 0.0, 0.0, 0.0, -9.0]

    state = validate_state(
        geometry,
        landmarks,
        terrain_horizon=terrain,
        skyline=skyline,
        reprojection_tolerance_px=TOLERANCE_PX,
        skyline_tolerance_deg=TOLERANCE_DEG,
    )

    assert state.verdict.status == REFUSED
    assert len(state.verdict.skyline_disagreements) == 2
    assert derivation_refusal(state) == GEOMETRY_FAILED


def test_not_run_when_the_terrain_horizon_is_absent() -> None:
    geometry = a_geometry()
    landmarks = landmarks_projected_by(geometry)

    verdict = validate_geometry(
        geometry,
        landmarks,
        terrain_horizon=None,
        skyline=a_horizon(),
        reprojection_tolerance_px=TOLERANCE_PX,
        skyline_tolerance_deg=TOLERANCE_DEG,
    )

    assert verdict.status == NOT_RUN
    assert verdict.unrun_check == TERRAIN_HORIZON
    assert verdict.reprojection_errors == []


def test_not_run_when_fewer_than_two_landmarks_are_registered() -> None:
    geometry = a_geometry()
    landmarks = landmarks_projected_by(geometry)[:1]
    terrain = a_horizon()

    state = validate_state(
        geometry,
        landmarks,
        terrain_horizon=terrain,
        skyline=list(terrain),
        reprojection_tolerance_px=TOLERANCE_PX,
        skyline_tolerance_deg=TOLERANCE_DEG,
    )

    assert state.verdict.status == NOT_RUN
    assert state.verdict.unrun_check == LANDMARK_REPROJECTION
    assert state.validated is False
    assert derivation_refusal(state) == GEOMETRY_UNVALIDATED


def test_camera_moved_marks_the_geometry_unvalidated_and_re_runs_both_checks() -> None:
    geometry = a_geometry()
    landmarks = landmarks_projected_by(geometry)
    terrain = a_horizon()

    accepted = validate_state(
        geometry,
        landmarks,
        terrain_horizon=terrain,
        skyline=list(terrain),
        reprojection_tolerance_px=TOLERANCE_PX,
        skyline_tolerance_deg=TOLERANCE_DEG,
    )
    assert accepted.validated is True
    assert derivation_refusal(accepted) is None

    # The camera is repointed: the same landmarks now reproject elsewhere.
    repointed = on_camera_moved(
        accepted,
        terrain_horizon=terrain,
        skyline=[angle + 3.0 for angle in terrain],
        reprojection_tolerance_px=TOLERANCE_PX,
        skyline_tolerance_deg=TOLERANCE_DEG,
    )

    assert repointed.validated is False
    assert repointed.verdict.status == REFUSED
    assert repointed.verdict.skyline_disagreements
    assert derivation_refusal(repointed) == GEOMETRY_FAILED
    assert repointed.geometry == accepted.geometry
    assert repointed.landmarks == accepted.landmarks


def test_camera_moved_suspends_derivations_until_both_checks_pass_again() -> None:
    geometry = a_geometry()
    landmarks = landmarks_projected_by(geometry)
    terrain = a_horizon()

    accepted = validate_state(
        geometry,
        landmarks,
        terrain_horizon=terrain,
        skyline=list(terrain),
        reprojection_tolerance_px=TOLERANCE_PX,
        skyline_tolerance_deg=TOLERANCE_DEG,
    )

    # No DEM to re-check against: the geometry stays suspended, naming the
    # unrun check rather than keeping its earlier acceptance.
    suspended = on_camera_moved(
        accepted,
        terrain_horizon=None,
        skyline=None,
        reprojection_tolerance_px=TOLERANCE_PX,
        skyline_tolerance_deg=TOLERANCE_DEG,
    )
    assert suspended.verdict.status == NOT_RUN
    assert suspended.verdict.unrun_check == TERRAIN_HORIZON
    assert derivation_refusal(suspended) == GEOMETRY_UNVALIDATED

    # Both checks re-run and pass: the camera is validated again.
    revalidated = on_camera_moved(
        suspended,
        terrain_horizon=terrain,
        skyline=list(terrain),
        reprojection_tolerance_px=TOLERANCE_PX,
        skyline_tolerance_deg=TOLERANCE_DEG,
    )
    assert revalidated.verdict.status == ACCEPTED
    assert revalidated.validated is True
    assert derivation_refusal(revalidated) is None


def test_geometry_module_carries_the_named_refusal_codes() -> None:
    assert GEOMETRY_FAILED == "geometry_failed"
    assert GEOMETRY_UNVALIDATED == "geometry_unvalidated"
    assert Literal["accepted", "refused", "not_run"] == GeometryStatus


def test_mismatched_horizon_resolutions_are_refused_rather_than_resampled() -> None:
    geometry = a_geometry()
    landmarks = landmarks_projected_by(geometry)

    with pytest.raises(ValueError, match="different resolutions"):
        validate_geometry(
            geometry,
            landmarks,
            terrain_horizon=a_horizon(count=12),
            skyline=a_horizon(count=8),
            reprojection_tolerance_px=TOLERANCE_PX,
            skyline_tolerance_deg=TOLERANCE_DEG,
        )
