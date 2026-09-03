#!/usr/bin/env python3
"""Load, validate and audit the site registration records.

A site is a preferred location, never an allowlist: nothing here restricts
where evidence is served. What a site adds is a hand-registered directional
horizon, which no source publishes at the resolution this deployment needs and
which terrain data cannot supply because buildings, trees and harbour
structures are absent from it.

This module reads one YAML file per site from ``registry/sites``, validates
each against ``registry/sites/schema.json``, and reports what the schema
cannot state: that the horizon holds exactly ``360 / bearing_resolution_deg``
values with no gap, that a terrain check which claims to have run carries the
model and the angles it ran against, and that no registered angle sits below
the terrain horizon beyond the declared tolerance. The terrain horizon is a
check on the registration; it is never substituted for it.

Run it as a script from ``experiments/st-johns-weather-map``::

    python3 registry/site_audit.py --all

or import it beside the rest of the registry::

    from registry import site_audit
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import jsonschema
import yaml

if __package__ in (None, ""):  # pragma: no cover - exercised by the CLI only
    # Run as a script the module has no package, so ``registry`` is not
    # importable by name. Put the experiment root on the path, the same shape
    # the API and the api tests use.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

HERE = Path(__file__).resolve().parent

#: Where the per-site YAML records live, one file per site.
SITES_ROOT = HERE / "sites"

#: The record schema, read once and reused across every file in a run.
SCHEMA_PATH = SITES_ROOT / "schema.json"

#: Error code prefixes. They are string prefixes rather than an enum because
#: they travel into field quality flags and into the audit output unchanged.
HORIZON_MISSING = "site_horizon_missing"
HORIZON_GAP = "site_horizon_gap"
BELOW_TERRAIN = "below_terrain"
TERRAIN_CHECK_INCOMPLETE = "terrain_check_incomplete"

#: Printed when the registry holds no site at all. An empty registry is a
#: notice, not a failure: field service at arbitrary points is unaffected.
EMPTY_NOTICE = (
    "no site is registered: the site list is empty and every horizon-dependent field is null; "
    "field service at arbitrary points inside the evidence box is unaffected"
)

#: Printed when the registry directory itself cannot be read.
MISSING_ROOT_NOTICE = (
    "the site registry directory {root} cannot be read: the site list is empty; "
    "field service at arbitrary points inside the evidence box is unaffected"
)


class SiteError(Exception):
    """A record that could not be read, parsed or validated.

    Carried rather than raised out of :func:`load_sites` so that one malformed
    file is reported without hiding the records beside it.
    """

    def __init__(self, site_id_or_stem: str, path: Path, detail: str) -> None:
        super().__init__(f"{site_id_or_stem} ({path.name}): {detail}")
        self.site_id = site_id_or_stem
        self.path = path
        self.detail = detail

    def __str__(self) -> str:
        return f"{self.site_id} ({self.path.name}): {self.detail}"


@dataclass(frozen=True)
class Site:
    """A parsed, schema-valid site record and the file it came from."""

    record: Mapping[str, Any]
    path: Path

    @property
    def site_id(self) -> str:
        return str(self.record["id"])

    @property
    def name(self) -> str:
        return str(self.record["name"])

    @property
    def bearing_resolution_deg(self) -> float:
        return float(self.record["horizon"]["bearing_resolution_deg"])

    @property
    def elevation_deg(self) -> list[Any]:
        return list(self.record["horizon"]["elevation_deg"])


def load_schema(path: Path | None = None) -> Mapping[str, Any]:
    """Read the record schema."""

    return json.loads(Path(path or SCHEMA_PATH).read_text(encoding="utf-8"))


def load_site(path: Path | str, *, schema: Mapping[str, Any] | None = None) -> Site:
    """Read one record, or raise :class:`SiteError` naming what is wrong."""

    path = Path(path)
    stem = path.stem
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SiteError(stem, path, f"unreadable: {exc}") from exc
    try:
        record = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise SiteError(stem, path, f"not valid YAML: {exc}") from exc
    if not isinstance(record, Mapping):
        raise SiteError(stem, path, f"expected a mapping at the top level, found {type(record).__name__}")
    try:
        jsonschema.validate(instance=dict(record), schema=dict(schema or load_schema()))
    except jsonschema.ValidationError as exc:
        where = ".".join(str(part) for part in exc.absolute_path) or "<root>"
        raise SiteError(stem, path, f"schema violation at {where}: {exc.message}") from exc
    if record["id"] != stem:
        raise SiteError(stem, path, f"id {record['id']!r} does not match the file stem {stem!r}")
    return Site(record=dict(record), path=path)


def registry_notice(root: Path | str = SITES_ROOT) -> str | None:
    """The notice for a registry that is missing, unreadable or empty.

    ``None`` when the registry holds at least one file. The caller decides
    what to do with the notice; an empty registry never refuses a request.
    """

    root = Path(root)
    if not root.is_dir():
        return MISSING_ROOT_NOTICE.format(root=root)
    try:
        any_file = any(root.glob("*.yaml"))
    except OSError:
        return MISSING_ROOT_NOTICE.format(root=root)
    return None if any_file else EMPTY_NOTICE


def load_sites(root: Path | str = SITES_ROOT) -> dict[str, Site | SiteError]:
    """Read every record under ``root``, keyed by file stem.

    A malformed record becomes a :class:`SiteError` value rather than an
    exception, so one bad file never hides the rest. A missing or unreadable
    root yields an empty mapping; :func:`registry_notice` names the failure.
    """

    root = Path(root)
    if not root.is_dir():
        return {}
    try:
        paths = sorted(root.glob("*.yaml"))
    except OSError:
        return {}
    schema = load_schema()
    loaded: dict[str, Site | SiteError] = {}
    for path in paths:
        try:
            loaded[path.stem] = load_site(path, schema=schema)
        except SiteError as exc:
            loaded[path.stem] = exc
    return loaded


def _format_bearing(bearing: float) -> str:
    return f"{bearing:g}"


def expected_bearings(resolution_deg: float) -> list[float]:
    """The bearings a complete horizon covers, from true north clockwise."""

    if resolution_deg <= 0:
        return []
    count = int(round(360.0 / resolution_deg))
    return [round(index * resolution_deg, 6) for index in range(count)]


def _audit_horizon(site: Site) -> list[str]:
    horizon = site.record.get("horizon")
    if not isinstance(horizon, Mapping):
        return [f"{HORIZON_MISSING}: {site.site_id} carries no directional horizon"]
    values = horizon.get("elevation_deg")
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)) or not values:
        return [f"{HORIZON_MISSING}: {site.site_id} carries no directional horizon"]

    resolution = float(horizon["bearing_resolution_deg"])
    bearings = expected_bearings(resolution)
    if not bearings:
        return [
            f"{HORIZON_MISSING}: {site.site_id} declares a bearing resolution of "
            f"{_format_bearing(resolution)} degrees, which covers no bearing"
        ]

    errors: list[str] = []
    # A wrong count and a null value are the same failure seen from two sides:
    # a bearing the reader asked for that nobody registered. Name each one.
    for index, bearing in enumerate(bearings):
        registered = values[index] if index < len(values) else None
        if registered is None:
            errors.append(
                f"{HORIZON_GAP}:{_format_bearing(bearing)}: {site.site_id} has no registered "
                f"horizon elevation at {_format_bearing(bearing)} degrees true"
            )
    if len(values) > len(bearings):
        errors.append(
            f"{HORIZON_GAP}:extra: {site.site_id} registers {len(values)} horizon values where a "
            f"bearing resolution of {_format_bearing(resolution)} degrees covers {len(bearings)}"
        )
    return errors


def _audit_terrain_check(site: Site) -> list[str]:
    check = site.record["terrain_check"]
    status = str(check["status"])
    if status == "not_run":
        # The check was not run and says so. That disclosure is the record's
        # honest state; the terrain horizon is not assumed to agree.
        return []

    errors: list[str] = []
    if check["dem"] is None or check["terrain_elevation_deg"] is None:
        missing = [
            key for key in ("dem", "terrain_elevation_deg") if check[key] is None
        ]
        errors.append(
            f"{TERRAIN_CHECK_INCOMPLETE}: {site.site_id} claims terrain_check.status "
            f"{status!r} without {', '.join(f'terrain_check.{key}' for key in missing)}"
        )
        return errors

    tolerance = float(check["tolerance_deg"])
    terrain = list(check["terrain_elevation_deg"])
    registered_values = site.elevation_deg
    bearings = expected_bearings(site.bearing_resolution_deg)
    below: list[str] = []
    for index, bearing in enumerate(bearings):
        if index >= len(terrain) or index >= len(registered_values):
            break
        terrain_angle = terrain[index]
        registered_angle = registered_values[index]
        if terrain_angle is None or registered_angle is None:
            continue
        if float(registered_angle) < float(terrain_angle) - tolerance:
            below.append(
                f"{BELOW_TERRAIN}:{_format_bearing(bearing)}:{float(registered_angle):g}:"
                f"{float(terrain_angle):g}: {site.site_id} registers "
                f"{float(registered_angle):g} degrees where the terrain horizon is "
                f"{float(terrain_angle):g} degrees, beyond the {tolerance:g} degree tolerance; "
                "the terrain cannot be seen through"
            )
    errors.extend(below)
    if status == "failed" and not below:
        errors.append(
            f"{TERRAIN_CHECK_INCOMPLETE}: {site.site_id} records terrain_check.status 'failed' "
            "but no bearing sits below the terrain horizon beyond the tolerance"
        )
    return errors


def audit_site(site: Site) -> list[str]:
    """Every reason this registration is not servable, in the reader's words.

    An empty list means the record is servable. A record whose terrain check
    was not run is servable with that disclosure: the check being absent is
    not the same as the registration disagreeing with terrain.
    """

    errors = _audit_horizon(site)
    errors.extend(_audit_terrain_check(site))
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit the site registration records.")
    parser.add_argument("--all", action="store_true", help="report every record, servable and not")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="report every record and exit non-zero when any record is not servable",
    )
    parser.add_argument("--root", type=Path, default=SITES_ROOT, help="the directory of site records to read")
    args = parser.parse_args(argv)

    report_all = args.all or args.strict

    notice = registry_notice(args.root)
    sites = load_sites(args.root)
    if not sites:
        print(notice or EMPTY_NOTICE)
        return 0

    failures = 0
    unservable = 0
    for site_id in sorted(sites):
        entry = sites[site_id]
        if isinstance(entry, SiteError):
            failures += 1
            print(f"ERROR: {entry}", file=sys.stderr)
            continue
        errors = audit_site(entry)
        if errors:
            unservable += 1
            for error in errors:
                print(f"ERROR: {error}", file=sys.stderr)
        if report_all:
            state = "not servable" if errors else "servable"
            check = entry.record["terrain_check"]
            print(
                f"{site_id}: {state}; horizon {len(entry.elevation_deg)} bearings at "
                f"{_format_bearing(entry.bearing_resolution_deg)} degrees; "
                f"terrain check {check['status']}"
            )
            if check["status"] == "not_run":
                print(f"{site_id}: terrain check not run: {check['note']}")

    print(
        f"sites: {len(sites)} records, {unservable} not servable, {failures} unreadable; "
        "sites are preferred locations and never a limit on where evidence is served"
    )
    if failures or unservable:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
