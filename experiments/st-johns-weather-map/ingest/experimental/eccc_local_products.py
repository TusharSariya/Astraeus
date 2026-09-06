"""Bounded acquisition of native ECCC partner SWOB and city XML products.

The documents are retained byte-for-byte for schema and provenance evidence.
No native element is promoted to a canonical field while the partner licences,
field mappings, forecast periods, and QC meanings lack an accepted contract.
"""
from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

import httpx

from ingest.contract import AdapterUnavailable, Artifact, DiscoveryBounds, FetchWindow, ResourceBounds, RunCandidate, RunResult
from ingest.http import MaxBytesExceeded, PoliteClient, RetriesExhausted, parse_directory_listing
from ingest.manifest import declared_classes, unresolved_manifest_validation

UTC = timezone.utc
PARTNER_BASE = "https://dd.weather.gc.ca/today/observations/swob-ml/partners"
CITY_BASE = "https://dd.weather.gc.ca/today/citypage_weather/NL"
METNOTES_URL = "https://dd.weather.gc.ca/today/metnotes/"
MAX_LISTING = 256 * 1024
MAX_XML = 128 * 1024
HEADERS = ("content-type", "content-length", "etag", "last-modified", "date")
PARTNER_STATIONS = (
    ("nl-water", "nlencl0001"), ("nl-water", "nlencl0013"), ("nl-water", "nlencl0015"),
    ("nl-firewx", "011"), ("nl-firewx", "014"), ("nl-firewx", "015"),
)
_SWOB_NAME = re.compile(r"^\d{4}-\d{2}-\d{2}-\d{4}-[a-z0-9-]+-AUTO-swob\.xml$")
_CITY_NAME = re.compile(r"^(?P<stamp>\d{8}T\d{6}\.\d+)Z_MSC_CitypageWeather_s0000280_en\.xml$")


def _receipt(url: str, body: bytes, headers: Mapping[str, str], completed: datetime) -> dict[str, Any]:
    lower = {str(k).lower(): str(v) for k, v in headers.items()}
    return {"url": url, "body_bytes": len(body), "body_sha256": hashlib.sha256(body).hexdigest(),
            "completed_at": completed.isoformat(), "headers": {k: lower[k] for k in HEADERS if k in lower}}


def _get(client: PoliteClient, url: str, cap: int, source: str) -> tuple[bytes, dict[str, Any]]:
    try:
        body, headers = client.get_bytes_with_headers(url, max_bytes=cap)
        completed = datetime.now(UTC)
    except (MaxBytesExceeded, RetriesExhausted, httpx.HTTPError, OSError, ValueError) as error:
        raise AdapterUnavailable(f"{source}: bounded request unavailable: {error}") from error
    return body, _receipt(url, body, headers, completed)


def _xml(body: bytes, source: str) -> ET.Element:
    if b"<!DOCTYPE" in body.upper() or b"<!ENTITY" in body.upper():
        raise AdapterUnavailable(f"{source}: declarations with external/entity semantics are refused")
    try:
        return ET.fromstring(body)
    except ET.ParseError as error:
        raise AdapterUnavailable(f"{source}: malformed XML: {error}") from error


def _inventory(root: ET.Element) -> list[dict[str, Any]]:
    rows=[]
    def visit(element: ET.Element, path: str) -> None:
        tag=element.tag.rsplit("}",1)[-1]
        here=f"{path}/{tag}"
        name=element.attrib.get("name")
        semantics = {
            key: value for key, value in element.attrib.items()
            if key in {"units", "unitType", "period", "textForecastName", "code", "category", "type", "language"}
        }
        # SWOB identifies values by ``name`` attributes while Citypage uses
        # element tags. Inventory both shapes so an unselected native field is
        # visible rather than silently disappearing from the disposition.
        if name or len(element) == 0 or semantics:
            rows.append({"path": here, "tag": tag, "name": name,
                         "uom": element.attrib.get("uom"), "attribute_names": sorted(element.attrib),
                         "has_value": "value" in element.attrib, "has_text": bool((element.text or "").strip()),
                         "native_semantics": semantics,
                         "native_code": (element.text or "").strip() if tag in {"iconCode", "index"} else None,
                         "qualifiers": [q.attrib.get("name") for q in element if q.attrib.get("name")]})
        seen: dict[str, int] = {}
        for child in element:
            child_tag=child.tag.rsplit("}",1)[-1]
            seen[child_tag]=seen.get(child_tag,0)+1
            visit(child,f"{here}[{child_tag}:{seen[child_tag]}]")
    visit(root,"")
    return rows


class ECCCPartnerSWOBNativeAdapter:
    source_id = "eccc-swob-partners-native"
    adapter_version = "eccc-swob-partners-native-v1"

    def __init__(self, client: PoliteClient | None = None, *, base_url: str = PARTNER_BASE, day: str | None = None) -> None:
        self._client=client or PoliteClient(); self._base=base_url.rstrip("/"); self._day=day

    def operation_bounds(self, _window: FetchWindow) -> ResourceBounds:
        return ResourceBounds(store_bytes=len(PARTNER_STATIONS)*MAX_XML, filesystem_bytes=len(PARTNER_STATIONS)*MAX_XML,
                              margin_bytes=len(PARTNER_STATIONS)*4096,
                              received_bytes=len(PARTNER_STATIONS)*(MAX_LISTING+MAX_XML))
    def discovery_bounds(self, window: FetchWindow) -> DiscoveryBounds: return DiscoveryBounds(self.operation_bounds(window).received_bytes)
    def resource_bounds(self, _candidate: RunCandidate, window: FetchWindow) -> ResourceBounds: return self.operation_bounds(window)

    def discover(self, window: FetchWindow) -> list[RunCandidate]:
        day=self._day or window.now.strftime("%Y%m%d"); products=[]; receipts=[]
        for partner,station in PARTNER_STATIONS:
            url=f"{self._base}/{partner}/{day}/{station}/"
            body,receipt=_get(self._client,url,MAX_LISTING,self.source_id)
            try: names=parse_directory_listing(body.decode("utf-8",errors="strict"),suffixes=(".xml",))
            except (UnicodeError,ValueError) as error: raise AdapterUnavailable(f"{self.source_id}: invalid listing: {error}") from error
            matching=[n for n in names if _SWOB_NAME.fullmatch(n)]
            if not matching: raise AdapterUnavailable(f"{self.source_id}: no SWOB XML for {partner}/{station}")
            name=matching[-1]; products.append({"partner":partner,"station_dir":station,"name":name,"url":url+name}); receipts.append(receipt)
        digest=hashlib.sha256("\n".join(p["url"] for p in products).encode()).hexdigest()[:12]
        return [RunCandidate(f"partner-swob-{day}-{digest}",None,[p["url"] for p in products],{"products":products,"listing_receipts":receipts})]

    def fetch(self,candidate:RunCandidate,_window:FetchWindow,workdir:Path)->RunResult:
        products=candidate.detail.get("products"); listings=candidate.detail.get("listing_receipts")
        if (not isinstance(products,list) or len(products)!=len(PARTNER_STATIONS)
                or not isinstance(listings,list) or len(listings)!=len(PARTNER_STATIONS)
                or not all(isinstance(item,dict) for item in products)
                or not all(isinstance(item,dict) for item in listings)):
            raise AdapterUnavailable(f"{self.source_id}: incomplete candidate")
        validation=unresolved_manifest_validation(self.source_id,"partner fields, QC codes, and redistribution contract are not accepted")
        artifacts=[]; completions=[]; workdir.mkdir(parents=True,exist_ok=True)
        try:
            for index,product in enumerate(products):
                body,receipt=_get(self._client,str(product["url"]),MAX_XML,self.source_id); root=_xml(body,self.source_id)
                values={e.attrib.get("name"):e.attrib.get("value") for e in root.iter() if e.attrib.get("name")}
                if root.tag.rsplit("}",1)[-1]!="ObservationCollection" or values.get("stn_id","").lower()!=str(product["station_dir"]).lower():
                    raise AdapterUnavailable(f"{self.source_id}: station/root identity mismatch")
                stamp=values.get("date_tm");
                try: observed=datetime.fromisoformat(str(stamp).replace("Z","+00:00"))
                except ValueError as error: raise AdapterUnavailable(f"{self.source_id}: invalid observation time") from error
                path=workdir/f"partner-{product['partner']}-{product['station_dir']}.xml"; path.write_bytes(body)
                artifacts.append(Artifact(f"partner-{product['partner']}-{product['station_dir']}","application/xml",path,{
                    "source_id":self.source_id,"producer":"Environment and Climate Change Canada partner SWOB relay",
                    "partner":product["partner"],"station_id":values.get("stn_id"),"station_name":values.get("stn_nam"),
                    "provider_id":values.get("msc_id"),"provider_attribution":values.get("data_attrib_not"),
                    "observed_at":observed.isoformat(),"native_element_inventory":_inventory(root),
                    "acquisition":{"listing":listings[index],"document":receipt},"upstream_sha256":receipt["body_sha256"],
                    "artifact_sha256":receipt["body_sha256"],"quality":validation.as_quality(),"source_qc":{"status":"unknown","native_qualifiers_preserved":True},
                    "operational":False,"adapter_version":self.adapter_version,**declared_classes(["uncalibrated_observation"])}))
                completions.append(datetime.fromisoformat(receipt["completed_at"]))
        except BaseException:
            for a in artifacts:a.payload_path.unlink(missing_ok=True)
            raise
        return RunResult(self.source_id,candidate.provider_run_id,None,max(completions),validation.complete,validation.qc_passed,artifacts,None,
                         "six named Avalon partner SWOB documents retained; canonical publication prohibited")


class ECCCCitypageNativeAdapter:
    source_id="eccc-citypage-st-johns-native"; adapter_version="eccc-citypage-st-johns-native-v1"
    def __init__(self,client:PoliteClient|None=None,*,base_url:str=CITY_BASE): self._client=client or PoliteClient();self._base=base_url.rstrip("/")
    def operation_bounds(self,_window): return ResourceBounds(MAX_XML,MAX_XML,4096,2*MAX_LISTING+MAX_XML)
    def discovery_bounds(self,window): return DiscoveryBounds(self.operation_bounds(window).received_bytes)
    def resource_bounds(self,_candidate,window): return self.operation_bounds(window)
    def discover(self,window):
        found=[]; receipts=[]
        for moment in (window.now,window.now-timedelta(hours=1)):
            url=f"{self._base}/{moment:%H}/"; body,receipt=_get(self._client,url,MAX_LISTING,self.source_id);receipts.append(receipt)
            try:
                names=parse_directory_listing(body.decode("utf-8",errors="strict"),suffixes=(".xml",))
            except (UnicodeError,ValueError) as error:
                raise AdapterUnavailable(f"{self.source_id}: invalid city listing: {error}") from error
            found.extend((n,url+n) for n in names if _CITY_NAME.fullmatch(n))
        if not found: raise AdapterUnavailable(f"{self.source_id}: no St. John's English city XML in current/previous hour")
        name,url=max(found,key=lambda x:x[0]); stamp=datetime.strptime(_CITY_NAME.fullmatch(name)["stamp"],"%Y%m%dT%H%M%S.%f").replace(tzinfo=UTC)
        return [RunCandidate(f"citypage-s0000280-{stamp.isoformat()}",stamp,[url],{"name":name,"listing_receipts":receipts})]
    def fetch(self,candidate,_window,workdir):
        listings=candidate.detail.get("listing_receipts")
        if len(candidate.urls)!=1 or not isinstance(listings,list) or len(listings)!=2 or not all(isinstance(item,dict) for item in listings):
            raise AdapterUnavailable(f"{self.source_id}: incomplete candidate")
        body,receipt=_get(self._client,candidate.urls[0],MAX_XML,self.source_id);root=_xml(body,self.source_id)
        names=[e for e in root.iter() if e.tag.rsplit("}",1)[-1]=="name"]
        if root.tag.rsplit("}",1)[-1]!="siteData" or not any(e.attrib.get("code")=="s0000280" for e in names): raise AdapterUnavailable(f"{self.source_id}: city document identity mismatch")
        validation=unresolved_manifest_validation(self.source_id,"city forecast periods, coded conditions, advisories, and UV fields lack an accepted native contract")
        workdir.mkdir(parents=True,exist_ok=True);path=workdir/"citypage-s0000280-en.xml";path.write_bytes(body)
        artifact=Artifact("citypage-s0000280-en","application/xml",path,{"source_id":self.source_id,"producer":"Environment and Climate Change Canada","site_code":"s0000280","language":"en","issue_time":candidate.run_time.isoformat(),"native_element_inventory":_inventory(root),"acquisition":{"listings":listings,"document":receipt},"upstream_sha256":receipt["body_sha256"],"artifact_sha256":receipt["body_sha256"],"quality":validation.as_quality(),"source_qc":{"status":"unknown"},"operational":False,"adapter_version":self.adapter_version,**declared_classes(["retrieved"])})
        return RunResult(self.source_id,candidate.provider_run_id,candidate.run_time,datetime.fromisoformat(receipt["completed_at"]),validation.complete,validation.qc_passed,[artifact],None,"native city XML retained; publication prohibited")


def discover_metnotes(client:PoliteClient|None=None,url:str=METNOTES_URL)->None:
    body,_receipt_data=_get(client or PoliteClient(),url,MAX_LISTING,"eccc-metnotes")
    names=parse_directory_listing(body.decode("utf-8",errors="strict"),suffixes=(".json",))
    if not names: raise AdapterUnavailable("eccc-metnotes: observed empty official directory; no payload fetched")
    raise AdapterUnavailable("eccc-metnotes: payload reappeared but complete size/schema bounds require a new reviewed capture before fetch")
