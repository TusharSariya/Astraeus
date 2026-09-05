"""GFZ Potsdam Hp30: the half-hour geomagnetic index, bounded to the window.

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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import numpy

from ingest.contract import (
    MEDIA_ZARR,
    AdapterUnavailable,
    Artifact,
    FetchWindow,
    RunCandidate,
    RunResult,
)
from ingest.grib import write_zarr
from ingest.http import PoliteClient
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


class GFZHp30Adapter:
    """The GFZ Hp30 half-hour geomagnetic index over a bounded time selection."""

    source_id = "gfz-hp30"
    adapter_version = "gfz-hp30-v1"

    def __init__(self, client: PoliteClient | None = None, url: str = GFZ_JSON_URL) -> None:
        self._client = client
        self._url = url

    def _get_client(self) -> PoliteClient:
        return self._client or PoliteClient()

    def _request_parameters(self, window: FetchWindow) -> dict[str, str]:
        """The selection, clamped so a wider window cannot widen the request."""
        end = window.now
        start = max(window.start, end - timedelta(hours=MAX_SELECTION_HOURS))
        return {"start": format_time(start), "end": format_time(end), "index": GFZ_INDEX}

    def discover(self, window: FetchWindow) -> list[RunCandidate]:
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
        missing = [key for key in ("Hp30", "datetime", "meta") if key not in payload]
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

        values = payload["Hp30"]
        stamps = payload["datetime"]
        if not isinstance(values, list) or not isinstance(stamps, list):
            raise AdapterUnavailable("GFZ Hp30 and datetime must both be arrays")
        if not values:
            raise AdapterUnavailable("GFZ Hp30 returned no values for the requested selection")
        if len(values) != len(stamps):
            raise AdapterUnavailable(
                f"GFZ Hp30 arrays are misaligned: {len(values)} values against {len(stamps)} instants"
            )

        rows: list[dict[str, Any]] = []
        for stamp, value in zip(stamps, values):
            instant = parse_time(stamp)
            if instant is None:
                continue
            rows.append({"time": format_time(instant), "hp30": value})
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
                provider_run_id=f"gfz-hp30-{newest.strftime('%Y%m%d%H%M')}",
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

    def fetch(self, candidate: RunCandidate, window: FetchWindow, workdir: Path) -> RunResult:
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
        values = numpy.array([float_or_nan(row.get("hp30")) for row in rows])

        dataset = series_dataset(
            times,
            {
                "hp30_index": (
                    values,
                    {
                        "units": "dimensionless",
                        "original_units": "Hp30 index",
                        "long_name": "Hp30 half-hour geomagnetic index, as retrieved",
                    },
                )
            },
            {
                "source": "GFZ Hp30 half-hour geomagnetic index",
                "licence": GFZ_LICENCE,
                "status_note": "the Hp30 JSON declares no per-value nowcast/definitive status; none is invented",
            },
        )
        quality, coverage = series_quality("hp30_index", values)
        path = workdir / "hp30.zarr.zip"
        write_zarr(dataset, path)
        provenance = series_provenance(
            source_id=self.source_id,
            producer="GFZ German Research Centre for Geosciences",
            product="Hp30 half-hour geomagnetic index",
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
                "status_declared": False,
                "status_note": "the Hp30 JSON declares no per-value nowcast/definitive status; none is invented",
                "request_window": dict(parameters),
            },
        )
        return RunResult(
            source_id=self.source_id,
            provider_run_id=candidate.provider_run_id,
            run_time=candidate.run_time or times[-1],
            retrieved_at=datetime.now(UTC),
            complete=quality["status"] == "passed",
            qc_passed=True,
            artifacts=[Artifact("hp30", MEDIA_ZARR, path, provenance)],
            native_crs=None,
            notes=(
                f"{len(times)} half-hour Hp30 values from {format_time(times[0])} to {format_time(times[-1])}; "
                f"licence {GFZ_LICENCE}; no per-value status declared by the feed"
            ),
        )


HP30_ADAPTER = register(GFZHp30Adapter())
