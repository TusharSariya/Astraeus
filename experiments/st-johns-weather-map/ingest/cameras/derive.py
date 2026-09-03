"""What a camera derivation may claim, and what it refuses outright.

Nothing in this module looks at an image. It is the gate in front of the
camera derivations, and it holds two rules that do not depend on any pixel:

* **No numeric visibility from an image.** A visibility in metres derived
  from a camera frame alone is refused by name, before any computation is
  reached, by :func:`request_numeric_visibility`. What a camera may say
  about visibility is a class, or an interval bounded by the farthest
  visible and the nearest invisible registered landmark, both named. A
  single number would be a measurement the camera never made.
* **Every camera method is awaiting validation.** All five camera entries
  are in the derivation method registry with ``enabled=False`` and stay
  there until a validation record comparing the method's output against
  CYYT METAR visibility and cloud over at least 30 days spanning day,
  night, fog, rain and snow is recorded with the entry and approved by the
  owner (wayfinder ticket 21). So :func:`derive` resolves the entry through
  the registry and, while it is disabled, returns ``value=None`` with
  :data:`AWAITING_VALIDATION` naming the method. The camera's frames and
  health flags are unaffected: they are retrieved evidence and are served
  whatever this gate says.

A method name the registry does not carry is ``unregistered_method``, never
a substitute or a near match.

Dependency direction: this reads ``ingest.derive.registry`` and nothing
else. ``ingest`` never imports ``api``.

Spec-Refs: openspec/changes/activity-profiles-sites-and-cameras/specs/camera-evidence/spec.md
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, NoReturn

from ingest.derive import registry as derive_registry
from ingest.derive.registry import CAMERA_METHODS

__all__ = [
    "AWAITING_VALIDATION",
    "CAMERA_METHODS",
    "CameraDerivation",
    "NUMERIC_VISIBILITY_REFUSED",
    "RefusedClaim",
    "UNREGISTERED_METHOD",
    "derive",
    "request_numeric_visibility",
]

#: The rule a request for a visibility in metres from an image breaks.
NUMERIC_VISIBILITY_REFUSED = "numeric_visibility_from_image_refused"

#: Why every camera-derived field is null today.
AWAITING_VALIDATION = "awaiting_validation"

#: A method name the derivation registry does not carry.
UNREGISTERED_METHOD = "unregistered_method"


class RefusedClaim(Exception):
    """A claim this deployment does not make from a camera image.

    Raised rather than returned: a refused claim is not a null value with a
    reason attached, it is a request that must not reach a computation at
    all. ``rule`` names the standing rule and ``detail`` says what was asked
    for.
    """

    def __init__(self, rule: str, detail: str) -> None:
        self.rule = rule
        self.detail = detail
        super().__init__(f"{rule}: {detail}")


def request_numeric_visibility(camera_id: str, frame_time: Any) -> NoReturn:
    """Always refuse: a camera image alone gives no visibility in metres.

    The camera may say which registered landmarks it can and cannot see, and
    that is an interval between two named distances. Turning that interval
    into a single number would state a precision the frame does not carry, so
    the request is refused here by name and no number is produced.
    """
    raise RefusedClaim(
        NUMERIC_VISIBILITY_REFUSED,
        (
            f"a visibility in metres was requested for camera {camera_id!r} at {frame_time}; a camera "
            f"image alone yields no numeric visibility. Ask for a visibility class, or for the bound "
            f"{derive_registry.CAMERA_VISIBILITY_BOUND!r}, which is an interval naming the farthest "
            "visible and the nearest invisible registered landmark."
        ),
    )


@dataclass(frozen=True, slots=True)
class CameraDerivation:
    """The result of asking a camera method for a value.

    ``value`` is ``None`` for as long as ``refusal`` is set, and today it is
    always ``None``: no camera method is enabled.
    """

    method: str
    value: float | str | None
    refusal: str | None
    detail: str

    @property
    def available(self) -> bool:
        return self.refusal is None


def derive(
    method: str,
    camera_id: str,
    frame_time: Any,
    *,
    reader_disabled: tuple[str, ...] = (),
) -> CameraDerivation:
    """Ask a camera method for a value, and be told why there is none.

    The registry is the authority: an unknown method is
    :data:`UNREGISTERED_METHOD`, and a registered method that is not enabled
    is :data:`AWAITING_VALIDATION` naming the method. Nothing here reads a
    frame; when the validation gate opens, the computation goes behind this
    function and the refusals stay in front of it.
    """
    entry = derive_registry.get(method)
    if entry is None:
        return CameraDerivation(
            method=method,
            value=None,
            refusal=UNREGISTERED_METHOD,
            detail=f"{method!r} is not a derivation method registry entry",
        )
    refusal = derive_registry.resolve(method, reader_disabled=reader_disabled)
    if refusal is not None and not entry.enabled:
        return CameraDerivation(
            method=method,
            value=None,
            refusal=AWAITING_VALIDATION,
            detail=(
                f"{method} is registered and disabled: {AWAITING_VALIDATION}. It is enabled only after a "
                "30-day CYYT METAR validation spanning day, night, fog, rain and snow is recorded with the "
                f"entry and approved by the owner. Camera {camera_id!r} still serves its frames and health "
                f"flags for {frame_time}."
            ),
        )
    if refusal is not None:
        return CameraDerivation(
            method=method, value=None, refusal=refusal.code, detail=refusal.detail
        )
    # Unreachable while every camera entry is disabled, and the registry
    # refuses to load one that is not. No camera value is computed here.
    return CameraDerivation(
        method=method,
        value=None,
        refusal=AWAITING_VALIDATION,
        detail=f"{method} has no implementation behind it yet; {AWAITING_VALIDATION}",
    )
