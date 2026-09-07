"""Deterministic native bytes; experiment, GOV-SPEC-004/GOV-SPEC-006."""
from datetime import UTC, datetime
import json

import numpy as np
import pytest
import zarr

from weather_api.weathernext_native import NativeLimits, NativeStatisticsReader, NativeUnavailable, ObjectIdentity
from weather_api.weathernext_query import WeatherNextSelection

FIELD = "total_cloud_cover_p90"
INIT = datetime(2026, 8, 1, tzinfo=UTC)
NOW = datetime(2026, 9, 1, tzinfo=UTC)


@pytest.fixture
def transport(tmp_path):
    arrays = {
        "init_time": (np.array(0, dtype="int64"), (), [], "days since 2026-08-01 00:00:00"),
        "lead_time": (np.array([5, 6, 7], dtype="int64"), (3,), ["lead_time"], "hours"),
        "lat_0p1": (np.array([47.6, 47.5], dtype="float64"), (2,), ["lat_0p1"], "degrees_north"),
        "lon_0p1": (np.array([307.2, 307.3], dtype="float64"), (2,), ["lon_0p1"], "degrees_east"),
        FIELD: (np.arange(12, dtype="float32").reshape(3, 2, 2) / 20, (1, 1, 2),
                ["lead_time", "lat_0p1", "lon_0p1"], "(0 - 1)"),
    }
    nodes = {}
    for name, (data, chunks, dims, unit) in arrays.items():
        a = zarr.create_array(tmp_path / name, data=data, chunks=chunks, dimension_names=dims,
                              config={"write_empty_chunks": True}, attributes={"units": unit}, fill_value=-9999 if name == FIELD else None)
        nodes[name] = json.loads((tmp_path / name / "zarr.json").read_bytes())
    class Transport:
        def __init__(self):
            self.calls = []
            self.nodes = nodes
            self.bodies = {str(p.relative_to(tmp_path)): p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
        def describe(self, bucket, name, *, timeout):
            relative = name.split("predictions.zarr/", 1)[1]
            body = self.body(relative)
            self.calls.append(("describe", relative))
            return ObjectIdentity(bucket, name, "42", "etag", len(body))
        def body(self, relative):
            if relative == 'zarr.json':
                return json.dumps({"zarr_format": 3, "node_type": "group", "consolidated_metadata": {"metadata": self.nodes}}).encode()
            return self.bodies[relative]
        def read(self, identity, *, max_bytes, timeout):
            assert identity.generation == "42"
            relative = identity.name.split("predictions.zarr/", 1)[1]
            self.calls.append(("read", relative))
            body = self.body(relative)
            assert len(body) <= max_bytes
            return body
    return Transport()


def selection():
    return WeatherNextSelection(INIT, datetime(2026, 8, 1, 6, tzinfo=UTC), 47.5, -52.7, (FIELD,))


def test_native_chunk_axes_time_statistic_and_bytes(transport):
    result = NativeStatisticsReader(transport).read_point(selection(), now=NOW)
    value = result.values[0]
    assert value.value == pytest.approx(.35)
    assert (value.statistic, value.unit, value.latitude, value.longitude) == ('p90', '(0 - 1)', 47.5, pytest.approx(-52.7))
    assert result.initialization == INIT and result.valid_time == selection().valid_time
    assert result.pressure_level is None and result.member is None
    assert result.received_bytes == sum(i.size for i in result.objects)
    assert [p for op, p in transport.calls if op == 'read' and p.startswith(FIELD)] == [FIELD + '/c/1/1/0']


def test_missing_chunk_is_not_implicit_zarr_fill(transport):
    del transport.bodies[FIELD + '/c/1/1/0']
    with pytest.raises(NativeUnavailable):
        NativeStatisticsReader(transport).read_point(selection(), now=NOW)


@pytest.mark.parametrize('mutation', ['unit', 'member', 'huge_chunk', 'lead_unit', 'init_epoch'])
def test_refuses_native_contract_drift(transport, mutation):
    if mutation == 'unit': transport.nodes[FIELD]['attributes']['units'] = '%'
    if mutation == 'member': transport.nodes[FIELD]['dimension_names'][0] = 'sample'
    if mutation == 'huge_chunk': transport.nodes[FIELD]['chunk_grid']['configuration']['chunk_shape'] = [1, 100000, 100000]
    if mutation == 'lead_unit': transport.nodes['lead_time']['attributes']['units'] = 'seconds'
    if mutation == 'init_epoch': transport.nodes['init_time']['attributes']['units'] = 'days since 2025-08-01'
    with pytest.raises(NativeUnavailable):
        NativeStatisticsReader(transport).read_point(selection(), now=NOW)
    assert not any(p.startswith(FIELD) for _, p in transport.calls)


def test_metadata_budget_prevents_read(transport):
    with pytest.raises(NativeUnavailable):
        NativeStatisticsReader(transport, limits=NativeLimits(metadata_bytes=1)).read_point(selection(), now=NOW)
    assert len(transport.calls) == 1


def test_historical_gate_prevents_all_operations(transport):
    with pytest.raises(NativeUnavailable):
        NativeStatisticsReader(transport).read_point(selection(), now=datetime(2026, 8, 3, 6, tzinfo=UTC))
    assert transport.calls == []


def test_fill_is_preserved(transport, tmp_path):
    # Present chunk containing a finite provider sentinel, not an absent object.
    target = tmp_path / 'masked'
    a = zarr.create_array(target, data=np.array([[[.3, -9999]]], dtype='float32'), chunks=(1, 1, 2), fill_value=-9999)
    transport.bodies[FIELD + '/c/1/1/0'] = (target / 'c/0/0/0').read_bytes()
    assert NativeStatisticsReader(transport).read_point(selection(), now=NOW).values[0].value is None


def test_received_and_operation_caps(transport):
    for limits in (NativeLimits(received_bytes=10), NativeLimits(operations=2)):
        with pytest.raises(NativeUnavailable):
            NativeStatisticsReader(transport, limits=limits).read_point(selection(), now=NOW)


@pytest.mark.parametrize('fault', ['generation', 'bucket', 'size'])
def test_identity_and_truncation_fail_closed(transport, fault):
    original = transport.describe
    def describe(bucket, name, *, timeout):
        item = original(bucket, name, timeout=timeout)
        if fault == 'generation': return ObjectIdentity(bucket, name, '', item.etag, item.size)
        if fault == 'bucket': return ObjectIdentity('weathernext3_spatial', name, '42', item.etag, item.size)
        return ObjectIdentity(bucket, name, '42', item.etag, item.size + 1)
    transport.describe = describe
    with pytest.raises(NativeUnavailable):
        NativeStatisticsReader(transport).read_point(selection(), now=NOW)


def test_nan_is_preserved(transport, tmp_path):
    target = tmp_path / 'nan'
    zarr.create_array(target, data=np.array([[[.3, np.nan]]], dtype='float32'), chunks=(1, 1, 2))
    transport.bodies[FIELD + '/c/1/1/0'] = (target / 'c/0/0/0').read_bytes()
    assert NativeStatisticsReader(transport).read_point(selection(), now=NOW).values[0].value is None
