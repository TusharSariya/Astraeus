"""Frames are stored with computed health flags under the general window.

Health flags are computed from the pixels and the times, never handed in.
A flagged frame is served flagged and refuses every derivation, naming the
first raised flag. A duplicate does not advance the capture time. An instant
outside the retention window on a camera that has held frames is
``aged_out``, which is a different answer from ``null``, and no neighbouring
frame is ever served for a requested instant.

Spec-Refs: openspec/changes/activity-profiles-sites-and-cameras/specs/camera-evidence/spec.md
"""

from __future__ import annotations

import hashlib
import inspect
from datetime import datetime, timedelta, timezone

import pytest

from ingest.cameras import frames as frames_module
from ingest.cameras.frames import (
    AGED_OUT,
    CAPTURE_TIME_UNKNOWN,
    HEALTH_FLAGS,
    NULL,
    Frame,
    FrameAbsence,
    FrameStore,
    Raster,
    RasterError,
    compute_health_flags,
    derivation_refusal,
)

CAMERA = "signal-hill-harbour"
NOW = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)
WINDOW_START = NOW - timedelta(hours=24)
WINDOW_END = NOW + timedelta(days=14)

WIDTH = 32
HEIGHT = 32


def a_raster(fill) -> Raster:
    """A raster whose pixel at ``(x, y)`` is ``fill(x, y)``."""

    pixels = bytes(fill(x, y) for y in range(HEIGHT) for x in range(WIDTH))
    return Raster(WIDTH, HEIGHT, pixels)


def sharp() -> Raster:
    """A textured, well-exposed, well-lit scene: no flag is earned."""

    return a_raster(lambda x, y: 40 if x % 2 == 0 else 200)


def sharp_shifted() -> Raster:
    """The same scene one pixel to the side."""

    return a_raster(lambda x, y: 40 if x % 2 == 1 else 200)


def other_sharp() -> Raster:
    """A different textured scene, so it is not a duplicate of `sharp`."""

    return a_raster(lambda x, y: 50 if (x + y) % 2 == 0 else 210)


def soft() -> Raster:
    """A gentle ramp: too little gradient to be sharp, but still textured."""

    return a_raster(lambda x, y: 120 + (x % 16) * 2)


def dim() -> Raster:
    """Textured but far too dark."""

    return a_raster(lambda x, y: 2 if x % 2 == 0 else 20)


def clipped() -> Raster:
    """Every pixel pinned at one end of the range or the other."""

    return a_raster(lambda x, y: 0 if x % 2 == 0 else 255)


def covered() -> Raster:
    """A flat field: something is sitting over the whole lens."""

    return a_raster(lambda x, y: 120)


def patchy() -> Raster:
    """Half the frame smeared flat, half of it textured."""

    return a_raster(lambda x, y: 120 if x < WIDTH // 2 else (40 if x % 2 == 0 else 200))


@pytest.fixture()
def store(monkeypatch: pytest.MonkeyPatch) -> FrameStore:
    """A store on a fixed clock with a fixed window."""

    monkeypatch.setattr(frames_module, "window_bounds", lambda now: (WINDOW_START, WINDOW_END))
    return FrameStore(lambda: NOW)


def test_a_clean_frame_earns_no_health_flag(store: FrameStore) -> None:
    frame = store.put(
        CAMERA, sharp(), capture_time=NOW, retrieval_time=NOW + timedelta(seconds=4)
    )

    assert frame.flags == frozenset()
    assert derivation_refusal(frame) is None
    assert frame.sha256 == hashlib.sha256(sharp().pixels).hexdigest()
    assert frame.capture_time == NOW
    assert frame.retrieval_time == NOW + timedelta(seconds=4)


@pytest.mark.parametrize(
    ("raster", "expected"),
    [
        (soft(), "blur"),
        (dim(), "darkness"),
        (clipped(), "exposure"),
        (covered(), "obstruction"),
        (patchy(), "lens_water_or_snow"),
    ],
)
def test_each_health_flag_is_raised_by_its_own_defect(
    store: FrameStore, raster: Raster, expected: str
) -> None:
    frame = store.put(CAMERA, raster, capture_time=NOW, retrieval_time=NOW)

    assert expected in frame.flags
    assert expected in HEALTH_FLAGS


def test_camera_moved_health_flag_needs_a_reference_and_a_shift(store: FrameStore) -> None:
    """A one-pixel shift against the reference raises the flag; a match does not."""

    still = store.put(CAMERA, sharp(), capture_time=NOW, retrieval_time=NOW, reference=sharp())
    assert "camera_moved" not in still.flags

    moved = store.put(
        CAMERA,
        sharp_shifted(),
        capture_time=NOW + timedelta(minutes=5),
        retrieval_time=NOW + timedelta(minutes=5),
        reference=sharp(),
    )
    assert "camera_moved" in moved.flags


def test_health_flags_are_computed_and_never_accepted_from_the_caller(
    store: FrameStore,
) -> None:
    """`put` has no parameter by which a caller could assert a flag."""

    parameters = set(inspect.signature(FrameStore.put).parameters)
    assert "flags" not in parameters
    assert not any("flag" in name for name in parameters)

    # A defect the caller cannot talk the store out of.
    frame = store.put(CAMERA, covered(), capture_time=NOW, retrieval_time=NOW)
    assert "obstruction" in frame.flags

    # And a clean frame the caller cannot talk it into.
    clean = store.put(
        CAMERA, sharp(), capture_time=NOW + timedelta(minutes=10), retrieval_time=NOW
    )
    assert clean.flags == frozenset()


def test_a_flagged_frame_is_served_flagged_and_is_not_dropped(store: FrameStore) -> None:
    frame = store.put(CAMERA, soft(), capture_time=NOW, retrieval_time=NOW)

    served = store.frame_at(CAMERA, NOW)

    assert served is frame
    assert isinstance(served, Frame)
    assert "blur" in served.flags
    assert store.derivation_refusal(served) == "blur"


def test_a_byte_identical_duplicate_is_flagged_and_the_capture_time_stands(
    store: FrameStore,
) -> None:
    first = store.put(CAMERA, sharp(), capture_time=NOW, retrieval_time=NOW)
    second = store.put(
        CAMERA,
        sharp(),
        capture_time=NOW + timedelta(minutes=10),
        retrieval_time=NOW + timedelta(minutes=10),
    )

    assert first.flags == frozenset()
    assert "stale_or_duplicate" in second.flags
    assert second.sha256 == first.sha256
    # Stored, not dropped, and the previous capture time still stands.
    assert store.frames(CAMERA) == (first, second)
    assert store.last_capture_time(CAMERA) == NOW
    # The retrieval did happen, so it is the last successful one.
    assert store.last_retrieval(CAMERA) == NOW + timedelta(minutes=10)


def test_a_duplicate_capture_time_is_flagged_even_when_the_image_differs(
    store: FrameStore,
) -> None:
    """A capture time that has not advanced is stale however new the pixels are."""

    store.put(CAMERA, sharp(), capture_time=NOW, retrieval_time=NOW)
    repeat = store.put(
        CAMERA, other_sharp(), capture_time=NOW, retrieval_time=NOW + timedelta(minutes=5)
    )

    assert "stale_or_duplicate" in repeat.flags
    assert repeat.sha256 != hashlib.sha256(sharp().pixels).hexdigest()
    assert store.last_capture_time(CAMERA) == NOW


def test_a_frame_with_no_capture_time_is_flagged_and_never_serves_an_instant(
    store: FrameStore,
) -> None:
    frame = store.put(CAMERA, sharp(), capture_time=None, retrieval_time=NOW)

    assert CAPTURE_TIME_UNKNOWN in frame.flags
    assert derivation_refusal(frame) == CAPTURE_TIME_UNKNOWN
    assert store.frames(CAMERA) == (frame,)
    assert store.last_capture_time(CAMERA) is None

    # It is not served for the retrieval instant, nor for any other.
    for instant in (NOW, NOW - timedelta(minutes=1), NOW + timedelta(minutes=1)):
        absence = store.frame_at(CAMERA, instant)
        assert isinstance(absence, FrameAbsence)
        assert absence.state == NULL


def test_a_missing_instant_is_null_naming_the_camera_and_last_retrieval(
    store: FrameStore,
) -> None:
    retrieved_at = NOW - timedelta(minutes=7)
    store.put(CAMERA, sharp(), capture_time=NOW - timedelta(minutes=10), retrieval_time=retrieved_at)

    absence = store.frame_at(CAMERA, NOW - timedelta(minutes=5))

    assert isinstance(absence, FrameAbsence)
    assert absence.state == NULL
    assert absence.last_retrieval == retrieved_at
    assert CAMERA in absence.detail
    assert retrieved_at.isoformat() in absence.detail


def test_a_camera_that_never_retrieved_is_null_with_no_last_retrieval(
    store: FrameStore,
) -> None:
    absence = store.frame_at("fort-amherst", NOW)

    assert isinstance(absence, FrameAbsence)
    assert absence.state == NULL
    assert absence.last_retrieval is None
    assert "fort-amherst" in absence.detail
    assert "none" in absence.detail


def test_no_neighbouring_frame_is_served_for_a_requested_instant(store: FrameStore) -> None:
    """A frame a second either side answers for its own instant, not this one."""

    before = store.put(
        CAMERA, sharp(), capture_time=NOW - timedelta(seconds=1), retrieval_time=NOW
    )
    after = store.put(
        CAMERA, other_sharp(), capture_time=NOW + timedelta(seconds=1), retrieval_time=NOW
    )

    absence = store.frame_at(CAMERA, NOW)

    assert isinstance(absence, FrameAbsence)
    assert absence.state == NULL
    assert store.frame_at(CAMERA, before.capture_time) is before
    assert store.frame_at(CAMERA, after.capture_time) is after


def test_an_instant_outside_the_window_is_aged_out_not_null(store: FrameStore) -> None:
    store.put(CAMERA, sharp(), capture_time=NOW, retrieval_time=NOW)

    absence = store.frame_at(CAMERA, WINDOW_START - timedelta(hours=1))

    assert isinstance(absence, FrameAbsence)
    assert absence.state == AGED_OUT
    assert absence.state != NULL
    assert absence.last_retrieval == NOW
    assert CAMERA in absence.detail


def test_a_purged_frame_ages_out_and_the_last_retrieval_survives(store: FrameStore) -> None:
    stale_capture = WINDOW_START - timedelta(hours=2)
    store.put(CAMERA, sharp(), capture_time=stale_capture, retrieval_time=stale_capture)
    store.put(
        CAMERA,
        other_sharp(),
        capture_time=NOW - timedelta(minutes=30),
        retrieval_time=NOW - timedelta(minutes=30),
    )

    dropped = store.purge_outside_window()

    assert [frame.capture_time for frame in dropped] == [stale_capture]
    assert [frame.capture_time for frame in store.frames(CAMERA)] == [
        NOW - timedelta(minutes=30)
    ]
    absence = store.frame_at(CAMERA, stale_capture)
    assert isinstance(absence, FrameAbsence)
    assert absence.state == AGED_OUT
    assert absence.last_retrieval == NOW - timedelta(minutes=30)


def test_a_never_seen_camera_is_null_rather_than_aged_out(store: FrameStore) -> None:
    """`aged_out` is only for a camera that has actually held a frame."""

    absence = store.frame_at("cape-spear", WINDOW_START - timedelta(hours=3))

    assert isinstance(absence, FrameAbsence)
    assert absence.state == NULL


def test_derivation_refusal_names_the_first_raised_health_flag_in_order(
    store: FrameStore,
) -> None:
    """A covered lens raises blur and obstruction; blur comes first in order."""

    frame = store.put(CAMERA, covered(), capture_time=NOW, retrieval_time=NOW)

    assert {"blur", "obstruction"} <= frame.flags
    assert HEALTH_FLAGS.index("blur") < HEALTH_FLAGS.index("obstruction")
    assert derivation_refusal(frame) == "blur"


def test_a_duplicate_refuses_before_any_later_health_flag(store: FrameStore) -> None:
    store.put(CAMERA, covered(), capture_time=NOW, retrieval_time=NOW)
    repeat = store.put(
        CAMERA, covered(), capture_time=NOW + timedelta(minutes=5), retrieval_time=NOW
    )

    assert {"stale_or_duplicate", "blur", "obstruction"} <= repeat.flags
    assert derivation_refusal(repeat) == HEALTH_FLAGS[0] == "stale_or_duplicate"


def test_the_seven_health_flags_are_pinned_in_order() -> None:
    assert HEALTH_FLAGS == (
        "stale_or_duplicate",
        "blur",
        "darkness",
        "exposure",
        "obstruction",
        "lens_water_or_snow",
        "camera_moved",
    )
    assert CAPTURE_TIME_UNKNOWN not in HEALTH_FLAGS


def test_compute_health_flags_takes_no_flag_from_the_caller() -> None:
    parameters = set(inspect.signature(compute_health_flags).parameters)

    assert parameters == {"raster", "previous", "capture_time", "reference"}


def test_a_raster_must_match_its_declared_size() -> None:
    with pytest.raises(RasterError):
        Raster(4, 4, bytes(15))
    with pytest.raises(RasterError):
        Raster(0, 4, b"")

    assert len(Raster(4, 4, bytes(16)).pixels) == 16
