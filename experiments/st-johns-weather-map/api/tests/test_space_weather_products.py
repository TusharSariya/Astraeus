"""`/space-weather/products`: every published space-weather series read back.

Built on real zipped-Zarr artifacts written by the shared seam and read through
the real ``LiveStore.read_series`` path (the ``ZipStore`` double swaps only the
object store for files on disk). Under test: series are listed by provenance
not by name, a platform axis is served per label, an issued product's
freshness is the retrieval's age, a reprocessed relay names both parties and
is not display primary, an unreadable artifact is reported as skipped, and
fixture mode answers unavailable.
"""

from __future__ import annotations

import sys as _sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy
import xarray
from fastapi.testclient import TestClient

import weather_api.app  # noqa: F401
from ingest.grib import write_zarr
from ingest.space_weather import FeedReceipt, flag_attrs, platform_series_dataset, series_dataset, series_provenance, series_quality
from ingest.store import CurrentArtifact
from weather_api.app import PREFIX, app
from weather_api.space_weather_products import build_products
from tests.test_space_weather_series import ZipStore

UTC = timezone.utc
api_module = _sys.modules["weather_api.app"]
client = TestClient(app)
REFERENCE = datetime(2026, 9, 5, 20, 0, tzinfo=UTC)
RECEIPT = FeedReceipt("https://services.swpc.noaa.gov/x.json", 1234, "ab" * 32, "2026-09-05T19:50:00Z", "Sat, 05 Sep 2026 19:49:00 GMT")


def artifact(source_id: str, logical_name: str, provenance: dict, *, retrieved_at: datetime = REFERENCE - timedelta(minutes=5)) -> CurrentArtifact:
    return CurrentArtifact(
        source_id=source_id, logical_name=logical_name, revision_id=f"rev-{source_id}-{logical_name}",
        object_key=f"artifacts/{source_id}/{logical_name}", media_type="application/zarr+zip", byte_size=1,
        provenance=provenance, published_at=retrieved_at, run_time=retrieved_at, retrieved_at=retrieved_at,
        provider_run_id="run", native_crs=None,
    )


def provenance(source_id: str, product: str, scope: str, values: numpy.ndarray, *, classes=("retrieved",), intermediary=None, extra=None) -> dict:
    quality, coverage = series_quality("x", values)
    return series_provenance(
        source_id=source_id, producer="NOAA Space Weather Prediction Center" if intermediary is None else "Kyoto World Data Center for Geomagnetism",
        product=product, adapter_version="test-v1", quality=quality, coverage=coverage, evidence_classes=list(classes),
        receipts=[RECEIPT], native_resolution="planetary index (no spatial resolution)", measurement_scope=scope,
        intermediary=intermediary, extra=extra,
    )


def hp30(tmp_path: Path):
    times = [REFERENCE - timedelta(minutes=90), REFERENCE - timedelta(minutes=60), REFERENCE - timedelta(minutes=30)]
    values = numpy.array([1.0, 1.333, numpy.nan])
    dataset = series_dataset(times, {"hp30_index": (values, {"units": "dimensionless"})}, {"source": "GFZ"})
    path = tmp_path / "hp30.zarr.zip"
    write_zarr(dataset, path)
    return artifact("gfz-hp30", "hp30", provenance("gfz-hp30", "Hp30 half-hour geomagnetic index", "planetary", values, extra={"status_declared": False})), path


def goes_xray(tmp_path: Path):
    times = [REFERENCE - timedelta(minutes=2), REFERENCE - timedelta(minutes=1)]
    short = numpy.array([[4.6e-07, numpy.nan], [4.0e-07, 5.0e-07]])
    dataset = platform_series_dataset(
        times, ["18", "19"],
        {"xray_flux_short": (short, {"units": "W m-2"}), "electron_contamination_short": (numpy.array([[0.0, numpy.nan], [0.0, 1.0]]), flag_attrs(["false", "true"], long_name="contamination"))},
        {"source": "GOES"}, platform_dim="satellite",
    )
    path = tmp_path / "xray.zarr.zip"
    write_zarr(dataset, path)
    return artifact("noaa-goes-xray", "goes_xray", provenance("noaa-goes-xray", "GOES X-ray flux (1-day)", "geosynchronous", short)), path


def dst(tmp_path: Path):
    times = [REFERENCE - timedelta(hours=2), REFERENCE - timedelta(hours=1)]
    values = numpy.array([-15.0, -9.0])
    dataset = series_dataset(times, {"dst_index": (values, {"units": "nT"})}, {"source": "Kyoto via SWPC"})
    path = tmp_path / "dst.zarr.zip"
    write_zarr(dataset, path)
    block = provenance(
        "noaa-swpc-kyoto-dst", "Dst index (provisional and real-time)", "planetary", values, classes=("reprocessed",),
        intermediary={"name": "NOAA SWPC", "method": "relay"}, extra={"display_primary": False},
    )
    return artifact("noaa-swpc-kyoto-dst", "kyoto_dst", block), path


def alerts(tmp_path: Path):
    times = [REFERENCE - timedelta(days=3)]
    dataset = series_dataset(
        times,
        {"product_id": (numpy.array(["K04A"], dtype=object), {"units": "text"}), "message": (numpy.array(["ALERT: Geomagnetic K-index of 4\r\n"], dtype=object), {"units": "text"})},
        {"source": "alerts"},
    )
    path = tmp_path / "alerts.zarr.zip"
    write_zarr(dataset, path)
    return artifact("noaa-swpc-alerts", "alerts", provenance("noaa-swpc-alerts", "Space weather alert products", "issued", numpy.array([1.0]))), path


def ovation(tmp_path: Path):
    stamps = numpy.array([numpy.datetime64((REFERENCE - timedelta(minutes=10)).replace(tzinfo=None), "ns")])
    dataset = xarray.Dataset(
        {"aurora_probability": (("valid_time", "latitude", "longitude"), numpy.full((1, 2, 2), 3.0), {"units": "percent"})},
        coords={"valid_time": stamps, "latitude": [47.0, 48.0], "longitude": [-53.0, -52.0]},
    )
    path = tmp_path / "ovation.zarr.zip"
    write_zarr(dataset, path)
    return artifact("noaa-swpc-ovation", "aurora_grid", {"product": "OVATION", "native_crs": "EPSG:4326", "evidence_classes": ["retrieved"]}), path


THRESHOLDS = {"gfz-hp30": 7200, "noaa-goes-xray": 900, "noaa-swpc-kyoto-dst": 10800, "noaa-swpc-alerts": 1800}


def test_products_are_listed_by_provenance_with_scope_receipts_and_latest_values(tmp_path: Path):
    store = ZipStore([hp30(tmp_path), goes_xray(tmp_path), dst(tmp_path), alerts(tmp_path), ovation(tmp_path)])
    response = build_products(store, REFERENCE, registry_threshold=THRESHOLDS.get)
    assert response.data_mode == "live" and response.operational is False
    by_id = {(p.source_id, p.logical_name): p for p in response.products}
    # The OVATION grid is a field, not a series: absent from the listing, not skipped.
    assert ("noaa-swpc-ovation", "aurora_grid") not in by_id and response.skipped == []
    assert set(by_id) == {("gfz-hp30", "hp30"), ("noaa-goes-xray", "goes_xray"), ("noaa-swpc-kyoto-dst", "kyoto_dst"), ("noaa-swpc-alerts", "alerts")}

    hp = by_id[("gfz-hp30", "hp30")]
    assert hp.measurement_scope == "planetary" and hp.evidence_classes == ["retrieved"] and hp.display_primary is True
    assert hp.retrieval == [RECEIPT.as_dict()] and "payload" not in str(hp.retrieval)
    assert hp.record_count == 3 and hp.newest_instant == REFERENCE - timedelta(minutes=60)  # the trailing NaN is a gap
    assert hp.freshness.status == "fresh" and hp.freshness.age_seconds == 3600
    (latest,) = hp.latest
    assert latest.variable == "hp30_index" and latest.label is None and latest.value == 1.333 and latest.time == REFERENCE - timedelta(minutes=60)

    xray = by_id[("noaa-goes-xray", "goes_xray")]
    assert xray.dimensions == {"satellite": ["18", "19"]} and xray.measurement_scope == "geosynchronous"
    values = {(item.variable, item.label): (item.value, item.time) for item in xray.latest}
    assert values[("xray_flux_short", "18")] == (4.0e-07, REFERENCE - timedelta(minutes=1))
    assert values[("xray_flux_short", "19")] == (5.0e-07, REFERENCE - timedelta(minutes=1))
    assert values[("electron_contamination_short", "19")] == ("true", REFERENCE - timedelta(minutes=1))

    relay = by_id[("noaa-swpc-kyoto-dst", "kyoto_dst")]
    assert relay.evidence_classes == ["reprocessed"] and relay.intermediary == {"name": "NOAA SWPC", "method": "relay"}
    assert relay.producer.startswith("Kyoto") and relay.display_primary is False

    issued = by_id[("noaa-swpc-alerts", "alerts")]
    assert issued.newest_instant == REFERENCE - timedelta(days=3)
    assert issued.freshness.status == "fresh" and issued.freshness.age_seconds == 300  # the retrieval's age, not the alert's
    assert "retrieval" in issued.freshness_basis
    assert {item.variable: item.value for item in issued.latest}["message"] == "ALERT: Geomagnetic K-index of 4\r\n"


def test_stale_and_unreadable_products_say_so(tmp_path: Path):
    hp_artifact, hp_path = hp30(tmp_path)
    broken = artifact("noaa-swpc-kp-1m", "kp_1m", {"native_crs": "not_applicable", "product": "Kp 1m", "evidence_classes": ["retrieved"]})
    store = ZipStore([(hp_artifact, hp_path), (broken, tmp_path / "missing.zarr.zip")])
    response = build_products(store, REFERENCE, registry_threshold={"gfz-hp30": 600}.get)
    (product,) = response.products
    assert product.freshness.status == "stale" and any("served stale" in notice for notice in product.notices)
    (skipped,) = response.skipped
    assert skipped.source_id == "noaa-swpc-kp-1m" and skipped.logical_name == "kp_1m" and skipped.reason


def test_nothing_published_is_unavailable_not_empty_success(tmp_path: Path):
    response = build_products(ZipStore([]), REFERENCE, registry_threshold=lambda _id: None)
    assert response.data_mode == "unavailable" and response.products == []
    assert any("nothing is invented" in notice for notice in response.notices)


def test_unknown_threshold_is_unknown_freshness(tmp_path: Path):
    store = ZipStore([hp30(tmp_path)])
    (product,) = build_products(store, REFERENCE, registry_threshold=lambda _id: None).products
    assert product.freshness.status == "unknown" and product.freshness.age_seconds == 3600 and product.freshness.threshold_seconds is None


# --- the route ---------------------------------------------------------------


def test_route_fixture_mode_fails_closed(data_mode):
    data_mode("fixture")
    body = client.get(f"{PREFIX}/space-weather/products").json()
    assert body["data_mode"] == "unavailable" and body["products"] == [] and body["operational"] is False
    assert any("fixture" in notice for notice in body["notices"])


def test_route_malformed_mode_fails_closed(data_mode):
    data_mode("nonsense")
    body = client.get(f"{PREFIX}/space-weather/products").json()
    assert body["data_mode"] == "unavailable" and body["products"] == []


def test_route_lists_live_products_through_the_real_reader(tmp_path: Path, monkeypatch, data_mode):
    data_mode("live")
    store = ZipStore([hp30(tmp_path), dst(tmp_path)])
    monkeypatch.setattr(api_module, "live_store", lambda: store)
    body = client.get(f"{PREFIX}/space-weather/products").json()
    assert body["data_mode"] == "live" and body["operational"] is False
    ids = {item["source_id"] for item in body["products"]}
    assert ids == {"gfz-hp30", "noaa-swpc-kyoto-dst"}
    relay = next(item for item in body["products"] if item["source_id"] == "noaa-swpc-kyoto-dst")
    assert relay["evidence_classes"] == ["reprocessed"] and relay["display_primary"] is False
    assert relay["retrieval"][0]["sha256"] == "ab" * 32
    # Registry thresholds are real here: Dst is 3 hours, Hp30 whatever the record says.
    assert relay["freshness"]["threshold_seconds"] == 10800


def test_route_without_a_store_is_unavailable(monkeypatch, data_mode):
    data_mode("live")
    monkeypatch.setattr(api_module, "live_store", lambda: None)
    body = client.get(f"{PREFIX}/space-weather/products").json()
    assert body["data_mode"] == "unavailable" and "no live artifact store" in body["notices"][0]
