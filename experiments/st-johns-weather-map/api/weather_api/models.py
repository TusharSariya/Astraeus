from __future__ import annotations

import sys
from collections.abc import Sequence
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator

EXPERIMENT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(EXPERIMENT_ROOT) not in sys.path:  # registry/ ships beside api/ in both images
    sys.path.insert(0, str(EXPERIMENT_ROOT))

from ingest.derive.registry import ENSEMBLE_STATISTIC_ENTRIES  # noqa: E402
from registry import fields as catalogue  # noqa: E402


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- evidence classes -----------------------------------------------------
# How a value came to exist. Exactly one of six, carried on every value and
# recorded per artifact (ADR 0001, ``docs/adr/0001-five-evidence-classes.md``).
# The class is a declared field and is never inferred from a derivation name,
# an ``evidence_basis``, a generated flag or a logical name: each of those was
# added for one feature, none knows about the others, and that is how a
# generated repair reached a data path on 2026-09-01.

EvidenceClass = Literal[
    "retrieved",
    "reprocessed",
    "derived_here",
    "intermediary_derived",
    "generated_display",
    "uncalibrated_observation",
]

EVIDENCE_CLASSES: tuple[str, ...] = (
    "retrieved",
    "reprocessed",
    "derived_here",
    "intermediary_derived",
    "generated_display",
    "uncalibrated_observation",
)

#: Classes that may be the display primary for a field and may be read as an
#: input to a derivation. Reprocessed, intermediary-derived and uncalibrated
#: values are served side by side, labelled, and never promoted.
PRIMARY_ELIGIBLE_CLASSES: frozenset[str] = frozenset({"retrieved", "derived_here"})

#: The only class a derivation may read.
DERIVATION_INPUT_CLASSES: frozenset[str] = frozenset({"retrieved"})

#: Never on ``/point``, ``/profile``, ``/timeline``, ``/features``, stories or
#: readings; display construction only, under the ``openspec/config.yaml``
#: carve-outs.
DISPLAY_ONLY_CLASSES: frozenset[str] = frozenset({"generated_display"})


# --- delivery kinds -------------------------------------------------------
# How a source's values reach this deployment, declared per registry record.
# A separate axis from the evidence class on purpose: a delivery kind says
# whose cell a value is, a class says how the value came to exist. An
# ``intermediary_derived`` value is still retrieved by this deployment, so
# reusing ``retrieved`` for a delivery kind would make one word mean two
# things.

DeliveryKind = Literal["published_cell", "reprocessed", "intermediary_derived"]

#: The only kind whose values may be a field's display primary. A value a
#: third party transformed or computed has no business outranking a producer's
#: own published cell.
PRIMARY_ELIGIBLE_DELIVERY_KINDS: frozenset[str] = frozenset({"published_cell"})


class DataMode(StrEnum):
    """How a response was produced. ``operational`` stays False regardless.

    ``UNAVAILABLE`` is the fail-closed value: it means nothing was retrieved and
    nothing was invented. It exists so a caller can never mistake an outage for
    a reading, which is what a silent fixture fallthrough used to do.
    """

    LIVE = "live"
    FIXTURE = "fixture"
    MIXED = "mixed"
    UNAVAILABLE = "unavailable"


class SourceState(StrEnum):
    #: ``OPERATIONAL`` is a member so that the ceiling in
    #: ``registry.admission`` has something to refuse. No record may declare it
    #: and no response ever emits it: the ceiling maps it to ``UNAVAILABLE``
    #: before a state reaches this enum, and ``active`` is not a state at all.
    OPERATIONAL = "operational"
    IMPLEMENTED_UNVERIFIED = "implemented-unverified"
    CATALOGUED = "catalogued"
    CREDENTIAL_REQUIRED = "credential-required"
    LICENCE_BLOCKED = "licence-blocked"
    LINK_ONLY = "link-only"
    PARTNERSHIP_ONLY = "partnership-only"
    UNAVAILABLE = "unavailable"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


#: ``derived`` is a flag, never a fifth status: a fifth status would break
#: every consumer that switches on the four, and a derived artifact whose QC
#: status was ``derived`` failed a whole ``/point`` response on 2026-09-01.
DERIVED_FLAG = "derived"
#: Set where a method's output was pulled back to the declared physical range.
RANGE_CLAMPED_FLAG = "range_clamped"
#: Set on a field whose ensemble statistic was refused: the request was not
#: answerable, which is not the same thing as the data being absent. The value
#: is null and ``provenance.ensemble.refusal`` names the condition that failed.
STATISTIC_REFUSED_FLAG = "statistic_refused"
#: Set where the member set a statistic covered is short of the count its
#: family declares. A flag rather than a status for the same reason ``derived``
#: is: the statistic is a true summary of the members that resolved, and what
#: the reader must be told is which set that was.
PARTIAL_MEMBER_SET_FLAG = "partial_member_set"
#: The comparisons a threshold probability may count members against. Kept as
#: a closed set beside the ``Literal`` on ``EnsembleProvenance`` so the request
#: surface can refuse an unknown one at the edge, with the same four words.
THRESHOLD_COMPARISONS: tuple[str, ...] = ("ge", "gt", "le", "lt")
#: Set where this deployment held the frame and purged it because its valid
#: time left the sliding window. A flag rather than a fifth QC status for the
#: same reason ``derived`` is: ageing out is a retention fact about the store,
#: not a verdict on the value, and the QC status a frame carried is not
#: retroactively changed by its removal.
AGED_OUT_FLAG = "aged_out"

#: Worst-first ordering of the four statuses. A derived value takes the worst
#: status among its inputs: it is the only rule that cannot launder a suspect
#: input into a passed output. ``unknown`` outranks ``suspect`` because an
#: unmeasured input is a weaker claim than a measured, doubted one.
QUALITY_SEVERITY: dict[str, int] = {"passed": 0, "suspect": 1, "unknown": 2, "failed": 3}


class Quality(StrictModel):
    """QC verdict on one value.

    ``status`` keeps exactly four values. Recognised ``flags`` include
    ``derived`` (this value was computed here by a registered method) and
    ``range_clamped``; the list stays open because adapters record their own
    QC flags, but ``derived`` is the one a client reads to know a number was
    constructed rather than read.
    """

    status: Literal["passed", "suspect", "failed", "unknown"]
    flags: list[str] = Field(default_factory=list)

    @property
    def derived(self) -> bool:
        return DERIVED_FLAG in self.flags

    @classmethod
    def worst_of(cls, inputs: list[Quality], *, flags: list[str] | None = None) -> Quality:
        """The derived quality: no better than the worst input, flagged derived.

        A method may downgrade further; nothing here may raise a status.
        """
        status = "unknown"
        if inputs:
            status = max((item.status for item in inputs), key=lambda value: QUALITY_SEVERITY.get(value, 2))
        collected = [DERIVED_FLAG, *(flags or [])]
        return cls(status=status, flags=list(dict.fromkeys(collected)))


class Coverage(StrictModel):
    status: Literal["complete", "partial", "outside", "unknown"]
    fraction: float | None = Field(default=None, ge=0, le=1)


class Freshness(StrictModel):
    status: Literal["fresh", "stale", "unknown"]
    age_seconds: int | None = Field(default=None, ge=0)
    # Some registry records state no resolvable freshness promise at all. A
    # missing threshold must stay missing rather than borrow a default, or the
    # response would assert a promise the provider never made.
    threshold_seconds: Annotated[int, Field(gt=0)] | None = None

    @classmethod
    def evaluate(cls, age_seconds: int | None, threshold_seconds: int | None) -> Freshness:
        """Unknown age stays unknown; an unmeasured source is never called fresh."""
        if age_seconds is None or threshold_seconds is None:
            return cls(status="unknown", age_seconds=None if age_seconds is None else max(0, int(age_seconds)), threshold_seconds=threshold_seconds)
        age = max(0, int(age_seconds))
        return cls(status="fresh" if age <= threshold_seconds else "stale", age_seconds=age, threshold_seconds=threshold_seconds)


class ContributorProvenance(StrictModel):
    source_id: str
    provider: str
    product: str
    licence: str
    attribution: str


class DerivedInput(StrictModel):
    """One value a ``derived_here`` construction read, with its own lineage.

    Every input of a derived value is listed, whatever source it came from, so
    a reader can see what the number was built out of rather than being asked
    to trust the method's name.
    """

    field: str
    source_id: str
    product: str
    valid_time: datetime
    units: str
    evidence_class: EvidenceClass
    quality: Quality
    run_time: datetime | None = None


class EnsembleMemberSet(StrictModel):
    """The members one ensemble number covers, as they actually resolved.

    Carried on the value rather than beside it, because a statistic whose
    member set a reader cannot recover is exactly the unnamed ensemble number
    this project refuses. ``members_declared`` is what the family's registry
    record declares, ``members_used`` is what resolved a value, and
    ``members_missing`` names the shortfall wherever the identifiers are known
    (the shortfall is never filled with invented member ids). ``partial``
    follows from the two counts at the derive step and is carried so a reader
    need not recompute it.

    There is deliberately no run-staleness field here. Run staleness is
    ``Provenance.run_stale`` with ``Provenance.run_stale_reason``, added by the
    horizon-tiers change, and this model hangs off that same ``Provenance``: a
    second field would let one value say two things about one run.
    """

    family: str
    source_id: str
    run_time: datetime | None
    members_declared: int = Field(ge=0)
    members_used: int = Field(ge=0)
    members_missing: list[str] = Field(default_factory=list)
    #: Whether the control member entered the set. ``None`` where the family
    #: publishes no control, which is not the same as excluding one.
    control_included: bool | None = None
    partial: bool = False

    @field_validator("run_time")
    @classmethod
    def require_aware_run_time(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("timestamps must include an offset")
        return value

    @model_validator(mode="after")
    def counts_agree_with_the_partial_verdict(self) -> EnsembleMemberSet:
        if self.members_used > self.members_declared:
            raise ValueError(
                f"member_set_overcounts: {self.members_used} members used exceeds the {self.members_declared} the family declares"
            )
        if self.partial != (self.members_used < self.members_declared):
            raise ValueError(
                f"member_set_partial_mismatch: partial={self.partial} with {self.members_used} of {self.members_declared} members used"
            )
        return self


class EnsembleProvenance(StrictModel):
    """What makes one value an ensemble number: family, statistic, member set.

    ``statistic`` is null on a per-member value (that value is one member's
    own reading, not a summary of any set) and is one of the five registered
    entry names on a statistic. ``computed_here`` separates a statistic this
    deployment computed over members it can serve from a provider's own
    published reduction, which is ``retrieved`` and stays the provider's.

    ``refusal`` names the condition code the derive step failed
    (``one_family:``, ``one_run:``, ``provider_reduction_mixed``,
    ``averaged_with_instantaneous``, ``below_minimum:``, ``no_member_resolved``
    or a switch level). A refusal is not an absence, so it only ever appears on
    a field whose value is null and whose quality carries
    ``statistic_refused``.
    """

    family: str
    statistic: str | None
    computed_here: bool
    member_set: EnsembleMemberSet | None
    refusal: str | None = None
    quantile: float | None = Field(default=None, ge=0, le=1)
    threshold: float | None = None
    threshold_units: str | None = None
    comparison: Literal["ge", "gt", "le", "lt"] | None = None
    #: The window a time-averaged member field is a mean over (the GEFS
    #: six-hour-mean cloud). Null on an instantaneous field; never defaulted,
    #: because a stated window is the only thing that makes the mean readable.
    averaging_window_hours: float | None = Field(default=None, gt=0)

    @field_validator("statistic")
    @classmethod
    def a_statistic_names_a_registered_entry(cls, value: str | None) -> str | None:
        """The name is the registry entry's, never the umbrella and never a
        short name a reader would have to map back."""
        if value is not None and value not in ENSEMBLE_STATISTIC_ENTRIES:
            raise ValueError(f"unregistered_method: {value} is not one of {', '.join(ENSEMBLE_STATISTIC_ENTRIES)}")
        return value

    @model_validator(mode="after")
    def a_refusal_names_the_statistic_it_refused(self) -> EnsembleProvenance:
        if self.refusal is not None and self.statistic is None:
            raise ValueError("statistic_refused requires the statistic that was refused; a per-member value has nothing to refuse")
        return self


class Provenance(StrictModel):
    data_mode: DataMode = DataMode.FIXTURE
    operational: Literal[False] = False
    #: How this value came to exist. Required, with no default: a required
    #: field cannot be forgotten, so the failure mode is a validation error at
    #: publication rather than a silent promotion at read time.
    evidence_class: EvidenceClass
    source_id: str
    provider: str
    product: str
    forecast_centre: str
    run_time: datetime | None
    valid_time: datetime
    retrieval_time: datetime
    #: The provider's own identifier for the member this value came from, on a
    #: per-member value only. Null on a statistic and on every non-ensemble
    #: value: a member id on a summary would name one member as the family.
    member: str | None = None
    #: Whether that member is the family's control run. Null where the family
    #: publishes no control or the control cannot be identified; never
    #: defaulted to False, which would assert a perturbed member.
    member_control: bool | None = None
    vertical_level: str
    original_units: str
    normalized_units: str
    native_resolution: str
    native_crs: str
    quality: Quality
    coverage: Coverage
    freshness: Freshness
    licence: str
    attribution: str
    derivation: str | None = None
    derivation_version: str | None = None
    #: The registry entry's citation to the published construction it
    #: implements. A ``derived_here`` value names one; nothing else does.
    derivation_citation: str | None = None
    #: Every input the method read, each with its own provenance.
    derivation_inputs: list[DerivedInput] = Field(default_factory=list)
    #: How this source's values reach the deployment, read from its registry
    #: record. A record that declares no kind leaves this ``None`` rather than
    #: claiming the producer's own cell on the record's behalf.
    delivery_kind: DeliveryKind | None = None
    #: What the source's registry record says about being a display primary.
    #: It follows from the kind unless the record overrides it, so it is
    #: carried rather than recomputed: a record may refuse the primary for a
    #: reason no other field states.
    source_display_primary: bool | None = None
    #: For ``reprocessed`` and ``intermediary_derived``: the intermediary that
    #: stands between the producer and this deployment, and its own method
    #: where the intermediary documents one. ``provider`` remains the producer.
    intermediary: str | None = None
    intermediary_method: str | None = None
    adapter_version: str
    #: The coordinate of the grid cell the value was actually read from. On a
    #: 2.5 km rotated grid this is not the coordinate that was requested, and
    #: echoing the request back would overstate where the reading came from.
    sampled_latitude: float | None = None
    sampled_longitude: float | None = None
    #: Distance from the requested coordinate to that cell, in kilometres.
    sample_distance_km: float | None = None
    #: How the cell was chosen: ``rectilinear`` label selection, or
    #: ``curvilinear_nearest_cell`` index selection on a 2-D coordinate grid.
    #: Never an interpolation - one published cell, unmodified.
    sample_method: str | None = None
    contributing_evidence: list[str] = Field(default_factory=list)
    contributors: list[ContributorProvenance] = Field(default_factory=list)
    #: The latest valid time this deployment ever held for the stream, kept
    #: after the frames themselves are purged. It is what turns "the value is
    #: absent" into "we held it out to here and it aged out", so the reader is
    #: told the edge of what was ever available rather than merely that
    #: something is gone. Null on every value that is not an aged-out absence.
    last_valid_time: datetime | None = None
    #: Whether the run behind this value is older than twice its producer's
    #: declared run cadence. A separate fact from ``freshness``, which measures
    #: how long ago the artifact was retrieved: a value retrieved minutes ago can
    #: come from a run superseded twice since. ``null`` with a reason wherever
    #: the run time or the cadence is unknown, and on a source with no run.
    run_stale: bool | None = None
    run_stale_reason: str | None = None
    #: The family, statistic and member set behind an ensemble number. Null on
    #: every value that is not one. An ensemble value whose family cannot be
    #: read from its registry record carries no ``EnsembleProvenance`` and is
    #: not served at all (``ensemble_family_unknown``), because a number whose
    #: construction a reader cannot recover is not evidence.
    ensemble: EnsembleProvenance | None = None

    @field_validator("run_time", "valid_time", "retrieval_time", "last_valid_time")
    @classmethod
    def require_aware_time(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("timestamps must include an offset")
        return value

    @model_validator(mode="after")
    def aged_out_states_the_last_valid_time(self) -> Provenance:
        """``aged_out`` without a last valid time is a claim, not a report.

        A deployment that never held a frame must not say it held one and lost
        it, so the flag and the time stand or fall together. The absence with
        no recorded time is ``null``; a store that cannot be read reports
        ``unavailable`` and neither flag.
        """
        if AGED_OUT_FLAG in self.quality.flags and self.last_valid_time is None:
            raise ValueError("aged_out requires a recorded last_valid_time; without one the absence is null, not aged out")
        return self

    @model_validator(mode="after")
    def a_control_flag_names_the_member_it_describes(self) -> Provenance:
        """``member_control`` says something about *this* member.

        Without a ``member`` there is no member for it to be true of, and a
        control flag floating free would read as the family being the control.
        """
        if self.member_control is not None and self.member is None:
            raise ValueError("member_control requires member; a control flag with no member identifier names nothing")
        return self

    @model_validator(mode="after")
    def a_statistic_is_labelled_by_the_class_that_produced_it(self) -> Provenance:
        """A computed statistic is ``derived_here`` and names its entry.

        The three facts have to agree or the value lies about its own
        construction: the class says a number was built here, the derivation
        names the registered entry that built it, and ``computed_here`` says
        this deployment did the building. A provider's own reduction is the
        only way to carry a statistic with ``computed_here`` false, and it is
        ``retrieved`` because the provider published the cell.
        """
        ensemble = self.ensemble
        if ensemble is None:
            return self
        if ensemble.statistic is not None and ensemble.computed_here:
            if self.evidence_class != "derived_here":
                raise ValueError(
                    f"a statistic computed here is derived_here, not {self.evidence_class}: {ensemble.statistic}"
                )
            if self.derivation != ensemble.statistic:
                raise ValueError(
                    f"derivation must name the statistic entry: {self.derivation!r} does not name {ensemble.statistic!r}"
                )
        if not ensemble.computed_here and ensemble.statistic is not None and self.evidence_class != "retrieved":
            raise ValueError(
                f"a statistic not computed here is the provider's own published reduction and is retrieved, not {self.evidence_class}"
            )
        return self

    @model_validator(mode="after")
    def a_partial_member_set_is_flagged_on_the_quality(self) -> Provenance:
        """A short member set is told on the verdict, not only in the counts.

        A reader who switches on ``quality.flags`` must not have to open the
        member set to learn that the number covers fewer members than the
        family declares.
        """
        member_set = self.ensemble.member_set if self.ensemble is not None else None
        if member_set is not None and member_set.partial and PARTIAL_MEMBER_SET_FLAG not in self.quality.flags:
            raise ValueError(
                f"{PARTIAL_MEMBER_SET_FLAG} must be flagged where the member set is partial "
                f"({member_set.members_used} of {member_set.members_declared} members)"
            )
        return self

    @model_validator(mode="after")
    def a_refusal_is_flagged_as_a_refusal(self) -> Provenance:
        """A refusal is a fact about the request, and the flag is how a reader
        tells it apart from a field that is null because nothing was
        retrieved."""
        refusal = self.ensemble.refusal if self.ensemble is not None else None
        if refusal is not None and STATISTIC_REFUSED_FLAG not in self.quality.flags:
            raise ValueError(f"{STATISTIC_REFUSED_FLAG} must be flagged where a statistic was refused: {refusal}")
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def display_primary_eligible(self) -> bool:
        """Whether this value may be a field's display primary.

        Three things can refuse it and none can grant it alone: the evidence
        class (a reprocessed, intermediary-derived or uncalibrated value is
        shown beside the others, labelled, and never promoted over a
        producer's own published cell), the delivery kind (a value a third
        party transformed is not the producer's own cell either), and the
        source record's own `display_primary`, which a record may set false
        for a reason no other field states. Computed rather than stored so it
        can never disagree with what it is computed from.
        """
        if self.evidence_class not in PRIMARY_ELIGIBLE_CLASSES:
            return False
        if self.delivery_kind is not None and self.delivery_kind not in PRIMARY_ELIGIBLE_DELIVERY_KINDS:
            return False
        return self.source_display_primary is not False


class ArtifactManifest(StrictModel):
    """The evidence classes one published artifact declares it contains.

    Recorded per artifact so storage and QC gates can act on it without
    opening the data, and so sampling can exclude a display-only artifact by
    its class rather than by matching its logical name - the match that
    stopped matching when the name grew a layer suffix.

    ``evidence_class_by_variable`` is required whenever an artifact carries
    more than one class: a value's class is per value, and an artifact that
    declares two classes without saying which variable carries which cannot be
    resolved to a value's class at read time.
    """

    source_id: str
    logical_name: str
    evidence_classes: Annotated[list[EvidenceClass], Field(min_length=1)]
    evidence_class_by_variable: dict[str, EvidenceClass] = Field(default_factory=dict)

    @model_validator(mode="after")
    def declared_set_covers_its_values(self) -> ArtifactManifest:
        declared = set(self.evidence_classes)
        carried = set(self.evidence_class_by_variable.values())
        missing = sorted(carried - declared)
        if missing:
            raise ValueError(f"evidence_class_mismatch: values carry {', '.join(missing)}, which the manifest does not declare")
        return self

    def class_for(self, variable: str) -> EvidenceClass:
        """The class of one value, or a refusal that names why it is unknown."""
        stated = self.evidence_class_by_variable.get(variable)
        if stated is not None:
            return stated
        if len(set(self.evidence_classes)) == 1:
            return self.evidence_classes[0]
        raise ValueError(
            f"evidence_class_mismatch: {self.source_id}/{self.logical_name} declares "
            f"{', '.join(sorted(set(self.evidence_classes)))} and says nothing about {variable!r}"
        )


FieldValue = float | int | str | bool | list[float] | list[str] | None


# --- the field catalogue on a response ------------------------------------
# ``registry/fields.py`` is the single source of truth for keys, families,
# phase and comparability. Nothing here reaches into its tables; every answer
# comes back through its query surface, so a key this module cannot resolve is
# a key nothing may serve.

Phase = Literal["liquid", "mixed"]
Storage = Literal["stored", "available-not-stored", "not-published"]

#: API field names that are not themselves catalogue keys, and the key each
#: one is. The API speaks a shorter name than the catalogue for the fields it
#: has served since before the catalogue existed - ``temperature`` for the 2 m
#: air temperature, ``wind_speed`` for the 10 m wind - and the level is carried
#: separately in ``provenance.vertical_level``. Every other field name is a
#: catalogue key and resolves without an entry here.
CATALOGUE_KEY_BY_FIELD: dict[str, str] = {
    "temperature": "temperature_2m",
    "dew_point": "dew_point_2m",
    "relative_humidity": "relative_humidity_2m",
    "specific_humidity": "specific_humidity_2m",
    "wind_u": "wind_u_10m",
    "wind_v": "wind_v_10m",
    "wind_speed": "wind_speed_10m",
    "wind_direction": "wind_direction_10m",
    "wind_gust": "wind_gust_10m",
}


def catalogue_key_for(field_name: str) -> str | None:
    """The catalogue key an API field name stands for, or None where it has none.

    None is a refusal, not a default: a field the catalogue does not carry is
    not served (``uncatalogued_field``). The lookup goes through
    ``catalogue.resolve`` so a level-expanded artifact variable
    (``relative_humidity_850hPa``) answers with the one profile key, its level
    staying on the provenance rather than in the key.
    """
    candidate = CATALOGUE_KEY_BY_FIELD.get(field_name, field_name)
    try:
        return catalogue.resolve(candidate).key
    except catalogue.UnknownFieldKey:
        return None


class EvidenceField(StrictModel):
    """One served value, and where the catalogue files it.

    ``key`` is the catalogue key; ``field`` stays the API's own name for the
    quantity, which for most fields is the same string. ``family`` follows from
    the key and is never set independently - two names for one grouping is how
    ``total_cloud`` came to mean three quantities. ``phase`` is non-null only
    where the catalogue requires a phase (the humidity fields) and is read from
    ``catalogue.PHASE_ATTRIBUTE`` on the value, never assumed. ``storage`` says
    whether this deployment holds the field at all, so
    ``available-not-stored`` and ``not-published`` stay distinguishable from a
    reading that is simply absent.
    """

    field: str
    value: FieldValue
    provenance: Provenance
    #: None only where the field has no catalogue key, which is also the only
    #: case in which the value must be null with ``uncatalogued_field`` set.
    key: str | None = None
    family: str | None = None
    phase: Phase | None = None
    storage: Storage = "stored"

    @model_validator(mode="after")
    def resolve_against_the_catalogue(self) -> EvidenceField:
        if self.key is None:
            self.key = catalogue_key_for(self.field)
        if self.key is None:
            if self.phase is not None or self.family is not None:
                raise ValueError(f"uncatalogued_field: {self.field} has no catalogue key and cannot carry a family or a phase")
            return self
        try:
            entry = catalogue.field(self.key)
        except catalogue.UnknownFieldKey:
            raise ValueError(f"uncatalogued_field: {self.key} is not a catalogue key") from None
        # Derived, never carried: a family stated beside a key is a second
        # place for the grouping to be wrong.
        self.family = entry.family
        if self.phase is not None and not entry.phase_attribute:
            raise ValueError(f"{self.key} is not a phase-bearing field and must not carry phase={self.phase!r}")
        return self

    @model_validator(mode="after")
    def a_refused_statistic_carries_no_number(self) -> EvidenceField:
        """A refusal and a value cannot both be true of one field.

        The refusal says the request was not answerable; a number beside it
        would be a value computed over whatever subset happened to pass, which
        is the thing the one-family, one-run rule exists to prevent. This is
        checked here rather than on ``Provenance`` because the value lives on
        the field.
        """
        ensemble = self.provenance.ensemble
        if ensemble is not None and ensemble.refusal is not None and self.value is not None:
            raise ValueError(
                f"statistic_refused: {self.field} was refused ({ensemble.refusal}) and must carry no value"
            )
        return self


class FieldComparability(StrictModel):
    """Whether two served members of one family may be drawn as one thing.

    One entry per unordered pair of served members within a family, from
    ``catalogue.comparability``. ``a`` and ``b`` are catalogue keys; where two
    sources serve the same key the pair names that key twice, which is the
    case the catalogue answers ``true`` for. ``reason`` and ``detail`` are null
    exactly when ``comparable`` is true.
    """

    family: str
    a: str
    b: str
    comparable: bool
    reason: str | None = None
    detail: str | None = None


def field_comparability(fields: Sequence[EvidenceField]) -> list[FieldComparability]:
    """Pairwise comparability over the served members, family by family.

    The humidity rule needs an air temperature to say which side of 273.16 K a
    pair sits on, so the served 2 m air temperature is passed to every pair.
    Where none was served the catalogue answers ``phase`` with the reason that
    no temperature was supplied, rather than assuming the pair is comparable.
    """
    served = [item for item in fields if item.key is not None and item.family is not None]
    temperature_k: float | None = None
    for item in served:
        if item.key == "temperature_2m" and isinstance(item.value, (int, float)) and not isinstance(item.value, bool):
            temperature_k = float(item.value) + 273.15
            break

    by_family: dict[str, list[EvidenceField]] = {}
    for item in served:
        by_family.setdefault(str(item.family), []).append(item)

    pairs: list[FieldComparability] = []
    for family_name in sorted(by_family):
        members = by_family[family_name]
        seen: set[tuple[str, str]] = set()
        for index, left in enumerate(members):
            for right in members[index + 1:]:
                first, second = (left, right) if str(left.key) <= str(right.key) else (right, left)
                pair = (str(first.key), str(second.key))
                if pair in seen:
                    continue
                seen.add(pair)
                result = catalogue.comparability(
                    pair[0], pair[1],
                    phase_a=first.phase, phase_b=second.phase, temperature_k=temperature_k,
                )
                pairs.append(FieldComparability(family=family_name, a=pair[0], b=pair[1], **result.as_dict()))
    return pairs


class SourceFieldEntry(StrictModel):
    """What one source does about one catalogue field, from the catalogue.

    ``storage`` is the answer the interface needs to tell three different
    things apart: the deployment holds it, the producer publishes it and the
    deployment does not fetch it, and the producer does not publish it at all.
    """

    key: str
    family: str
    storage: Storage
    upstream: str | None = None
    note: str = ""


class SourceRecord(StrictModel):
    """One catalogue entry. Derived from ``registry/source_data.py`` in every
    mode: the registry is a checked-in declaration of what may be retrieved, not
    retrieved evidence, so publishing it is honest regardless of data mode."""

    id: str
    category: str
    producer: str
    product: str
    state: SourceState
    status_reason: str
    role: str
    #: How this source's values reach the deployment, and who stands between
    #: the producer and this deployment when anyone does. A catalogue reader
    #: can then tell a producer's own cell from an aggregator's rendering of
    #: it without opening a value.
    delivery_kind: DeliveryKind | None = None
    intermediary: str | None = None
    #: Whether this source's values may be a field's display primary, as the
    #: record declares it. Never inferred from the id or the producer.
    display_primary: bool = True
    may_enter_consensus: bool
    #: Every catalogue field this source is mapped onto, with what the
    #: deployment does about each. Read from ``catalogue.source_mapping``, so a
    #: field the producer publishes and this deployment does not fetch is
    #: visible here rather than absent.
    fields: list[SourceFieldEntry] = Field(default_factory=list)
    exact_variables: list[str]
    levels: list[str]
    geographic_coverage: str
    cadence: str
    forecast_horizon: str
    authentication: str
    licence: str
    attribution: str
    caching: str
    archival: str
    redistribution: str
    schema_version: str
    freshness_threshold_seconds: Annotated[int, Field(gt=0)] | None = None
    documentation_url: str
    access_endpoint: str
    integration: str
    schedulable: bool
    fixture_status: Literal["passing", "missing", "not_applicable", "planned", "blocked"]
    live_smoke_status: Literal["not_run", "passing", "failing", "credential_required", "planned", "blocked", "not_applicable"]


class CatalogResponse(StrictModel):
    experimental: Literal[True] = True
    data_mode: DataMode = DataMode.FIXTURE
    operational: Literal[False] = False
    generated_at: datetime
    sources: list[SourceRecord]


class HorizonTier(StrictModel):
    """One of the two horizon tiers, as a valid-time range.

    A tier names no source and excludes none. It says only which range of
    valid time the reader is looking at; what can answer inside it is the
    source's own declared reach, tested per instant.
    """

    id: Literal["core", "planning"]
    start: datetime
    end: datetime


class CoverageEntry(StrictModel):
    """One retained run covering one instant.

    ``run_time`` is the adapter-declared run time, or ``null`` where the
    adapter declared none - the retrieval instant recorded beside the run is
    never promoted into this field. ``run_stale`` is ``null``, with a reason,
    whenever the run time or the producer cadence cannot be resolved: false
    would be a claim that the run is current, which is exactly what is not
    known.
    """

    source_id: str
    provider_run_id: str
    run_time: datetime | None = None
    run_cadence_seconds: int | None = None
    run_age_seconds: int | None = None
    run_stale: bool | None = None
    run_stale_reason: str | None = None


class TimelineItem(StrictModel):
    valid_time_utc: datetime
    valid_time_newfoundland: datetime
    available_products: list[str]
    #: Sources whose frames this deployment held and purged when their valid
    #: times left the window, each with the last valid time it reached. An
    #: hour with no products and no aged-out source is an hour nothing ever
    #: covered; without this the two read identically.
    aged_out_sources: dict[str, datetime] = Field(default_factory=dict)
    #: Which of the two tier ranges this instant falls in. Never a filter on
    #: what may cover it.
    tier: Literal["core", "planning"] | None = None
    #: Every retained run whose declared reach contains this instant and which
    #: actually published frames spanning it, sorted by source then run time.
    #: Empty means nothing covers it - never that coverage was not resolved,
    #: which ``coverage_notice`` and the response notices say instead.
    coverage: list[CoverageEntry] = Field(default_factory=list)
    #: Set only when the store answered and nothing covers this instant.
    coverage_notice: str | None = None


class TimelineResponse(StrictModel):
    data_mode: DataMode = DataMode.FIXTURE
    operational: Literal[False] = False
    start: datetime
    end: datetime
    items: list[TimelineItem]
    notices: list[str] = Field(default_factory=list)
    #: The instant the core tier ends and the planning tier begins.
    boundary: datetime | None = None
    #: The two tiers as ranges, core first.
    tiers: list[HorizonTier] = Field(default_factory=list)


class LayerFrame(StrictModel):
    """One published frame, with the run that produced it.

    Frame staleness and run staleness are two separate facts, and this is the
    second one: a frame can sit well inside its layer's tolerance and still come
    from a run that has been superseded twice. ``run_stale`` never withholds the
    frame - a stale run that is the only evidence is still the only evidence -
    and it is ``null``, never ``false``, wherever the run time or the producer
    cadence is unknown.
    """

    valid_time: datetime
    run_time: datetime | None = None
    provider_run_id: str | None = None
    run_stale: bool | None = None


class LayerRunSummary(StrictModel):
    """One run standing behind a layer's frames.

    A short cycle leaves two runs in one index - the newest run serving the
    leads it reaches, the previous one the leads it does not - and this is where
    the index shows them as two rather than as one merged time axis.
    """

    provider_run_id: str
    run_time: datetime | None = None
    run_stale: bool | None = None
    frame_count: int


class Layer(StrictModel):
    id: str
    title: str
    kind: Literal["raster", "point", "line", "alert", "mask"]
    field: str
    product: str
    units: str
    semantics: str
    #: Exactly the valid times this layer published, at its own cadence. Empty
    #: means the artifact carries no time coordinate, never that it covers all
    #: hours: a client must not synthesise frames for a layer that declared none.
    times: list[datetime] = Field(default_factory=list)
    #: Modal gap between consecutive frames. ``None`` below two frames.
    cadence_seconds: int | None = None
    #: How far a requested time may sit from the nearest published frame before
    #: the layer must report unavailable. Beyond this a client renders nothing;
    #: quietly showing the nearest older frame would misdate the evidence.
    staleness_tolerance_seconds: int
    default_opacity: float = 0.85
    #: Draw order within the stack, low to high. Observations sit above fields
    #: so a station reading is never hidden under a raster.
    z_index: int = 0
    #: Where this layer's evidence comes from, and the single field a client
    #: must read before presenting it as evidence.
    #:
    #: ``published_artifact``
    #:     Times and values were read from an artifact the worker fetched,
    #:     validated against a manifest, QC-gated and published atomically.
    #: ``live_proxy``
    #:     Times were read from the upstream service at request time and the
    #:     imagery is rendered upstream on demand. Nothing is stored, nothing
    #:     passed ingest QC, and no value from it is sampled by ``/point`` or
    #:     counted in ``/timeline``. Display evidence, not audited evidence, and
    #:     an interface must say so where a reader can see it.
    evidence_basis: Literal["published_artifact", "live_proxy"] = "published_artifact"
    #: Where a layer index should file this layer. Derived here from
    #: ``evidence_basis`` and ``kind`` so a client never has to infer it from
    #: the shape of an id. ``satellite`` is observed imagery relayed live:
    #: frames exist only for the past and it is never a forecast.
    #: ``rendered_grid`` is a published-model forecast raster rendered by this
    #: experiment itself from a retrieved grid artifact - stored values at
    #: their native cells, nearest-neighbor, never smoothed - as opposed to
    #: imagery rendered upstream by a provider.
    group: Literal["forecast_proxy", "published_model", "observation", "alert", "satellite", "rendered_grid"] = "published_model"
    #: True when ``/layers/{id}/raster`` will serve an image for this layer.
    #: False means the 501 stands, with its reason.
    raster_available: bool = False
    #: True when ``/layers/{id}/legend`` will serve the upstream colour ramp.
    legend_available: bool = False
    #: The upstream WMS layer imagery is drawn from, when there is one. Read
    #: from the artifact's own recorded provenance or from the proxied layer's
    #: declaration; never guessed.
    upstream_wms_layer: str | None = None
    upstream_endpoint: str | None = None
    #: The run time of the newest run standing behind this layer's frames, or
    #: ``null`` where none is known. Only ever the adapter's own declaration.
    run_time: datetime | None = None
    #: Whether that run is older than twice its producer's declared run cadence.
    #: ``null`` with a reason wherever the run time or the cadence cannot be
    #: resolved, and on an observation layer, which has no run concept at all.
    #: Never a reason to withhold the layer or any of its frames.
    run_stale: bool | None = None
    #: Why ``run_stale`` is ``null``. Set whenever it is, so an unknown verdict
    #: always says which half of the comparison was missing.
    run_stale_reason: str | None = None
    #: The producer's declared run cadence, read from the registry record.
    run_cadence_seconds: int | None = None
    #: One entry per entry of ``times``, in the same order, naming the run that
    #: produced each frame. Where two runs stand behind one layer, this is what
    #: keeps them apart; a client must not draw a value across a run change.
    frames: list[LayerFrame] = Field(default_factory=list)
    #: The runs behind those frames, newest first, each with how many frames of
    #: this layer it answers for.
    runs: list[LayerRunSummary] = Field(default_factory=list)


class LayersResponse(StrictModel):
    data_mode: DataMode = DataMode.FIXTURE
    operational: Literal[False] = False
    layers: list[Layer]
    notices: list[str] = Field(default_factory=list)
    #: Sources whose frames were held here and purged when they left the
    #: window, each with the last valid time reached. Present so an empty
    #: layer index can be read as "the evidence aged out" rather than as
    #: "nothing was ever drawn here".
    aged_out_sources: dict[str, datetime] = Field(default_factory=dict)


class MethodScore(StrictModel):
    """One method's measured skill for one layer's variable, as published.

    Every field here is read out of a motion artifact's provenance. A score
    that was not measured is absent, never a zero - a method with no scores
    has not been derived against real frames yet, which is a different fact
    from a method that was measured and lost.
    """

    layer_id: str
    source_id: str
    variable: str
    held_out_frames: int
    #: Improvement over the same construction with its motion reversed. Kept
    #: as the motion veto's own number; it cannot rank methods against each
    #: other because the control moves with the method.
    improvement_over_reversed_flow: float
    #: Fixed-control skill: improvement over a plain crossfade of the same
    #: two frames, and over plain linear advection of them. These rank
    #: methods, because the control does not move with the method.
    improvement_over_crossfade: float
    improvement_over_advection: float | None = None
    midpoint_mae_percent: float
    midpoint_ssim: float | None = None
    #: Structure scores at the midpoint: sharpness relative to the real frame
    #: (1.0 = as sharp as real; pointwise error alone rewards blur) and the
    #: radial power-spectrum log-ratio error against it.
    midpoint_sharpness_ratio: float | None = None
    midpoint_spectral_ratio_error: float | None = None
    #: Midpoint error stratified by what the cell did between the frames.
    midpoint_mae_grew: float | None = None
    midpoint_mae_decayed: float | None = None
    advect_weight_median: float | None = None
    derivation_version: str | None = None
    #: Which of the method's measured options the derive actually applied on
    #: this layer, by option name. Every False here is a switch the harness
    #: refused on this variable's own held-out frames.
    applied: dict[str, bool] = Field(default_factory=dict)
    #: True where this method drew the default construction on this layer -
    #: an unmet requirement, or every option refused - so a reader who picks
    #: it is told rather than left to wonder whether the control did anything.
    reduced_to_default: bool = False


class MethodRequirement(StrictModel):
    """One thing a method needs before it can differ from the baseline.

    A method whose ingredient this deployment lacks is not broken - it
    reduces to another construction by design. But a reader who selects it
    and sees no change is owed the reason, because a control that appears to
    do something must do it.
    """

    name: str
    met: bool
    detail: str = ""
    #: The per-method provenance diagnostic the API read `met` from, when it
    #: had one. Empty where the method answered for itself.
    diagnostic: str = ""


class InterpolationMethodItem(StrictModel):
    """One entry in the interpolation bench."""

    id: str
    title: str
    summary: str
    #: The client construction these fields are meant for.
    shader: str
    enabled: bool
    #: True where the disclosure must say the pixels were generated rather
    #: than retrieved. Never true without an owner-approved carve-out.
    generative: bool = False
    #: Reader-facing copy, server-supplied so the menu never paraphrases a
    #: construction: one plain sentence, one sentence on what it cannot show,
    #: and the cited science behind it.
    plain: str = ""
    gap: str = ""
    notes: str = ""
    #: True when this deployment's kill switch (WEATHER_GENERATED_DISPLAY=off)
    #: refuses this generative method, so it is neither derived nor offered.
    generation_disabled: bool = False
    #: Whether any currently published motion artifact carries this method.
    published: bool = False
    #: Unmet requirements are why a selected method may draw the same picture
    #: the baseline does. Empty means it works with what it is handed.
    requirements: list[MethodRequirement] = Field(default_factory=list)
    scores: list[MethodScore] = Field(default_factory=list)


class MethodsResponse(StrictModel):
    data_mode: DataMode = DataMode.FIXTURE
    operational: Literal[False] = False
    default_method: str
    methods: list[InterpolationMethodItem]
    notices: list[str] = Field(default_factory=list)


class Selection(StrictModel):
    mode: Literal["consensus", "fallback", "evidence_only"]
    selected_source_id: str | None
    selected_product_id: str | None
    badge: str
    reason: str


class PointResponse(StrictModel):
    data_mode: DataMode = DataMode.FIXTURE
    operational: Literal[False] = False
    latitude: float
    longitude: float
    valid_time: datetime
    selection: Selection
    fields: list[EvidenceField]
    notices: list[str] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def comparability(self) -> list[FieldComparability]:
        """Which served members of a family may be drawn as one thing.

        Computed from the fields actually served rather than stored beside
        them, so it can never describe a set of members the response does not
        carry.
        """
        return field_comparability(self.fields)


class ProfileLevel(StrictModel):
    pressure_hpa: int
    fields: list[EvidenceField]


class ProfileResponse(StrictModel):
    data_mode: DataMode = DataMode.FIXTURE
    operational: Literal[False] = False
    latitude: float
    longitude: float
    valid_time: datetime
    levels: list[ProfileLevel]
    notices: list[str] = Field(default_factory=list)


class Coordinate(StrictModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class CrossSectionRequest(StrictModel):
    path: Annotated[list[Coordinate], Field(min_length=2, max_length=100)]
    valid_time: datetime | None = None
    fields: list[str] = Field(default_factory=lambda: ["temperature", "relative_humidity", "wind_speed"])


class CrossSectionSample(StrictModel):
    coordinate: Coordinate
    distance_km: float
    levels: list[ProfileLevel]


class CrossSectionResponse(StrictModel):
    data_mode: DataMode = DataMode.FIXTURE
    operational: Literal[False] = False
    valid_time: datetime
    samples: list[CrossSectionSample]


class SourceStatus(StrictModel):
    source_id: str
    state: SourceState
    data_mode: DataMode = DataMode.FIXTURE
    operational: Literal[False] = False
    last_retrieval: datetime | None
    freshness: Freshness
    detail: str


class SourceStatusResponse(StrictModel):
    data_mode: DataMode = DataMode.FIXTURE
    operational: Literal[False] = False
    statuses: list[SourceStatus]
    notices: list[str] = Field(default_factory=list)


class RefreshRequest(StrictModel):
    source_ids: list[str] = Field(default_factory=list)


class JobState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class Job(StrictModel):
    id: str
    state: JobState
    created_at: datetime
    updated_at: datetime
    source_ids: list[str]
    detail: str
    operational_ingestion: Literal[False] = False


class HealthResponse(StrictModel):
    status: Literal["ok"]
    experimental: Literal[True] = True
    data_mode: DataMode = DataMode.FIXTURE
    operational: Literal[False] = False
    time: datetime


class ReadyResponse(StrictModel):
    data_mode: DataMode = DataMode.FIXTURE
    operational: Literal[False] = False
    ready: bool
    checks: dict[str, bool]
    #: Sources whose frames this deployment held and purged, each with the
    #: last valid time it reached. A store holding only aged-out frames is not
    #: ready, and saying so as aged out rather than as never retrieved is the
    #: difference between "ingestion has stopped" and "ingestion never ran".
    aged_out_sources: dict[str, datetime] = Field(default_factory=dict)
    notices: list[str] = Field(default_factory=list)


class ErrorResponse(StrictModel):
    detail: str


# --- space weather --------------------------------------------------------
# Planetary quantities: served with times, ages and provider statuses, never
# with a coordinate, a sample distance, or an invented value. An absent feed is
# an absent series with a notice; a stale feed says so with its age.


class SpaceWeatherReading(StrictModel):
    """One retrieved series value at the feed's own instant.

    ``status`` is the provider's own per-value label (``observed`` |
    ``estimated`` | ``predicted``) on the Kp forecast series, exactly as the
    feed declared it; ``None`` everywhere the provider declared none. A null
    ``value`` is a gap in the feed, never zero.
    """

    time: datetime
    value: float | None
    status: str | None = None


class SpaceWeatherSeries(StrictModel):
    """A planetary index series, or its honest absence."""

    available: bool
    source_id: str
    product: str
    readings: list[SpaceWeatherReading] = Field(default_factory=list)
    freshness: Freshness
    notices: list[str] = Field(default_factory=list)


class SolarWindLatest(StrictModel):
    """The newest retrieved solar-wind magnetometer reading, with its instant.

    ``measured_at`` is the instant the served ``bz_gsm_nt`` was measured -
    the newest record carrying a finite Bz, never a gap filled with zero.
    ``feed_declared_spacecraft`` is whatever the feed's own source field said,
    verbatim; no spacecraft is ever named beyond that.
    """

    available: bool
    source_id: str
    product: str
    bz_gsm_nt: float | None
    bt_nt: float | None
    measured_at: datetime | None
    feed_declared_spacecraft: str | None
    freshness: Freshness
    notices: list[str] = Field(default_factory=list)


class SpaceWeatherResponse(StrictModel):
    data_mode: DataMode
    operational: Literal[False] = False
    generated_at: datetime
    kp_observed: SpaceWeatherSeries
    kp_forecast: SpaceWeatherSeries
    solar_wind: SolarWindLatest
    notices: list[str] = Field(default_factory=list)


# --- astronomy ------------------------------------------------------------


class AstronomyInterval(StrictModel):
    """One labelled interval over the evidence window."""

    kind: str
    start: datetime
    end: datetime


class AstronomyMoon(StrictModel):
    rise: datetime | None
    set: datetime | None
    above_horizon: list[AstronomyInterval]
    phase_deg: float
    illuminated_fraction: float


class AstronomyCoreWindow(StrictModel):
    """The geometric Milky Way core window: geometry only, never blended."""

    windows: list[AstronomyInterval]
    max_altitude_deg: float
    caption: str


class AstronomyProvenance(StrictModel):
    source_id: str
    kernel_id: str
    kernel_sha256: str
    derivation: str
    derivation_version: str
    operational: Literal[False] = False


class AstronomyResponse(StrictModel):
    data_mode: DataMode
    operational: Literal[False] = False
    latitude: float
    longitude: float
    window_start: datetime
    window_end: datetime
    valid_time: datetime
    sun_altitude_deg: float
    moon_altitude_deg: float
    core_altitude_deg: float
    twilight_bands: list[AstronomyInterval]
    moon: AstronomyMoon
    milky_way_core: AstronomyCoreWindow
    provenance: AstronomyProvenance | None
    notices: list[str]
