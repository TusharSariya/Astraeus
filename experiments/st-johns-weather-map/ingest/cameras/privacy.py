"""Privacy masks over camera frames, and the claims this deployment refuses.

Two rules live here, and neither of them is a setting.

* **A frame is masked or it is discarded.** Every registered privacy region
  of a camera is filled with :data:`MASK_FILL` before the frame is stored and
  before it is served. :func:`apply_masks` is the only way a frame becomes
  storable, and it raises :class:`MaskUnavailable` rather than returning a
  partly-masked raster: an empty mask list, a polygon with fewer than three
  vertices, and a vertex outside the raster are all failures, because each
  one means the region that was meant to be hidden is not known to have been
  hidden. :func:`mask_or_discard` turns that failure into a discard: no
  raster comes back, a :class:`MaskFailure` naming
  :data:`PRIVACY_MASK_UNAVAILABLE` is recorded, and the instant is served as
  ``null`` naming that code. There is no store-then-mask path and no
  serve-unmasked path, because either one would put an unmasked frame where
  something could read it.

* **The named claims are refused outright.** :data:`REFUSED_CLAIMS` is the
  list of things this deployment does not say from a camera image: face and
  licence plate recognition, person and vessel tracking, military inference,
  "black ice detected", and camera-only safe-wave or safe-road claims. A
  camera admitted to see fog must not become a surveillance input, and a
  claim that a road or a wave is safe must not rest on an image alone,
  because the reader acts on it. :func:`refuse_claim` raises rather than
  returns: a refused claim is not a null value with a reason, it is a request
  that must not reach a computation. The refusal holds regardless of the
  camera's licence, of a reader asking for it, and of any derivation being
  enabled, so :func:`refuse_claim` accepts arbitrary context keywords such as
  ``licence`` or ``permission`` and refuses anyway, naming them in the
  detail.

The exception raised is :class:`ingest.cameras.derive.RefusedClaim`, the same
one the numeric-visibility refusal raises, imported rather than redefined so
that one ``except RefusedClaim`` catches every claim this deployment declines
and no caller has to know which module said no.

Dependency direction: pure ``dataclasses`` and ``typing`` plus that one
sibling import. ``ingest`` never imports ``api``.

Spec-Refs: openspec/changes/activity-profiles-sites-and-cameras/specs/camera-evidence/spec.md
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, NoReturn, Sequence

from ingest.cameras.derive import RefusedClaim

__all__ = [
    "MASK_FILL",
    "MINIMUM_VERTICES",
    "PRIVACY_MASK_UNAVAILABLE",
    "REFUSED_CLAIMS",
    "STANDING_PRIVACY_REFUSAL",
    "MaskFailure",
    "MaskRegion",
    "MaskUnavailable",
    "RefusedClaim",
    "apply_masks",
    "mask_or_discard",
    "refuse_claim",
]

#: The greyscale value a masked pixel takes. Flat black, not a blur and not a
#: pixelation: both of those keep some of the signal they were meant to
#: remove, and a mask that keeps signal is not a mask.
MASK_FILL = 0

#: A polygon needs three vertices to enclose anything at all.
MINIMUM_VERTICES = 3

#: The code carried by every field whose frame was discarded because its
#: privacy mask could not be applied.
PRIVACY_MASK_UNAVAILABLE = "privacy_mask_unavailable"

#: The rule broken by asking for any of :data:`REFUSED_CLAIMS`.
STANDING_PRIVACY_REFUSAL = "standing_privacy_refusal"

#: The claims this deployment does not make from a camera image, ever. This
#: tuple is the whole list: a name outside it is not silently allowed, it is
#: a :class:`ValueError` from :func:`refuse_claim`, so that a typo in a claim
#: name can never read as a permission.
REFUSED_CLAIMS = (
    "face_recognition",
    "licence_plate_recognition",
    "person_tracking",
    "vessel_tracking",
    "military_inference",
    "black_ice_detected",
    "safe_wave_camera_only",
    "safe_road_camera_only",
)


class MaskUnavailable(Exception):
    """The registered privacy masks cannot be applied to this frame.

    Raised, not returned, for the same reason the mask exists: a caller that
    ignored a return value would go on to store an unmasked frame.
    """


@dataclass(frozen=True)
class MaskRegion:
    """One registered privacy region, as a closed polygon of pixel vertices.

    The polygon is in image pixel coordinates, origin at the top left, and
    is implicitly closed: the last vertex joins the first.
    """

    name: str
    polygon: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class MaskFailure:
    """The record left behind by a frame that was discarded unmasked.

    ``code`` is always :data:`PRIVACY_MASK_UNAVAILABLE`; it is a field rather
    than a constant read at the call site so the record is self-describing
    wherever it is stored or logged.
    """

    camera_id: str
    detail: str
    code: str = PRIVACY_MASK_UNAVAILABLE


def _check_polygon(region: MaskRegion, width: int, height: int) -> None:
    """Refuse a region that does not enclose an area inside this raster."""
    polygon = tuple(region.polygon)
    if len(polygon) < MINIMUM_VERTICES:
        raise MaskUnavailable(
            f"privacy mask {region.name!r} has {len(polygon)} vertices; a mask polygon needs at least "
            f"{MINIMUM_VERTICES}. The frame is discarded rather than stored with the region unmasked."
        )
    for x, y in polygon:
        if not (0 <= x < width and 0 <= y < height):
            raise MaskUnavailable(
                f"privacy mask {region.name!r} has vertex ({x}, {y}) outside the {width}x{height} raster; "
                "the mask was registered against a different image size, so the region it names cannot be "
                "located in this frame. The frame is discarded rather than stored partly masked."
            )


def _on_segment(px: int, py: int, ax: int, ay: int, bx: int, by: int) -> bool:
    """Is the pixel exactly on the segment ``a``-``b``, endpoints included?

    Integer arithmetic throughout: the cross product is zero only for an
    exactly collinear point, so an edge pixel is never missed to rounding.
    """
    cross = (bx - ax) * (py - ay) - (by - ay) * (px - ax)
    if cross != 0:
        return False
    return min(ax, bx) <= px <= max(ax, bx) and min(ay, by) <= py <= max(ay, by)


def _contains(polygon: tuple[tuple[int, int], ...], px: int, py: int) -> bool:
    """Even-odd point-in-polygon test with edges counted as inside.

    The edge test comes first and is exact, so a pixel on the boundary is
    always masked; the ray cast then decides the interior. Masking is
    inclusive on purpose: a pixel the registered region touches is a pixel
    the region meant to hide.
    """
    count = len(polygon)
    inside = False
    for index in range(count):
        ax, ay = polygon[index]
        bx, by = polygon[(index + 1) % count]
        if _on_segment(px, py, ax, ay, bx, by):
            return True
        if (ay > py) != (by > py):
            # Horizontal ray to +x: does the edge cross it to the right?
            # Cross-multiplied to stay in integers, with the sign of the
            # vertical span folded in so the inequality keeps its direction.
            span = by - ay
            crossing = (bx - ax) * (py - ay) - (px - ax) * span
            if (crossing > 0) == (span > 0):
                inside = not inside
    return inside


def apply_masks(raster: Any, masks: Sequence[MaskRegion]) -> Any:
    """Fill every registered privacy region with :data:`MASK_FILL`.

    Returns a new raster of the same type; the input is never mutated, so a
    caller holding the unmasked frame cannot be confused about which one it
    has. Raises :class:`MaskUnavailable` when there are no masks at all, when
    a polygon has fewer than three vertices, or when any vertex lies outside
    the raster. Each of those is a region that cannot be shown to have been
    hidden, and a frame in that state is not storable.
    """
    regions = tuple(masks)
    if not regions:
        raise MaskUnavailable(
            "no privacy mask regions are registered for this frame; a frame with no mask is not a frame "
            "with nothing to hide, so it is discarded rather than stored unmasked."
        )
    width = raster.width
    height = raster.height
    for region in regions:
        _check_polygon(region, width, height)

    pixels = bytearray(raster.pixels)
    if len(pixels) != width * height:
        raise MaskUnavailable(
            f"raster carries {len(pixels)} bytes for a {width}x{height} greyscale image, which needs "
            f"{width * height}; the frame is discarded rather than masked against the wrong shape."
        )

    for region in regions:
        polygon = tuple(region.polygon)
        xs = [vertex[0] for vertex in polygon]
        ys = [vertex[1] for vertex in polygon]
        for y in range(min(ys), max(ys) + 1):
            row = y * width
            for x in range(min(xs), max(xs) + 1):
                if _contains(polygon, x, y):
                    pixels[row + x] = MASK_FILL

    return type(raster)(width, height, bytes(pixels))


def mask_or_discard(
    camera_id: str, raster: Any, masks: Sequence[MaskRegion]
) -> tuple[Any | None, MaskFailure | None]:
    """Mask a frame for storage and service, or discard it and say why.

    Exactly one half of the pair is ever set. On success the masked raster
    comes back with no failure; on any :class:`MaskUnavailable` the raster is
    ``None`` - the frame is discarded unstored, not held for a later retry -
    and a :class:`MaskFailure` naming :data:`PRIVACY_MASK_UNAVAILABLE` is
    returned for the caller to record, so the instant is served as ``null``
    naming that code.
    """
    try:
        masked = apply_masks(raster, masks)
    except MaskUnavailable as error:
        return None, MaskFailure(camera_id=camera_id, detail=str(error))
    return masked, None


def refuse_claim(name: str, **context: Any) -> NoReturn:
    """Always refuse one of :data:`REFUSED_CLAIMS`, naming the standing rule.

    ``context`` is accepted and reported, never consulted: a ``licence`` or
    ``permission`` keyword saying the claim is allowed changes nothing, which
    is the point of a standing refusal. A name outside :data:`REFUSED_CLAIMS`
    is a :class:`ValueError`, not a quiet success, so that a misspelt claim
    cannot slip past this gate as an unrecognised and therefore permitted
    one.
    """
    if name not in REFUSED_CLAIMS:
        raise ValueError(
            f"not a named refusal: {name!r}. This function refuses only the standing privacy refusals "
            f"{REFUSED_CLAIMS!r}; it is not the place to allow anything, so an unknown name is an error "
            "rather than a permission."
        )
    stated = (
        ", ".join(f"{key}={value!r}" for key, value in sorted(context.items()))
        if context
        else "none"
    )
    raise RefusedClaim(
        STANDING_PRIVACY_REFUSAL,
        (
            f"{name} is not a claim this deployment makes from a camera image. The refusal holds "
            "regardless of the camera's licence, of a reader requesting it, and of any camera derivation "
            f"being enabled. Context stated by the caller and not consulted: {stated}."
        ),
    )
