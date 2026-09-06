from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from ingest.contract import AdapterUnavailable, FetchWindow
from ingest.experimental.eccc_wmo_aviation import (
    ECCCIWXXMAviationNativeAdapter,
    ECCCWMOFDBulletinNativeAdapter,
    MAX_IWXXM,
)
from ingest.http import MaxBytesExceeded, PoliteClient, RetriesExhausted, USER_AGENT
from ingest.registry import get_adapter

UTC = timezone.utc
NOW = datetime(2026, 9, 6, 6, tzinfo=UTC)
WINDOW = FetchWindow(NOW)
COMPLETED = datetime(2026, 9, 6, 6, 1, 2, 345678, tzinfo=UTC)
TAF_NAME = "A_LTCN38CWAO060500_C_CWAO_20260906050000.xml"
SIGMET_NAME = "A_LSCN27CWAO060320_C_CWAO_20260906032055.xml"
TAF = b'''<iwxxm:TAF xmlns:iwxxm="http://icao.int/iwxxm/3.0" xmlns:gml="http://www.opengis.net/gml/3.2" xmlns:aixm="http://www.aixm.aero/schema/5.1.1" reportStatus="NORMAL"><iwxxm:issueTime><gml:TimeInstant><gml:timePosition>2026-09-06T05:40:00Z</gml:timePosition></gml:TimeInstant></iwxxm:issueTime><iwxxm:aerodrome><aixm:AirportHeliport><aixm:timeSlice><aixm:AirportHeliportTimeSlice><aixm:locationIndicatorICAO>CYYT</aixm:locationIndicatorICAO></aixm:AirportHeliportTimeSlice></aixm:timeSlice></aixm:AirportHeliport></iwxxm:aerodrome><iwxxm:baseForecast><iwxxm:MeteorologicalAerodromeForecast><iwxxm:prevailingVisibility uom="m">9600</iwxxm:prevailingVisibility></iwxxm:MeteorologicalAerodromeForecast></iwxxm:baseForecast></iwxxm:TAF>'''
SIGMET = b'''<iwxxm:SIGMET xmlns:iwxxm="http://icao.int/iwxxm/3.0" xmlns:gml="http://www.opengis.net/gml/3.2" xmlns:aixm="http://www.aixm.aero/schema/5.1.1" isCancelReport="true"><iwxxm:issueTime><gml:TimeInstant><gml:timePosition>2026-09-06T03:20:00.000Z</gml:timePosition></gml:TimeInstant></iwxxm:issueTime><iwxxm:issuingAirTrafficServicesUnit><aixm:Unit><aixm:timeSlice><aixm:UnitTimeSlice><aixm:designator>CZQX</aixm:designator></aixm:UnitTimeSlice></aixm:timeSlice></aixm:Unit></iwxxm:issuingAirTrafficServicesUnit><iwxxm:sequenceNumber>K2</iwxxm:sequenceNumber></iwxxm:SIGMET>'''
_OPEN = b'<collect:MeteorologicalBulletin xmlns:collect="http://def.wmo.int/collect/2014"><collect:meteorologicalInformation>'
_CLOSE = b'</collect:meteorologicalInformation></collect:MeteorologicalBulletin>'
TAF = _OPEN + TAF + _CLOSE
SIGMET = _OPEN + SIGMET + _CLOSE


def listing(*names: str) -> bytes:
    return ("<html>" + "".join(f'<a href="{name}">{name}</a>' for name in names) + "</html>").encode()


def client(handler) -> PoliteClient:
    result = PoliteClient(min_host_interval_seconds=0, attempts=1)
    result._client = httpx.Client(transport=httpx.MockTransport(handler), headers={"User-Agent": USER_AGENT})
    return result


def iwxxm_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path.endswith("/taf/cwao/") or path.endswith("/sigmet/czqx/"):
        return httpx.Response(200, content=listing("05/"))
    if path.endswith("/taf/cwao/05/"):
        return httpx.Response(200, content=listing(TAF_NAME))
    if path.endswith("/sigmet/czqx/05/"):
        return httpx.Response(200, content=listing(SIGMET_NAME))
    if path.endswith(TAF_NAME):
        return httpx.Response(200, content=TAF, headers={"etag": "taf-etag"})
    if path.endswith(SIGMET_NAME):
        return httpx.Response(200, content=SIGMET, headers={"etag": "sigmet-etag"})
    raise AssertionError(path)


def bulletin(period: str) -> bytes:
    return (f"FDCN{period} CWAO 060330\n"
            "FCST BASED ON 060000 DATA VALID 061200 FOR USE 09-18\n"
            "    3000 6000    9000    12000   18000\n"
            "YYT 1047 1323+09 1317+06 1515+01 1426-10\n"
            "WPM 47N  49W\n"
            "    1158 1817+11 1512+08 2015+03 1916-10\n").encode("ascii")


def fd_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path.endswith("/FD/CWAO/"):
        return httpx.Response(200, content=listing("02/"))
    if path.endswith("/FD/CWAO/02/"):
        return httpx.Response(200, content=listing(
            "FDCN01_CWAO_060320___49601", "FDCN02_CWAO_060330___21020", "FDCN03_CWAO_060330___32484"))
    for period in ("01", "02", "03"):
        if f"FDCN{period}_" in path:
            return httpx.Response(200, content=bulletin(period), headers={"last-modified": "native"})
    raise AssertionError(path)


def test_iwxxm_retains_exact_documents_full_shape_headers_and_completion(tmp_path: Path) -> None:
    http = client(iwxxm_handler)
    original = http.get_bytes_with_headers_completed
    http.get_bytes_with_headers_completed = lambda url, *, max_bytes, headers: (*original(url, max_bytes=max_bytes, headers=headers)[:2], COMPLETED)
    adapter = ECCCIWXXMAviationNativeAdapter(http, base_url="https://fixture.invalid/iwxxm")
    candidate = adapter.discover(WINDOW)[0]
    result = adapter.fetch(candidate, WINDOW, tmp_path)
    assert not result.complete and result.retrieved_at == COMPLETED
    assert [artifact.payload_path.read_bytes() for artifact in result.artifacts] == [TAF, SIGMET]
    taf, sigmet = [artifact.provenance for artifact in result.artifacts]
    assert taf["element_qname_counts"]["{http://icao.int/iwxxm/3.0}TAF"] == 1
    assert taf["attribute_qname_counts"]["uom"] == 1
    assert taf["acquisition"]["document"]["headers"]["etag"] == "taf-etag"
    assert taf["acquisition"]["document"]["completed_at"] == COMPLETED.isoformat()
    assert sigmet["source_qc"]["status"] == "unknown"
    assert all(item["operational"] is False for item in (taf, sigmet))


def test_fd_retains_all_selected_bulletins_and_uninterpreted_rows(tmp_path: Path) -> None:
    adapter = ECCCWMOFDBulletinNativeAdapter(client(fd_handler), archive="https://fixture.invalid", day="20260906")
    result = adapter.fetch(adapter.discover(WINDOW)[0], WINDOW, tmp_path)
    assert not result.complete and len(result.artifacts) == 3
    for index, artifact in enumerate(result.artifacts, 1):
        assert artifact.payload_path.read_bytes() == bulletin(f"0{index}")
        provenance = artifact.provenance
        assert provenance["selected_native_rows"]["YYT"]["tokens"][0] == "YYT"
        assert provenance["selected_native_rows"]["WPM"]["raw_lines"] == [
            "WPM 47N  49W", "    1158 1817+11 1512+08 2015+03 1916-10"]
        assert provenance["line_count"] == 6
        assert len(provenance["line_inventory"]) == provenance["line_count"]
        assert provenance["source_qc"]["status"] == "unknown"


@pytest.mark.parametrize("error", [
    MaxBytesExceeded("large"),
    RetriesExhausted("retries"),
    httpx.ConnectError("transport"),
    httpx.HTTPStatusError("status", request=httpx.Request("GET", "https://fixture.invalid"),
                          response=httpx.Response(503)),
])
def test_iwxxm_network_failures_are_unavailable_and_clean(tmp_path: Path, error: Exception) -> None:
    class FailingSecondDocument:
        def __init__(self) -> None:
            self.documents = 0

        def get_bytes_with_headers_completed(self, url: str, *, max_bytes: int, headers):
            if url.endswith("/"):
                if url.endswith("/taf/cwao/") or url.endswith("/sigmet/czqx/"):
                    return listing("05/"), {}, COMPLETED
                return listing(TAF_NAME if "/taf/" in url else SIGMET_NAME), {}, COMPLETED
            self.documents += 1
            if self.documents == 2:
                raise error
            return TAF, {}, COMPLETED

    adapter = ECCCIWXXMAviationNativeAdapter(FailingSecondDocument(), base_url="https://fixture.invalid/iwxxm")
    candidate = adapter.discover(WINDOW)[0]
    with pytest.raises(AdapterUnavailable, match="bounded request unavailable"):
        adapter.fetch(candidate, WINDOW, tmp_path)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("body, message", [
    (b"<!DOCTYPE x [<!ENTITY e 'bad'>]><TAF>&e;</TAF>", "external/entity"),
    (b"<broken>", "malformed XML"),
    (TAF.replace(b"2026-09-06T05:40:00Z", b"2026-09-06T05:40:00"), "no aware native timePosition"),
])
def test_iwxxm_invalid_xml_fails_closed(tmp_path: Path, body: bytes, message: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        response = iwxxm_handler(request)
        if request.url.path.endswith(TAF_NAME):
            return httpx.Response(200, content=body)
        return response

    adapter = ECCCIWXXMAviationNativeAdapter(client(handler), base_url="https://fixture.invalid/iwxxm")
    with pytest.raises(AdapterUnavailable, match=message):
        adapter.fetch(adapter.discover(WINDOW)[0], WINDOW, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_iwxxm_oversize_and_partial_writes_clean(tmp_path: Path, monkeypatch) -> None:
    def oversized(request: httpx.Request) -> httpx.Response:
        response = iwxxm_handler(request)
        if request.url.path.endswith(TAF_NAME):
            return httpx.Response(200, content=b"x" * (MAX_IWXXM + 1))
        return response

    adapter = ECCCIWXXMAviationNativeAdapter(client(oversized), base_url="https://fixture.invalid/iwxxm")
    with pytest.raises(AdapterUnavailable, match="bounded request unavailable"):
        adapter.fetch(adapter.discover(WINDOW)[0], WINDOW, tmp_path)
    original = Path.write_bytes

    def partial(path: Path, data: bytes):
        original(path, data[:7])
        raise OSError("partial")

    adapter = ECCCIWXXMAviationNativeAdapter(client(iwxxm_handler), base_url="https://fixture.invalid/iwxxm")
    candidate = adapter.discover(WINDOW)[0]
    monkeypatch.setattr(Path, "write_bytes", partial)
    with pytest.raises(OSError, match="partial"):
        adapter.fetch(candidate, WINDOW, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_iwxxm_refuses_uncontracted_taf_amendment_precedence() -> None:
    amended = "A_LTCN38CWAO060500AAA_C_CWAO_20260906050001.xml"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/taf/cwao/") or request.url.path.endswith("/sigmet/czqx/"):
            return httpx.Response(200, content=listing("05/"))
        if request.url.path.endswith("/taf/cwao/05/"):
            return httpx.Response(200, content=listing(TAF_NAME, amended))
        return httpx.Response(200, content=listing(SIGMET_NAME))

    adapter = ECCCIWXXMAviationNativeAdapter(client(handler), base_url="https://fixture.invalid/iwxxm")
    with pytest.raises(AdapterUnavailable, match="amendment/correction precedence"):
        adapter.discover(WINDOW)


def test_fd_malformed_or_geographically_incomplete_fails_closed(tmp_path: Path) -> None:
    def bad(request: httpx.Request) -> httpx.Response:
        response = fd_handler(request)
        if "FDCN01_" in request.url.path:
            return httpx.Response(200, content=bulletin("01").replace(b"WPM 47N  49W\n", b""))
        return response

    adapter = ECCCWMOFDBulletinNativeAdapter(client(bad), archive="https://fixture.invalid", day="20260906")
    with pytest.raises(AdapterUnavailable, match="expected one WPM row"):
        adapter.fetch(adapter.discover(WINDOW)[0], WINDOW, tmp_path)
    assert list(tmp_path.iterdir()) == []
    assert get_adapter("eccc-iwxxm-aviation-native") is None
    assert get_adapter("eccc-wmo-fd-native") is None


def test_fd_requires_complete_three_period_family() -> None:
    def partial(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/FD/CWAO/"):
            return httpx.Response(200, content=listing("02/"))
        return httpx.Response(200, content=listing("FDCN01_CWAO_060320___49601"))

    adapter = ECCCWMOFDBulletinNativeAdapter(client(partial), archive="https://fixture.invalid", day="20260906")
    with pytest.raises(AdapterUnavailable, match="incomplete FDCN01/02/03 family"):
        adapter.discover(WINDOW)


def test_fd_transport_completion_and_partial_write_cleanup(tmp_path: Path, monkeypatch) -> None:
    http = client(fd_handler)
    original_read = http.get_bytes_with_headers_completed
    http.get_bytes_with_headers_completed = lambda url, *, max_bytes, headers: (
        *original_read(url, max_bytes=max_bytes, headers=headers)[:2], COMPLETED)
    adapter = ECCCWMOFDBulletinNativeAdapter(http, archive="https://fixture.invalid", day="20260906")
    candidate = adapter.discover(WINDOW)[0]
    result = adapter.fetch(candidate, WINDOW, tmp_path)
    assert result.retrieved_at == COMPLETED
    assert all(a.provenance["acquisition"]["document"]["completed_at"] == COMPLETED.isoformat()
               for a in result.artifacts)
    for path in tmp_path.iterdir():
        path.unlink()
    original_write = Path.write_bytes
    writes = 0

    def partial_second(path: Path, data: bytes):
        nonlocal writes
        writes += 1
        if writes == 2:
            original_write(path, data[:7])
            raise OSError("partial FD write")
        return original_write(path, data)

    monkeypatch.setattr(Path, "write_bytes", partial_second)
    with pytest.raises(OSError, match="partial FD write"):
        adapter.fetch(candidate, WINDOW, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_xml_inventory_retains_every_path_attribute_and_text(tmp_path: Path) -> None:
    adapter = ECCCIWXXMAviationNativeAdapter(client(iwxxm_handler), base_url="https://fixture.invalid/iwxxm")
    result = adapter.fetch(adapter.discover(WINDOW)[0], WINDOW, tmp_path)
    for artifact in result.artifacts:
        inventory = artifact.provenance["native_element_inventory"]
        assert len(inventory) == sum(artifact.provenance["element_qname_counts"].values())
        assert all(set(row) == {"path", "qname", "attributes", "text"} for row in inventory)
    taf_rows = result.artifacts[0].provenance["native_element_inventory"]
    assert any(row["text"] == "CYYT" for row in taf_rows)
    assert any(row["attributes"] for row in taf_rows)
