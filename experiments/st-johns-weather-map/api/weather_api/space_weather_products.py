"""``GET /space-weather/products``: every published space-weather series, read back.

The ten space-weather series sources (Kp, one-minute Kp, Hp30, Dst, the L1
magnetometer and plasma feeds, the propagated wind, GOES magnetometer and
X-ray, NOAA scales, alerts) are stored on a bare time axis, or time times one
platform axis, and none of them may ever be localized. This module reads them
back through the one path ``LiveStore.read_series`` provides and reports, per
artifact, exactly what the store holds: scope, evidence class, producer and
intermediary, the retrieval receipts, the stored dimensions, each variable's
units and latest finite value, the newest instant and freshness against the
registry threshold.

Honesty rules:

- The listing is built from ``current_artifacts`` filtered by provenance
  (``native_crs == "not_applicable"`` marks a coordinate-free series), never
  by logical name. The OVATION grid is a field and is served by sampling.
- An artifact that cannot be read is reported under ``skipped`` with the
  reason; it is never dropped silently and nothing is substituted for it.
- Freshness is judged from the feed's own newest instant, except for issued
  text products (``measurement_scope: issued``), where a quiet week is not a
  stale feed: their age is the age of the retrieval.
- Fixture mode answers unavailable: no fixture space weather exists.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Mapping

from pydantic import Field

from .models import DataMode, Freshness, StrictModel
from .store import LiveStore, SeriesData

LOGGER = logging.getLogger(__name__)

SERIES_CRS = "not_applicable"
ISSUED_SCOPE = "issued"


class SpaceWeatherLatestValue(StrictModel):
    """The newest finite value of one stored variable, with its instant.

    ``label`` is the platform label (spacecraft, satellite, day offset) the
    value belongs to on a platform-axis series, verbatim; None on a plain
    series. ``value`` is a number, a flag meaning or a text product exactly
    as stored; ``time`` is the instant the feed gave it.
    """

    variable: str
    label: str | None = None
    units: str
    value: float | str | None
    time: datetime | None


class SpaceWeatherProduct(StrictModel):
    """One published coordinate-free space-weather artifact, as stored."""

    source_id: str
    logical_name: str
    revision_id: str
    provider_run_id: str | None = None
    product: str
    producer: str
    intermediary: dict[str, Any] | None = None
    measurement_scope: str
    evidence_classes: list[str] = Field(default_factory=list)
    display_primary: bool
    adapter_version: str | None = None
    retrieval: list[dict[str, Any]] = Field(default_factory=list)
    quality: dict[str, Any] = Field(default_factory=dict)
    structural_validation: dict[str, Any] = Field(default_factory=dict)
    coverage: dict[str, Any] = Field(default_factory=dict)
    dimensions: dict[str, list[str]] = Field(default_factory=dict)
    record_count: int
    newest_instant: datetime | None
    retrieved_at: datetime | None
    freshness: Freshness
    freshness_basis: str
    latest: list[SpaceWeatherLatestValue] = Field(default_factory=list)
    notices: list[str] = Field(default_factory=list)


class SpaceWeatherSkipped(StrictModel):
    source_id: str
    logical_name: str
    reason: str


class SpaceWeatherProductsResponse(StrictModel):
    data_mode: DataMode
    operational: bool = False
    generated_at: datetime
    products: list[SpaceWeatherProduct] = Field(default_factory=list)
    skipped: list[SpaceWeatherSkipped] = Field(default_factory=list)
    notices: list[str] = Field(default_factory=list)


def unavailable_products(reference: datetime, reason: str) -> SpaceWeatherProductsResponse:
    return SpaceWeatherProductsResponse(data_mode=DataMode.UNAVAILABLE, generated_at=reference, notices=[reason])


def _latest_values(series: SeriesData) -> list[SpaceWeatherLatestValue]:
    """The newest non-gap value per served variable, with the instant it carries."""
    latest: list[SpaceWeatherLatestValue] = []
    for served_name, variable in series.variables.items():
        name, _, label = served_name.partition("@")
        found: tuple[datetime, float | str] | None = None
        for index in range(len(variable.values) - 1, -1, -1):
            value = variable.values[index]
            if value is None:
                continue
            found = (series.times[index], value)
            break
        latest.append(
            SpaceWeatherLatestValue(
                variable=name,
                label=label or None,
                units=variable.units,
                value=None if found is None else found[1],
                time=None if found is None else found[0],
            )
        )
    return latest


def _threshold(source_id: str, registry_threshold: Any) -> int | None:
    try:
        return registry_threshold(source_id)
    except Exception:  # pragma: no cover - registry read is best effort here
        LOGGER.debug("registry threshold unavailable for %s", source_id, exc_info=True)
        return None


def _newest_finite_instant(series: SeriesData) -> datetime | None:
    """The newest instant at which any variable carries a non-gap value."""
    for index in range(len(series.times) - 1, -1, -1):
        if any(variable.values[index] is not None for variable in series.variables.values()):
            return series.times[index]
    return None


def product_from_series(series: SeriesData, reference: datetime, threshold: int | None) -> SpaceWeatherProduct:
    provenance: Mapping[str, Any] = series.provenance
    scope = str(provenance.get("measurement_scope") or "undeclared")
    newest = _newest_finite_instant(series)
    notices: list[str] = []
    if scope == ISSUED_SCOPE:
        anchor = series.retrieved_at
        basis = "age of the retrieval; an issued product is not stale because nothing was issued"
    else:
        anchor = newest
        basis = "age of the newest instant carrying a value"
    age = int((reference - anchor).total_seconds()) if anchor is not None else None
    freshness = Freshness.evaluate(age, threshold)
    if freshness.status == "stale":
        notices.append(f"{series.logical_name}: {age} s past the anchor, beyond the {threshold} s registry threshold; served stale, not as current")
    if newest is None:
        notices.append(f"{series.logical_name}: no instant carries a value; every variable is a gap")
    if scope == "undeclared":
        notices.append(f"{series.logical_name}: the artifact declares no measurement scope")
    classes = [str(name) for name in (provenance.get("evidence_classes") or [])]
    display_primary = bool(provenance.get("display_primary", "reprocessed" not in classes))
    return SpaceWeatherProduct(
        source_id=series.source_id,
        logical_name=series.logical_name,
        revision_id=series.revision_id,
        provider_run_id=series.provider_run_id,
        product=str(provenance.get("product", series.logical_name)),
        producer=str(provenance.get("producer", "undeclared")),
        intermediary=dict(provenance["intermediary"]) if isinstance(provenance.get("intermediary"), Mapping) else None,
        measurement_scope=scope,
        evidence_classes=classes,
        display_primary=display_primary,
        adapter_version=str(provenance["adapter_version"]) if provenance.get("adapter_version") else None,
        retrieval=[dict(item) for item in (provenance.get("retrieval") or []) if isinstance(item, Mapping)],
        quality=dict(provenance.get("quality") or {}),
        structural_validation=dict(provenance.get("structural_validation") or {}),
        coverage=dict(provenance.get("coverage") or {}),
        dimensions=dict(series.dimensions),
        record_count=len(series.times),
        newest_instant=newest,
        retrieved_at=series.retrieved_at,
        freshness=freshness,
        freshness_basis=basis,
        latest=_latest_values(series),
        notices=notices,
    )


def build_products(store: LiveStore, reference: datetime, *, registry_threshold: Any) -> SpaceWeatherProductsResponse:
    """Every coordinate-free space-weather artifact the store currently publishes.

    ``registry_threshold(source_id) -> int | None`` supplies the freshness
    threshold; it is injected so the listing can be tested without the
    registry and so a registry read failure degrades to ``unknown``
    freshness rather than to a guess.
    """
    store.skipped = []
    artifacts = [
        artifact for artifact in store.current()
        if (artifact.provenance or {}).get("native_crs") == SERIES_CRS
    ]
    products: list[SpaceWeatherProduct] = []
    for artifact in sorted(artifacts, key=lambda item: (item.source_id, item.logical_name)):
        series = store.read_series(artifact.source_id, artifact.logical_name)
        if series is None:
            continue  # the reader recorded why under store.skipped
        products.append(product_from_series(series, reference, _threshold(artifact.source_id, registry_threshold)))
    skipped = [SpaceWeatherSkipped(source_id=item.source_id, logical_name=_logical_for(item, artifacts), reason=item.reason) for item in store.skipped]
    notices: list[str] = []
    if not products:
        notices.append("no coordinate-free space-weather artifact is currently published; nothing is listed and nothing is invented")
    return SpaceWeatherProductsResponse(
        data_mode=DataMode.LIVE if products else DataMode.UNAVAILABLE,
        generated_at=reference,
        products=products,
        skipped=skipped,
        notices=notices,
    )


def _logical_for(skip: Any, artifacts: list[Any]) -> str:
    for artifact in artifacts:
        if artifact.revision_id == skip.revision_id:
            return str(artifact.logical_name)
    return str(skip.revision_id)
