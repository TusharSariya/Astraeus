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


class ManifestError(ValueError):
    """A manifest is self-contradictory; the adapter, not the data, is wrong."""


@dataclass(frozen=True)
class RequiredField:
    """One canonical variable a run must carry to be worth publishing.

    ``units`` is the *normalized* unit the experiment stores, not the
    provider's. A mismatch is a QC failure rather than an incompleteness:
    the data arrived, but it does not mean what the rest of the stack assumes.
    """

    name: str
    units: str
    level: str = "surface"
    optional: bool = False


@dataclass(frozen=True)
class RunManifest:
    """The contract one adapter promises for one run."""

    source_id: str
    fields: tuple[RequiredField, ...]
    required_valid_times: tuple[datetime, ...] = ()
    min_coverage_fraction: float = 1.0
    bounds: Mapping[str, float] | None = None

    def __post_init__(self) -> None:
        if not self.fields:
            raise ManifestError(f"{self.source_id}: a manifest must declare at least one field")
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
