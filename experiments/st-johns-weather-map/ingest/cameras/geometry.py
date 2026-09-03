"""Camera geometry: landmark reprojection and the terrain-horizon check.

A camera geometry is a claim about where a camera points. Nothing that reads
a frame may rely on that claim until it has been checked twice, against two
independent things:

* **Landmark reprojection.** Every hand-registered landmark carries a true
  bearing, a ground distance and the pixel it occupies in the image. Project
  the landmark through the declared geometry and the projected pixel must
  land within ``reprojection_tolerance_px`` of the recorded one.
* **The terrain horizon.** The horizon computed from a digital elevation
  model must match the visible skyline within ``skyline_tolerance_deg`` at
  every sampled bearing.

Both checks must pass for :data:`ACCEPTED`. A geometry that fails either is
refused outright, naming each failing landmark with its pixel error and each
disagreeing bearing with both angles. There is no degraded status, no
partial credit and no reduced derivation for a nearly-correct geometry: a
refused geometry serves no camera derivation at all, and every camera-derived
field for it is ``null`` naming :data:`GEOMETRY_FAILED`. A check that cannot
be run at all (fewer than two landmarks, or no DEM horizon) is neither a pass
nor a failure: the verdict is :data:`NOT_RUN` and it names the unrun check,
and the camera serves no derivation until both checks have run.

Both checks are re-run by :func:`on_camera_moved` when the ``camera_moved``
health flag is raised on a frame; the geometry is marked unvalidated first,
so derivations stay suspended until both checks pass again.

The projection model
--------------------

:func:`project_landmark` is a pinhole camera with square-ish pixels and no
lens distortion, built from the declared orientation alone:

1. The horizontal angle off the optical axis is the landmark's true bearing
   minus the camera's, wrapped to ``[-180, 180)``.
2. The vertical angle off the optical axis is the depression angle of the
   landmark, ``atan(elevation_m / distance_m)``, positive downward, taking
   the landmark to be at the camera's ground level at its declared range.
3. Both angles become normalised image coordinates through their tangents,
   which are rotated by ``roll_deg`` in the image plane.
4. The focal lengths follow from the fields of view,
   ``fx = (width_px / 2) / tan(hfov_deg / 2)`` and likewise ``fy`` from
   ``vfov_deg`` and ``height_px``, and scale the rotated coordinates into
   pixels from the image centre.

This is deliberately the simplest model that a hand-registered record can
support. It is the model the tolerance is declared against; if a camera needs
lens distortion the record is not yet complete, and the reprojection check
will say so by failing rather than by quietly widening.

Dependency direction: pure ``math`` and ``dataclasses``. ``ingest`` never
imports ``api``.

Spec-Refs: openspec/changes/activity-profiles-sites-and-cameras/specs/camera-evidence/spec.md
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Literal, Sequence

#: The refusal code every camera-derived field carries when the camera's
#: geometry was refused by either check.
GEOMETRY_FAILED = "geometry_failed"

#: The refusal code for a geometry that has not been validated (or has been
#: marked unvalidated after a move) and so has not yet earned a derivation.
GEOMETRY_UNVALIDATED = "geometry_unvalidated"

#: The three verdict statuses. There is no degraded or partial-credit status,
#: and adding one would contradict the camera-evidence spec.
ACCEPTED = "accepted"
REFUSED = "refused"
NOT_RUN = "not_run"

GeometryStatus = Literal["accepted", "refused", "not_run"]

#: The names the verdict uses for a check that could not be run.
LANDMARK_REPROJECTION = "landmark_reprojection"
TERRAIN_HORIZON = "terrain_horizon"
VISIBLE_SKYLINE = "visible_skyline"

#: Reprojection fixes an orientation only from two or more landmarks; a
#: single landmark is satisfied by a whole family of geometries. This mirrors
#: ``registry.camera_audit.MINIMUM_LANDMARKS``.
MINIMUM_LANDMARKS = 2


class GeometryError(ValueError):
    """The declared geometry cannot be projected through at all."""


@dataclass(frozen=True)
class CameraGeometry:
    """Where a camera sits and how it points, as registered by hand."""

    latitude: float
    longitude: float
    elevation_m: float
    bearing_deg: float
    hfov_deg: float
    vfov_deg: float
    roll_deg: float
    width_px: int
    height_px: int


@dataclass(frozen=True)
class Landmark:
    """A hand-registered horizon landmark and the pixel it occupies."""

    name: str
    bearing_deg: float
    distance_m: float
    pixel_x: float
    pixel_y: float


@dataclass(frozen=True)
class GeometryVerdict:
    """What the two checks found.

    ``reprojection_errors`` carries every landmark whose projected pixel
    missed its recorded one by more than the tolerance, as
    ``(name, error_px)``. ``skyline_disagreements`` carries every sampled
    bearing where the terrain horizon and the visible skyline differ by more
    than the tolerance, as ``(bearing_deg, terrain_deg, skyline_deg)``.
    ``unrun_check`` names the check that could not be run, and is set only
    when ``status`` is ``not_run``.
    """

    status: GeometryStatus
    reprojection_errors: list[tuple[str, float]]
    skyline_disagreements: list[tuple[float, float, float]]
    unrun_check: str | None


@dataclass(frozen=True)
class GeometryState:
    """A camera's geometry, its landmarks and the standing verdict.

    ``validated`` is true only while the standing verdict is ``accepted``;
    raising ``camera_moved`` clears it through :func:`on_camera_moved`.
    """

    geometry: CameraGeometry
    landmarks: tuple[Landmark, ...]
    verdict: GeometryVerdict
    validated: bool


def _wrap180(degrees: float) -> float:
    """The angle in ``[-180, 180)``."""

    return (degrees + 180.0) % 360.0 - 180.0


def project_landmark(geometry: CameraGeometry, landmark: Landmark) -> tuple[float, float]:
    """Project a landmark to a pixel through the declared geometry.

    The pinhole model is the one documented in the module docstring: azimuth
    offset from the optical axis and the depression angle from the camera
    height and the landmark distance, then roll in the image plane, then the
    focal lengths implied by the fields of view.

    Raises :class:`GeometryError` when the declared geometry has no usable
    projection (a field of view at or past a half turn, a non-positive image
    size or distance), or when the landmark falls behind the camera, where a
    pinhole model has no answer rather than a distant one.
    """

    if not (0.0 < geometry.hfov_deg < 180.0):
        raise GeometryError(f"hfov_deg out of range for a pinhole model: {geometry.hfov_deg}")
    if not (0.0 < geometry.vfov_deg < 180.0):
        raise GeometryError(f"vfov_deg out of range for a pinhole model: {geometry.vfov_deg}")
    if geometry.width_px <= 0 or geometry.height_px <= 0:
        raise GeometryError(
            f"image size must be positive: {geometry.width_px}x{geometry.height_px}"
        )
    if landmark.distance_m <= 0.0:
        raise GeometryError(f"landmark {landmark.name} has a non-positive distance")

    azimuth_offset = _wrap180(landmark.bearing_deg - geometry.bearing_deg)
    if abs(azimuth_offset) >= 90.0:
        raise GeometryError(
            f"landmark {landmark.name} lies {azimuth_offset:.1f} degrees off the optical axis, "
            "behind the image plane"
        )

    depression = math.degrees(math.atan2(geometry.elevation_m, landmark.distance_m))

    tan_x = math.tan(math.radians(azimuth_offset))
    tan_y = math.tan(math.radians(depression))

    roll = math.radians(geometry.roll_deg)
    cos_roll, sin_roll = math.cos(roll), math.sin(roll)
    rolled_x = tan_x * cos_roll - tan_y * sin_roll
    rolled_y = tan_x * sin_roll + tan_y * cos_roll

    focal_x = (geometry.width_px / 2.0) / math.tan(math.radians(geometry.hfov_deg / 2.0))
    focal_y = (geometry.height_px / 2.0) / math.tan(math.radians(geometry.vfov_deg / 2.0))

    return (
        geometry.width_px / 2.0 + focal_x * rolled_x,
        geometry.height_px / 2.0 + focal_y * rolled_y,
    )


def sample_bearings(geometry: CameraGeometry, count: int) -> list[float]:
    """The true bearing of each horizon sample, in ``[0, 360)``.

    The samples are taken at equal resolution across the camera's horizontal
    field of view, at the centre of each of ``count`` equal cells, so that a
    terrain horizon and a skyline of the same length are comparable sample by
    sample.
    """

    if count <= 0:
        raise GeometryError("a horizon needs at least one sample")
    step = geometry.hfov_deg / count
    start = geometry.bearing_deg - geometry.hfov_deg / 2.0
    return [(start + (index + 0.5) * step) % 360.0 for index in range(count)]


def validate_geometry(
    geometry: CameraGeometry,
    landmarks: Sequence[Landmark],
    *,
    terrain_horizon: Sequence[float] | None,
    skyline: Sequence[float] | None,
    reprojection_tolerance_px: float,
    skyline_tolerance_deg: float,
) -> GeometryVerdict:
    """Run both checks and return the verdict.

    ``terrain_horizon`` and ``skyline`` are elevation angles in degrees, one
    per bearing, at equal resolution across the camera's horizontal field of
    view; the bearing of each sample follows from its index, ``hfov_deg`` and
    ``bearing_deg`` (see :func:`sample_bearings`).

    A geometry is ``accepted`` only when both checks ran and both passed. A
    check that failed makes the verdict ``refused``, with no degraded path. A
    check that could not be run at all makes the verdict ``not_run``, naming
    the unrun check: fewer than :data:`MINIMUM_LANDMARKS` landmarks names
    ``landmark_reprojection``, an absent DEM horizon names ``terrain_horizon``
    and an absent skyline names ``visible_skyline``.
    """

    if reprojection_tolerance_px <= 0.0:
        raise GeometryError("reprojection_tolerance_px must be positive")
    if skyline_tolerance_deg <= 0.0:
        raise GeometryError("skyline_tolerance_deg must be positive")

    unrun: list[str] = []

    reprojection_errors: list[tuple[str, float]] = []
    if len(landmarks) < MINIMUM_LANDMARKS:
        unrun.append(LANDMARK_REPROJECTION)
    else:
        for landmark in landmarks:
            projected_x, projected_y = project_landmark(geometry, landmark)
            error = math.hypot(projected_x - landmark.pixel_x, projected_y - landmark.pixel_y)
            if error > reprojection_tolerance_px:
                reprojection_errors.append((landmark.name, error))

    skyline_disagreements: list[tuple[float, float, float]] = []
    if terrain_horizon is None:
        unrun.append(TERRAIN_HORIZON)
    elif skyline is None:
        unrun.append(VISIBLE_SKYLINE)
    elif len(terrain_horizon) != len(skyline):
        raise GeometryError(
            "terrain horizon and skyline are sampled at different resolutions: "
            f"{len(terrain_horizon)} against {len(skyline)}"
        )
    elif not terrain_horizon:
        unrun.append(TERRAIN_HORIZON)
    else:
        bearings = sample_bearings(geometry, len(terrain_horizon))
        for bearing, terrain_deg, skyline_deg in zip(bearings, terrain_horizon, skyline):
            if abs(terrain_deg - skyline_deg) > skyline_tolerance_deg:
                skyline_disagreements.append((bearing, float(terrain_deg), float(skyline_deg)))

    if reprojection_errors or skyline_disagreements:
        # A failure is decisive even when the other check could not be run:
        # there is nothing left to accept.
        return GeometryVerdict(
            status=REFUSED,
            reprojection_errors=reprojection_errors,
            skyline_disagreements=skyline_disagreements,
            unrun_check=None,
        )
    if unrun:
        return GeometryVerdict(
            status=NOT_RUN,
            reprojection_errors=[],
            skyline_disagreements=[],
            unrun_check=unrun[0],
        )
    return GeometryVerdict(
        status=ACCEPTED,
        reprojection_errors=[],
        skyline_disagreements=[],
        unrun_check=None,
    )


def refusal_messages(verdict: GeometryVerdict) -> list[str]:
    """One human-readable line per failing landmark and disagreeing bearing.

    A refusal says which landmark missed and by how many pixels, and which
    bearing disagreed with both the terrain angle and the skyline angle, so
    that the record can be corrected rather than loosened.
    """

    messages = [
        f"landmark {name} reprojection error {error:.2f} px" for name, error in verdict.reprojection_errors
    ]
    messages.extend(
        f"bearing {bearing:.2f} deg: terrain {terrain:.2f} deg against skyline {sky:.2f} deg"
        for bearing, terrain, sky in verdict.skyline_disagreements
    )
    if verdict.unrun_check is not None:
        messages.append(f"check not run: {verdict.unrun_check}")
    return messages


def validate_state(
    geometry: CameraGeometry,
    landmarks: Sequence[Landmark],
    *,
    terrain_horizon: Sequence[float] | None,
    skyline: Sequence[float] | None,
    reprojection_tolerance_px: float,
    skyline_tolerance_deg: float,
) -> GeometryState:
    """Validate a geometry and hold the verdict beside it."""

    verdict = validate_geometry(
        geometry,
        landmarks,
        terrain_horizon=terrain_horizon,
        skyline=skyline,
        reprojection_tolerance_px=reprojection_tolerance_px,
        skyline_tolerance_deg=skyline_tolerance_deg,
    )
    return GeometryState(
        geometry=geometry,
        landmarks=tuple(landmarks),
        verdict=verdict,
        validated=verdict.status == ACCEPTED,
    )


def on_camera_moved(
    state: GeometryState,
    *,
    terrain_horizon: Sequence[float] | None,
    skyline: Sequence[float] | None,
    reprojection_tolerance_px: float,
    skyline_tolerance_deg: float,
) -> GeometryState:
    """Re-run both checks after a ``camera_moved`` flag was raised.

    The geometry is marked unvalidated first, so a caller that reads the
    state between the two steps sees a suspended camera rather than a stale
    acceptance, and both checks are then re-run. The returned state is
    validated again only when the re-run accepted; until then
    :func:`derivation_refusal` keeps every camera derivation suspended.
    """

    suspended = replace(state, validated=False)
    return validate_state(
        suspended.geometry,
        suspended.landmarks,
        terrain_horizon=terrain_horizon,
        skyline=skyline,
        reprojection_tolerance_px=reprojection_tolerance_px,
        skyline_tolerance_deg=skyline_tolerance_deg,
    )


def derivation_refusal(state: GeometryState) -> str | None:
    """The refusal a camera derivation carries, or ``None`` when it may run.

    ``geometry_failed`` when a check refused the geometry, and
    ``geometry_unvalidated`` when the geometry has not been validated (a
    check that could not run, or a camera that has moved since). There is no
    third, weaker answer: anything short of an accepted geometry refuses
    every camera derivation outright.
    """

    if state.verdict.status == REFUSED:
        return GEOMETRY_FAILED
    if not state.validated or state.verdict.status != ACCEPTED:
        return GEOMETRY_UNVALIDATED
    return None
