#!/usr/bin/env python3
"""Load, validate and audit the camera registration records.

A camera is usable only through a complete registration record. This module
reads one YAML file per camera from ``registry/cameras``, validates each
against ``registry/cameras/schema.json``, and reports every element nobody has
registered by its dotted path. Nothing here fetches a frame or promotes a
status: an audit says what a record carries and what it lacks, and
``retrieval_allowed`` refuses every camera this change catalogues.

Run it as a script from ``experiments/st-johns-weather-map``::

    python3 registry/camera_audit.py --all

or import it beside the rest of the registry::

    from registry import camera_audit
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Mapping

import jsonschema
import yaml

if __package__ in (None, ""):  # pragma: no cover - exercised by the CLI only
    # Run as a script the module has no package, so ``registry`` is not
    # importable by name. Put the experiment root on the path, the same shape
    # the API and the api tests use.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

HERE = Path(__file__).resolve().parent

#: Where the per-camera YAML records live, one file per camera.
CAMERAS_ROOT = HERE / "cameras"

#: The record schema, read once and reused across every file in a run.
SCHEMA_PATH = CAMERAS_ROOT / "schema.json"

#: A complete record needs at least this many horizon landmarks: a single
#: landmark fixes no orientation, and the visibility bound named in the camera
#: evidence spec is an interval between two of them.
MINIMUM_LANDMARKS = 2

#: The refusal codes ``retrieval_allowed`` may return.
REFUSAL_PARTNERSHIP_ONLY = "partnership_only"
REFUSAL_REGISTRATION_INCOMPLETE = "registration_incomplete"

#: Printed when the registry holds no camera at all. The catalogue is empty
#: with a notice rather than silently absent.
EMPTY_NOTICE = "no camera is registered: the camera catalogue is empty and every camera-derived field is null"


class CameraError(Exception):
    """A record that could not be read, parsed or validated.

    Carried rather than raised out of :func:`load_cameras` so that one
    malformed file is reported without hiding the records beside it.
    """

    def __init__(self, camera_id: str, path: Path, detail: str) -> None:
        super().__init__(f"{camera_id} ({path.name}): {detail}")
        self.camera_id = camera_id
        self.path = path
        self.detail = detail

    def __str__(self) -> str:
        return f"{self.camera_id} ({self.path.name}): {self.detail}"


@dataclass(frozen=True)
class Camera:
    """A parsed, schema-valid camera record and the file it came from."""

    record: Mapping[str, Any]
    path: Path

    @property
    def camera_id(self) -> str:
        return str(self.record["id"])

    @property
    def status(self) -> str:
        return str(self.record["status"])

    @property
    def terms_text(self) -> str:
        return str(self.record["terms"]["text"])


@dataclass(frozen=True)
class CameraVerdict:
    """What a record carries and what nobody has registered yet."""

    status: Literal["complete", "incomplete"]
    missing: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Refusal:
    """A refused retrieval, naming the camera and the reason in the reader's words."""

    code: str
    camera_id: str
    detail: str


def _schema() -> Mapping[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def load_camera(path: Path) -> Camera:
    """Read one record, or raise :class:`CameraError` naming what is wrong."""

    path = Path(path)
    stem = path.stem
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CameraError(stem, path, f"unreadable: {exc}") from exc
    try:
        record = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise CameraError(stem, path, f"not valid YAML: {exc}") from exc
    if not isinstance(record, Mapping):
        raise CameraError(stem, path, f"expected a mapping at the top level, found {type(record).__name__}")
    try:
        jsonschema.validate(instance=dict(record), schema=_schema())
    except jsonschema.ValidationError as exc:
        where = ".".join(str(part) for part in exc.absolute_path) or "<root>"
        raise CameraError(stem, path, f"schema violation at {where}: {exc.message}") from exc
    if record["id"] != stem:
        raise CameraError(stem, path, f"id {record['id']!r} does not match the file stem {stem!r}")
    return Camera(record=dict(record), path=path)


def load_cameras(root: Path = CAMERAS_ROOT) -> dict[str, Camera | CameraError]:
    """Read every record under ``root``, keyed by file stem.

    A malformed record becomes a :class:`CameraError` value rather than an
    exception, so one bad file never hides the rest. An absent or empty
    directory yields an empty mapping; the notice belongs to the caller.
    """

    root = Path(root)
    if not root.is_dir():
        return {}
    loaded: dict[str, Camera | CameraError] = {}
    for path in sorted(root.glob("*.yaml")):
        try:
            loaded[path.stem] = load_camera(path)
        except CameraError as exc:
            loaded[path.stem] = exc
    return loaded


def _missing_elements(record: Mapping[str, Any]) -> list[str]:
    missing: list[str] = []

    def absent(dotted: str, value: Any) -> None:
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(dotted)

    endpoint = record["endpoint"]
    absent("endpoint.cadence_seconds", endpoint["cadence_seconds"])
    absent("endpoint.cadence_measured_on", endpoint["cadence_measured_on"])

    position = record["position"]
    absent("position.latitude", position["latitude"])
    absent("position.longitude", position["longitude"])
    absent("position.elevation.metres", position["elevation"]["metres"])
    absent("position.elevation.datum", position["elevation"]["datum"])

    orientation = record["orientation"]
    for key in ("bearing_deg", "hfov_deg", "vfov_deg", "roll_deg"):
        absent(f"orientation.{key}", orientation[key])

    image = record["image"]
    absent("image.width_px", image["width_px"])
    absent("image.height_px", image["height_px"])

    landmarks = record["landmarks"]
    if len(landmarks) < MINIMUM_LANDMARKS:
        missing.append("landmarks")
    for index, landmark in enumerate(landmarks):
        absent(f"landmarks[{index}].bearing_deg", landmark["bearing_deg"])
        absent(f"landmarks[{index}].distance_m", landmark["distance_m"])
        pixel = landmark["pixel"]
        if pixel is None:
            missing.append(f"landmarks[{index}].pixel")
        else:
            absent(f"landmarks[{index}].pixel.x", pixel["x"])
            absent(f"landmarks[{index}].pixel.y", pixel["y"])

    if not record["privacy_masks"]:
        missing.append("privacy_masks")

    registered = record["registered"]
    absent("registered.date", registered["date"])
    absent("registered.by", registered["by"])

    validation = record["geometry_validation"]
    absent("geometry_validation.dem", validation["dem"])
    if validation["status"] != "passed":
        missing.append("geometry_validation.status")

    return missing


def audit_camera(camera: Camera) -> CameraVerdict:
    """Name every element of the registration nobody has registered.

    The record has already passed the schema by the time it is a
    :class:`Camera`, so ``errors`` stays empty here for anything the schema can
    state. It carries the checks the schema cannot: a record that claims a
    surveyed position without one, and a status the terms do not support.
    """

    record = camera.record
    errors: list[str] = []

    position = record["position"]
    if record["position"]["surveyed"] and (position["latitude"] is None or position["longitude"] is None):
        errors.append(f"{camera.camera_id}: position.surveyed is true but the position is not registered")
    permission = record["terms"]["permission"]
    if record["status"] != "partnership-only" and permission["granted_on"] is None:
        errors.append(
            f"{camera.camera_id}: status {record['status']!r} without a recorded permission; "
            "a camera stays partnership-only until terms.permission.granted_on and .document are set"
        )

    missing = _missing_elements(record)
    status: Literal["complete", "incomplete"] = "complete" if not missing and not errors else "incomplete"
    return CameraVerdict(status=status, missing=missing, errors=errors)


def retrieval_allowed(camera: Camera) -> Refusal | None:
    """Refuse retrieval, or return ``None`` when nothing stands in the way.

    Nothing in this change returns ``None``: every catalogued camera is
    ``partnership-only``, so every camera is refused with its own terms quoted
    back. The incomplete-registration refusal stands behind it for the day a
    permission arrives.
    """

    if camera.status == "partnership-only":
        return Refusal(
            code=REFUSAL_PARTNERSHIP_ONLY,
            camera_id=camera.camera_id,
            detail=(
                f"{camera.camera_id} ({camera.record['name']}) is partnership-only: no frame is fetched "
                f"or stored. Operator {camera.record['operator']} states: \"{camera.terms_text}\""
            ),
        )
    verdict = audit_camera(camera)
    if verdict.status == "incomplete":
        named = ", ".join(verdict.missing + verdict.errors)
        return Refusal(
            code=REFUSAL_REGISTRATION_INCOMPLETE,
            camera_id=camera.camera_id,
            detail=f"{camera.camera_id} has an incomplete registration record; missing: {named}",
        )
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit the camera registration records.")
    parser.add_argument("--all", action="store_true", help="report every record, complete and incomplete")
    parser.add_argument("--strict", action="store_true", help="exit non-zero when any record is incomplete")
    parser.add_argument("--root", type=Path, default=CAMERAS_ROOT, help="the directory of camera records to read")
    args = parser.parse_args(argv)

    cameras = load_cameras(args.root)
    if not cameras:
        print(EMPTY_NOTICE)
        return 0

    failures = 0
    incomplete = 0
    for camera_id in sorted(cameras):
        entry = cameras[camera_id]
        if isinstance(entry, CameraError):
            failures += 1
            print(f"ERROR: {entry}", file=sys.stderr)
            continue
        verdict = audit_camera(entry)
        if verdict.status == "incomplete":
            incomplete += 1
        for error in verdict.errors:
            print(f"ERROR: {error}", file=sys.stderr)
        if verdict.status == "incomplete" or args.all:
            named = ", ".join(verdict.missing) if verdict.missing else "nothing"
            print(f"{camera_id}: {verdict.status}; missing: {named}")
        refusal = retrieval_allowed(entry)
        if refusal is not None and args.all:
            print(f"{camera_id}: retrieval refused ({refusal.code}): {refusal.detail}")

    print(
        f"cameras: {len(cameras)} records, {incomplete} incomplete, {failures} unreadable; "
        "none admitted, none retrieved"
    )
    if failures:
        return 1
    if args.strict and incomplete:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
