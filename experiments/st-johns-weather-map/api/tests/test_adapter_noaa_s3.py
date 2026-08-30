"""Unit tests for NOAA GFS S3 adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import httpx
import numpy
import pytest
import xarray
import zarr

from ingest.adapters.noaa_s3 import (
    GFS_DECODE_SHORTNAMES,
    GFS_IDX_SELECTORS,
    MAX_BYTES_PER_LEAD,
    NOAAS3Adapter,
    select_gfs_ranges,
)
from ingest.contract import AdapterUnavailable, FetchWindow
from ingest.grib import GribError, selected_bytes
from ingest.http import PoliteClient, USER_AGENT

UTC = timezone.utc

# A condensed but structurally faithful GFS pgrb2 inventory: every message this
# adapter wants, interleaved with the traps that previously broke it — the same
# parameters at isobaric levels (TMP:500 mb, TCDC:850 mb, UGRD:10 mb...), the
# time-averaged duplicates of the cloud fields, and APCP accumulations.
# Messages sit 5 MB apart so the 1 MiB gap-merge cannot absorb a distractor and
# hide an over-selection.
_M = 5_000_000
SAMPLE_GFS_IDX_LINES = [
    # (param, level, forecast, wanted)
    ("PRMSL", "mean sea level", "3 hour fcst", True),
    ("VIS", "surface", "3 hour fcst", True),
    ("UGRD", "planetary boundary layer", "3 hour fcst", False),
    ("TMP", "500 mb", "3 hour fcst", False),
    ("RH", "500 mb", "3 hour fcst", False),
    ("UGRD", "10 mb", "3 hour fcst", False),
    ("VGRD", "10 mb", "3 hour fcst", False),
    ("TCDC", "850 mb", "3 hour fcst", False),
    ("TCDC", "500 mb", "3 hour fcst", False),
    ("TMP", "2 m above ground", "3 hour fcst", True),
    ("DPT", "2 m above ground", "3 hour fcst", True),
    ("RH", "2 m above ground", "3 hour fcst", True),
    ("UGRD", "10 m above ground", "3 hour fcst", True),
    ("VGRD", "10 m above ground", "3 hour fcst", True),
    ("APCP", "surface", "0-3 hour acc fcst", False),
    ("LCDC", "low cloud layer", "3 hour fcst", True),
    ("LCDC", "low cloud layer", "2-3 hour ave fcst", False),
    ("MCDC", "middle cloud layer", "3 hour fcst", True),
    ("MCDC", "middle cloud layer", "2-3 hour ave fcst", False),
    ("HCDC", "high cloud layer", "3 hour fcst", True),
    ("HCDC", "high cloud layer", "2-3 hour ave fcst", False),
    ("TCDC", "entire atmosphere", "3 hour fcst", True),
    ("TCDC", "entire atmosphere", "2-3 hour ave fcst", False),
    ("HGT", "500 mb", "3 hour fcst", False),
]

SAMPLE_GFS_IDX = "\n".join(
    f"{i + 1}:{i * _M}:d=2026082912:{param}:{level}:{forecast}:"
    for i, (param, level, forecast, _) in enumerate(SAMPLE_GFS_IDX_LINES)
) + "\n"

WANTED_OFFSETS = {i * _M for i, (_, _, _, wanted) in enumerate(SAMPLE_GFS_IDX_LINES) if wanted}
UNWANTED_OFFSETS = {i * _M for i, (_, _, _, wanted) in enumerate(SAMPLE_GFS_IDX_LINES) if not wanted}


def _covered(ranges, offset: int) -> bool:
    return any(r.start <= offset and (r.end is None or offset <= r.end) for r in ranges)


def test_select_gfs_ranges_picks_only_declared_messages():
    ranges, params = select_gfs_ranges(SAMPLE_GFS_IDX)
    assert params == {p for p, _ in GFS_IDX_SELECTORS}
    for offset in WANTED_OFFSETS:
        assert _covered(ranges, offset), f"wanted message at {offset} not covered"
    for offset in UNWANTED_OFFSETS:
        assert not _covered(ranges, offset), f"unwanted message at {offset} covered"


def test_select_gfs_ranges_excludes_time_averaged_cloud_duplicates():
    """The instantaneous LCDC/MCDC/HCDC/TCDC messages are selected; their
    '2-3 hour ave fcst' twins are not, so cfgrib never sees two step types."""
    ranges, _ = select_gfs_ranges(SAMPLE_GFS_IDX)
    ave_offsets = {
        i * _M
        for i, (param, level, forecast, _) in enumerate(SAMPLE_GFS_IDX_LINES)
        if "ave" in forecast
    }
    for offset in ave_offsets:
        assert not _covered(ranges, offset)


def test_select_gfs_ranges_full_inventory_stays_under_ceiling():
    """Regression for the live failure that killed every GFS lead: a full-size
    inventory (the wanted params also published at dozens of isobaric levels,
    ~800 KB per message, like the real ~450 MB pgrb2 file) must still resolve
    to a range set below the per-lead ceiling. Param-only selection matched
    all of those levels and exceeded it on every lead."""
    lines = []
    offset = 0
    number = 0
    msg = 800_000
    # The isobaric stack that used to be over-selected.
    for level in [f"{mb} mb" for mb in range(10, 1010, 25)]:
        for param in ("TMP", "RH", "UGRD", "VGRD", "TCDC"):
            number += 1
            lines.append(f"{number}:{offset}:d=2026082912:{param}:{level}:3 hour fcst:")
            offset += msg
    for param, level, forecast, _ in SAMPLE_GFS_IDX_LINES:
        number += 1
        lines.append(f"{number}:{offset}:d=2026082912:{param}:{level}:{forecast}:")
        offset += msg
    idx_text = "\n".join(lines) + "\n"

    ranges, params = select_gfs_ranges(idx_text)
    assert params == {p for p, _ in GFS_IDX_SELECTORS}
    total = selected_bytes(ranges)
    assert total is not None
    assert total < MAX_BYTES_PER_LEAD


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


LATITUDES = numpy.array([45.0, 48.0])
LONGITUDES = numpy.array([-55.0, -50.0])


def _message(name: str, value: float, units: str, scalar_coords: dict[str, float]) -> xarray.Dataset:
    """One decoded GRIB message the way cfgrib returns it: a single variable
    plus the scalar coordinates that describe the message's own level."""
    coords: dict[str, object] = {"latitude": LATITUDES, "longitude": LONGITUDES}
    coords.update(scalar_coords)
    array = xarray.DataArray(
        numpy.full((2, 2), value),
        dims=("latitude", "longitude"),
        coords=coords,
        attrs={"units": units, "GRIB_typeOfLevel": next(iter(scalar_coords), "surface")},
    )
    return xarray.Dataset({name: array})


def full_message_set() -> dict[str, xarray.Dataset]:
    return {
        "prmsl": _message("prmsl", 101300.0, "Pa", {"meanSea": 0.0}),
        "2t": _message("t2m", 288.15, "K", {"heightAboveGround": 2.0}),
        "2d": _message("d2m", 285.15, "K", {"heightAboveGround": 2.0}),
        "2r": _message("r2", 82.0, "%", {"heightAboveGround": 2.0}),
        "10u": _message("u10", 5.0, "m s**-1", {"heightAboveGround": 10.0}),
        "10v": _message("v10", -3.0, "m s**-1", {"heightAboveGround": 10.0}),
        "vis": _message("vis", 10000.0, "m", {"surface": 0.0}),
        "tcc": _message("tcc", 90.0, "%", {"atmosphere": 0.0}),
        "lcc": _message("lcc", 55.0, "%", {"lowCloudLayer": 0.0}),
        "mcc": _message("mcc", 25.0, "%", {"middleCloudLayer": 0.0}),
        "hcc": _message("hcc", 10.0, "%", {"highCloudLayer": 0.0}),
    }


def make_mock_open_grib(messages: dict[str, xarray.Dataset]):
    def mock_open_grib(path: Path, *, filter_by_keys=None):
        short_name = (filter_by_keys or {}).get("shortName")
        if short_name not in messages:
            raise GribError(f"no message for shortName {short_name!r}")
        return messages[short_name]

    return mock_open_grib


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


def _four_lead_client() -> PoliteClient:
    return make_mock_client(
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


def test_noaa_gfs_fetch_subset_ranges(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    client = _four_lead_client()
    adapter = NOAAS3Adapter(client=client)

    # Track download_ranges calls
    download_calls = []

    def mock_download_ranges(url, dest, ranges, max_bytes):
        download_calls.append((url, ranges, max_bytes))
        dest.write_bytes(b"dummy_grib_subset")
        return 1000

    monkeypatch.setattr(client, "download_ranges", mock_download_ranges)
    monkeypatch.setattr("ingest.adapters.noaa_s3.open_grib", make_mock_open_grib(full_message_set()))
    monkeypatch.setattr("ingest.adapters.noaa_s3.crop_to_bbox", lambda ds, bounds: ds)

    now = datetime(2026, 8, 29, 13, tzinfo=UTC)
    window = FetchWindow(now=now, back_hours=1, forward_hours=2)
    candidates = adapter.discover(window)

    result = adapter.fetch(candidates[0], window, tmp_path)
    assert result.source_id == "noaa-gfs"
    assert result.complete is True
    assert result.qc_passed is True
    assert len(download_calls) == 4
    assert len(result.artifacts) == 1

    # Every requested range set stays bounded and covers no distractor message.
    for _, ranges, max_bytes in download_calls:
        assert max_bytes == MAX_BYTES_PER_LEAD
        for offset in UNWANTED_OFFSETS:
            assert not any(start <= offset and (end is None or offset <= end) for start, end in ranges)

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

    # Provider-declared cloud strata: retrieved GFS LCDC/MCDC/HCDC, renamed to
    # canonical names, served in percent. These are provider fields, not a
    # derived classification.
    assert float(ds["cloud_low"].values[0, 0, 0]) == 55.0
    assert float(ds["cloud_middle"].values[0, 0, 0]) == 25.0
    assert float(ds["cloud_high"].values[0, 0, 0]) == 10.0
    assert float(ds["total_cloud"].values[0, 0, 0]) == 90.0
    for name in ("cloud_low", "cloud_middle", "cloud_high", "total_cloud"):
        assert ds[name].attrs["units"] == "percent"


def test_noaa_gfs_message_scalar_levels_survive_assembly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Regression for the message-scalar bug: each GRIB message carries its own
    scalar level coordinate (heightAboveGround = 2 for t2m, = 10 for u10, plus
    meanSea, surface and the three cloud layers). Assembling them into one
    dataset must not raise a MergeError, and the level each value was read at
    must survive into the variable's attrs rather than being discarded."""
    client = _four_lead_client()
    adapter = NOAAS3Adapter(client=client)

    monkeypatch.setattr(client, "download_ranges", lambda url, dest, ranges, max_bytes: dest.write_bytes(b"x") or 100)
    monkeypatch.setattr("ingest.adapters.noaa_s3.open_grib", make_mock_open_grib(full_message_set()))
    monkeypatch.setattr("ingest.adapters.noaa_s3.crop_to_bbox", lambda ds, bounds: ds)

    now = datetime(2026, 8, 29, 13, tzinfo=UTC)
    window = FetchWindow(now=now, back_hours=1, forward_hours=2)
    result = adapter.fetch(adapter.discover(window)[0], window, tmp_path)
    assert result.complete is True

    store = zarr.storage.ZipStore(str(result.artifacts[0].payload_path), mode="r")
    ds = xarray.open_zarr(store, consolidated=False)

    # The disagreeing scalar coordinates are gone from the coords...
    assert "heightAboveGround" not in ds.coords
    # ...and preserved per variable as the level actually read.
    assert ds["temperature_2m"].attrs["level_value"] == 2.0
    assert ds["wind_u_10m"].attrs["level_value"] == 10.0
    assert ds["cloud_low"].attrs["level_type"] == "lowCloudLayer"
    assert ds["cloud_high"].attrs["level_type"] == "highCloudLayer"


def test_noaa_gfs_fetch_missing_mandatory_field_comes_back_incomplete(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """The mirror image of the happy path: drop UGRD (wind_u_10m, mandatory in
    GFS_MANIFEST) from every lead's inventory. The run must come back
    ``complete=False`` with a ``missing_field:`` flag rather than silently
    publishing a run with a hole in it."""
    idx_without_ugrd = "\n".join(
        line for line in SAMPLE_GFS_IDX.splitlines() if ":UGRD:10 m above ground:" not in line
    ) + "\n"
    client = make_mock_client(
        {
            f"gfs.20260829/12/atmos/gfs.t12z.pgrb2.0p25.f{lead:03d}.idx": (200, idx_without_ugrd)
            for lead in range(4)
        }
    )
    adapter = NOAAS3Adapter(client=client)

    monkeypatch.setattr(client, "download_ranges", lambda url, dest, ranges, max_bytes: dest.write_bytes(b"x") or 100)
    messages = full_message_set()
    del messages["10u"]  # not in the inventory, so never even asked for
    monkeypatch.setattr("ingest.adapters.noaa_s3.open_grib", make_mock_open_grib(messages))
    monkeypatch.setattr("ingest.adapters.noaa_s3.crop_to_bbox", lambda ds, bounds: ds)

    now = datetime(2026, 8, 29, 13, tzinfo=UTC)
    window = FetchWindow(now=now, back_hours=1, forward_hours=2)
    candidates = adapter.discover(window)

    result = adapter.fetch(candidates[0], window, tmp_path)
    assert result.complete is False
    assert any(flag.startswith("missing_field:wind_u_10m") for flag in _flags_of(result))


def test_noaa_gfs_decode_failure_of_fetched_message_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A message the inventory carried and the adapter fetched but could not
    decode is a decode error, which must lower the verdict - it is not the
    same thing as an optional field the provider never published."""
    client = _four_lead_client()
    adapter = NOAAS3Adapter(client=client)

    monkeypatch.setattr(client, "download_ranges", lambda url, dest, ranges, max_bytes: dest.write_bytes(b"x") or 100)
    messages = full_message_set()
    del messages["lcc"]  # selected from the idx, then unreadable
    monkeypatch.setattr("ingest.adapters.noaa_s3.open_grib", make_mock_open_grib(messages))
    monkeypatch.setattr("ingest.adapters.noaa_s3.crop_to_bbox", lambda ds, bounds: ds)

    now = datetime(2026, 8, 29, 13, tzinfo=UTC)
    window = FetchWindow(now=now, back_hours=1, forward_hours=2)
    result = adapter.fetch(adapter.discover(window)[0], window, tmp_path)

    assert result.complete is False
    assert any(flag.startswith("decode_error:decode:") and ":lcc" in flag for flag in _flags_of(result))


def _flags_of(result) -> list[str]:
    provenance = result.artifacts[0].provenance
    return list(provenance["quality"]["flags"])


def test_decode_shortnames_and_selectors_agree():
    """Every shortName the decode loop asks cfgrib for maps back to an .idx
    parameter the range selection actually fetches, and vice versa."""
    assert set(GFS_DECODE_SHORTNAMES.values()) == {param for param, _ in GFS_IDX_SELECTORS}
