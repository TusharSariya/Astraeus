"""The owner-approved registry of derivation methods.

Every value of evidence class ``derived_here`` names an entry here. An entry
is a declaration, not an implementation: it says what the construction is
(name, version), where it is published (citation), which catalogue fields it
reads and produces, the physical range of each output and what happens when a
result leaves that range, whether it is switched on, and who approved it. A
method absent from this registry cannot produce a served value at all
(:class:`UnregisteredMethod`, code ``unregistered_method``).

Two refusals happen at load, before anything is served, because a registry
that admits them is worse than no registry:

* **Blending.** An entry whose inputs take the same catalogue field, or two
  members of one field family, from more than one source is a blend of what
  two centres said, and no centre issued the result. So is an entry that mixes
  a provider's own reduction with a statistic computed over a different member
  set. Both are refused at registration, naming the rule.
* **Unapproved entries.** An entry without an approval record naming the owner
  and the decision it came from fails validation, and importing this module
  raises, so the deployment refuses to start with it.
* **Statistic entries that cannot stay inside one family and one run.** A
  ``member_statistic`` entry whose inputs name more than one source, one that
  mixes a time-averaged key with an instantaneous key of the same family, and
  a quantile entry that declares no convention are all refused at
  registration. The same conditions are checked again at derive time against
  the artifacts that actually resolved, in
  :func:`derive_ensemble_statistic`, because those are what carry the family
  and the run.

Three switches, mirroring the generated-display kill switch in
``ingest.derive.methods``: ``enabled`` per entry, ``WEATHER_DERIVED_HERE``
per deployment, and the reader's own set of switched-off entries passed in by
the interface. A refused method yields ``None`` with a notice naming the level
that refused it - never a substitute construction.

Dependency direction: this module imports ``ingest.meteorology`` (the pure
constructions) and nothing from ``api``. The API and the worker both import
it as ``ingest.derive.registry``.

Spec-Refs: openspec/changes/evidence-classes-and-derived-here/specs/derivation-method-registry/spec.md
Spec-Refs: openspec/changes/ensemble-families-and-member-statistics/specs/derivation-method-registry/spec.md
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field as dataclass_field
from datetime import datetime
from statistics import fmean, stdev
from typing import Any, Iterable, Literal, Sequence

from ingest.meteorology import fog_state, relative_humidity_from_dewpoint, resolve_wind

EVIDENCE_CLASS = "derived_here"

#: The deployment-level refusal switch, read at call time so an operator or a
#: test can flip it without restarting the process. ``off``, ``0``, ``false``
#: or ``no`` (any case, surrounding whitespace ignored) refuses every derived
#: value; anything else, including unset, allows them. Retrieved values are
#: never affected by it.
DERIVED_HERE_ENV = "WEATHER_DERIVED_HERE"

#: What a caller declares as the source of an input when the method reads
#: whichever single source published the inputs at that point (relative
#: humidity beside its own temperature and dew point). Two inputs both marked
#: this way are the same source, so they are not a blend.
SAME_SOURCE = "same-source"

InputKind = Literal["field", "provider_reduction", "member_statistic"]
RangeRule = Literal["clamp", "wrap", "null", "inherit_input_range"]

_RANGE_RULES: frozenset[str] = frozenset({"clamp", "wrap", "null", "inherit_input_range"})
_INPUT_KINDS: frozenset[str] = frozenset({"field", "provider_reduction", "member_statistic"})

#: Catalogue keys that are an average over a window rather than an instant.
#: A statistic entry may not mix one of these with another key of the same
#: family: the inputs are two quantities and the output would carry no window.
TIME_AVERAGED_FIELDS: frozenset[str] = frozenset({"total_cloud_mean_6h"})

#: Field families that hold a provider's own reduction over its own member
#: set rather than the members themselves. A member set of one of these is
#: retrieved evidence and is never an input to a statistic computed here.
PROVIDER_REDUCTION_FAMILIES: frozenset[str] = frozenset({"ensemble_reduction"})

#: The comparison senses a threshold probability admits.
THRESHOLD_COMPARISONS: frozenset[str] = frozenset({"ge", "gt", "le", "lt"})

#: The flag a value carries when it was computed here, and the flag a
#: statistic carries when the member set it covered was incomplete. Mirrors
#: ``api.weather_api.models``; ``ingest`` never imports ``api``.
DERIVED_FLAG = "derived"
PARTIAL_MEMBER_SET_FLAG = "partial_member_set"

#: How bad each QC status is. A statistic is no better than its worst member.
QUALITY_SEVERITY: dict[str, int] = {"passed": 0, "suspect": 1, "unknown": 2, "failed": 3}


class RegistryError(RuntimeError):
    """The registry itself is invalid; the deployment must not start."""

    def __init__(self, errors: Iterable[str]) -> None:
        self.errors = list(errors)
        super().__init__("derivation method registry refused:\n  " + "\n  ".join(self.errors))


class UnregisteredMethod(LookupError):
    """A derived value named a method the registry does not carry."""

    code = "unregistered_method"

    def __init__(self, name: str) -> None:
        self.method = name
        super().__init__(f"unregistered_method: {name!r} is not a derivation method registry entry")


@dataclass(frozen=True, slots=True)
class Approval:
    """Who admitted this construction, when, and against what record."""

    approver: str
    decided_on: str
    record: str
    note: str

    def as_dict(self) -> dict[str, str]:
        return {"approver": self.approver, "decided_on": self.decided_on, "record": self.record, "note": self.note}


@dataclass(frozen=True, slots=True)
class Input:
    """One catalogue field an entry reads.

    ``family`` is the field family (``CONTEXT.md``) the field belongs to, and
    it is what the no-blend rule reads: two members of one family taken from
    two sources are a blend even when their catalogue names differ, which is
    exactly the ``total_cloud_opacity_weighted`` from HRDPS plus
    ``total_cloud_geometric`` from GFS case.
    """

    field: str
    family: str
    source: str = SAME_SOURCE
    kind: InputKind = "field"

    def as_dict(self) -> dict[str, str]:
        return {"field": self.field, "family": self.family, "source": self.source, "kind": self.kind}


@dataclass(frozen=True, slots=True)
class Output:
    """One catalogue field an entry produces, with its physical range.

    ``minimum``/``maximum`` are the declared physical range and ``range_rule``
    says what happens to a result outside it: ``clamp`` (bound it and flag the
    value ``range_clamped``), ``wrap`` (a circular quantity such as a bearing),
    ``null`` (refuse the value with a notice), or ``inherit_input_range`` for a
    statistic whose bound is the input field's own published range rather than
    a constant this registry can state. Only ``inherit_input_range`` may leave
    the bounds unset; ``note`` then says what bounds the statistic carries.
    """

    field: str
    units: str
    minimum: float | None
    maximum: float | None
    range_rule: RangeRule
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "units": self.units,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "range_rule": self.range_rule,
            "note": self.note,
        }


@dataclass(frozen=True, slots=True)
class DerivationMethod:
    """One registered construction."""

    name: str
    version: str
    citation: str
    inputs: tuple[Input, ...]
    outputs: tuple[Output, ...]
    approval: Approval
    enabled: bool = True
    #: Whether a reader may switch this entry off for their own view. Every
    #: entry is switchable today; the field exists so an entry that a later
    #: change makes structural can say so rather than being special-cased.
    reader_switchable: bool = True
    #: Whether the reader-level switch starts on. Derived-here values are
    #: evidence, so they start on; generated-display values do not.
    reader_default_on: bool = True
    summary: str = ""
    #: The conventions this construction chose where more than one exists, as
    #: sentences a reader can check the number against: which mean, which
    #: denominator, which quantile definition. An entry that admits more than
    #: one convention and declares none is refused at registration, because
    #: two conventions differ visibly over 21 members.
    conventions: tuple[str, ...] = ()
    #: Whether the control member takes part in the computation. Declared on
    #: every statistic entry, because a mean over 20 perturbed members and a
    #: mean over 21 members including the control are different numbers.
    include_control: bool = True
    #: The owner-approved least number of members a value may cover. ``None``
    #: means none is declared, and none is invented at derive time: the
    #: shortfall rides on the value instead (owner gate 6.4).
    minimum_members: int | None = None

    @property
    def output(self) -> Output:
        """The single output, for the common one-output entry.

        Two of the first five entries (wind, the ephemeris geometry) produce
        several fields from one construction, so ``outputs`` is the general
        form and this raises rather than picking one silently.
        """
        if len(self.outputs) != 1:
            raise ValueError(f"{self.name!r} produces {len(self.outputs)} fields; read `outputs`")
        return self.outputs[0]

    def output_for(self, field: str) -> Output | None:
        return next((item for item in self.outputs if item.field == field), None)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "citation": self.citation,
            "evidence_class": EVIDENCE_CLASS,
            "inputs": [item.as_dict() for item in self.inputs],
            "outputs": [item.as_dict() for item in self.outputs],
            "approval": self.approval.as_dict(),
            "enabled": self.enabled,
            "reader_switchable": self.reader_switchable,
            "reader_default_on": self.reader_default_on,
            "summary": self.summary,
            "conventions": list(self.conventions),
            "include_control": self.include_control,
            "minimum_members": self.minimum_members,
        }


@dataclass(frozen=True, slots=True)
class Refusal:
    """Why a derived value is ``None``."""

    code: Literal["unregistered_method", "method_disabled", "deployment_refused", "reader_disabled"]
    method: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "method": self.method, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class Derived:
    """A derived result: a value, its entry and any flags, or a refusal."""

    value: float | None
    method: DerivationMethod | None = None
    flags: tuple[str, ...] = ()
    refusal: Refusal | None = None

    @property
    def available(self) -> bool:
        return self.refusal is None


def validation_errors(entries: Iterable[DerivationMethod]) -> list[str]:
    """Every reason this set of entries may not be loaded, in entry order."""
    errors: list[str] = []
    seen: set[str] = set()
    for entry in entries:
        name = entry.name
        if name in seen:
            errors.append(f"{name}: duplicate registry entry name")
        seen.add(name)
        for text, label in ((name, "name"), (entry.version, "version"), (entry.citation, "citation")):
            if not text or not text.strip():
                errors.append(f"{name}: {label} is required")
        approval = entry.approval
        if not (approval.approver and approval.approver.strip() and approval.decided_on and approval.record):
            errors.append(
                f"{name}: no approval record; adding or changing an entry requires the owner's approval, "
                "recorded in the entry"
            )
        if not entry.inputs:
            errors.append(f"{name}: an entry declares the catalogue fields it reads")
        if not entry.outputs:
            errors.append(f"{name}: an entry declares the catalogue field it produces")
        for item in entry.inputs:
            if item.kind not in _INPUT_KINDS:
                errors.append(f"{name}: unknown input kind {item.kind!r}")
            if not item.field or not item.family:
                errors.append(f"{name}: every input names a catalogue field and its family")
        for item in entry.outputs:
            if item.range_rule not in _RANGE_RULES:
                errors.append(f"{name}: unknown range rule {item.range_rule!r} for {item.field!r}")
            elif item.range_rule != "inherit_input_range":
                if item.minimum is None or item.maximum is None:
                    errors.append(f"{name}: {item.field!r} declares no physical range")
                elif item.minimum >= item.maximum:
                    errors.append(f"{name}: {item.field!r} declares an empty physical range")
        errors.extend(_blending_errors(entry))
        errors.extend(_member_statistic_errors(entry))
        errors.extend(_camera_validation_errors(entry))
    return errors


def _member_statistic_errors(entry: DerivationMethod) -> list[str]:
    """Refuse a statistic entry that cannot stay inside one family and one run.

    A statistic over an ensemble is a statement about one centre's own member
    set. An entry whose inputs name two sources is a statistic over two member
    sets by another name, and an entry that reads a six-hour-mean field beside
    an instantaneous field of the same family is a statistic over two
    quantities whose output carries no window. Both are refused here, before
    anything is served; the same conditions are checked again at derive time
    against the artifacts actually resolved, because those are what carry the
    family and the run.
    """
    member_inputs = [item for item in entry.inputs if item.kind == "member_statistic"]
    if not member_inputs:
        return []
    errors: list[str] = []
    sources = {item.source for item in member_inputs}
    if len(sources) > 1:
        errors.append(
            f"{entry.name}: one-family rule - a member statistic reads the members of one family from one "
            f"source, and these inputs name {len(sources)} ({', '.join(sorted(sources))})"
        )
    by_family: dict[str, set[str]] = {}
    for item in member_inputs:
        by_family.setdefault(item.family, set()).add(item.field)
    for family, fields in sorted(by_family.items()):
        averaged = sorted(fields & TIME_AVERAGED_FIELDS)
        if averaged and fields - TIME_AVERAGED_FIELDS:
            errors.append(
                f"{entry.name}: averaged-with-instantaneous refused - family {family!r} mixes the "
                f"time-averaged key {averaged[0]!r} with {', '.join(sorted(fields - TIME_AVERAGED_FIELDS))}; "
                "the inputs are two quantities and the output would have no meaningful window"
            )
    if "quantile" in entry.name and not entry.conventions:
        errors.append(
            f"{entry.name}: a quantile entry declares its quantile convention and interpolation rule; "
            "two conventions differ visibly over 21 members"
        )
    return errors


def _camera_validation_errors(entry: DerivationMethod) -> list[str]:
    """Refuse a camera method that is enabled before its validation exists.

    Every camera derivation enters this registry disabled and is enabled only
    after a validation record comparing its output against CYYT METAR
    visibility and cloud over at least 30 days spanning day, night, fog, rain
    and snow is recorded with the entry and approved by the owner. Flipping
    ``enabled`` here is not that record, so it is refused at registration and
    the deployment refuses to start.
    """
    if entry.name in CAMERA_METHODS and entry.enabled:
        return [
            f"{entry.name}: {CAMERA_ENABLED_WITHOUT_VALIDATION} - a camera derivation method is enabled "
            "only after a 30-day CYYT METAR validation spanning day, night, fog, rain and snow is "
            "recorded with the entry and approved by the owner"
        ]
    return []


def _blending_errors(entry: DerivationMethod) -> list[str]:
    """Refuse an entry that combines what two centres said.

    Two rules, both from the truth boundary: the same catalogue field, or two
    members of one field family, taken from more than one source; and a
    provider's own reduction combined with a statistic over another member set.
    """
    errors: list[str] = []
    by_family: dict[str, set[str]] = {}
    by_field: dict[str, set[str]] = {}
    for item in entry.inputs:
        by_family.setdefault(item.family, set()).add(item.source)
        by_field.setdefault(item.field, set()).add(item.source)
    for field_name, sources in sorted(by_field.items()):
        if len(sources) > 1:
            errors.append(
                f"{entry.name}: blending refused - input field {field_name!r} is taken from more than one "
                f"source ({', '.join(sorted(sources))}); combining the same field across centres is blending"
            )
    for family, sources in sorted(by_family.items()):
        if len(sources) > 1 and not any(len(by_field[item.field]) > 1 for item in entry.inputs if item.family == family):
            errors.append(
                f"{entry.name}: blending refused - field family {family!r} is taken from more than one source "
                f"({', '.join(sorted(sources))}); members of one family from two centres are the same field "
                "averaged across centres by another name"
            )
    kinds = {item.kind for item in entry.inputs}
    if "provider_reduction" in kinds and "member_statistic" in kinds:
        errors.append(
            f"{entry.name}: blending refused - a provider's own reduction combined with a statistic over "
            "another member set"
        )
    return errors


@dataclass(frozen=True, slots=True)
class DerivationRegistry:
    """A validated set of entries. Constructing an invalid one raises."""

    entries: tuple[DerivationMethod, ...]
    _by_name: dict[str, DerivationMethod] = dataclass_field(default_factory=dict, compare=False, repr=False)

    def __post_init__(self) -> None:
        errors = validation_errors(self.entries)
        if errors:
            raise RegistryError(errors)
        object.__setattr__(self, "_by_name", {entry.name: entry for entry in self.entries})

    def get(self, name: str) -> DerivationMethod | None:
        """The entry with this name, or ``None`` - never a substitute."""
        return self._by_name.get(name)

    def require(self, name: str) -> DerivationMethod:
        entry = self.get(name)
        if entry is None:
            raise UnregisteredMethod(name)
        return entry

    def resolve(self, name: str, *, reader_disabled: Iterable[str] = ()) -> Refusal | None:
        """``None`` when this method may produce a value now, else why not.

        The three levels are checked outermost-first so a reader sees the
        reason that actually applies to them.
        """
        entry = self.get(name)
        if entry is None:
            return Refusal("unregistered_method", name, "not a derivation method registry entry")
        if not entry.enabled:
            return Refusal("method_disabled", name, "the registry entry is not enabled")
        if not derivations_enabled():
            return Refusal(
                "deployment_refused", name,
                f"{DERIVED_HERE_ENV} refuses derived values in this deployment; retrieved values are unaffected",
            )
        if name in set(reader_disabled):
            return Refusal("reader_disabled", name, "switched off in this reader's interface")
        return None

    def catalogue(self, *, reader_disabled: Iterable[str] = ()) -> list[dict[str, Any]]:
        """Every entry, as the API and the interface announce it.

        This is the reader-level switch contract: the interface renders one
        row per entry, offers a switch where ``reader_switchable`` is true,
        starts it at ``reader_default_on``, and sends the names it switched
        off back as ``reader_disabled``. A reader's choice never leaves that
        reader's view, and never enables what the entry or the deployment has
        already refused.
        """
        disabled = set(reader_disabled)
        rows: list[dict[str, Any]] = []
        for entry in self.entries:
            refusal = self.resolve(entry.name, reader_disabled=disabled)
            row = entry.as_dict()
            row["available"] = refusal is None
            row["refusal"] = refusal.as_dict() if refusal is not None else None
            rows.append(row)
        return rows

    def bound(self, name: str, field: str, value: float | None) -> tuple[float | None, tuple[str, ...]]:
        """Bound a result to its declared physical range.

        ``clamp`` bounds and flags ``range_clamped``; ``wrap`` folds a circular
        quantity into its interval; ``null`` refuses the value and flags
        ``range_refused``; ``inherit_input_range`` leaves the value alone
        because the bound belongs to the input field, not to this entry.
        """
        entry = self.require(name)
        spec = entry.output_for(field)
        if spec is None:
            raise UnregisteredMethod(f"{name}:{field}")
        if value is None:
            return None, ()
        if spec.range_rule == "inherit_input_range" or spec.minimum is None or spec.maximum is None:
            return value, ()
        if spec.minimum <= value <= spec.maximum:
            return value, ()
        if spec.range_rule == "wrap":
            span = spec.maximum - spec.minimum
            return spec.minimum + (value - spec.minimum) % span, ("range_wrapped",)
        if spec.range_rule == "null":
            return None, ("range_refused",)
        return min(max(value, spec.minimum), spec.maximum), ("range_clamped",)

    def provenance(self, name: str) -> dict[str, Any]:
        """What a provenance record carries for a value from this entry."""
        entry = self.require(name)
        return {
            "evidence_class": EVIDENCE_CLASS,
            "derivation": entry.name,
            "derivation_version": entry.version,
            "derivation_citation": entry.citation,
            "derivation_inputs": [item.as_dict() for item in entry.inputs],
        }


def derivations_enabled() -> bool:
    """Is this deployment allowed to serve ``derived_here`` values at all?"""
    return os.environ.get(DERIVED_HERE_ENV, "").strip().lower() not in {"off", "0", "false", "no"}


_OWNER_APPROVAL = Approval(
    approver="@TusharSariya",
    decided_on="2026-09-02",
    record="docs/adr/0001-five-evidence-classes.md; wayfinder tickets 17 and 25",
    note=(
        "Admitted with the five evidence classes and the derived-here class. Each construction here was "
        "already served or already specified; none is fitted to the values it produces."
    ),
)

RELATIVE_HUMIDITY = "relative_humidity_from_dewpoint_liquid"
WIND_SPEED_AND_DIRECTION = "wind_speed_and_direction_from_components"
FOG_STATE = "fog_state_from_present_weather"
#: The umbrella entry. Every member statistic goes through it: it is the
#: family-level switch, resolved before the specific entry, so disabling it at
#: any of the three levels nulls all five statistics with a notice naming the
#: level, and the per-member values are unaffected.
ENSEMBLE_STATISTICS = "ensemble_statistics_within_run"
ENSEMBLE_MEAN = "ensemble_mean"
ENSEMBLE_SPREAD = "ensemble_spread"
ENSEMBLE_QUANTILE = "ensemble_quantile"
ENSEMBLE_THRESHOLD_PROBABILITY = "ensemble_threshold_probability"
ENSEMBLE_MEMBER_COUNT = "ensemble_member_count"

#: The five entries a served statistic may name. A value's ``derivation`` is
#: one of these, never the umbrella.
ENSEMBLE_STATISTIC_ENTRIES: tuple[str, ...] = (
    ENSEMBLE_MEAN,
    ENSEMBLE_SPREAD,
    ENSEMBLE_QUANTILE,
    ENSEMBLE_THRESHOLD_PROBABILITY,
    ENSEMBLE_MEMBER_COUNT,
)

#: The statistic a caller asks for, and the entry that produces it.
ENSEMBLE_ENTRY_BY_STATISTIC: dict[str, str] = {
    "mean": ENSEMBLE_MEAN,
    "spread": ENSEMBLE_SPREAD,
    "quantile": ENSEMBLE_QUANTILE,
    "threshold_probability": ENSEMBLE_THRESHOLD_PROBABILITY,
    "member_count": ENSEMBLE_MEMBER_COUNT,
}

SECTOR_SAMPLING = "sector_sampling_along_bearing"
DE442_GEOMETRY = "de442_sun_moon_geometry"

CAMERA_FOG_VISIBILITY_CLASS = "camera_fog_and_visibility_class"
CAMERA_VISIBILITY_BOUND = "camera_visibility_bound_from_landmarks"
CAMERA_SECTOR_CLOUD_FRACTION = "camera_daytime_sector_cloud_fraction"
CAMERA_HORIZON_FOG_BANK = "camera_horizon_fog_bank_presence"
CAMERA_SKYDOME_NIGHT_CLOUD = "camera_skydome_night_cloud_from_starfield"

#: The five camera methods. Every one of them enters this registry disabled
#: and stays disabled until a validation record comparing its output against
#: CYYT METAR visibility and cloud over at least 30 days spanning day, night,
#: fog, rain and snow is recorded with the entry and approved by the owner
#: (wayfinder ticket 21). Registration refuses any of these with
#: ``enabled=True``, so the gate cannot be stepped over by an edit here.
CAMERA_METHODS: tuple[str, ...] = (
    CAMERA_FOG_VISIBILITY_CLASS,
    CAMERA_VISIBILITY_BOUND,
    CAMERA_SECTOR_CLOUD_FRACTION,
    CAMERA_HORIZON_FOG_BANK,
    CAMERA_SKYDOME_NIGHT_CLOUD,
)

#: The registration refusal a camera entry earns by being enabled before its
#: validation exists.
CAMERA_ENABLED_WITHOUT_VALIDATION = "camera_method_enabled_without_validation"

#: What every camera method reads: one frame from one registered camera. A
#: camera derivation never reads two cameras and never reads a frame beside a
#: model field, so there is one input family and one source.
_CAMERA_FRAME_INPUT = Input(field="camera_frame", family="camera_frame", source="registered-camera")
_CAMERA_LANDMARK_INPUT = Input(field="camera_landmarks", family="camera_geometry", source="registered-camera")

#: The sentence every camera summary ends with, named once so the gate reads
#: the same on all five entries.
_CAMERA_GATE = (
    "Registered disabled (wayfinder ticket 21); enabled only after a 30-day CYYT METAR validation "
    "spanning day, night, fog, rain and snow is recorded with this entry and approved by the owner."
)

#: What the five statistic entries and their umbrella cite, and the single
#: input each declares: one catalogue field over the member axis of one
#: source. The field is the family placeholder, not a particular key; the key
#: a value actually covered rides on the member set the value carries.
_ENSEMBLE_CITATION = (
    "Sample statistics over an ensemble's own members within one run and one family, as in "
    "Wilks (2019), Statistical Methods in the Atmospheric Sciences, 4th ed., chapter 8."
)
_ENSEMBLE_MEMBER_INPUT = Input(
    field="ensemble_member_field", family="ensemble_member_field", kind="member_statistic"
)

#: The first entries: the derivations this deployment already serves or has
#: already specified. Order is menu order.
ENTRIES: tuple[DerivationMethod, ...] = (
    DerivationMethod(
        name=RELATIVE_HUMIDITY,
        version="metpy-1.7.1-liquid-v1",
        citation=(
            "Saturation vapour pressure after Bolton (1980), Monthly Weather Review 108, 1046-1053, "
            "evaluated by MetPy 1.7.1 `relative_humidity_from_dewpoint` with an explicit liquid-water phase."
        ),
        inputs=(
            Input(field="air_temperature", family="air_temperature"),
            Input(field="dew_point", family="humidity_dew_point"),
        ),
        outputs=(
            Output(field="relative_humidity", units="percent", minimum=0.0, maximum=100.0, range_rule="clamp"),
        ),
        approval=_OWNER_APPROVAL,
        summary=(
            "Relative humidity over liquid water from a source's own temperature and dew point, used only "
            "where that source published no relative humidity of its own."
        ),
    ),
    DerivationMethod(
        name=WIND_SPEED_AND_DIRECTION,
        version="metpy-1.7.1-wind-v1",
        citation=(
            "MetPy 1.7.1 `wind_speed` and `wind_direction` over the stored u and v components, "
            "meteorological from-direction convention (WMO No. 8, Part I, Chapter 5)."
        ),
        inputs=(
            Input(field="wind_u", family="wind_vector_component"),
            Input(field="wind_v", family="wind_vector_component"),
        ),
        outputs=(
            Output(field="wind_speed", units="m s-1", minimum=0.0, maximum=150.0, range_rule="clamp"),
            Output(
                field="wind_direction", units="degree", minimum=0.0, maximum=360.0, range_rule="wrap",
                note="A bearing is circular; a result outside the interval is folded into it, not clamped.",
            ),
        ),
        approval=_OWNER_APPROVAL,
        summary="Wind speed and the from-direction bearing from one source's own u and v components.",
    ),
    DerivationMethod(
        name=FOG_STATE,
        version="fog-state-present-weather-v1",
        citation=(
            "The present-weather group of a METAR or TAF as defined in ICAO Annex 3 / WMO No. 49 and coded "
            "per FM 15/FM 51: FG (with FZFG, MIFG, BCFG, PRFG) and VCFG are fog evidence; BR is mist and is "
            "not. Read beside the report's own visibility."
        ),
        inputs=(
            Input(field="present_weather_fog_code", family="present_weather"),
            Input(field="present_weather_fog_vicinity_code", family="present_weather"),
            Input(field="visibility", family="visibility"),
        ),
        outputs=(
            Output(
                field="fog_state", units="category", minimum=None, maximum=None,
                range_rule="inherit_input_range",
                note=(
                    "A categorical state carries no numeric range; its admissible values are "
                    "evidence_present, not_indicated and unknown, and not_indicated is unreachable where no "
                    "provider publishes a fog diagnostic."
                ),
            ),
        ),
        approval=_OWNER_APPROVAL,
        summary=(
            "Fog evidence read from one report's present-weather group, already served on /point. An absent "
            "FG code is not a finding of no fog, so the state is unknown rather than not_indicated."
        ),
    ),
    DerivationMethod(
        name=ENSEMBLE_STATISTICS,
        version="within-run-v1",
        citation=_ENSEMBLE_CITATION,
        inputs=(_ENSEMBLE_MEMBER_INPUT,),
        outputs=(
            Output(
                field="ensemble_statistic", units="input field units", minimum=None, maximum=None,
                range_rule="inherit_input_range",
                note=(
                    "Mean and quantiles carry the input field's own published range; spread is non-negative; "
                    "a threshold probability is 0 to 1; a count is 0 to the run's member count."
                ),
            ),
        ),
        approval=_OWNER_APPROVAL,
        conventions=(
            "Every member statistic resolves this entry first, so switching it off at any of the three "
            "levels switches off all five without switching off the members themselves.",
        ),
        summary=(
            "The umbrella entry for mean, spread, quantiles, threshold probabilities and counts over the "
            "members of one ensemble family within one run. Enabled by "
            "`ensemble-families-and-member-statistics`; a served value names the specific entry below, not "
            "this one."
        ),
    ),
    DerivationMethod(
        name=ENSEMBLE_MEAN,
        version="within-run-v1",
        citation=_ENSEMBLE_CITATION,
        inputs=(_ENSEMBLE_MEMBER_INPUT,),
        outputs=(
            Output(
                field="ensemble_mean", units="input field units", minimum=None, maximum=None,
                range_rule="inherit_input_range",
                note="A mean of one field carries that field's own published unit and range.",
            ),
        ),
        approval=_OWNER_APPROVAL,
        conventions=("The arithmetic mean of the resolved member values, each member weighted equally.",),
        summary="The arithmetic mean over the members of one family, one run and one field.",
    ),
    DerivationMethod(
        name=ENSEMBLE_SPREAD,
        version="within-run-v1",
        citation=_ENSEMBLE_CITATION,
        inputs=(_ENSEMBLE_MEMBER_INPUT,),
        outputs=(
            Output(
                field="ensemble_spread", units="input field units", minimum=None, maximum=None,
                range_rule="inherit_input_range",
                note=(
                    "A spread is non-negative and is zero when every member agrees; its upper bound is the "
                    "span of the input field's own published range, which this entry cannot state as a "
                    "constant."
                ),
            ),
        ),
        approval=_OWNER_APPROVAL,
        conventions=(
            "The sample standard deviation with an n-1 denominator, zero when every member agrees.",
            "Fewer than two resolved members is no sample, so no spread is produced.",
        ),
        summary="The sample standard deviation over the members of one family, one run and one field.",
    ),
    DerivationMethod(
        name=ENSEMBLE_QUANTILE,
        version="within-run-v1",
        citation=_ENSEMBLE_CITATION,
        inputs=(_ENSEMBLE_MEMBER_INPUT,),
        outputs=(
            Output(
                field="ensemble_quantile", units="input field units", minimum=None, maximum=None,
                range_rule="inherit_input_range",
                note="A quantile of one field carries that field's own published unit and range.",
            ),
        ),
        approval=_OWNER_APPROVAL,
        conventions=(
            "Hyndman and Fan (1996) type 7: linear interpolation between the order statistics at position "
            "(n-1)q on the sorted resolved member values, which is the numpy default.",
            "The requested quantile rides on every value the entry produces.",
        ),
        summary="A quantile over the members of one family, one run and one field.",
    ),
    DerivationMethod(
        name=ENSEMBLE_THRESHOLD_PROBABILITY,
        version="within-run-v1",
        citation=_ENSEMBLE_CITATION,
        inputs=(_ENSEMBLE_MEMBER_INPUT,),
        outputs=(
            Output(
                field="ensemble_threshold_probability", units="fraction", minimum=0.0, maximum=1.0,
                range_rule="clamp",
                note="The fraction of resolved members satisfying the comparison, 0 to 1.",
            ),
        ),
        approval=_OWNER_APPROVAL,
        conventions=(
            "The fraction of resolved members satisfying the comparison, over the members resolved and not "
            "over the members declared.",
            "The threshold, its unit and its comparison sense (ge, gt, le or lt) ride on every value the "
            "entry produces; a probability without all three is not served.",
        ),
        summary="The fraction of one family's members that cross a threshold, within one run.",
    ),
    DerivationMethod(
        name=ENSEMBLE_MEMBER_COUNT,
        version="within-run-v1",
        citation=_ENSEMBLE_CITATION,
        inputs=(_ENSEMBLE_MEMBER_INPUT,),
        outputs=(
            Output(
                field="ensemble_members_used", units="count", minimum=0.0, maximum=1000.0, range_rule="clamp",
                note="Members that resolved a value. Reported beside the declared count, never instead of it.",
            ),
            Output(
                field="ensemble_members_declared", units="count", minimum=0.0, maximum=1000.0, range_rule="clamp",
                note="Members the registry declares for the family, whether or not they resolved.",
            ),
        ),
        approval=_OWNER_APPROVAL,
        conventions=(
            "Members used and members declared are two numbers; neither stands for both.",
            "No member resolved is null with that reason, never a count of zero standing for agreement.",
        ),
        summary="How many of one family's declared members resolved for one run and one field.",
    ),
    DerivationMethod(
        name=SECTOR_SAMPLING,
        version="geodesic-sector-v1",
        citation=(
            "Great-circle sector sampling of a gridded field along a bearing from a site, on WGS84 geodesics "
            "after Karney (2013), Journal of Geodesy 87, 43-55."
        ),
        inputs=(
            Input(field="gridded_field", family="gridded_field"),
            Input(field="site_geometry", family="site_geometry", source="registered-site"),
        ),
        outputs=(
            Output(
                field="sector_statistic", units="input field units", minimum=None, maximum=None,
                range_rule="inherit_input_range",
                note="A sample of one field over a sector carries that field's own published range.",
            ),
        ),
        approval=_OWNER_APPROVAL,
        conventions=(
            "Reduction: the mean of the sampled cell values, every in-sector cell weighted equally; a "
            "far cell counts the same as a near one, because the question is about the whole sector.",
            "Parameters: the origin latitude and longitude, the bearing, the sector width, the maximum "
            "range and the elevation-angle band. The band is carried in provenance and is not applied to "
            "a 2-D surface grid, which has no elevation axis to select on.",
            "A cell is in the sector when its great-circle bearing from the origin is within half the "
            "width of the bearing and its great-circle distance is at most the maximum range.",
            "Minimum covered fraction 0.8: below it the sample is null naming the uncovered fraction, "
            "never a mean over the covered part alone.",
            "Inputs are retrieved gridded fields from one source; a non-retrieved class is refused "
            "naming the class, and one field or family from two sources is refused as a blend.",
        ),
        summary=(
            "Sampling one gridded field over a sector along a bearing from a registered site, for the "
            "sunrise-sector cloud question. Implemented in `ingest.derive.sector`: the mean of the "
            "retrieved cells inside the sector, null below a covered fraction of 0.8."
        ),
    ),
    DerivationMethod(
        name=DE442_GEOMETRY,
        version="de442-skyfield-1.55-v1",
        citation=(
            "JPL planetary and lunar ephemerides, Park et al. (2021), Astronomical Journal 161:105; the "
            "pinned DE442 kernel (sha256 8d5001fa...fd388) evaluated with Skyfield 1.55."
        ),
        inputs=(
            Input(field="ephemeris_kernel_de442", family="ephemeris_kernel", source="nasa-jpl-de442"),
        ),
        outputs=(
            Output(field="sun_altitude", units="degree", minimum=-90.0, maximum=90.0, range_rule="clamp"),
            Output(field="sun_azimuth", units="degree", minimum=0.0, maximum=360.0, range_rule="wrap"),
            Output(field="moon_altitude", units="degree", minimum=-90.0, maximum=90.0, range_rule="clamp"),
            Output(field="moon_azimuth", units="degree", minimum=0.0, maximum=360.0, range_rule="wrap"),
            Output(field="moon_illuminated_fraction", units="fraction", minimum=0.0, maximum=1.0, range_rule="clamp"),
            Output(field="moon_phase_angle", units="degree", minimum=0.0, maximum=180.0, range_rule="clamp"),
        ),
        approval=_OWNER_APPROVAL,
        summary=(
            "Sun and Moon geometry for a point and instant from the checksum-pinned DE442 ephemeris. "
            "Deterministic geometry, never blended with weather evidence."
        ),
    ),
    DerivationMethod(
        name=CAMERA_FOG_VISIBILITY_CLASS,
        version="camera-class-v0",
        citation=(
            "Classification of fog and of a visibility band from the contrast of registered landmarks in a "
            "fixed camera frame, in the sense of the WMO Guide to Instruments and Methods of Observation "
            "(WMO-No. 8) Part I Chapter 9, section on visual estimation of visibility by marks at known "
            "distances. No published skill for this camera; the entry is a declaration pending validation."
        ),
        inputs=(_CAMERA_FRAME_INPUT,),
        outputs=(
            Output(
                field="camera_fog_class", units="category", minimum=None, maximum=None,
                range_rule="inherit_input_range",
                note=(
                    "Admissible values: no_fog, fog_patches, fog, dense_fog. A category carries no numeric "
                    "range; the admissible set is the range."
                ),
            ),
            Output(
                field="camera_visibility_class", units="category", minimum=None, maximum=None,
                range_rule="inherit_input_range",
                note=(
                    "Admissible values: good, moderate, poor, very_poor. A class, never a distance: a "
                    "visibility in metres from the image alone is refused."
                ),
            ),
            Output(
                field="camera_class_confidence", units="fraction", minimum=0.0, maximum=1.0,
                range_rule="clamp",
                note="One confidence per class, reported with the class and never in place of it.",
            ),
        ),
        approval=_OWNER_APPROVAL,
        enabled=False,
        summary=(
            "A fog class and a visibility class, each with a confidence, from one frame of a registered "
            "camera with an accepted geometry. " + _CAMERA_GATE
        ),
    ),
    DerivationMethod(
        name=CAMERA_VISIBILITY_BOUND,
        version="camera-landmark-bound-v0",
        citation=(
            "Landmark-contrast visibility bounding: the interval between the farthest visible and the "
            "nearest invisible registered landmark, after the visibility-by-marks method of the WMO Guide "
            "to Instruments and Methods of Observation (WMO-No. 8) Part I Chapter 9. Pending validation "
            "against CYYT METAR visibility for this camera."
        ),
        inputs=(_CAMERA_FRAME_INPUT, _CAMERA_LANDMARK_INPUT),
        outputs=(
            Output(
                field="visibility_bound_lower_m", units="m", minimum=0.0, maximum=100000.0,
                range_rule="clamp",
                note=(
                    "The distance to the farthest visible registered landmark, which is named on every "
                    "value along with the nearest invisible one. Half of an interval, never a numeric "
                    "visibility derived from the image alone."
                ),
            ),
            Output(
                field="visibility_bound_upper_m", units="m", minimum=0.0, maximum=100000.0,
                range_rule="clamp",
                note=(
                    "The distance to the nearest invisible registered landmark, which is named on every "
                    "value along with the farthest visible one. Half of an interval, never a numeric "
                    "visibility derived from the image alone."
                ),
            ),
        ),
        approval=_OWNER_APPROVAL,
        enabled=False,
        conventions=(
            "The claim is an interval between two named registered landmarks, never a single number.",
            "Both landmarks are named on every value, with their distances and the geometry version.",
            "Where the landmarks a bound needs are absent or flagged, the bound is null naming them.",
        ),
        summary=(
            "A visibility interval bounded by the farthest visible and the nearest invisible registered "
            "landmark, both named. " + _CAMERA_GATE
        ),
    ),
    DerivationMethod(
        name=CAMERA_SECTOR_CLOUD_FRACTION,
        version="camera-sector-cloud-v0",
        citation=(
            "Region-of-interest sky fraction: the fraction of the registered sky region of a daytime frame "
            "classified as cloud, within the camera's registered sector. A standard whole-sky-imager "
            "approach in outline; unvalidated for this camera and pending the METAR comparison."
        ),
        inputs=(_CAMERA_FRAME_INPUT,),
        outputs=(
            Output(
                field="camera_sector_cloud_fraction", units="fraction", minimum=0.0, maximum=1.0,
                range_rule="clamp",
                note="Cloud fraction within the camera's registered sector, from a daylight frame only.",
            ),
        ),
        approval=_OWNER_APPROVAL,
        enabled=False,
        summary=(
            "Daytime cloud fraction within a registered camera's own sector. Refused on any frame carrying "
            "the darkness or darkness_unknown flag. " + _CAMERA_GATE
        ),
    ),
    DerivationMethod(
        name=CAMERA_HORIZON_FOG_BANK,
        version="camera-fog-bank-v0",
        citation=(
            "Presence of a fog bank on the horizon from the loss of the skyline against the registered "
            "terrain horizon in a fixed camera frame. A presence statement, not an amount; unvalidated for "
            "this camera and pending the METAR comparison."
        ),
        inputs=(_CAMERA_FRAME_INPUT,),
        outputs=(
            Output(
                field="horizon_fog_bank_present", units="category", minimum=None, maximum=None,
                range_rule="inherit_input_range",
                note=(
                    "Admissible values: present, absent, indeterminate. A presence statement only: no "
                    "distance to the bank and no visibility is inferred from it."
                ),
            ),
        ),
        approval=_OWNER_APPROVAL,
        enabled=False,
        summary=(
            "Whether a fog bank is present on the horizon in one frame of a registered camera. "
            + _CAMERA_GATE
        ),
    ),
    DerivationMethod(
        name=CAMERA_SKYDOME_NIGHT_CLOUD,
        version="camera-starfield-v0",
        citation=(
            "Night cloud fraction from star-field visibility: the fraction of catalogue stars expected "
            "above the horizon that are absent from a sky-dome frame, the star-count approach used by "
            "night-sky camera cloud detection. Unvalidated for the NTV sky-dome camera and pending the "
            "METAR comparison."
        ),
        inputs=(_CAMERA_FRAME_INPUT,),
        outputs=(
            Output(
                field="skydome_night_cloud_fraction", units="fraction", minimum=0.0, maximum=1.0,
                range_rule="clamp",
                note="Night cloud fraction over the sky dome, from the absent fraction of expected stars.",
            ),
        ),
        approval=_OWNER_APPROVAL,
        enabled=False,
        summary=(
            "Night cloud fraction from the star field of the NTV sky-dome camera, the one derivation that "
            "runs on a dark frame. " + _CAMERA_GATE
        ),
    ),
)

#: The loaded registry. Importing this module with an invalid entry set raises
#: :class:`RegistryError`, so the deployment refuses to start with it.
REGISTRY = DerivationRegistry(ENTRIES)


def get(name: str) -> DerivationMethod | None:
    """The entry with this name, or ``None``."""
    return REGISTRY.get(name)


def require(name: str) -> DerivationMethod:
    """The entry with this name, or raise :class:`UnregisteredMethod`."""
    return REGISTRY.require(name)


def resolve(name: str, *, reader_disabled: Iterable[str] = ()) -> Refusal | None:
    """``None`` when the method may produce a value now, else the refusal."""
    return REGISTRY.resolve(name, reader_disabled=reader_disabled)


def catalogue(*, reader_disabled: Iterable[str] = ()) -> list[dict[str, Any]]:
    """Every entry as the API and the interface announce it."""
    return REGISTRY.catalogue(reader_disabled=reader_disabled)


def provenance(name: str) -> dict[str, Any]:
    """What a provenance record carries for a value from this entry."""
    return REGISTRY.provenance(name)


def bound(name: str, field: str, value: float | None) -> tuple[float | None, tuple[str, ...]]:
    """Bound a result to the entry's declared physical range."""
    return REGISTRY.bound(name, field, value)


def derive_relative_humidity(
    temperature_c: float | None,
    dewpoint_c: float | None,
    *,
    reader_disabled: Iterable[str] = (),
) -> Derived:
    """Relative humidity through its registry entry, with the three switches.

    The construction itself stays in ``ingest.meteorology``; this adds the
    registry gate, the physical-range bound and the provenance the entry
    carries, so no caller reaches the bare function on a data path.
    """
    refusal = resolve(RELATIVE_HUMIDITY, reader_disabled=reader_disabled)
    if refusal is not None:
        return Derived(value=None, method=get(RELATIVE_HUMIDITY), refusal=refusal)
    entry = require(RELATIVE_HUMIDITY)
    if temperature_c is None or dewpoint_c is None:
        return Derived(value=None, method=entry)
    value, flags = bound(RELATIVE_HUMIDITY, "relative_humidity", relative_humidity_from_dewpoint(temperature_c, dewpoint_c))
    return Derived(value=value, method=entry, flags=flags)


def resolve_registered_relative_humidity(
    direct_rh_percent: float | None,
    temperature_c: float | None,
    dewpoint_c: float | None,
    *,
    reader_disabled: Iterable[str] = (),
) -> tuple[float | None, str | None, str | None]:
    """``ingest.meteorology.resolve_relative_humidity`` through the registry.

    Same three-tuple, so the call site changes by one name: the derivation and
    version it returns are the registry entry's name and version rather than a
    free-text description, and a refusal at any of the three switch levels
    yields ``(None, None, None)`` rather than a number.

    A source that published its own relative humidity keeps it: a derivation
    never replaces a published field.
    """
    if direct_rh_percent is not None:
        return direct_rh_percent, None, None
    derived = derive_relative_humidity(temperature_c, dewpoint_c, reader_disabled=reader_disabled)
    if derived.value is None or derived.method is None:
        return None, None, None
    return derived.value, derived.method.name, derived.method.version


@dataclass(frozen=True, slots=True)
class DerivedWind:
    """One wind derivation: two values from one construction, or a refusal.

    Speed and direction come from one entry and are bounded by different rules
    (a speed is clamped, a bearing is folded), so the flags are kept per field
    rather than merged: a provenance must record which of its two numbers the
    range rule touched.
    """

    speed: float | None
    direction: float | None
    method: DerivationMethod | None = None
    speed_flags: tuple[str, ...] = ()
    direction_flags: tuple[str, ...] = ()
    refusal: Refusal | None = None

    @property
    def available(self) -> bool:
        return self.refusal is None


def derive_wind(u_ms: float | None, v_ms: float | None, *, reader_disabled: Iterable[str] = ()) -> DerivedWind:
    """Wind speed and direction through their registry entry, with the flags.

    The bounding flags are what a served provenance records, so this is the
    form a data path uses; :func:`resolve_registered_wind` is the three-switch
    tuple for callers that only want the numbers.
    """
    refusal = resolve(WIND_SPEED_AND_DIRECTION, reader_disabled=reader_disabled)
    if refusal is not None:
        return DerivedWind(speed=None, direction=None, method=get(WIND_SPEED_AND_DIRECTION), refusal=refusal)
    entry = require(WIND_SPEED_AND_DIRECTION)
    speed, direction, _, _ = resolve_wind(u_ms, v_ms)
    if speed is None or direction is None:
        return DerivedWind(speed=None, direction=None, method=entry)
    speed, speed_flags = bound(WIND_SPEED_AND_DIRECTION, "wind_speed", speed)
    direction, direction_flags = bound(WIND_SPEED_AND_DIRECTION, "wind_direction", direction)
    return DerivedWind(speed=speed, direction=direction, method=entry, speed_flags=speed_flags, direction_flags=direction_flags)


def resolve_registered_wind(
    u_ms: float | None,
    v_ms: float | None,
    *,
    reader_disabled: Iterable[str] = (),
) -> tuple[float | None, float | None, str | None, str | None]:
    """``ingest.meteorology.resolve_wind`` through the registry entry."""
    derived = derive_wind(u_ms, v_ms, reader_disabled=reader_disabled)
    if derived.speed is None or derived.direction is None or derived.method is None:
        return None, None, None, None
    return derived.speed, derived.direction, derived.method.name, derived.method.version


@dataclass(frozen=True, slots=True)
class DerivedState:
    """A categorical derived value - a fog state - or a refusal."""

    value: str | None
    method: DerivationMethod | None = None
    refusal: Refusal | None = None

    @property
    def available(self) -> bool:
        return self.refusal is None


def derive_fog_state(
    *,
    provider_diagnostic: bool | None,
    visibility_m: float | None,
    fog_code: bool | None,
    reader_disabled: Iterable[str] = (),
) -> DerivedState:
    """The fog state through its registry entry.

    Categorical, so there is no range to bound: the entry's admissible values
    are the construction's own three, and ``not_indicated`` stays unreachable
    while no provider here publishes a fog diagnostic.
    """
    refusal = resolve(FOG_STATE, reader_disabled=reader_disabled)
    if refusal is not None:
        return DerivedState(value=None, method=get(FOG_STATE), refusal=refusal)
    entry = require(FOG_STATE)
    return DerivedState(
        value=fog_state(provider_diagnostic=provider_diagnostic, visibility_m=visibility_m, fog_code=fog_code),
        method=entry,
    )


def resolve_registered_fog_state(
    *,
    provider_diagnostic: bool | None,
    visibility_m: float | None,
    fog_code: bool | None,
    reader_disabled: Iterable[str] = (),
) -> tuple[str | None, str | None, str | None]:
    """``(state, entry name, entry version)``, or three ``None`` on refusal."""
    derived = derive_fog_state(
        provider_diagnostic=provider_diagnostic,
        visibility_m=visibility_m,
        fog_code=fog_code,
        reader_disabled=reader_disabled,
    )
    if derived.value is None or derived.method is None:
        return None, None, None
    return derived.value, derived.method.name, derived.method.version


# --- Ensemble statistics over one family's own members within one run -------


@dataclass(frozen=True, slots=True)
class MemberValue:
    """One member's value for one field, with its own QC verdict.

    ``control`` marks the control run, which lands on the member axis as a
    flagged member rather than beside it. A member that resolved no value
    keeps its row with ``value=None``, because a named absence is what lets a
    partial set name the members it is missing.
    """

    member: str
    control: bool
    value: float | None
    quality_status: str = "unknown"

    def as_dict(self) -> dict[str, Any]:
        return {
            "member": self.member,
            "control": self.control,
            "value": self.value,
            "quality_status": self.quality_status,
        }


@dataclass(frozen=True, slots=True)
class MemberSet:
    """The members of one family, one run and one field, as they resolved.

    ``declared`` is the member count the registry declares for the family, so
    a statistic can say what it covered and what it did not. ``time_averaged``
    marks a field that is a mean over a window (the GEFS six-hour-mean cloud);
    such a set is never combined with an instantaneous set of the same
    quantity.
    """

    family: str
    source_id: str
    run_time: datetime | None
    field: str
    declared: int
    members: tuple[MemberValue, ...]
    time_averaged: bool = False

    @property
    def used(self) -> tuple[MemberValue, ...]:
        """The members that resolved a value."""
        return tuple(item for item in self.members if item.value is not None)

    @property
    def missing(self) -> tuple[str, ...]:
        """The declared members that are absent, named where they are known.

        A member row with no value names itself. Where the family's declared
        member ids are not known here - only the count is - the shortfall is
        carried as :attr:`missing_count` instead, because inventing member ids
        to fill it would be a fabricated member set.
        """
        return tuple(item.member for item in self.members if item.value is None)

    @property
    def missing_count(self) -> int:
        """How many declared members did not resolve, named or not."""
        return max(self.declared, len(self.members)) - len(self.used)

    @property
    def partial(self) -> bool:
        return self.missing_count > 0

    @property
    def quality_status(self) -> str:
        """The worst QC status among the members that resolved a value."""
        statuses = [item.quality_status for item in self.used]
        if not statuses:
            return "unknown"
        return max(statuses, key=lambda value: QUALITY_SEVERITY.get(value, 2))

    def as_dict(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "source_id": self.source_id,
            "run_time": self.run_time.isoformat() if self.run_time is not None else None,
            "field": self.field,
            "declared": self.declared,
            "members_used": len(self.used),
            "members_missing": list(self.missing),
            "partial": self.partial,
            "time_averaged": self.time_averaged,
        }


@dataclass(frozen=True, slots=True)
class EnsembleStatistic:
    """One statistic over one member set, or the reason there is no number.

    Three ways to have no value, and they are not the same thing: ``refusal``
    is a switch (the umbrella entry, the deployment or the reader),
    ``condition_failed`` is a resolved input that broke the one-family,
    one-run, one-quantity rule, and a ``value`` of ``None`` with neither is a
    field that simply did not resolve. In every case the member set the
    statistic would have covered is still carried, so a reader sees what was
    refused rather than only that something was.
    """

    statistic: str
    value: float | None
    method: DerivationMethod | None
    member_set: MemberSet | None
    flags: tuple[str, ...]
    refusal: Refusal | None
    condition_failed: str | None
    members_used: int
    members_declared: int
    members_missing: tuple[str, ...]
    control_included: bool | None
    quantile: float | None = None
    threshold: float | None = None
    threshold_units: str | None = None
    comparison: str | None = None

    @property
    def available(self) -> bool:
        return self.refusal is None and self.condition_failed is None

    @property
    def partial(self) -> bool:
        return PARTIAL_MEMBER_SET_FLAG in self.flags

    @property
    def quality_status(self) -> str:
        """No better than the worst member the statistic covered."""
        return self.member_set.quality_status if self.member_set is not None else "unknown"


def _statistic_entry_name(statistic: str) -> str:
    """The registry entry that produces this statistic, by its short name.

    An unknown statistic keeps the name it was asked for, so it resolves to
    ``unregistered_method`` rather than to some nearest entry.
    """
    return ENSEMBLE_ENTRY_BY_STATISTIC.get(statistic, statistic)


def _condition_failure(member_sets: Sequence[MemberSet]) -> str | None:
    """The first condition these resolved member sets fail, or ``None``.

    The conditions the registry refuses at registration, checked again against
    what actually resolved, because the artifacts are what carry the family
    and the run. Order matters: a provider's own reduction dragged in beside
    members is reported as that, not as a second family.
    """
    if any(item.family in PROVIDER_REDUCTION_FAMILIES for item in member_sets):
        return "provider_reduction_mixed"
    families = sorted({item.family for item in member_sets})
    if len(families) > 1:
        return f"one_family:{families[0]},{families[1]}"
    runs = sorted(
        {item.run_time.isoformat() if item.run_time is not None else "unknown" for item in member_sets}
    )
    if len(runs) > 1:
        return f"one_run:{runs[0]},{runs[1]}"
    averaged = {item.time_averaged or item.field in TIME_AVERAGED_FIELDS for item in member_sets}
    if len(averaged) > 1:
        return "averaged_with_instantaneous"
    return None


def _quantile_type_7(values: Sequence[float], quantile: float) -> float:
    """Hyndman and Fan type 7, in plain Python.

    Linear interpolation between the order statistics at position ``(n-1)q``,
    which is what numpy's default gives; written out here so the registry
    computes without numpy installed.
    """
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[int(position)]
    return ordered[lower] + (position - lower) * (ordered[upper] - ordered[lower])


def _satisfies(value: float, threshold: float, comparison: str) -> bool:
    if comparison == "ge":
        return value >= threshold
    if comparison == "gt":
        return value > threshold
    if comparison == "le":
        return value <= threshold
    return value < threshold


def derive_ensemble_statistic(
    statistic: str,
    member_sets: Sequence[MemberSet],
    *,
    quantile: float | None = None,
    threshold: float | None = None,
    threshold_units: str | None = None,
    comparison: str | None = None,
    reader_disabled: Iterable[str] = (),
) -> EnsembleStatistic:
    """One of the five statistics over the members that actually resolved.

    The umbrella entry is resolved first, so switching
    ``ensemble_statistics_within_run`` off at any of the three levels nulls
    every statistic with a notice naming the level while the per-member values
    go on being served. The specific entry is resolved next, so one statistic
    can be switched off without the others.

    A failed condition yields no value at all: nothing is computed over
    whichever subset passes, because a mean over the members of one of two
    runs is not the mean the reader asked for. A partial set does produce a
    value, flagged ``partial_member_set`` and carrying the members it missed.
    """
    reader_off = set(reader_disabled)
    sets = tuple(member_sets)
    primary = sets[0] if sets else None
    declared = sum(item.declared for item in sets)
    resolved = [item for member_set in sets for item in member_set.used]
    missing = tuple(name for member_set in sets for name in member_set.missing)

    def _result(
        *,
        value: float | None,
        method: DerivationMethod | None,
        flags: tuple[str, ...] = (),
        refusal: Refusal | None = None,
        condition_failed: str | None = None,
        control_included: bool | None = None,
        members_used: int | None = None,
    ) -> EnsembleStatistic:
        return EnsembleStatistic(
            statistic=statistic,
            value=value,
            method=method,
            member_set=primary,
            flags=flags,
            refusal=refusal,
            condition_failed=condition_failed,
            members_used=len(resolved) if members_used is None else members_used,
            members_declared=declared,
            members_missing=missing,
            control_included=control_included,
            quantile=quantile,
            threshold=threshold,
            threshold_units=threshold_units,
            comparison=comparison,
        )

    umbrella = resolve(ENSEMBLE_STATISTICS, reader_disabled=reader_off)
    if umbrella is not None:
        return _result(value=None, method=get(ENSEMBLE_STATISTICS), refusal=umbrella)
    entry_name = _statistic_entry_name(statistic)
    refusal = resolve(entry_name, reader_disabled=reader_off)
    if refusal is not None:
        return _result(value=None, method=get(entry_name), refusal=refusal)
    entry = require(entry_name)

    if not sets:
        return _result(value=None, method=entry, condition_failed="no_member_resolved")
    failed = _condition_failure(sets)
    if failed is not None:
        return _result(value=None, method=entry, condition_failed=failed)

    declared_control = any(item.control for member_set in sets for item in member_set.members)
    counted = resolved if entry.include_control else [item for item in resolved if not item.control]
    control_included: bool | None = None
    if declared_control:
        control_included = bool(entry.include_control and any(item.control for item in counted))

    flags: tuple[str, ...] = (DERIVED_FLAG,)
    if any(member_set.partial for member_set in sets):
        flags += (PARTIAL_MEMBER_SET_FLAG,)

    values = [item.value for item in counted if item.value is not None]
    if not values:
        return _result(
            value=None, method=entry, flags=flags, condition_failed="no_member_resolved",
            control_included=control_included, members_used=0,
        )
    minimum = entry.minimum_members
    if minimum is not None and len(values) < minimum:
        return _result(
            value=None, method=entry, flags=flags,
            condition_failed=f"below_minimum:{len(values)}/{minimum}",
            control_included=control_included, members_used=len(values),
        )

    if entry_name == ENSEMBLE_MEAN:
        raw, output_field = fmean(values), "ensemble_mean"
    elif entry_name == ENSEMBLE_SPREAD:
        if len(values) < 2:
            # A sample standard deviation with an n-1 denominator needs two
            # members; one member is not a spread of zero.
            return _result(
                value=None, method=entry, flags=flags,
                condition_failed=f"below_minimum:{len(values)}/2",
                control_included=control_included, members_used=len(values),
            )
        raw, output_field = stdev(values), "ensemble_spread"
    elif entry_name == ENSEMBLE_QUANTILE:
        if quantile is None or not 0.0 <= quantile <= 1.0:
            raise ValueError("ensemble_quantile needs a quantile in 0 to 1; none is assumed")
        raw, output_field = _quantile_type_7(values, quantile), "ensemble_quantile"
    elif entry_name == ENSEMBLE_THRESHOLD_PROBABILITY:
        if threshold is None or comparison not in THRESHOLD_COMPARISONS:
            raise ValueError(
                "ensemble_threshold_probability needs a threshold and a comparison in "
                f"{', '.join(sorted(THRESHOLD_COMPARISONS))}; neither is assumed"
            )
        crossing = sum(1 for value in values if _satisfies(value, threshold, comparison))
        raw, output_field = crossing / len(values), "ensemble_threshold_probability"
    else:
        raw, output_field = float(len(values)), "ensemble_members_used"

    value, bound_flags = bound(entry_name, output_field, raw)
    return _result(
        value=value, method=entry, flags=flags + bound_flags,
        control_included=control_included, members_used=len(values),
    )
