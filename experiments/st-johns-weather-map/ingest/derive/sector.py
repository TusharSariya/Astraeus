"""Sampling a retrieved gridded field over a sector along a bearing.

The construction behind the registry entry ``sector_sampling_along_bearing``
(``ingest.derive.registry.SECTOR_SAMPLING``): given an origin on the ground, a
bearing, a sector width and a maximum range, take the cells of a retrieved
grid that fall inside that sector and reduce them to one number.

What this module refuses, and why each refusal exists:

* **A non-retrieved input.** A sector sample is a statement about what a
  centre published on its own grid. An input whose evidence class is not
  ``retrieved`` - a ``reprocessed`` grid, an ``intermediary_derived`` one -
  would make the sample a statement about a construction, so it is refused
  with ``input_class_refused:<class>`` naming the class that arrived.
* **A blend.** The same catalogue field, or two members of one field family,
  taken from two sources is the same field averaged across centres by another
  name, so it is refused with ``blend_refused``. This mirrors the no-blend
  rule the registry applies to the entry's declaration; here it is applied to
  the inputs that actually arrived.
* **A sector the grid does not cover.** A mean over the covered part of a
  sector is not the sector, so a covered fraction below
  :data:`MINIMUM_COVERED_FRACTION` yields ``null`` with
  ``uncovered_fraction:<fraction>`` naming what was covered. A sector with no
  in-sector cells at all is ``uncovered_fraction:0.0``; it is never a mean
  over nothing.
* **A switched-off entry.** The three kill-switch levels are checked through
  :func:`ingest.derive.registry.resolve`, so a disabled entry, a deployment
  with ``WEATHER_DERIVED_HERE=off`` and a reader who switched the entry off
  each get the registry's own refusal code (``method_disabled``,
  ``deployment_refused``, ``reader_disabled``). No unsectored substitute is
  served in place of a refused sample.

Geometry. The entry's citation names Karney (2013) geodesics, which is what a
WGS84-exact sector would use. This module computes the great-circle bearing
and distance with the spherical haversine and forward-azimuth formulas from
:mod:`math` on a mean-radius sphere. Over the ranges a site sector asks for
(tens of kilometres) the spherical approximation differs from the WGS84
geodesic by under 0.5 percent in distance, which is far inside one grid cell,
so it does not move a cell in or out of a sector. Pure ``math``, no numpy.

The elevation-angle band is a parameter of the sector and is carried in the
provenance, but it is **not** applied here: these inputs are a 2-D surface
grid, which has no elevation axis to select on. A method that reads a 3-D
field would apply it; this one records what was asked for and says so.

Quality is the worst input status by :data:`ingest.derive.registry.QUALITY_SEVERITY`
(``passed`` < ``suspect`` < ``unknown`` < ``failed``), mirroring
``api.weather_api.models``; ``ingest`` never imports ``api``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from ingest.derive import registry as derive_registry
from ingest.derive.registry import QUALITY_SEVERITY, SECTOR_SAMPLING

__all__ = [
    "MINIMUM_COVERED_FRACTION",
    "REDUCTION",
    "RETRIEVED",
    "SectorInput",
    "SectorParameters",
    "SectorResult",
    "sample_sector",
]

#: The evidence class a sector sample may read, and only that one.
RETRIEVED = "retrieved"

#: The least fraction of a sector's in-sector cells that must carry a value
#: before the sample is served. Below it the sample is ``null`` naming the
#: fraction, because a mean over part of a sector is not the sector.
MINIMUM_COVERED_FRACTION = 0.8

#: The reduction over the sampled cells, declared on the entry. Cells are
#: weighted equally: a cell far along the bearing counts the same as a near
#: one, because the sector is a question about the whole sector.
REDUCTION = "mean"

#: Mean Earth radius in kilometres (IUGG mean radius), for the spherical
#: great-circle formulas above.
_EARTH_RADIUS_KM = 6371.0088


@dataclass(frozen=True, slots=True)
class SectorParameters:
    """The sector a sample covers: where it starts, where it points, how far.

    ``elevation_band_deg`` is the ``(lower, upper)`` elevation-angle band the
    question asks about. It is carried in the provenance and not applied to a
    2-D surface grid; see the module docstring.
    """

    origin_latitude: float
    origin_longitude: float
    bearing_deg: float
    width_deg: float
    max_range_km: float
    elevation_band_deg: tuple[float, float]


@dataclass(frozen=True, slots=True)
class SectorInput:
    """One retrieved gridded field offered to a sector sample.

    ``cells`` is the grid the caller listed for this sector as
    ``(latitude, longitude, value)`` triples; ``value`` is ``None`` where the
    grid has no value there. The cells the caller lists are the sample's
    denominator: the covered fraction is the share of the listed cells falling
    inside the sector that carry a value.
    """

    field: str
    family: str
    source_id: str
    evidence_class: str
    quality_status: str
    cells: Sequence[tuple[float, float, float | None]]


@dataclass(frozen=True, slots=True)
class SectorResult:
    """One sector sample, or the reason there is none.

    ``value`` is ``None`` whenever ``refusal`` is set, and the provenance is
    carried either way, so a refused field still says what was asked for.
    """

    value: float | None
    quality_status: str
    covered_fraction: float
    refusal: str | None
    provenance: dict[str, Any]

    @property
    def available(self) -> bool:
        return self.refusal is None


def _worst_quality(inputs: Sequence[SectorInput]) -> str:
    """The worst input status. Nothing here may raise a status."""
    if not inputs:
        return "unknown"
    return max(
        (item.quality_status for item in inputs),
        key=lambda status: QUALITY_SEVERITY.get(status, QUALITY_SEVERITY["unknown"]),
    )


def _blend_refusal(inputs: Sequence[SectorInput]) -> str | None:
    """``blend_refused`` when one field or family arrives from two sources."""
    by_field: dict[str, set[str]] = {}
    by_family: dict[str, set[str]] = {}
    for item in inputs:
        by_field.setdefault(item.field, set()).add(item.source_id)
        by_family.setdefault(item.family, set()).add(item.source_id)
    for sources in (*by_field.values(), *by_family.values()):
        if len(sources) > 1:
            return "blend_refused"
    return None


def _bearing_and_distance(
    origin_latitude: float, origin_longitude: float, latitude: float, longitude: float
) -> tuple[float, float]:
    """Great-circle forward azimuth in degrees and distance in kilometres."""
    phi1 = math.radians(origin_latitude)
    phi2 = math.radians(latitude)
    delta_lambda = math.radians(longitude - origin_longitude)
    bearing = math.degrees(
        math.atan2(
            math.sin(delta_lambda) * math.cos(phi2),
            math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(delta_lambda),
        )
    ) % 360.0
    delta_phi = phi2 - phi1
    haversine = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    distance = 2.0 * _EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(haversine)))
    return bearing, distance


def _angular_difference(first_deg: float, second_deg: float) -> float:
    """The smaller angle between two bearings, wrapping around 360."""
    return abs((first_deg - second_deg + 180.0) % 360.0 - 180.0)


def _in_sector(latitude: float, longitude: float, params: SectorParameters) -> bool:
    """Is this cell inside the sector: within half the width, within range?"""
    bearing, distance = _bearing_and_distance(
        params.origin_latitude, params.origin_longitude, latitude, longitude
    )
    if distance > params.max_range_km:
        return False
    return _angular_difference(bearing, params.bearing_deg) <= params.width_deg / 2.0


def _provenance(inputs: Sequence[SectorInput], params: SectorParameters) -> dict[str, Any]:
    """What a served sample carries: the entry, the sector and every input."""
    entry = derive_registry.get(SECTOR_SAMPLING)
    return {
        "derivation": SECTOR_SAMPLING,
        "derivation_version": entry.version if entry is not None else None,
        "origin": (params.origin_latitude, params.origin_longitude),
        "bearing_deg": params.bearing_deg,
        "width_deg": params.width_deg,
        "max_range_km": params.max_range_km,
        "elevation_band_deg": params.elevation_band_deg,
        "reduction": REDUCTION,
        "inputs": [
            {
                "field": item.field,
                "family": item.family,
                "source_id": item.source_id,
                "evidence_class": item.evidence_class,
                "quality_status": item.quality_status,
            }
            for item in inputs
        ],
    }


def sample_sector(
    inputs: Sequence[SectorInput],
    params: SectorParameters,
    *,
    reader_disabled: Iterable[str] = (),
) -> SectorResult:
    """Reduce the in-sector cells of retrieved grids to one number, or refuse.

    The order of the checks is the order in which a reader would want the
    reason: the kill switches first, because a switched-off entry never
    reaches the inputs; then the inputs' evidence class and the no-blend rule,
    because they say the sample may not be built at all; then coverage, which
    is a property of the geometry the caller asked for.
    """
    provenance = _provenance(inputs, params)
    quality = _worst_quality(inputs)

    refusal = derive_registry.resolve(SECTOR_SAMPLING, reader_disabled=reader_disabled)
    if refusal is not None:
        return SectorResult(None, quality, 0.0, refusal.code, provenance)

    for item in inputs:
        if item.evidence_class != RETRIEVED:
            return SectorResult(
                None, quality, 0.0, f"input_class_refused:{item.evidence_class}", provenance
            )

    blend = _blend_refusal(inputs)
    if blend is not None:
        return SectorResult(None, quality, 0.0, blend, provenance)

    in_sector = 0
    values: list[float] = []
    for item in inputs:
        for latitude, longitude, value in item.cells:
            if not _in_sector(latitude, longitude, params):
                continue
            in_sector += 1
            if value is not None:
                values.append(float(value))

    covered_fraction = (len(values) / in_sector) if in_sector else 0.0
    if covered_fraction < MINIMUM_COVERED_FRACTION:
        return SectorResult(
            None, quality, covered_fraction, f"uncovered_fraction:{covered_fraction}", provenance
        )

    return SectorResult(sum(values) / len(values), quality, covered_fraction, None, provenance)
