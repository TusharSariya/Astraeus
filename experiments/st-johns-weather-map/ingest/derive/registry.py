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

Three switches, mirroring the generated-display kill switch in
``ingest.derive.methods``: ``enabled`` per entry, ``WEATHER_DERIVED_HERE``
per deployment, and the reader's own set of switched-off entries passed in by
the interface. A refused method yields ``None`` with a notice naming the level
that refused it - never a substitute construction.

Dependency direction: this module imports ``ingest.meteorology`` (the pure
constructions) and nothing from ``api``. The API and the worker both import
it as ``ingest.derive.registry``.

Spec-Refs: openspec/changes/evidence-classes-and-derived-here/specs/derivation-method-registry/spec.md
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field as dataclass_field
from typing import Any, Iterable, Literal

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
    return errors


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
ENSEMBLE_STATISTICS = "ensemble_statistics_within_run"
SECTOR_SAMPLING = "sector_sampling_along_bearing"
DE442_GEOMETRY = "de442_sun_moon_geometry"

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
        citation=(
            "Sample statistics over an ensemble's own members within one run and one family, as in "
            "Wilks (2019), Statistical Methods in the Atmospheric Sciences, 4th ed., chapter 8."
        ),
        inputs=(
            Input(field="ensemble_member_field", family="ensemble_member_field", kind="member_statistic"),
        ),
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
        enabled=False,
        summary=(
            "Mean, spread, quantiles, threshold probabilities and counts over the members of one ensemble "
            "family within one run. Registered and disabled: `ensemble-members-and-source-plurality` "
            "enables it when member retrieval exists."
        ),
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
        enabled=False,
        summary=(
            "Sampling one gridded field over a sector along a bearing from a registered site, for the "
            "sunrise-sector cloud question. Registered and disabled until the sector sampler exists."
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
