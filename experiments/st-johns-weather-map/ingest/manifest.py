"""Fail-closed run validation.

Every adapter used to hard-code ``complete=True, qc_passed=True`` and a
``"quality": {"status": "passed"}`` provenance literal. That is precisely how a
run whose fields were silently skipped reached publication labelled complete
and QC-passed. This module removes the possibility: an adapter declares what a
usable run *must* contain, hands the assembled dataset and its own decode
failures to :func:`validate_run`, and takes whatever comes back.

The one-way rule is deliberate. ``complete=False`` is a hard stop with no
downgrade path back to publishable: :class:`ValidationResult` is frozen, the
only mutator (:meth:`ValidationResult.failing`) can lower a verdict and never
raise one, and ``weather_experiment.publish_run`` refuses the run outright.
There is no such thing as a partially published run in this experiment.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

_EXPERIMENT_ROOT = Path(__file__).resolve().parent.parent
if str(_EXPERIMENT_ROOT) not in sys.path:  # registry/ ships beside ingest/ in both images
    sys.path.insert(0, str(_EXPERIMENT_ROOT))

from registry import fields as catalogue  # noqa: E402

from .validate import MAX_REPORTED_OUT_OF_WINDOW, NO_STEP_IN_WINDOW, out_of_window_verdict  # noqa: E402,F401

UTC = timezone.utc

# Coordinate names an adapter may legitimately produce; anything else means the
# dataset was never normalized and must not be judged against a manifest.
_TIME_NAMES = ("valid_time", "time")
_LATITUDE_NAMES = ("latitude", "lat", "y")
_LONGITUDE_NAMES = ("longitude", "lon", "x")

#: The ensemble member axis (``ingest.grib.stack_members``) and the boolean
#: coordinate along it that flags the control member.
_MEMBER_NAMES = ("member",)
_CONTROL_COORD = "control"

#: A field averaged over a time window declares it here. ``cell_methods`` is
#: the CF attribute ``ingest.grib.declare_time_average`` stamps.
TIME_MEAN_CELL_METHODS = "time: mean"
AVERAGING_WINDOW_ATTRIBUTE = "averaging_window_hours"

#: The two storage scopes, spelled exactly as ``registry/fields.py``
#: ``SOURCE_SCOPE`` spells them, because the registry's ensemble declaration
#: copies those values and the two must never drift into synonyms.
SCOPE_EVERY_PUBLISHED_FIELD = "every_published_field"
SCOPE_FAMILY_FIELDS_ONLY = "family_fields_only"
STORAGE_SCOPES: tuple[str, ...] = (SCOPE_EVERY_PUBLISHED_FIELD, SCOPE_FAMILY_FIELDS_ONLY)

#: Failure names the storage-scope rules raise on a run.
SCOPE_UNSTATED = "storage_scope_unstated"
SCOPE_INCOMPLETE = "scope_incomplete"


#: The six evidence classes, mirrored from ``api.weather_api.models`` so the
#: worker image - which does not ship the API package - can validate against
#: them. Kept as one list in both places on purpose: a manifest that declares a
#: class the API cannot model would publish and then fail at read time.
EVIDENCE_CLASSES: tuple[str, ...] = (
    "retrieved",
    "reprocessed",
    "derived_here",
    "intermediary_derived",
    "generated_display",
    "uncalibrated_observation",
)


class ManifestError(ValueError):
    """A manifest is self-contradictory; the adapter, not the data, is wrong."""


@dataclass(frozen=True)
class RequiredField:
    """One catalogue field a run must carry to be worth publishing.

    ``name`` is a **catalogue key** (``registry.fields``), not a convention the
    adapter invented. That is the whole change: three adapters used to declare
    a field called ``total_cloud`` and two of them were not the same quantity,
    because a manifest name meant only what its author remembered it to mean.
    A name the catalogue does not carry raises here, at import time, so the
    adapter is never schedulable rather than publishing a colliding key. A
    level-expanded name a GRIB adapter writes one variable per level for
    (``relative_humidity_850hPa``) resolves to its one profile key.

    ``units`` is the *normalized* unit the experiment stores, not the
    provider's, and it must be the unit the catalogue declares: a mismatch is
    the adapter contradicting the catalogue and is refused here. A mismatch
    between the catalogue and what the *data* carries is a QC failure instead,
    raised by :func:`validate_run`, because the data arrived and does not mean
    what the rest of the stack assumes.

    ``evidence_class`` is how this field's values came to exist. An adapter
    fetches what the producer issued, so ``retrieved`` is the default here and
    only here: a derivation or a display construction states its own class,
    and a publisher that says nothing has said "the producer issued this",
    which is a claim the audit can check rather than an inference.
    """

    name: str
    units: str
    level: str = "surface"
    optional: bool = False
    evidence_class: str = "retrieved"

    def __post_init__(self) -> None:
        if self.evidence_class not in EVIDENCE_CLASSES:
            raise ManifestError(f"{self.name}: {self.evidence_class!r} is not one of the six evidence classes")
        try:
            resolved = catalogue.resolve(self.name)
        except catalogue.UnknownFieldKey:
            raise ManifestError(
                f"uncatalogued_field:{self.name}: the field catalogue carries no key {self.name!r}, "
                "so this manifest cannot be validated and the adapter is not schedulable"
            ) from None
        expected = resolved.field.units
        if expected is not None and self.units != expected:
            raise ManifestError(
                f"bad_units:{self.name}: the catalogue declares {expected!r} and this manifest "
                f"declares {self.units!r}"
            )
    @property
    def catalogue_field(self) -> "catalogue.Field":
        """The catalogue entry this field declares. Resolution already succeeded."""
        return catalogue.resolve(self.name).field


@dataclass(frozen=True)
class RunManifest:
    """The contract one adapter promises for one run."""

    source_id: str
    fields: tuple[RequiredField, ...]
    required_valid_times: tuple[datetime, ...] = ()
    min_coverage_fraction: float = 1.0
    bounds: Mapping[str, float] | None = None
    #: The set of evidence classes this artifact declares it contains. Left
    #: empty it is the set its own fields declare, which is what an adapter
    #: publishing only retrieved fields means. Stated explicitly it must agree
    #: with those fields: a manifest that understates its classes is refused
    #: with ``evidence_class_mismatch`` rather than published.
    evidence_classes: tuple[str, ...] = ()
    #: How many members the registry declares for this family, or ``None`` for
    #: a deterministic source. Stated here so completeness is judged against the
    #: declaration rather than against whatever happened to decode.
    member_count: int | None = None
    #: The provider's own identifier for the control member, or ``None`` where
    #: the family publishes no control. The control is a flagged member on the
    #: same axis, never a field beside the members and never a second artifact.
    control: str | None = None
    #: The storage scope the registry declares for this family, one of
    #: :data:`STORAGE_SCOPES`, or ``None`` for a source whose scope nobody has
    #: declared. ``None`` on an ensemble family is itself the defect
    #: :data:`SCOPE_UNSTATED` names: a family whose subsettability is undeclared
    #: retrieves nothing rather than defaulting to either scope.
    storage_scope: str | None = None

    def __post_init__(self) -> None:
        if self.storage_scope is not None and self.storage_scope not in STORAGE_SCOPES:
            raise ManifestError(
                f"{self.source_id}: storage scope {self.storage_scope!r} is not one of "
                f"{', '.join(STORAGE_SCOPES)}"
            )
        if self.member_count is not None and self.member_count < 1:
            raise ManifestError(f"{self.source_id}: a declared member count must be at least 1")
        if self.control is not None and not str(self.control).strip():
            raise ManifestError(f"{self.source_id}: a declared control needs the provider's own identifier")
        if not self.fields:
            raise ManifestError(f"{self.source_id}: a manifest must declare at least one field")
        for name in self.evidence_classes:
            if name not in EVIDENCE_CLASSES:
                raise ManifestError(f"{self.source_id}: {name!r} is not one of the six evidence classes")
        if not 0.0 < self.min_coverage_fraction <= 1.0:
            raise ManifestError(f"{self.source_id}: min_coverage_fraction must fall in (0, 1]")
        names = [field.name for field in self.fields]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise ManifestError(f"{self.source_id}: duplicate declared fields: {', '.join(duplicates)}")
        for moment in self.required_valid_times:
            if moment.tzinfo is None:
                raise ManifestError(f"{self.source_id}: required valid times must carry an offset")

    @property
    def mandatory(self) -> tuple[RequiredField, ...]:
        return tuple(field for field in self.fields if not field.optional)

    @property
    def declared_classes(self) -> tuple[str, ...]:
        """The class set this artifact publishes, in a stable order."""
        stated = self.evidence_classes or tuple(field.evidence_class for field in self.fields)
        return tuple(sorted(set(stated)))

    @property
    def class_by_field(self) -> dict[str, str]:
        """Each declared field's own class, for the artifact's manifest block."""
        return {field.name: field.evidence_class for field in self.fields}

    def as_manifest_block(self) -> dict[str, Any]:
        """The class declaration an artifact records in its own provenance.

        This is the block ``weather_api.store`` reads to admit or exclude an
        artifact and to give each sampled value its class, so it is produced
        here rather than assembled by hand in each adapter. Splat it into the
        provenance dict an adapter builds.
        """
        return declared_classes(self.declared_classes, by_variable=self.class_by_field)


def declared_classes(classes: Sequence[str], *, by_variable: Mapping[str, str] | None = None) -> dict[str, Any]:
    """The class declaration for an artifact that has no run manifest.

    A derived or display construction stages its own artifact without an
    adapter's manifest, and it still has to say what its values are. The
    classes are checked here rather than at read time, because an artifact
    that declares a class the contract does not know is isolated by the API
    and answers null - a defect worth catching where it is written.
    """
    declared = tuple(dict.fromkeys(classes))
    if not declared:
        raise ManifestError("an artifact declares at least one evidence class")
    for name in (*declared, *(by_variable or {}).values()):
        if name not in EVIDENCE_CLASSES:
            raise ManifestError(f"{name!r} is not one of the six evidence classes")
    undeclared = sorted({name for name in (by_variable or {}).values() if name not in declared})
    if undeclared:
        raise ManifestError(f"evidence_class_mismatch: values carry {', '.join(undeclared)}, which the artifact does not declare")
    return {"evidence_classes": sorted(declared), "evidence_class_by_variable": dict(by_variable or {})}


#: How the control member was retrieved, from the adapter's access shape.
#: ``same_file`` is IFS ENS, whose control is message ``number=0`` in the member
#: file; ``separate_file`` is AIFS-ENS, whose control is a whole separate ``cf``
#: object; ``separate_coverage`` is a per-member WCS coverage such as REPS. The
#: value never changes what lands on the axis - the control is one flagged
#: member either way - it records what had to be fetched to put it there, so a
#: run missing its control can be read against the retrieval that failed.
CONTROL_RETRIEVALS = ("same_file", "separate_file", "separate_coverage")


@dataclass(frozen=True)
class MemberReport:
    """What the member axis of one run actually held, against what was declared.

    ``declared`` is the registry's count and is ``None`` only where a manifest
    declared none, which for an ensemble family is itself a defect. ``present``
    is read off the dataset's own ``member`` coordinate - never from the request
    that was issued - and ``missing`` names the identifiers that did not arrive,
    including the control when it did not. ``control`` is the declared control's
    identifier, which stays named even when it is the thing that is missing, and
    ``control_retrieval`` is one of :data:`CONTROL_RETRIEVALS` or ``None`` where
    the family publishes no control or the adapter stated no shape.
    """

    declared: int | None = None
    present: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()
    control: str | None = None
    control_retrieval: str | None = None


@dataclass(frozen=True)
class StorageScopeReport:
    """Which storage scope one run applied, and what the scope left behind.

    The difference between the two scopes is the whole storage story, so it is
    recorded rather than inferred at read time. ``available_not_stored`` holds
    the producer's own upstream names - a WCS coverage id, a GRIB record label -
    because that is what a reader would have to go and fetch to get the field,
    and a catalogue key would not name the thing that exists upstream. It is a
    deliberate exclusion: the field is published, this deployment does not keep
    it, nobody is missing anything they were promised.

    ``not_retrieved`` holds **catalogue keys**, because these are fields inside
    the applied scope that should have arrived and did not. That is a gap, not
    an exclusion, and the two are kept in separate lists precisely so a reader
    is never asked to tell them apart by eye.
    """

    applied: str
    available_not_stored: tuple[str, ...] = ()
    not_retrieved: tuple[str, ...] = ()

    def as_provenance(self) -> dict[str, Any]:
        """The storage-scope block an artifact records in its own provenance."""
        return {
            "applied": self.applied,
            "available_not_stored": list(self.available_not_stored),
            "not_retrieved": list(self.not_retrieved),
        }


def apply_storage_scope(
    source_id: str,
    *,
    scope: str,
    published: Sequence[str] = (),
    retrieved: Sequence[str] = (),
) -> StorageScopeReport:
    """Apply one family's declared storage scope to one retrieval.

    ``published`` and ``retrieved`` are the producer's own upstream names: what
    the producer advertises for this product, and what the retrieval actually
    brought back. They are resolved to catalogue keys through
    ``registry.fields.key_for_upstream``, which is the one place that mapping
    lives; nothing here re-derives which fields a source stores.

    Under ``every_published_field`` there is nothing to leave behind: the source
    subsets server side, so wire and stored are the same set. A published name
    that was not retrieved is therefore the adapter contradicting its own scope,
    and is refused here rather than published as a thin run - the adapter, not
    the data, is wrong.

    Under ``family_fields_only`` the catalogue's ``stored`` mapping decides.
    Every other published name is listed as ``available-not-stored``, and every
    key the catalogue maps ``stored`` for this source that the retrieval did not
    bring is listed as ``not_retrieved`` for :func:`validate_run` to publish the
    run incomplete against.

    A scope value outside :data:`STORAGE_SCOPES`, and a source the catalogue
    declares no scope for at all, are both refused: where the subsettability
    declaration is absent nothing is retrieved for that family, which is not the
    same as quietly picking one of the two scopes.
    """
    if scope not in STORAGE_SCOPES:
        raise ManifestError(
            f"{source_id}: storage scope {scope!r} is not one of {', '.join(STORAGE_SCOPES)}"
        )
    declared = catalogue.source_scope(source_id)
    if declared is None:
        raise ManifestError(
            f"{source_id}: the field catalogue declares no storage scope for this source, so the "
            f"{scope!r} scope cannot be applied and nothing is retrieved for it"
        )
    if declared.policy != scope:
        raise ManifestError(
            f"{source_id}: the manifest applies {scope!r} and the field catalogue declares "
            f"{declared.policy!r}; a scope is declared once and copied, never chosen twice"
        )

    published_names = tuple(dict.fromkeys(str(name) for name in published))
    retrieved_names = tuple(dict.fromkeys(str(name) for name in retrieved))

    if scope == SCOPE_EVERY_PUBLISHED_FIELD:
        absent = tuple(name for name in published_names if name not in retrieved_names)
        if absent:
            raise ManifestError(
                f"{source_id}: {scope} stores every published field and "
                f"{', '.join(absent)} was published and not retrieved; a subsetting source has no "
                "available-not-stored list to put it on"
            )
        return StorageScopeReport(applied=scope)

    stored_keys = tuple(
        item.key for item in catalogue.source_mapping(source_id) if item.storage == "stored"
    )
    arrived = {
        key
        for key in (catalogue.key_for_upstream(source_id, name) for name in retrieved_names)
        if key is not None
    }
    available = tuple(
        name
        for name in published_names
        if catalogue.key_for_upstream(source_id, name) not in set(stored_keys)
    )
    return StorageScopeReport(
        applied=scope,
        available_not_stored=available,
        not_retrieved=tuple(key for key in stored_keys if key not in arrived),
    )


@dataclass(frozen=True)
class ValidationResult:
    """The verdict on one assembled run. Never constructed by hand in adapters."""

    complete: bool
    qc_passed: bool
    coverage_fraction: float
    flags: tuple[str, ...]
    detail: str
    #: Advisory items that do not lower the verdict. The one this change adds is
    #: ``uncatalogued_upstream_field``: a producer advertising a field the
    #: catalogue does not know must not stop the fields it does know from
    #: publishing, and must not be silently skipped either. The name is carried
    #: through provenance so the registry audit can list it until someone
    #: extends the catalogue.
    notices: tuple[str, ...] = ()
    #: What the run's member axis held, or ``None`` for a deterministic run that
    #: has no member axis and declared no members.
    members: MemberReport | None = None
    #: Which storage scope was applied and what it left behind, or ``None`` for
    #: a run whose manifest declared no scope.
    storage_scope: StorageScopeReport | None = None

    @property
    def publishable(self) -> bool:
        return self.complete and self.qc_passed

    def failing(self, flag: str, detail: str, *, qc: bool = False) -> ValidationResult:
        """Lower this verdict. There is deliberately no inverse operation."""
        return replace(
            self,
            complete=False,
            qc_passed=self.qc_passed and not qc,
            flags=tuple(dict.fromkeys((*self.flags, flag))),
            detail="; ".join(part for part in (self.detail, detail) if part),
        )

    def noting(self, notice: str) -> ValidationResult:
        """Record something a reader must be told without judging the run for it."""
        return replace(self, notices=tuple(dict.fromkeys((*self.notices, notice))))

    def as_quality(self) -> dict[str, Any]:
        """Provenance quality block. ``passed`` is only ever earned, never set."""
        if not self.qc_passed:
            status = "failed"
        elif not self.complete:
            status = "suspect"
        else:
            status = "passed"
        block: dict[str, Any] = {"status": status, "flags": list(self.flags), "detail": self.detail}
        if self.notices:
            block["notices"] = list(self.notices)
        return block

    def as_members(self) -> dict[str, Any] | None:
        """The member provenance block, or ``None`` for a deterministic run.

        ``control_retrieval`` is the access shape the adapter stated when it
        called :func:`validate_run`; this module cannot infer it, so an adapter
        that states nothing gets ``None`` rather than a guess. Everything else
        is the identity and the arithmetic completeness was judged on.
        """
        if self.members is None:
            return None
        return {
            "declared": self.members.declared,
            "present": list(self.members.present),
            "missing": list(self.members.missing),
            "control": self.members.control,
            "control_retrieval": self.members.control_retrieval,
        }

    def as_storage_scope(self) -> dict[str, Any] | None:
        """The storage-scope provenance block, beside ``as_members``.

        ``None`` where the manifest declared no scope, which for a deterministic
        source is simply the question not arising and for an ensemble family is
        the QC failure :data:`SCOPE_UNSTATED` already recorded on the flags.
        """
        if self.storage_scope is None:
            return None
        return self.storage_scope.as_provenance()

    def as_coverage(self) -> dict[str, Any]:
        if self.coverage_fraction <= 0.0:
            status = "outside"
        elif self.complete:
            status = "complete"
        else:
            status = "partial"
        return {"status": status, "fraction": round(self.coverage_fraction, 4)}


def _coordinate_name(dataset: Any, candidates: Sequence[str]) -> str | None:
    for name in candidates:
        if name in getattr(dataset, "coords", {}) or name in getattr(dataset, "dims", ()):
            return name
    return None


def _as_naive_utc64(moment: datetime) -> Any:
    import numpy  # noqa: PLC0415

    return numpy.datetime64(moment.astimezone(UTC).replace(tzinfo=None), "ns")


def _field_coverage(variable: Any) -> float:
    """Fraction of cells carrying an actual number rather than a fill value."""
    import numpy  # noqa: PLC0415

    values = numpy.asarray(variable.values)
    if values.size == 0:
        return 0.0
    if not numpy.issubdtype(values.dtype, numpy.floating):
        return 1.0
    return float(numpy.count_nonzero(numpy.isfinite(values))) / float(values.size)


# --- the member axis (Seam B) ----------------------------------------------
#
# Everything below reads the dataset's own ``member`` coordinate and the boolean
# ``control`` coordinate along it, which ``ingest.grib.stack_members`` writes.
# Member completeness is computed from what was decoded, never asserted from the
# request that was issued, which is why nothing here consults the adapter.


def _member_identifiers(dataset: Any) -> tuple[str, ...] | None:
    """The member identifiers this dataset carries, or ``None`` for no axis."""
    name = _coordinate_name(dataset, _MEMBER_NAMES)
    if name is None:
        return None
    coords = getattr(dataset, "coords", {})
    if name not in coords:  # a bare dimension with no identifiers is not a member axis
        return ()
    return tuple(str(value) for value in coords[name].values.ravel().tolist())


def _flagged_control(dataset: Any, identifiers: Sequence[str]) -> tuple[str, ...]:
    """The identifiers whose ``control`` coordinate is true."""
    coords = getattr(dataset, "coords", {})
    if _CONTROL_COORD not in coords:
        return ()
    flags = coords[_CONTROL_COORD].values.ravel().tolist()
    return tuple(identifier for identifier, flag in zip(identifiers, flags) if bool(flag))


def _stated_averaging_window(variable: Any) -> float | None:
    """The numeric averaging window on a variable, or ``None`` if it states none."""
    try:
        hours = float(variable.attrs.get(AVERAGING_WINDOW_ATTRIBUTE))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if hours != hours or hours <= 0.0:  # NaN or a window that is not a window
        return None
    return hours


# One flag per offending step, capped: a badly-bounded run can carry hundreds,
# and the flag list is meant to be read by a person. Kept as an alias so the
# adapters and tests that import it from here still resolve; the cap itself now
# lives beside the window gate in ``ingest.validate``.
_MAX_REPORTED_OUT_OF_WINDOW = MAX_REPORTED_OUT_OF_WINDOW


UNCATALOGUED_UPSTREAM = "uncatalogued_upstream_field"


def uncatalogued_upstream(names: Iterable[str], *, source_id: str | None = None) -> tuple[str, ...]:
    """The upstream names in ``names`` that no catalogue key claims.

    A GeoMet source is subset server side, so the scope rule is "every field the
    producer publishes". That makes a newly advertised coverage a real event: it
    must neither block the fields the catalogue does know, nor vanish. This
    returns the names to carry as notices, and the caller passes them to
    :func:`validate_run`.

    ``names`` are the producer's own names - WCS coverage ids, GRIB record
    labels - so with a ``source_id`` they are resolved through that source's
    field mapping. Without one, they are read as catalogue keys, which is what a
    caller that has already canonicalised them wants.
    """
    unknown: list[str] = []
    for name in names:
        if source_id is not None and catalogue.key_for_upstream(source_id, name) is not None:
            continue
        try:
            catalogue.resolve(name)
        except catalogue.UnknownFieldKey:
            unknown.append(name)
    return tuple(dict.fromkeys(unknown))


def _judge_members(
    result: ValidationResult,
    manifest: RunManifest,
    dataset: Any,
    *,
    declared_members: Sequence[str] = (),
    control_retrieval: str | None = None,
) -> ValidationResult:
    """Judge the run's member axis against what the registry declared.

    A run that retrieved fewer members than declared publishes partial with the
    missing members named; a run that retrieved none does not publish at all,
    because an ensemble artifact with no members is not a thin ensemble but an
    absent one. Both are completeness failures rather than QC failures: the data
    that arrived is not wrong, there is less of it than was promised.

    The control is judged separately, because a set of the declared size with no
    control in it is a different failure from a short set: it means the
    unperturbed run is the member that did not arrive, and nothing may quietly
    flag another member in its place.
    """
    present = _member_identifiers(dataset)
    declared = tuple(str(item) for item in declared_members)

    if control_retrieval is not None and control_retrieval not in CONTROL_RETRIEVALS:
        raise ManifestError(
            f"{manifest.source_id}: control_retrieval {control_retrieval!r} is not one of "
            f"{', '.join(CONTROL_RETRIEVALS)}"
        )

    if present is None and manifest.member_count is None and manifest.control is None:
        return result  # a deterministic run; there is no member axis to judge

    identifiers = present or ()
    flagged = _flagged_control(dataset, identifiers)
    missing = tuple(item for item in declared if item not in identifiers)

    if manifest.member_count is not None and not identifiers:
        result = result.failing(
            "no_members",
            f"{manifest.source_id} declares {manifest.member_count} members and the dataset carries none; "
            "an ensemble artifact with no members is an absent ensemble, not a thin one",
        )
    elif manifest.member_count is not None and (len(identifiers) < manifest.member_count or missing):
        named = ",".join(missing) if missing else f"{len(identifiers)}/{manifest.member_count}"
        result = result.failing(
            f"partial_members:{named}",
            f"{manifest.source_id} declares {manifest.member_count} members and "
            f"{len(identifiers)} arrived ({', '.join(identifiers) or 'none'})",
        )

    if manifest.control is not None and not flagged:
        result = result.failing(
            f"control_missing:{manifest.control}",
            f"{manifest.source_id} declares control member {manifest.control!r} and no member carries the "
            "control flag; the control is a flagged member and is never defaulted onto another one",
        )
        if manifest.control not in missing and manifest.control not in identifiers:
            missing = (*missing, manifest.control)

    return replace(
        result,
        members=MemberReport(
            declared=manifest.member_count,
            present=identifiers,
            missing=missing,
            control=manifest.control,
            control_retrieval=control_retrieval if manifest.control is not None else None,
        ),
    )


def _judge_storage_scope(
    result: ValidationResult,
    manifest: RunManifest,
    dataset: Any,
    *,
    published: Sequence[str] = (),
    retrieved: Sequence[str] = (),
) -> ValidationResult:
    """Apply the manifest's declared scope and record what it left behind.

    An ensemble family that states no scope fails QC rather than publishing:
    the scope is what tells a reader whether a field they cannot find was
    deliberately excluded or silently lost, and a member artifact with neither
    answer is the silent gap this module exists to rule out. A deterministic
    source that states no scope is not judged here at all, which is what keeps
    every existing adapter validating exactly as before.

    "An ensemble family" is read as: this run carries a member axis or declares
    members, **and** the field catalogue declares a scope for its source. Every
    one of the six families is in ``SOURCE_SCOPE``, so the gate covers all of
    them; a member-shaped fixture over a source the catalogue has never heard of
    is not a family whose scope anyone could have declared, and is left alone
    rather than failed for a declaration that has no home.
    """
    if manifest.storage_scope is None:
        ensemble = (
            manifest.member_count is not None
            or manifest.control is not None
            or _member_identifiers(dataset) is not None
        )
        if ensemble and catalogue.source_scope(manifest.source_id) is not None:
            result = result.failing(
                SCOPE_UNSTATED,
                f"{manifest.source_id} carries a member axis and declares no storage scope; "
                "without one a field that is absent cannot be told from a field that was "
                "deliberately not stored",
                qc=True,
            )
        return result

    report = apply_storage_scope(
        manifest.source_id,
        scope=manifest.storage_scope,
        published=published,
        retrieved=retrieved,
    )
    if report.not_retrieved:
        result = result.failing(
            f"{SCOPE_INCOMPLETE}:{','.join(report.not_retrieved)}",
            f"{manifest.source_id} applies the {report.applied} scope and did not retrieve "
            f"{', '.join(report.not_retrieved)}, which the scope requires; this is distinct from "
            "the fields the scope excluded on purpose",
        )
    return replace(result, storage_scope=report)


def _judge_averaging_windows(result: ValidationResult, dataset: Any) -> ValidationResult:
    """Refuse any time-averaged field that does not state its own window.

    A mean of 50 percent over an unknown window is one sky at half cover or two
    skies, one clear and one overcast, and nothing downstream can tell which. So
    an unstated window is a contract violation rather than a gap: the field
    arrived and does not mean what a reader would take it to mean.
    """
    for name, variable in dict(getattr(dataset, "data_vars", {})).items():
        methods = str(variable.attrs.get("cell_methods", "")).strip()
        if methods != TIME_MEAN_CELL_METHODS:
            continue
        if _stated_averaging_window(variable) is None:
            result = result.failing(
                f"averaging_window_unstated:{name}",
                f"{name} is a time mean and carries no numeric {AVERAGING_WINDOW_ATTRIBUTE}; "
                "the window is read from the producer's own record and is never assumed from the lead",
                qc=True,
            )
    return result


def validate_run(
    manifest: RunManifest,
    dataset: Any,
    *,
    window: Any,
    decode_errors: Iterable[str] = (),
    upstream_fields: Iterable[str] = (),
    declared_members: Sequence[str] = (),
    control_retrieval: str | None = None,
    retrieved_fields: Sequence[str] = (),
) -> ValidationResult:
    """Judge one assembled run against its manifest.

    ``decode_errors`` is the list of variables or URLs the adapter failed to
    read. Adapters used to swallow those with ``except Exception: continue``;
    passing them here is what turns a silent gap into a refused publication.

    ``upstream_fields`` is what the producer advertised for this product, by the
    producer's own name. Any of them the catalogue does not carry is reported as
    ``uncatalogued_upstream_field`` and does not lower the verdict: the run
    publishes what it knows and names what it does not, which is the opposite of
    the silent skip this module exists to rule out.

    ``declared_members`` is the registry's list of member identifiers for the
    family. The manifest carries only the count, so an adapter that can name the
    members it expected passes them here and the missing ones are named rather
    than counted; an adapter that cannot gets the shortfall as a ratio.

    ``control_retrieval`` is the adapter's own access shape, one of
    :data:`CONTROL_RETRIEVALS`. It is stated rather than inferred because only
    the adapter knows whether the control arrived in the member file, in a
    separate file or as a separate coverage; it is carried into provenance and
    changes nothing about the axis itself.

    ``retrieved_fields`` is what the retrieval actually brought back, again by
    the producer's own name. Together with ``upstream_fields`` - which is what
    the producer *publishes* - it is what the declared storage scope is applied
    to, so ``available-not-stored`` names a deliberate exclusion and
    ``scope_incomplete`` names a field inside the scope that did not arrive.
    Both lists are the producer's names, never the adapter's request, for the
    same reason the member axis is read off the dataset.
    """
    result = ValidationResult(complete=True, qc_passed=True, coverage_fraction=0.0, flags=(), detail="")

    # Materialised once: the same list is read again by the storage-scope rules
    # below, and a generator would arrive there already exhausted.
    published_fields = tuple(upstream_fields)

    for name in uncatalogued_upstream(published_fields, source_id=manifest.source_id):
        result = result.noting(f"{UNCATALOGUED_UPSTREAM}:{name}")

    data_vars = dict(getattr(dataset, "data_vars", {}))

    # A crop that produced no grid is not a thin run, it is the wrong domain.
    for axis, names in (("latitude", _LATITUDE_NAMES), ("longitude", _LONGITUDE_NAMES)):
        coord_name = _coordinate_name(dataset, names)
        if coord_name is None:
            result = result.failing(f"missing_axis:{axis}", f"dataset has no {axis} coordinate")
            continue
        if int(getattr(dataset[coord_name], "size", 0)) == 0:
            result = result.failing(f"empty_grid:{axis}", f"{axis} dimension is empty; the bbox crop matched nothing")

    # A manifest that understates the classes it contains is refused before
    # anything is published: the class is what a data path admits or excludes
    # on, so an artifact whose declaration disagrees with its values would let
    # a generated value through a gate that read the declaration and believed
    # it. A contract violation, so it fails QC rather than completeness.
    if manifest.evidence_classes:
        undeclared = sorted({field.evidence_class for field in manifest.fields} - set(manifest.evidence_classes))
        for name in undeclared:
            result = result.failing(
                f"evidence_class_mismatch:{name}",
                f"the manifest declares {', '.join(manifest.evidence_classes)} and a declared field carries {name}",
                qc=True,
            )

    coverages: list[float] = []
    for field in manifest.fields:
        if field.name not in data_vars:
            if field.optional:
                continue
            result = result.failing(f"missing_field:{field.name}", f"{field.name} is absent from the run")
            continue

        variable = data_vars[field.name]
        coverage = _field_coverage(variable)
        if not field.optional:
            coverages.append(coverage)
        if coverage <= 0.0:
            result = result.failing(f"empty_field:{field.name}", f"{field.name} is present but entirely missing values")

        # A value may state its own class in its attributes. Where it does, it
        # is the value speaking, and the manifest is checked against it rather
        # than the other way round.
        carried = str(variable.attrs.get("evidence_class", "")).strip()
        if carried and carried != field.evidence_class:
            result = result.failing(
                f"evidence_class_mismatch:{field.name}:{carried}",
                f"{field.name} carries evidence class {carried!r}, not the declared {field.evidence_class!r}",
                qc=True,
            )
        got = str(variable.attrs.get("units", "")).strip()
        if got != field.units:
            result = result.failing(
                f"bad_units:{field.name}:{got or 'unset'}",
                f"{field.name} carries units {got or 'unset'!r}, not the normalized {field.units!r}",
                qc=True,
            )

        # The catalogue says which classes a field may carry at all: Sun
        # altitude is never retrieved, a producer's own cloud cover is never
        # derived here. A declaration outside that set is a contract violation,
        # not a gap, so it fails QC. Checked here rather than at declaration
        # because a manifest is allowed to be built with a wrong class on
        # purpose - the mismatch gate above exists to catch exactly that - and
        # the run, not the constructor, is what must refuse to publish.
        if field.catalogue_field.evidence_class_refused(field.evidence_class):
            result = result.failing(
                f"evidence_class_not_permitted:{field.name}:{field.evidence_class}",
                f"the catalogue does not allow evidence class {field.evidence_class!r} on "
                f"{field.name}; it allows {', '.join(field.catalogue_field.evidence_classes)}",
                qc=True,
            )

        # A humidity value without its phase cannot be weighed. HRDPS divides
        # by saturation over liquid water at every temperature and GFS by a
        # mixed-phase saturation ramping from ice at 253.16 K, so at -25 degC
        # they differ by about 24 percent for identical air. A threshold
        # calibrated on one is not valid on the other, which makes an unstamped
        # humidity a contract violation rather than a gap.
        if field.catalogue_field.phase_attribute:
            convention = str(variable.attrs.get(catalogue.PHASE_ATTRIBUTE, "")).strip()
            phase = catalogue.phase_from_convention(convention)
            if phase is None:
                result = result.failing(
                    f"missing_phase:{field.name}",
                    f"{field.name} carries {catalogue.PHASE_ATTRIBUTE}="
                    f"{convention or 'unset'!r}, which is not one of the measured saturation "
                    "conventions the catalogue maps to a phase; a threshold calibrated on one "
                    "phase is not transferable to the other",
                    qc=True,
                )

    for item in decode_errors:
        result = result.failing(f"decode_error:{item}", f"could not decode {item}")

    # --- the member axis, the averaging window and the storage scope (Seam B)
    #
    # Deliberately three self-contained blocks: the member axis is judged from
    # the dataset, the scope from the producer's own name lists, and neither
    # reads the other's verdict.
    result = _judge_members(
        result, manifest, dataset, declared_members=declared_members, control_retrieval=control_retrieval
    )
    result = _judge_averaging_windows(result, dataset)
    result = _judge_storage_scope(
        result, manifest, dataset, published=published_fields, retrieved=retrieved_fields
    )

    time_name = _coordinate_name(dataset, _TIME_NAMES)

    # Every step must sit inside the declared evidence boundary. Checking only
    # that the REQUIRED times are present would let a run carry extra steps
    # outside it: the API samples the nearest step within an hour, so an
    # out-of-window step can surface as if it answered the question asked, and
    # it consumes the 64 GiB cap for evidence nothing may display. This is a
    # contract violation rather than a gap, so it fails QC, not completeness.
    #
    # The bounds and the flag shape live in ``ingest.validate``, which reads
    # the one window definition in ``weather_api.config``. Restating them here
    # is what let the ingestion window and the API window drift apart before.
    if time_name is not None and window is not None:
        import numpy  # noqa: PLC0415

        stamps = numpy.asarray(dataset[time_name].values).ravel().astype("datetime64[ns]").astype("int64")
        verdict = out_of_window_verdict(stamps.tolist(), window)
        for flag, detail in verdict.flags:
            result = result.failing(flag, detail, qc=True)

    if manifest.required_valid_times:
        if time_name is None:
            result = result.failing("missing_axis:valid_time", "dataset has no time coordinate to check leads against")
        else:
            import numpy  # noqa: PLC0415

            # Compare as integer nanoseconds so a resolution difference between
            # the coordinate and the manifest can never read as a missing lead.
            present = set(numpy.asarray(dataset[time_name].values).ravel().astype("datetime64[ns]").astype("int64").tolist())
            for moment in manifest.required_valid_times:
                stamp = int(_as_naive_utc64(moment).astype("int64"))
                if stamp not in present:
                    iso = moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
                    result = result.failing(f"missing_valid_time:{iso}", f"required valid time {iso} is absent")

    fraction = (sum(coverages) / len(coverages)) if coverages else 0.0
    result = replace(result, coverage_fraction=fraction)
    if fraction < manifest.min_coverage_fraction:
        result = result.failing(
            f"coverage_below_threshold:{fraction:.4f}<{manifest.min_coverage_fraction:.4f}",
            f"coverage {fraction:.4f} is below the declared minimum {manifest.min_coverage_fraction:.4f}",
        )

    if result.publishable:
        result = replace(result, detail=f"{manifest.source_id}: all declared fields present, in units, and covered")
    return result


def required_leads(
    window: Any,
    run_time: datetime,
    *,
    step_hours: int = 1,
    max_lead_hours: int = 24,
) -> tuple[datetime, ...]:
    """Every valid time inside ``window`` a run of ``run_time`` must supply.

    Adapters call this so ``required_valid_times`` states the run's own leads
    rather than an assumption about the clock.
    """
    from datetime import timedelta  # noqa: PLC0415

    if step_hours <= 0:
        raise ManifestError("lead step must be positive")
    moments = []
    for lead in range(0, max_lead_hours + 1, step_hours):
        moment = run_time + timedelta(hours=lead)
        if window.covers(moment):
            moments.append(moment)
    return tuple(moments)
