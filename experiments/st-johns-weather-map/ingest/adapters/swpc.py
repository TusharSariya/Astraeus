"""NOAA SWPC space-weather adapters: planetary Kp, real-time solar wind, OVATION.

Four adapters over the keyless SWPC JSON services, in the AWC pattern:
injectable PoliteClient and URLs, JSON parsed in ``discover`` and carried
through ``RunCandidate.detail``, xarray to zipped Zarr.

Honesty rules specific to space weather:

- Observed and forecast Kp are separate artifacts; the forecast keeps the
  provider's own per-value ``observed|estimated|predicted`` status as a
  flag-coded variable. No lead hours are synthesized.
- These series carry deliberately NO latitude/longitude: a planetary or L1
  quantity must never reach ``/point`` wearing a sample distance. Only the
  OVATION grid - genuinely gridded - keeps coordinates.
- Every timestamp comes from the feed itself; an OVATION payload without its
  own Observation/Forecast Time is refused, never wall-clock stamped.
- DSCOVR is gone from the real-time solar wind feed. Nothing here names a
  spacecraft: the feed's own ``source`` token per record is the only
  authority, so the L1 series is stored on a ``spacecraft`` axis whose
  labels are those tokens verbatim (SWFO-L1 as ``SOLAR1``, ``ACE``,
  ``IMAP``), and a reading is never detached from the craft that took it.
  Which craft the feed calls primary is the feed's own ``active`` flag,
  stored per row like any other value rather than resolved away here.
- Every quality flag the feed serves is stored, including the ``-9999``
  sentinel SWPC puts in ``max_data_flag``, verbatim and un-recoded: a
  reading whose quality the provider could not state must not arrive
  looking clean. A null stays NaN; a spacecraft absent at an instant stays
  NaN in that cell.
"""

from __future__ import annotations

import logging
import hashlib
import json
import shutil
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import httpx
import numpy
import xarray

from ingest.contract import (
    ATLANTIC_CONTEXT_BOUNDS,
    MEDIA_ZARR,
    AdapterUnavailable,
    Artifact,
    DiscoveryBounds,
    FetchWindow,
    ResourceBounds,
    RunCandidate,
    RunResult,
)
from ingest.grib import write_zarr
from ingest.http import MaxBytesExceeded, PoliteClient, RetriesExhausted
from ingest.isolation import BoundedProcessError, ProcessAllocationLimits, run_bounded_process
from ingest.manifest import declared_classes
from ingest.registry import register
from ingest.space_weather import (
    MAX_LARGE_FEED_BYTES,
    FeedReceipt,
    fetch_json,
    flag_attrs,
    flag_or_nan,
    float_or_nan,
    format_time,
    parse_time,
    platform_series_dataset,
    records as _feed_records,
    series_provenance,
    series_quality,
)

UTC = timezone.utc
_log = logging.getLogger(__name__)

SWPC_BASE = "https://services.swpc.noaa.gov"
KP_OBSERVED_URL = f"{SWPC_BASE}/products/noaa-planetary-k-index.json"
KP_FORECAST_URL = f"{SWPC_BASE}/products/noaa-planetary-k-index-forecast.json"
RTSW_MAG_URL = f"{SWPC_BASE}/json/rtsw/rtsw_mag_1m.json"
RTSW_WIND_URL = f"{SWPC_BASE}/json/rtsw/rtsw_wind_1m.json"
OVATION_URL = f"{SWPC_BASE}/json/ovation_aurora_latest.json"

KP_STATUS_VALUES = [0, 1, 2]
KP_STATUS_MEANINGS = "observed estimated predicted"
_KP_STATUS_CODE = {"observed": 0, "estimated": 1, "predicted": 2}
KP_DOCUMENT_BYTES = 512 * 1024
KP_PROCESS_LIMITS = ProcessAllocationLimits(
    address_space_bytes=256 * 1024 * 1024,
    output_bytes=KP_DOCUMENT_BYTES,
    stdin_bytes=KP_DOCUMENT_BYTES,
    stdout_bytes=KP_DOCUMENT_BYTES,
    stderr_bytes=64 * 1024,
)
KP_FILESYSTEM_MARGIN_BYTES = 4096
KP_FILESYSTEM_BLOCK_BYTES = 4096


#: The seam's parser and reader under the names this module has always
#: exported. They are the same behaviour, defined once in
#: ``ingest.space_weather`` so every space-weather adapter reads a feed the
#: same way; the aliases stay because callers (and the live-smoke tripwire)
#: import them from here.
_parse_time = parse_time
_float_or_nan = float_or_nan


def _records(payload: Any, *, required: Sequence[str]) -> list[dict[str, Any]]:
    """SWPC list payloads as dicts (objects or a header row); see the seam."""
    return _feed_records(payload, required=required)


def _series_dataset(times: list[datetime], variables: Mapping[str, tuple[numpy.ndarray, dict[str, Any]]], attrs: Mapping[str, Any]) -> xarray.Dataset:
    """A time-only dataset: deliberately no latitude/longitude coordinates."""
    stamps = numpy.array([numpy.datetime64(t.replace(tzinfo=None), "ns") for t in times])
    data_vars = {name: (("valid_time",), values, dict(var_attrs)) for name, (values, var_attrs) in variables.items()}
    return xarray.Dataset(data_vars, coords={"valid_time": stamps}, attrs=dict(attrs))


def _series_quality(name: str, values: numpy.ndarray) -> tuple[dict[str, Any], dict[str, Any]]:
    """Manual quality/coverage blocks for a coordinate-free series.

    ``validate_run`` requires a horizontal grid by design; these series have
    none on purpose, so their completeness is stated directly: the fraction
    of records carrying a finite value.
    """
    finite = float(numpy.isfinite(values).mean()) if values.size else 0.0
    quality = {
        "status": "passed" if finite > 0.0 else "failed",
        "flags": [] if finite > 0.0 else [f"empty_field:{name}"],
        "detail": f"{name}: {finite:.4f} of records carry a finite value; planetary series, no spatial coverage claimed",
    }
    coverage = {"status": "complete" if finite > 0.0 else "outside", "fraction": round(finite, 4)}
    return quality, coverage


class SWPCKpAdapter:
    """Planetary K index: the observed series and the provider's forecast."""

    source_id = "noaa-swpc-kp"
    adapter_version = "swpc-kp-isolated-v2"

    def __init__(self, client: PoliteClient | None = None, observed_url: str = KP_OBSERVED_URL, forecast_url: str = KP_FORECAST_URL) -> None:
        self._client = client
        self._observed_url = observed_url
        self._forecast_url = forecast_url

    def _get_client(self) -> PoliteClient:
        return self._client or PoliteClient()

    def operation_bounds(self, _window: FetchWindow) -> ResourceBounds:
        # The worker calls this before reserving resources or issuing discovery
        # requests; reject an unmeasured allocation geometry at that boundary.
        self._require_measured_filesystem(Path(tempfile.gettempdir()))
        self._require_bounded_runtime()
        return ResourceBounds(
            store_bytes=2 * KP_PROCESS_LIMITS.output_bytes,
            filesystem_bytes=2 * KP_PROCESS_LIMITS.output_bytes,
            margin_bytes=2 * KP_FILESYSTEM_MARGIN_BYTES,
            received_bytes=2 * KP_PROCESS_LIMITS.stdin_bytes,
        )

    def discovery_bounds(self, window: FetchWindow) -> DiscoveryBounds:
        return DiscoveryBounds(received_bytes=self.operation_bounds(window).received_bytes)

    def resource_bounds(self, _candidate: RunCandidate, window: FetchWindow) -> ResourceBounds:
        return self.operation_bounds(window)

    @staticmethod
    def _require_measured_filesystem(path: Path) -> None:
        """Fail closed unless the target matches the measured Linux allocation geometry."""
        geometry = path.stat().st_dev, path.stat().st_blksize, __import__("os").statvfs(path).f_frsize
        if geometry[1:] != (KP_FILESYSTEM_BLOCK_BYTES, KP_FILESYSTEM_BLOCK_BYTES):
            raise AdapterUnavailable(
                f"SWPC Kp bounded writer requires measured 4096-byte filesystem blocks; got {geometry[1:]}"
            )

    @staticmethod
    def _require_bounded_runtime() -> None:
        """Prove this runtime can lock both kernel limits before any source read."""
        run_bounded_process(
            command=[sys.executable, "-c", "import sys; assert len(sys.argv) == 2", "{output}"],
            stdin=b"",
            destination=None,
            limits=KP_PROCESS_LIMITS,
            timeout_seconds=5,
            require_output=False,
        )

    @staticmethod
    def _isolated(action: str, mode: str, raw: bytes, destination: Path | None):
        package_root = Path(__file__).resolve().parents[2]
        launcher = (
            "import sys; "
            f"sys.path.insert(0, {str(package_root)!r}); "
            "from ingest.kp3h_isolated import main; raise SystemExit(main())"
        )
        return run_bounded_process(
            command=[sys.executable, "-c", launcher, action, mode, "{output}"],
            stdin=raw,
            destination=destination,
            limits=KP_PROCESS_LIMITS,
            timeout_seconds=30,
            require_output=action == "normalize",
        )

    @staticmethod
    def _receipt(url: str, raw: bytes, headers: Mapping[str, str], completed_at: datetime) -> FeedReceipt:
        return FeedReceipt(
            url=url,
            byte_count=len(raw),
            sha256=hashlib.sha256(raw).hexdigest(),
            captured_at=completed_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            last_modified=headers.get("Last-Modified") or headers.get("last-modified"),
        )

    def discover(self, window: FetchWindow) -> list[RunCandidate]:
        client = self._get_client()
        try:
            observed_raw, observed_headers, observed_completed = client.get_bytes_with_headers_completed(
                self._observed_url, max_bytes=KP_PROCESS_LIMITS.stdin_bytes
            )
            observed_metadata = json.loads(self._isolated("inspect", "observed", observed_raw, None).stdout)
        except (BoundedProcessError, MaxBytesExceeded, RetriesExhausted, httpx.HTTPError, OSError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise AdapterUnavailable(f"SWPC Kp endpoint unavailable: {error}") from error

        # The forecast feed failing must not stop the observed series.
        forecast_raw: bytes | None = None
        forecast_receipt: FeedReceipt | None = None
        forecast_completed: datetime | None = None
        forecast_times: list[datetime] = []
        forecast_error = ""
        try:
            forecast_raw, forecast_headers, forecast_completed = client.get_bytes_with_headers_completed(
                self._forecast_url, max_bytes=KP_PROCESS_LIMITS.stdin_bytes
            )
            forecast_metadata = json.loads(self._isolated("inspect", "forecast", forecast_raw, None).stdout)
            forecast_times = [stamp for value in forecast_metadata["times"] if (stamp := _parse_time(value)) is not None]
            if len(forecast_times) != forecast_metadata["count"]:
                raise ValueError("isolated forecast inspection returned invalid times")
            forecast_receipt = self._receipt(self._forecast_url, forecast_raw, forecast_headers, forecast_completed)
        except (BoundedProcessError, KeyError, MaxBytesExceeded, RetriesExhausted, httpx.HTTPError, OSError, TypeError, ValueError, json.JSONDecodeError) as error:
            forecast_error = str(error)
            _log.warning("SWPC Kp forecast endpoint unavailable: %s", error)

        observed_times = [stamp for value in observed_metadata["times"] if (stamp := _parse_time(value)) is not None]
        if not observed_times or len(observed_times) != observed_metadata["count"]:
            raise AdapterUnavailable("isolated observed Kp inspection returned invalid times")
        newest = observed_times[-1]
        return [
            RunCandidate(
                provider_run_id=f"swpc-kp-{newest.strftime('%Y%m%d%H%M')}",
                run_time=newest,
                urls=[self._observed_url, self._forecast_url],
                detail={
                    "observed_raw": observed_raw,
                    "observed_receipt": self._receipt(self._observed_url, observed_raw, observed_headers, observed_completed),
                    "observed_completed": observed_completed,
                    "observed_times": [format_time(stamp) for stamp in observed_times],
                    "forecast_raw": forecast_raw,
                    "forecast_receipt": forecast_receipt,
                    "forecast_completed": forecast_completed if forecast_receipt is not None else None,
                    "forecast_times": [format_time(stamp) for stamp in forecast_times],
                    "forecast_error": forecast_error,
                },
            )
        ]

    def fetch(self, candidate: RunCandidate, window: FetchWindow, workdir: Path) -> RunResult:
        workdir.mkdir(parents=True, exist_ok=True)
        self._require_measured_filesystem(workdir)
        observed_raw = candidate.detail.get("observed_raw")
        observed_receipt = candidate.detail.get("observed_receipt")
        forecast_raw = candidate.detail.get("forecast_raw")
        forecast_receipt = candidate.detail.get("forecast_receipt")
        if not isinstance(observed_raw, bytes) or not isinstance(observed_receipt, FeedReceipt):
            raise AdapterUnavailable("SWPC Kp fetch carried no bounded observed document or receipt")

        completed = [value for value in (candidate.detail.get("observed_completed"), candidate.detail.get("forecast_completed"))
                     if isinstance(value, datetime)]
        if not completed:
            raise AdapterUnavailable("SWPC Kp fetch carried no transport completion time")
        retrieved_at = max(completed)
        artifacts: list[Artifact] = []
        notes: list[str] = []
        complete = True

        def provenance(quality: dict[str, Any], coverage: dict[str, Any], product: str, receipt: FeedReceipt) -> dict[str, Any]:
            return {
                "source_id": self.source_id,
                "producer": "NOAA Space Weather Prediction Center",
                "product": product,
                "native_resolution": "planetary index (no spatial resolution)",
                "native_crs": "not_applicable",
                "adapter_version": self.adapter_version,
                "quality": quality,
                "coverage": coverage,
                "receipts": [receipt.as_dict()],
                # The planetary indices as SWPC issued them.
                **declared_classes(["retrieved"]),
            }

        times = [_parse_time(value) for value in candidate.detail.get("observed_times") or []]
        if not times or any(stamp is None for stamp in times):
            raise AdapterUnavailable("SWPC Kp fetch carried no observed times")
        valid_times = [stamp for stamp in times if stamp is not None]
        observed_path = workdir / "swpc_kp_observed.zarr.zip"
        try:
            self._isolated("normalize", "observed", observed_raw, observed_path)
        except BoundedProcessError as error:
            raise AdapterUnavailable(f"SWPC observed Kp isolated normalization failed: {error}") from error
        quality = {"status": "passed", "flags": [], "detail": f"all {len(valid_times)} observed rows passed isolated validation"}
        coverage = {"status": "complete", "fraction": 1.0}
        artifacts.append(Artifact("kp_observed", MEDIA_ZARR, observed_path, provenance(quality, coverage, "Planetary K index (observed)", observed_receipt)))
        notes.append(f"{len(valid_times)} observed Kp records")

        if isinstance(forecast_raw, bytes) and isinstance(forecast_receipt, FeedReceipt):
            f_times = [_parse_time(value) for value in candidate.detail.get("forecast_times") or []]
            if not f_times or any(stamp is None for stamp in f_times):
                observed_path.unlink(missing_ok=True)
                raise AdapterUnavailable("SWPC Kp fetch carried invalid forecast times")
            forecast_path = workdir / "swpc_kp_forecast.zarr.zip"
            try:
                self._isolated("normalize", "forecast", forecast_raw, forecast_path)
            except BoundedProcessError as error:
                observed_path.unlink(missing_ok=True)
                raise AdapterUnavailable(f"SWPC forecast Kp isolated normalization failed: {error}") from error
            f_quality = {"status": "passed", "flags": [], "detail": f"all {len(f_times)} forecast rows passed isolated validation"}
            f_coverage = {"status": "complete", "fraction": 1.0}
            artifacts.append(Artifact("kp_forecast", MEDIA_ZARR, forecast_path, provenance(f_quality, f_coverage, "Planetary K index (3-day outlook, per-value status)", forecast_receipt)))
            notes.append(f"{len(f_times)} forecast Kp records with provider status")
        else:
            reason = candidate.detail.get("forecast_error") or "forecast feed returned no records"
            notes.append(f"no kp_forecast artifact: {reason}")
            complete = False

        return RunResult(
            source_id=self.source_id,
            provider_run_id=candidate.provider_run_id,
            run_time=candidate.run_time or times[-1],
            retrieved_at=retrieved_at,
            complete=complete,
            qc_passed=True,
            artifacts=artifacts,
            native_crs=None,
            notes="; ".join(notes),
        )


@dataclass(frozen=True)
class _Field:
    """One stored variable of an interleaved L1 feed.

    ``name`` is both the stored variable name and the feed's own key: the
    two rtsw feeds spell every field exactly as the pinned contract does
    (verified against a live capture, 2026-09-05), so there is no rename
    to hide a drift behind. A field the feed stops serving becomes NaN
    everywhere rather than silently disappearing.
    """

    name: str
    attrs: dict[str, Any]
    #: Booleans go through ``flag_or_nan`` so ``false`` stays 0 and absent
    #: stays NaN; numbers go through ``float_or_nan``.
    flag: bool = False
    #: Counted in provenance ``quality_flags_stored`` - the provider's own
    #: quality statement about the row, stored, never used to filter here.
    quality: bool = False


def _measured(units: str, long_name: str, *, original: str | None = None) -> dict[str, Any]:
    return {"units": units, "original_units": original or units, "long_name": long_name}


def _verbatim_flag(long_name: str, *, sentinel: bool = False) -> dict[str, Any]:
    """A provider integer kept exactly as served, sentinel included."""
    attrs = {
        "units": "dimensionless",
        "original_units": "provider flag integer",
        "long_name": long_name,
    }
    if sentinel:
        # SWPC serves -9999 where it has no flag to give. It is stored as
        # -9999, not as a gap and not as zero, so a consumer can tell
        # "no quality stated" from "quality nominal".
        attrs["sentinel_as_served"] = -9999
    return attrs


_ACTIVE_FIELD = _Field(
    "active",
    flag_attrs(["inactive", "active"], long_name="the feed's own primary-spacecraft flag for this row"),
    flag=True,
    quality=True,
)

RTSW_MAG_FIELDS: tuple[_Field, ...] = (
    _Field("bt", _measured("nT", "interplanetary magnetic field total, as retrieved")),
    _Field("bx_gse", _measured("nT", "interplanetary magnetic field Bx, GSE, as retrieved")),
    _Field("by_gse", _measured("nT", "interplanetary magnetic field By, GSE, as retrieved")),
    _Field("bz_gse", _measured("nT", "interplanetary magnetic field Bz, GSE, as retrieved")),
    _Field("bx_gsm", _measured("nT", "interplanetary magnetic field Bx, GSM, as retrieved")),
    _Field("by_gsm", _measured("nT", "interplanetary magnetic field By, GSM, as retrieved")),
    _Field("bz_gsm", _measured("nT", "interplanetary magnetic field Bz, GSM, as retrieved")),
    _Field("theta_gse", _measured("degree", "field latitude angle, GSE, as retrieved")),
    _Field("phi_gse", _measured("degree", "field longitude angle, GSE, as retrieved")),
    _Field("theta_gsm", _measured("degree", "field latitude angle, GSM, as retrieved")),
    _Field("phi_gsm", _measured("degree", "field longitude angle, GSM, as retrieved")),
    _Field("sample_size", _measured("dimensionless", "samples averaged into this minute, as retrieved")),
    _Field("range", _measured("dimensionless", "magnetometer range as served; NaN where the feed serves null")),
    _Field("scale", _measured("dimensionless", "magnetometer scale as served; NaN where the feed serves null")),
    _Field("sensitivity", _measured("dimensionless", "magnetometer sensitivity as served; NaN where the feed serves null")),
    _Field("manual_mode", flag_attrs(["false", "true"], long_name="provider manual-mode flag"), flag=True, quality=True),
    _ACTIVE_FIELD,
    _Field("max_telemetry_flag", _verbatim_flag("provider maximum telemetry flag, verbatim", sentinel=True), quality=True),
    _Field("max_data_flag", _verbatim_flag("provider maximum data flag, verbatim", sentinel=True), quality=True),
    _Field("overall_quality", _verbatim_flag("provider overall quality, verbatim", sentinel=True), quality=True),
)

_PLASMA_SPEED = "km s-1"
RTSW_WIND_FIELDS: tuple[_Field, ...] = (
    _Field("proton_speed", _measured(_PLASMA_SPEED, "solar wind proton bulk speed, as retrieved")),
    _Field("alpha_speed", _measured(_PLASMA_SPEED, "solar wind alpha bulk speed, as retrieved")),
    _Field("proton_temperature", _measured("K", "solar wind proton temperature, as retrieved")),
    _Field("alpha_temperature", _measured("K", "solar wind alpha temperature, as retrieved")),
    _Field("proton_density", _measured("cm-3", "solar wind proton number density, as retrieved")),
    _Field("alpha_density", _measured("cm-3", "solar wind alpha number density, as retrieved")),
    _Field("proton_vx_gse", _measured(_PLASMA_SPEED, "proton velocity Vx, GSE, as retrieved")),
    _Field("proton_vy_gse", _measured(_PLASMA_SPEED, "proton velocity Vy, GSE, as retrieved")),
    _Field("proton_vz_gse", _measured(_PLASMA_SPEED, "proton velocity Vz, GSE, as retrieved")),
    _Field("proton_vx_gsm", _measured(_PLASMA_SPEED, "proton velocity Vx, GSM, as retrieved")),
    _Field("proton_vy_gsm", _measured(_PLASMA_SPEED, "proton velocity Vy, GSM, as retrieved")),
    _Field("proton_vz_gsm", _measured(_PLASMA_SPEED, "proton velocity Vz, GSM, as retrieved")),
    _Field("alpha_vx_gse", _measured(_PLASMA_SPEED, "alpha velocity Vx, GSE, as retrieved")),
    _Field("alpha_vy_gse", _measured(_PLASMA_SPEED, "alpha velocity Vy, GSE, as retrieved")),
    _Field("alpha_vz_gse", _measured(_PLASMA_SPEED, "alpha velocity Vz, GSE, as retrieved")),
    _Field("alpha_vx_gsm", _measured(_PLASMA_SPEED, "alpha velocity Vx, GSM, as retrieved")),
    _Field("alpha_vy_gsm", _measured(_PLASMA_SPEED, "alpha velocity Vy, GSM, as retrieved")),
    _Field("alpha_vz_gsm", _measured(_PLASMA_SPEED, "alpha velocity Vz, GSM, as retrieved")),
    _Field("proton_sample_size", _measured("dimensionless", "proton samples averaged into this minute, as retrieved")),
    _Field("alpha_sample_size", _measured("dimensionless", "alpha samples averaged into this minute, as retrieved")),
    _ACTIVE_FIELD,
    _Field("max_convergence_flag", _verbatim_flag("provider maximum convergence flag, verbatim"), quality=True),
    _Field("max_data_flag", _verbatim_flag("provider maximum data flag, verbatim"), quality=True),
    _Field("max_error_count_flag", _verbatim_flag("provider maximum error count flag, verbatim"), quality=True),
    _Field("max_processing_flag", _verbatim_flag("provider maximum processing flag, verbatim"), quality=True),
    _Field("max_range_flag", _verbatim_flag("provider maximum range flag, verbatim"), quality=True),
    _Field("max_sample_count_flag", _verbatim_flag("provider maximum sample count flag, verbatim"), quality=True),
    _Field("max_telemetry_flag", _verbatim_flag("provider maximum telemetry flag, verbatim"), quality=True),
    _Field("overall_quality", _verbatim_flag("provider overall quality, verbatim"), quality=True),
)


def _parse_platform_records(
    records: list[dict[str, Any]], fields: Sequence[_Field]
) -> tuple[list[datetime], list[str], dict[str, numpy.ndarray]]:
    """The one parser both interleaved L1 feeds use.

    The rtsw feeds serve one record per (instant, spacecraft), newest first,
    with the spacecraft in the record's own ``source`` token. This lays them
    onto the union of the instants any spacecraft reported times the sorted
    set of the tokens seen, so a spacecraft that did not report at an
    instant holds NaN in that cell rather than borrowing its neighbour's
    reading. A record without a parseable instant or a declared source is
    dropped: it names no time and no craft, so it is not evidence.
    """
    rows: list[tuple[datetime, str, dict[str, Any]]] = []
    for record in records:
        stamp = _parse_time(record.get("time_tag"))
        raw_source = record.get("source")
        label = str(raw_source).strip() if isinstance(raw_source, str) else ""
        if stamp is None or not label:
            continue
        rows.append((stamp, label, record))
    if not rows:
        raise AdapterUnavailable("the rtsw feed carried no record with both a parseable time_tag and a declared source")
    times = sorted({stamp for stamp, _, _ in rows})
    labels = sorted({label for _, label, _ in rows})
    time_index = {stamp: index for index, stamp in enumerate(times)}
    label_index = {label: index for index, label in enumerate(labels)}
    arrays = {field.name: numpy.full((len(times), len(labels)), numpy.nan) for field in fields}
    for stamp, label, record in rows:
        row, column = time_index[stamp], label_index[label]
        for field in fields:
            raw = record.get(field.name)
            arrays[field.name][row, column] = flag_or_nan(raw) if field.flag else float_or_nan(raw)
    return times, labels, arrays


def _active_at(times: list[datetime], labels: list[str], active: numpy.ndarray) -> str | None:
    """The spacecraft the feed flagged active at the newest instant, if any."""
    newest = active[-1]
    flagged = [labels[index] for index, value in enumerate(newest) if value == 1.0]
    return flagged[0] if len(flagged) == 1 else None


class _RTSWFeedAdapter:
    """Shared behaviour for the two interleaved real-time solar wind feeds.

    Both are the same shape - one JSON list of per-(minute, spacecraft)
    records under a byte ceiling - so discovery, the staleness guard and the
    write differ only in which fields are stored and what the product is
    called. Subclasses supply those; nothing else is per-feed.
    """

    source_id: str
    adapter_version: str
    logical_name: str
    product: str
    run_prefix: str
    key_variable: str
    fields: tuple[_Field, ...]
    required_keys: tuple[str, ...]
    required_physical_fields: tuple[str, ...]
    default_url: str

    def __init__(self, client: PoliteClient | None = None, url: str | None = None) -> None:
        self._client = client
        self._url = url or self.default_url

    def _get_client(self) -> PoliteClient:
        return self._client or PoliteClient()

    def discover(self, window: FetchWindow) -> list[RunCandidate]:
        scratch = Path(tempfile.mkdtemp(prefix="rtsw-"))
        try:
            payload, receipt = fetch_json(
                self._get_client(), self._url, max_bytes=MAX_LARGE_FEED_BYTES, workdir=scratch
            )
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
        records = _records(payload, required=self.required_keys)
        if not records:
            raise AdapterUnavailable(
                f"{self._url} carried no record with {', '.join(self.required_keys)}; refused rather than guessed"
            )
        times, labels, _arrays = _parse_platform_records(records, self.fields)
        newest = times[-1]
        if newest < window.start:
            # An HTTP 200 over a frozen feed is not evidence of now.
            raise AdapterUnavailable(
                f"{self._url} is stale behind HTTP 200: its newest instant {format_time(newest)} "
                f"is older than the window start {format_time(window.start)}"
            )
        return [
            RunCandidate(
                provider_run_id=f"{self.run_prefix}-{newest.strftime('%Y%m%d%H%M')}",
                run_time=newest,
                urls=[self._url],
                detail={
                    "records": records,
                    "receipt": receipt,
                    "valid_times": [format_time(stamp) for stamp in times],
                    "spacecraft": labels,
                },
            )
        ]

    def fetch(self, candidate: RunCandidate, window: FetchWindow, workdir: Path) -> RunResult:
        records = candidate.detail.get("records") or []
        receipt = candidate.detail.get("receipt")
        if not records or not isinstance(receipt, FeedReceipt):
            raise AdapterUnavailable(f"{self.source_id} fetch carried no records or no retrieval receipt")
        times, labels, arrays = _parse_platform_records(records, self.fields)
        declared = ", ".join(labels)
        dataset = platform_series_dataset(
            times,
            labels,
            {field.name: (arrays[field.name], field.attrs) for field in self.fields},
            {
                "source": self.product,
                "feed_declared_spacecraft": declared,
                "spacecraft_axis_note": "labels are the feed's own source tokens, verbatim; a spacecraft absent at an instant is NaN there",
            },
            platform_dim="spacecraft",
        )
        quality, coverage = series_quality(
            self.key_variable,
            arrays[self.key_variable],
            required_fields={name: arrays[name] for name in self.required_physical_fields},
        )
        path = workdir / f"{self.logical_name}.zarr.zip"
        write_zarr(dataset, path)
        active_label = _active_at(times, labels, arrays["active"])
        provenance = series_provenance(
            source_id=self.source_id,
            producer="NOAA Space Weather Prediction Center",
            product=self.product,
            adapter_version=self.adapter_version,
            quality=quality,
            coverage=coverage,
            evidence_classes=["retrieved"],
            receipts=[receipt],
            native_resolution="L1 point measurement, 1-minute (no spatial resolution)",
            measurement_scope="l1",
            extra={
                "spacecraft": labels,
                "active_spacecraft_at_newest": active_label,
                "quality_flags_stored": [field.name for field in self.fields if field.quality],
                "feed_declared_spacecraft": declared,
            },
        )
        return RunResult(
            source_id=self.source_id,
            provider_run_id=candidate.provider_run_id,
            run_time=candidate.run_time or times[-1],
            retrieved_at=datetime.now(UTC),
            complete=coverage["status"] == "complete",
            qc_passed=True,
            artifacts=[Artifact(self.logical_name, MEDIA_ZARR, path, provenance)],
            native_crs=None,
            notes=(
                f"{len(records)} records over {len(times)} instants x spacecraft {declared}; "
                f"active at the newest instant: {active_label or 'none flagged'}"
            ),
        )


class SWPCSolarWindAdapter(_RTSWFeedAdapter):
    """The real-time solar wind magnetometer feed, per spacecraft.

    SWFO-L1 (the feed's ``SOLAR1``), ACE and IMAP are interleaved minute by
    minute; which one the feed calls primary moves. Storing them on a
    spacecraft axis with the feed's ``active`` flag per row is what lets a
    reader say which craft measured the Bz it is looking at.
    """

    source_id = "noaa-swpc-rtsw"
    adapter_version = "swpc-rtsw-v2"
    logical_name = "solar_wind"
    product = "Real-time solar wind magnetic field (1-minute, per spacecraft)"
    run_prefix = "swpc-rtsw"
    key_variable = "bz_gsm"
    fields = RTSW_MAG_FIELDS
    required_keys = ("time_tag", "source", "bz_gsm")
    required_physical_fields = ("bz_gsm", "bt")
    default_url = RTSW_MAG_URL


class SWPCPlasmaAdapter(_RTSWFeedAdapter):
    """The real-time solar wind plasma feed, per spacecraft.

    The old ``products/solar-wind/plasma-7-day.json`` product is HTTP 404
    (verified 2026-09-05); this rtsw wind feed is where the plasma moments
    live, and it is a separate source because it is a separate retrieval
    with its own receipt, its own quality flags and its own gaps.
    """

    source_id = "noaa-swpc-plasma"
    adapter_version = "swpc-plasma-v1"
    logical_name = "solar_wind_plasma"
    product = "Real-time solar wind plasma (1-minute, per spacecraft)"
    run_prefix = "swpc-plasma"
    key_variable = "proton_speed"
    fields = RTSW_WIND_FIELDS
    required_keys = ("time_tag", "source", "proton_speed")
    required_physical_fields = ("proton_speed", "proton_density", "proton_temperature")
    default_url = RTSW_WIND_URL


class SWPCOvationAdapter:
    """The OVATION aurora probability nowcast grid, cropped to the context box."""

    source_id = "noaa-swpc-ovation"
    adapter_version = "swpc-ovation-v1"

    def __init__(self, client: PoliteClient | None = None, url: str = OVATION_URL, bounds: Mapping[str, float] = ATLANTIC_CONTEXT_BOUNDS) -> None:
        self._client = client
        self._url = url
        self._bounds = dict(bounds)

    def _get_client(self) -> PoliteClient:
        return self._client or PoliteClient()

    def discover(self, window: FetchWindow) -> list[RunCandidate]:
        client = self._get_client()
        try:
            payload = client.get(self._url).json()
        except Exception as error:
            raise AdapterUnavailable(f"SWPC OVATION endpoint unavailable: {error}") from error
        if not isinstance(payload, dict):
            raise AdapterUnavailable("SWPC OVATION returned a non-object payload")
        observation = _parse_time(payload.get("Observation Time"))
        forecast = _parse_time(payload.get("Forecast Time"))
        if observation is None or forecast is None:
            # A nowcast without its own timestamps is not evidence.
            raise AdapterUnavailable("SWPC OVATION payload lacks Observation Time or Forecast Time; refused rather than wall-clock stamped")
        coordinates = payload.get("coordinates")
        if not isinstance(coordinates, list) or not coordinates:
            raise AdapterUnavailable("SWPC OVATION payload carries no coordinates")
        return [
            RunCandidate(
                provider_run_id=f"swpc-ovation-{observation.strftime('%Y%m%d%H%M')}",
                run_time=observation,
                urls=[self._url],
                detail={"payload": payload, "observation": observation, "forecast": forecast},
            )
        ]

    def fetch(self, candidate: RunCandidate, window: FetchWindow, workdir: Path) -> RunResult:
        payload = candidate.detail.get("payload")
        observation: datetime | None = candidate.detail.get("observation")
        forecast: datetime | None = candidate.detail.get("forecast")
        if not isinstance(payload, dict) or observation is None or forecast is None:
            raise AdapterUnavailable("SWPC OVATION fetch carried no payload")
        coordinates = payload.get("coordinates")
        if not isinstance(coordinates, list) or not coordinates:
            raise AdapterUnavailable("SWPC OVATION payload carries no coordinates")

        south, north = self._bounds["south"], self._bounds["north"]
        west, east = self._bounds["west"], self._bounds["east"]
        cells: dict[tuple[float, float], float] = {}
        for entry in coordinates:
            if not isinstance(entry, list) or len(entry) < 3:
                continue
            lon_raw, lat_raw, value = entry[0], entry[1], entry[2]
            try:
                lon = float(lon_raw)
                lat = float(lat_raw)
                probability = float(value)
            except (TypeError, ValueError):
                continue
            if lon > 180.0:
                lon -= 360.0
            if south <= lat <= north and west <= lon <= east:
                cells[(lat, lon)] = probability
        if not cells:
            raise AdapterUnavailable("SWPC OVATION grid carries no cell inside the context box")

        latitudes = numpy.array(sorted({lat for lat, _ in cells}))
        longitudes = numpy.array(sorted({lon for _, lon in cells}))
        grid = numpy.full((1, latitudes.size, longitudes.size), numpy.nan)
        lat_index = {v: i for i, v in enumerate(latitudes)}
        lon_index = {v: i for i, v in enumerate(longitudes)}
        for (lat, lon), probability in cells.items():
            grid[0, lat_index[lat], lon_index[lon]] = probability

        stamps = numpy.array([numpy.datetime64(forecast.replace(tzinfo=None), "ns")])
        dataset = xarray.Dataset(
            {
                "aurora_probability": (
                    ("valid_time", "latitude", "longitude"),
                    grid,
                    {"units": "percent", "original_units": "percent", "long_name": "OVATION probability of visible aurora, as retrieved"},
                )
            },
            coords={"valid_time": stamps, "latitude": latitudes, "longitude": longitudes},
            attrs={
                "source": "SWPC OVATION aurora nowcast",
                "observation_time": observation.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "forecast_time": forecast.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "model_disclosure": "OVATION model output, a nowcast ~30-40 minutes past its observation instant; not an observation",
            },
        )
        finite = float(numpy.isfinite(grid).mean())
        quality = {
            "status": "passed" if finite > 0.5 else "suspect",
            "flags": [] if finite > 0.5 else ["sparse_grid"],
            "detail": f"aurora_probability: {finite:.4f} of context-box cells carry a value; valid at the file's own Forecast Time",
        }
        coverage = {"status": "complete" if finite > 0.5 else "partial", "fraction": round(finite, 4)}

        path = workdir / "swpc_ovation.zarr.zip"
        write_zarr(dataset, path)
        provenance = {
            "source_id": self.source_id,
            "producer": "NOAA Space Weather Prediction Center",
            "product": "OVATION aurora probability nowcast",
            "native_resolution": "1 deg lat x 1 deg lon (as served)",
            "native_crs": "EPSG:4326",
            "adapter_version": self.adapter_version,
            "quality": quality,
            "coverage": coverage,
            **declared_classes(["retrieved"]),
            "observation_time": observation.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "model_disclosure": "OVATION model output; a nowcast, not an observation",
        }
        return RunResult(
            source_id=self.source_id,
            provider_run_id=candidate.provider_run_id,
            run_time=observation,
            retrieved_at=datetime.now(UTC),
            complete=finite > 0.5,
            qc_passed=True,
            artifacts=[Artifact("aurora_grid", MEDIA_ZARR, path, provenance)],
            native_crs="EPSG:4326",
            notes=f"OVATION grid {latitudes.size}x{longitudes.size} cells, forecast instant {forecast.isoformat()}",
        )


KP_ADAPTER = register(SWPCKpAdapter())
RTSW_ADAPTER = register(SWPCSolarWindAdapter())
PLASMA_ADAPTER = register(SWPCPlasmaAdapter())
OVATION_ADAPTER = register(SWPCOvationAdapter())
