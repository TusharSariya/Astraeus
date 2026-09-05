"""Shared shapes for the coordinate-free space-weather series adapters.

Every space-weather product this experiment retrieves is a series with no
horizontal coordinates: a planetary index, an L1 or geosynchronous point
measurement, a propagated model value or an issued text product. What they
have in common is pinned here once so that the adapters written for each
feed (``ingest/adapters/swpc.py``, ``swpc_products.py``, ``gfz.py``) produce
artifacts the API reads back through one path, ``LiveStore.read_series``.

The rules these helpers enforce, none of them negotiable per adapter:

- Every transfer is finite and bounded: :func:`fetch_json` streams to disk
  under a byte ceiling and refuses a body that grows past it. It returns the
  payload together with a :class:`FeedReceipt` - URL, byte count, SHA-256,
  capture instant, the provider's ``Last-Modified`` - which is the evidence
  of retrieval that belongs in provenance. The payload itself never does.
- Every timestamp is the feed's own. :func:`parse_time` reads the forms the
  feeds actually use and returns ``None`` for anything else; nothing is ever
  stamped with the wall clock.
- A missing value stays a gap (NaN), never zero and never carried forward.
- A series is stored on ``valid_time`` alone, or on ``valid_time`` times one
  categorical platform axis (``spacecraft``, ``satellite``) where a feed
  interleaves several measuring platforms at the same instant. A 1-D series
  with duplicate instants is refused: the duplicate is a platform the caller
  failed to separate, not a second reading.
- Quality is stated directly, because these series have no grid for
  ``validate_run`` to check: the fraction of instants carrying a finite
  value of the series' key variable.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy
import xarray

from ingest.contract import AdapterUnavailable
from ingest.http import MaxBytesExceeded, PoliteClient
from ingest.manifest import declared_classes

UTC = timezone.utc

#: Ceilings for the feeds this experiment reads, in bytes. Measured sizes
#: on 2026-09-05 sit well under each ceiling; a feed that outgrows its
#: ceiling is refused, never partially read, so the ceiling is a safeguard
#: against an unbounded transfer rather than a tuning knob.
MAX_SMALL_FEED_BYTES = 512 * 1024
MAX_LARGE_FEED_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True)
class FeedReceipt:
    """What was retrieved, without the retrieval itself.

    This is the completion evidence the owner's 2026-09-05 decision asks
    for: enough to reproduce and verify a capture, and nothing that would
    put provider bytes into Git or into a response.
    """

    url: str
    byte_count: int
    sha256: str
    captured_at: str
    last_modified: str | None = None
    request_parameters: dict[str, str] | None = None

    def as_dict(self) -> dict[str, Any]:
        record = asdict(self)
        if record["request_parameters"] is None:
            del record["request_parameters"]
        if record["last_modified"] is None:
            del record["last_modified"]
        return record


def fetch_json(
    client: PoliteClient,
    url: str,
    *,
    max_bytes: int,
    workdir: Path,
    request_parameters: Mapping[str, str] | None = None,
) -> tuple[Any, FeedReceipt]:
    """Retrieve one JSON feed under a byte ceiling and receipt it.

    The body is streamed to ``workdir`` through ``PoliteClient.download`` so
    the ceiling is enforced mid-stream, hashed, parsed, and the scratch file
    removed. Anything that is not a well-formed JSON document is refused as
    unavailable: a provider error page behind an HTTP 200 is not a feed.
    """
    workdir.mkdir(parents=True, exist_ok=True)
    scratch = workdir / f".feed-{hashlib.sha1(url.encode()).hexdigest()}.json"
    captured_at = datetime.now(UTC)
    try:
        _written, headers = client.download_with_headers(url, scratch, max_bytes=max_bytes)
        last_modified = headers.get("Last-Modified") or headers.get("last-modified")
        body = scratch.read_bytes()
    except MaxBytesExceeded as error:
        scratch.unlink(missing_ok=True)
        raise AdapterUnavailable(f"space-weather feed refused: {error}") from error
    except Exception as error:
        scratch.unlink(missing_ok=True)
        raise AdapterUnavailable(f"space-weather feed unavailable: {url}: {error}") from error
    scratch.unlink(missing_ok=True)
    if not body:
        raise AdapterUnavailable(f"space-weather feed answered with an empty body: {url}")
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AdapterUnavailable(f"space-weather feed is not JSON: {url}: {error}") from error
    receipt = FeedReceipt(
        url=url,
        byte_count=len(body),
        sha256=hashlib.sha256(body).hexdigest(),
        captured_at=captured_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        last_modified=last_modified,
        request_parameters=dict(request_parameters) if request_parameters else None,
    )
    return payload, receipt


def parse_time(value: Any) -> datetime | None:
    """A feed instant as an aware UTC datetime, or None.

    Accepts the forms the SWPC and GFZ feeds actually serve:
    ``2026-09-05T19:29:00``, ``2026-09-05T19:29:00Z``,
    ``2026-09-05 16:33:07.073`` (alerts ``issue_datetime``) and a
    ``DateStamp``/``TimeStamp`` pair joined with a space. A naive instant is
    UTC, because every one of these feeds documents UTC.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    if " " in text and "T" not in text:
        text = text.replace(" ", "T", 1)
    try:
        stamp = datetime.fromisoformat(text)
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=UTC)
    return stamp.astimezone(UTC)


def format_time(stamp: datetime) -> str:
    return stamp.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def records(payload: Any, *, required: Sequence[str]) -> list[dict[str, Any]]:
    """SWPC list payloads as dicts.

    The products endpoints serve either a list of objects or a list of rows
    under a header row; both are accepted. Anything else yields an empty list
    for the caller to refuse.
    """
    if not isinstance(payload, list) or not payload:
        return []
    if isinstance(payload[0], dict):
        return [record for record in payload if isinstance(record, dict) and all(key in record for key in required)]
    if isinstance(payload[0], list):
        header = [str(name) for name in payload[0]]
        if not all(name in header for name in required):
            return []
        return [dict(zip(header, row)) for row in payload[1:] if isinstance(row, list) and len(row) == len(header)]
    return []


def float_or_nan(value: Any) -> float:
    """A number as float; None, a bool, or anything unparseable is a gap."""
    if value is None or isinstance(value, bool):
        return float("nan")
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def flag_or_nan(value: Any) -> float:
    """A boolean or integer flag as float; absent is NaN, never 0."""
    if value is None:
        return float("nan")
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    return float_or_nan(value)


def flag_attrs(meanings: Sequence[str], *, long_name: str, values: Sequence[int] | None = None) -> dict[str, Any]:
    """CF flag attributes so ``read_series`` serves the meaning, not the code."""
    codes = list(values) if values is not None else list(range(len(meanings)))
    if len(codes) != len(meanings):
        raise ValueError("flag values and meanings differ in length")
    return {
        "units": "flag",
        "original_units": "provider label",
        "flag_values": codes,
        "flag_meanings": " ".join(meanings),
        "long_name": long_name,
    }


def _stamps(times: Sequence[datetime]) -> numpy.ndarray:
    return numpy.array([numpy.datetime64(t.astimezone(UTC).replace(tzinfo=None), "ns") for t in times])


def series_dataset(
    times: Sequence[datetime],
    variables: Mapping[str, tuple[numpy.ndarray | Sequence[Any], Mapping[str, Any]]],
    attrs: Mapping[str, Any],
) -> xarray.Dataset:
    """A time-only dataset: deliberately no latitude/longitude coordinates.

    ``times`` must be strictly increasing. A repeated instant is refused:
    where a feed interleaves platforms, use :func:`platform_series_dataset`.
    """
    if not times:
        raise AdapterUnavailable("a space-weather series needs at least one instant")
    stamps = _stamps(times)
    if len(numpy.unique(stamps)) != len(stamps) or not numpy.all(numpy.diff(stamps.astype("int64")) > 0):
        raise AdapterUnavailable("series instants must be strictly increasing; an interleaved feed needs a platform axis")
    data_vars = {}
    for name, (values, var_attrs) in variables.items():
        array = numpy.asarray(values)
        if array.shape != (len(times),):
            raise AdapterUnavailable(f"{name}: {array.shape} does not match {len(times)} instants")
        data_vars[name] = (("valid_time",), array, dict(var_attrs))
    return xarray.Dataset(data_vars, coords={"valid_time": stamps}, attrs=dict(attrs))


def platform_series_dataset(
    times: Sequence[datetime],
    platforms: Sequence[str],
    variables: Mapping[str, tuple[numpy.ndarray, Mapping[str, Any]]],
    attrs: Mapping[str, Any],
    *,
    platform_dim: str = "spacecraft",
) -> xarray.Dataset:
    """A series on ``valid_time`` times one categorical platform axis.

    Every variable is ``(len(times), len(platforms))``; a platform with no
    record at an instant holds NaN there. The platform labels are the feed's
    own tokens verbatim (``SOLAR1``, ``ACE``, ``IMAP``; GOES ``18``/``19``),
    sorted, never renamed to a spacecraft the feed did not declare.
    """
    if not times or not platforms:
        raise AdapterUnavailable("a platform series needs at least one instant and one platform")
    stamps = _stamps(times)
    if len(numpy.unique(stamps)) != len(stamps) or not numpy.all(numpy.diff(stamps.astype("int64")) > 0):
        raise AdapterUnavailable("platform series instants must be strictly increasing")
    labels = [str(p) for p in platforms]
    if len(set(labels)) != len(labels) or labels != sorted(labels):
        raise AdapterUnavailable("platform labels must be unique and sorted")
    data_vars = {}
    for name, (values, var_attrs) in variables.items():
        array = numpy.asarray(values)
        if array.shape != (len(times), len(labels)):
            raise AdapterUnavailable(f"{name}: {array.shape} does not match ({len(times)}, {len(labels)})")
        data_vars[name] = (("valid_time", platform_dim), array, dict(var_attrs))
    return xarray.Dataset(
        data_vars,
        coords={"valid_time": stamps, platform_dim: numpy.array(labels)},
        attrs=dict(attrs),
    )


def series_quality(name: str, values: numpy.ndarray, *, note: str = "no spatial coverage claimed") -> tuple[dict[str, Any], dict[str, Any]]:
    """Manual quality/coverage blocks for a coordinate-free series.

    ``validate_run`` requires a horizontal grid by design; these series have
    none on purpose, so completeness is stated directly: the fraction of
    instants carrying at least one finite value of ``values`` (across
    platforms where there is a platform axis).
    """
    array = numpy.asarray(values, dtype="float64")
    if array.ndim == 2:
        per_instant = numpy.isfinite(array).any(axis=1)
    else:
        per_instant = numpy.isfinite(array)
    finite = float(per_instant.mean()) if per_instant.size else 0.0
    quality = {
        "status": "passed" if finite > 0.0 else "failed",
        "flags": [] if finite > 0.0 else [f"empty_field:{name}"],
        "detail": f"{name}: {finite:.4f} of instants carry a finite value; {note}",
    }
    coverage = {"status": "complete" if finite > 0.0 else "outside", "fraction": round(finite, 4)}
    return quality, coverage


def series_provenance(
    *,
    source_id: str,
    producer: str,
    product: str,
    adapter_version: str,
    quality: Mapping[str, Any],
    coverage: Mapping[str, Any],
    evidence_classes: Sequence[str],
    receipts: Sequence[FeedReceipt],
    native_resolution: str,
    measurement_scope: str,
    intermediary: Mapping[str, Any] | None = None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """The provenance block every space-weather artifact carries.

    ``measurement_scope`` is one of ``planetary``, ``l1``, ``propagated``,
    ``geosynchronous``, ``station``, ``issued`` - the separation the ticket
    asks for between planet-wide indices, L1 measurements, propagated model
    values, geosynchronous measurements, ground stations and issued text.
    ``intermediary`` is required when the evidence class is ``reprocessed``
    and refused otherwise, so a relayed index can never pass as retrieved.
    """
    if measurement_scope not in {"planetary", "l1", "propagated", "geosynchronous", "station", "issued"}:
        raise ValueError(f"unknown measurement scope {measurement_scope!r}")
    classes = declared_classes(list(evidence_classes))
    if "reprocessed" in evidence_classes and not intermediary:
        raise ValueError("a reprocessed artifact must name its intermediary")
    if intermediary and "reprocessed" not in evidence_classes:
        raise ValueError("an intermediary is declared only on a reprocessed artifact")
    block: dict[str, Any] = {
        "source_id": source_id,
        "producer": producer,
        "product": product,
        "native_resolution": native_resolution,
        "native_crs": "not_applicable",
        "measurement_scope": measurement_scope,
        "adapter_version": adapter_version,
        "quality": dict(quality),
        "coverage": dict(coverage),
        **classes,
        "retrieval": [receipt.as_dict() for receipt in receipts],
    }
    if intermediary:
        block["intermediary"] = dict(intermediary)
    if extra:
        block.update(dict(extra))
    return block
