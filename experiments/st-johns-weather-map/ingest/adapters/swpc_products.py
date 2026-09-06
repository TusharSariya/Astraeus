"""The rest of the free NOAA SWPC space-weather products (issue #89).

Seven coordinate-free series over keyless SWPC JSON endpoints, all built on
the shared seam in ``ingest.space_weather`` so that one reader,
``LiveStore.read_series``, serves every one of them:

- ``noaa-swpc-propagated-solar-wind`` - the L1 solar wind propagated to the
  bow shock. The series is stored on the feed's ``time_tag`` (the L1
  measurement minute) and carries the feed's own ``propagated_time_tag`` as
  an instant, ``propagated_time_unix``. No lag is derived from the pair: the
  difference between the two is the provider's, not ours to restate.
- ``noaa-swpc-kp-1m`` - the 1-minute planetary K index, with the provider's
  own thirds code (``0P``, ``4M``, ...) kept as a flag variable rather than
  re-derived from the number.
- ``noaa-swpc-alerts`` - the issued text products, verbatim including their
  CRLF line endings. This is the one feed with no staleness refusal: an
  alert may legitimately be days old, so provenance records the newest issue
  instant and the feed's ``Last-Modified`` instead of the adapter refusing.
- ``noaa-swpc-scales`` - the NOAA R/S/G scales for yesterday, today and three
  forecast days. The feed serves five day keys that can share one instant,
  so the series is one instant times a ``day_offset`` axis, and each key
  keeps its own ``valid_from_unix``.
- ``noaa-goes-magnetometer`` and ``noaa-goes-xray`` - geosynchronous
  measurements on a ``satellite`` axis, the feed's own satellite numbers as
  labels. The X-ray feed serves two energy rows per minute; the two known
  channels fold into ``_short``/``_long`` variables and an unrecognised
  energy label refuses the run rather than guessing which channel it is.
- ``noaa-swpc-kyoto-dst`` - the Kyoto WDC Dst index relayed by SWPC. It is
  ``reprocessed`` with both the producer of record and the intermediary
  named, and it is never the display primary.

Honesty rules that hold across all seven: every timestamp is the feed's own;
a missing value is NaN, never zero and never carried forward; nothing is
stored that was not retrieved; the retrieval receipt goes into provenance and
the payload never does.
"""

from __future__ import annotations

import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

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
    MAX_LARGE_FEED_BYTES,
    MAX_SMALL_FEED_BYTES,
    FeedReceipt,
    fetch_json,
    flag_attrs,
    flag_or_nan,
    float_or_nan,
    format_time,
    parse_time,
    platform_series_dataset,
    records,
    series_dataset,
    series_provenance,
    series_quality,
)

UTC = timezone.utc

SWPC_BASE = "https://services.swpc.noaa.gov"
PROPAGATED_URL = f"{SWPC_BASE}/products/geospace/propagated-solar-wind-1-hour.json"
KP_1M_URL = f"{SWPC_BASE}/json/planetary_k_index_1m.json"
ALERTS_URL = f"{SWPC_BASE}/products/alerts.json"
SCALES_URL = f"{SWPC_BASE}/products/noaa-scales.json"
GOES_MAGNETOMETER_URL = f"{SWPC_BASE}/json/goes/primary/magnetometers-1-day.json"
GOES_XRAY_URL = f"{SWPC_BASE}/json/goes/primary/xrays-1-day.json"
KYOTO_DST_URL = f"{SWPC_BASE}/products/kyoto-dst.json"

SWPC_PRODUCER = "NOAA Space Weather Prediction Center"
KYOTO_PRODUCER = "Kyoto World Data Center for Geomagnetism"

#: The SWPC thirds codes for Kp, in ascending order. The feed serves the code
#: (``0P`` = 0+, ``4M`` = 4-, ``4Z`` = 4o) beside the number; keeping it as a
#: flag preserves the provider's own quantisation instead of re-deriving it.
KP_CODES = (
    "0Z", "0P", "1M", "1Z", "1P", "2M", "2Z", "2P", "3M", "3Z", "3P",
    "4M", "4Z", "4P", "5M", "5Z", "5P", "6M", "6Z", "6P", "7M", "7Z",
    "7P", "8M", "8Z", "8P", "9M", "9Z",
)
_KP_CODE_INDEX = {code: index for index, code in enumerate(KP_CODES)}

#: The GOES X-ray energy bands, as the feed spells them, and the suffix each
#: one folds into. An energy outside this map is schema drift, not a third
#: channel to invent a name for.
XRAY_CHANNELS = {"0.05-0.4nm": "short", "0.1-0.8nm": "long"}

#: The scale keys the product serves and what each one means. "-1" is
#: yesterday's observed maximum, "0" the current period, "1".."3" the
#: forecast days.
SCALE_KEYS = ("-1", "0", "1", "2", "3")
SCALE_KIND_MEANINGS = ("observed", "current", "forecast")
_SCALE_KIND = {"-1": 0.0, "0": 1.0, "1": 2.0, "2": 2.0, "3": 2.0}
SCALE_TEXT_TABLE = "0 none 1 minor 2 moderate 3 strong 4 severe 5 extreme"

_MESSAGE_CODE_LINE = re.compile(r"^Space Weather Message Code:\s*(.*)$", re.MULTILINE)
_SERIAL_LINE = re.compile(r"^Serial Number:\s*(.*)$", re.MULTILINE)
_NOAA_SCALE_LINE = re.compile(r"^NOAA Scale:\s*(.*)$", re.MULTILINE)

EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
UNIX_UNITS = "s since 1970-01-01T00:00:00Z"


def _retrieve(client: PoliteClient | None, url: str, max_bytes: int) -> tuple[Any, FeedReceipt]:
    """One bounded, receipted JSON retrieval into a scratch directory.

    The scratch directory is the only place provider bytes ever land, and it
    is removed before this returns whether or not the parse succeeded.
    """
    workdir = Path(tempfile.mkdtemp(prefix="space-weather-"))
    try:
        return fetch_json(client or PoliteClient(), url, max_bytes=max_bytes, workdir=workdir)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _refuse_if_stale(newest: datetime, window: FetchWindow, source: str) -> None:
    """Stale behind an HTTP 200 is unavailable, not evidence."""
    if newest < window.start:
        raise AdapterUnavailable(
            f"{source} is stale: newest instant {format_time(newest)} is older than the window start {format_time(window.start)}"
        )


def _timed_rows(rows: Iterable[Mapping[str, Any]], key: str) -> list[tuple[datetime, Mapping[str, Any]]]:
    """Records paired with their own parsed instant, in time order."""
    paired = [(parse_time(row.get(key)), row) for row in rows]
    return sorted(((stamp, row) for stamp, row in paired if stamp is not None), key=lambda item: item[0])


def _unix(stamp: datetime) -> float:
    return (stamp - EPOCH).total_seconds()


def _grid(times: Sequence[datetime], labels: Sequence[str]) -> numpy.ndarray:
    return numpy.full((len(times), len(labels)), numpy.nan)


def _quantity(long_name: str, units: str, original: str | None = None) -> dict[str, Any]:
    return {"units": units, "original_units": original or units, "long_name": long_name}


def _candidate(prefix: str, newest: datetime, url: str, detail: dict[str, Any], times: Sequence[datetime]) -> RunCandidate:
    return RunCandidate(
        provider_run_id=f"{prefix}-{newest.strftime('%Y%m%d%H%M')}",
        run_time=newest,
        urls=[url],
        detail={**detail, "valid_times": [format_time(stamp) for stamp in times]},
    )


def _receipt_of(candidate: RunCandidate, source: str) -> FeedReceipt:
    receipt = candidate.detail.get("receipt")
    if not isinstance(receipt, FeedReceipt):
        raise AdapterUnavailable(f"{source} fetch carried no retrieval receipt")
    return receipt


class SWPCPropagatedSolarWindAdapter:
    """L1 solar wind propagated to the bow shock, 1-minute, one hour deep."""

    source_id = "noaa-swpc-propagated-solar-wind"
    adapter_version = "swpc-propagated-v1"

    _REQUIRED = ("time_tag", "propagated_time_tag", "speed", "density", "bz")

    def __init__(self, client: PoliteClient | None = None, url: str = PROPAGATED_URL) -> None:
        self._client = client
        self._url = url

    def discover(self, window: FetchWindow) -> list[RunCandidate]:
        payload, receipt = _retrieve(self._client, self._url, MAX_SMALL_FEED_BYTES)
        rows = records(payload, required=self._REQUIRED)
        if not rows:
            raise AdapterUnavailable("SWPC propagated solar wind returned no usable records")
        timed = _timed_rows(rows, "time_tag")
        if not timed:
            raise AdapterUnavailable("SWPC propagated solar wind records carry no parseable time_tag")
        times = [stamp for stamp, _ in timed]
        _refuse_if_stale(times[-1], window, "SWPC propagated solar wind")
        return [_candidate("swpc-propagated", times[-1], self._url, {"records": [row for _, row in timed], "receipt": receipt}, times)]

    def fetch(self, candidate: RunCandidate, window: FetchWindow, workdir: Path) -> RunResult:
        receipt = _receipt_of(candidate, "SWPC propagated solar wind")
        timed = _timed_rows(candidate.detail.get("records") or [], "time_tag")
        if not timed:
            raise AdapterUnavailable("SWPC propagated solar wind fetch carried no records")
        times = [stamp for stamp, _ in timed]
        rows = [row for _, row in timed]

        def column(key: str) -> numpy.ndarray:
            return numpy.array([float_or_nan(row.get(key)) for row in rows])

        arrival = numpy.array([
            _unix(stamp) if (stamp := parse_time(row.get("propagated_time_tag"))) is not None else numpy.nan
            for row in rows
        ])
        speed = column("speed")
        variables = {
            "speed": (speed, _quantity("solar wind bulk speed as propagated, as retrieved", "km s-1")),
            "vx": (column("vx"), _quantity("propagated solar wind velocity x component, as retrieved", "km s-1")),
            "vy": (column("vy"), _quantity("propagated solar wind velocity y component, as retrieved", "km s-1")),
            "vz": (column("vz"), _quantity("propagated solar wind velocity z component, as retrieved", "km s-1")),
            "density": (column("density"), _quantity("propagated solar wind proton density, as retrieved", "cm-3")),
            "temperature": (column("temperature"), _quantity("propagated solar wind temperature, as retrieved", "K")),
            "bx": (column("bx"), _quantity("propagated interplanetary field x component, as retrieved", "nT")),
            "by": (column("by"), _quantity("propagated interplanetary field y component, as retrieved", "nT")),
            "bz": (column("bz"), _quantity("propagated interplanetary field z component, as retrieved", "nT")),
            "bt": (column("bt"), _quantity("propagated interplanetary field magnitude, as retrieved", "nT")),
            "propagated_time_unix": (
                arrival,
                {
                    "units": UNIX_UNITS,
                    "original_units": "ISO 8601 instant",
                    "long_name": "the feed's propagated_time_tag: the bow-shock arrival instant, stored verbatim; no lag is derived",
                },
            ),
        }
        dataset = series_dataset(
            times,
            variables,
            {
                "source": "SWPC propagated solar wind (1 hour)",
                "valid_time_meaning": "the feed's time_tag, the L1 measurement minute",
                "model_disclosure": "propagated model values, not a measurement at the bow shock",
            },
        )
        quality, coverage = series_quality("speed", speed, required_fields={key: variables[key][0] for key in ("speed", "density", "bz", "bt")})
        path = workdir / "propagated_solar_wind.zarr.zip"
        write_zarr(dataset, path)
        provenance = series_provenance(
            source_id=self.source_id,
            producer=SWPC_PRODUCER,
            product="Propagated solar wind (1 hour)",
            adapter_version=self.adapter_version,
            quality=quality,
            coverage=coverage,
            evidence_classes=["retrieved"],
            receipts=[receipt],
            native_resolution="1 minute (no spatial resolution)",
            measurement_scope="propagated",
            extra={"status_declared": False, "newest_instant": format_time(times[-1])},
        )
        return RunResult(
            source_id=self.source_id,
            provider_run_id=candidate.provider_run_id,
            run_time=candidate.run_time or times[-1],
            retrieved_at=datetime.now(UTC),
            complete=coverage["status"] == "complete",
            qc_passed=True,
            artifacts=[Artifact("propagated_solar_wind", MEDIA_ZARR, path, provenance)],
            native_crs=None,
            notes=f"{len(times)} propagated solar wind minutes, newest {format_time(times[-1])}",
        )


class SWPCKp1mAdapter:
    """The 1-minute planetary K index, with the provider's own thirds code."""

    source_id = "noaa-swpc-kp-1m"
    adapter_version = "swpc-kp1m-v1"

    _REQUIRED = ("time_tag", "kp_index", "estimated_kp", "kp")

    def __init__(self, client: PoliteClient | None = None, url: str = KP_1M_URL) -> None:
        self._client = client
        self._url = url

    def discover(self, window: FetchWindow) -> list[RunCandidate]:
        payload, receipt = _retrieve(self._client, self._url, MAX_SMALL_FEED_BYTES)
        rows = records(payload, required=self._REQUIRED)
        raw_count = len(payload) if isinstance(payload, list) else 0
        header_rows = 1 if payload and isinstance(payload[0], list) else 0
        if len(rows) != raw_count - header_rows:
            raise AdapterUnavailable("SWPC 1-minute Kp contains a malformed or incomplete row; refused without thinning")
        if not rows:
            raise AdapterUnavailable("SWPC 1-minute Kp returned no usable records")
        for index, row in enumerate(rows):
            if parse_time(row.get("time_tag")) is None:
                raise AdapterUnavailable(f"SWPC 1-minute Kp row {index} has an unparseable time_tag")
            for field in ("kp_index", "estimated_kp"):
                value = row.get(field)
                if value is None or isinstance(value, bool):
                    raise AdapterUnavailable(f"SWPC 1-minute Kp row {index} has invalid {field}")
                try:
                    float(value)
                except (TypeError, ValueError) as error:
                    raise AdapterUnavailable(f"SWPC 1-minute Kp row {index} has invalid {field}") from error
            if str(row.get("kp", "")).strip() not in _KP_CODE_INDEX:
                raise AdapterUnavailable(f"SWPC 1-minute Kp row {index} has an unsupported kp code")
        timed = _timed_rows(rows, "time_tag")
        if not timed:
            raise AdapterUnavailable("SWPC 1-minute Kp records carry no parseable time_tag")
        times = [stamp for stamp, _ in timed]
        _refuse_if_stale(times[-1], window, "SWPC 1-minute Kp")
        return [_candidate("swpc-kp1m", times[-1], self._url, {"records": [row for _, row in timed], "receipt": receipt}, times)]

    def fetch(self, candidate: RunCandidate, window: FetchWindow, workdir: Path) -> RunResult:
        receipt = _receipt_of(candidate, "SWPC 1-minute Kp")
        timed = _timed_rows(candidate.detail.get("records") or [], "time_tag")
        if not timed:
            raise AdapterUnavailable("SWPC 1-minute Kp fetch carried no records")
        times = [stamp for stamp, _ in timed]
        rows = [row for _, row in timed]

        kp_index = numpy.array([float_or_nan(row.get("kp_index")) for row in rows])
        estimated = numpy.array([float_or_nan(row.get("estimated_kp")) for row in rows])
        codes = numpy.array([
            float(_KP_CODE_INDEX[text]) if (text := str(row.get("kp", "")).strip()) in _KP_CODE_INDEX else numpy.nan
            for row in rows
        ])
        unknown = int(numpy.count_nonzero(numpy.isnan(codes)))

        dataset = series_dataset(
            times,
            {
                "kp_index": (kp_index, _quantity("planetary K index, 1-minute, as retrieved", "dimensionless", "Kp index")),
                "estimated_kp": (estimated, _quantity("estimated planetary K index, as retrieved", "dimensionless", "Kp index")),
                "kp_code": (codes, flag_attrs(list(KP_CODES), long_name="the provider's own Kp thirds code, as retrieved")),
            },
            {"source": "SWPC 1-minute planetary K index"},
        )
        quality, coverage = series_quality("kp_index", kp_index, required_fields={"kp_index": kp_index, "estimated_kp": estimated})
        path = workdir / "kp_1m.zarr.zip"
        write_zarr(dataset, path)
        provenance = series_provenance(
            source_id=self.source_id,
            producer=SWPC_PRODUCER,
            product="Planetary K index (1 minute)",
            adapter_version=self.adapter_version,
            quality=quality,
            coverage=coverage,
            evidence_classes=["retrieved"],
            receipts=[receipt],
            native_resolution="1 minute (planetary index, no spatial resolution)",
            measurement_scope="planetary",
            extra={"status_declared": False, "kp_codes_outside_the_table": unknown},
        )
        return RunResult(
            source_id=self.source_id,
            provider_run_id=candidate.provider_run_id,
            run_time=candidate.run_time or times[-1],
            retrieved_at=datetime.now(UTC),
            complete=coverage["status"] == "complete",
            qc_passed=True,
            artifacts=[Artifact("kp_1m", MEDIA_ZARR, path, provenance)],
            native_crs=None,
            notes=f"{len(times)} Kp minutes, {unknown} code(s) outside the SWPC thirds table, newest {format_time(times[-1])}",
        )


def _header_field(pattern: re.Pattern[str], message: str, *, last: bool = False) -> str:
    """One labelled header line out of an alert message, verbatim.

    The alert body is the product; these are the few lines SWPC states in a
    fixed form. Absent means empty, never a value borrowed from another
    message.
    """
    found = pattern.findall(message)
    if not found:
        return ""
    return str(found[-1] if last else found[0]).strip()


class SWPCAlertsAdapter:
    """The issued SWPC alert, watch and warning texts, verbatim.

    This is the one space-weather feed with no staleness refusal. A quiet Sun
    means the newest alert can be genuinely days old, and refusing it would
    turn a true "nothing has been issued lately" into an outage. Instead the
    provenance states the newest issue instant and the feed's own
    ``Last-Modified`` so a reader can judge the age itself.
    """

    source_id = "noaa-swpc-alerts"
    adapter_version = "swpc-alerts-v1"

    _REQUIRED = ("product_id", "issue_datetime", "message")

    def __init__(self, client: PoliteClient | None = None, url: str = ALERTS_URL) -> None:
        self._client = client
        self._url = url

    def _parsed(self, payload: Any) -> list[tuple[datetime, dict[str, Any]]]:
        rows = records(payload, required=self._REQUIRED)
        if not rows:
            raise AdapterUnavailable("SWPC alerts returned no usable records")
        timed = _timed_rows(rows, "issue_datetime")
        if not timed:
            raise AdapterUnavailable("SWPC alerts records carry no parseable issue_datetime")

        # Exact duplicates are one message served twice; two different
        # messages at one instant are a collision this series cannot store
        # honestly, because valid_time is the issue instant.
        keep: list[tuple[datetime, dict[str, Any]]] = []
        seen: dict[datetime, tuple[str, str]] = {}
        for stamp, row in timed:
            identity = (str(row.get("product_id", "")), str(row.get("message", "")))
            if stamp in seen:
                if seen[stamp] == identity:
                    continue
                raise AdapterUnavailable(
                    f"SWPC alerts served two distinct messages at {format_time(stamp)}; the issue instant cannot identify a row"
                )
            seen[stamp] = identity
            keep.append((stamp, dict(row)))
        return keep

    def discover(self, window: FetchWindow) -> list[RunCandidate]:
        payload, receipt = _retrieve(self._client, self._url, MAX_SMALL_FEED_BYTES)
        parsed = self._parsed(payload)
        times = [stamp for stamp, _ in parsed]
        return [_candidate("swpc-alerts", times[-1], self._url, {"records": [row for _, row in parsed], "receipt": receipt}, times)]

    def fetch(self, candidate: RunCandidate, window: FetchWindow, workdir: Path) -> RunResult:
        receipt = _receipt_of(candidate, "SWPC alerts")
        parsed = self._parsed(candidate.detail.get("records") or [])
        times = [stamp for stamp, _ in parsed]
        rows = [row for _, row in parsed]

        messages = [str(row.get("message", "")) for row in rows]
        product_ids = numpy.array([str(row.get("product_id", "")) for row in rows], dtype=object)
        message_values = numpy.array(messages, dtype=object)
        message_codes = numpy.array([_header_field(_MESSAGE_CODE_LINE, text) for text in messages], dtype=object)
        scales = numpy.array([_header_field(_NOAA_SCALE_LINE, text, last=True) for text in messages], dtype=object)
        serials = numpy.array([float_or_nan(_header_field(_SERIAL_LINE, text) or None) for text in messages])
        present = numpy.array([1.0 if text else numpy.nan for text in messages])

        dataset = series_dataset(
            times,
            {
                "product_id": (product_ids, {"units": "text", "original_units": "provider product id", "long_name": "SWPC product identifier, as retrieved"}),
                "message": (message_values, {"units": "text", "original_units": "provider message body", "long_name": "the issued message verbatim, line endings included"}),
                "message_code": (message_codes, {"units": "text", "original_units": "provider message code", "long_name": "the message's own Space Weather Message Code line, empty when absent"}),
                "serial_number": (serials, _quantity("the message's own Serial Number line, NaN when absent", "dimensionless", "provider serial number")),
                "noaa_scale": (scales, {"units": "text", "original_units": "provider NOAA Scale line", "long_name": "the last NOAA Scale line of the message, empty when absent"}),
            },
            {
                "source": "SWPC issued alerts, watches and warnings",
                "valid_time_meaning": "the message's own issue_datetime",
                "staleness_policy": "not refused on age: an issued alert may legitimately be days old",
            },
        )
        quality, coverage = series_quality("message", present, note="issued text products; no spatial coverage claimed")
        path = workdir / "alerts.zarr.zip"
        write_zarr(dataset, path)
        provenance = series_provenance(
            source_id=self.source_id,
            producer=SWPC_PRODUCER,
            product="Space weather alerts, watches and warnings",
            adapter_version=self.adapter_version,
            quality=quality,
            coverage=coverage,
            evidence_classes=["retrieved"],
            receipts=[receipt],
            native_resolution="issuance dependent (no spatial resolution)",
            measurement_scope="issued",
            extra={
                "status_declared": False,
                "newest_issue_instant": format_time(times[-1]),
                "feed_last_modified": receipt.last_modified,
            },
        )
        return RunResult(
            source_id=self.source_id,
            provider_run_id=candidate.provider_run_id,
            run_time=candidate.run_time or times[-1],
            retrieved_at=datetime.now(UTC),
            complete=coverage["status"] == "complete",
            qc_passed=True,
            artifacts=[Artifact("alerts", MEDIA_ZARR, path, provenance)],
            native_crs=None,
            notes=f"{len(times)} issued messages, newest issue instant {format_time(times[-1])}",
        )


class SWPCScalesAdapter:
    """The NOAA R/S/G scales for yesterday, today and three forecast days.

    The product is an object keyed ``-1`` through ``3``, and two of those
    keys routinely carry the same DateStamp/TimeStamp, so day offset is a
    platform axis rather than a second time coordinate. The series' single
    instant is the current period's (key ``0``); every key keeps its own
    stamp as ``valid_from_unix``.
    """

    source_id = "noaa-swpc-scales"
    adapter_version = "swpc-scales-v1"

    def __init__(self, client: PoliteClient | None = None, url: str = SCALES_URL) -> None:
        self._client = client
        self._url = url

    def _parsed(self, payload: Any) -> dict[str, dict[str, Any]]:
        if not isinstance(payload, dict):
            raise AdapterUnavailable("SWPC NOAA scales did not serve an object keyed by day offset")
        blocks: dict[str, dict[str, Any]] = {}
        for key in SCALE_KEYS:
            block = payload.get(key)
            if not isinstance(block, dict):
                raise AdapterUnavailable(f"SWPC NOAA scales is missing the day offset {key!r}")
            if parse_time(f"{block.get('DateStamp')} {block.get('TimeStamp')}") is None:
                raise AdapterUnavailable(f"SWPC NOAA scales day offset {key!r} carries no parseable DateStamp/TimeStamp")
            blocks[key] = block
        return blocks

    def discover(self, window: FetchWindow) -> list[RunCandidate]:
        payload, receipt = _retrieve(self._client, self._url, MAX_SMALL_FEED_BYTES)
        blocks = self._parsed(payload)
        current = parse_time(f"{blocks['0'].get('DateStamp')} {blocks['0'].get('TimeStamp')}")
        assert current is not None  # _parsed refused anything unparseable
        _refuse_if_stale(current, window, "SWPC NOAA scales")
        return [_candidate("swpc-scales", current, self._url, {"payload": blocks, "receipt": receipt}, [current])]

    def fetch(self, candidate: RunCandidate, window: FetchWindow, workdir: Path) -> RunResult:
        receipt = _receipt_of(candidate, "SWPC NOAA scales")
        blocks = self._parsed(candidate.detail.get("payload"))
        current = parse_time(f"{blocks['0'].get('DateStamp')} {blocks['0'].get('TimeStamp')}")
        assert current is not None
        times = [current]
        labels = list(SCALE_KEYS)

        def cell(reader) -> numpy.ndarray:
            grid = _grid(times, labels)
            for index, key in enumerate(labels):
                grid[0, index] = reader(blocks[key])
            return grid

        def scale(letter: str) -> numpy.ndarray:
            return cell(lambda block: float_or_nan((block.get(letter) or {}).get("Scale")))

        def probability(letter: str, field: str) -> numpy.ndarray:
            return cell(lambda block: float_or_nan((block.get(letter) or {}).get(field)))

        g_scale = scale("G")
        stamps = cell(lambda block: _unix(parse_time(f"{block.get('DateStamp')} {block.get('TimeStamp')}")))
        kinds = _grid(times, labels)
        for index, key in enumerate(labels):
            kinds[0, index] = _SCALE_KIND[key]

        dataset = platform_series_dataset(
            times,
            labels,
            {
                "r_scale": (scale("R"), _quantity("NOAA R (radio blackout) scale, as retrieved", "dimensionless", "NOAA scale 0-5")),
                "s_scale": (scale("S"), _quantity("NOAA S (solar radiation storm) scale, as retrieved", "dimensionless", "NOAA scale 0-5")),
                "g_scale": (g_scale, _quantity("NOAA G (geomagnetic storm) scale, as retrieved", "dimensionless", "NOAA scale 0-5")),
                "r_minor_probability": (probability("R", "MinorProb"), _quantity("provider probability of a minor radio blackout", "percent")),
                "r_major_probability": (probability("R", "MajorProb"), _quantity("provider probability of a major radio blackout", "percent")),
                "s_probability": (probability("S", "Prob"), _quantity("provider probability of a solar radiation storm", "percent")),
                "valid_from_unix": (
                    stamps,
                    {
                        "units": UNIX_UNITS,
                        "original_units": "provider DateStamp and TimeStamp",
                        "long_name": "each day offset's own DateStamp/TimeStamp, stored verbatim as an instant",
                    },
                ),
                "scale_kind": (kinds, flag_attrs(list(SCALE_KIND_MEANINGS), long_name="what the day offset states: yesterday observed, the current period, or a forecast day")),
            },
            {
                "source": "SWPC NOAA space weather scales",
                "valid_time_meaning": "the current period's DateStamp/TimeStamp (day offset 0)",
                "scale_text_table": SCALE_TEXT_TABLE,
            },
            platform_dim="day_offset",
        )
        quality, coverage = series_quality("g_scale", g_scale, required_fields={"r_scale": scale("R"), "s_scale": scale("S"), "g_scale": g_scale})
        path = workdir / "noaa_scales.zarr.zip"
        write_zarr(dataset, path)
        provenance = series_provenance(
            source_id=self.source_id,
            producer=SWPC_PRODUCER,
            product="NOAA space weather scales (R, S, G)",
            adapter_version=self.adapter_version,
            quality=quality,
            coverage=coverage,
            evidence_classes=["retrieved"],
            receipts=[receipt],
            native_resolution="one current period plus four day offsets (no spatial resolution)",
            measurement_scope="planetary",
            extra={"status_declared": False, "scale_text_table": SCALE_TEXT_TABLE},
        )
        return RunResult(
            source_id=self.source_id,
            provider_run_id=candidate.provider_run_id,
            run_time=candidate.run_time or current,
            retrieved_at=datetime.now(UTC),
            complete=coverage["status"] == "complete",
            qc_passed=True,
            artifacts=[Artifact("noaa_scales", MEDIA_ZARR, path, provenance)],
            native_crs=None,
            notes=f"NOAA scales at {format_time(current)} across day offsets {' '.join(labels)}",
        )


class _GOESAdapter:
    """Shared discovery for the two geosynchronous GOES products.

    Both feeds interleave satellites at the same minute and both are read
    under the large ceiling, so only parsing and dataset construction differ.
    """

    source_id = ""
    adapter_version = ""
    _REQUIRED: tuple[str, ...] = ()
    _PREFIX = ""
    _LABEL = ""

    def __init__(self, client: PoliteClient | None = None, url: str = "") -> None:
        self._client = client
        self._url = url

    def _timed(self, rows: Sequence[Mapping[str, Any]]) -> list[tuple[datetime, Mapping[str, Any]]]:
        timed = _timed_rows(rows, "time_tag")
        if not timed:
            raise AdapterUnavailable(f"{self._LABEL} records carry no parseable time_tag")
        return timed

    def discover(self, window: FetchWindow) -> list[RunCandidate]:
        payload, receipt = _retrieve(self._client, self._url, MAX_LARGE_FEED_BYTES)
        rows = records(payload, required=self._REQUIRED)
        if not rows:
            raise AdapterUnavailable(f"{self._LABEL} returned no usable records")
        timed = self._timed(rows)
        self._check(timed)
        times = sorted({stamp for stamp, _ in timed})
        _refuse_if_stale(times[-1], window, self._LABEL)
        return [_candidate(self._PREFIX, times[-1], self._url, {"records": [row for _, row in timed], "receipt": receipt}, times)]

    def _check(self, timed: Sequence[tuple[datetime, Mapping[str, Any]]]) -> None:
        """Refuse anything the dataset builder could not store honestly."""

    def _axes(self, timed: Sequence[tuple[datetime, Mapping[str, Any]]]) -> tuple[list[datetime], list[str], dict[datetime, int], dict[str, int]]:
        times = sorted({stamp for stamp, _ in timed})
        labels = sorted({str(row.get("satellite")) for _, row in timed})
        return times, labels, {stamp: i for i, stamp in enumerate(times)}, {label: i for i, label in enumerate(labels)}


class GOESMagnetometerAdapter(_GOESAdapter):
    """The GOES primary magnetometer, 1-minute over a rolling day."""

    source_id = "noaa-goes-magnetometer"
    adapter_version = "goes-magnetometer-v1"
    _REQUIRED = ("time_tag", "satellite", "He", "Hp", "Hn", "total")
    _PREFIX = "goes-magnetometer"
    _LABEL = "GOES magnetometer"

    def __init__(self, client: PoliteClient | None = None, url: str = GOES_MAGNETOMETER_URL) -> None:
        super().__init__(client, url)

    def fetch(self, candidate: RunCandidate, window: FetchWindow, workdir: Path) -> RunResult:
        receipt = _receipt_of(candidate, self._LABEL)
        timed = self._timed(candidate.detail.get("records") or [])
        times, labels, time_index, label_index = self._axes(timed)

        fields = {"he": "He", "hp": "Hp", "hn": "Hn", "total": "total"}
        grids = {name: _grid(times, labels) for name in fields}
        arcjet = _grid(times, labels)
        for stamp, row in timed:
            r, c = time_index[stamp], label_index[str(row.get("satellite"))]
            for name, key in fields.items():
                grids[name][r, c] = float_or_nan(row.get(key))
            arcjet[r, c] = flag_or_nan(row.get("arcjet_flag"))

        dataset = platform_series_dataset(
            times,
            labels,
            {
                "he": (grids["he"], _quantity("GOES magnetometer eastward component, as retrieved", "nT")),
                "hp": (grids["hp"], _quantity("GOES magnetometer northward (parallel to spin axis) component, as retrieved", "nT")),
                "hn": (grids["hn"], _quantity("GOES magnetometer normal component, as retrieved", "nT")),
                "total": (grids["total"], _quantity("GOES magnetometer total field, as retrieved", "nT")),
                "arcjet_flag": (arcjet, flag_attrs(["false", "true"], long_name="the feed's own arcjet contamination flag")),
            },
            {"source": "SWPC GOES primary magnetometer (1 day)"},
            platform_dim="satellite",
        )
        quality, coverage = series_quality("total", grids["total"], required_fields=grids)
        path = workdir / "goes_magnetometer.zarr.zip"
        write_zarr(dataset, path)
        provenance = series_provenance(
            source_id=self.source_id,
            producer=SWPC_PRODUCER,
            product="GOES magnetometer (1 day)",
            adapter_version=self.adapter_version,
            quality=quality,
            coverage=coverage,
            evidence_classes=["retrieved"],
            receipts=[receipt],
            native_resolution="1 minute (geosynchronous point measurement)",
            measurement_scope="geosynchronous",
            extra={"status_declared": False, "satellites": labels},
        )
        return RunResult(
            source_id=self.source_id,
            provider_run_id=candidate.provider_run_id,
            run_time=candidate.run_time or times[-1],
            retrieved_at=datetime.now(UTC),
            complete=coverage["status"] == "complete",
            qc_passed=True,
            artifacts=[Artifact("goes_magnetometer", MEDIA_ZARR, path, provenance)],
            native_crs=None,
            notes=f"{len(times)} minutes across satellites {' '.join(labels)}, newest {format_time(times[-1])}",
        )


class GOESXrayAdapter(_GOESAdapter):
    """The GOES X-ray flux, both energy channels, over a rolling day."""

    source_id = "noaa-goes-xray"
    adapter_version = "goes-xray-v1"
    _REQUIRED = ("time_tag", "satellite", "energy", "flux")
    _PREFIX = "goes-xray"
    _LABEL = "GOES X-ray flux"

    def __init__(self, client: PoliteClient | None = None, url: str = GOES_XRAY_URL) -> None:
        super().__init__(client, url)

    def _check(self, timed: Sequence[tuple[datetime, Mapping[str, Any]]]) -> None:
        unknown = sorted({str(row.get("energy")) for _, row in timed} - set(XRAY_CHANNELS))
        if unknown:
            raise AdapterUnavailable(
                f"GOES X-ray flux served an unrecognised energy band {unknown!r}; the channel map covers {sorted(XRAY_CHANNELS)}"
            )

    def fetch(self, candidate: RunCandidate, window: FetchWindow, workdir: Path) -> RunResult:
        receipt = _receipt_of(candidate, self._LABEL)
        timed = self._timed(candidate.detail.get("records") or [])
        self._check(timed)
        times, labels, time_index, label_index = self._axes(timed)

        # The feed spells the contamination flag `electron_contaminaton`; the
        # stored name is the correct spelling and the feed's key is read as
        # served.
        fields = {"xray_flux": "flux", "observed_flux": "observed_flux", "electron_correction": "electron_correction"}
        grids = {f"{name}_{suffix}": _grid(times, labels) for name in fields for suffix in XRAY_CHANNELS.values()}
        for suffix in XRAY_CHANNELS.values():
            grids[f"electron_contamination_{suffix}"] = _grid(times, labels)
        for stamp, row in timed:
            suffix = XRAY_CHANNELS[str(row.get("energy"))]
            r, c = time_index[stamp], label_index[str(row.get("satellite"))]
            for name, key in fields.items():
                grids[f"{name}_{suffix}"][r, c] = float_or_nan(row.get(key))
            grids[f"electron_contamination_{suffix}"][r, c] = flag_or_nan(row.get("electron_contaminaton"))

        variables: dict[str, tuple[numpy.ndarray, Mapping[str, Any]]] = {}
        for suffix, band in (("short", "0.05-0.4 nm"), ("long", "0.1-0.8 nm")):
            variables[f"xray_flux_{suffix}"] = (grids[f"xray_flux_{suffix}"], _quantity(f"GOES X-ray flux, {band} channel, as retrieved", "W m-2"))
            variables[f"observed_flux_{suffix}"] = (grids[f"observed_flux_{suffix}"], _quantity(f"GOES observed X-ray flux before correction, {band} channel, as retrieved", "W m-2"))
            variables[f"electron_correction_{suffix}"] = (grids[f"electron_correction_{suffix}"], _quantity(f"the feed's own electron correction, {band} channel, as retrieved", "W m-2"))
            variables[f"electron_contamination_{suffix}"] = (
                grids[f"electron_contamination_{suffix}"],
                flag_attrs(["false", "true"], long_name=f"the feed's own electron contamination flag ({band}); the feed spells the key electron_contaminaton"),
            )

        dataset = platform_series_dataset(
            times, labels, variables,
            {"source": "SWPC GOES X-ray flux (1 day)", "channel_map": "0.05-0.4nm short; 0.1-0.8nm long"},
            platform_dim="satellite",
        )
        quality, coverage = series_quality("xray_flux_long", grids["xray_flux_long"], required_fields={key: grids[key] for key in ("xray_flux_short", "xray_flux_long")})
        path = workdir / "goes_xray.zarr.zip"
        write_zarr(dataset, path)
        provenance = series_provenance(
            source_id=self.source_id,
            producer=SWPC_PRODUCER,
            product="GOES X-ray flux (1 day, both channels)",
            adapter_version=self.adapter_version,
            quality=quality,
            coverage=coverage,
            evidence_classes=["retrieved"],
            receipts=[receipt],
            native_resolution="1 minute per channel (geosynchronous point measurement)",
            measurement_scope="geosynchronous",
            extra={"status_declared": False, "satellites": labels, "channel_map": dict(XRAY_CHANNELS)},
        )
        return RunResult(
            source_id=self.source_id,
            provider_run_id=candidate.provider_run_id,
            run_time=candidate.run_time or times[-1],
            retrieved_at=datetime.now(UTC),
            complete=coverage["status"] == "complete",
            qc_passed=True,
            artifacts=[Artifact("goes_xray", MEDIA_ZARR, path, provenance)],
            native_crs=None,
            notes=f"{len(times)} minutes x {len(labels)} satellite(s), both channels, newest {format_time(times[-1])}",
        )


class SWPCKyotoDstAdapter:
    """The Kyoto WDC Dst index, relayed by SWPC.

    SWPC is the intermediary here, not the producer: the index is the Kyoto
    World Data Center's, re-serialised from the WDC tables and served with
    provisional and real-time values interleaved and no WDC final flag. That
    is what makes this artifact ``reprocessed`` and what keeps it off the
    display primary path.
    """

    source_id = "noaa-swpc-kyoto-dst"
    adapter_version = "swpc-kyoto-dst-v1"

    INTERMEDIARY = {
        "name": "NOAA SWPC",
        "method": "relay of the Kyoto WDC provisional and real-time Dst series as a JSON product",
        "transformations": [
            "re-serialised from the WDC text tables to SWPC JSON",
            "provisional and real-time values interleaved without the WDC final flag",
        ],
    }

    def __init__(self, client: PoliteClient | None = None, url: str = KYOTO_DST_URL) -> None:
        self._client = client
        self._url = url

    def discover(self, window: FetchWindow) -> list[RunCandidate]:
        payload, receipt = _retrieve(self._client, self._url, MAX_SMALL_FEED_BYTES)
        rows = records(payload, required=("time_tag", "dst"))
        if not rows:
            raise AdapterUnavailable("SWPC Kyoto Dst returned no usable records")
        timed = _timed_rows(rows, "time_tag")
        if not timed:
            raise AdapterUnavailable("SWPC Kyoto Dst records carry no parseable time_tag")
        times = [stamp for stamp, _ in timed]
        _refuse_if_stale(times[-1], window, "SWPC Kyoto Dst")
        return [_candidate("swpc-kyoto-dst", times[-1], self._url, {"records": [row for _, row in timed], "receipt": receipt}, times)]

    def fetch(self, candidate: RunCandidate, window: FetchWindow, workdir: Path) -> RunResult:
        receipt = _receipt_of(candidate, "SWPC Kyoto Dst")
        timed = _timed_rows(candidate.detail.get("records") or [], "time_tag")
        if not timed:
            raise AdapterUnavailable("SWPC Kyoto Dst fetch carried no records")
        times = [stamp for stamp, _ in timed]
        dst = numpy.array([float_or_nan(row.get("dst")) for _, row in timed])

        dataset = series_dataset(
            times,
            {"dst_index": (dst, _quantity("Dst index as produced by the Kyoto WDC and relayed by SWPC, as retrieved", "nT"))},
            {
                "source": "Kyoto WDC Dst index, relayed by SWPC",
                "producer_of_record": KYOTO_PRODUCER,
                "display_disclosure": "relayed index; never a display primary and never a derivation input",
            },
        )
        quality, coverage = series_quality("dst_index", dst)
        path = workdir / "kyoto_dst.zarr.zip"
        write_zarr(dataset, path)
        provenance = series_provenance(
            source_id=self.source_id,
            producer=KYOTO_PRODUCER,
            product="Dst index (provisional and real-time)",
            adapter_version=self.adapter_version,
            quality=quality,
            coverage=coverage,
            evidence_classes=["reprocessed"],
            receipts=[receipt],
            native_resolution="1 hour (planetary index, no spatial resolution)",
            measurement_scope="planetary",
            intermediary=dict(self.INTERMEDIARY),
            extra={
                "status_declared": False,
                "display_primary": False,
                "producer_of_record": KYOTO_PRODUCER,
            },
        )
        return RunResult(
            source_id=self.source_id,
            provider_run_id=candidate.provider_run_id,
            run_time=candidate.run_time or times[-1],
            retrieved_at=datetime.now(UTC),
            complete=coverage["status"] == "complete",
            qc_passed=True,
            artifacts=[Artifact("kyoto_dst", MEDIA_ZARR, path, provenance)],
            native_crs=None,
            notes=f"{len(times)} relayed Dst hours, newest {format_time(times[-1])}",
        )


PROPAGATED_ADAPTER = register(SWPCPropagatedSolarWindAdapter())
KP_1M_ADAPTER = register(SWPCKp1mAdapter())
ALERTS_ADAPTER = register(SWPCAlertsAdapter())
SCALES_ADAPTER = register(SWPCScalesAdapter())
GOES_MAGNETOMETER_ADAPTER = register(GOESMagnetometerAdapter())
GOES_XRAY_ADAPTER = register(GOESXrayAdapter())
KYOTO_DST_ADAPTER = register(SWPCKyotoDstAdapter())
