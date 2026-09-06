"""ECMWF Open Data adapters: the deterministic IFS, and the two ensemble shapes.

Three adapters live here because they share one access mechanism - a ``.index``
sidecar of JSON lines carrying ``_offset`` and ``_length``, then HTTP byte
ranges against the ``.grib2`` beside it - and differ only in where the control
member is:

* ``ecmwf-aifs-ens`` (build order 2) retrieves the 50 perturbed members from the
  ``pf`` file and the control from a **separate** ``cf`` file. Two retrievals,
  one member axis of 51. A run whose ``cf`` is absent is partial with the
  control named as the missing member, never a complete run of 50.
* ``ecmwf-ens`` (build order 3, IFS ENS) exposes the 50 ``pf`` members in the
  Open Data ``enfo-ef`` object. An explicitly authorized experiment may add
  only six producer-designated Cycle 50r1 ``oper:fc`` fields as control ``0``;
  absent that exact mapping and object, the adapter reports control ``0``
  missing and leaves the retrieval shape unstated.

Neither ensemble family subsets server side. A byte range buys a whole global
record and the evidence box is cut locally afterwards, with the same
``crop_to_bbox`` the deterministic adapters use, so only the seven-or-nine
catalogue-family fields are ever requested (the ``family_fields_only`` scope).

The deterministic IFS adapter below is unchanged and still non-publishing.

The ensemble portal listing is parsed by ``discover_experiment`` for bounded,
unregistered verification. Normal ``discover`` and ``fetch`` remain behind the
unchanged registry gate, so this evidence cannot activate either family.

Verified 2026-08-30: ``data.ecmwf.int/forecasts/`` lists only the last four
dates and ``/forecasts/20260830/`` is a 404, so the run this window needs cannot
be addressed by the dated path this adapter assumed. Until the real listing
contract is pinned - which dates exist, when a cycle appears, and how a lead's
``.index`` maps onto its ``.grib2`` - any run it returned would be a guess about
which cycle the numbers came from.

The registry record stays ``implementing``. Publishing a partial or mislabelled
IFS run is exactly the failure this experiment exists to rule out, so
:meth:`ECMWFIFSAdapter.discover` raises :class:`AdapterUnavailable` with that
reason and :meth:`fetch` cannot be reached.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urljoin

from ingest.contract import (
    ATLANTIC_CONTEXT_BOUNDS,
    MEDIA_ZARR,
    Adapter,
    AdapterUnavailable,
    Artifact,
    FetchWindow,
    RunCandidate,
    RunResult,
)
from ingest.grib import stack_members, write_zarr
from ingest.http import PoliteClient
from ingest.manifest import RequiredField, RunManifest, validate_run
from ingest.registry import EnsembleDeclaration, get_config, register
from registry import fields as catalogue

UTC = timezone.utc
_log = logging.getLogger(__name__)

ECMWF_OPEN_DATA_BASE = "https://data.ecmwf.int/forecasts"
MAX_LEAD_HOURS = 24

UNRESOLVED_REASON = (
    "ECMWF Open Data discovery is unresolved: data.ecmwf.int/forecasts/ lists only the last "
    "four dates and the current date returned 404 on 2026-08-30, so the dated cycle path this "
    "adapter assumed cannot address a run in the window. No IFS run is published until the "
    "listing contract is pinned; a guessed cycle would mislabel every value."
)

_PORTAL_DATE = re.compile(r"/forecasts/(?P<date>\d{8})/")
_PORTAL_CYCLE = re.compile(r"/forecasts/\d{8}/(?P<hour>00|12)z/")
_ENSEMBLE_FILE = re.compile(
    r"(?P<stamp>\d{14})-(?P<lead>\d+)h-enfo-(?P<suffix>ef|pf|cf)\.grib2"
)
_IFS_OPER_FILE = re.compile(r"(?P<stamp>\d{14})-(?P<lead>\d+)h-oper-fc\.grib2")

# Discovery is metadata-only and intentionally finite. The portal retains four
# dates; two full ensemble cycles per date and one product directory per cycle
# are enough to establish every lead currently addressable for a family.
MAX_DISCOVERY_DATES = 4
FULL_ENSEMBLE_CYCLES = ("00", "12")
MAX_DISCOVERY_REQUESTS = 1 + MAX_DISCOVERY_DATES + MAX_DISCOVERY_DATES * len(FULL_ENSEMBLE_CYCLES)
MAX_MAPPED_CONTROL_DISCOVERY_REQUESTS = (
    MAX_DISCOVERY_REQUESTS + MAX_DISCOVERY_DATES * len(FULL_ENSEMBLE_CYCLES)
)
MAX_METADATA_BYTES = 16 * 1024 * 1024
ECMWF_ENSEMBLE_BOUNDS = {"south": 45.0, "west": -58.0, "north": 50.5, "east": -46.0}

# ECMWF parameter name -> canonical variable name
ECMWF_PARAM_MAP = {
    "2t": "temperature_2m",
    "2d": "dew_point_2m",
    "10u": "wind_u_10m",
    "10v": "wind_v_10m",
    "msl": "mean_sea_level_pressure",
    "tp": "precipitation_accumulation",
    "tcc": "total_cloud_geometric",
}

# GRIB short names produced by cfgrib for ECMWF
ECMWF_GRIB_RENAME = {
    "t2m": "temperature_2m",
    "d2m": "dew_point_2m",
    "u10": "wind_u_10m",
    "v10": "wind_v_10m",
    "msl": "mean_sea_level_pressure",
    "tp": "precipitation_accumulation",
    "tcc": "total_cloud_geometric",
}


def parse_ecmwf_index(text: str, target_params: set[str]) -> list[tuple[int, int]]:
    """Parse ECMWF JSON-lines .index and return sorted (start, end) byte ranges."""
    selected_ranges: list[tuple[int, int]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except Exception:
            continue
        param = str(entry.get("param", "")).lower()
        if param in target_params:
            offset = entry.get("_offset")
            length = entry.get("_length")
            if offset is not None and length is not None:
                selected_ranges.append((int(offset), int(offset) + int(length) - 1))
    return sorted(selected_ranges, key=lambda item: item[0])


class ECMWFIFSAdapter:
    """Registered so the source id is known; never yields data (see module docstring)."""

    source_id = "ecmwf-ifs"
    adapter_version = "ecmwf-ifs-v1"

    def __init__(
        self,
        *,
        base_url: str = ECMWF_OPEN_DATA_BASE,
        bounds: Mapping[str, float] = ATLANTIC_CONTEXT_BOUNDS,
        client: PoliteClient | None = None,
    ) -> None:
        self._base_url = base_url
        self._bounds = dict(bounds)
        self._client = client

    def _get_client(self) -> PoliteClient:
        return self._client or PoliteClient()

    def discover(self, window: FetchWindow) -> list[RunCandidate]:
        raise AdapterUnavailable(UNRESOLVED_REASON)

    def fetch(self, candidate: RunCandidate, window: FetchWindow, workdir: Path) -> RunResult:
        raise AdapterUnavailable(UNRESOLVED_REASON)


IFS_ADAPTER = register(ECMWFIFSAdapter())


# ---------------------------------------------------------------------------
# The ensemble shapes: byte ranges over a member axis
# ---------------------------------------------------------------------------

#: The ECMWF ``.index`` record types that carry a member. ``cf`` is the
#: unperturbed control and ``pf`` a perturbed member; anything else in an index
#: (a provider reduction in an ``enfo-ep`` file, say) is not a member and is
#: never stacked onto the axis.
CONTROL_TYPE = "cf"
PERTURBED_TYPE = "pf"


@dataclass(frozen=True)
class IndexRecord:
    """One ``.index`` line, as the member selector reads it."""

    param: str
    number: str | None
    record_type: str | None
    offset: int
    length: int
    date: str | None = None
    time: str | None = None
    step: str | None = None
    stream: str | None = None

    @property
    def byte_range(self) -> tuple[int, int]:
        return (self.offset, self.offset + self.length - 1)


def parse_ecmwf_index_records(text: str) -> tuple[IndexRecord, ...]:
    """Every usable line of a ``.index``, with the member fields kept.

    :func:`parse_ecmwf_index` answers the deterministic question - which byte
    ranges hold these parameters - and deliberately drops ``number`` and
    ``type``. A member axis cannot be assembled without them: two records for
    ``tcc`` differ only by their ``number``, and dropping it is exactly how 50
    members would collapse into one field.
    """
    records: list[IndexRecord] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except Exception:
            continue
        offset, length = entry.get("_offset"), entry.get("_length")
        if offset is None or length is None:
            continue
        number = entry.get("number")
        record_type = entry.get("type")
        records.append(
            IndexRecord(
                param=str(entry.get("param", "")).lower(),
                number=None if number is None else str(number),
                record_type=None if record_type is None else str(record_type).lower(),
                offset=int(offset),
                length=int(length),
                date=None if entry.get("date") is None else str(entry["date"]),
                time=None if entry.get("time") is None else str(entry["time"]),
                step=None if entry.get("step") is None else str(entry["step"]),
                stream=None if entry.get("stream") is None else str(entry["stream"]).lower(),
            )
        )
    return tuple(records)


def member_of(record: IndexRecord, *, control_identifier: str | None) -> str | None:
    """The provider's own member token for one index record, or ``None``.

    A ``cf`` record is the control and takes the identifier the registry
    declares - ``0`` for both ECMWF families - rather than the record's own
    ``number``, which ECMWF publishes as ``0`` or omits depending on the file. A
    ``pf`` record is its ``number`` as a string. A record that is neither is not
    a member: it is skipped rather than guessed onto the axis.
    """
    if record.record_type == CONTROL_TYPE:
        return control_identifier
    if record.record_type == PERTURBED_TYPE and record.number:
        return record.number
    return None


def select_member_ranges(
    text: str,
    params: Sequence[str],
    *,
    control_identifier: str | None,
) -> tuple[dict[str, dict[str, tuple[int, int]]], tuple[str, ...]]:
    """Byte ranges per member per wanted parameter, and every param published.

    The second return value is what the producer advertises in this file, by the
    producer's own name, which is what the ``family_fields_only`` scope is
    applied to: everything in it outside the family fields becomes
    ``available-not-stored`` rather than vanishing.
    """
    wanted = {str(name).lower() for name in params}
    by_member: dict[str, dict[str, tuple[int, int]]] = {}
    published: list[str] = []
    for record in parse_ecmwf_index_records(text):
        if record.param not in published:
            published.append(record.param)
        if record.param not in wanted:
            continue
        member = member_of(record, control_identifier=control_identifier)
        if member is None:
            continue
        member_ranges = by_member.setdefault(member, {})
        if record.param in member_ranges:
            raise ValueError(
                f"duplicate_index_record:{member}:{record.param}: an exact member field must have one range"
            )
        member_ranges[record.param] = record.byte_range
    return by_member, tuple(published)


def family_upstream_params(source_id: str) -> tuple[str, ...]:
    """The catalogue-mapped ``stored`` upstream names for this source.

    The ``family_fields_only`` scope is not a list this adapter keeps: it is the
    field catalogue's own ``stored`` mapping, read here so the set requested and
    the set the scope checks are the same set by construction.
    """
    return tuple(
        item.upstream
        for item in catalogue.source_mapping(source_id)
        if item.storage == "stored" and item.upstream
    )


def family_keys_by_param(source_id: str) -> dict[str, str]:
    """``upstream name -> catalogue key`` for the stored family fields."""
    return {
        item.upstream: item.key
        for item in catalogue.source_mapping(source_id)
        if item.storage == "stored" and item.upstream
    }


def _refusing_reader(
    path: Path,
    *,
    param: str,
    member: str,
    bounds: Mapping[str, float],
    read_identity: bool = False,
) -> Any:
    """Decode one member's record out of a downloaded byte-range subset.

    The default is the real one: cfgrib opens the subset filtered to the
    parameter's shortName, the whole global record is cropped to the evidence
    box **locally** - these families cannot subset server side - units are
    normalized and the message's scalar coordinates (the GRIB ``number``
    included, kept as ``grib_number``) move into the variable's attrs so that
    one member's field carries no member coordinate of its own before
    :func:`ingest.grib.stack_members` builds the axis.
    """
    from ingest.grib import crop_to_bbox, normalize_units, open_grib, strip_message_scalars  # noqa: PLC0415

    identity_keys = (
        "dataDate",
        "dataTime",
        "stepRange",
        "shortName",
        "dataType",
        "validityDate",
        "validityTime",
        "marsStream",
    )
    decoded = open_grib(
        path,
        filter_by_keys={"shortName": param},
        read_keys=identity_keys if read_identity else None,
    )
    normalized = normalize_units(crop_to_bbox(decoded, bounds))
    names = [str(name) for name in normalized.data_vars]
    if not names:
        raise ValueError(f"no data variable decoded for shortName {param} of member {member}")
    field = normalized[names[0]].load()
    if param in {"tcc", "lcc", "mcc", "hcc"}:
        step_type = str(field.attrs.get("GRIB_stepType", "")).lower()
        if step_type != "instant":
            raise ValueError(
                f"{param} member {member} has GRIB_stepType={step_type!r}; "
                "an instantaneous cloud field was required"
            )
    return strip_message_scalars(field)


IFS_CYCLE_50R1_CONTROL_MAPPING = {
    "producer": "ECMWF",
    "cycle": "50r1",
    "source_stream": "oper",
    "source_type": "fc",
    "target_member": "0",
    "fields": ("tcc", "2t", "2d", "10u", "10v", "msl"),
}


def _assert_mapped_control_payload_identity(
    field: Any, *, param: str, candidate: RunCandidate
) -> None:
    """Verify identity from the mapped control's GRIB message, not its sidecar."""
    if candidate.run_time is None or not isinstance(candidate.detail.get("lead_hours"), int):
        raise ValueError("mapped_control_payload_identity:candidate_run_or_lead_missing")
    attrs = field.attrs
    expected = {
        "GRIB_dataDate": int(candidate.run_time.strftime("%Y%m%d")),
        "GRIB_dataTime": int(candidate.run_time.strftime("%H%M")),
        "GRIB_stepRange": str(candidate.detail["lead_hours"]),
        "GRIB_shortName": param,
        "GRIB_dataType": "fc",
        "GRIB_marsStream": "oper",
        "GRIB_validityDate": int(
            (candidate.run_time + timedelta(hours=candidate.detail["lead_hours"])).strftime("%Y%m%d")
        ),
        "GRIB_validityTime": int(
            (candidate.run_time + timedelta(hours=candidate.detail["lead_hours"])).strftime("%H%M")
        ),
    }
    for key, wanted in expected.items():
        actual = attrs.get(key)
        if str(actual).lower() != str(wanted).lower():
            raise ValueError(
                f"mapped_control_payload_identity:{param}:{key}={actual!r}: expected {wanted!r}"
            )


def _assert_exact_grid_and_bounds(
    fields: Mapping[str, Mapping[str, Any]], bounds: Mapping[str, float]
) -> None:
    """Refuse alignment, padding, or any source cell outside the evidence box."""
    import numpy  # noqa: PLC0415

    reference: tuple[Any, Any] | None = None
    for member, by_param in fields.items():
        for param, field in by_param.items():
            lat_name = "latitude" if "latitude" in field.coords else "lat" if "lat" in field.coords else None
            lon_name = "longitude" if "longitude" in field.coords else "lon" if "lon" in field.coords else None
            if lat_name is None or lon_name is None:
                raise AdapterUnavailable(f"grid_identity:{member}:{param}: latitude/longitude coordinates missing")
            latitudes = numpy.asarray(field[lat_name].values)
            longitudes = numpy.asarray(field[lon_name].values)
            if (
                not numpy.isfinite(latitudes).all()
                or not numpy.isfinite(longitudes).all()
                or float(latitudes.min()) < bounds["south"]
                or float(latitudes.max()) > bounds["north"]
                or float(longitudes.min()) < bounds["west"]
                or float(longitudes.max()) > bounds["east"]
            ):
                raise AdapterUnavailable(
                    f"grid_bounds:{member}:{param}: a source grid cell lies outside the declared bounds"
                )
            if reference is None:
                reference = (latitudes, longitudes)
            elif not (
                numpy.array_equal(reference[0], latitudes)
                and numpy.array_equal(reference[1], longitudes)
            ):
                raise AdapterUnavailable(
                    f"grid_identity:{member}:{param}: coordinates differ from the first decoded field"
                )


def _download_verified_range(
    client: Any,
    url: str,
    destination: Path,
    byte_range: tuple[int, int],
    *,
    response_evidence: dict[str, Any] | None = None,
) -> int:
    """Download one ECMWF record and verify the server honoured its index.

    The stricter response validation belongs to this unregistered experiment;
    it does not alter the shared client's behavior for accepted ingest paths.
    Test doubles may expose only ``download_ranges`` and are still checked
    against the index length after returning.
    """
    start, end = byte_range
    if start < 0 or end < start:
        raise ValueError(f"range_bounds:{start}-{end}: expected non-negative inclusive bounds")
    expected = end - start + 1
    if expected > MAX_MEMBER_BYTES:
        raise ValueError(f"range_length:{expected}: exceeds the {MAX_MEMBER_BYTES} byte ceiling")
    if isinstance(client, PoliteClient):
        response = client._request(
            "GET", url, headers={"Range": f"bytes={start}-{end}"}, stream=True
        )
        try:
            if response.status_code != 206:
                raise ValueError(f"range_status:{response.status_code}: expected 206")
            content_range = response.headers.get("Content-Range", "")
            match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", content_range)
            if (
                match is None
                or int(match.group(1)) != start
                or int(match.group(2)) != end
                or int(match.group(3)) <= end
            ):
                raise ValueError(
                    f"range_content_range:{content_range!r}: expected bytes {start}-{end}/<total>"
                )
            declared = response.headers.get("Content-Length", "")
            if declared:
                if not declared.isdigit() or int(declared) != expected:
                    raise ValueError(f"range_length:{declared}: expected {expected}")
            if response_evidence is not None:
                response_evidence.update(
                    {"http_status": response.status_code, "content_range": content_range}
                )
            destination.parent.mkdir(parents=True, exist_ok=True)
            written = 0
            try:
                with destination.open("wb") as handle:
                    for chunk in response.iter_bytes():
                        written += len(chunk)
                        if written > expected:
                            raise ValueError(f"range_length:{written}: expected {expected}")
                        handle.write(chunk)
                if written != expected:
                    raise ValueError(f"range_length:{written}: expected {expected}")
            except BaseException:
                destination.unlink(missing_ok=True)
                raise
            return written
        finally:
            response.close()
    downloaded = client.download_ranges(url, destination, [byte_range], max_bytes=MAX_MEMBER_BYTES)
    if downloaded != expected:
        raise ValueError(f"range_length:{downloaded}: expected {expected}")
    if response_evidence is not None:
        response_evidence.update(getattr(client, "last_response_evidence", {}))
    return downloaded


def _get_bounded_metadata(client: Any, url: str) -> str:
    """Read one listing or index under the experiment's metadata byte ceiling."""
    if not isinstance(client, PoliteClient):
        text = client.get_text(url)
        if len(text.encode()) > MAX_METADATA_BYTES:
            raise ValueError(f"metadata_length:{url}: exceeds {MAX_METADATA_BYTES} bytes")
        return text
    response = client._request("GET", url, stream=True)
    payload = bytearray()
    try:
        declared = response.headers.get("Content-Length", "")
        if declared.isdigit() and int(declared) > MAX_METADATA_BYTES:
            raise ValueError(f"metadata_length:{url}: declares {declared} bytes")
        for chunk in response.iter_bytes():
            payload.extend(chunk)
            if len(payload) > MAX_METADATA_BYTES:
                raise ValueError(f"metadata_length:{url}: exceeds {MAX_METADATA_BYTES} bytes")
    finally:
        response.close()
    return payload.decode("utf-8")


class _ECMWFEnsembleAdapter:
    """Shared machinery for the two ECMWF member families.

    Everything family-shaped - the member count, the control identifier, whether
    the control needs its own retrieval, the storage scope - is read from the
    registry's ``ensemble`` declaration at call time. Subclasses state only
    their source id, their product name and the file suffixes their access
    shape uses.
    """

    source_id: str = ""
    adapter_version: str = ""
    product: str = ""
    #: The file suffix holding the perturbed members, and the one holding the
    #: control where the control has its own file. ``None`` means the control
    #: rides in the member file.
    member_suffix: str = "pf"
    control_suffix: str | None = None

    def __init__(
        self,
        *,
        base_url: str = ECMWF_OPEN_DATA_BASE,
        bounds: Mapping[str, float] = ECMWF_ENSEMBLE_BOUNDS,
        client: PoliteClient | None = None,
        reader: Any = _refusing_reader,
        retain_inputs: bool = False,
    ) -> None:
        self._base_url = base_url
        self._bounds = dict(bounds)
        self._client = client
        self._reader = reader
        self._retain_inputs = retain_inputs
        self._range_evidence: list[dict[str, Any]] = []

    def _get_client(self) -> PoliteClient:
        return self._client or PoliteClient()

    # -------------------------------------------------------------- declaration

    def declaration(self) -> EnsembleDeclaration:
        declaration = get_config(self.source_id).ensemble
        if declaration is None:
            raise AdapterUnavailable(
                f"{self.source_id}: the registry record declares no ensemble block, so the member "
                "count, control rule and storage scope are unstated and nothing is retrieved"
            )
        return declaration

    def control_identifier(self) -> str | None:
        control = self.declaration().control
        return None if control is None else control.identifier

    def control_retrieval(self) -> str | None:
        """``separate_file`` or ``same_file``, from the declaration's own flag."""
        control = self.declaration().control
        if control is None or control.identifier is None:
            return None
        return "separate_file" if control.separate_retrieval else "same_file"

    def manifest(self) -> RunManifest:
        declaration = self.declaration()
        control = declaration.control
        keys = tuple(family_keys_by_param(self.source_id).values())
        return RunManifest(
            source_id=self.source_id,
            fields=tuple(
                RequiredField(
                    key,
                    catalogue.resolve(key).field.units or "",
                    optional=key != _ECMWF_MANDATORY_KEY,
                )
                for key in keys
            ),
            member_count=declaration.member_count,
            control=None if control is None else control.identifier,
            storage_scope=declaration.storage_scope,
        )

    # ------------------------------------------------------------- schedule gate

    def _gate(self) -> EnsembleDeclaration:
        declaration = self.declaration()
        if not declaration.schedulable:
            raise AdapterUnavailable(
                f"{self.source_id}: the registry declares {declaration.family} not schedulable. "
                f"{declaration.schedulable_reason}"
            )
        return declaration

    def discover(self, window: FetchWindow) -> list[RunCandidate]:
        self._gate()
        return self.discover_experiment(window)

    def fetch(self, candidate: RunCandidate, window: FetchWindow, workdir: Path) -> RunResult:
        self._gate()
        return self.assemble(candidate, window, workdir)

    def discover_experiment(
        self,
        window: FetchWindow,
        *,
        include_ifs_cycle_50r1_control: bool = False,
    ) -> list[RunCandidate]:
        """Discover every addressable lead in ``window`` without scheduling it.

        This is the explicitly unregistered experiment seam. ``discover`` still
        passes through the registry gate, while a bounded verification run can
        exercise the real portal listing without changing registry, scheduler,
        or operational status.
        """
        client = self._get_client()
        root_html = _get_bounded_metadata(client, f"{self._base_url}/")
        dates = sorted(
            {match.group("date") for match in _PORTAL_DATE.finditer(root_html)},
            reverse=True,
        )[:MAX_DISCOVERY_DATES]
        candidates: list[RunCandidate] = []
        metadata_requests = 1
        for date_text in dates:
            date_url = f"{self._base_url}/{date_text}/"
            date_html = _get_bounded_metadata(client, date_url)
            metadata_requests += 1
            cycles = {
                match.group("hour") for match in _PORTAL_CYCLE.finditer(date_html)
            }
            for cycle in FULL_ENSEMBLE_CYCLES:
                if cycle not in cycles:
                    continue
                directory = (
                    f"{date_url}{cycle}z/{'aifs-ens' if self.control_suffix else 'ifs'}"
                    "/0p25/enfo/"
                )
                listing = _get_bounded_metadata(client, directory)
                metadata_requests += 1
                mapped_controls: dict[tuple[str, int], str] = {}
                if include_ifs_cycle_50r1_control:
                    if self.source_id != "ecmwf-ens":
                        raise ValueError("Cycle 50r1 oper:fc mapping applies only to ecmwf-ens")
                    oper_directory = f"{date_url}{cycle}z/ifs/0p25/oper/"
                    metadata_requests += 1
                    if metadata_requests > MAX_MAPPED_CONTROL_DISCOVERY_REQUESTS:
                        raise AdapterUnavailable("IFS mapped-control discovery exceeded its request ceiling")
                    try:
                        oper_listing = _get_bounded_metadata(client, oper_directory)
                    except Exception as error:
                        _log.warning("IFS mapped-control listing unavailable at %s: %s", oper_directory, error)
                        oper_listing = ""
                    for oper_match in _IFS_OPER_FILE.finditer(oper_listing):
                        oper_stamp = oper_match.group("stamp")
                        oper_lead = int(oper_match.group("lead"))
                        mapped_controls[(oper_stamp, oper_lead)] = urljoin(
                            oper_directory, oper_match.group(0)
                        )
                files: dict[tuple[str, int], dict[str, str]] = {}
                for match in _ENSEMBLE_FILE.finditer(listing):
                    suffix = match.group("suffix")
                    if suffix not in {self.member_suffix, self.control_suffix}:
                        continue
                    stamp = match.group("stamp")
                    lead = int(match.group("lead"))
                    filename = match.group(0)
                    files.setdefault((stamp, lead), {})[suffix] = urljoin(directory, filename)
                for (stamp, lead), urls in files.items():
                    if self.member_suffix not in urls:
                        continue
                    run_time = datetime.strptime(stamp, "%Y%m%d%H%M%S").replace(tzinfo=UTC)
                    valid_time = run_time + timedelta(hours=lead)
                    if not window.covers(valid_time):
                        continue
                    detail = {
                        "member_url": urls[self.member_suffix],
                        "lead_hours": lead,
                        "valid_time": valid_time.isoformat(),
                        "metadata_requests": metadata_requests,
                    }
                    if self.control_suffix and self.control_suffix in urls:
                        detail["control_url"] = urls[self.control_suffix]
                    mapped_control_url = mapped_controls.get((stamp, lead))
                    if mapped_control_url:
                        detail["control_url"] = mapped_control_url
                        detail["ifs_cycle_50r1_control_mapping"] = {
                            **IFS_CYCLE_50R1_CONTROL_MAPPING,
                            "fields": list(IFS_CYCLE_50R1_CONTROL_MAPPING["fields"]),
                        }
                        urls["oper-fc-control0"] = mapped_control_url
                    candidates.append(
                        RunCandidate(
                            provider_run_id=f"{self.source_id}-{stamp}-f{lead:03d}",
                            run_time=run_time,
                            urls=list(urls.values()),
                            detail=detail,
                        )
                    )
        return sorted(candidates, key=lambda item: (item.run_time or datetime.min.replace(tzinfo=UTC), int(item.detail["lead_hours"])), reverse=True)

    # ------------------------------------------------------------- the retrieval

    def _read_one_file(
        self,
        *,
        url: str,
        params: Sequence[str],
        control_identifier: str | None,
        workdir: Path,
        label: str,
        errors: list[str],
        candidate: RunCandidate,
        mapped_control: bool = False,
    ) -> tuple[dict[str, dict[str, Any]], tuple[str, ...], tuple[str, ...]]:
        """One ``.index`` plus its byte ranges, decoded into member fields.

        Returns the decoded fields keyed by member and then by the producer's
        own parameter name, every parameter the file advertises, and the
        parameters actually retrieved.
        """
        client = self._get_client()
        index_url = f"{url.removesuffix('.grib2')}.index"
        try:
            index_text = _get_bounded_metadata(client, index_url)
        except Exception as error:
            errors.append(f"index:{label}")
            _log.warning("ECMWF index sidecar unavailable at %s: %s", index_url, error)
            return {}, (), ()

        records = parse_ecmwf_index_records(index_text)
        if self._retain_inputs:
            (workdir / f"{label}.index").write_text(index_text)
        expected_date = candidate.run_time.strftime("%Y%m%d") if candidate.run_time else None
        expected_time = candidate.run_time.strftime("%H%M") if candidate.run_time else None
        expected_step = str(candidate.detail.get("lead_hours", ""))
        mismatches = sorted(
            {
                f"{record.date}/{record.time}/f{record.step}"
                for record in records
                if (expected_date and record.date != expected_date)
                or (expected_time and record.time != expected_time)
                or (expected_step and record.step != expected_step)
            }
        )
        if mismatches:
            errors.append(f"run_identity:{label}")
            _log.warning("ECMWF index identity mismatch for %s: %s", url, ", ".join(mismatches[:3]))
            return {}, tuple(dict.fromkeys(record.param for record in records)), ()
        if mapped_control:
            eligible = [
                record
                for record in records
                if record.param in params
                and record.record_type == IFS_CYCLE_50R1_CONTROL_MAPPING["source_type"]
                and record.stream == IFS_CYCLE_50R1_CONTROL_MAPPING["source_stream"]
                and record.number in (None, "0")
            ]
            by_member = {str(control_identifier): {}}
            for record in eligible:
                if record.param in by_member[str(control_identifier)]:
                    raise ValueError(f"duplicate_index_record:{control_identifier}:{record.param}")
                by_member[str(control_identifier)][record.param] = record.byte_range
            published = tuple(dict.fromkeys(record.param for record in records))
            for param in params:
                if param not in by_member[str(control_identifier)]:
                    errors.append(f"mapped_control_index_identity:{param}")
        else:
            by_member, published = select_member_ranges(
                index_text, params, control_identifier=control_identifier
            )
        fields: dict[str, dict[str, Any]] = {}
        retrieved: list[str] = []
        for member, ranges in sorted(by_member.items()):
            for param, byte_range in sorted(ranges.items()):
                selected_record = next(
                    record for record in records
                    if record.byte_range == byte_range and record.param == param
                )
                local = workdir / f"{label}.{member}.{param}.grib2"
                try:
                    response_evidence: dict[str, Any] = {}
                    byte_size = _download_verified_range(
                        client, url, local, byte_range, response_evidence=response_evidence
                    )
                    if self._retain_inputs:
                        shutil.copyfile(
                            local, workdir / f"{label}.{member}.{param}.source.grib2"
                        )
                    if mapped_control and self._reader is _refusing_reader:
                        field = self._reader(
                            local, param=param, member=member, bounds=self._bounds,
                            read_identity=True,
                        )
                    else:
                        field = self._reader(
                            local, param=param, member=member, bounds=self._bounds
                        )
                    if mapped_control:
                        _assert_mapped_control_payload_identity(
                            field, param=param, candidate=candidate
                        )
                    evidence = {
                        "member": member,
                        "parameter": param,
                        "url": url,
                        "range": [byte_range[0], byte_range[1]],
                        "byte_size": byte_size,
                        "sha256": hashlib.sha256(local.read_bytes()).hexdigest(),
                        "source_index_metadata": {
                            "stream": selected_record.stream,
                            "type": selected_record.record_type,
                            "number": selected_record.number,
                            "date": selected_record.date,
                            "time": selected_record.time,
                            "step": selected_record.step,
                            "parameter": selected_record.param,
                        },
                        **response_evidence,
                    }
                    if mapped_control:
                        evidence["decoded_grib_metadata"] = {
                            key.removeprefix("GRIB_"): value
                            for key, value in field.attrs.items()
                            if key in {
                                "GRIB_dataDate", "GRIB_dataTime", "GRIB_stepRange",
                                "GRIB_shortName", "GRIB_dataType", "GRIB_validityDate",
                                "GRIB_validityTime", "GRIB_marsStream",
                            }
                        }
                        evidence["producer_mapping"] = {
                            **IFS_CYCLE_50R1_CONTROL_MAPPING,
                            "fields": list(IFS_CYCLE_50R1_CONTROL_MAPPING["fields"]),
                        }
                    self._range_evidence.append(evidence)
                    fields.setdefault(member, {})[param] = field
                except Exception as error:
                    errors.append(f"member:{label}:{member}:{param}")
                    _log.warning("ECMWF member %s param %s failed: %s", member, param, error)
                    continue
                finally:
                    local.unlink(missing_ok=True)
                if param not in retrieved:
                    retrieved.append(param)
        return fields, published, tuple(retrieved)

    def _member_urls(self, candidate: RunCandidate) -> tuple[str, str | None]:
        """The perturbed-member URL and the control URL, from the candidate.

        The dated listing contract for ``data.ecmwf.int`` is still unresolved
        (see :data:`UNRESOLVED_REASON`), so the URLs are the candidate's own -
        the caller states which objects it means rather than this adapter
        guessing a cycle path.
        """
        member_url = candidate.detail.get("member_url")
        if not member_url:
            raise AdapterUnavailable(
                f"{self.source_id}: the candidate names no member file URL, and the dated listing "
                "contract for data.ecmwf.int is unresolved, so no object is addressed"
            )
        control_url = candidate.detail.get("control_url")
        if self.control_suffix is not None and not control_url:
            control_url = str(member_url).replace(f"-{self.member_suffix}.", f"-{self.control_suffix}.")
        return str(member_url), (str(control_url) if control_url else None)

    def assemble(self, candidate: RunCandidate, window: FetchWindow, workdir: Path) -> RunResult:
        import xarray  # noqa: PLC0415

        declaration = self.declaration()
        control = self.control_identifier()
        params = family_upstream_params(self.source_id)
        keys_by_param = family_keys_by_param(self.source_id)
        retrieved_at = datetime.now(UTC)
        self._range_evidence = []
        member_url, control_url = self._member_urls(candidate)

        errors: list[str] = []
        fields, published, retrieved = self._read_one_file(
            url=member_url,
            params=params,
            control_identifier=control,
            workdir=workdir,
            label=self.member_suffix,
            errors=errors,
            candidate=candidate,
        )
        published_names = list(published)
        retrieved_names = list(retrieved)

        mapped_control_metadata: dict[str, Any] | None = None
        mapping = candidate.detail.get("ifs_cycle_50r1_control_mapping")
        if mapping is not None:
            expected_mapping = {
                **IFS_CYCLE_50R1_CONTROL_MAPPING,
                "fields": list(IFS_CYCLE_50R1_CONTROL_MAPPING["fields"]),
            }
            if self.source_id != "ecmwf-ens" or mapping != expected_mapping:
                errors.append("mapped_control_authorization_identity")
            else:
                mapped_url = candidate.detail.get("control_url")
                stamp = candidate.run_time.strftime("%Y%m%d%H%M%S") if candidate.run_time else ""
                lead = candidate.detail.get("lead_hours")
                expected_url = (
                    f"{self._base_url}/{candidate.run_time:%Y%m%d}/{candidate.run_time:%H}z"
                    f"/ifs/0p25/oper/{stamp}-{lead}h-oper-fc.grib2"
                    if candidate.run_time else ""
                )
                if not isinstance(mapped_url, str) or mapped_url != expected_url:
                    errors.append("mapped_control_url_identity")
                else:
                    control_fields, control_published, control_retrieved = self._read_one_file(
                        url=mapped_url,
                        params=IFS_CYCLE_50R1_CONTROL_MAPPING["fields"],
                        control_identifier=control,
                        workdir=workdir,
                        label="oper-fc-control0",
                        errors=errors,
                        candidate=candidate,
                        mapped_control=True,
                    )
                    for member, by_param in control_fields.items():
                        fields.setdefault(member, {}).update(by_param)
                    for name in control_published:
                        if name not in published_names:
                            published_names.append(name)
                    for name in control_retrieved:
                        if name not in retrieved_names:
                            retrieved_names.append(name)
                    mapped_control_metadata = {
                        **expected_mapping,
                        "source_url": mapped_url,
                        "source_index_url": f"{mapped_url.removesuffix('.grib2')}.index",
                    }

        # The AIFS-ENS shape: the control is a whole separate object. Its
        # absence is a missing member, never a failed run - the 50 perturbed
        # members that did arrive are real, and the axis publishes partial with
        # the control named.
        if self.control_suffix is not None and control_url:
            control_fields, control_published, control_retrieved = self._read_one_file(
                url=control_url,
                params=params,
                control_identifier=control,
                workdir=workdir,
                label=self.control_suffix,
                errors=[],  # a missing control is judged on the axis, not as a decode error
                candidate=candidate,
            )
            for member, by_param in control_fields.items():
                fields.setdefault(member, {}).update(by_param)
            for name in control_published:
                if name not in published_names:
                    published_names.append(name)
            for name in control_retrieved:
                if name not in retrieved_names:
                    retrieved_names.append(name)

        if not fields:
            raise AdapterUnavailable(
                f"{self.source_id}: no member decoded for {candidate.provider_run_id}; an ensemble "
                "artifact with no members is an absent ensemble, not a thin one"
            )

        for member, by_param in fields.items():
            for param in params:
                if param not in by_param:
                    errors.append(f"member_field_missing:{member}:{param}")

        _assert_exact_grid_and_bounds(fields, self._bounds)

        stacked: dict[str, Any] = {}
        for param, key in keys_by_param.items():
            by_member = {
                member: by_param[param] for member, by_param in sorted(fields.items()) if param in by_param
            }
            if by_member:
                stacked[key] = stack_members(by_member, control=control)

        # A partial mapped control can leave different variables with different
        # member sets. Build the shared control coordinate after xarray aligns
        # those sets, so inconsistent input becomes null/incomplete rather than
        # raising a coordinate merge error before validation can report it.
        try:
            dataset = xarray.Dataset(stacked)
        except xarray.MergeError:
            without_control = {
                key: field.drop_vars("control") if "control" in field.coords else field
                for key, field in stacked.items()
            }
            dataset = xarray.Dataset(without_control)
            if "member" in dataset.coords and control is not None:
                dataset = dataset.assign_coords(
                    control=("member", [str(member) == control for member in dataset.member.values])
                )
        lead_hours = candidate.detail.get("lead_hours")
        if candidate.run_time is None or not isinstance(lead_hours, int):
            raise AdapterUnavailable(
                f"{self.source_id}: candidate lacks exact run/lead identity; no valid time can be assigned"
            )
        valid_time = candidate.run_time + timedelta(hours=lead_hours)
        dataset = dataset.expand_dims(valid_time=[valid_time.replace(tzinfo=None)])
        manifest = self.manifest()
        control_retrieval = "separate_file" if mapped_control_metadata else self.control_retrieval()
        validation = validate_run(
            manifest,
            dataset,
            window=window,
            decode_errors=errors,
            upstream_fields=published_names,
            retrieved_fields=retrieved_names,
            declared_members=self.declared_members(),
            control_retrieval=control_retrieval,
        )

        provenance = {
            "source_id": self.source_id,
            "producer": "ECMWF",
            "product": self.product,
            "family": declaration.family,
            "adapter_version": self.adapter_version,
            "licence": "ECMWF real-time open data, CC BY 4.0",
            "attribution": "ECMWF",
            "subsetting": declaration.subsetting,
            "bounds": dict(self._bounds),
            "run_time": candidate.run_time.isoformat(),
            "provider_run_id": candidate.provider_run_id,
            "lead_hours": lead_hours,
            "valid_time": valid_time.isoformat(),
            "valid_times": [valid_time.isoformat()],
            "member_file": member_url,
            "control_file": control_url if self.control_suffix is not None else None,
            "mapped_control": mapped_control_metadata,
            "quality": validation.as_quality(),
            "coverage": validation.as_coverage(),
            "members": validation.as_members(),
            "storage_scope": validation.as_storage_scope(),
            "upstream_ranges": list(self._range_evidence),
            "upstream_bytes": sum(item["byte_size"] for item in self._range_evidence),
            **manifest.as_manifest_block(),
        }

        payload_path = workdir / f"{self.source_id.replace('-', '_')}_members.zarr.zip"
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
            notes=f"{declaration.family} members via .index byte ranges; {validation.detail}",
        )

    def declared_members(self) -> tuple[str, ...]:
        """``0`` (the control) then ``1``..``50``, from the declared count.

        The GRIB ``number`` as a string, which is what both ECMWF families
        publish. A family whose count the registry does not state cannot have
        its members enumerated, and none is invented here.
        """
        declaration = self.declaration()
        if declaration.member_count is None:
            return ()
        control = self.control_identifier()
        perturbed = declaration.member_count - (1 if control is not None else 0)
        return ((control,) if control is not None else ()) + tuple(
            str(index) for index in range(1, perturbed + 1)
        )


#: The one field either ECMWF ensemble run is not worth publishing without: the
#: instantaneous per-member total cloud column, which is the quantity this
#: experiment draws. Every other family field is optional, so one absent
#: parameter costs that field and not the run.
_ECMWF_MANDATORY_KEY = "total_cloud_geometric"

#: Ceiling on one member's one-parameter byte range. The largest measured record
#: is the AIFS-ENS ``tcc`` at 1 448 560 bytes (2026-09-02); 8 MiB is ~5x that
#: and still three orders of magnitude below a whole-file pull (the f024 ``pf``
#: file is 4.16 GiB).
MAX_MEMBER_BYTES = 8 * 1024 * 1024


class ECMWFAIFSEnsembleAdapter(_ECMWFEnsembleAdapter):
    """AIFS-ENS: 50 perturbed members in ``pf``, the control in its own ``cf``."""

    source_id = "ecmwf-aifs-ens"
    adapter_version = "ecmwf-aifs-ens-v1"
    product = "AIFS ensemble (aifs-ens 0.25 deg enfo)"
    member_suffix = "pf"
    control_suffix = "cf"


class ECMWFENSEnsembleAdapter(_ECMWFEnsembleAdapter):
    """IFS ENS with an optional, exact Cycle 50r1 experimental control mapping.

    The measured ``enfo-ef`` file carries ``type=pf`` numbers 1 to 50 and no
    ``cf`` record. Without the authorized six-field ``oper:fc`` mapping, the 50
    real perturbed members publish partial and control ``0`` stays missing.
    """

    source_id = "ecmwf-ens"
    adapter_version = "ecmwf-ens-v1"
    product = "IFS ensemble (ifs 0.25 deg enfo)"
    member_suffix = "ef"
    control_suffix = None

    def control_retrieval(self) -> str | None:
        """No control object is exposed in the verified Open Data ``enfo`` path."""
        return None


AIFS_ENS_ADAPTER: Adapter = register(ECMWFAIFSEnsembleAdapter())
IFS_ENS_ADAPTER: Adapter = register(ECMWFENSEnsembleAdapter())
