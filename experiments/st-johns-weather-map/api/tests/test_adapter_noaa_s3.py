"""Unit tests for NOAA GFS S3 adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import os

import httpx
import numpy
import pytest
import xarray
import zarr

from ingest.adapters.noaa_s3 import (
    GFS_DECODE_SPECS,
    GFS_MANIFEST,
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
    # Upper-air seeing/transparency messages, with the neighbouring isobaric
    # levels as distractors: only 200 and 300 mb are declared.
    ("UGRD", "200 mb", "3 hour fcst", True),
    ("VGRD", "200 mb", "3 hour fcst", True),
    ("UGRD", "250 mb", "3 hour fcst", False),
    ("VGRD", "250 mb", "3 hour fcst", False),
    ("UGRD", "300 mb", "3 hour fcst", True),
    ("VGRD", "300 mb", "3 hour fcst", True),
    # Cloud steering winds, again with a neighbouring level as a distractor
    # and HGT at 500 mb above: the level alone never selects a message.
    ("UGRD", "850 mb", "3 hour fcst", True),
    ("VGRD", "850 mb", "3 hour fcst", True),
    ("UGRD", "800 mb", "3 hour fcst", False),
    ("VGRD", "800 mb", "3 hour fcst", False),
    ("UGRD", "700 mb", "3 hour fcst", True),
    ("VGRD", "700 mb", "3 hour fcst", True),
    ("UGRD", "500 mb", "3 hour fcst", True),
    ("VGRD", "500 mb", "3 hour fcst", True),
    # Vertical velocity at the same three steering levels, read by the
    # computed-residual interpolation methods to re-time growth and decay
    # inside an interval (the `development-residual` module that first asked
    # for it was deleted on 2026-09-01; `residual-advection` and its
    # generative sibling are what read omega now). DZDT is the geometric vertical velocity
    # GFS publishes beside every one of these messages; it is a deliberate
    # distractor here because the adapter takes omega (VVEL, Pa s-1) only -
    # mixing the two conventions is how a sign error would get in.
    ("VVEL", "850 mb", "3 hour fcst", True),
    ("DZDT", "850 mb", "3 hour fcst", False),
    ("VVEL", "800 mb", "3 hour fcst", False),
    ("VVEL", "700 mb", "3 hour fcst", True),
    ("DZDT", "700 mb", "3 hour fcst", False),
    ("VVEL", "500 mb", "3 hour fcst", True),
    ("DZDT", "500 mb", "3 hour fcst", False),
    # RH and temperature at the same three levels, for the humidity-based
    # low-cloud diagnosis. The 800 mb neighbours and the 2 m screen messages
    # above are the distractors that matter here: `TMP` and `RH` are the two
    # parameters GFS publishes at BOTH a screen level and every isobaric
    # level, so a param-only or level-only match mixes them.
    ("RH", "850 mb", "3 hour fcst", True),
    ("TMP", "850 mb", "3 hour fcst", True),
    ("RH", "800 mb", "3 hour fcst", False),
    ("TMP", "800 mb", "3 hour fcst", False),
    ("RH", "700 mb", "3 hour fcst", True),
    ("TMP", "700 mb", "3 hour fcst", True),
    ("RH", "500 mb", "3 hour fcst", True),
    ("TMP", "500 mb", "3 hour fcst", True),
    ("PWAT", "entire atmosphere (considered as a single layer)", "3 hour fcst", True),
    # A trailing unwanted message so the last selected range is closed, as in
    # the real inventory where hundreds of messages follow PWAT.
    ("HGT", "1000 mb", "3 hour fcst", False),
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
    ranges, pairs = select_gfs_ranges(SAMPLE_GFS_IDX)
    assert pairs == set(GFS_IDX_SELECTORS)
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

    ranges, pairs = select_gfs_ranges(idx_text)
    assert pairs == set(GFS_IDX_SELECTORS)
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


def _isobaric_message(name: str, values_by_level: dict[int, float], units: str) -> xarray.Dataset:
    """A two-level isobaric message the way cfgrib returns it: one variable on
    an ``isobaricInhPa`` dimension."""
    levels = numpy.array(sorted(values_by_level), dtype=float)
    data = numpy.stack([numpy.full((2, 2), values_by_level[int(level)]) for level in levels])
    array = xarray.DataArray(
        data,
        dims=("isobaricInhPa", "latitude", "longitude"),
        coords={"isobaricInhPa": levels, "latitude": LATITUDES, "longitude": LONGITUDES},
        attrs={"units": units, "GRIB_typeOfLevel": "isobaricInhPa"},
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
        "u": _isobaric_message("u", {200: 45.0, 300: 35.0, 500: 22.0, 700: 14.0, 850: 9.0}, "m s**-1"),
        "v": _isobaric_message("v", {200: -12.0, 300: -8.0, 500: -5.0, 700: -3.0, 850: -2.0}, "m s**-1"),
        # Omega at the three steering levels, in the units ecCodes spells for
        # WMO 0/2/8. Negative is ascent, which is why the values are signed.
        "w": _isobaric_message("w", {500: -0.12, 700: -0.31, 850: 0.18}, "Pa s**-1"),
        # RH and temperature on the same three levels. Both come back under
        # the bare shortNames `r` and `t`, which is exactly why the decode
        # spec pins typeOfLevel=isobaricInhPa: the screen-level twins above
        # decode as `2r` and `2t` only because cfgrib was given a filter.
        "r": _isobaric_message("r", {500: 40.0, 700: 78.0, 850: 92.0}, "%"),
        "t": _isobaric_message("t", {500: 253.15, 700: 268.15, 850: 278.15}, "K"),
        "pwat": _message("pwat", 12.5, "kg m**-2", {"atmosphereSingleLayer": 0.0}),
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
    assert len(result.artifacts) == 2

    # Every requested range set stays bounded and covers no distractor message.
    for _, ranges, max_bytes in download_calls:
        assert max_bytes == MAX_BYTES_PER_LEAD
        for offset in UNWANTED_OFFSETS:
            assert not any(start <= offset and (end is None or offset <= end) for start, end in ranges)

    artifact = result.artifacts[0]
    assert artifact.logical_name == "surface"
    assert artifact.payload_path.exists()
    assert artifact.provenance["evidence_classes"] == ["retrieved"], "a retrieved artifact declares how its values came to exist"

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

    # Precipitable water is a column total stored beside the surface set,
    # normalized only in unit spelling.
    assert float(ds["precipitable_water"].values[0, 0, 0]) == 12.5
    assert ds["precipitable_water"].attrs["units"] == "kg m-2"
    # The jet-level winds live in their own artifact, flat and level-suffixed.
    for name in ("wind_u_200hPa", "wind_v_200hPa", "wind_u_300hPa", "wind_v_300hPa"):
        assert name not in ds.data_vars

    upper = result.artifacts[1]
    assert upper.logical_name == "upper_air"
    upper_store = zarr.storage.ZipStore(str(upper.payload_path), mode="r")
    upper_ds = xarray.open_zarr(upper_store, consolidated=False)
    assert "isobaricInhPa" not in upper_ds.dims
    assert float(upper_ds["wind_u_200hPa"].values[0, 0, 0]) == 45.0
    assert float(upper_ds["wind_v_200hPa"].values[0, 0, 0]) == -12.0
    assert float(upper_ds["wind_u_300hPa"].values[0, 0, 0]) == 35.0
    assert float(upper_ds["wind_v_300hPa"].values[0, 0, 0]) == -8.0
    for name in ("wind_u_200hPa", "wind_u_300hPa"):
        assert upper_ds[name].attrs["units"] == "m s-1"


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


def test_decode_specs_and_selectors_agree():
    """Every (param, level) pair a decode spec claims to justify its open is a
    pair the range selection actually fetches, and vice versa - so nothing is
    decoded that was not selected and nothing is selected that nothing reads."""
    spec_pairs = {pair for _, _, idx_pairs in GFS_DECODE_SPECS for pair in idx_pairs}
    assert spec_pairs == set(GFS_IDX_SELECTORS)


def test_noaa_gfs_missing_pwat_is_optional_absence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A lead whose inventory carries no PWAT message publishes without
    ``precipitable_water`` and the run stays complete: optional inventory
    absence is not a failure and is never filled in."""
    idx_without_pwat = "\n".join(
        line for line in SAMPLE_GFS_IDX.splitlines() if ":PWAT:" not in line
    ) + "\n"
    client = make_mock_client(
        {
            f"gfs.20260829/12/atmos/gfs.t12z.pgrb2.0p25.f{lead:03d}.idx": (200, idx_without_pwat)
            for lead in range(4)
        }
    )
    adapter = NOAAS3Adapter(client=client)
    monkeypatch.setattr(client, "download_ranges", lambda url, dest, ranges, max_bytes: dest.write_bytes(b"x") or 100)
    messages = full_message_set()
    del messages["pwat"]  # not in the inventory, so never even asked for
    monkeypatch.setattr("ingest.adapters.noaa_s3.open_grib", make_mock_open_grib(messages))
    monkeypatch.setattr("ingest.adapters.noaa_s3.crop_to_bbox", lambda ds, bounds: ds)

    now = datetime(2026, 8, 29, 13, tzinfo=UTC)
    window = FetchWindow(now=now, back_hours=1, forward_hours=2)
    result = adapter.fetch(adapter.discover(window)[0], window, tmp_path)

    assert result.complete is True
    store = zarr.storage.ZipStore(str(result.artifacts[0].payload_path), mode="r")
    ds = xarray.open_zarr(store, consolidated=False)
    assert "precipitable_water" not in ds.data_vars


def test_noaa_gfs_single_isobaric_level_still_publishes_that_level(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Only the 200 mb wind messages in the inventory: the 200 hPa fields
    publish, the 300 hPa fields are simply absent - never guessed from the
    level that did arrive."""
    idx_without_300 = "\n".join(
        line for line in SAMPLE_GFS_IDX.splitlines() if ":300 mb:" not in line
    ) + "\n"
    client = make_mock_client(
        {
            f"gfs.20260829/12/atmos/gfs.t12z.pgrb2.0p25.f{lead:03d}.idx": (200, idx_without_300)
            for lead in range(4)
        }
    )
    adapter = NOAAS3Adapter(client=client)
    monkeypatch.setattr(client, "download_ranges", lambda url, dest, ranges, max_bytes: dest.write_bytes(b"x") or 100)
    messages = full_message_set()
    # cfgrib would decode a single-level message with a scalar coordinate.
    single_u = _isobaric_message("u", {200: 45.0}, "m s**-1")
    messages["u"] = xarray.Dataset({"u": single_u["u"].isel(isobaricInhPa=0)})
    messages["v"] = xarray.Dataset({"v": _isobaric_message("v", {200: -12.0}, "m s**-1")["v"].isel(isobaricInhPa=0)})
    monkeypatch.setattr("ingest.adapters.noaa_s3.open_grib", make_mock_open_grib(messages))
    monkeypatch.setattr("ingest.adapters.noaa_s3.crop_to_bbox", lambda ds, bounds: ds)

    now = datetime(2026, 8, 29, 13, tzinfo=UTC)
    window = FetchWindow(now=now, back_hours=1, forward_hours=2)
    result = adapter.fetch(adapter.discover(window)[0], window, tmp_path)

    upper = next(a for a in result.artifacts if a.logical_name == "upper_air")
    upper_ds = xarray.open_zarr(zarr.storage.ZipStore(str(upper.payload_path), mode="r"), consolidated=False)
    assert float(upper_ds["wind_u_200hPa"].values[0, 0, 0]) == 45.0
    assert "wind_u_300hPa" not in upper_ds.data_vars
    assert "wind_v_300hPa" not in upper_ds.data_vars

@pytest.mark.live_smoke
@pytest.mark.skipif(os.environ.get("WEATHER_LIVE_SMOKE") != "1", reason="set WEATHER_LIVE_SMOKE=1 to hit the noaa-gfs-bdp-pds bucket")
def test_live_gfs_idx_carries_upper_air_messages_under_the_ceiling():
    """Against the real bucket: a recent cycle's f000 inventory carries every
    declared (param, level) message - the five upper-air additions included -
    and the merged selected span stays under MAX_BYTES_PER_LEAD as measured,
    not assumed."""
    from datetime import timedelta

    from ingest.grib import selected_bytes

    client = PoliteClient()
    adapter = NOAAS3Adapter(client=client)
    window = FetchWindow(now=datetime.now(UTC).replace(minute=0, second=0, microsecond=0))
    candidate = adapter.discover(window)[0]
    idx_text = client.get_text(candidate.urls[0])

    ranges, pairs = select_gfs_ranges(idx_text)
    assert pairs == set(GFS_IDX_SELECTORS), f"missing from live inventory: {set(GFS_IDX_SELECTORS) - pairs}"
    total = selected_bytes(ranges)
    assert total is not None
    assert total < MAX_BYTES_PER_LEAD, f"merged span {total} bytes exceeds the {MAX_BYTES_PER_LEAD} ceiling"


def test_isobaric_rh_and_temperature_publish_beside_the_screen_fields(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """`t` and `r` at pressure must not collide with, or merge into, `2t`/`2r`.

    GFS publishes TMP and RH at both 2 m above ground and every isobaric
    level. The decode spec pins ``typeOfLevel=isobaricInhPa`` on the isobaric
    open for exactly that reason; this asserts the outcome - six suffixed
    upper-level variables AND the two screen-level ones, all in one dataset.
    """
    client = _four_lead_client()
    adapter = NOAAS3Adapter(client=client)
    monkeypatch.setattr(client, "download_ranges", lambda url, dest, ranges, max_bytes: dest.write_bytes(b"x") or 100)
    monkeypatch.setattr("ingest.adapters.noaa_s3.open_grib", make_mock_open_grib(full_message_set()))
    monkeypatch.setattr("ingest.adapters.noaa_s3.crop_to_bbox", lambda ds, bounds: ds)

    now = datetime(2026, 8, 29, 13, tzinfo=UTC)
    window = FetchWindow(now=now, back_hours=1, forward_hours=2)
    result = adapter.fetch(adapter.discover(window)[0], window, tmp_path)
    assert result.complete is True

    surface = next(a for a in result.artifacts if a.logical_name == "surface")
    with zarr.storage.ZipStore(str(surface.payload_path), mode="r") as store:
        dataset = xarray.open_zarr(store, consolidated=False).load()

    for level in (850, 700, 500):
        assert f"relative_humidity_{level}hPa" in dataset
        assert f"temperature_{level}hPa" in dataset
    # The screen-level twins survive untouched and keep their own values.
    assert float(dataset["relative_humidity_2m"].isel(valid_time=0).mean()) == pytest.approx(82.0)
    assert float(dataset["relative_humidity_850hPa"].isel(valid_time=0).mean()) == pytest.approx(92.0)
    # Temperature is normalised to degC on every level, screen and isobaric.
    assert float(dataset["temperature_850hPa"].isel(valid_time=0).mean()) == pytest.approx(5.0)
    assert float(dataset["temperature_500hPa"].isel(valid_time=0).mean()) == pytest.approx(-20.0)
    assert dataset["temperature_500hPa"].attrs["units"] == "degC"
    assert dataset["relative_humidity_700hPa"].attrs["units"] == "percent"


def test_gfs_relative_humidity_carries_its_measured_saturation_phase(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """GRIB2 0/1/1 codes no phase key, so the measurement travels in attrs.

    GFS divides by a mixed-phase saturation (linear ice->water between 253.16 K
    and 273.16 K, measured 2026-09-01); ECCC divides by liquid water. A
    threshold scheme has to be able to tell them apart, and the only place that
    information can live is the variable's own attrs.
    """
    client = _four_lead_client()
    adapter = NOAAS3Adapter(client=client)
    monkeypatch.setattr(client, "download_ranges", lambda url, dest, ranges, max_bytes: dest.write_bytes(b"x") or 100)
    monkeypatch.setattr("ingest.adapters.noaa_s3.open_grib", make_mock_open_grib(full_message_set()))
    monkeypatch.setattr("ingest.adapters.noaa_s3.crop_to_bbox", lambda ds, bounds: ds)

    now = datetime(2026, 8, 29, 13, tzinfo=UTC)
    window = FetchWindow(now=now, back_hours=1, forward_hours=2)
    result = adapter.fetch(adapter.discover(window)[0], window, tmp_path)

    surface = next(a for a in result.artifacts if a.logical_name == "surface")
    with zarr.storage.ZipStore(str(surface.payload_path), mode="r") as store:
        dataset = xarray.open_zarr(store, consolidated=False).load()

    from ingest.derive.weong_low_cloud import assert_liquid_water_rh
    from ingest.grib import RH_PHASE_MIXED_LINEAR_253K_273K

    for level in (850, 700, 500):
        attrs = dataset[f"relative_humidity_{level}hPa"].attrs
        assert attrs["rh_phase_convention"] == RH_PHASE_MIXED_LINEAR_253K_273K
        assert "SPFH" in attrs["rh_phase_basis"]
        # And the ECCC-calibrated WEonG table refuses it rather than silently
        # applying a threshold it was not calibrated for.
        with pytest.raises(ValueError, match="liquid water"):
            assert_liquid_water_rh(dataset[f"relative_humidity_{level}hPa"])


def test_isobaric_rh_and_temperature_are_optional_not_mandatory():
    """A level the inventory omits costs the diagnosis, never the artifact."""
    optional = {field.name for field in GFS_MANIFEST.fields if field.optional}
    for level in (850, 700, 500):
        assert f"relative_humidity_{level}hPa" in optional
        assert f"temperature_{level}hPa" in optional


@pytest.mark.skipif(os.environ.get("WEATHER_LIVE_SMOKE") != "1", reason="set WEATHER_LIVE_SMOKE=1 to hit the noaa-gfs-bdp-pds bucket")
def test_live_gfs_rh_is_mixed_phase_and_eccc_rh_is_not():
    """The claim in GFS_RH_PHASE_BASIS, re-measured against the live bucket.

    Reconstructs vapour pressure from the message's own SPFH at 500 mb and
    checks it against Buck (1981) saturation over ice and over water below
    -25 degC. Measured 2026-09-01: matches ice to 0.24 %, misses water by
    24.5 %. Fails loudly if NCEP ever changes the convention, because every
    RH threshold downstream is calibrated against a phase.
    """
    eccodes = pytest.importorskip("eccodes")
    import tempfile

    from ingest.grib import ByteRange, parse_idx

    client = PoliteClient()
    adapter = NOAAS3Adapter(client=client)
    window = FetchWindow(now=datetime.now(UTC).replace(minute=0, second=0, microsecond=0))
    candidate = adapter.discover(window)[0]
    detail = candidate.detail
    base = f"{adapter._base_url}/gfs.{detail['date_str']}/{detail['cycle']}/atmos/gfs.t{detail['cycle']}z.pgrb2.0p25.f003"
    records = parse_idx(client.get_text(base + ".idx"))
    wanted = {"RH": None, "TMP": None, "SPFH": None}
    for record in records:
        if record.param.upper() in wanted and record.level.lower() == "500 mb" and "hour fcst" in record.forecast:
            wanted[record.param.upper()] = record
    if any(value is None for value in wanted.values()):
        pytest.skip("live inventory does not carry RH/TMP/SPFH at 500 mb")

    def read(record) -> numpy.ndarray:
        response = client.get(base, headers={"Range": ByteRange(record.offset, record.end).header})
        with tempfile.NamedTemporaryFile(suffix=".grib2") as handle:
            handle.write(response.content)
            handle.flush()
            with open(handle.name, "rb") as grib:
                gid = eccodes.codes_grib_new_from_file(grib)
                try:
                    return numpy.asarray(eccodes.codes_get_values(gid), dtype=float)
                finally:
                    eccodes.codes_release(gid)

    q, temperature, rh = read(wanted["SPFH"]), read(wanted["TMP"]), read(wanted["RH"])
    vapour = q * 50000.0 / (0.622 + 0.378 * q)
    celsius = temperature - 273.15
    over_water = 611.21 * numpy.exp((18.678 - celsius / 234.5) * (celsius / (257.14 + celsius)))
    over_ice = 611.15 * numpy.exp((23.036 - celsius / 333.7) * (celsius / (279.82 + celsius)))
    cold = (celsius < -25.0) & (rh > 50.0)
    assert cold.sum() > 1000
    bias_ice = float(numpy.mean(100 * vapour[cold] / over_ice[cold] - rh[cold]))
    bias_water = float(numpy.mean(100 * vapour[cold] / over_water[cold] - rh[cold]))
    print(f"GFS 500 mb RH below -25 degC: bias vs ice {bias_ice:+.2f} %, vs water {bias_water:+.2f} %")
    assert abs(bias_ice) < 2.0, "GFS RH no longer matches saturation over ice below -25 degC"
    assert abs(bias_water) > 10.0, "GFS RH now matches saturation over water; the declared convention is wrong"
