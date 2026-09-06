"""Bounded, nonpublishable CWFIS fire-source acquisition.

Native CWFIS fields are preserved as source records.  They are not fire-risk,
emissions, or air-quality values until a field/unit/mask contract is accepted.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections.abc import Mapping
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Any

import httpx

from ingest.contract import AdapterUnavailable, Artifact, DiscoveryBounds, FetchWindow, ResourceBounds, RunCandidate, RunResult
from ingest.http import MaxBytesExceeded, PoliteClient, RetriesExhausted, parse_directory_listing
from ingest.manifest import declared_classes, unresolved_manifest_validation

UTC = timezone.utc
CWFIS_DOWNLOADS = "https://cwfis.cfs.nrcan.gc.ca/downloads/hotspots"
CWFIS_WFS = "https://cwfis.cfs.nrcan.gc.ca/geoserver/public/ows"
FIRMS_ORIGIN = "https://firms.modaps.eosdis.nasa.gov"
FIRMS_INDEX = f"{FIRMS_ORIGIN}/api/active_fire_files/all?format=json"
MAX_LISTING_BYTES = 256 * 1024
MAX_WFS_BYTES = 2 * 1024 * 1024
MAX_CSV_BYTES = 32 * 1024 * 1024
MAX_FIRMS_INDEX_BYTES = 512 * 1024
MAX_FIRMS_CSV_BYTES = 32 * 1024 * 1024
_DATED_CSV = re.compile(r"^(?:in)?(\d{8})\.csv$")
RECEIPT_HEADERS = ("content-type", "content-length", "etag", "last-modified", "date")


def _get_bytes_with_completion(client: PoliteClient, url: str, *, max_bytes: int) -> tuple[bytes, Mapping[str, str], datetime]:
    completed_read = getattr(client, "get_bytes_with_headers_completed", None)
    if callable(completed_read):
        return completed_read(url, max_bytes=max_bytes)
    body, headers = client.get_bytes_with_headers(url, max_bytes=max_bytes)
    return body, headers, datetime.now(UTC)


def _receipt(url: str, body: bytes, headers: dict[str, str], completed: datetime) -> dict[str, Any]:
    return {"url": url, "body_bytes": len(body), "body_sha256": hashlib.sha256(body).hexdigest(),
            "completed_at": completed.isoformat(),
            "headers": {name: value for name in RECEIPT_HEADERS if (value := headers.get(name)) is not None}}


def _wfs_inventory(body: bytes) -> tuple[dict[str, Any], dict[str, str]]:
    try:
        document = json.loads(body)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise AdapterUnavailable(f"eccc-cwfis-fire: WFS is not JSON: {error}") from error
    if not isinstance(document, Mapping) or document.get("type") != "FeatureCollection" or not isinstance(document.get("features"), list):
        raise AdapterUnavailable("eccc-cwfis-fire: WFS is not a FeatureCollection")
    fields: set[str] = set()
    for index, feature in enumerate(document["features"]):
        if not isinstance(feature, Mapping) or feature.get("type") != "Feature":
            raise AdapterUnavailable(f"eccc-cwfis-fire: WFS feature {index} is invalid")
        properties = feature.get("properties")
        geometry = feature.get("geometry")
        if not isinstance(properties, Mapping) or (geometry is not None and not isinstance(geometry, Mapping)):
            raise AdapterUnavailable(f"eccc-cwfis-fire: WFS feature {index} has invalid properties or geometry")
        fields.update(str(key) for key in properties)
    inventory = {"geometry": "retrieved" if document["features"] else "observed-empty", **{key: "retrieved" for key in sorted(fields)}}
    snapshot = {key: document[key] for key in ("numberMatched", "numberReturned", "timeStamp") if key in document}
    return {"document": document, "snapshot": snapshot}, inventory


def _csv_inventory(body: bytes) -> tuple[list[str], int]:
    try:
        rows = csv.reader(StringIO(body.decode("utf-8")))
        header = next(rows)
    except (UnicodeError, StopIteration, csv.Error) as error:
        raise AdapterUnavailable(f"eccc-cwfis-fire: invalid CSV: {error}") from error
    if not header or any(not name.strip() for name in header) or len(set(header)) != len(header):
        raise AdapterUnavailable("eccc-cwfis-fire: CSV has an invalid header")
    count = 0
    for row in rows:
        if len(row) != len(header):
            raise AdapterUnavailable("eccc-cwfis-fire: CSV row does not match header width")
        count += 1
    return header, count


class CWFISFireProductsAdapter:
    source_id = "eccc-cwfis-fire-products"
    adapter_version = "cwfis-fire-products-v1"
    product = "CWFIS native hotspot and CFFEPS source records"

    def __init__(self, client: PoliteClient | None = None, *, downloads: str = CWFIS_DOWNLOADS, wfs: str = CWFIS_WFS) -> None:
        self._client = client or PoliteClient()
        self._downloads, self._wfs = downloads.rstrip("/"), wfs

    def discovery_bounds(self, _window: FetchWindow) -> DiscoveryBounds:
        return DiscoveryBounds(received_bytes=2 * MAX_LISTING_BYTES + MAX_WFS_BYTES)

    def resource_bounds(self, _candidate: RunCandidate, _window: FetchWindow) -> ResourceBounds:
        return ResourceBounds(store_bytes=2 * MAX_CSV_BYTES + MAX_WFS_BYTES,
                              filesystem_bytes=2 * MAX_CSV_BYTES + MAX_WFS_BYTES,
                              margin_bytes=2 * MAX_CSV_BYTES + MAX_WFS_BYTES,
                              received_bytes=2 * MAX_CSV_BYTES + MAX_WFS_BYTES)

    def _listed_date(self, directory: str, *, prefix: str = "") -> tuple[str, dict[str, Any]]:
        url = f"{directory}/"
        try:
            body, headers, completed = _get_bytes_with_completion(self._client, url, max_bytes=MAX_LISTING_BYTES)
            names = parse_directory_listing(body.decode("utf-8"))
        except (MaxBytesExceeded, RetriesExhausted, httpx.HTTPError, UnicodeError, ValueError, OSError) as error:
            raise AdapterUnavailable(f"{self.source_id}: unavailable listing {url}: {error}") from error
        eligible = [name for name in names if (match := _DATED_CSV.fullmatch(name)) and name.startswith(prefix)]
        if not eligible:
            raise AdapterUnavailable(f"{self.source_id}: listing {url} has no dated CSV")
        return max(eligible), _receipt(url, body, headers, completed)

    def discover(self, _window: FetchWindow) -> list[RunCandidate]:
        hotspot, hotspot_listing = self._listed_date(self._downloads)
        cffeps, cffeps_listing = self._listed_date(f"{self._downloads}/cffeps", prefix="in")
        return [RunCandidate(provider_run_id=f"cwfis-{hotspot}-{cffeps}", run_time=None,
                             urls=[self._wfs, f"{self._downloads}/{hotspot}", f"{self._downloads}/cffeps/{cffeps}"],
                             detail={"hotspot_csv": hotspot, "cffeps_csv": cffeps,
                                     "listings": {"hotspot": hotspot_listing, "cffeps": cffeps_listing}})]

    def fetch(self, candidate: RunCandidate, window: FetchWindow, workdir: Path) -> RunResult:
        names = {"hotspot_csv": candidate.detail.get("hotspot_csv"), "cffeps_csv": candidate.detail.get("cffeps_csv")}
        listings = candidate.detail.get("listings")
        if not all(isinstance(value, str) and _DATED_CSV.fullmatch(value) for value in names.values()) or not isinstance(listings, dict):
            raise AdapterUnavailable(f"{self.source_id}: invalid candidate discovery state")
        wfs_url = (f"{self._wfs}?service=WFS&version=1.0.0&request=GetFeature&typeName=public%3Ahotspots_last24hrs"
                   "&outputFormat=application%2Fjson&CQL_FILTER=lat%20BETWEEN%2045%20AND%2050.5%20AND%20lon%20BETWEEN%20-58%20AND%20-46&maxFeatures=1000")
        requests = (("wfs_hotspots", wfs_url, MAX_WFS_BYTES),
                    ("daily_hotspots", f"{self._downloads}/{names['hotspot_csv']}", MAX_CSV_BYTES),
                    ("cffeps", f"{self._downloads}/cffeps/{names['cffeps_csv']}", MAX_CSV_BYTES))
        validation = unresolved_manifest_validation(self.source_id, "native fire source fields have no owner-approved field, unit, mask, or API contract")
        workdir.mkdir(parents=True, exist_ok=True)
        artifacts: list[Artifact] = []
        completions: list[datetime] = []
        try:
            for kind, url, maximum in requests:
                try:
                    body, headers, completed = _get_bytes_with_completion(self._client, url, max_bytes=maximum)
                except (MaxBytesExceeded, RetriesExhausted, httpx.HTTPError, ValueError, OSError) as error:
                    raise AdapterUnavailable(f"{self.source_id}: unavailable {kind}: {error}") from error
                receipt = _receipt(url, body, headers, completed)
                if kind == "wfs_hotspots":
                    try:
                        wfs, inventory = _wfs_inventory(body)
                    except AdapterUnavailable as error:
                        raise AdapterUnavailable(f"{self.source_id}: {error}") from error
                    suffix, media = ".geojson", "application/geo+json"
                else:
                    fields, rows = _csv_inventory(body)
                    inventory = {field: "retrieved" for field in fields}
                    suffix, media = ".csv", "text/csv"
                output = workdir / f"{kind}{suffix}"
                output.write_bytes(body)
                digest = hashlib.sha256(body).hexdigest()
                artifacts.append(Artifact(kind, media, output, {
                    "source_id": self.source_id, "producer": "Natural Resources Canada, Canadian Forest Service",
                    "product": self.product, "source_uri": url, "provider_run_id": candidate.provider_run_id,
                    "valid_times": [],
                    "acquisition": {"listing": listings, "response": receipt,
                                    "query_window": {"start": window.start.isoformat(), "end": window.end.isoformat()}}, "upstream_sha256": digest,
                    "artifact_sha256": digest, "sha256": digest, "field_dispositions": inventory,
                    "field_interpretation": {"values": "verbatim native source strings or JSON values", "units": "uncontracted", "times": "verbatim, not normalized", "masks": "uncontracted"},
                    **({"record_count": rows, "source_file_date": str(names["hotspot_csv"] if kind == "daily_hotspots" else names["cffeps_csv"])} if kind != "wfs_hotspots" else {"feature_count": len(wfs["document"]["features"]), "source_snapshot": wfs["snapshot"]}),
                    "source_qc": {"status": "unknown", "flags": ["provider_quality_not_contracted"]},
                    "quality": validation.as_quality(), "operational": False, "adapter_version": self.adapter_version,
                    **declared_classes(["retrieved"]),
                }))
                completions.append(completed)
        except BaseException:
            for artifact in artifacts: artifact.payload_path.unlink(missing_ok=True)
            raise
        return RunResult(source_id=self.source_id, provider_run_id=candidate.provider_run_id, run_time=candidate.run_time,
                         retrieved_at=max(completions), complete=validation.complete, qc_passed=validation.qc_passed,
                         artifacts=artifacts, native_crs=None, notes="source records retained; publication blocked by unresolved contract")


class FIRMSActiveFireDownloadsAdapter:
    """Bounded public FIRMS Canada 24-hour MODIS/VIIRS CSV acquisition.

    FIRMS's MAP_KEY-gated area API is deliberately not used. Its public active-fire
    index advertises the selected download paths, which are retained as native CSV
    source records and remain nonpublishable pending an accepted field contract.
    """

    source_id = "nasa-firms-active-fire-downloads"
    adapter_version = "firms-active-fire-downloads-v1"
    product = "NASA FIRMS public Canada 24-hour active fire source records"
    _sensors = ("modis", "snpp", "noaa20", "noaa21")

    def __init__(self, client: PoliteClient | None = None, *, index: str = FIRMS_INDEX, origin: str = FIRMS_ORIGIN) -> None:
        self._client = client or PoliteClient()
        self._index, self._origin = index, origin.rstrip("/")

    def discovery_bounds(self, _window: FetchWindow) -> DiscoveryBounds:
        return DiscoveryBounds(received_bytes=MAX_FIRMS_INDEX_BYTES)

    def resource_bounds(self, _candidate: RunCandidate, _window: FetchWindow) -> ResourceBounds:
        total = len(self._sensors) * MAX_FIRMS_CSV_BYTES
        return ResourceBounds(store_bytes=total, filesystem_bytes=total, margin_bytes=total, received_bytes=total)

    def discover(self, _window: FetchWindow) -> list[RunCandidate]:
        try:
            body, headers, completed = _get_bytes_with_completion(self._client, self._index, max_bytes=MAX_FIRMS_INDEX_BYTES)
            document = json.loads(body)
        except (MaxBytesExceeded, RetriesExhausted, httpx.HTTPError, UnicodeError, json.JSONDecodeError, ValueError, OSError) as error:
            raise AdapterUnavailable(f"{self.source_id}: unavailable public download index: {error}") from error
        if not isinstance(document, Mapping) or not isinstance(document.get("csv"), Mapping):
            raise AdapterUnavailable(f"{self.source_id}: public download index has no CSV catalogue")
        paths: dict[str, str] = {}
        for sensor in self._sensors:
            regions = document["csv"].get(sensor)
            options = regions.get("Canada") if isinstance(regions, Mapping) else None
            selected = [path for path in options if isinstance(path, str) and path.endswith("_Canada_24h.csv")] if isinstance(options, list) else []
            if len(selected) != 1 or not selected[0].startswith("/data/active_fire/") or ".." in selected[0]:
                raise AdapterUnavailable(f"{self.source_id}: public index has no safe Canada 24-hour CSV for {sensor}")
            paths[sensor] = selected[0]
        return [RunCandidate(provider_run_id="firms-public-canada-24h", run_time=None,
                             urls=[self._index, *(f"{self._origin}{path}" for path in paths.values())],
                             detail={"paths": paths, "index": _receipt(self._index, body, headers, completed)})]

    def fetch(self, candidate: RunCandidate, window: FetchWindow, workdir: Path) -> RunResult:
        paths, index_receipt = candidate.detail.get("paths"), candidate.detail.get("index")
        if not isinstance(paths, Mapping) or set(paths) != set(self._sensors) or not isinstance(index_receipt, Mapping):
            raise AdapterUnavailable(f"{self.source_id}: invalid candidate discovery state")
        validation = unresolved_manifest_validation(self.source_id, "native FIRMS fields have no owner-approved field, unit, mask, or API contract")
        workdir.mkdir(parents=True, exist_ok=True)
        artifacts: list[Artifact] = []
        completions: list[datetime] = []
        try:
            for sensor in self._sensors:
                path = paths[sensor]
                if not isinstance(path, str) or not path.startswith("/data/active_fire/") or ".." in path:
                    raise AdapterUnavailable(f"{self.source_id}: unsafe public CSV path")
                url = f"{self._origin}{path}"
                try:
                    body, headers, completed = _get_bytes_with_completion(self._client, url, max_bytes=MAX_FIRMS_CSV_BYTES)
                except (MaxBytesExceeded, RetriesExhausted, httpx.HTTPError, ValueError, OSError) as error:
                    raise AdapterUnavailable(f"{self.source_id}: unavailable {sensor} CSV: {error}") from error
                fields, rows = _csv_inventory(body)
                output = workdir / f"firms_{sensor}.csv"
                output.write_bytes(body)
                digest = hashlib.sha256(body).hexdigest()
                artifacts.append(Artifact(f"firms_{sensor}_canada_24h", "text/csv", output, {
                    "source_id": self.source_id, "producer": "NASA FIRMS / LANCE",
                    "product": self.product, "source_uri": url, "provider_run_id": candidate.provider_run_id,
                    "valid_times": [], "acquisition": {"index": dict(index_receipt), "response": _receipt(url, body, headers, completed),
                    "query_window": {"start": window.start.isoformat(), "end": window.end.isoformat()}},
                    "upstream_sha256": digest, "artifact_sha256": digest, "sha256": digest,
                    "field_dispositions": {field: "retrieved" for field in fields}, "record_count": rows,
                    "field_interpretation": {"values": "verbatim native CSV strings", "units": "uncontracted", "times": "verbatim, not normalized", "masks": "uncontracted"},
                    "source_qc": {"status": "unknown", "flags": ["provider_quality_not_contracted"]},
                    "quality": validation.as_quality(), "operational": False, "adapter_version": self.adapter_version,
                    **declared_classes(["retrieved"]),
                }))
                completions.append(completed)
        except BaseException:
            for artifact in artifacts:
                artifact.payload_path.unlink(missing_ok=True)
            raise
        return RunResult(source_id=self.source_id, provider_run_id=candidate.provider_run_id, run_time=None,
                         retrieved_at=max(completions), complete=validation.complete, qc_passed=validation.qc_passed,
                         artifacts=artifacts, native_crs=None,
                         notes="public download records retained; publication blocked by unresolved contract")


class FIRMSPermissionRequiredAdapter:
    """Explicitly refuse only the MAP_KEY-gated FIRMS area API without handling secrets."""
    source_id = "nasa-firms-area-api"

    def discover(self, _window: FetchWindow) -> list[RunCandidate]:
        raise AdapterUnavailable("nasa-firms-area-api: official area API requires a MAP_KEY; use public download adapter or configure permission separately")
