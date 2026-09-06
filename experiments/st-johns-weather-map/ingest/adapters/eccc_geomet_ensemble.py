"""ECCC REPS members over the GeoMet WCS, one coverage per member per field.

The first of the four ensemble access shapes, in the owner's build order. REPS
is the only admitted member family that subsets **server side**: GeoMet answers
``GetCoverage`` with the evidence box already cut, 40 224 bytes per member field
per lead (verified live 2026-09-02,
``docs/research/wayfinder/ensemble-access.md`` section 5). So there is no local
crop here and no byte-range arithmetic: the request shape *is* the subset, and
the storage scope is ``every_published_field`` because wire and stored are the
same set.

Three things this module deliberately does not do.

It does not name the control. The registry declares ``control.identifier`` as
``None`` for REPS - GeoMet publishes ``REPS.MEM.<VAR>.01`` through ``.21`` and
distinguishes no coverage as the unperturbed run - so no member carries the flag
and nothing here defaults it onto ``01``. Where the declaration ever names one,
:func:`control_retrieval_for` reports ``separate_coverage`` and the identifier
travels straight into :func:`ingest.grib.stack_members`.

It does not decode GeoTIFF itself. ``reader`` is injected; the default refuses,
because no GeoTIFF-to-``DataArray`` path is wired in this deployment and a
silently empty decode would look like a thin run. Tests inject a fake reader,
which is also how the assembly below is exercised without touching the network.

It does not schedule anything. :meth:`discover` reads
``IngestConfig.ensemble.schedulable`` and refuses while it is false, quoting the
registry's own reason. Registering an adapter must never make a family
schedulable, and REPS is unschedulable on two counts the registry states: the
run cycles and lead set were never enumerated, and the control was never
located.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import urlencode

from ingest.adapters.eccc_geomet import GEOMET_BASE_URL
from ingest.contract import (
    MEDIA_ZARR,
    Adapter,
    AdapterUnavailable,
    Artifact,
    FetchWindow,
    RunCandidate,
    RunResult,
)
from ingest.grib import (
    ECCC_RH_PHASE_BASIS,
    RH_PHASE_LIQUID_WATER,
    declare_rh_phase,
    stack_members,
    write_zarr,
)
from ingest.http import PoliteClient
from ingest.manifest import RequiredField, RunManifest, validate_run
from ingest.registry import EnsembleDeclaration, get_config, register
from registry import fields as catalogue

UTC = timezone.utc
_log = logging.getLogger(__name__)

WCS_VERSION = "2.0.1"
WCS_FORMAT = "image/tiff"

#: The box the one bounded GeoMet call for ticket 13 was made against, and the
#: only box whose native ``SCALESIZE`` has been measured. A different box needs
#: its own measured grid size; deriving one would be a guess about the native
#: resolution, so the adapter carries the measured pair together.
REPS_EVIDENCE_BOX = {"south": 45.0, "west": -58.0, "north": 50.5, "east": -46.0}

#: ``long(133),lat(61)`` is REPS' native cell count over
#: :data:`REPS_EVIDENCE_BOX`, from ``docs/research/wayfinder/geomet-wcs-inventory.md``.
#: ``SCALESIZE`` is mandatory on this endpoint: omitting it returns a resampled
#: coverage at the server's default size, which is not the model's own grid.
REPS_SCALESIZE = "long(133),lat(61)"

#: The placeholder the field catalogue writes into a per-member coverage id.
MEMBER_PLACEHOLDER = "<member>"

#: The placeholder for a pressure level in ``REPS.MEM.PRES_<VAR>.<hPa>.<member>``.
LEVEL_PLACEHOLDER = "<hPa>"

CONTROL_RETRIEVAL = "separate_coverage"

LICENCE = "Environment and Climate Change Canada Data Servers End-use Licence"
ATTRIBUTION = "Environment and Climate Change Canada"


class REPSCoverageError(RuntimeError):
    """A coverage id could not be formed, or a coverage did not decode."""


def declaration_for(source_id: str) -> EnsembleDeclaration:
    """The family's own declaration, or refuse.

    Everything family-shaped below - how many members exist, what the control is
    called, which scope applies - is read from here and never restated as a
    literal. A record with no ``ensemble`` block declares no family at all, and
    an adapter that invented one would be retrieving on an assumption.
    """
    declaration = get_config(source_id).ensemble
    if declaration is None:
        raise AdapterUnavailable(
            f"{source_id}: the registry record declares no ensemble block, so the member count, "
            "control rule and storage scope are unstated and nothing is retrieved for it"
        )
    return declaration


def member_identifiers(declaration: EnsembleDeclaration) -> tuple[str, ...]:
    """``01``..``21`` - GeoMet's own member tokens, from the declared count.

    Zero-padded two-digit strings because that is what the coverage ids carry;
    ``1`` and ``01`` are different tokens to this producer and neither is an
    integer here.
    """
    if declaration.member_count is None:
        raise REPSCoverageError(
            f"{declaration.family}: the registry declares no member count, so the member set "
            "cannot be enumerated and no coverage is requested"
        )
    return tuple(f"{index:02d}" for index in range(1, declaration.member_count + 1))


def control_retrieval_for(declaration: EnsembleDeclaration) -> str | None:
    """``separate_coverage`` where a control is named, else ``None``.

    REPS' declared control block carries ``identifier: None``: the family
    publishes members and the control among them was never located. That is not
    the same as a family with no control, and it is emphatically not a licence
    to flag ``01``, so the retrieval shape stays null until an identifier exists.
    """
    control = declaration.control
    if control is None or control.identifier is None:
        return None
    return CONTROL_RETRIEVAL


def stored_member_coverages(source_id: str) -> tuple[tuple[str, str], ...]:
    """``(catalogue key, coverage template)`` for every stored per-member field.

    Read off the field catalogue rather than listed here, so the set this
    adapter retrieves and the set the catalogue calls ``stored`` cannot drift.
    Templates carrying a pressure level are excluded: their exact per-level
    coverage naming was never established upstream, and a guessed id would be a
    request for a coverage nobody has seen.
    """
    return tuple(
        (item.key, item.upstream)
        for item in catalogue.source_mapping(source_id)
        if item.storage == "stored"
        and item.upstream
        and MEMBER_PLACEHOLDER in item.upstream
        and LEVEL_PLACEHOLDER not in item.upstream
    )


def coverage_id(template: str, member: str) -> str:
    """``REPS.MEM.ETA_NT.<member>`` + ``01`` -> ``REPS.MEM.ETA_NT.01``."""
    if MEMBER_PLACEHOLDER not in template:
        raise REPSCoverageError(f"{template!r} carries no {MEMBER_PLACEHOLDER} placeholder to fill")
    if LEVEL_PLACEHOLDER in template:
        raise REPSCoverageError(
            f"{template!r} is a pressure-level template; its per-level coverage naming was never "
            "established and is not guessed here"
        )
    return template.replace(MEMBER_PLACEHOLDER, member)


def coverage_params(
    coverage: str,
    bounds: Mapping[str, float] = REPS_EVIDENCE_BOX,
    *,
    scalesize: str = REPS_SCALESIZE,
    image_format: str = WCS_FORMAT,
) -> list[tuple[str, str]]:
    """The working ``GetCoverage`` request, as ordered key/value pairs.

    Pairs rather than a dict because ``SUBSET`` appears twice, once per axis -
    the shape verified live on 2026-09-02. ``BBOX`` is not accepted by this
    endpoint and ``FORMAT`` is mandatory; both were established in
    ``docs/research/wayfinder/geomet-wcs-inventory.md``.
    """
    return [
        ("SERVICE", "WCS"),
        ("VERSION", WCS_VERSION),
        ("REQUEST", "GetCoverage"),
        ("COVERAGEID", coverage),
        ("FORMAT", image_format),
        ("SUBSET", f"long({bounds['west']},{bounds['east']})"),
        ("SUBSET", f"lat({bounds['south']},{bounds['north']})"),
        ("SCALESIZE", scalesize),
    ]


def coverage_url(
    coverage: str,
    bounds: Mapping[str, float] = REPS_EVIDENCE_BOX,
    *,
    base_url: str = GEOMET_BASE_URL,
    scalesize: str = REPS_SCALESIZE,
    image_format: str = WCS_FORMAT,
) -> str:
    params = coverage_params(coverage, bounds, scalesize=scalesize, image_format=image_format)
    return f"{base_url}?{urlencode(params)}"


def _refusing_reader(payload: bytes, *, coverage: str) -> Any:
    raise AdapterUnavailable(
        f"{coverage}: no GeoTIFF decode path is wired for GeoMet WCS coverages in this deployment, "
        f"so the {len(payload)} bytes retrieved cannot become a member field. A caller supplies its "
        "own reader; nothing here publishes an empty grid in its place."
    )


CoverageReader = Callable[..., Any]


@dataclass(frozen=True)
class _CoverageFetch:
    """One field's members, plus the coverages that did not arrive."""

    fields_by_member: dict[str, Any]
    retrieved: tuple[str, ...]
    errors: tuple[str, ...]


def reps_manifest(declaration: EnsembleDeclaration, *, source_id: str = "eccc-reps") -> RunManifest:
    """The run contract, with the family's own numbers filled in from the registry.

    ``member_count``, ``control`` and ``storage_scope`` are the declaration's,
    never this module's: a manifest that restated them could disagree with the
    record the audit checks.
    """
    control = declaration.control
    return RunManifest(
        source_id=source_id,
        fields=tuple(
            RequiredField(
                key,
                catalogue.resolve(key).field.units or "",
                optional=key not in _MANDATORY_KEYS,
            )
            for key, _template in stored_member_coverages(source_id)
        ),
        member_count=declaration.member_count,
        control=None if control is None else control.identifier,
        storage_scope=declaration.storage_scope,
    )


#: The two fields a REPS run is worth publishing without: the member cloud this
#: experiment exists to draw, and the member wind speed beside it. Every other
#: stored ETA_* field is optional, so one absent coverage costs that field and
#: not the run.
_MANDATORY_KEYS = frozenset({"total_cloud_opacity", "wind_speed_10m"})


class ECCCREPSEnsembleAdapter:
    """REPS members from the GeoMet WCS: one coverage per member per field."""

    source_id = "eccc-reps"
    adapter_version = "eccc-reps-ensemble-v1"

    def __init__(
        self,
        *,
        base_url: str = GEOMET_BASE_URL,
        bounds: Mapping[str, float] = REPS_EVIDENCE_BOX,
        scalesize: str = REPS_SCALESIZE,
        client: PoliteClient | None = None,
        reader: CoverageReader = _refusing_reader,
    ) -> None:
        self._base_url = base_url
        self._bounds = dict(bounds)
        self._scalesize = scalesize
        self._client = client
        self._reader = reader

    def _get_client(self) -> PoliteClient:
        return self._client or PoliteClient()

    # ------------------------------------------------------------ the schedule gate

    def _gate(self) -> EnsembleDeclaration:
        declaration = declaration_for(self.source_id)
        if not declaration.schedulable:
            raise AdapterUnavailable(
                f"{self.source_id}: the registry declares {declaration.family} not schedulable. "
                f"{declaration.schedulable_reason}"
            )
        return declaration

    def discover(self, window: FetchWindow) -> list[RunCandidate]:
        self._gate()
        raise AdapterUnavailable(
            f"{self.source_id}: REPS run cycles and lead set were never enumerated, so no candidate "
            "run is addressed from this window"
        )

    def fetch(self, candidate: RunCandidate, window: FetchWindow, workdir: Path) -> RunResult:
        self._gate()
        return self.assemble(candidate, window, workdir)

    # ------------------------------------------------------------ the retrieval path

    def _fetch_field(
        self, key: str, template: str, members: Sequence[str], *, valid_time: datetime | None
    ) -> _CoverageFetch:
        client = self._get_client()
        fields_by_member: dict[str, Any] = {}
        retrieved: list[str] = []
        errors: list[str] = []
        for member in members:
            coverage = coverage_id(template, member)
            url = coverage_url(
                coverage,
                self._bounds,
                base_url=self._base_url,
                scalesize=self._scalesize,
            )
            try:
                response = client.get(url)
                payload = response.content
                if not payload:
                    raise REPSCoverageError(f"{coverage}: the service answered an empty body")
                field = self._reader(payload, coverage=coverage)
                if key == "relative_humidity_2m":
                    # Measured 2026-09-01: the GEM family divides by saturation
                    # over liquid water at every temperature. An unstamped
                    # humidity is a QC failure rather than a gap, because a
                    # threshold calibrated on one phase is not valid on the
                    # other.
                    field = declare_rh_phase(
                        field, convention=RH_PHASE_LIQUID_WATER, basis=ECCC_RH_PHASE_BASIS
                    )
                fields_by_member[member] = field
            except Exception as error:  # transport, service fault or decode
                errors.append(f"coverage:{coverage}")
                _log.warning("REPS coverage %s unavailable: %s", coverage, error)
                continue
            retrieved.append(coverage)
        return _CoverageFetch(
            fields_by_member=fields_by_member,
            retrieved=tuple(retrieved),
            errors=tuple(errors),
        )

    def assemble(self, candidate: RunCandidate, window: FetchWindow, workdir: Path) -> RunResult:
        """Retrieve every stored member field and publish one member axis.

        The retrieval path proper, separated from :meth:`fetch` only by the
        schedule gate, so it can be driven by a caller that supplies its own
        client and reader without the family becoming schedulable.
        """
        import xarray  # noqa: PLC0415

        declaration = declaration_for(self.source_id)
        members = member_identifiers(declaration)
        control = None if declaration.control is None else declaration.control.identifier
        retrieved_at = datetime.now(UTC)

        stacked: dict[str, Any] = {}
        retrieved_names: list[str] = []
        decode_errors: list[str] = []
        for key, template in stored_member_coverages(self.source_id):
            fetched = self._fetch_field(key, template, members, valid_time=candidate.run_time)
            decode_errors.extend(fetched.errors)
            retrieved_names.extend(fetched.retrieved)
            if not fetched.fields_by_member:
                continue
            stacked[key] = stack_members(fetched.fields_by_member, control=control)

        if not stacked:
            raise AdapterUnavailable(
                f"{self.source_id}: no member coverage decoded for {candidate.provider_run_id}; "
                "an ensemble artifact with no members is an absent ensemble, not a thin one"
            )

        dataset = xarray.Dataset(stacked)
        manifest = reps_manifest(declaration, source_id=self.source_id)
        # Under ``every_published_field`` the wire set and the stored set are
        # the same set, so ``published`` is exactly what arrived: a coverage
        # that failed is a decode error above and shortens the member axis, not
        # a field the scope left behind. The available-not-stored list is
        # therefore empty for this family, which is what the scope means.
        validation = validate_run(
            manifest,
            dataset,
            window=window,
            decode_errors=decode_errors,
            upstream_fields=retrieved_names,
            retrieved_fields=retrieved_names,
            declared_members=members,
            control_retrieval=control_retrieval_for(declaration),
        )

        provenance = {
            "source_id": self.source_id,
            "producer": "Environment and Climate Change Canada",
            "product": "Regional Ensemble Prediction System (REPS) members",
            "family": declaration.family,
            "adapter_version": self.adapter_version,
            "endpoint": self._base_url,
            "licence": LICENCE,
            "attribution": ATTRIBUTION,
            "subsetting": declaration.subsetting,
            "scalesize": self._scalesize,
            "bounds": dict(self._bounds),
            "quality": validation.as_quality(),
            "coverage": validation.as_coverage(),
            "members": validation.as_members(),
            "storage_scope": validation.as_storage_scope(),
            **manifest.as_manifest_block(),
        }

        payload_path = workdir / "eccc_reps_members.zarr.zip"
        write_zarr(dataset, payload_path)
        return RunResult(
            source_id=self.source_id,
            provider_run_id=candidate.provider_run_id,
            run_time=candidate.run_time,
            retrieved_at=retrieved_at,
            complete=validation.complete,
            qc_passed=validation.qc_passed,
            artifacts=[
                Artifact(
                    logical_name="members",
                    media_type=MEDIA_ZARR,
                    payload_path=payload_path,
                    provenance=provenance,
                )
            ],
            native_crs="EPSG:4326",
            notes=f"REPS members over GeoMet WCS; {validation.detail}",
        )


REPS_ENSEMBLE_ADAPTER: Adapter = register(ECCCREPSEnsembleAdapter())
