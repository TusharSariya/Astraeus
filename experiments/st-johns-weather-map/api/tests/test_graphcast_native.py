"""Real HDF5/range experiment fixtures; GOV-SPEC-004/GOV-SPEC-006."""
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from io import BytesIO

import h5py
import httpx
import numpy as np
import pytest

from weather_api.graphcast_native import GraphCastObject, RangeRefused, read_point

INIT = datetime(2026, 9, 6, 12, tzinfo=UTC)
KEY = "GRAP_v100_GFS/2026/0906/GRAP_v100_GFS_2026090612_f000_f240_06.nc"


@pytest.fixture
def native():
    body = BytesIO()
    with h5py.File(body, "w") as f:
        f.attrs.update(Conventions="CF-1.8", model_name="graphcast", version="3_2025-02-20",
                       initialization_model="GFS", initialization_time="2026-09-06T12:00:00",
                       first_forecast_hour="0", last_forecast_hour="240", forecast_hour_step="6")
        for name, data, unit in (
            ("time", np.array(INIT.timestamp() + np.arange(41)*21600, dtype="int32"), "seconds since 1970-1-1"),
            ("latitude", np.array(90-np.arange(721)*.25, dtype="float32"), "degree"),
            ("longitude", np.array(np.arange(1440)*.25, dtype="float32"), "degree"),
        ):
            a = f.create_dataset(name, data=data, compression="gzip", shuffle=True)
            a.attrs["units"] = unit
            a.make_scale(name)
        f["time"].attrs["calendar"] = "standard"
        for name, unit, value in (("t2", "K", 281.25), ("msl", "Pa", 101234.0)):
            a = f.create_dataset(name, shape=(41,721,1440), chunks=(1,721,1440),
                                 dtype="float32", compression="gzip", shuffle=True, fillvalue=-9999)
            a.attrs.update(units=unit, _FillValue=np.float32(-9999))
            for i, dim in enumerate(("time", "latitude", "longitude")):
                a.dims[i].attach_scale(f[dim])
            a[1,170,1229] = value
    return body.getvalue()


def transport(body, *, etag='"abc-2"', status=206):
    calls = []
    def handle(request):
        calls.append(request)
        start, end = map(int, request.headers["range"][6:].split("-"))
        assert request.headers["if-match"] == '"abc-2"'
        assert "authorization" not in request.headers
        return httpx.Response(status, headers={"Content-Range": f"bytes {start}-{end}/{len(body)}",
            "Content-Length": str(end-start+1), "ETag": etag},
            stream=httpx.ByteStream(body[start:end+1]))
    return httpx.MockTransport(handle), calls


def run(body, **kwargs):
    wire, calls = transport(body)
    result = read_point(GraphCastObject(KEY, len(body), '"abc-2"'), INIT+timedelta(hours=6),
                        47.51, -52.7, transport=wire, **kwargs)
    return result, calls


def mutate(body, change):
    data = BytesIO(body)
    with h5py.File(data, "r+") as f:
        change(f)
    return data.getvalue()


def test_real_hdf5_selected_values_and_pinned_receipts(native):
    result, calls = run(native)
    assert result.values == (("t2", 281.25, "K"), ("msl", 101234, "Pa"))
    assert (result.latitude,result.longitude) == (47.5,-52.75)
    assert result.initialization == INIT and result.valid_time == INIT+timedelta(hours=6)
    assert result.initializer == "GFS" and result.native_version == "3_2025-02-20"
    assert result.requests == len(calls) <= 128
    assert result.received_bytes == sum(r["bytes"] for r in result.receipts) <= 8*1024**2
    assert all(r["object_identity"] == result.object_identity for r in result.receipts)


@pytest.mark.parametrize("change", [
    lambda f: f.attrs.__setitem__("model_name", "panguweather"),
    lambda f: f.attrs.__setitem__("initialization_model", "IFS"),
    lambda f: f.attrs.__setitem__("initialization_time", "2026-09-06T00:00:00"),
    lambda f: f["t2"].attrs.__setitem__("units", "C"),
    lambda f: f["time"].attrs.__setitem__("calendar", "360_day"),
    lambda f: f["time"].__setitem__(1, int(INIT.timestamp()+3*3600)),
    lambda f: f["longitude"].__setitem__(0, .1),
    lambda f: f["latitude"].attrs.__setitem__("units", "radians"),
    lambda f: f["t2"].attrs.__setitem__("scale_factor", .5),
    lambda f: f["t2"].dims[1].detach_scale(f["latitude"]),
])
def test_native_contract_drift_refused(native, change):
    with pytest.raises(RangeRefused):
        run(mutate(native, change))


@pytest.mark.parametrize("raw", [-9999, np.nan, np.inf])
def test_native_missing_preserved(native, raw):
    result, _ = run(mutate(native, lambda f: f["t2"].__setitem__((1,170,1229), raw)))
    assert result.values[0] == ("t2", None, "K")
    assert result.values[1][1] == 101234


@pytest.mark.parametrize("options", [{"etag": '"def"'}, {"status": 200}])
def test_unpinned_or_unranged_response_refused(native, options):
    wire, calls = transport(native, **options)
    with pytest.raises(RangeRefused):
        read_point(GraphCastObject(KEY,len(native),'"abc-2"'), INIT, 47.5,-52.7,transport=wire)
    assert len(calls) == 1


def test_unsupported_time_before_network(native):
    wire, calls = transport(native)
    with pytest.raises(RangeRefused):
        read_point(GraphCastObject(KEY,len(native),'"abc-2"'), INIT+timedelta(hours=3),47.5,-52.7,transport=wire)
    assert not calls


def test_initializer_and_model_identity_are_distinct(native):
    source = GraphCastObject(KEY,len(native),'"abc-2"')
    assert source.identity != replace(source,key=KEY.replace("GFS","IFS")).identity
    for key in (KEY.replace("GRAP","AURO"), KEY.replace("v100","v200"), KEY.replace("/0906/","/0907/")):
        with pytest.raises(ValueError):
            GraphCastObject(key,len(native),'"abc-2"')


def test_unallocated_field_chunk_is_refused(native):
    wire, _ = transport(native)
    with pytest.raises(RangeRefused):
        read_point(GraphCastObject(KEY,len(native),'"abc-2"'),INIT,47.5,-52.7,transport=wire)


def test_distinct_ifs_initializer_decodes_without_substitution(native):
    body = mutate(native, lambda f: f.attrs.__setitem__("initialization_model", "IFS"))
    wire, calls = transport(body)
    result = read_point(GraphCastObject(KEY.replace("GFS","IFS"),len(body),'"abc-2"'),
                        INIT+timedelta(hours=6),47.5,-52.7,fields=("t2",),transport=wire)
    assert result.initializer == "IFS" and result.values == (("t2",281.25,"K"),)
    assert all("GRAP_v100_IFS" in str(call.url) for call in calls)


def test_multiple_plane_chunk_refused(native):
    def change(f):
        del f["t2"]
        f.create_dataset("t2",shape=(41,721,1440),chunks=(2,721,1440),
                         dtype="float32",compression="gzip").attrs["units"]="K"
    with pytest.raises(RangeRefused):
        run(mutate(native,change))
