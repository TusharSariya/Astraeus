"""A frame is masked or discarded, and the named claims are always refused.

These tests pin both halves of the privacy rule. Masking fills exactly the
registered polygon and nothing else; a mask that cannot be applied discards
the frame rather than storing it partly masked; and every name in
``REFUSED_CLAIMS`` is refused whatever the caller says about licence or
permission, while a name outside the list is an error rather than a silent
allowance.

The raster is defined locally: ``privacy`` takes any object with ``width``,
``height`` and ``pixels`` and returns the same type, so these tests do not
wait on ``ingest.cameras.frames``.

Spec-Refs: openspec/changes/activity-profiles-sites-and-cameras/specs/camera-evidence/spec.md
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from ingest.cameras.derive import RefusedClaim
from ingest.cameras.privacy import (
    MASK_FILL,
    PRIVACY_MASK_UNAVAILABLE,
    REFUSED_CLAIMS,
    STANDING_PRIVACY_REFUSAL,
    MaskFailure,
    MaskRegion,
    MaskUnavailable,
    apply_masks,
    mask_or_discard,
    refuse_claim,
)

WIDTH = 8
HEIGHT = 6
BACKGROUND = 200


@dataclass(frozen=True)
class Raster:
    """A greyscale image: one byte per pixel, row-major."""

    width: int
    height: int
    pixels: bytes


def blank() -> Raster:
    return Raster(WIDTH, HEIGHT, bytes([BACKGROUND]) * (WIDTH * HEIGHT))


def filled_pixels(raster: Raster) -> set[tuple[int, int]]:
    """Every pixel carrying :data:`MASK_FILL`, as ``(x, y)``."""
    return {
        (index % raster.width, index // raster.width)
        for index, value in enumerate(raster.pixels)
        if value == MASK_FILL
    }


def test_a_rectangle_mask_fills_exactly_its_pixels() -> None:
    region = MaskRegion("window", ((1, 1), (4, 1), (4, 3), (1, 3)))
    masked = apply_masks(blank(), [region])

    expected = {(x, y) for x in range(1, 5) for y in range(1, 4)}
    assert filled_pixels(masked) == expected


def test_a_triangle_mask_fills_exactly_its_pixels_edges_included() -> None:
    region = MaskRegion("garden", ((0, 0), (4, 0), (0, 4)))
    masked = apply_masks(blank(), [region])

    expected = {
        (x, y) for x in range(0, 5) for y in range(0, 5) if x + y <= 4
    }
    assert filled_pixels(masked) == expected
    # The hypotenuse itself is inside: an edge pixel is a pixel the region
    # touches, and masking is inclusive on purpose.
    assert (2, 2) in expected


def test_pixels_outside_the_mask_are_untouched() -> None:
    raster = blank()
    masked = apply_masks(raster, [MaskRegion("window", ((1, 1), (4, 1), (4, 3), (1, 3)))])

    masked_set = filled_pixels(masked)
    for y in range(HEIGHT):
        for x in range(WIDTH):
            if (x, y) not in masked_set:
                assert masked.pixels[y * WIDTH + x] == BACKGROUND
    # The input raster is never mutated.
    assert raster.pixels == bytes([BACKGROUND]) * (WIDTH * HEIGHT)
    assert type(masked) is Raster


def test_two_regions_are_both_masked() -> None:
    regions = [
        MaskRegion("left", ((0, 0), (1, 0), (1, 1), (0, 1))),
        MaskRegion("right", ((6, 4), (7, 4), (7, 5), (6, 5))),
    ]
    masked = apply_masks(blank(), regions)

    assert filled_pixels(masked) == {(0, 0), (1, 0), (0, 1), (1, 1), (6, 4), (7, 4), (6, 5), (7, 5)}


def test_an_empty_mask_list_is_mask_unavailable() -> None:
    with pytest.raises(MaskUnavailable) as raised:
        apply_masks(blank(), [])
    assert "no privacy mask regions" in str(raised.value)


def test_a_vertex_outside_the_raster_is_mask_unavailable() -> None:
    outside = MaskRegion("wide", ((1, 1), (WIDTH, 1), (WIDTH, 3), (1, 3)))
    with pytest.raises(MaskUnavailable) as raised:
        apply_masks(blank(), [outside])
    assert "wide" in str(raised.value)
    assert f"{WIDTH}x{HEIGHT}" in str(raised.value)


def test_a_negative_vertex_is_mask_unavailable() -> None:
    with pytest.raises(MaskUnavailable):
        apply_masks(blank(), [MaskRegion("above", ((0, -1), (2, 0), (0, 2)))])


def test_a_polygon_with_two_vertices_is_mask_unavailable() -> None:
    with pytest.raises(MaskUnavailable) as raised:
        apply_masks(blank(), [MaskRegion("line", ((0, 0), (3, 3)))])
    assert "at least 3" in str(raised.value)


def test_mask_or_discard_returns_the_masked_frame_on_success() -> None:
    region = MaskRegion("window", ((1, 1), (4, 1), (4, 3), (1, 3)))
    masked, failure = mask_or_discard("ntv-sky", blank(), [region])

    assert failure is None
    assert masked is not None
    assert filled_pixels(masked) == {(x, y) for x in range(1, 5) for y in range(1, 4)}


@pytest.mark.parametrize(
    "masks",
    [
        pytest.param([], id="empty"),
        pytest.param([MaskRegion("line", ((0, 0), (3, 3)))], id="two_vertices"),
        pytest.param([MaskRegion("wide", ((1, 1), (99, 1), (99, 3)))], id="outside"),
    ],
)
def test_mask_or_discard_discards_and_records_the_failure(masks: list[MaskRegion]) -> None:
    masked, failure = mask_or_discard("ccg-harbour-1", blank(), masks)

    assert masked is None
    assert isinstance(failure, MaskFailure)
    assert failure.code == PRIVACY_MASK_UNAVAILABLE
    assert failure.camera_id == "ccg-harbour-1"
    assert failure.detail


def test_every_named_claim_is_refused() -> None:
    for name in REFUSED_CLAIMS:
        with pytest.raises(RefusedClaim) as raised:
            refuse_claim(name)
        assert raised.value.rule == STANDING_PRIVACY_REFUSAL
        assert name in raised.value.detail


@pytest.mark.parametrize("name", REFUSED_CLAIMS)
@pytest.mark.parametrize(
    "context",
    [
        {"licence": "permits face recognition"},
        {"permission": "granted by the operator"},
        {"licence": "open", "permission": "granted", "enabled": True},
    ],
)
def test_a_permissive_context_does_not_allow_a_refused_claim(
    name: str, context: dict[str, object]
) -> None:
    with pytest.raises(RefusedClaim) as raised:
        refuse_claim(name, **context)

    assert raised.value.rule == STANDING_PRIVACY_REFUSAL
    detail = raised.value.detail
    assert "regardless of the camera's licence" in detail
    for key in context:
        assert key in detail


def test_the_refused_list_is_the_eight_named_claims() -> None:
    assert REFUSED_CLAIMS == (
        "face_recognition",
        "licence_plate_recognition",
        "person_tracking",
        "vessel_tracking",
        "military_inference",
        "black_ice_detected",
        "safe_wave_camera_only",
        "safe_road_camera_only",
    )


@pytest.mark.parametrize(
    "name",
    ["fog_class", "face recognition", "FACE_RECOGNITION", "", "person_track"],
)
def test_a_name_outside_the_list_is_an_error_not_a_permission(name: str) -> None:
    with pytest.raises(ValueError) as raised:
        refuse_claim(name)
    assert "not a named refusal" in str(raised.value)
    # A ValueError, and specifically not the refusal exception: an unknown
    # name is a caller mistake, never a quiet allowance.
    assert not isinstance(raised.value, RefusedClaim)
