"""Unit tests for NOAA GFS S3 adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import httpx
import numpy
import pytest
import xarray
import zarr

from ingest.adapters.noaa_s3 import NOAAS3Adapter
from ingest.contract import AdapterUnavailable, FetchWindow
from ingest.http import PoliteClient, USER_AGENT

UTC = timezone.utc

SAMPLE_GFS_IDX = """\
1:0:d=2026082912:PRMSL:mean sea level:3 hour fcst:
2:100000:d=2026082912:TMP:2 m above ground:3 hour fcst:
3:200000:d=2026082912:DPT:2 m above ground:3 hour fcst:
4:300000:d=2026082912:RH:2 m above ground:3 hour fcst:
5:400000:d=2026082912:UGRD:10 m above ground:3 hour fcst:
6:500000:d=2026082912:VGRD:10 m above ground:3 hour fcst:
7:600000:d=2026082912:VIS:surface:3 hour fcst:
8:700000:d=2026082912:TCDC:entire atmosphere:3 hour fcst:
9:800000:d=2026082912:APCP:surface:0-3 hour acc fcst:
10:900000:d=2026082912:HGT:500 mb:3 hour fcst:
"""


def make_mock_client(url_responses: dict[str, tuple[int, str]]) -> PoliteClient:
    def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        for pattern, (status, text) in sorted(url_responses.items(), key=lambda item: len(item[0]), reverse=True):
            if pattern in url_str:
                return httpx.Response(status, text=text)
        return httpx.Response(404)

    client = PoliteClient(min_host_interval_seconds=0.0)
    client._client = httpx.Client(
        transport=httpx.MockTransport(handler),
        headers={"User-Agent": USER_AGENT},
    )
    return client


def test_noaa_gfs_discover():
    client = make_mock_client(
        {
            "gfs.20260829/12/atmos/gfs.t12z.pgrb2.0p25.f000.idx": (200, SAMPLE_GFS_IDX),
        }
    )
    adapter = NOAAS3Adapter(client=client)
    now = datetime(2026, 8, 29, 14, tzinfo=UTC)
    window = FetchWindow(now=now)

    candidates = adapter.discover(window)
    assert len(candidates) >= 1
    assert candidates[0].provider_run_id == "gfs-2026082912"
    assert candidates[0].run_time == datetime(2026, 8, 29, 12, 0, tzinfo=UTC)


def test_noaa_gfs_discover_unavailable():
    client = make_mock_client({})
    adapter = NOAAS3Adapter(client=client)
    window = FetchWindow(now=datetime(2026, 8, 29, 14, tzinfo=UTC))
    with pytest.raises(AdapterUnavailable):
        adapter.discover(window)


def test_noaa_gfs_fetch_subset_ranges(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    client = make_mock_client(
        {
            # window covers now=13Z +/- (1h back, 2h forward) against a 12Z run,
            # i.e. valid times 12/13/14/15Z -> leads f000-f003. Every one needs
            # its own idx sidecar or the run comes back incomplete for the
            # wrong reason (a missing lead, not a missing field).
            "gfs.20260829/12/atmos/gfs.t12z.pgrb2.0p25.f000.idx": (200, SAMPLE_GFS_IDX),
            "gfs.20260829/12/atmos/gfs.t12z.pgrb2.0p25.f001.idx": (200, SAMPLE_GFS_IDX),
            "gfs.20260829/12/atmos/gfs.t12z.pgrb2.0p25.f002.idx": (200, SAMPLE_GFS_IDX),
            "gfs.20260829/12/atmos/gfs.t12z.pgrb2.0p25.f003.idx": (200, SAMPLE_GFS_IDX),
        }
    )
    adapter = NOAAS3Adapter(client=client)

    # Track download_ranges calls
    download_calls = []

    def mock_download_ranges(url, dest, ranges, max_bytes):
        download_calls.append((url, ranges))
        dest.write_bytes(b"dummy_grib_subset")
        return 1000

    monkeypatch.setattr(client, "download_ranges", mock_download_ranges)

    latitudes = numpy.array([45.0, 48.0])
    longitudes = numpy.array([-55.0, -50.0])

    def mock_open_grib(path: Path):
        return xarray.Dataset(
            {
                "t2m": (("latitude", "longitude"), numpy.full((2, 2), 288.15), {"units": "K"}),
                "d2m": (("latitude", "longitude"), numpy.full((2, 2), 285.15), {"units": "K"}),
                "vis": (("latitude", "longitude"), numpy.full((2, 2), 10000.0), {"units": "m"}),
                "prmsl": (("latitude", "longitude"), numpy.full((2, 2), 101300.0), {"units": "Pa"}),
                "u10": (("latitude", "longitude"), numpy.full((2, 2), 5.0), {"units": "m s-1"}),
                "v10": (("latitude", "longitude"), numpy.full((2, 2), -3.0), {"units": "m s-1"}),
            },
            coords={"latitude": latitudes, "longitude": longitudes},
        )

    monkeypatch.setattr("ingest.adapters.noaa_s3.open_grib", mock_open_grib)
    monkeypatch.setattr("ingest.adapters.noaa_s3.crop_to_bbox", lambda ds, bounds: ds)

    now = datetime(2026, 8, 29, 13, tzinfo=UTC)
    window = FetchWindow(now=now, back_hours=1, forward_hours=2)
    candidates = adapter.discover(window)

    result = adapter.fetch(candidates[0], window, tmp_path)
    assert result.source_id == "noaa-gfs"
    assert result.complete is True
    assert result.qc_passed is True
    assert len(download_calls) >= 1
    assert len(result.artifacts) == 1

    artifact = result.artifacts[0]
    assert artifact.logical_name == "surface"
    assert artifact.payload_path.exists()

    # Open and verify Zarr content
    store = zarr.storage.ZipStore(str(artifact.payload_path), mode="r")
    ds = xarray.open_zarr(store, consolidated=False)

    assert "temperature_2m" in ds.data_vars
    assert "dew_point_2m" in ds.data_vars
    assert "visibility" in ds.data_vars
    assert "mean_sea_level_pressure" in ds.data_vars

    # Verify unit normalization: Kelvin -> degC, Pa -> hPa
    assert float(ds["temperature_2m"].values[0, 0, 0]) == pytest.approx(15.0, abs=0.1)
    assert float(ds["dew_point_2m"].values[0, 0, 0]) == pytest.approx(12.0, abs=0.1)
    assert float(ds["mean_sea_level_pressure"].values[0, 0, 0]) == pytest.approx(1013.0, abs=0.1)
    assert float(ds["visibility"].values[0, 0, 0]) == 10000.0


def test_noaa_gfs_fetch_missing_mandatory_field_comes_back_incomplete(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """The mirror image of the happy path: drop one field GFS_MANIFEST declares
    mandatory (wind_u_10m) from every decoded lead. The run must come back
    ``complete=False`` with a ``missing_field:`` flag rather than silently
    publishing a run with a hole in it."""
    client = make_mock_client(
        {
            "gfs.20260829/12/atmos/gfs.t12z.pgrb2.0p25.f000.idx": (200, SAMPLE_GFS_IDX),
            "gfs.20260829/12/atmos/gfs.t12z.pgrb2.0p25.f001.idx": (200, SAMPLE_GFS_IDX),
            "gfs.20260829/12/atmos/gfs.t12z.pgrb2.0p25.f002.idx": (200, SAMPLE_GFS_IDX),
            "gfs.20260829/12/atmos/gfs.t12z.pgrb2.0p25.f003.idx": (200, SAMPLE_GFS_IDX),
        }
    )
    adapter = NOAAS3Adapter(client=client)

    def mock_download_ranges(url, dest, ranges, max_bytes):
        dest.write_bytes(b"dummy_grib_subset")
        return 1000

    monkeypatch.setattr(client, "download_ranges", mock_download_ranges)

    latitudes = numpy.array([45.0, 48.0])
    longitudes = numpy.array([-55.0, -50.0])

    def mock_open_grib(path: Path):
        # wind_u_10m (u10) is deliberately absent: a mandatory field GFS_MANIFEST
        # declares but this decoded lead never produced.
        return xarray.Dataset(
            {
                "t2m": (("latitude", "longitude"), numpy.full((2, 2), 288.15), {"units": "K"}),
                "d2m": (("latitude", "longitude"), numpy.full((2, 2), 285.15), {"units": "K"}),
                "prmsl": (("latitude", "longitude"), numpy.full((2, 2), 101300.0), {"units": "Pa"}),
                "v10": (("latitude", "longitude"), numpy.full((2, 2), -3.0), {"units": "m s-1"}),
            },
            coords={"latitude": latitudes, "longitude": longitudes},
        )

    monkeypatch.setattr("ingest.adapters.noaa_s3.open_grib", mock_open_grib)
    monkeypatch.setattr("ingest.adapters.noaa_s3.crop_to_bbox", lambda ds, bounds: ds)

    now = datetime(2026, 8, 29, 13, tzinfo=UTC)
    window = FetchWindow(now=now, back_hours=1, forward_hours=2)
    candidates = adapter.discover(window)

    result = adapter.fetch(candidates[0], window, tmp_path)
    assert result.complete is False
    assert any(flag.startswith("missing_field:wind_u_10m") for flag in _flags_of(result))


def _flags_of(result) -> list[str]:
    provenance = result.artifacts[0].provenance
    return list(provenance["quality"]["flags"])
