"""Unit tests for ECCC Datamart adapters (HRDPS, RDPS, GDPS).

Discovery walks the *dated* Datamart tree
(``https://dd.weather.gc.ca/{YYYYMMDD}/WXO-DD/{model}/{HH}/{FFF}/``) and the
run identity is read from the filename's own ``{YYYYMMDD}T{HH}Z`` stamp, never
from ``window.now``. These tests exercise that contract directly, including
the 00Z rollover (today's dated directory is empty; yesterday's is not) and a
cycle whose ``000/`` directory carries mixed or absent stamps, which must be
skipped rather than mislabelled.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import httpx
import numpy
import pytest
import xarray
import zarr

from ingest.adapters.eccc_datamart import (
    GDPS_VARS,
    HRDPS_OMEGA_VARS,
    HRDPS_STEERING_VARS,
    HRDPS_VARS,
    RDPS_VARS,
    ECCCDataMartAdapter,
    manifest_for,
)
from ingest.contract import AdapterUnavailable, FetchWindow
from ingest.http import PoliteClient, USER_AGENT

UTC = timezone.utc


def make_html_listing(items: list[str]) -> str:
    links = "".join(f'<a href="{item}">{item}</a><br>\n' for item in items)
    return f"<html><body>{links}</body></html>"


def make_mock_client(url_map: dict[str, str]) -> PoliteClient:
    def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        for pattern, html in sorted(url_map.items(), key=lambda item: len(item[0]), reverse=True):
            if pattern in url_str:
                return httpx.Response(200, text=html)
        return httpx.Response(404)

    client = PoliteClient(min_host_interval_seconds=0.0)
    client._client = httpx.Client(
        transport=httpx.MockTransport(handler),
        headers={"User-Agent": USER_AGENT},
    )
    return client


def make_adapter(client: PoliteClient, *, var_map=HRDPS_VARS, **kwargs) -> ECCCDataMartAdapter:
    return ECCCDataMartAdapter(
        source_id="eccc-hrdps",
        model_subpath="model_hrdps/continental/2.5km",
        grid_token="RLatLon0.0225",
        var_map=var_map,
        client=client,
        **kwargs,
    )


def stamp_files(date_str: str, hour: str, *, names: tuple[str, ...] = ("TMP", "DPT")) -> list[str]:
    return [f"{date_str}T{hour}Z_MSC_HRDPS_{var}_AGL-2m_RLatLon0.0225_PT000H.grib2" for var in names]


def test_hrdps_discover():
    url_map = {
        "20260829/WXO-DD/model_hrdps/continental/2.5km/": make_html_listing(["00/", "06/", "12/"]),
        "20260829/WXO-DD/model_hrdps/continental/2.5km/12/": make_html_listing(["000/", "001/", "002/"]),
        "20260829/WXO-DD/model_hrdps/continental/2.5km/12/000/": make_html_listing(stamp_files("20260829", "12")),
        "20260829/WXO-DD/model_hrdps/continental/2.5km/06/": make_html_listing(["000/", "001/"]),
        "20260829/WXO-DD/model_hrdps/continental/2.5km/06/000/": make_html_listing(stamp_files("20260829", "06")),
    }
    client = make_mock_client(url_map)
    adapter = make_adapter(client)
    now = datetime(2026, 8, 29, 15, tzinfo=UTC)
    window = FetchWindow(now=now)

    candidates = adapter.discover(window)
    assert len(candidates) >= 1
    newest = candidates[0]
    assert newest.provider_run_id == "2026082912"
    assert newest.run_time == datetime(2026, 8, 29, 12, 0, tzinfo=UTC)
    assert newest.detail["cycle"] == "12"
    # The run identity comes from the filename stamp, never window.now (15Z).
    assert newest.run_time != now


def test_discover_empty_raises():
    url_map = {
        "20260829/WXO-DD/model_hrdps/continental/2.5km/": make_html_listing([]),
    }
    client = make_mock_client(url_map)
    adapter = make_adapter(client, fallback_days=0)
    window = FetchWindow(now=datetime(2026, 8, 29, 15, tzinfo=UTC))
    with pytest.raises(AdapterUnavailable):
        adapter.discover(window)


def test_discover_falls_back_to_yesterday_across_the_00z_rollover():
    """Today's dated directory is empty in the first hours of the UTC day;
    discovery must fall back to yesterday's and still return a candidate
    stamped with yesterday's date, not today's."""
    url_map = {
        # 2026-08-30 (today) has rolled over and has nothing published yet.
        "20260830/WXO-DD/model_hrdps/continental/2.5km/": make_html_listing([]),
        # 2026-08-29 (yesterday) is fully populated.
        "20260829/WXO-DD/model_hrdps/continental/2.5km/": make_html_listing(["18/"]),
        "20260829/WXO-DD/model_hrdps/continental/2.5km/18/": make_html_listing(["000/"]),
        "20260829/WXO-DD/model_hrdps/continental/2.5km/18/000/": make_html_listing(stamp_files("20260829", "18")),
    }
    client = make_mock_client(url_map)
    adapter = make_adapter(client, fallback_days=1)
    window = FetchWindow(now=datetime(2026, 8, 30, 2, 30, tzinfo=UTC))

    candidates = adapter.discover(window)
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.provider_run_id == "2026082918"
    assert candidate.run_time == datetime(2026, 8, 29, 18, 0, tzinfo=UTC)
    assert candidate.detail["date_str"] == "20260829"


def test_a_cycle_with_mixed_or_absent_stamps_is_skipped_not_mislabelled():
    """A ``000/`` directory that carries files stamped with two different runs
    (a rollover caught mid-listing) or no recognizable stamp at all must never
    become a candidate: it is skipped, and discovery falls through to a cycle
    it can name honestly."""
    url_map = {
        "20260829/WXO-DD/model_hrdps/continental/2.5km/": make_html_listing(["06/", "12/"]),
        # 12/000 mixes two distinct run stamps -> unusable.
        "20260829/WXO-DD/model_hrdps/continental/2.5km/12/": make_html_listing(["000/"]),
        "20260829/WXO-DD/model_hrdps/continental/2.5km/12/000/": make_html_listing(
            ["20260829T12Z_MSC_HRDPS_TMP_AGL-2m_RLatLon0.0225_PT000H.grib2", "20260829T18Z_MSC_HRDPS_DPT_AGL-2m_RLatLon0.0225_PT000H.grib2"]
        ),
        # 06/000 has files with no recognizable run stamp at all -> unusable.
        "20260829/WXO-DD/model_hrdps/continental/2.5km/06/": make_html_listing(["000/"]),
        "20260829/WXO-DD/model_hrdps/continental/2.5km/06/000/": make_html_listing(
            ["MSC_HRDPS_TMP_AGL-2m_RLatLon0.0225_PT000H.grib2"]
        ),
    }
    client = make_mock_client(url_map)
    adapter = make_adapter(client, fallback_days=0)
    window = FetchWindow(now=datetime(2026, 8, 29, 15, tzinfo=UTC))

    with pytest.raises(AdapterUnavailable):
        adapter.discover(window)


def test_eccc_fetch_with_mocked_decode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    url_map = {
        "20260829/WXO-DD/model_hrdps/continental/2.5km/": make_html_listing(["12/"]),
        "20260829/WXO-DD/model_hrdps/continental/2.5km/12/": make_html_listing(["000/"]),
        "20260829/WXO-DD/model_hrdps/continental/2.5km/12/000/": make_html_listing(
            [
                "20260829T12Z_MSC_HRDPS_TMP_AGL-2m_RLatLon0.0225_PT000H.grib2",
                "20260829T12Z_MSC_HRDPS_DPT_AGL-2m_RLatLon0.0225_PT000H.grib2",
            ]
        ),
    }
    client = make_mock_client(url_map)
    # Only the two variables the mocked directory actually carries are
    # declared, so this is a genuinely complete run rather than one that
    # happens to satisfy validate_run by omission.
    fetch_var_map = {"temperature_2m": HRDPS_VARS["temperature_2m"], "dew_point_2m": HRDPS_VARS["dew_point_2m"]}
    adapter = make_adapter(client, var_map=fetch_var_map)

    # Mock download to avoid network download of binary GRIB2
    monkeypatch.setattr(client, "download", lambda url, dest, max_bytes: dest.write_bytes(b"dummy"))

    # Mock open_grib and crop_to_bbox
    latitudes = numpy.array([47.5, 47.6])
    longitudes = numpy.array([-52.8, -52.7])

    def mock_open_grib(path: Path):
        var_name = "t2m" if ("TMP" in str(path) or "temperature" in str(path)) else "d2m"
        val = 15.0 if ("TMP" in str(path) or "temperature" in str(path)) else 12.0
        ds = xarray.Dataset(
            {var_name: (("latitude", "longitude"), numpy.full((2, 2), val))},
            coords={"latitude": latitudes, "longitude": longitudes},
        )
        # validate_run reads units off the variable, not the dataset, so the
        # mock must set them where the real decode path does after
        # normalize_units.
        ds[var_name].attrs["units"] = "degC"
        return ds

    monkeypatch.setattr("ingest.adapters.eccc_datamart.open_grib", mock_open_grib)
    monkeypatch.setattr("ingest.adapters.eccc_datamart.crop_to_bbox", lambda ds, bounds: ds)
    monkeypatch.setattr("ingest.adapters.eccc_datamart.normalize_units", lambda ds: ds)

    # window.now (13Z) deliberately differs from the filename stamp (12Z): the
    # run identity below must come from the stamp, not the clock.
    now = datetime(2026, 8, 29, 13, tzinfo=UTC)
    window = FetchWindow(now=now, back_hours=3, forward_hours=24)
    candidates = adapter.discover(window)

    result = adapter.fetch(candidates[0], window, tmp_path)
    assert result.source_id == "eccc-hrdps"
    assert result.provider_run_id == "2026082912"
    assert result.run_time == datetime(2026, 8, 29, 12, tzinfo=UTC)
    assert result.run_time != now
    assert result.complete is True
    assert result.qc_passed is True
    assert len(result.artifacts) == 1

    artifact = result.artifacts[0]
    assert artifact.logical_name == "surface"
    assert artifact.payload_path.exists()

    # Open and verify Zarr content
    store = zarr.storage.ZipStore(str(artifact.payload_path), mode="r")
    ds = xarray.open_zarr(store, consolidated=False)

    assert "temperature_2m" in ds.data_vars
    assert "dew_point_2m" in ds.data_vars
    # Only what the map declared, and never the withheld cloud field.
    assert set(ds.data_vars) == {"temperature_2m", "dew_point_2m"}
    assert "total_cloud" not in ds.data_vars
    assert float(ds["temperature_2m"].sel(latitude=47.5, longitude=-52.7).values[0]) == 15.0
    assert float(ds["dew_point_2m"].sel(latitude=47.5, longitude=-52.7).values[0]) == 12.0


def test_a_rotated_hrdps_grid_survives_the_real_crop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """The same fetch, but with the real ``crop_to_bbox`` and HRDPS's own grid.

    ``test_eccc_fetch_with_mocked_decode`` stubs ``crop_to_bbox`` out and hands
    the adapter a 1-D lat/lon grid, which is why it stayed green while every
    live HRDPS and RDPS run died in the crop. HRDPS is a rotated lat/lon
    product, so cfgrib returns 2-D ``latitude``/``longitude`` over anonymous
    ``y``/``x`` dimensions; this exercises that shape through the real
    normalization path.
    """
    url_map = {
        "20260829/WXO-DD/model_hrdps/continental/2.5km/": make_html_listing(["12/"]),
        "20260829/WXO-DD/model_hrdps/continental/2.5km/12/": make_html_listing(["000/"]),
        "20260829/WXO-DD/model_hrdps/continental/2.5km/12/000/": make_html_listing(
            [
                "20260829T12Z_MSC_HRDPS_TMP_AGL-2m_RLatLon0.0225_PT000H.grib2",
                "20260829T12Z_MSC_HRDPS_DPT_AGL-2m_RLatLon0.0225_PT000H.grib2",
            ]
        ),
    }
    client = make_mock_client(url_map)
    fetch_var_map = {"temperature_2m": HRDPS_VARS["temperature_2m"], "dew_point_2m": HRDPS_VARS["dew_point_2m"]}
    adapter = make_adapter(client, var_map=fetch_var_map)
    monkeypatch.setattr(client, "download", lambda url, dest, max_bytes: dest.write_bytes(b"dummy"))

    rows, columns = 60, 60
    row, column = numpy.meshgrid(numpy.arange(rows), numpy.arange(columns), indexing="ij")
    latitudes = 45.0 + 0.1 * row + 0.01 * column
    longitudes = -56.0 + 0.15 * column - 0.01 * row

    def mock_open_grib(path: Path):
        warm = "TMP" in str(path) or "temperature" in str(path)
        name, kelvin = ("t2m", 288.15) if warm else ("d2m", 285.15)
        dataset = xarray.Dataset(
            {name: (("y", "x"), numpy.full((rows, columns), kelvin, dtype="float32"))},
            coords={"latitude": (("y", "x"), latitudes), "longitude": (("y", "x"), longitudes)},
        )
        dataset[name].attrs["units"] = "K"
        return dataset

    monkeypatch.setattr("ingest.adapters.eccc_datamart.open_grib", mock_open_grib)

    window = FetchWindow(now=datetime(2026, 8, 29, 13, tzinfo=UTC), back_hours=3, forward_hours=24)
    result = adapter.fetch(adapter.discover(window)[0], window, tmp_path)

    assert result.complete is True and result.qc_passed is True
    store = zarr.storage.ZipStore(str(result.artifacts[0].payload_path), mode="r")
    try:
        stored = xarray.open_zarr(store, consolidated=False)
        assert stored["latitude"].dims == ("y", "x")
        # The crop kept a real sub-grid, not the whole continental domain, and
        # the Kelvin the provider sent came back as degrees Celsius.
        assert 0 < stored.sizes["y"] < rows and 0 < stored.sizes["x"] < columns
        assert stored["temperature_2m"].attrs["units"] == "degC"
        assert float(stored["temperature_2m"].max()) == pytest.approx(15.0, abs=1e-3)
        assert float(stored["dew_point_2m"].max()) == pytest.approx(12.0, abs=1e-3)
    finally:
        store.close()


#: The evidence set HRDPS publishes. The steering winds sit apart from it:
#: they are display-derivation input for cloud motion, declared optional, and
#: never read on an evidence path.
HRDPS_EVIDENCE_FIELDS = frozenset(
    {
        "temperature_2m",
        "dew_point_2m",
        "relative_humidity_2m",
        "wind_u_10m",
        "wind_v_10m",
        "mean_sea_level_pressure",
        "total_cloud",
    }
)
HRDPS_PUBLISHED_FIELDS = HRDPS_EVIDENCE_FIELDS | set(HRDPS_STEERING_VARS) | set(HRDPS_OMEGA_VARS)

_TCDC_URL_MAP = {
    "20260830/WXO-DD/model_hrdps/continental/2.5km/": make_html_listing(["12/"]),
    "20260830/WXO-DD/model_hrdps/continental/2.5km/12/": make_html_listing(["000/"]),
    "20260830/WXO-DD/model_hrdps/continental/2.5km/12/000/": make_html_listing(
        ["20260830T12Z_MSC_HRDPS_TCDC_Sfc_RLatLon0.0225_PT000H.grib2"]
    ),
}

#: What cfgrib hands back for the live ``TCDC_Sfc`` file: a variable named
#: ``unknown`` whose ``units`` attr is the literal string ``unknown``. With
#: ``read_keys`` requested, the message's own WMO identity keys ride along as
#: ``GRIB_*`` attrs.
def _mock_tcdc_dataset(*, with_wmo_keys: bool) -> xarray.Dataset:
    dataset = xarray.Dataset(
        {"unknown": (("latitude", "longitude"), numpy.array([[0.0, 100.0], [37.5, 62.5]]))},
        coords={"latitude": numpy.array([47.5, 47.6]), "longitude": numpy.array([-52.8, -52.7])},
    )
    dataset["unknown"].attrs["units"] = "unknown"
    if with_wmo_keys:
        dataset["unknown"].attrs.update(
            {
                "GRIB_discipline": 0,
                "GRIB_parameterCategory": 6,
                "GRIB_parameterNumber": 1,
                "GRIB_typeOfFirstFixedSurface": 1,
                "GRIB_typeOfSecondFixedSurface": 255,
            }
        )
    return dataset


def test_total_cloud_is_published_from_the_messages_own_wmo_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """MSC's ``TCDC_Sfc`` decodes as ``unknown``/``unknown`` in ecCodes 2.48.0.

    Live on 2026-08-30 the message carries WMO 0/6/1 with
    ``typeOfSecondFixedSurface=255``; ecCodes' ``tcc`` concept requires 8, so
    the decoder declares no units. Owner decision 2026-08-31: publish from the
    coded WMO keys themselves - they are retrieved facts in the message - with
    the basis recorded in the variable's attrs.
    """
    assert "total_cloud" in HRDPS_VARS
    assert "total_cloud" in RDPS_VARS
    assert "total_cloud" not in GDPS_VARS
    assert set(HRDPS_VARS) == HRDPS_PUBLISHED_FIELDS
    # The steering winds and the vertical velocity are optional - they inform
    # display derivations only; every evidence field is mandatory. That
    # disjointness is the invariant that matters: a display input may go
    # missing, a reading may not.
    optional = {field.name for field in manifest_for("eccc-hrdps", HRDPS_VARS).fields if field.optional}
    assert optional == set(HRDPS_STEERING_VARS) | set(HRDPS_OMEGA_VARS)
    assert optional.isdisjoint(HRDPS_EVIDENCE_FIELDS)

    client = make_mock_client(_TCDC_URL_MAP)
    adapter = make_adapter(client, var_map={"total_cloud": ("TCDC", "Sfc")})
    monkeypatch.setattr(client, "download", lambda url, dest, max_bytes: dest.write_bytes(b"dummy"))

    seen_read_keys: list[tuple[str, ...] | None] = []

    def mock_open_grib(path: Path, *, read_keys=None):
        seen_read_keys.append(tuple(read_keys) if read_keys else None)
        return _mock_tcdc_dataset(with_wmo_keys=True)

    monkeypatch.setattr("ingest.adapters.eccc_datamart.open_grib", mock_open_grib)
    monkeypatch.setattr("ingest.adapters.eccc_datamart.crop_to_bbox", lambda ds, bounds: ds)

    window = FetchWindow(now=datetime(2026, 8, 30, 13, tzinfo=UTC), back_hours=3, forward_hours=24)
    result = adapter.fetch(adapter.discover(window)[0], window, tmp_path)

    # The identity keys were actually requested from the decoder.
    assert seen_read_keys and "parameterNumber" in (seen_read_keys[0] or ())
    assert result.qc_passed is True
    assert result.complete is True

    store = zarr.storage.ZipStore(str(result.artifacts[0].payload_path), mode="r")
    try:
        stored = xarray.open_zarr(store, consolidated=False)
        cloud = stored["total_cloud"]
        assert cloud.attrs["units"] == "percent"
        assert cloud.attrs["original_units"] == "unknown"
        assert "WMO GRIB2 code table 4.2" in cloud.attrs["units_basis"]
        assert float(cloud.max()) == 100.0
    finally:
        store.close()


def test_total_cloud_without_its_wmo_identity_is_still_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A message whose coded keys do not say 'total cloud cover' stays refused.

    The 0-100 value range alone is an inference, not a retrieval; without the
    WMO 0/6/1 identity the field must not be published, and the run fails
    loudly rather than shipping an artifact with undeclared units.
    """
    client = make_mock_client(_TCDC_URL_MAP)
    adapter = make_adapter(client, var_map={"total_cloud": ("TCDC", "Sfc")})
    monkeypatch.setattr(client, "download", lambda url, dest, max_bytes: dest.write_bytes(b"dummy"))
    monkeypatch.setattr(
        "ingest.adapters.eccc_datamart.open_grib",
        lambda path, *, read_keys=None: _mock_tcdc_dataset(with_wmo_keys=False),
    )
    monkeypatch.setattr("ingest.adapters.eccc_datamart.crop_to_bbox", lambda ds, bounds: ds)
    # The real normalize_units runs: it must leave ``unknown`` untouched rather
    # than guessing ``percent`` from the 0-100 value range.

    window = FetchWindow(now=datetime(2026, 8, 30, 13, tzinfo=UTC), back_hours=3, forward_hours=24)
    with pytest.raises(AdapterUnavailable):
        adapter.fetch(adapter.discover(window)[0], window, tmp_path)


@pytest.mark.live_smoke
@pytest.mark.skipif(os.environ.get("WEATHER_LIVE_SMOKE") != "1", reason="set WEATHER_LIVE_SMOKE=1 to hit Datamart")
def test_live_hrdps_tcdc_still_carries_wmo_total_cloud_keys(tmp_path: Path):
    """One polite download of today's HRDPS ``TCDC_Sfc`` PT006H file.

    Asserts only the WMO identity of the message (category 6, number 1) and
    prints what ecCodes declares for units. It never asserts a unit outcome:
    the day the decoder starts declaring ``%`` is a finding for the owner,
    not a test failure.
    """
    eccodes = pytest.importorskip("eccodes")
    from ingest.adapters.eccc_datamart import HRDPS_ADAPTER

    client = PoliteClient()
    adapter = ECCCDataMartAdapter(
        source_id=HRDPS_ADAPTER.source_id,
        model_subpath=HRDPS_ADAPTER.model_subpath,
        grid_token=HRDPS_ADAPTER.grid_token,
        var_map=HRDPS_VARS,
        client=client,
    )
    window = FetchWindow(now=datetime.now(UTC))
    candidate = next((c for c in adapter.discover(window) if "006" in c.detail["available_hours"]), None)
    if candidate is None:
        pytest.skip("no HRDPS cycle with a populated 006/ directory right now")
    hour_url = candidate.detail["cycle_url"] + "006/"
    files = [f for f in client.list_directory(hour_url, suffixes=(".grib2",)) if "_TCDC_Sfc_" in f]
    if not files:
        pytest.skip(f"no TCDC_Sfc file under {hour_url}")
    local = tmp_path / files[0]
    client.download(hour_url + files[0], local, max_bytes=10 * 1024 * 1024)

    with local.open("rb") as handle:
        gid = eccodes.codes_grib_new_from_file(handle)
        try:
            keys = {
                key: eccodes.codes_get(gid, key)
                for key in ("discipline", "parameterCategory", "parameterNumber", "typeOfSecondFixedSurface", "units")
            }
        finally:
            eccodes.codes_release(gid)
    print(f"HRDPS TCDC_Sfc GRIB keys: {keys}")
    assert keys["discipline"] == 0
    assert keys["parameterCategory"] == 6
    assert keys["parameterNumber"] == 1
