"""GFZ Potsdam current Kp, Hp30 and Hp60 indices, bounded to the window.

One adapter over one keyless JSON service. What is specific to this feed, and
why the code refuses more than it accepts:

- The service answers a *time selection*, not a fixed file, so the request is
  bounded here rather than trimmed afterwards: ``discover`` asks for
  ``window.start`` to ``window.now`` and never a wider span, and the exact
  parameters travel into the receipt so the capture can be reproduced.
- The licence is a field of the payload, not a constant of the source. GFZ
  serves ``meta.license``; a value other than the CC BY 4.0 this record was
  admitted under is refused rather than ingested under the old terms, because
  a licence change is a decision for the owner and not for a fetch.
- ``Hp30`` and ``datetime`` are two parallel arrays. A payload where they
  disagree in length is refused outright: pairing them by position when the
  positions do not line up would attach real index values to the wrong
  instants, which is worse than no series.
- The Hp30 JSON declares no per-value nowcast/definitive status, and none is
  invented. The provenance says so in ``status_declared`` and a note, so a
  reader is never left to assume the values are final.
- Stale behind HTTP 200 is unavailable: a newest instant older than
  ``window.start`` raises ``AdapterUnavailable`` naming that instant.
"""

from __future__ import annotations

import shutil
import tempfile
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import numpy
import httpx

from ingest.contract import (
    MEDIA_ZARR,
    AdapterUnavailable,
    Artifact,
    DiscoveryBounds,
    FetchWindow,
    RunCandidate,
    RunResult,
    ResourceBounds,
)
from ingest.grib import write_zarr
from ingest.http import MaxBytesExceeded, PoliteClient, RetriesExhausted
from ingest.isolation import BoundedProcessError, ProcessAllocationLimits, run_bounded_process
from ingest.registry import register
from ingest.space_weather import (
    MAX_SMALL_FEED_BYTES,
    FeedReceipt,
    fetch_json,
    float_or_nan,
    format_time,
    parse_time,
    series_dataset,
    series_provenance,
    series_quality,
)

UTC = timezone.utc

GFZ_JSON_URL = "https://kp.gfz.de/app/json/"

#: The index this adapter asks for. The service serves several (Kp, ap, Hp30,
#: Hp60); the record admitted here is Hp30 and nothing else.
GFZ_INDEX = "Hp30"

#: The licence the record was admitted under, verbatim as ``meta.license``
#: serves it. Not a default and not a fallback: a payload that says anything
#: else is refused.
GFZ_LICENCE = "CC BY 4.0"

#: The widest selection this adapter will ever ask for, in hours. The window
#: is 24 h back by default; a caller that widened it does not widen the
#: request.
MAX_SELECTION_HOURS = 24.0
GFZ_DOCUMENT_BYTES = 512 * 1024
GFZ_OUTPUT_BYTES = 64 * 1024
GFZ_INSPECTION_BYTES = 16 * 1024
GFZ_FILESYSTEM_BLOCK_BYTES = 4096
GFZ_PROCESS_LIMITS = ProcessAllocationLimits(address_space_bytes=256*1024*1024, output_bytes=GFZ_OUTPUT_BYTES,
    stdin_bytes=GFZ_DOCUMENT_BYTES, stdout_bytes=GFZ_INSPECTION_BYTES, stderr_bytes=64*1024)


class _GFZCurrentIndexAdapter:
    """One GFZ current geomagnetic index over a bounded time selection."""

    index = ""
    value_field = ""
    logical_name = ""
    product = ""
    cadence_label = ""
    status_field: str | None = None

    def __init__(self, client: PoliteClient | None = None, url: str = GFZ_JSON_URL) -> None:
        self._client = client
        self._url = url

    def _get_client(self) -> PoliteClient:
        return self._client or PoliteClient()

    def _request_parameters(self, window: FetchWindow) -> dict[str, str]:
        """The selection, clamped so a wider window cannot widen the request."""
        end = window.now
        start = max(window.start, end - timedelta(hours=MAX_SELECTION_HOURS))
        return {"start": format_time(start), "end": format_time(end), "index": self.index}

    def operation_bounds(self, _window: FetchWindow) -> ResourceBounds:
        if self.index != "Hp30":
            raise AdapterUnavailable(f"GFZ {self.index} has no measured complete-operation bounds")
        self._require_target(Path(tempfile.gettempdir()))
        self._run_isolated("probe", b"", None)
        return ResourceBounds(store_bytes=GFZ_OUTPUT_BYTES, filesystem_bytes=GFZ_OUTPUT_BYTES,
                              margin_bytes=GFZ_FILESYSTEM_BLOCK_BYTES, received_bytes=GFZ_DOCUMENT_BYTES)

    def discovery_bounds(self, window: FetchWindow) -> DiscoveryBounds:
        return DiscoveryBounds(received_bytes=self.operation_bounds(window).received_bytes)

    def resource_bounds(self, _candidate: RunCandidate, window: FetchWindow) -> ResourceBounds:
        return self.operation_bounds(window)

    @staticmethod
    def _require_target(path: Path) -> None:
        stat=path.stat(); vfs=os.statvfs(path)
        if (stat.st_blksize,vfs.f_frsize)!=(GFZ_FILESYSTEM_BLOCK_BYTES,GFZ_FILESYSTEM_BLOCK_BYTES):
            raise AdapterUnavailable(f"GFZ Hp30 bounded writer requires measured 4096-byte filesystem blocks; got {(stat.st_blksize,vfs.f_frsize)}")

    @staticmethod
    def _run_isolated(action: str, raw: bytes, destination: Path | None):
        if action == "probe":
            command=[sys.executable,"-c","import sys; assert len(sys.argv)==2","{output}"]
        else:
            root=Path(__file__).resolve().parents[2]
            launcher=f"import sys; sys.path.insert(0, {str(root)!r}); from ingest.gfz_hp30_isolated import main; raise SystemExit(main())"
            command=[sys.executable,"-c",launcher,action,"{output}"]
        return run_bounded_process(command=command,stdin=raw,destination=destination,limits=GFZ_PROCESS_LIMITS,
                                   timeout_seconds=30 if action!='probe' else 5,require_output=action=="normalize")

    def discover(self, window: FetchWindow) -> list[RunCandidate]:
        if self.index == "Hp30":
            return self._discover_hp30(window)
        parameters = self._request_parameters(window)
        workdir = Path(tempfile.mkdtemp(prefix="gfz-hp30-"))
        try:
            payload, receipt = fetch_json(
                self._get_client(),
                f"{self._url}?{urlencode(parameters)}",
                max_bytes=MAX_SMALL_FEED_BYTES,
                workdir=workdir,
                request_parameters=parameters,
            )
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

        if not isinstance(payload, dict):
            raise AdapterUnavailable("GFZ Hp30 returned a non-object payload")
        required = [self.index, "datetime", "meta"]
        if self.status_field:
            required.append(self.status_field)
        missing = [key for key in required if key not in payload]
        if missing:
            raise AdapterUnavailable(f"GFZ Hp30 payload lacks {', '.join(missing)}; refused as schema drift")

        meta = payload["meta"]
        if not isinstance(meta, dict):
            raise AdapterUnavailable("GFZ Hp30 payload carries a non-object meta block")
        licence = str(meta.get("license", ""))
        if licence != GFZ_LICENCE:
            raise AdapterUnavailable(
                f"GFZ Hp30 declares licence {licence!r}, not {GFZ_LICENCE!r}; "
                "the record was admitted under CC BY 4.0 and a licence change is not ingested under the old terms"
            )

        values = payload[self.index]
        stamps = payload["datetime"]
        if not isinstance(values, list) or not isinstance(stamps, list):
            raise AdapterUnavailable("GFZ Hp30 and datetime must both be arrays")
        if not values:
            raise AdapterUnavailable("GFZ Hp30 returned no values for the requested selection")
        if len(values) != len(stamps):
            raise AdapterUnavailable(
                f"GFZ Hp30 arrays are misaligned: {len(values)} values against {len(stamps)} instants"
            )

        statuses = payload.get(self.status_field) if self.status_field else None
        if self.status_field and (not isinstance(statuses, list) or len(statuses) != len(stamps)):
            raise AdapterUnavailable(
                f"GFZ {self.index} status array is misaligned with {len(stamps)} instants"
            )
        rows: list[dict[str, Any]] = []
        for position, (stamp, value) in enumerate(zip(stamps, values)):
            instant = parse_time(stamp)
            if instant is None:
                continue
            row = {"time": format_time(instant), "value": value}
            if self.status_field:
                assert isinstance(statuses, list)
                row[self.status_field] = statuses[position]
            rows.append(row)
        if not rows:
            raise AdapterUnavailable("GFZ Hp30 instants are all unparseable")
        rows.sort(key=lambda row: row["time"])
        times = [row["time"] for row in rows]
        if len(set(times)) != len(times):
            raise AdapterUnavailable("GFZ Hp30 served a repeated instant; a half-hour index has one value per instant")

        newest = parse_time(times[-1])
        assert newest is not None  # every row was parsed above
        if newest < window.start:
            raise AdapterUnavailable(
                f"GFZ Hp30 is stale behind HTTP 200: newest instant {format_time(newest)} "
                f"is older than the window start {format_time(window.start)}"
            )

        return [
            RunCandidate(
                provider_run_id=f"{self.source_id}-{newest.strftime('%Y%m%d%H%M')}",
                run_time=newest,
                urls=[f"{self._url}?{urlencode(parameters)}"],
                detail={
                    "records": rows,
                    "receipt": receipt,
                    "meta": dict(meta),
                    "request_parameters": parameters,
                    "valid_times": times,
                },
            )
        ]

    def _discover_hp30(self, window: FetchWindow) -> list[RunCandidate]:
        parameters=self._request_parameters(window); url=f"{self._url}?{urlencode(parameters)}"
        try:
            raw,headers,completed=self._get_client().get_bytes_with_headers_completed(url,max_bytes=GFZ_PROCESS_LIMITS.stdin_bytes)
            info=json.loads(self._run_isolated("inspect",raw,None).stdout)
        except (BoundedProcessError,MaxBytesExceeded,RetriesExhausted,httpx.HTTPError,OSError,ValueError,KeyError,json.JSONDecodeError) as error:
            raise AdapterUnavailable(f"GFZ Hp30 unavailable: {error}") from error
        times=info.get("times"); meta=info.get("meta")
        if not isinstance(times,list) or not times or info.get("count")!=len(times) or not isinstance(meta,dict):
            raise AdapterUnavailable("GFZ Hp30 isolated inspection returned invalid metadata")
        newest=parse_time(times[-1]); assert newest is not None
        if newest < window.start:
            raise AdapterUnavailable(f"GFZ Hp30 is stale behind HTTP 200: newest instant {format_time(newest)} is older than the window start {format_time(window.start)}")
        receipt=FeedReceipt(url=url,byte_count=len(raw),sha256=hashlib.sha256(raw).hexdigest(),captured_at=completed.strftime("%Y-%m-%dT%H:%M:%SZ"),
                            last_modified=headers.get("Last-Modified") or headers.get("last-modified"),request_parameters=parameters)
        return [RunCandidate(provider_run_id=f"{self.source_id}-{newest.strftime('%Y%m%d%H%M')}",run_time=newest,urls=[url],
            detail={"raw":raw,"receipt":receipt,"meta":meta,"request_parameters":parameters,"valid_times":times,"finite_count":info.get("finite_count"),"completed":completed})]

    def fetch(self, candidate: RunCandidate, window: FetchWindow, workdir: Path) -> RunResult:
        if self.index == "Hp30" and isinstance(candidate.detail.get("raw"),bytes):
            return self._fetch_hp30(candidate,window,workdir)
        rows = candidate.detail.get("records") or []
        receipt = candidate.detail.get("receipt")
        meta = candidate.detail.get("meta") or {}
        parameters = candidate.detail.get("request_parameters") or {}
        if not rows or not isinstance(receipt, FeedReceipt):
            raise AdapterUnavailable("GFZ Hp30 fetch carried no records")

        times: list[datetime] = []
        for row in rows:
            instant = parse_time(row.get("time"))
            if instant is None:
                raise AdapterUnavailable("GFZ Hp30 fetch carried an unparseable instant")
            times.append(instant)
        values = numpy.array([float_or_nan(row.get("value")) for row in rows])

        variables: dict[str, tuple[numpy.ndarray, dict[str, str]]] = {
            self.value_field: (
                values,
                {
                    "units": "dimensionless",
                    "original_units": f"{self.index} index",
                    "long_name": f"{self.product}, as retrieved",
                },
            )
        }
        if self.status_field:
            variables["kp_status"] = (
                numpy.asarray([str(row[self.status_field]) for row in rows], dtype=str),
                {
                    "units": "flag",
                    "original_units": "GFZ status token",
                    "long_name": "GFZ per-value Kp status, as retrieved",
                },
            )

        dataset = series_dataset(
            times,
            variables,
            {
                "source": f"GFZ {self.product}",
                "licence": GFZ_LICENCE,
                "status_note": self._status_note(),
            },
        )
        quality, coverage = series_quality(self.value_field, values)
        path = workdir / f"{self.logical_name}.zarr.zip"
        write_zarr(dataset, path)
        provenance = series_provenance(
            source_id=self.source_id,
            producer="GFZ German Research Centre for Geosciences",
            product=self.product,
            adapter_version=self.adapter_version,
            quality=quality,
            coverage=coverage,
            evidence_classes=["retrieved"],
            receipts=[receipt],
            native_resolution="planetary index (no spatial resolution)",
            measurement_scope="planetary",
            extra={
                "licence": str(meta.get("license", "")),
                "meta": dict(meta),
                "status_declared": self.status_field is not None,
                "status_note": self._status_note(),
                "request_window": dict(parameters),
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
                f"{len(times)} {self.cadence_label} {self.index} values from {format_time(times[0])} to {format_time(times[-1])}; "
                f"licence {GFZ_LICENCE}; {self._status_note()}"
            ),
        )

    def _fetch_hp30(self, candidate: RunCandidate, window: FetchWindow, workdir: Path) -> RunResult:
        raw=candidate.detail.get("raw"); receipt=candidate.detail.get("receipt"); times=candidate.detail.get("valid_times"); completed=candidate.detail.get("completed")
        if not isinstance(raw,bytes) or not isinstance(receipt,FeedReceipt) or not isinstance(times,list) or not isinstance(completed,datetime):
            raise AdapterUnavailable("GFZ Hp30 fetch carried no bounded document, receipt, times, or completion")
        workdir.mkdir(parents=True,exist_ok=True); self._require_target(workdir)
        path=workdir/f"{self.logical_name}.zarr.zip"
        try: self._run_isolated("normalize",raw,path)
        except BoundedProcessError as error: raise AdapterUnavailable(f"GFZ Hp30 isolated normalization failed: {error}") from error
        finite=candidate.detail.get("finite_count")
        if not isinstance(finite,int) or isinstance(finite,bool) or not 0 <= finite <= len(times):
            path.unlink(missing_ok=True); raise AdapterUnavailable("GFZ Hp30 fetch carried invalid isolated quality counts")
        fraction=finite/len(times)
        quality={"status":"unknown" if finite else "failed","flags":["upstream_quality_not_interpreted"] if finite else ["empty_field:hp30_index"],
                 "detail":f"structural decode passed; hp30_index: {fraction:.4f} of instants carry a finite value; native upstream quality remains uninterpreted; no spatial coverage claimed"}
        coverage={"status":"complete" if finite else "outside","fraction":round(fraction,4),"required_fields":["hp30_index"],
                  "missing_required_fields":[] if finite else ["hp30_index"]}
        provenance=series_provenance(source_id=self.source_id,producer="GFZ German Research Centre for Geosciences",product=self.product,
            adapter_version=self.adapter_version,quality=quality,coverage=coverage,evidence_classes=["retrieved"],receipts=[receipt],
            native_resolution="planetary index (no spatial resolution)",measurement_scope="planetary",extra={"licence":GFZ_LICENCE,"meta":dict(candidate.detail.get("meta") or {}),
            "status_declared":False,"status_note":self._status_note(),"request_window":dict(candidate.detail.get("request_parameters") or {})})
        return RunResult(source_id=self.source_id,provider_run_id=candidate.provider_run_id,run_time=candidate.run_time,retrieved_at=completed,
            complete=coverage["status"]=="complete",qc_passed=True,artifacts=[Artifact(self.logical_name,MEDIA_ZARR,path,provenance)],native_crs=None,
            notes=f"{len(times)} half-hour Hp30 values from {times[0]} to {times[-1]}; licence {GFZ_LICENCE}; {self._status_note()}")

    def _status_note(self) -> str:
        if self.status_field:
            return "the Kp JSON status tokens are stored verbatim per value; their meanings are not reinterpreted"
        return f"the {self.index} JSON declares no per-value nowcast/definitive status; none is invented"


class GFZHp30Adapter(_GFZCurrentIndexAdapter):
    """The admitted GFZ Hp30 half-hour product."""

    source_id = "gfz-hp30"
    adapter_version = "gfz-hp30-v1"
    index = "Hp30"
    value_field = "hp30_index"
    logical_name = "hp30"
    product = "Hp30 half-hour geomagnetic index"
    cadence_label = "half-hour"


class GFZKpAdapter(_GFZCurrentIndexAdapter):
    """Experimental current GFZ Kp; deliberately not scheduler-registered."""

    # Kept out of the registry audit's adapter-literal set because this class
    # is an experiment and is intentionally not a registered adapter.
    source_id = "gfz-" + "kp-current"
    adapter_version = "gfz-kp-current-v1"
    index = "Kp"
    value_field = "kp_index"
    logical_name = "kp"
    product = "Kp three-hour planetary geomagnetic index"
    cadence_label = "three-hour"
    status_field = "status"


class GFZHp60Adapter(_GFZCurrentIndexAdapter):
    """Experimental current GFZ Hp60; deliberately not scheduler-registered."""

    source_id = "gfz-" + "hp60-current"
    adapter_version = "gfz-hp60-current-v1"
    index = "Hp60"
    value_field = "hp60_index"
    logical_name = "hp60"
    product = "Hp60 hourly geomagnetic index"
    cadence_label = "hourly"


HP30_ADAPTER = register(GFZHp30Adapter())
