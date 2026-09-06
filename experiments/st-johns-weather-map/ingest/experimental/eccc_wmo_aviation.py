"""Bounded native retention for selected Canadian aviation products.

The adapters in this module retain official ECCC IWXXM documents and selected
CWAO winds/temperature alphanumeric bulletins byte-for-byte. They do not
translate native values or publish them through an Astraeus API.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re
from typing import Any, Mapping
import xml.etree.ElementTree as ET

import httpx

from ingest.contract import AdapterUnavailable, Artifact, FetchWindow, RunCandidate, RunResult
from ingest.experimental.eccc_local_products import _xml
from ingest.http import MaxBytesExceeded, PoliteClient, RetriesExhausted, parse_directory_listing
from ingest.manifest import declared_classes, unresolved_manifest_validation

UTC = timezone.utc
IWXXM_BASE = "https://dd.weather.gc.ca/today/aviation/iwxxm"
BULLETIN_ARCHIVE = "https://dd.weather.gc.ca"
MAX_LISTING = 128 * 1024
MAX_IWXXM = 1024 * 1024
MAX_BULLETIN = 256 * 1024
MAX_HOURS = 24
MAX_BULLETINS = 3
_TAF_NAME = re.compile(r"^A_LTCN38CWAO\d{6}(?P<bbb>[A-Z]*)_C_CWAO_(?P<stamp>\d{14})\.xml$")
_SIGMET_NAME = re.compile(r"^A_L(?:S|Y|V)CN[^_]*_C_CWAO_(?P<stamp>\d{14})\.xml$")
_FD_NAME = re.compile(r"^FDCN(?P<period>0[123])_CWAO_(?P<stamp>\d{6})_[A-Z]*_*\d+$")
_ISO_TIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$")


def _receipt(url: str, body: bytes, headers: Mapping[str, str], completed: datetime) -> dict[str, Any]:
    return {
        "url": url,
        "body_bytes": len(body),
        "body_sha256": hashlib.sha256(body).hexdigest(),
        "completed_at": completed.isoformat(),
        "headers": {str(name).lower(): str(value) for name, value in headers.items()},
    }


def _get(client: PoliteClient, url: str, cap: int, source_id: str) -> tuple[bytes, dict[str, Any]]:
    try:
        body, headers, completed = client.get_bytes_with_headers_completed(
            url, max_bytes=cap, headers={"Accept-Encoding": "identity"}
        )
    except (MaxBytesExceeded, RetriesExhausted, httpx.HTTPError, OSError, ValueError) as error:
        raise AdapterUnavailable(f"{source_id}: bounded request unavailable: {error}") from error
    return body, _receipt(url, body, headers, completed)


def _listing(client: PoliteClient, url: str, source_id: str, *, suffixes: tuple[str, ...] = ()) -> tuple[list[str], dict[str, Any]]:
    body, receipt = _get(client, url, MAX_LISTING, source_id)
    try:
        return parse_directory_listing(body.decode("utf-8"), suffixes=suffixes), receipt
    except (UnicodeError, ValueError) as error:
        raise AdapterUnavailable(f"{source_id}: invalid directory listing: {error}") from error


def _hour_documents(client: PoliteClient, root: str, source_id: str, pattern: re.Pattern[str]) -> tuple[list[tuple[str, str]], list[dict[str, Any]]]:
    names, root_receipt = _listing(client, root, source_id)
    hours = sorted(name for name in names if re.fullmatch(r"\d{2}/", name))
    if not hours or len(hours) > MAX_HOURS:
        raise AdapterUnavailable(f"{source_id}: expected 1..{MAX_HOURS} UTC hour directories")
    found: list[tuple[str, str]] = []
    receipts = [root_receipt]
    for hour in hours:
        hour_url = root + hour
        documents, receipt = _listing(client, hour_url, source_id, suffixes=(".xml",))
        receipts.append(receipt)
        found.extend((name, hour_url + name) for name in documents if pattern.fullmatch(name))
    return found, receipts


def _local_name(qname: str) -> str:
    return qname.rsplit("}", 1)[-1]


def _xml_shape(root: ET.Element) -> dict[str, Any]:
    elements = Counter(element.tag for element in root.iter())
    attributes = Counter(name for element in root.iter() for name in element.attrib)
    times: list[dict[str, str]] = []
    for element in root.iter():
        text = (element.text or "").strip()
        if _ISO_TIME.fullmatch(text):
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                raise AdapterUnavailable("eccc-iwxxm-aviation-native: native time lacks an offset")
            times.append({"element": element.tag, "value": text})
    if not any(_local_name(item["element"]) == "timePosition" for item in times):
        raise AdapterUnavailable("eccc-iwxxm-aviation-native: no aware native timePosition")
    inventory: list[dict[str, Any]] = []

    def visit(element: ET.Element, path: str) -> None:
        local = _local_name(element.tag)
        here = f"{path}/{local}"
        inventory.append({
            "path": here,
            "qname": element.tag,
            "attributes": dict(sorted(element.attrib.items())),
            "text": (element.text or "").strip(),
        })
        seen: dict[str, int] = {}
        for child in element:
            child_local = _local_name(child.tag)
            seen[child_local] = seen.get(child_local, 0) + 1
            visit(child, f"{here}[{child_local}:{seen[child_local]}]")

    visit(root, "")
    return {
        "element_qname_counts": dict(sorted(elements.items())),
        "attribute_qname_counts": dict(sorted(attributes.items())),
        "native_times": times,
        "native_element_inventory": inventory,
    }


class ECCCIWXXMAviationNativeAdapter:
    source_id = "eccc-iwxxm-aviation-native"
    adapter_version = "eccc-iwxxm-aviation-native-v1"

    def __init__(self, client: PoliteClient | None = None, *, base_url: str = IWXXM_BASE) -> None:
        self._client = client or PoliteClient()
        self._base = base_url.rstrip("/")

    def discover(self, _window: FetchWindow) -> list[RunCandidate]:
        selections = (
            ("taf-cyyt", f"{self._base}/taf/cwao/", _TAF_NAME),
            ("sigmet-czqx", f"{self._base}/sigmet/czqx/", _SIGMET_NAME),
        )
        products: list[dict[str, str]] = []
        listing_receipts: dict[str, list[dict[str, Any]]] = {}
        for product, root, pattern in selections:
            found, receipts = _hour_documents(self._client, root, self.source_id, pattern)
            if not found:
                raise AdapterUnavailable(f"{self.source_id}: no current {product} document")
            if product == "taf-cyyt" and any(pattern.fullmatch(item[0]).group("bbb") for item in found):
                raise AdapterUnavailable(f"{self.source_id}: TAF amendment/correction precedence is unresolved")
            latest_stamp = max(pattern.fullmatch(item[0]).group("stamp") for item in found)
            latest = [item for item in found if pattern.fullmatch(item[0]).group("stamp") == latest_stamp]
            if len(latest) != 1:
                raise AdapterUnavailable(f"{self.source_id}: ambiguous {product} amendment/correction state")
            name, url = latest[0]
            products.append({"product": product, "name": name, "url": url})
            listing_receipts[product] = receipts
        digest = hashlib.sha256("\n".join(item["url"] for item in products).encode()).hexdigest()[:12]
        return [RunCandidate(f"eccc-iwxxm-{digest}", None, [item["url"] for item in products], {
            "products": products,
            "listing_receipts": listing_receipts,
            "selection": {
                "taf": "LTCN38 bulletin must contain CYYT",
                "sigmet": "Gander FIR issuer designator CZQX",
                "evidence_box": [45.0, -58.0, 50.5, -46.0],
            },
        })]

    def fetch(self, candidate: RunCandidate, _window: FetchWindow, workdir: Path) -> RunResult:
        products = candidate.detail.get("products")
        listings = candidate.detail.get("listing_receipts")
        if not isinstance(products, list) or len(products) != 2 or not isinstance(listings, dict):
            raise AdapterUnavailable(f"{self.source_id}: incomplete candidate")
        validation = unresolved_manifest_validation(
            self.source_id,
            "IWXXM fields, quality, geographic intersection, licence, manifest, and API contract are unresolved",
        )
        workdir.mkdir(parents=True, exist_ok=True)
        artifacts: list[Artifact] = []
        outputs: list[Path] = []
        completions: list[datetime] = []
        try:
            for product in products:
                if not isinstance(product, dict) or product.get("product") not in {"taf-cyyt", "sigmet-czqx"}:
                    raise AdapterUnavailable(f"{self.source_id}: invalid product selection")
                kind = str(product["product"])
                body, receipt = _get(self._client, str(product["url"]), MAX_IWXXM, self.source_id)
                root = _xml(body, self.source_id)
                shape = _xml_shape(root)
                values = [(element.text or "").strip() for element in root.iter()]
                expected_member = "TAF" if kind == "taf-cyyt" else "SIGMET"
                required_identity = "CYYT" if kind == "taf-cyyt" else "CZQX"
                member_count = sum(_local_name(element.tag) == expected_member for element in root.iter())
                if (_local_name(root.tag) != "MeteorologicalBulletin" or member_count < 1
                        or required_identity not in values):
                    raise AdapterUnavailable(f"{self.source_id}: {kind} identity mismatch")
                output = workdir / f"{kind}.xml"
                outputs.append(output)
                output.write_bytes(body)
                artifacts.append(Artifact(kind, "application/xml", output, {
                    "source_id": self.source_id,
                    "producer": "Meteorological Service of Canada aviation IWXXM relay",
                    "product": kind,
                    "selection": candidate.detail["selection"],
                    "schema": "IWXXM 3.0 with Canadian extension observed in retained document",
                    "field_disposition": "all native elements and attributes retained; none canonically interpreted",
                    **shape,
                    "acquisition": {"listings": listings.get(kind), "document": receipt},
                    "upstream_sha256": receipt["body_sha256"],
                    "artifact_sha256": receipt["body_sha256"],
                    "licence": "unresolved; public HTTPS access is not treated as redistribution permission",
                    "quality": validation.as_quality(),
                    "source_qc": {"status": "unknown"},
                    "operational": False,
                    "adapter_version": self.adapter_version,
                    **declared_classes(["retrieved"]),
                }))
                completions.append(datetime.fromisoformat(receipt["completed_at"]))
        except BaseException:
            for output in outputs:
                output.unlink(missing_ok=True)
            raise
        return RunResult(self.source_id, candidate.provider_run_id, None, max(completions), validation.complete,
                         validation.qc_passed, artifacts, None,
                         "native CYYT TAF and CZQX SIGMET retained; publication prohibited")


def _bulletin_inventory(body: bytes) -> dict[str, Any]:
    try:
        text = body.decode("ascii")
    except UnicodeError as error:
        raise AdapterUnavailable(f"eccc-wmo-fd-native: bulletin is not ASCII: {error}") from error
    if any(character not in "\n\r\t" and not " " <= character <= "~" for character in text):
        raise AdapterUnavailable("eccc-wmo-fd-native: bulletin contains a control character")
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    if len(lines) < 5 or len(lines) > 1024 or any(len(line) > 512 for line in lines):
        raise AdapterUnavailable("eccc-wmo-fd-native: bulletin line bounds violated")
    heading = lines[0].split()
    if len(heading) < 3 or not re.fullmatch(r"FDCN0[123]", heading[0]) or heading[1] != "CWAO":
        raise AdapterUnavailable("eccc-wmo-fd-native: bulletin heading identity mismatch")
    selected = {}
    for label in ("YYT", "WPM"):
        indexes = [index for index, line in enumerate(lines) if line.startswith(label + " ")]
        if len(indexes) != 1:
            raise AdapterUnavailable(f"eccc-wmo-fd-native: expected one {label} row")
        index = indexes[0]
        row_lines = [lines[index]]
        if label == "WPM":
            if index + 1 >= len(lines) or not lines[index + 1].startswith("    "):
                raise AdapterUnavailable("eccc-wmo-fd-native: WPM coordinate row lacks its value line")
            row_lines.append(lines[index + 1])
        selected[label] = {"raw_lines": row_lines, "tokens": " ".join(row_lines).split()}
    return {
        "line_count": len(lines),
        "line_inventory": [
            {"line": index, "first_token": line.split()[0], "token_count": len(line.split()),
             "disposition": "retrieved_uninterpreted"}
            for index, line in enumerate(lines, 1)
        ],
        "selected_native_rows": selected,
        "altitude_header_raw": next(line for line in lines if "3000" in line and "18000" in line),
    }


class ECCCWMOFDBulletinNativeAdapter:
    source_id = "eccc-wmo-fd-native"
    adapter_version = "eccc-wmo-fd-native-v1"

    def __init__(self, client: PoliteClient | None = None, *, archive: str = BULLETIN_ARCHIVE,
                 day: str | None = None) -> None:
        self._client = client or PoliteClient()
        self._archive = archive.rstrip("/")
        self._day = day

    def discover(self, window: FetchWindow) -> list[RunCandidate]:
        day = self._day or window.now.astimezone(UTC).strftime("%Y%m%d")
        root = f"{self._archive}/{day}/WXO-DD/bulletins/alphanumeric/{day}/FD/CWAO/"
        names, root_receipt = _listing(self._client, root, self.source_id)
        hours = sorted(name for name in names if re.fullmatch(r"\d{2}/", name))
        if not hours or len(hours) > MAX_HOURS:
            raise AdapterUnavailable(f"{self.source_id}: expected 1..{MAX_HOURS} UTC hour directories")
        found: list[tuple[str, str]] = []
        receipts = [root_receipt]
        for hour in hours:
            hour_url = root + hour
            documents, receipt = _listing(self._client, hour_url, self.source_id)
            receipts.append(receipt)
            found.extend((name, hour_url + name) for name in documents if _FD_NAME.fullmatch(name))
        selected: list[dict[str, str]] = []
        for period in ("01", "02", "03"):
            matches = [(name, url) for name, url in found if _FD_NAME.fullmatch(name).group("period") == period]
            if matches:
                latest_stamp = max(_FD_NAME.fullmatch(item[0]).group("stamp") for item in matches)
                latest = [item for item in matches if _FD_NAME.fullmatch(item[0]).group("stamp") == latest_stamp]
                if len(latest) != 1:
                    raise AdapterUnavailable(f"{self.source_id}: ambiguous FDCN{period} amendment state")
                name, url = latest[0]
                selected.append({"period": period, "name": name, "url": url})
        if len(selected) != MAX_BULLETINS:
            raise AdapterUnavailable(f"{self.source_id}: incomplete FDCN01/02/03 family")
        return [RunCandidate(f"cwao-fd-{day}", None, [item["url"] for item in selected], {
            "products": selected,
            "listing_receipts": receipts,
            "selection": {
                "station": "YYT (St. John's aviation anchor)",
                "grid_point": "WPM 47N 49W",
                "evidence_box": [45.0, -58.0, 50.5, -46.0],
            },
        })]

    def fetch(self, candidate: RunCandidate, _window: FetchWindow, workdir: Path) -> RunResult:
        products = candidate.detail.get("products")
        if not isinstance(products, list) or len(products) != MAX_BULLETINS:
            raise AdapterUnavailable(f"{self.source_id}: incomplete candidate")
        validation = unresolved_manifest_validation(
            self.source_id,
            "FD code semantics, units, quality, licence, manifest, and API contract are unresolved",
        )
        workdir.mkdir(parents=True, exist_ok=True)
        artifacts: list[Artifact] = []
        outputs: list[Path] = []
        completions: list[datetime] = []
        try:
            for product in products:
                if not isinstance(product, dict) or product.get("period") not in {"01", "02", "03"}:
                    raise AdapterUnavailable(f"{self.source_id}: invalid product selection")
                body, receipt = _get(self._client, str(product["url"]), MAX_BULLETIN, self.source_id)
                inventory = _bulletin_inventory(body)
                period = str(product["period"])
                if not body.startswith(f"FDCN{period} CWAO ".encode("ascii")):
                    raise AdapterUnavailable(f"{self.source_id}: period {period} identity mismatch")
                output = workdir / f"fdcn{period}.txt"
                outputs.append(output)
                output.write_bytes(body)
                artifacts.append(Artifact(f"fdcn{period}", "text/plain", output, {
                    "source_id": self.source_id,
                    "producer": "CWAO bulletin issuer via Meteorological Service of Canada Datamart",
                    "product": f"FDCN{period}",
                    "selection": candidate.detail["selection"],
                    "field_disposition": "all lines retained; YYT and WPM rows selected without decoding",
                    **inventory,
                    "acquisition": {"listings": candidate.detail.get("listing_receipts"), "document": receipt},
                    "upstream_sha256": receipt["body_sha256"],
                    "artifact_sha256": receipt["body_sha256"],
                    "licence": "unresolved; public HTTPS access is not treated as redistribution permission",
                    "quality": validation.as_quality(),
                    "source_qc": {"status": "unknown"},
                    "operational": False,
                    "adapter_version": self.adapter_version,
                    **declared_classes(["retrieved"]),
                }))
                completions.append(datetime.fromisoformat(receipt["completed_at"]))
        except BaseException:
            for output in outputs:
                output.unlink(missing_ok=True)
            raise
        return RunResult(self.source_id, candidate.provider_run_id, None, max(completions), validation.complete,
                         validation.qc_passed, artifacts, None,
                         "native FDCN bulletins retained; values remain uninterpreted and publication prohibited")
