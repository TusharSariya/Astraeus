"""Camera frames as stored evidence, with computed health flags.

A frame is evidence about one instant: an image, the time it was captured,
the time it was retrieved, and the health flags the deployment computed for
it. This module holds all four together and refuses to let any of them be
asserted from outside.

Three rules shape everything below.

* **Health flags are computed, never accepted.** :func:`compute_health_flags`
  is the only producer of a flag set, and :meth:`FrameStore.put` calls it
  itself. There is no parameter by which a caller hands the store a flag it
  would like the frame to carry. A frame that arrives with a raised flag is
  stored flagged and served flagged: it is never silently dropped, because a
  dropped frame is indistinguishable from a camera that was never read.
* **Retention is the general retention rule.** The window comes from
  :func:`ingest.window.window_bounds`, which reads the one definition in
  ``api/weather_api/config.py``. Camera frames get no extension and no second
  copy of the offsets. Once an instant has left that window, the answer for
  it is :data:`AGED_OUT`, which is a different answer from ``null``.
* **A frame answers for its own instant only.** :meth:`FrameStore.frame_at`
  matches ``capture_time`` exactly. No neighbouring frame is served for a
  requested instant, however close it sits, and a frame whose capture time
  could not be established is never served for any instant at all: it carries
  :data:`CAPTURE_TIME_UNKNOWN` and stays out of every answer.

Every derivation that reads a frame is refused while any flag stands, and
the refusal names the flag: see :func:`derivation_refusal`.

Thresholds
----------

The seven health tests are deliberately simple statistics over a greyscale
:class:`Raster`. Every threshold is a named module constant and every one of
them is **provisional**: the numbers here are first guesses that stand until
the 30-day validation against CYYT METAR (wayfinder ticket 21) either
confirms them or replaces them. They are constants precisely so that the
validation has one place to correct, rather than a literal buried in a
comparison.

Dependency direction: ``math``, ``dataclasses``, ``hashlib``, ``statistics``
and :mod:`ingest.window`. No numpy, no Pillow, and ``ingest`` never imports
``api``.

Spec-Refs: openspec/changes/activity-profiles-sites-and-cameras/specs/camera-evidence/spec.md
"""

from __future__ import annotations

import hashlib
import statistics
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Literal

from ingest.window import window_bounds

__all__ = [
    "AGED_OUT",
    "BLOCK_GRID",
    "BLUR_MEAN_GRADIENT",
    "CAMERA_MOVED_IMPROVEMENT",
    "CAPTURE_TIME_UNKNOWN",
    "DARKNESS_MEAN_INTENSITY",
    "EXPOSURE_CLIPPED_FRACTION",
    "HEALTH_FLAGS",
    "LENS_WATER_MIN_BLOCK_FRACTION",
    "LOW_VARIANCE",
    "NULL",
    "OBSTRUCTION_BLOCK_FRACTION",
    "Frame",
    "FrameAbsence",
    "FrameStore",
    "Raster",
    "RasterError",
    "compute_health_flags",
    "derivation_refusal",
    "window_bounds",
]

#: The seven health flags, in the order a refusal reports them. The order is
#: part of the interface: :func:`derivation_refusal` names the first raised
#: flag in this order, so a frame that is both stale and blurred refuses as
#: ``stale_or_duplicate`` every time rather than by set iteration order.
HEALTH_FLAGS = (
    "stale_or_duplicate",
    "blur",
    "darkness",
    "exposure",
    "obstruction",
    "lens_water_or_snow",
    "camera_moved",
)

#: A frame whose capture time could not be established. Not one of the seven
#: health flags - it is a statement about the record rather than the image -
#: but it refuses every derivation just as they do, and it keeps the frame
#: out of every answer about an instant.
CAPTURE_TIME_UNKNOWN = "capture_time_unknown"

#: The two absence states this module can return. ``blocked`` is a different
#: matter, decided before a frame is ever retrieved, and is not one of these.
NULL = "null"
AGED_OUT = "aged_out"

#: Mean absolute horizontal gradient, in intensity levels per pixel, below
#: which a frame is called blurred. Provisional: a first guess pending the
#: 30-day validation.
BLUR_MEAN_GRADIENT = 8.0

#: Mean intensity below which a frame is called dark. Provisional: a first
#: guess pending the 30-day validation. Darkness is a health flag about the
#: image; whether the sun was down is :mod:`ingest.cameras.night`'s question.
DARKNESS_MEAN_INTENSITY = 24.0

#: Fraction of pixels sitting at 0 or 255 above which a frame is called
#: badly exposed. Provisional: a first guess pending the 30-day validation.
EXPOSURE_CLIPPED_FRACTION = 0.15

#: The frame is divided into a ``BLOCK_GRID`` by ``BLOCK_GRID`` grid of
#: blocks for the obstruction and lens-water tests. Provisional.
BLOCK_GRID = 8

#: Population variance below which a block counts as near-uniform.
#: Provisional: a first guess pending the 30-day validation.
LOW_VARIANCE = 25.0

#: Fraction of near-uniform blocks at or above which the frame is called
#: obstructed: something large and flat is sitting in front of the lens.
#: Provisional.
OBSTRUCTION_BLOCK_FRACTION = 0.7

#: Fraction of near-uniform blocks at or above which a frame that is *not*
#: obstructed is called patchy, which is what water or snow on the lens looks
#: like: several flat smears over a scene that is otherwise textured.
#:
#: This is a first heuristic and is explicitly provisional. Patchiness alone
#: does not distinguish drops on the glass from fog banks or from a partly
#: snow-covered scene, and the 30-day validation against CYYT METAR is what
#: will say whether this test earns its place, gets a different threshold, or
#: is replaced. Until then the flag is raised generously: a false raise
#: refuses a derivation, which is the safe direction.
LENS_WATER_MIN_BLOCK_FRACTION = 0.25

#: How much better a one-pixel horizontal shift must fit the reference before
#: the camera is called moved: the shifted mean absolute difference must be
#: below this multiple of the unshifted one. Provisional.
#:
#: This is the crudest possible motion test - a single-pixel shift in one
#: axis - and it is documented as such. It catches the mount that has been
#: knocked, which is what the geometry re-validation needs to hear about; it
#: says nothing about rotation, zoom or a larger displacement, and a camera
#: that has moved further will usually raise it anyway because neither
#: alignment fits.
CAMERA_MOVED_IMPROVEMENT = 0.8


class RasterError(ValueError):
    """The pixel buffer does not match the declared image size."""


@dataclass(frozen=True)
class Raster:
    """A greyscale image: one byte per pixel, row-major, no colour, no alpha.

    This is the whole image abstraction the camera modules have. It is not a
    decoder: something upstream turns whatever the camera served into these
    bytes, and this package never learns the wire format.
    """

    width: int
    height: int
    pixels: bytes

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise RasterError(f"raster size must be positive: {self.width}x{self.height}")
        expected = self.width * self.height
        if len(self.pixels) != expected:
            raise RasterError(
                f"raster is {self.width}x{self.height} = {expected} bytes "
                f"but carries {len(self.pixels)}"
            )

    def row(self, index: int) -> bytes:
        """One row of pixels."""

        start = index * self.width
        return self.pixels[start : start + self.width]


@dataclass(frozen=True)
class Frame:
    """One retrieved image with its times and its computed flags.

    ``capture_time`` is ``None`` when the camera did not say when it took the
    image and nothing else could establish it; such a frame carries
    :data:`CAPTURE_TIME_UNKNOWN` and is never served for an instant.
    """

    camera_id: str
    sha256: str
    capture_time: datetime | None
    retrieval_time: datetime
    raster: Raster
    flags: frozenset[str]


@dataclass(frozen=True)
class FrameAbsence:
    """Why there is no frame for a requested instant.

    ``state`` is ``"null"`` when nothing was retrieved for that instant and
    ``"aged_out"`` when the instant has left the retention window on a camera
    that has held frames. ``detail`` names the camera and the last successful
    retrieval, so a reader can tell a silent camera from a purged one.
    """

    state: Literal["null", "aged_out"]
    detail: str
    last_retrieval: datetime | None


def _mean_absolute_horizontal_gradient(raster: Raster) -> float:
    """Mean ``|p[x + 1] - p[x]|`` over every adjacent pair within a row."""

    if raster.width < 2:
        return 0.0
    total = 0
    count = 0
    for y in range(raster.height):
        row = raster.row(y)
        for x in range(raster.width - 1):
            total += abs(row[x + 1] - row[x])
            count += 1
    return total / count if count else 0.0


def _block_variances(raster: Raster) -> list[float]:
    """Population variance of each block of a ``BLOCK_GRID`` square grid.

    The grid is clipped to the image where the image is smaller than the
    grid, so a tiny raster yields fewer, larger blocks rather than empty ones.
    """

    columns = min(BLOCK_GRID, raster.width)
    rows = min(BLOCK_GRID, raster.height)
    variances: list[float] = []
    for block_y in range(rows):
        y_start = block_y * raster.height // rows
        y_end = (block_y + 1) * raster.height // rows
        for block_x in range(columns):
            x_start = block_x * raster.width // columns
            x_end = (block_x + 1) * raster.width // columns
            values: list[int] = []
            for y in range(y_start, y_end):
                values.extend(raster.row(y)[x_start:x_end])
            if len(values) < 2:
                variances.append(0.0)
            else:
                variances.append(statistics.pvariance(values))
    return variances


def _mean_absolute_difference(left: bytes, right: bytes) -> float:
    if not left:
        return 0.0
    return sum(abs(a - b) for a, b in zip(left, right)) / len(left)


def _shifted_fits_better(raster: Raster, reference: Raster) -> bool:
    """Whether a one-pixel horizontal shift fits the reference better.

    Rasters of different sizes are taken as moved outright: the framing has
    changed by more than this test was built to measure.
    """

    if raster.width != reference.width or raster.height != reference.height:
        return True
    if raster.width < 3:
        return False

    unshifted: list[int] = []
    left_shift: list[int] = []
    right_shift: list[int] = []
    reference_interior: list[int] = []
    for y in range(raster.height):
        row = raster.row(y)
        ref = reference.row(y)
        # Compare over the interior columns only, so all three alignments
        # cover exactly the same reference pixels.
        reference_interior.extend(ref[1:-1])
        unshifted.extend(row[1:-1])
        left_shift.extend(row[2:])
        right_shift.extend(row[:-2])

    reference_bytes = bytes(reference_interior)
    straight = _mean_absolute_difference(bytes(unshifted), reference_bytes)
    if straight == 0.0:
        return False
    best_shift = min(
        _mean_absolute_difference(bytes(left_shift), reference_bytes),
        _mean_absolute_difference(bytes(right_shift), reference_bytes),
    )
    return best_shift < straight * CAMERA_MOVED_IMPROVEMENT


def compute_health_flags(
    raster: Raster,
    *,
    previous: Frame | None,
    capture_time: datetime | None,
    reference: Raster | None = None,
) -> frozenset[str]:
    """The flags this frame earns, computed from the pixels and the times.

    This is the only producer of a flag set. Nothing in the signature lets a
    caller assert a flag: ``previous`` and ``reference`` are evidence the
    tests read, not verdicts.

    * ``stale_or_duplicate`` when the image hashes to the previous frame's
      digest, or the capture time has not advanced past the previous frame's.
      An unknown capture time cannot advance past a known one, so a frame
      with no capture time behind a frame that had one is stale as well as
      :data:`CAPTURE_TIME_UNKNOWN`.
    * ``blur`` when the mean absolute horizontal gradient is below
      :data:`BLUR_MEAN_GRADIENT`.
    * ``darkness`` when the mean intensity is below
      :data:`DARKNESS_MEAN_INTENSITY`.
    * ``exposure`` when the fraction of pixels at 0 or 255 exceeds
      :data:`EXPOSURE_CLIPPED_FRACTION`.
    * ``obstruction`` when at least :data:`OBSTRUCTION_BLOCK_FRACTION` of the
      blocks are near-uniform.
    * ``lens_water_or_snow`` when at least
      :data:`LENS_WATER_MIN_BLOCK_FRACTION` of the blocks are near-uniform
      but the frame is not obstructed - a patchy rather than a covered lens.
    * ``camera_moved`` when a ``reference`` raster is given and a one-pixel
      horizontal shift fits it better than no shift at all.

    :data:`CAPTURE_TIME_UNKNOWN` is included when ``capture_time`` is
    ``None``.
    """

    flags: set[str] = set()
    digest = hashlib.sha256(raster.pixels).hexdigest()

    if previous is not None:
        if digest == previous.sha256:
            flags.add("stale_or_duplicate")
        elif capture_time is None:
            if previous.capture_time is not None:
                flags.add("stale_or_duplicate")
        elif previous.capture_time is not None and capture_time <= previous.capture_time:
            flags.add("stale_or_duplicate")

    if _mean_absolute_horizontal_gradient(raster) < BLUR_MEAN_GRADIENT:
        flags.add("blur")

    if statistics.fmean(raster.pixels) < DARKNESS_MEAN_INTENSITY:
        flags.add("darkness")

    clipped = sum(1 for value in raster.pixels if value == 0 or value == 255)
    if clipped / len(raster.pixels) > EXPOSURE_CLIPPED_FRACTION:
        flags.add("exposure")

    variances = _block_variances(raster)
    if variances:
        low = sum(1 for variance in variances if variance < LOW_VARIANCE) / len(variances)
        if low >= OBSTRUCTION_BLOCK_FRACTION:
            flags.add("obstruction")
        elif low >= LENS_WATER_MIN_BLOCK_FRACTION:
            flags.add("lens_water_or_snow")

    if reference is not None and _shifted_fits_better(raster, reference):
        flags.add("camera_moved")

    if capture_time is None:
        flags.add(CAPTURE_TIME_UNKNOWN)

    return frozenset(flags)


def derivation_refusal(frame: Frame) -> str | None:
    """The refusal a derivation over this frame carries, or ``None``.

    The first raised flag in :data:`HEALTH_FLAGS` order, then
    :data:`CAPTURE_TIME_UNKNOWN`, then ``None`` when the frame is clean. A
    refused derivation returns ``null`` naming this string; the frame itself
    is still served, flags and all.
    """

    for flag in HEALTH_FLAGS:
        if flag in frame.flags:
            return flag
    if CAPTURE_TIME_UNKNOWN in frame.flags:
        return CAPTURE_TIME_UNKNOWN
    return None


class FrameStore:
    """Frames held in memory under the general retention rule.

    ``now`` is the clock the window is taken against, injected so that a test
    fixes the window rather than the wall clock. The store keeps, per camera,
    the frames themselves, the last capture time that counted as a new
    observation, the last successful retrieval time, and whether the camera
    has ever held a frame at all - the last of which survives a purge, so a
    purged camera answers ``aged_out`` rather than pretending it was never
    read.
    """

    def __init__(self, now: Callable[[], datetime]) -> None:
        self._now = now
        self._frames: dict[str, list[Frame]] = {}
        self._last_capture: dict[str, datetime] = {}
        self._last_retrieval: dict[str, datetime] = {}
        self._ever_held: set[str] = set()

    def put(
        self,
        camera_id: str,
        raster: Raster,
        *,
        capture_time: datetime | None,
        retrieval_time: datetime,
        reference: Raster | None = None,
    ) -> Frame:
        """Store one retrieved frame, computing its digest and its flags.

        The flags are computed here against the camera's own previous frame.
        A duplicate is stored, flagged ``stale_or_duplicate``, and does not
        advance the camera's last capture time: it is not a new observation,
        and the previous capture time stands.
        """

        previous = self._previous(camera_id)
        flags = compute_health_flags(
            raster,
            previous=previous,
            capture_time=capture_time,
            reference=reference,
        )
        frame = Frame(
            camera_id=camera_id,
            sha256=hashlib.sha256(raster.pixels).hexdigest(),
            capture_time=capture_time,
            retrieval_time=retrieval_time,
            raster=raster,
            flags=flags,
        )
        self._frames.setdefault(camera_id, []).append(frame)
        self._ever_held.add(camera_id)
        self._last_retrieval[camera_id] = retrieval_time
        if capture_time is not None and "stale_or_duplicate" not in flags:
            self._last_capture[camera_id] = capture_time
        return frame

    def _previous(self, camera_id: str) -> Frame | None:
        held = self._frames.get(camera_id)
        return held[-1] if held else None

    def last_capture_time(self, camera_id: str) -> datetime | None:
        """The last capture time that counted as a new observation."""

        return self._last_capture.get(camera_id)

    def last_retrieval(self, camera_id: str) -> datetime | None:
        """The last successful retrieval, whatever became of its frame."""

        return self._last_retrieval.get(camera_id)

    def frames(self, camera_id: str) -> tuple[Frame, ...]:
        """Every frame still held for a camera, oldest first."""

        return tuple(self._frames.get(camera_id, ()))

    def frame_at(self, camera_id: str, instant: datetime) -> Frame | FrameAbsence:
        """The frame captured at exactly ``instant``, or why there is none.

        No neighbouring frame is served: a frame captured a second either
        side of ``instant`` is a frame about a different instant. A frame
        with no capture time is never served for any instant.
        """

        for frame in self._frames.get(camera_id, ()):
            if frame.capture_time is not None and frame.capture_time == instant:
                return frame

        last = self._last_retrieval.get(camera_id)
        start, end = window_bounds(self._now())
        if (instant < start or instant > end) and camera_id in self._ever_held:
            return FrameAbsence(
                state=AGED_OUT,
                detail=(
                    f"camera {camera_id}: {instant.isoformat()} is outside the retention "
                    f"window {start.isoformat()} to {end.isoformat()}; "
                    f"last successful retrieval {_stamp(last)}"
                ),
                last_retrieval=last,
            )
        return FrameAbsence(
            state=NULL,
            detail=(
                f"camera {camera_id}: no frame captured at {instant.isoformat()}; "
                f"last successful retrieval {_stamp(last)}"
            ),
            last_retrieval=last,
        )

    def purge_outside_window(self) -> tuple[Frame, ...]:
        """Drop every frame whose capture time has left the window.

        Retention is the general retention rule and is not extended for
        camera frames. A frame with no capture time is aged on its retrieval
        time instead, since that is the only time it has. The last successful
        retrieval is recorded per camera and survives the purge, so a camera
        whose frames have all aged out can still say when it was last read.
        """

        start, end = window_bounds(self._now())
        dropped: list[Frame] = []
        for camera_id, held in self._frames.items():
            kept: list[Frame] = []
            for frame in held:
                moment = frame.capture_time or frame.retrieval_time
                if start <= moment <= end:
                    kept.append(frame)
                else:
                    dropped.append(frame)
            self._frames[camera_id] = kept
            # The last successful retrieval is a fact about the camera, not
            # about a frame, so it is untouched by the purge and stays
            # available to name in a later absence.
        return tuple(dropped)

    def derivation_refusal(self, frame: Frame) -> str | None:
        """The refusal a derivation over ``frame`` carries, or ``None``."""

        return derivation_refusal(frame)


def _stamp(moment: datetime | None) -> str:
    return moment.isoformat() if moment is not None else "none"
