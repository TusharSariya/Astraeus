"""Bounded ECCC structured hazard products for the isolated experiment."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping as MappingABC
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from ingest.contract import EVIDENCE_BOX_BOUNDS, MEDIA_GEOJSON, AdapterUnavailable, Artifact, FetchWindow, RunCandidate, RunResult
import httpx

from ingest.http import MaxBytesExceeded, PoliteClient, RetriesExhausted
from ingest.manifest import declared_classes, unresolved_manifest_validation

UTC = timezone.utc
BASE = "https://api.weather.gc.ca"
MAX_COLLECTION_BYTES = 8 * 1024 * 1024
HURRICANE_COLLECTIONS = (
    "hurricanes-cyclone-realtime",
    "hurricanes-track-realtime",
    "hurricanes-error_cone-realtime",
    "hurricanes-wind_radii-realtime",
)
RECEIPT_HEADERS = ("content-type", "content-length", "etag", "last-modified", "date")


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _feature_times(features: list[dict[str, Any]]) -> list[datetime]:
    names = ("publication_datetime", "validity_datetime", "forecast_datetime", "expiration_datetime", "datetime", "issue_datetime", "issue_time", "valid_time", "valid_datetime", "timestamp")
    found: list[datetime] = []
    for feature in features:
        properties = feature.get("properties") or {}
        for name in names:
            moment = _parse_time(properties.get(name))
            if moment is not None:
                found.append(moment.astimezone(UTC))
                break
    return sorted(set(found))


def _validated_features(source_id: str, collection: str, document: Any) -> list[dict[str, Any]]:
    if not isinstance(document, MappingABC) or document.get("type") != "FeatureCollection":
        raise AdapterUnavailable(f"{source_id}: {collection} is not a GeoJSON FeatureCollection")
    features = document.get("features")
    if not isinstance(features, list):
        raise AdapterUnavailable(f"{source_id}: {collection} features are not a list")
    for index, feature in enumerate(features):
        if not isinstance(feature, MappingABC) or feature.get("type") != "Feature":
            raise AdapterUnavailable(f"{source_id}: {collection} feature {index} is not a GeoJSON Feature")
        if not isinstance(feature.get("properties"), MappingABC):
            raise AdapterUnavailable(f"{source_id}: {collection} feature {index} properties are not an object")
        geometry = feature.get("geometry")
        if geometry is not None and not isinstance(geometry, MappingABC):
            raise AdapterUnavailable(f"{source_id}: {collection} feature {index} geometry is not an object or null")
    return features


class ECCCOGCHazardAdapter:
    """Fetch one or more official OGC feature collections without interpreting them."""

    adapter_version = "eccc-ogc-hazards-v1"
    collections: tuple[str, ...] = ()
    product = ""
    source_key = ""
    advertised_fields: tuple[str, ...] = ()

    def __init__(self, client: PoliteClient | None = None, *, base_url: str = BASE) -> None:
        self._client = client or PoliteClient()
        self._base_url = base_url.rstrip("/")

    @property
    def source_id(self) -> str:
        """Experimental identity; static registry discovery intentionally excludes it."""
        return self.source_key

    def _url(self, collection: str) -> str:
        box = EVIDENCE_BOX_BOUNDS
        bbox = f"{box['west']},{box['south']},{box['east']},{box['north']}"
        return f"{self._base_url}/collections/{collection}/items?bbox={bbox}&limit=1000&f=json"

    def discover(self, window: FetchWindow) -> list[RunCandidate]:
        documents: dict[str, dict[str, Any]] = {}
        digests: dict[str, str] = {}
        receipts: dict[str, dict[str, Any]] = {}
        times: list[datetime] = []
        for collection in self.collections:
            url = self._url(collection)
            try:
                raw, headers = self._client.get_bytes_with_headers(url, max_bytes=MAX_COLLECTION_BYTES)
                completed_at = datetime.now(UTC)
                document = json.loads(raw)
            except (MaxBytesExceeded, RetriesExhausted, httpx.HTTPError, ValueError, TypeError, OSError) as error:
                raise AdapterUnavailable(f"{self.source_id}: invalid or oversized {collection} response: {error}") from error
            features = _validated_features(self.source_id, collection, document)
            documents[collection] = document
            digests[collection] = hashlib.sha256(raw).hexdigest()
            receipts[collection] = {
                "url": url,
                "body_bytes": len(raw),
                "body_sha256": digests[collection],
                "completed_at": completed_at.isoformat(),
                "headers": {name: value for name in RECEIPT_HEADERS if (value := headers.get(name)) is not None},
            }
            times.extend(_feature_times(features))
        observed_at = max(times) if times else None
        identity = hashlib.sha256("".join(digests[name] for name in self.collections).encode()).hexdigest()[:16]
        run_label = observed_at.strftime("%Y%m%dT%H%M%SZ") if observed_at else "observed-empty"
        return [RunCandidate(
            provider_run_id=f"{self.source_id}-{run_label}-{identity}",
            run_time=observed_at,
            urls=[self._url(name) for name in self.collections],
            detail={
                "documents": documents,
                "digests": digests,
                "receipts": receipts,
                "valid_times": [moment.isoformat() for moment in sorted(set(times))],
                "query_window": {"start": window.start.isoformat(), "end": window.end.isoformat()},
            },
        )]

    def fetch(self, candidate: RunCandidate, window: FetchWindow, workdir: Path) -> RunResult:
        documents = candidate.detail.get("documents") or {}
        if set(documents) != set(self.collections):
            raise AdapterUnavailable(f"{self.source_id}: candidate is missing a required collection")
        receipts = candidate.detail.get("receipts") or {}
        if set(receipts) != set(self.collections):
            raise AdapterUnavailable(f"{self.source_id}: candidate is missing a required acquisition receipt")
        completed = [_parse_time(receipts[name].get("completed_at")) for name in self.collections]
        if any(moment is None for moment in completed):
            raise AdapterUnavailable(f"{self.source_id}: candidate has an invalid acquisition completion time")
        retrieved_at = max(moment for moment in completed if moment is not None)
        validation = unresolved_manifest_validation(
            self.source_id,
            "native hazard GeoJSON has no owner-approved canonical RunManifest",
        )
        workdir.mkdir(parents=True, exist_ok=True)
        artifacts: list[Artifact] = []
        for collection in self.collections:
            document = documents[collection]
            features = _validated_features(self.source_id, collection, document)
            output = workdir / f"{collection}.geojson"
            output.write_text(json.dumps(document, sort_keys=True, separators=(",", ":")), "utf-8")
            digest = hashlib.sha256(output.read_bytes()).hexdigest()
            present_fields = {str(name) for feature in features for name in (feature.get("properties") or {})}
            dispositions = {
                name: "observed-empty" if not features else "retrieved" if name in present_fields else "missing-in-snapshot"
                for name in self.advertised_fields
            }
            extra_fields = sorted(present_fields.difference(self.advertised_fields))
            artifacts.append(Artifact(collection, MEDIA_GEOJSON, output, {
                "source_id": self.source_id,
                "producer": "Environment and Climate Change Canada",
                "product": self.product,
                "collection": collection,
                "source_uri": self._url(collection),
                "provider_run_id": candidate.provider_run_id,
                "valid_times": list(candidate.detail.get("valid_times") or []),
                "query_window": dict(candidate.detail["query_window"]),
                "retrieved_at": retrieved_at.isoformat(),
                "acquisition": dict(receipts[collection]),
                "upstream_sha256": candidate.detail["digests"][collection],
                "artifact_sha256": digest,
                "sha256": digest,
                "feature_count": len(features),
                "empty_is_an_answer": len(features) == 0,
                "field_dispositions": {"geometry": "observed-empty" if not features else "retrieved", **dispositions},
                "uncontracted_properties": extra_fields,
                "property_semantics": "preserved as published; no hazard category or numeric value is inferred",
                "quality": {
                    **validation.as_quality(),
                    "notices": [f"uncontracted_property:{name}" for name in extra_fields],
                },
                "coverage": {"status": "observed-empty" if not features else "complete", "bounds": dict(EVIDENCE_BOX_BOUNDS)},
                "operational": False,
                "adapter_version": self.adapter_version,
                **declared_classes(["retrieved"]),
            }))
        return RunResult(
            source_id=self.source_id, provider_run_id=candidate.provider_run_id,
            run_time=candidate.run_time, retrieved_at=retrieved_at, complete=validation.complete,
            qc_passed=validation.qc_passed, artifacts=artifacts, native_crs="OGC:CRS84",
            notes=(f"retained {len(artifacts)} structurally checked collection snapshot(s); "
                   "publication blocked by unresolved canonical manifest"),
        )


class ECCCThunderstormOutlookAdapter(ECCCOGCHazardAdapter):
    source_key = "eccc-thunderstorm-outlooks"
    product = "Thunderstorm Outlooks (experimental GeoJSON)"
    collections = ("thunderstorm_outlook",)
    advertised_fields = (
        "amendment", "domain", "expiration_datetime", "file_id", "metobject.confidence.value",
        "metobject.gust.unit", "metobject.gust.value", "metobject.hail.unit", "metobject.hail.value",
        "metobject.impact.value", "metobject.rain.unit", "metobject.rain.value", "metobject.risk_swo.value",
        "metobject.severity.value", "metobject.sub_type", "metobject.thunderstorm.value",
        "metobject.tornado_risk.value", "product_class", "product_sub_type", "product_type",
        "publication_datetime", "status", "type", "validity_datetime",
    )


class ECCCHurricaneProductsAdapter(ECCCOGCHazardAdapter):
    source_key = "eccc-hurricane-products"
    product = "Canadian Hurricane Centre structured prediction products"
    collections = HURRICANE_COLLECTIONS
    advertised_fields = (
        "active", "file_name", "forecast_datetime", "latest_publication",
        "publication_datetime", "storm_name", "validity_datetime",
    )
