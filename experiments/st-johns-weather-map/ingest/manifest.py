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

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence

UTC = timezone.utc

# Coordinate names an adapter may legitimately produce; anything else means the
# dataset was never normalized and must not be judged against a manifest.
_TIME_NAMES = ("valid_time", "time")
_LATITUDE_NAMES = ("latitude", "lat", "y")
_LONGITUDE_NAMES = ("longitude", "lon", "x")


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
    """One canonical variable a run must carry to be worth publishing.

    ``units`` is the *normalized* unit the experiment stores, not the
    provider's. A mismatch is a QC failure rather than an incompleteness:
    the data arrived, but it does not mean what the rest of the stack assumes.

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

    def __post_init__(self) -> None:
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


@dataclass(frozen=True)
class ValidationResult:
    """The verdict on one assembled run. Never constructed by hand in adapters."""

    complete: bool
    qc_passed: bool
    coverage_fraction: float
    flags: tuple[str, ...]
    detail: str

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

    def as_quality(self) -> dict[str, Any]:
        """Provenance quality block. ``passed`` is only ever earned, never set."""
        if not self.qc_passed:
            status = "failed"
        elif not self.complete:
            status = "suspect"
        else:
            status = "passed"
        return {"status": status, "flags": list(self.flags), "detail": self.detail}

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


# One flag per offending step, capped: a badly-bounded run can carry hundreds,
# and the flag list is meant to be read by a person.
_MAX_REPORTED_OUT_OF_WINDOW = 5


def validate_run(
    manifest: RunManifest,
    dataset: Any,
    *,
    window: Any,
    decode_errors: Iterable[str] = (),
) -> ValidationResult:
    """Judge one assembled run against its manifest.

    ``decode_errors`` is the list of variables or URLs the adapter failed to
    read. Adapters used to swallow those with ``except Exception: continue``;
    passing them here is what turns a silent gap into a refused publication.
    """
    result = ValidationResult(complete=True, qc_passed=True, coverage_fraction=0.0, flags=(), detail="")

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

    for item in decode_errors:
        result = result.failing(f"decode_error:{item}", f"could not decode {item}")

    time_name = _coordinate_name(dataset, _TIME_NAMES)

    # Every step must sit inside the declared evidence boundary. Checking only
    # that the REQUIRED times are present would let a run carry extra steps
    # outside it: the API samples the nearest step within an hour, so an
    # out-of-window step can surface as if it answered the question asked, and
    # it consumes the 25 GiB cap for evidence nothing may display. This is a
    # contract violation rather than a gap, so it fails QC, not completeness.
    if time_name is not None and window is not None:
        start, end = getattr(window, "start", None), getattr(window, "end", None)
        if start is not None and end is not None:
            import numpy  # noqa: PLC0415

            low = _as_naive_utc64(start).astype("int64")
            high = _as_naive_utc64(end).astype("int64")
            stamps = numpy.asarray(dataset[time_name].values).ravel().astype("datetime64[ns]").astype("int64")
            outside = sorted({int(value) for value in stamps.tolist() if value < low or value > high})
            for value in outside[:_MAX_REPORTED_OUT_OF_WINDOW]:
                # .item() on datetime64[ns] yields an int, not a datetime:
                # nanoseconds exceed datetime's microsecond resolution.
                iso = numpy.datetime64(value, "ns").astype("datetime64[s]").item().strftime("%Y-%m-%dT%H:%M:%SZ")
                result = result.failing(f"out_of_window:{iso}", f"valid time {iso} falls outside the evidence window", qc=True)
            if len(outside) > _MAX_REPORTED_OUT_OF_WINDOW:
                remaining = len(outside) - _MAX_REPORTED_OUT_OF_WINDOW
                result = result.failing(f"out_of_window:+{remaining}_more", f"{remaining} further step(s) fall outside the evidence window", qc=True)

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
