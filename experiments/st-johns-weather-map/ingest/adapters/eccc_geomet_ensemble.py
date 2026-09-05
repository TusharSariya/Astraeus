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

It decodes the numeric GeoTIFF through the same strict geometry reader as the
deterministic WCS experiment. Tests may inject a fake reader to exercise
assembly without touching the network.

It does not schedule anything. :meth:`discover` reads
``IngestConfig.ensemble.schedulable`` and refuses while it is false, quoting the
registry's own reason. Registering an adapter must never make a family
schedulable, and REPS is unschedulable on two counts the registry states: the
run cycles and lead set were never enumerated, and the control was never
located.
"""

from __future__ import annotations

import hashlib
import io
import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import numpy
import xarray
from PIL import Image
from registry import fields as catalogue

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

_log = logging.getLogger(__name__)

WCS_VERSION = "2.0.1"
WCS_FORMAT = "image/tiff"
WCS_EPSG4326 = "http://www.opengis.net/def/crs/EPSG/0/4326"

#: The bounded validation box. Output shape and box travel together because a
#: different pair would be a different server-resampling request.
REPS_EVIDENCE_BOX = {"south": 45.0, "west": -58.0, "north": 50.5, "east": -46.0}

#: The bounded output shape measured for the evidence box. DescribeCoverage
#: reports the source grid as EPSG:102990 with 0.09 degree grid-axis offsets.
#: GeoMet reprojects/resamples that source grid into this explicitly requested
#: EPSG:4326 output. This is therefore an output geometry, never a native-grid
#: claim.
REPS_SCALESIZE = "long(133),lat(61)"
REPS_WIDTH = 133
REPS_HEIGHT = 61

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


def pressure_coverage_id(
    template: str, *, level_hpa: int, member: str, advertised: Sequence[str],
) -> str:
    """Resolve a pressure coverage only when the exact level is advertised."""
    if LEVEL_PLACEHOLDER not in template or MEMBER_PLACEHOLDER not in template:
        raise REPSCoverageError(f"{template!r} is not a pressure/member coverage template")
    candidate = template.replace(LEVEL_PLACEHOLDER, str(level_hpa)).replace(MEMBER_PLACEHOLDER, member)
    if candidate not in advertised:
        raise REPSCoverageError(f"{candidate}: selected pressure level/member is not advertised")
    return candidate


def coverage_params(
    coverage: str,
    bounds: Mapping[str, float] = REPS_EVIDENCE_BOX,
    *,
    scalesize: str = REPS_SCALESIZE,
    image_format: str = WCS_FORMAT,
    valid_time: datetime | None = None,
    reference_time: datetime | None = None,
    subsetting_crs: str = WCS_EPSG4326,
) -> list[tuple[str, str]]:
    """The working ``GetCoverage`` request, as ordered key/value pairs.

    Pairs rather than a dict because ``SUBSET`` appears twice, once per axis -
    the shape verified live on 2026-09-02. ``BBOX`` is not accepted by this
    endpoint and ``FORMAT`` is mandatory; both were established in
    ``docs/research/wayfinder/geomet-wcs-inventory.md``.
    """
    params = [
        ("SERVICE", "WCS"),
        ("VERSION", WCS_VERSION),
        ("REQUEST", "GetCoverage"),
        ("COVERAGEID", coverage),
        ("FORMAT", image_format),
        ("SUBSETTINGCRS", subsetting_crs),
        ("SUBSET", f"long({bounds['west']},{bounds['east']})"),
        ("SUBSET", f"lat({bounds['south']},{bounds['north']})"),
        ("SCALESIZE", scalesize),
    ]
    if valid_time is not None:
        params.append(("TIME", valid_time.astimezone(UTC).isoformat().replace("+00:00", "Z")))
    if reference_time is not None:
        params.append(("DIM_REFERENCE_TIME", reference_time.astimezone(UTC).isoformat().replace("+00:00", "Z")))
    return params


def coverage_url(
    coverage: str,
    bounds: Mapping[str, float] = REPS_EVIDENCE_BOX,
    *,
    base_url: str = GEOMET_BASE_URL,
    scalesize: str = REPS_SCALESIZE,
    image_format: str = WCS_FORMAT,
    valid_time: datetime | None = None,
    reference_time: datetime | None = None,
    subsetting_crs: str = WCS_EPSG4326,
) -> str:
    params = coverage_params(
        coverage, bounds, scalesize=scalesize, image_format=image_format,
        valid_time=valid_time, reference_time=reference_time,
        subsetting_crs=subsetting_crs,
    )
    return f"{base_url}?{urlencode(params)}"


def decode_reps_geotiff(
    payload: bytes, *, coverage: str, variable: str, valid_time: datetime,
    bounds: Mapping[str, float], width: int = REPS_WIDTH, height: int = REPS_HEIGHT,
) -> Any:
    """Decode the real WCS TIFF and retain its measured output geometry."""
    if payload[:4] not in (b"II*\x00", b"MM\x00*"):
        raise REPSCoverageError(f"{coverage}: GeoMet response is not a TIFF")
    with Image.open(io.BytesIO(payload)) as image:
        values = numpy.asarray(image, dtype=numpy.float32)
        scale = tuple(float(value) for value in image.tag_v2.get(33550, ()))
        tie = tuple(float(value) for value in image.tag_v2.get(33922, ()))
        geokeys = tuple(image.tag_v2.get(34735, ()))
    if values.shape != (height, width):
        raise REPSCoverageError(f"{coverage}: shape {values.shape} != requested {(height, width)}")
    if len(scale) < 2 or len(tie) != 6 or scale[0] <= 0 or scale[1] <= 0:
        raise REPSCoverageError(f"{coverage}: unusable GeoTIFF scale/tie-point metadata")
    if geokeys:
        if len(geokeys) < 4 or int(geokeys[0]) != 1:
            raise REPSCoverageError(f"{coverage}: unusable GeoTIFF key directory")
        keys = {
            int(geokeys[offset]): int(geokeys[offset + 3])
            for offset in range(4, len(geokeys), 4)
            if int(geokeys[offset + 1]) == 0 and int(geokeys[offset + 2]) == 1
        }
        if keys.get(2048) != 4326:
            raise REPSCoverageError(f"{coverage}: GeoTIFF is not EPSG:4326")
    west, north = tie[3], tie[4]
    east, south = west + width * scale[0], north - height * scale[1]
    wanted = tuple(float(bounds[key]) for key in ("west", "south", "east", "north"))
    actual = (west, south, east, north)
    if any(abs(a - b) > 1e-6 for a, b in zip(actual, wanted)):
        raise REPSCoverageError(f"{coverage}: output bounds {actual} != requested {wanted}")
    if numpy.isinf(values).any():
        raise REPSCoverageError(f"{coverage}: coverage carries infinite values")
    longitude = west + (numpy.arange(width, dtype=numpy.float64) + 0.5) * scale[0]
    latitude = north - (numpy.arange(height, dtype=numpy.float64) + 0.5) * scale[1]
    return xarray.DataArray(
        values, dims=("latitude", "longitude"),
        coords={"latitude": latitude, "longitude": longitude},
        attrs={
            "sampling_geometry": "pixel_is_area_cell_centres",
            "longitude_resolution_degrees": scale[0],
            "latitude_resolution_degrees": scale[1],
            "crs": "EPSG:4326",
            "crs_evidence": (
                "GeoTIFF GeoKeyDirectoryTag" if geokeys
                else "WCS subset axes; GeoTIFF carries no GeoKeyDirectoryTag"
            ),
            "resampling": "server_resampled_method_unknown",
        },
    )


CoverageReader = Callable[..., Any]


@dataclass(frozen=True)
class _CoverageFetch:
    """One field's members, plus the coverages that did not arrive."""

    fields_by_member: dict[str, Any]
    retrieved: tuple[str, ...]
    errors: tuple[str, ...]
    receipts: tuple[dict[str, Any], ...]


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
        reader: CoverageReader | None = None,
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
        self, key: str, template: str, members: Sequence[str], *,
        valid_time: datetime | None, reference_time: datetime | None,
    ) -> _CoverageFetch:
        client = self._get_client()
        fields_by_member: dict[str, Any] = {}
        retrieved: list[str] = []
        errors: list[str] = []
        receipts: list[dict[str, Any]] = []
        for member in members:
            coverage = coverage_id(template, member)
            url = coverage_url(
                coverage,
                self._bounds,
                base_url=self._base_url,
                scalesize=self._scalesize,
                valid_time=valid_time,
                reference_time=reference_time,
            )
            try:
                response = client.get(url)
                payload = response.content
                if not payload:
                    raise REPSCoverageError(f"{coverage}: the service answered an empty body")
                if valid_time is None:
                    raise REPSCoverageError(f"{coverage}: an explicit valid/reference time is required")
                if self._reader is None:
                    field = decode_reps_geotiff(
                        payload, coverage=coverage, variable=key, valid_time=valid_time,
                        bounds=self._bounds,
                    )
                else:
                    field = self._reader(payload, coverage=coverage)
                field.attrs["units"] = catalogue.resolve(key).field.units or "unknown"
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
            except Exception as error:  # noqa: BLE001 - isolate one failed member
                errors.append(f"coverage:{coverage}")
                _log.warning("REPS coverage %s unavailable: %s", coverage, error)
                continue
            retrieved.append(coverage)
            receipts.append({
                "coverage_id": coverage,
                "source_uri": url,
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            })
        return _CoverageFetch(
            fields_by_member=fields_by_member,
            retrieved=tuple(retrieved),
            errors=tuple(errors),
            receipts=tuple(receipts),
        )

    def assemble(
        self, candidate: RunCandidate, window: FetchWindow, workdir: Path,
        *, selected_keys: Sequence[str] | None = None,
    ) -> RunResult:
        """Retrieve every stored member field and publish one member axis.

        The retrieval path proper, separated from :meth:`fetch` only by the
        schedule gate, so it can be driven by a caller that supplies its own
        client and reader without the family becoming schedulable.
        """
        import xarray

        declaration = declaration_for(self.source_id)
        members = member_identifiers(declaration)
        control = None if declaration.control is None else declaration.control.identifier
        retrieved_at = datetime.now(UTC)

        valid_time = candidate.detail.get("valid_time", candidate.run_time)
        if not isinstance(valid_time, datetime) or candidate.run_time is None:
            raise AdapterUnavailable(
                f"{self.source_id}: experimental WCS assembly requires explicit run_time and valid_time"
            )
        available = dict(stored_member_coverages(self.source_id))
        keys = tuple(available) if selected_keys is None else tuple(selected_keys)
        unknown = sorted(set(keys) - set(available))
        if unknown:
            raise REPSCoverageError(f"selected fields have no verified REPS coverage template: {unknown}")
        stacked: dict[str, Any] = {}
        retrieved_names: list[str] = []
        decode_errors: list[str] = []
        receipts: list[dict[str, Any]] = []
        for key in keys:
            template = available[key]
            fetched = self._fetch_field(
                key, template, members, valid_time=valid_time, reference_time=candidate.run_time,
            )
            decode_errors.extend(fetched.errors)
            retrieved_names.extend(fetched.retrieved)
            receipts.extend(fetched.receipts)
            if not fetched.fields_by_member:
                continue
            stacked[key] = stack_members(fetched.fields_by_member, control=control).drop_vars("control")

        if not stacked:
            raise AdapterUnavailable(
                f"{self.source_id}: no member coverage decoded for {candidate.provider_run_id}; "
                "an ensemble artifact with no members is an absent ensemble, not a thin one"
            )

        dataset = xarray.Dataset(stacked)
        dataset = dataset.assign_coords(
            control=("member", [control is not None and str(member) == control for member in dataset.member.values])
        )
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
            "requested_output_scalesize": self._scalesize,
            "source_grid_crs": "EPSG:102990",
            "source_grid_axis_spacing": [0.09, 0.09],
            "stored_crs": "EPSG:4326",
            "resampling": "server_resampled_method_unknown",
            "bounds": dict(self._bounds),
            "run_time": candidate.run_time.astimezone(UTC).isoformat(),
            "valid_time": valid_time.astimezone(UTC).isoformat(),
            "selected_fields": list(keys),
            "coverages": receipts,
            "quality": validation.as_quality(),
            "coverage": validation.as_coverage(),
            "members": validation.as_members(),
            "storage_scope": validation.as_storage_scope(),
            **manifest.as_manifest_block(),
        }

        payload_path = workdir / "eccc_reps_members.zarr.zip"
        write_zarr(dataset, payload_path)
        provenance["sha256"] = hashlib.sha256(payload_path.read_bytes()).hexdigest()
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
