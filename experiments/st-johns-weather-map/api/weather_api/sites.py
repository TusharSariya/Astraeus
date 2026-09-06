"""Sites as preferred locations, never as a limit on where evidence is served.

The evidence layer serves every catalogue field at any point inside the
evidence box, whether or not that point is a registered site. This module is
what makes that statement enforceable rather than aspirational:

- :func:`inside_evidence_box` and :func:`refuse_outside_box` are the only
  geographic refusal in the deployment. Inside the box every field is served;
  outside it nothing is extrapolated and the refusal names the box.
- :func:`horizon_for` answers with a horizon for an exactly matching site id
  and with ``None`` for everything else. There is deliberately no nearest-site
  lookup anywhere in this module. A horizon is a property of one position; the
  horizon from Signal Hill is wrong 300 m away and catastrophically wrong at
  the foot of the hill, so borrowing one would be a fabricated value dressed
  as a measurement.
- :func:`horizon_dependent_null` is what a caller emits instead: the field
  present, the value ``null``, the flag ``no_registered_horizon`` naming why,
  and every field that does not need a horizon served beside it untouched.

Nothing here refuses a request for being off-site, and nothing here promotes a
site to an allowlist. Travel choice, routing and site ranking are
decision-layer concerns and are not implemented here.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

EXPERIMENT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(EXPERIMENT_ROOT) not in sys.path:  # registry/ ships beside api/ in both images
    sys.path.insert(0, str(EXPERIMENT_ROOT))

from registry import site_audit  # noqa: E402
from registry.site_audit import Site, SiteError  # noqa: E402

from . import store  # noqa: E402
from .models import EvidenceField  # noqa: E402

#: The area evidence is served over, as (south, north, west, east) in degrees.
#: The same four numbers are the retrieval bounds one adapter asks GeoMet for
#: (``ingest.adapters.eccc_geomet_ensemble.REPS_EVIDENCE_BOX``); they are
#: restated here rather than imported because the serving box is a property of
#: this deployment and must not move when an adapter changes what it fetches.
EVIDENCE_BOX: tuple[float, float, float, float] = (45.0, 50.5, -58.0, -46.0)

#: The refusal code for a point the deployment holds no evidence over.
OUTSIDE_EVIDENCE_BOX = "outside_evidence_box"

#: The flag on a horizon-dependent field asked for where nobody registered a
#: horizon. It is a plain ``null`` absence with a reason, not a block and not
#: an aged-out value: no horizon was ever held for this point.
NO_REGISTERED_HORIZON = "no_registered_horizon"

#: The field names that cannot be answered without a registered horizon: the
#: sector-sampling output, which needs the horizon to bound its elevation
#: band, and the two camera visibility bounds, which are read against
#: landmarks whose apparent elevation the horizon fixes. Every other field is
#: served at any point in the box regardless of site.
HORIZON_DEPENDENT_FIELDS: frozenset[str] = frozenset(
    {
        "sector_statistic",
        "visibility_bound_lower_m",
        "visibility_bound_upper_m",
    }
)


def _format_box() -> str:
    south, north, west, east = EVIDENCE_BOX
    return f"latitude {south:g} to {north:g}, longitude {west:g} to {east:g}"


def inside_evidence_box(latitude: float, longitude: float) -> bool:
    """Whether this point is one the deployment serves evidence over.

    The bounds are inclusive: a point exactly on an edge is inside, because a
    reader standing on the boundary is not standing anywhere else.
    """

    south, north, west, east = EVIDENCE_BOX
    return south <= float(latitude) <= north and west <= float(longitude) <= east


def refuse_outside_box(latitude: float, longitude: float) -> str | None:
    """The refusal for a point outside the box, or ``None`` for one inside.

    ``None`` is the whole point of this function: every point inside the box
    is accepted, whether or not a site is registered near it.
    """

    if inside_evidence_box(latitude, longitude):
        return None
    return (
        f"{OUTSIDE_EVIDENCE_BOX}: {float(latitude):g}, {float(longitude):g} lies outside the "
        f"evidence box ({_format_box()}); no value is extrapolated to it"
    )


@dataclass(frozen=True)
class Horizon:
    """One site's hand-registered directional horizon and its terrain check.

    ``elevation_deg`` runs from true north clockwise in steps of
    ``bearing_resolution_deg``. The terrain check travels with it because a
    check that was not run is a disclosure a reader is owed, not an absence to
    be quietly read as agreement.
    """

    site_id: str
    bearing_resolution_deg: float
    elevation_deg: tuple[float, ...]
    terrain_check_status: str
    terrain_check_note: str


@dataclass(frozen=True)
class SiteSummary:
    """A servable site record as the serving side reads it."""

    id: str
    name: str
    latitude: float
    longitude: float
    elevation_m: float
    datum: str
    horizon: Horizon
    registered_on: str
    registered_by: str


@dataclass(frozen=True)
class SiteRegistry:
    """The servable sites, and the notice for whatever was left out.

    ``notice`` is ``None`` only when every file read cleanly and every record
    audited clean. It never turns into a refusal: an empty registry means
    every horizon-dependent field is ``null`` and nothing else changes.
    """

    sites: list[SiteSummary]
    notice: str | None = None

    def by_id(self) -> dict[str, SiteSummary]:
        return {site.id: site for site in self.sites}


def _summarise(site: Site) -> SiteSummary:
    record = site.record
    horizon = record["horizon"]
    check = record["terrain_check"]
    position = record["position"]
    elevation = record["elevation"]
    registered = record["registered"]
    return SiteSummary(
        id=site.site_id,
        name=site.name,
        latitude=float(position["latitude"]),
        longitude=float(position["longitude"]),
        elevation_m=float(elevation["metres"]),
        datum=str(elevation["datum"]),
        horizon=Horizon(
            site_id=site.site_id,
            bearing_resolution_deg=float(horizon["bearing_resolution_deg"]),
            elevation_deg=tuple(float(angle) for angle in horizon["elevation_deg"]),
            terrain_check_status=str(check["status"]),
            terrain_check_note=str(check["note"]),
        ),
        registered_on=str(registered["date"]),
        registered_by=str(registered["by"]),
    )


def load_site_registry(root: Path | str | None = None) -> SiteRegistry:
    """Read the registry, keeping only the records that are servable.

    A record that could not be read and a record the audit calls not servable
    are both left out of ``sites`` and named in ``notice``. Neither is raised:
    one bad file must not take the registry with it, and no registry failure
    of any kind changes what is served at an arbitrary point.
    """

    root = Path(root) if root is not None else site_audit.SITES_ROOT
    loaded = site_audit.load_sites(root)
    reasons: list[str] = []
    servable: list[SiteSummary] = []
    for site_id in sorted(loaded):
        entry = loaded[site_id]
        if isinstance(entry, SiteError):
            reasons.append(f"{site_id}: {entry.detail}")
            continue
        errors = site_audit.audit_site(entry)
        if errors:
            reasons.append(f"{site_id}: {'; '.join(errors)}")
            continue
        servable.append(_summarise(entry))

    notice = site_audit.registry_notice(root)
    if reasons:
        left_out = (
            f"{len(reasons)} site record(s) are not served: {'; '.join(reasons)}; "
            "field service at arbitrary points inside the evidence box is unaffected"
        )
        notice = f"{notice} {left_out}" if notice else left_out
    return SiteRegistry(sites=servable, notice=notice)


def horizon_for(site_id: str | None, *, registry: SiteRegistry | None = None) -> Horizon | None:
    """The registered horizon for exactly this site id, or ``None``.

    ``None`` in, ``None`` out: a request that names no site has no horizon,
    and there is no nearest-site lookup in this module to fall back on. An id
    that names no servable site answers ``None`` for the same reason.
    """

    if site_id is None:
        return None
    registry = registry if registry is not None else load_site_registry()
    match = registry.by_id().get(site_id)
    return None if match is None else match.horizon


def horizon_dependent_null(
    field: str,
    *,
    valid_time: datetime,
    units: str,
    key: str | None = None,
) -> EvidenceField:
    """The field a caller emits where no horizon is registered.

    The field is present and its value is ``null`` with the reason attached,
    rather than the field being dropped: an absent field reads as a field
    nobody asked for, and this one was asked for and cannot be answered here.
    The absence state is ``null`` because no horizon was ever held for this
    point, not blocked by terms and not aged out of a window.
    """

    provenance = store.unavailable_provenance(
        valid_time,
        units=units,
        flags=[NO_REGISTERED_HORIZON],
        source_id="site-registry",
        product="no_registered_horizon",
    )
    return EvidenceField(
        field=field,
        value=None,
        key=key,
        provenance=provenance,
        absence_state="null",
    )
