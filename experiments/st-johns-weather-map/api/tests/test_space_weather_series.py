"""The shared space-weather series seam: bounded receipts, feed instants,
platform axes, and the reader that serves them.

``ingest.space_weather`` is what every space-weather adapter builds on and
``LiveStore.read_series`` is what the API reads them back through, so the
two are tested together: what one writes, the other must serve exactly.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import numpy
import pytest

from ingest.contract import AdapterUnavailable
from ingest.grib import write_zarr
from ingest.http import USER_AGENT, PoliteClient
from ingest.space_weather import (
    FeedReceipt,
    fetch_json,
    flag_attrs,
    flag_or_nan,
    float_or_nan,
    parse_time,
    platform_series_dataset,
    records,
    series_dataset,
    series_provenance,
    series_quality,
)
from ingest.store import CurrentArtifact
from weather_api.store import LiveStore

UTC = timezone.utc


def mock_client(body: bytes | object, *, status: int = 200, headers: dict[str, str] | None = None) -> PoliteClient:
    raw = body if isinstance(body, bytes) else json.dumps(body).encode()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, content=raw, headers=headers or {})

    client = PoliteClient(min_host_interval_seconds=0.0, attempts=1)
    client._client = httpx.Client(transport=httpx.MockTransport(handler), headers={"User-Agent": USER_AGENT})
    return client


# --- fetch_json and receipts ---------------------------------------------


def test_fetch_json_returns_payload_and_a_receipt_without_the_payload(tmp_path: Path):
    payload = [{"time_tag": "2026-09-05T19:29:00", "bz_gsm": -1.5}]
    client = mock_client(payload, headers={"Last-Modified": "Sat, 05 Sep 2026 19:33:56 GMT"})
    parsed, receipt = fetch_json(client, "https://example.test/feed.json", max_bytes=1024, workdir=tmp_path, request_parameters={"index": "Hp30"})
    assert parsed == payload
    assert isinstance(receipt, FeedReceipt)
    assert receipt.byte_count == len(json.dumps(payload).encode())
    assert len(receipt.sha256) == 64
    assert receipt.last_modified == "Sat, 05 Sep 2026 19:33:56 GMT"
    assert receipt.captured_at.endswith("Z")
    record = receipt.as_dict()
    assert record["request_parameters"] == {"index": "Hp30"}
    assert "payload" not in record and "body" not in record
    # The scratch file never survives the call.
    assert not list(tmp_path.iterdir())


def test_fetch_json_receipt_timestamp_is_taken_after_http_completion(tmp_path: Path, monkeypatch):
    import ingest.space_weather as module

    completed: list[bool] = []

    class Client:
        def download_with_headers(self, _url, destination, *, max_bytes):
            destination.write_bytes(b'[{"time_tag":"2026-09-06T04:21:00"}]')
            completed.append(True)
            return destination.stat().st_size, {}

    class Clock:
        @staticmethod
        def now(_zone):
            assert completed == [True], "receipt time must follow the completed response"
            return datetime(2026, 9, 6, 4, 25, 2, tzinfo=UTC)

    monkeypatch.setattr(module, "datetime", Clock)
    _payload, receipt = fetch_json(Client(), "https://example.test/feed.json", max_bytes=1024, workdir=tmp_path)

    assert receipt.captured_at == "2026-09-06T04:25:02Z"


def test_fetch_json_refuses_a_body_past_the_ceiling(tmp_path: Path):
    client = mock_client(b"[" + b"1," * 600 + b"1]")
    with pytest.raises(AdapterUnavailable, match="ceiling"):
        fetch_json(client, "https://example.test/big.json", max_bytes=100, workdir=tmp_path)
    assert not list(tmp_path.iterdir())


def test_fetch_json_refuses_an_error_page_behind_200(tmp_path: Path):
    client = mock_client(b"<html>not found</html>")
    with pytest.raises(AdapterUnavailable, match="not JSON"):
        fetch_json(client, "https://example.test/dead.json", max_bytes=1024, workdir=tmp_path)


def test_fetch_json_refuses_an_empty_body_and_a_404(tmp_path: Path):
    with pytest.raises(AdapterUnavailable, match="empty body"):
        fetch_json(mock_client(b""), "https://example.test/empty.json", max_bytes=1024, workdir=tmp_path)
    with pytest.raises(AdapterUnavailable, match="unavailable"):
        fetch_json(mock_client(b"gone", status=404), "https://example.test/gone.json", max_bytes=1024, workdir=tmp_path)


# --- instants and values -------------------------------------------------


def test_parse_time_reads_the_feed_forms_and_refuses_the_rest():
    assert parse_time("2026-09-05T19:29:00") == datetime(2026, 9, 5, 19, 29, tzinfo=UTC)
    assert parse_time("2026-09-05T19:29:00Z") == datetime(2026, 9, 5, 19, 29, tzinfo=UTC)
    assert parse_time("2026-09-05 16:33:07.073") == datetime(2026, 9, 5, 16, 33, 7, 73000, tzinfo=UTC)
    assert parse_time("2026-09-05 19:34:00") == datetime(2026, 9, 5, 19, 34, tzinfo=UTC)
    assert parse_time("") is None and parse_time(None) is None and parse_time("yesterday") is None


def test_records_accepts_objects_and_header_rows():
    objects = [{"time_tag": "t", "dst": -5}, {"dst": 1}]
    assert records(objects, required=("time_tag", "dst")) == [{"time_tag": "t", "dst": -5}]
    rows = [["time_tag", "speed"], ["t", 344.7], ["short"]]
    assert records(rows, required=("time_tag",)) == [{"time_tag": "t", "speed": 344.7}]
    assert records(rows, required=("density",)) == []
    assert records({"not": "a list"}, required=()) == []


def test_values_keep_gaps_and_flags_honest():
    assert numpy.isnan(float_or_nan(None)) and numpy.isnan(float_or_nan("x")) and numpy.isnan(float_or_nan(True))
    assert float_or_nan("3.5") == 3.5
    assert numpy.isnan(flag_or_nan(None))
    assert flag_or_nan(False) == 0.0 and flag_or_nan(True) == 1.0 and flag_or_nan(-9999) == -9999.0
    attrs = flag_attrs(["ACE", "IMAP"], long_name="platform")
    assert attrs["flag_values"] == [0, 1] and attrs["flag_meanings"] == "ACE IMAP"
    with pytest.raises(ValueError):
        flag_attrs(["a"], long_name="x", values=[0, 1])


# --- datasets --------------------------------------------------------------


def test_series_dataset_refuses_duplicate_instants():
    stamp = datetime(2026, 9, 5, 19, tzinfo=UTC)
    with pytest.raises(AdapterUnavailable, match="platform axis"):
        series_dataset([stamp, stamp], {"x": (numpy.array([1.0, 2.0]), {"units": "nT"})}, {})
    with pytest.raises(AdapterUnavailable, match="at least one instant"):
        series_dataset([], {}, {})


def test_platform_dataset_shape_and_quality():
    times = [datetime(2026, 9, 5, 19, m, tzinfo=UTC) for m in range(3)]
    bz = numpy.array([[1.0, numpy.nan], [numpy.nan, numpy.nan], [2.0, 3.0]])
    dataset = platform_series_dataset(times, ["ACE", "SOLAR1"], {"bz_gsm": (bz, {"units": "nT"})}, {"source": "test"})
    assert list(dataset.dims) == ["valid_time", "spacecraft"]
    assert list(dataset.spacecraft.values) == ["ACE", "SOLAR1"]
    quality, coverage = series_quality("bz_gsm", bz)
    assert quality["status"] == "unknown" and "upstream_quality_not_interpreted" in quality["flags"]
    assert coverage["fraction"] == round(2 / 3, 4)
    empty_quality, empty_coverage = series_quality("bz_gsm", numpy.full((2, 2), numpy.nan))
    assert empty_quality["status"] == "failed" and empty_coverage["status"] == "outside"
    with pytest.raises(AdapterUnavailable, match="unique and sorted"):
        platform_series_dataset(times, ["SOLAR1", "ACE"], {"bz_gsm": (bz, {})}, {})
    with pytest.raises(AdapterUnavailable, match="does not match"):
        platform_series_dataset(times, ["ACE"], {"bz_gsm": (bz, {})}, {})


def test_series_provenance_pins_scope_and_reprocessing():
    receipt = FeedReceipt("https://example.test/f.json", 10, "0" * 64, "2026-09-05T19:00:00Z")
    quality, coverage = series_quality("dst", numpy.array([-5.0]))
    block = series_provenance(
        source_id="noaa-swpc-kyoto-dst", producer="Kyoto WDC", product="Dst", adapter_version="v1",
        quality=quality, coverage=coverage, evidence_classes=["reprocessed"], receipts=[receipt],
        native_resolution="planetary index", measurement_scope="planetary",
        intermediary={"name": "NOAA SWPC", "method": "relay"},
    )
    assert block["evidence_classes"] == ["reprocessed"] and block["intermediary"]["name"] == "NOAA SWPC"
    assert block["retrieval"] == [receipt.as_dict()] and block["measurement_scope"] == "planetary"
    with pytest.raises(ValueError, match="intermediary"):
        series_provenance(
            source_id="x", producer="p", product="q", adapter_version="v", quality=quality, coverage=coverage,
            evidence_classes=["reprocessed"], receipts=[], native_resolution="r", measurement_scope="l1",
        )
    with pytest.raises(ValueError, match="only on a reprocessed"):
        series_provenance(
            source_id="x", producer="p", product="q", adapter_version="v", quality=quality, coverage=coverage,
            evidence_classes=["retrieved"], receipts=[], native_resolution="r", measurement_scope="l1",
            intermediary={"name": "n"},
        )
    with pytest.raises(ValueError, match="scope"):
        series_provenance(
            source_id="x", producer="p", product="q", adapter_version="v", quality=quality, coverage=coverage,
            evidence_classes=["retrieved"], receipts=[], native_resolution="r", measurement_scope="nowhere",
        )


# --- read_series on what the helpers write --------------------------------


class ZipStore(LiveStore):
    """A live store over zipped-Zarr files on disk; no object store touched."""

    def __init__(self, entries: list[tuple[CurrentArtifact, Path]]) -> None:
        super().__init__(artifact_store=None, cache_dir=Path("/nonexistent"))
        self._entries = list(entries)

    def current(self):
        return [artifact for artifact, _ in self._entries]

    def _local_copy(self, artifact):
        return next(path for candidate, path in self._entries if candidate.revision_id == artifact.revision_id)

    def assert_object_store_reachable(self) -> None:
        """Files on disk stand in for the object store here."""


def artifact(source_id: str, logical_name: str) -> CurrentArtifact:
    stamp = datetime(2026, 9, 5, 19, tzinfo=UTC)
    return CurrentArtifact(
        source_id=source_id, logical_name=logical_name, revision_id=f"rev-{source_id}-{logical_name}",
        object_key=f"artifacts/{source_id}/{logical_name}", media_type="application/zarr+zip", byte_size=1,
        provenance={"product": logical_name, "evidence_classes": ["retrieved"]}, published_at=stamp,
        run_time=stamp, retrieved_at=stamp, provider_run_id="run", native_crs=None,
    )


def test_read_series_serves_a_platform_axis_per_label_and_by_selection(tmp_path: Path):
    times = [datetime(2026, 9, 5, 19, m, tzinfo=UTC) for m in range(2)]
    bz = numpy.array([[1.0, numpy.nan], [2.0, 3.0]])
    active = numpy.array([[0.0, numpy.nan], [0.0, 1.0]])
    dataset = platform_series_dataset(
        times, ["ACE", "SOLAR1"],
        {"bz_gsm": (bz, {"units": "nT"}), "active": (active, flag_attrs(["inactive", "active"], long_name="feed active flag"))},
        {"source": "test"},
    )
    path = tmp_path / "rtsw.zarr.zip"
    write_zarr(dataset, path)
    store = ZipStore([(artifact("noaa-swpc-rtsw", "solar_wind"), path)])

    series = store.read_series("noaa-swpc-rtsw", "solar_wind")
    assert series is not None
    assert series.dimensions == {"spacecraft": ["ACE", "SOLAR1"]}
    assert series.variables["bz_gsm@ACE"].values == [1.0, 2.0]
    assert series.variables["bz_gsm@SOLAR1"].values == [None, 3.0]
    assert series.variables["active@SOLAR1"].values == [None, "active"]
    assert "bz_gsm" not in series.variables

    picked = store.read_series("noaa-swpc-rtsw", "solar_wind", select={"spacecraft": "SOLAR1"})
    assert picked is not None and picked.variables["bz_gsm"].values == [None, 3.0]
    assert picked.dimensions == {"spacecraft": ["ACE", "SOLAR1"]}

    store.skipped = []
    assert store.read_series("noaa-swpc-rtsw", "solar_wind", select={"spacecraft": "DSCOVR"}) is None
    assert store.skipped and "no label 'DSCOVR'" in store.skipped[0].reason
    store.skipped = []
    assert store.read_series("noaa-swpc-rtsw", "solar_wind", select={"satellite": "19"}) is None
    assert store.skipped and "no axis satellite" in store.skipped[0].reason


def test_read_series_serves_text_values_verbatim(tmp_path: Path):
    times = [datetime(2026, 9, 5, 16, 20, tzinfo=UTC), datetime(2026, 9, 5, 16, 33, tzinfo=UTC)]
    dataset = series_dataset(
        times,
        {
            "message": (numpy.array(["WARNING: Proton\r\nValid From: x", "ALERT: Proton"], dtype=object), {"units": "text"}),
            "serial_number": (numpy.array([631.0, 368.0]), {"units": "dimensionless"}),
        },
        {"source": "alerts"},
    )
    path = tmp_path / "alerts.zarr.zip"
    write_zarr(dataset, path)
    store = ZipStore([(artifact("noaa-swpc-alerts", "alerts"), path)])
    series = store.read_series("noaa-swpc-alerts", "alerts")
    assert series is not None and series.dimensions == {}
    assert series.variables["message"].values == ["WARNING: Proton\r\nValid From: x", "ALERT: Proton"]
    assert series.variables["serial_number"].values == [631.0, 368.0]
    assert series.times == times


def test_read_series_refuses_two_platform_axes(tmp_path: Path):
    import xarray

    stamps = numpy.array([numpy.datetime64("2026-09-05T19:00", "ns")])
    dataset = xarray.Dataset(
        {"x": (("valid_time", "a", "b"), numpy.zeros((1, 1, 1)))},
        coords={"valid_time": stamps, "a": ["p"], "b": ["q"]},
    )
    path = tmp_path / "two.zarr.zip"
    write_zarr(dataset, path)
    store = ZipStore([(artifact("s", "two"), path)])
    assert store.read_series("s", "two") is None
    assert store.skipped and "at most one platform axis" in store.skipped[0].reason
