#!/usr/bin/env python3
"""Validate the activity profile registry against the field catalogue.

An activity profile is a file, not a code path, which is only an improvement if
something checks the file. This is that something. It reads every YAML file
under ``registry/profiles``, validates it against
``registry/profiles/schema.json``, and then resolves every name the file uses
against the field catalogue of ``registry/fields.py``: families through
``family``, field keys through ``field``, units through ``units_for``.

What it refuses is the list of ways a profile can look right and be wrong:

* a family the catalogue does not define, so the profile would read nothing;
* a threshold whose declared units disagree with the catalogue's, which is the
  silent factor of 3.6 between ``km h-1`` and ``m s-1``;
* a weight outside ``[0, 1]``, which makes a weighted sum mean nothing;
* a threshold with no default, which leaves an override with nothing to record
  itself against;
* the same field named as a hard stop and as a graded criterion, which lets one
  quantity both stop the evaluation and contribute to the score it stopped;
* a window rule written in wall-clock time, which would be a second,
  unregistered solar model;
* a ``blocked_fields`` entry for a key the catalogue carries, because an
  admitted source can supply it and the entry must be removed before the field
  is served.

It fails closed. If the field catalogue cannot be imported at all, every
profile is reported ``catalogue_unavailable`` and none is reported valid: a
profile validated against an absent catalogue has been validated against
nothing. The catalogue import goes through :func:`load_catalogue` so a test can
simulate that failure without breaking the module.

Nothing here promotes a registry status, admits a source, or enables a
derivation. It reads files and says whether they are honest.

Run it from ``experiments/st-johns-weather-map``::

    python3 registry/profile_audit.py --all
    python3 registry/profile_audit.py --all --strict
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field as dataclass_field
from pathlib import Path
from typing import Any, Mapping

if __package__ in (None, ""):  # run as a script, not imported as registry.profile_audit
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import jsonschema  # noqa: E402
import yaml  # noqa: E402

HERE = Path(__file__).resolve().parent

#: Where profile files live. One YAML file per profile, the stem is the id.
PROFILES_ROOT = HERE / "profiles"

#: The JSON Schema every profile file is validated against before any name in
#: it is resolved. Shape first, meaning second.
SCHEMA_PATH = PROFILES_ROOT / "schema.json"

#: The one registered ephemeris entry a window rule may name.
GEOMETRY_ENTRY = "de442_sun_moon_geometry"

#: Its outputs. A window written in anything else is written in a solar model
#: this deployment does not have.
GEOMETRY_FIELDS = (
    "sun_altitude",
    "sun_azimuth",
    "moon_altitude",
    "moon_azimuth",
    "moon_illuminated_fraction",
    "moon_phase_angle",
)

#: The window rules and the parameters each one takes.
WINDOW_RULES: dict[str, tuple[str, ...]] = {
    "any_window_within_24h": ("length_hours", "daylight_only"),
    "astronomical_night": (),
    "dark_hours": (),
    "sunrise_sunset_margin": ("margin_minutes",),
}

#: A window parameter naming any of these is a wall-clock rule wearing an
#: astronomical rule's schema. Refused by name so the message says which key.
_CLOCK_SUBSTRINGS = ("local_time", "wall_clock", "clock", "hour_range", "hours_range")
_CLOCK_PATTERN = re.compile(r"(^|_)(start|end|from|to|begin|after|before)_hour(s)?($|_)")

#: The catalogue's own key style. A blocked or wanted field need not exist in
#: the catalogue, but it must be spelled the way a catalogue key is spelled, or
#: the entry could never be matched to the field it is about.
KEY_PATTERN = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$")

#: The fail-closed message. One string, so a caller can grep for it.
CATALOGUE_UNAVAILABLE = "catalogue_unavailable"


class CatalogueUnavailable(RuntimeError):
    """The field catalogue could not be imported, so nothing can be resolved."""


class ProfileError(Exception):
    """One profile file that could not be read, parsed or shaped.

    Carried rather than raised out of :func:`load_profiles`: a malformed file
    makes its own profile unavailable and leaves every other profile alone,
    which is what the specification requires.
    """

    def __init__(self, profile: str, path: Path, detail: str) -> None:
        self.profile = profile
        self.path = Path(path)
        self.detail = detail
        super().__init__(f"{profile}: {detail} ({self.path.name})")


@dataclass(frozen=True)
class Profile:
    """A parsed profile file: its id, its mapping, and where it came from."""

    id: str
    path: Path
    data: Mapping[str, Any] = dataclass_field(default_factory=dict)

    @property
    def version(self) -> Any:
        return self.data.get("version")

    @property
    def title(self) -> Any:
        return self.data.get("title")


def load_catalogue():
    """The field catalogue module, or :class:`CatalogueUnavailable`.

    A seam rather than a plain import so a test can simulate the catalogue
    being unreadable and check that validation fails closed instead of
    reporting every profile valid against nothing.
    """
    try:
        from registry import fields as catalogue
    except Exception as exc:  # pragma: no cover - exercised through the seam
        raise CatalogueUnavailable(str(exc)) from exc
    return catalogue


def load_schema(path: Path | None = None) -> Mapping[str, Any]:
    """The profile JSON Schema, read from disk on every call.

    Cheap, and it keeps a long-lived process from validating against a schema
    the working tree no longer has.
    """
    schema_path = Path(path) if path is not None else SCHEMA_PATH
    with schema_path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _clock_keys(params: Mapping[str, Any]) -> list[str]:
    """Every parameter name that is a clock in disguise."""
    found: list[str] = []
    for name in params:
        text = str(name).lower()
        if any(part in text for part in _CLOCK_SUBSTRINGS) or _CLOCK_PATTERN.search(text):
            found.append(str(name))
    return sorted(found)


def load_profile(path: Path | str, *, schema: Mapping[str, Any] | None = None) -> Profile:
    """Read and shape-check one profile file.

    Raises :class:`ProfileError` on a read failure, a YAML parse failure, a
    schema failure, an id that disagrees with the file stem, or a window rule
    written in wall-clock time. It does not touch the field catalogue; that is
    :func:`audit_profile`, so a shape failure is never reported as a catalogue
    failure.
    """
    path = Path(path)
    stem = path.stem
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ProfileError(stem, path, f"cannot be read: {exc}") from exc
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        detail = str(exc).replace("\n", " ")
        raise ProfileError(stem, path, f"cannot be parsed: {detail}") from exc
    if not isinstance(data, Mapping):
        raise ProfileError(
            stem, path, f"is not a mapping at the top level, it is {type(data).__name__}"
        )

    # The clock check runs before the schema so its message can name the rule
    # rather than a JSON pointer into params.
    window = data.get("window")
    if isinstance(window, Mapping):
        params = window.get("params")
        if isinstance(params, Mapping):
            clock = _clock_keys(params)
            if clock:
                raise ProfileError(
                    stem,
                    path,
                    f"window rule {window.get('rule')!r} declares the wall-clock parameter "
                    f"{', '.join(clock)}; a window is an astronomical quantity computed by "
                    f"{GEOMETRY_ENTRY} and may not be written in local time",
                )

    try:
        jsonschema.validate(dict(data), dict(schema if schema is not None else load_schema()))
    except jsonschema.ValidationError as exc:
        where = "/".join(str(part) for part in exc.absolute_path) or "<root>"
        raise ProfileError(stem, path, f"fails the profile schema at {where}: {exc.message}") from exc

    declared = data.get("id")
    if declared != stem:
        raise ProfileError(
            stem, path, f"declares id {declared!r} but its file stem is {stem!r}"
        )
    return Profile(id=stem, path=path, data=dict(data))


def load_profiles(root: Path | str = PROFILES_ROOT) -> dict[str, Profile | ProfileError]:
    """Every profile file under ``root``, keyed by file stem.

    A file that will not load is present in the result as its
    :class:`ProfileError` rather than absent: an unavailable profile is
    reported unavailable, and it does not take the rest of the registry with
    it. ``schema.json`` is the validator, not a profile, and is skipped.
    """
    root = Path(root)
    schema = load_schema()
    out: dict[str, Profile | ProfileError] = {}
    if not root.is_dir():
        return out
    for path in sorted(root.glob("*.yaml")) + sorted(root.glob("*.yml")):
        stem = path.stem
        try:
            out[stem] = load_profile(path, schema=schema)
        except ProfileError as error:
            out[stem] = error
    return out


def audit_profile(profile: Profile, *, catalogue: Any = None) -> list[str]:
    """Everything wrong with one profile, as messages a build can print.

    Every message starts with the profile id and then names the thing at fault,
    so a failing CI line reads as "which profile, which name" without the
    reader opening the file.
    """
    pid = profile.id
    data = profile.data
    if catalogue is None:
        try:
            catalogue = load_catalogue()
        except CatalogueUnavailable as exc:
            return [
                f"{pid}: {CATALOGUE_UNAVAILABLE}: the field catalogue could not be imported "
                f"({exc}); no name in this profile could be resolved and the profile is not "
                "reported valid"
            ]

    errors: list[str] = []

    def known_field(key: Any) -> bool:
        try:
            catalogue.field(key)
        except Exception:
            return False
        return True

    # Families. The profile asks for families, so an unknown one means the
    # profile reads nothing at all rather than reading a smaller set.
    for name in data.get("families", []):
        try:
            catalogue.family(name)
        except Exception:
            errors.append(
                f"{pid}: {name}: unknown family; the field catalogue does not define it, so "
                f"this profile would resolve to no member of it ({profile.path.name})"
            )

    # Thresholds: the field must exist, the default must be there, and the
    # units must be the catalogue's units for that field.
    thresholds = data.get("thresholds", {}) or {}
    for name, spec in thresholds.items():
        if not isinstance(spec, Mapping):
            errors.append(f"{pid}: {name}: threshold is not a mapping")
            continue
        key = spec.get("field")
        if "default" not in spec or spec.get("default") is None:
            errors.append(
                f"{pid}: {name}: threshold declares no default; a reader override has nothing "
                "to be recorded against and the profile is not served"
            )
        if not known_field(key):
            errors.append(
                f"{pid}: {name}: threshold names field {key!r}, which the field catalogue does "
                "not carry"
            )
            continue
        declared = spec.get("units")
        actual = catalogue.units_for(key)
        if declared != actual:
            errors.append(
                f"{pid}: {name}: threshold on {key} declares units {declared!r} and the "
                f"catalogue gives {actual!r}"
            )
        if spec.get("comparison") not in ("ge", "gt", "le", "lt"):
            errors.append(
                f"{pid}: {name}: threshold comparison {spec.get('comparison')!r} is not one of "
                "ge, gt, le, lt"
            )

    # Weights out of range make a weighted sum mean nothing, so they are an
    # error here as well as in the schema: audit_profile is called directly on
    # profiles built in memory.
    weights = data.get("weights", {}) or {}
    for name, value in weights.items():
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            errors.append(f"{pid}: {name}: weight {value!r} is not a number")
            continue
        if not 0 <= float(value) <= 1:
            errors.append(f"{pid}: {name}: weight {value} is outside the declared range [0, 1]")

    hard_stops = data.get("hard_stops", []) or []
    graded = data.get("graded_criteria", []) or []

    for entry in hard_stops:
        if not isinstance(entry, Mapping):
            errors.append(f"{pid}: hard stop {entry!r} is not a mapping")
            continue
        name = entry.get("name")
        key = entry.get("field")
        if not known_field(key):
            errors.append(
                f"{pid}: {name}: hard stop names field {key!r}, which the field catalogue does "
                "not carry"
            )
        if entry.get("threshold") not in thresholds:
            errors.append(
                f"{pid}: {name}: hard stop names threshold {entry.get('threshold')!r}, which "
                "this profile does not declare"
            )

    for entry in graded:
        if not isinstance(entry, Mapping):
            errors.append(f"{pid}: graded criterion {entry!r} is not a mapping")
            continue
        name = entry.get("name")
        key = entry.get("field")
        if not known_field(key):
            errors.append(
                f"{pid}: {name}: graded criterion names field {key!r}, which the field "
                "catalogue does not carry"
            )
        if entry.get("threshold") not in thresholds:
            errors.append(
                f"{pid}: {name}: graded criterion names threshold {entry.get('threshold')!r}, "
                "which this profile does not declare"
            )
        if entry.get("weight") not in weights:
            errors.append(
                f"{pid}: {name}: graded criterion names weight {entry.get('weight')!r}, which "
                "this profile does not declare"
            )

    # One field may not both stop the evaluation and contribute to the score
    # that the stop would have prevented.
    stop_fields = {e.get("field") for e in hard_stops if isinstance(e, Mapping)}
    graded_fields = {e.get("field") for e in graded if isinstance(e, Mapping)}
    for key in sorted(stop_fields & graded_fields, key=str):
        errors.append(
            f"{pid}: {key}: named in both the hard stops and the graded criteria; a hard stop "
            "answers on its own and may not also carry a weight"
        )

    errors.extend(_audit_window(pid, data.get("window")))
    errors.extend(_audit_site_needs(pid, data.get("site_needs"), known_field))

    # Blocked fields. The key must be spelled like a catalogue key so it can be
    # matched to the field it refuses, and it must not be a key the catalogue
    # carries: an admitted source can supply that one, and the entry has to be
    # removed before it is served.
    for entry in data.get("blocked_fields", []) or []:
        if not isinstance(entry, Mapping):
            errors.append(f"{pid}: blocked field {entry!r} is not a mapping")
            continue
        key = entry.get("field")
        if not isinstance(key, str) or not KEY_PATTERN.match(key):
            errors.append(
                f"{pid}: {key!r}: blocked field key is not in catalogue key style "
                "(lower snake case)"
            )
            continue
        if known_field(key):
            errors.append(
                f"{pid}: {key}: listed as blocked but the field catalogue carries it; an "
                "admitted source can supply this field, so the blocked entry must be removed "
                "before it is served"
            )
        if entry.get("reason") not in ("licence", "credential", "partnership"):
            errors.append(
                f"{pid}: {key}: blocked reason {entry.get('reason')!r} is not one of licence, "
                "credential, partnership"
            )

    for entry in data.get("wanted_not_catalogued", []) or []:
        if not isinstance(entry, Mapping):
            errors.append(f"{pid}: wanted field {entry!r} is not a mapping")
            continue
        key = entry.get("field")
        if not isinstance(key, str) or not KEY_PATTERN.match(key):
            errors.append(
                f"{pid}: {key!r}: wanted_not_catalogued key is not in catalogue key style "
                "(lower snake case)"
            )

    return errors


def _audit_window(pid: str, window: Any) -> list[str]:
    """The window rule, the ephemeris entry it names, and its parameters."""
    errors: list[str] = []
    if not isinstance(window, Mapping):
        return [f"{pid}: window: is missing or is not a mapping"]
    rule = window.get("rule")
    if rule not in WINDOW_RULES:
        return [
            f"{pid}: {rule!r}: is not one of the declared window rules "
            f"({', '.join(sorted(WINDOW_RULES))})"
        ]
    entry = window.get("geometry_entry")
    if entry != GEOMETRY_ENTRY:
        errors.append(
            f"{pid}: {rule}: names geometry entry {entry!r}; the only registered ephemeris "
            f"entry is {GEOMETRY_ENTRY} and a window may not be written in another solar model"
        )
    for name in window.get("geometry_fields", []) or []:
        if name not in GEOMETRY_FIELDS:
            errors.append(
                f"{pid}: {name}: is not an output of {GEOMETRY_ENTRY} "
                f"({', '.join(GEOMETRY_FIELDS)})"
            )
    params = window.get("params")
    if not isinstance(params, Mapping):
        return errors + [f"{pid}: {rule}: window params is missing or is not a mapping"]
    clock = _clock_keys(params)
    if clock:
        errors.append(
            f"{pid}: {rule}: declares the wall-clock parameter {', '.join(clock)}; a window is "
            f"an astronomical quantity computed by {GEOMETRY_ENTRY} and may not be written in "
            "local time"
        )
    allowed = set(WINDOW_RULES[rule])
    for name in sorted(set(params) - allowed - set(clock)):
        errors.append(f"{pid}: {rule}: window rule takes no parameter {name!r}")
    for name in sorted(allowed - set(params)):
        errors.append(f"{pid}: {rule}: window rule requires the parameter {name!r}")
    return errors


def _audit_site_needs(pid: str, site_needs: Any, known_field) -> list[str]:
    """Sector parameter sets: the field must be catalogued, the geometry sane."""
    errors: list[str] = []
    if not isinstance(site_needs, Mapping):
        return [f"{pid}: site_needs: is missing or is not a mapping"]
    if not isinstance(site_needs.get("horizon_required"), bool):
        errors.append(f"{pid}: site_needs: horizon_required is not a boolean")
    for sector in site_needs.get("sectors", []) or []:
        if not isinstance(sector, Mapping):
            errors.append(f"{pid}: sector {sector!r} is not a mapping")
            continue
        name = sector.get("name")
        key = sector.get("field")
        if not known_field(key):
            errors.append(
                f"{pid}: {name}: sector samples field {key!r}, which the field catalogue does "
                "not carry"
            )
        bearing = sector.get("bearing_deg")
        width = sector.get("width_deg")
        if not isinstance(bearing, (int, float)) or not 0 <= float(bearing) < 360:
            errors.append(f"{pid}: {name}: sector bearing {bearing!r} is not in [0, 360)")
        if not isinstance(width, (int, float)) or not 0 < float(width) <= 180:
            errors.append(f"{pid}: {name}: sector width {width!r} is not in (0, 180]")
    return errors


def profile_warnings(profile: Profile, *, catalogue: Any = None) -> list[str]:
    """Things that are not wrong but are probably not intended.

    Kept apart from the errors so ``--strict`` can be the build's choice rather
    than the auditor's. A declared threshold nobody refers to is the common
    case: a criterion was removed and its threshold was left behind.
    """
    pid = profile.id
    data = profile.data
    warnings: list[str] = []
    referenced = {
        entry.get("threshold")
        for entry in list(data.get("hard_stops", []) or []) + list(data.get("graded_criteria", []) or [])
        if isinstance(entry, Mapping)
    }
    for name in sorted(data.get("thresholds", {}) or {}):
        if name not in referenced:
            warnings.append(f"{pid}: {name}: threshold is declared and no criterion refers to it")
    weighted = {
        entry.get("weight")
        for entry in data.get("graded_criteria", []) or []
        if isinstance(entry, Mapping)
    }
    for name in sorted(data.get("weights", {}) or {}):
        if name not in weighted:
            warnings.append(f"{pid}: {name}: weight is declared and no criterion carries it")
    if catalogue is None:
        try:
            catalogue = load_catalogue()
        except CatalogueUnavailable:
            return warnings
    for entry in data.get("wanted_not_catalogued", []) or []:
        if not isinstance(entry, Mapping):
            continue
        key = entry.get("field")
        try:
            catalogue.field(key)
        except Exception:
            continue
        warnings.append(
            f"{pid}: {key}: listed as wanted and not catalogued, but the field catalogue now "
            "carries it; the entry can be replaced by a real reference"
        )
    return warnings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the activity profile registry.")
    parser.add_argument("--all", action="store_true", help="audit every profile file in the registry")
    parser.add_argument("--strict", action="store_true", help="fail on warnings as well as errors")
    parser.add_argument("--root", default=None, help="profile directory (defaults to registry/profiles)")
    args = parser.parse_args(argv)

    # --strict alone audits the whole registry: a CI line that passes only
    # --strict must not be a no-op, and there is only one registry to audit.
    if args.strict:
        args.all = True

    if not args.all:
        print("nothing to do: pass --all to audit the profile registry", file=sys.stderr)
        return 2

    root = Path(args.root) if args.root else PROFILES_ROOT
    loaded = load_profiles(root)
    if not loaded:
        print(f"profile registry is empty: no profile file under {root}; no profile is invented")
        return 0

    failed = False
    for stem in sorted(loaded):
        entry = loaded[stem]
        if isinstance(entry, ProfileError):
            failed = True
            print(f"{stem}: unavailable: {entry.detail}")
            print(f"ERROR: {entry}", file=sys.stderr)
            continue
        errors = audit_profile(entry)
        warnings = profile_warnings(entry)
        if errors:
            failed = True
            print(f"{stem}: {len(errors)} error(s), version {entry.version}")
            for message in errors:
                print(f"ERROR: {message}", file=sys.stderr)
        else:
            note = f", {len(warnings)} warning(s)" if warnings else ""
            print(f"{stem}: valid, version {entry.version}{note}")
        for message in warnings:
            print(f"WARNING: {message}", file=sys.stderr)
            if args.strict:
                failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
