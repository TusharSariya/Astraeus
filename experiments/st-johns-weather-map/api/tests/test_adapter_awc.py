"""Unit tests for the AWC METAR/SPECI adapter."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
import numpy
import pytest
import xarray
import zarr

from ingest.adapters.awc import (
    CLOUD_COVER_FLAGS,
    FEET_TO_METRES,
    MAX_CLOUD_LAYERS,
    AWCMetarAdapter,
    PresentWeather,
    parse_cloud_cover_percent,
    parse_cloud_layers,
    parse_present_weather,
    parse_pressure_hpa,
    parse_visibility_meters,
    parse_wind_components,
)
from ingest.contract import AdapterUnavailable, FetchWindow
from ingest.http import PoliteClient, USER_AGENT

UTC = timezone.utc

SAMPLE_METAR_JSON = [
    {
        "metarId": 101,
        "icaoId": "CYYT",
        "receiptTime": "2026-08-29 14:05:00",
        "obsTime": int(datetime(2026, 8, 29, 14, 0, tzinfo=UTC).timestamp()),
        "reportTime": "2026-08-29 14:00:00",
        "temp": 18.0,
        "dewp": 17.0,
        "wdir": 180,
        "wspd": 10,
        "visib": "4",
        "altim": 1012.0,
        "slp": 1012.3,
        "qcField": 0,
        "wxString": "-SHRA BR",
        "metarType": "METAR",
        "rawOb": "METAR CYYT 291400Z 18010KT 4SM -SHRA BR OVC008 18/17 A2989",
        "cover": "OVC",
        "clouds": [{"cover": "OVC", "base": 800}],
    },
    {
        "metarId": 100,
        "icaoId": "CYYT",
        "receiptTime": "2026-08-29 13:05:00",
        "obsTime": int(datetime(2026, 8, 29, 13, 0, tzinfo=UTC).timestamp()),
        "reportTime": "2026-08-29 13:00:00",
        "temp": 17.0,
        "dewp": 16.0,
        "wdir": 270,
        "wspd": 15,
        "visib": "1 1/2",
        "altim": 29.88,
        "slp": None,
        "qcField": 0,
        "wxString": "FG",
        "metarType": "METAR",
        "rawOb": "METAR CYYT 291300Z 27015KT 1 1/2SM FG BKN005 17/16 A2988",
        "cover": "BKN",
        "clouds": [{"cover": "BKN", "base": 500}],
    },
]


def test_parse_visibility_meters():
    assert parse_visibility_meters(None) is None
    assert parse_visibility_meters("") is None
    assert parse_visibility_meters(4) == pytest.approx(4 * 1609.344)
    assert parse_visibility_meters("4") == pytest.approx(4 * 1609.344)
    assert parse_visibility_meters("4SM") == pytest.approx(4 * 1609.344)
    assert parse_visibility_meters("10+") == pytest.approx(10 * 1609.344)
    assert parse_visibility_meters("1/2") == pytest.approx(0.5 * 1609.344)
    assert parse_visibility_meters("1 1/2") == pytest.approx(1.5 * 1609.344)


def test_parse_cloud_cover_percent():
    assert parse_cloud_cover_percent("CLR", []) == 0.0
    assert parse_cloud_cover_percent("FEW", []) == 25.0
    assert parse_cloud_cover_percent("SCT", []) == 50.0
    assert parse_cloud_cover_percent("BKN", []) == 75.0
    assert parse_cloud_cover_percent("OVC", []) == 100.0
    assert parse_cloud_cover_percent(None, [{"cover": "SCT"}]) == 50.0


def test_parse_wind_components():
    assert parse_wind_components(None, 180) == (None, None)
    assert parse_wind_components(10, "VRB") == (None, None)
    # 180 deg (from south): u = 0, v = +speed (blowing northward)
    u, v = parse_wind_components(10, 180)
    assert u == pytest.approx(0.0, abs=0.1)
    assert v == pytest.approx(5.14, abs=0.1)
    # 270 deg (from west): u = +speed (blowing eastward), v = 0
    u2, v2 = parse_wind_components(10, 270)
    assert u2 == pytest.approx(5.14, abs=0.1)
    assert v2 == pytest.approx(0.0, abs=0.1)
    # 360 deg (from north): u = 0, v = -speed (blowing southward)
    u3, v3 = parse_wind_components(10, 360)
    assert u3 == pytest.approx(0.0, abs=0.1)
    assert v3 == pytest.approx(-5.14, abs=0.1)
    # 090 deg (from east): u = -speed (blowing westward), v = 0
    u4, v4 = parse_wind_components(10, 90)
    assert u4 == pytest.approx(-5.14, abs=0.1)
    assert v4 == pytest.approx(0.0, abs=0.1)


def test_parse_pressure_hpa():
    assert parse_pressure_hpa(1013.25, None) == 1013.2
    assert parse_pressure_hpa(None, 29.92) == pytest.approx(1013.2, abs=0.2)
    assert parse_pressure_hpa(None, 1013.0) == 1013.0


def make_mock_client(data: Any, status_code: int = 200) -> PoliteClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=data if status_code == 200 else None)

    client = PoliteClient(min_host_interval_seconds=0.0)
    client._client = httpx.Client(
        transport=httpx.MockTransport(handler),
        headers={"User-Agent": USER_AGENT},
    )
    return client


def test_awc_metar_discover():
    client = make_mock_client(SAMPLE_METAR_JSON)
    adapter = AWCMetarAdapter(client=client)
    now = datetime(2026, 8, 29, 15, tzinfo=UTC)
    window = FetchWindow(now=now, back_hours=3, forward_hours=24)

    candidates = adapter.discover(window)
    assert len(candidates) == 1
    candidate = candidates[0]
    expected_ts = int(datetime(2026, 8, 29, 14, 0, tzinfo=UTC).timestamp())
    assert candidate.provider_run_id == f"cyyt-metar-{expected_ts}"
    assert candidate.run_time == datetime(2026, 8, 29, 14, 0, tzinfo=UTC)


def test_awc_metar_discover_empty_raises():
    client = make_mock_client([])
    adapter = AWCMetarAdapter(client=client)
    window = FetchWindow(now=datetime(2026, 8, 29, 15, tzinfo=UTC))
    with pytest.raises(AdapterUnavailable):
        adapter.discover(window)


def test_awc_metar_fetch_creates_valid_zarr_artifact(tmp_path: Path):
    client = make_mock_client(SAMPLE_METAR_JSON)
    adapter = AWCMetarAdapter(client=client)
    now = datetime(2026, 8, 29, 15, tzinfo=UTC)
    window = FetchWindow(now=now, back_hours=3, forward_hours=24)

    candidates = adapter.discover(window)
    result = adapter.fetch(candidates[0], window, tmp_path)

    assert result.source_id == "awc-metar-speci"
    assert result.complete is True
    assert result.qc_passed is True
    assert len(result.artifacts) == 1

    artifact = result.artifacts[0]
    assert artifact.logical_name == "surface"
    assert artifact.media_type == "application/zarr+zip"
    assert artifact.provenance["evidence_classes"] == ["retrieved"], "a retrieved artifact declares how its values came to exist"
    assert artifact.payload_path.exists()

    # Open and verify Zarr content
    store = zarr.storage.ZipStore(str(artifact.payload_path), mode="r")
    ds = xarray.open_zarr(store, consolidated=False)

    assert "temperature_2m" in ds.data_vars
    assert "dew_point_2m" in ds.data_vars
    assert "visibility" in ds.data_vars
    assert "total_cloud" in ds.data_vars
    assert "wind_u_10m" in ds.data_vars
    assert "mean_sea_level_pressure" in ds.data_vars

    # Step 1: 14:00Z -> temp 18.0, dewp 17.0, vis 4SM (~6437m)
    assert float(ds["temperature_2m"].sel(latitude=47.6186, longitude=-52.7519).values[1]) == 18.0
    assert float(ds["dew_point_2m"].sel(latitude=47.6186, longitude=-52.7519).values[1]) == 17.0
    assert float(ds["visibility"].sel(latitude=47.6186, longitude=-52.7519).values[1]) == pytest.approx(4 * 1609.344)
    assert ds["temperature_2m"].attrs["units"] == "degC"


SAMPLE_TAF_JSON = [
    {
        "tafId": 501,
        "icaoId": "CYYT",
        "issueTime": "2026-08-29 14:00:00",
        "validTimeFrom": int(datetime(2026, 8, 29, 14, 0, tzinfo=UTC).timestamp()),
        "validTimeTo": int(datetime(2026, 8, 30, 14, 0, tzinfo=UTC).timestamp()),
        "rawTAF": "TAF CYYT 291400Z 2914/3014 18012KT 6SM -SHRA BKN015",
        "lat": 47.6186,
        "lon": -52.7519,
        "fcsts": [
            {
                "timeFrom": int(datetime(2026, 8, 29, 14, 0, tzinfo=UTC).timestamp()),
                "timeTo": int(datetime(2026, 8, 29, 18, 0, tzinfo=UTC).timestamp()),
                "wspd": 12,
                "wdir": 180,
                "visib": "6",
                "clouds": [{"cover": "BKN", "base": 1500}],
            },
            {
                "timeFrom": int(datetime(2026, 8, 29, 18, 0, tzinfo=UTC).timestamp()),
                "timeTo": int(datetime(2026, 8, 29, 23, 0, tzinfo=UTC).timestamp()),
                "wspd": 15,
                "wdir": 200,
                "visib": "4",
                "clouds": [{"cover": "OVC", "base": 800}],
            },
        ],
    }
]


def test_awc_taf_discover_and_fetch(tmp_path: Path):
    from ingest.adapters.awc import AWCTafAdapter

    client = make_mock_client(SAMPLE_TAF_JSON)
    adapter = AWCTafAdapter(client=client)
    now = datetime(2026, 8, 29, 15, tzinfo=UTC)
    window = FetchWindow(now=now, back_hours=3, forward_hours=24)

    candidates = adapter.discover(window)
    assert len(candidates) == 1
    result = adapter.fetch(candidates[0], window, tmp_path)

    assert result.source_id == "awc-taf"
    assert result.complete is True
    assert len(result.artifacts) == 1

    store = zarr.storage.ZipStore(str(result.artifacts[0].payload_path), mode="r")
    ds = xarray.open_zarr(store, consolidated=False)

    assert "visibility" in ds.data_vars
    assert "wind_u_10m" in ds.data_vars
    assert "total_cloud" in ds.data_vars
    assert float(ds["visibility"].values[0, 0, 0]) == pytest.approx(6 * 1609.344)



# --- present weather: fog is FG, mist is BR, and the two are not the same ----

@pytest.mark.parametrize(
    ("wx_string", "expected"),
    [
        (None, PresentWeather(False, False, False, None)),
        ("", PresentWeather(False, False, False, None)),
        ("   ", PresentWeather(False, False, False, None)),
        ("FG", PresentWeather(True, False, False, "FG")),
        ("FZFG", PresentWeather(True, False, False, "FZFG")),
        ("MIFG", PresentWeather(True, False, False, "MIFG")),
        ("BCFG", PresentWeather(True, False, False, "BCFG")),
        ("PRFG", PresentWeather(True, False, False, "PRFG")),
        ("+FG", PresentWeather(True, False, False, "+FG")),
        ("-FG", PresentWeather(True, False, False, "-FG")),
        # Vicinity fog is fog evidence near, not at, the station, kept apart.
        ("VCFG", PresentWeather(False, True, False, "VCFG")),
        # Mist (table 4678) is not fog and must never be read as fog.
        ("BR", PresentWeather(False, False, True, "BR")),
        ("-SHRA BR", PresentWeather(False, False, True, "-SHRA BR")),
        ("FG BR", PresentWeather(True, False, True, "FG BR")),
        ("-RA VCFG BR", PresentWeather(False, True, True, "-RA VCFG BR")),
        # Haze, smoke, dust, sand and ash are neither.
        ("HZ", PresentWeather(False, False, False, "HZ")),
        ("FU", PresentWeather(False, False, False, "FU")),
        ("DU SA VA", PresentWeather(False, False, False, "DU SA VA")),
        ("-SHRA", PresentWeather(False, False, False, "-SHRA")),
        ("TSRA", PresentWeather(False, False, False, "TSRA")),
    ],
)
def test_present_weather_distinguishes_fog_from_mist(wx_string: str | None, expected: PresentWeather):
    assert parse_present_weather(wx_string) == expected


# --- cloud layers: published per layer, as reported, never bucketed --------

def test_cloud_layers_are_read_per_layer_in_provider_order():
    layers, errors = parse_cloud_layers([{"cover": "FEW", "base": 1200}, {"cover": "BKN", "base": 14000}, {"cover": "OVC", "base": None}], stamp="t")
    assert errors == []
    assert [layer.code_flag for layer in layers] == [CLOUD_COVER_FLAGS["FEW"], CLOUD_COVER_FLAGS["BKN"], CLOUD_COVER_FLAGS["OVC"]]
    assert [layer.cover_pct for layer in layers] == [25.0, 75.0, 100.0]
    assert layers[0].base_m == pytest.approx(1200 * FEET_TO_METRES)
    assert layers[1].base_m == pytest.approx(14000 * FEET_TO_METRES)
    assert layers[2].base_m is None, "a missing base is an absence, not zero"


def test_cloud_layers_with_no_report_are_empty_and_not_an_error():
    assert parse_cloud_layers(None, stamp="t") == ([], [])
    assert parse_cloud_layers([], stamp="t") == ([], [])


def test_an_unknown_cover_vocabulary_is_a_decode_error_not_a_guess():
    layers, errors = parse_cloud_layers([{"cover": "XYZ", "base": 500}], stamp="2026-08-29T14:00:00Z")
    assert layers == []
    assert errors == ["cloud_cover_code:XYZ@2026-08-29T14:00:00Z"]


def test_a_non_numeric_base_is_a_decode_error():
    layers, errors = parse_cloud_layers([{"cover": "BKN", "base": "low"}], stamp="s")
    assert errors == ["cloud_base:low@s"]
    assert len(layers) == 1 and layers[0].base_m is None


def test_more_than_six_layers_is_reported_loudly_and_never_dropped_silently():
    clouds = [{"cover": "FEW", "base": 100 * (index + 1)} for index in range(MAX_CLOUD_LAYERS + 2)]
    layers, errors = parse_cloud_layers(clouds, stamp="s")
    assert errors == [f"cloud_layers_truncated:{MAX_CLOUD_LAYERS + 2}@s"]
    assert len(layers) == MAX_CLOUD_LAYERS


def test_a_report_with_seven_layers_refuses_publication(tmp_path: Path):
    record = dict(SAMPLE_METAR_JSON[0])
    record["clouds"] = [{"cover": "FEW", "base": 100 * (index + 1)} for index in range(7)]
    client = make_mock_client([record])
    adapter = AWCMetarAdapter(client=client)
    window = FetchWindow(now=datetime(2026, 8, 29, 15, tzinfo=UTC), back_hours=3, forward_hours=24)

    result = adapter.fetch(adapter.discover(window)[0], window, tmp_path)

    assert result.complete is False
    assert any(flag.startswith("decode_error:cloud_layers_truncated:7@") for flag in result.artifacts[0].provenance["quality"]["flags"])


def test_metar_publishes_each_cloud_layer_as_reported_and_the_fog_flags(tmp_path: Path):
    client = make_mock_client(SAMPLE_METAR_JSON)
    adapter = AWCMetarAdapter(client=client)
    window = FetchWindow(now=datetime(2026, 8, 29, 15, tzinfo=UTC), back_hours=3, forward_hours=24)

    result = adapter.fetch(adapter.discover(window)[0], window, tmp_path)
    assert result.complete is True and result.qc_passed is True
    artifact = result.artifacts[0]
    assert artifact.provenance["adapter_version"] == "awc-metar-v2"
    ds = xarray.open_zarr(zarr.storage.ZipStore(str(artifact.payload_path), mode="r"), consolidated=False)

    # Step 1 is 14Z: OVC008 -> flag 6, 100 %, base 800 ft in metres.
    code = ds["cloud_layer_1_cover_code"]
    assert float(code.values[1, 0, 0]) == 6.0
    assert code.attrs["units"] == "code"
    assert list(code.attrs["flag_values"]) == list(range(10))
    assert code.attrs["flag_meanings"].split()[6] == "OVC"
    assert float(ds["cloud_layer_1_cover"].values[1, 0, 0]) == 100.0
    base = ds["cloud_layer_1_base"]
    assert float(base.values[1, 0, 0]) == pytest.approx(800 * 0.3048)
    assert base.attrs == {"units": "m", "original_units": "ft", "long_name": "cloud base above ground level"}
    # Step 0 is 13Z: BKN005.
    assert float(code.values[0, 0, 0]) == 5.0
    assert float(base.values[0, 0, 0]) == pytest.approx(500 * 0.3048)
    # No second layer was reported: the slot is absent, not zero.
    for suffix in ("cover_code", "cover", "base"):
        assert numpy.isnan(ds[f"cloud_layer_2_{suffix}"].values).all()
    # The collapsed total is untouched by the per-layer publication.
    assert float(ds["total_cloud"].values[1, 0, 0]) == 100.0
    assert float(ds["total_cloud"].values[0, 0, 0]) == 75.0
    # The provenance names the provider's unit for the base.
    assert artifact.provenance["original_units"]["cloud_layer_1_base"] == "ft"

    # Present weather: 13Z "FG" is fog; 14Z "-SHRA BR" is mist, not fog.
    assert ds["weather_fog_code"].values[:, 0, 0].tolist() == [1.0, 0.0]
    assert ds["weather_fog_vicinity_code"].values[:, 0, 0].tolist() == [0.0, 0.0]
    assert ds["weather_mist_code"].values[:, 0, 0].tolist() == [0.0, 1.0]
    assert ds["weather_fog_code"].attrs["units"] == "flag"
    assert ds["weather_fog_code"].attrs["flag_meanings"] == "absent present"
    assert list(ds.attrs["present_weather_strings"]) == ["FG", "-SHRA BR"]


def test_metar_with_no_present_weather_records_a_retrieved_absence(tmp_path: Path):
    records = [dict(item, wxString=None) for item in SAMPLE_METAR_JSON]
    adapter = AWCMetarAdapter(client=make_mock_client(records))
    window = FetchWindow(now=datetime(2026, 8, 29, 15, tzinfo=UTC), back_hours=3, forward_hours=24)
    result = adapter.fetch(adapter.discover(window)[0], window, tmp_path)
    ds = xarray.open_zarr(zarr.storage.ZipStore(str(result.artifacts[0].payload_path), mode="r"), consolidated=False)
    assert ds["weather_fog_code"].values[:, 0, 0].tolist() == [0.0, 0.0]
    assert ds["weather_mist_code"].values[:, 0, 0].tolist() == [0.0, 0.0]
    assert list(ds.attrs["present_weather_strings"]) == ["", ""]


def test_taf_periods_carry_their_own_layers_and_present_weather(tmp_path: Path):
    from ingest.adapters.awc import AWCTafAdapter

    taf = json.loads(json.dumps(SAMPLE_TAF_JSON))
    taf[0]["fcsts"][0]["wxString"] = "-SHRA"
    taf[0]["fcsts"][1]["wxString"] = "VCFG"
    taf[0]["fcsts"][1]["clouds"] = [{"cover": "SCT", "base": 500}, {"cover": "OVC", "base": 800}]
    adapter = AWCTafAdapter(client=make_mock_client(taf))
    window = FetchWindow(now=datetime(2026, 8, 29, 15, tzinfo=UTC), back_hours=3, forward_hours=24)

    result = adapter.fetch(adapter.discover(window)[0], window, tmp_path)
    assert result.complete is True
    artifact = result.artifacts[0]
    assert artifact.provenance["adapter_version"] == "awc-taf-v2"
    assert artifact.provenance["original_units"]["cloud_layer_2_base"] == "ft"
    ds = xarray.open_zarr(zarr.storage.ZipStore(str(artifact.payload_path), mode="r"), consolidated=False)

    assert ds["cloud_layer_1_cover_code"].values[:, 0, 0].tolist() == [5.0, 4.0]
    assert ds["cloud_layer_2_cover_code"].values[:, 0, 0].tolist()[0] != ds["cloud_layer_2_cover_code"].values[:, 0, 0].tolist()[0]  # NaN in period 1
    assert float(ds["cloud_layer_2_cover_code"].values[1, 0, 0]) == 6.0
    assert float(ds["cloud_layer_2_base"].values[1, 0, 0]) == pytest.approx(800 * 0.3048)
    assert ds["cloud_layer_1_cover_code"].attrs["long_name"] == "TAF cloud layer 1 cover code as reported"
    assert ds["weather_fog_code"].values[:, 0, 0].tolist() == [0.0, 0.0]
    assert ds["weather_fog_vicinity_code"].values[:, 0, 0].tolist() == [0.0, 1.0]
    assert list(ds.attrs["present_weather_strings"]) == ["-SHRA", "VCFG"]
