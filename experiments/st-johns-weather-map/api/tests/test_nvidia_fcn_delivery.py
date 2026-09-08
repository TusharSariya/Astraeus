"""Synthetic plumbing tests; no inference, model download or scientific proof."""
from dataclasses import replace
import io
from pathlib import Path
import tarfile
import time

import httpx
import numpy as np
import pytest

from weather_api import nvidia_fcn_delivery as fcn

INIT = fcn.Initialization("caller ERA5", "run-20260101", "2026-01-01T00:00:00Z",
                          ("caller contract v1",), "a" * 64)
DEPLOY = fcn.Deployment("http://localhost:8000", "b" * 64, "c" * 64, "runtime-v1", "caller GPU")


def npy_header(shape=fcn.INPUT_SHAPE, dtype="float32"):
    stream = io.BytesIO()
    np.lib.format.write_array_header_1_0(stream, {
        "descr": np.dtype(dtype).str, "fortran_order": False, "shape": shape})
    return stream.getvalue()


@pytest.fixture
def tiny_native(monkeypatch):
    # Deliberately reduced fixture dimensions, never a native inference claim.
    monkeypatch.setattr(fcn, "INPUT_SHAPE", (1, 1, 2, 2, 2))
    monkeypatch.setattr(fcn, "NATIVE_BYTES", 32)
    monkeypatch.setattr(fcn, "MAX_NPY_BYTES", 65568)


def fixture_input(tmp_path):
    path = tmp_path / "input.npy"
    np.save(path, np.zeros(fcn.INPUT_SHAPE, dtype=np.float32))
    return path


def archive_bytes(names=("000_000.npy", "006_000.npy"), *, kind=tarfile.REGTYPE,
                  array=None):
    data = io.BytesIO()
    np.save(data, np.zeros(fcn.INPUT_SHAPE, dtype=np.float32) if array is None else array)
    body = io.BytesIO()
    with tarfile.open(fileobj=body, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for name in names:
            member = tarfile.TarInfo(name)
            member.type = kind
            member.size = len(data.getvalue()) if kind == tarfile.REGTYPE else 0
            archive.addfile(member, io.BytesIO(data.getvalue()))
    return body.getvalue()


class Chunks(httpx.SyncByteStream):
    def __init__(self, data):
        self.data = data
    def __iter__(self):
        yield self.data


def call(tmp_path, body, **response_args):
    def handler(request):
        assert request.method == "POST"
        assert str(request.url) == "http://localhost:8000/v1/infer"
        payload = request.read()
        assert b'name="input_time"' in payload and INIT.input_time.encode() in payload
        assert b'name="simulation_length"\r\n\r\n1\r\n' in payload
        assert b'name="input_array"' in payload
        return httpx.Response(response_args.pop("status", 200), stream=Chunks(body),
            headers=response_args.pop("headers", {"content-type": "application/x-tar"}), **response_args)
    return fcn.infer(input_array=fixture_input(tmp_path), initialization=INIT,
                     deployment=DEPLOY, simulation_length=1,
                     output_archive=tmp_path / "output.tar",
                     transport=httpx.MockTransport(handler))


def test_native_constants_and_validated_sparse_full_input(tmp_path):
    assert fcn.INPUT_SHAPE == (1, 1, 73, 721, 1440)
    path = tmp_path / "native.npy"
    with path.open("wb") as stream:
        stream.write(npy_header())
        stream.truncate(stream.tell() + fcn.NATIVE_BYTES)
    with (tmp_path / "snapshot").open("w+b") as snapshot:
        digest = fcn._copy_input(path, snapshot, time.monotonic() + 30)
        assert len(digest) == 64
        assert snapshot.read(6) == b"\x93NUMPY"


def test_complete_delivery(tiny_native, tmp_path):
    result = call(tmp_path, archive_bytes())
    assert result.archive.exists()
    assert [m.lead_hours for m in result.members] == [0, 6]
    assert result.members[1].valid_time == "2026-01-01T06:00:00Z"
    assert result.initialization == INIT and result.deployment == DEPLOY
    assert result.scientific_status == "native-channels-unmapped"
    assert not result.critical_cloud_eligible and result.centre_votes == 0
    assert result.provenance_kind == "generated-here"


@pytest.mark.parametrize("names,kind", [
    (("../000_000.npy",), tarfile.REGTYPE),
    (("/000_000.npy",), tarfile.REGTYPE),
    (("000_000.npy", "000_000.npy"), tarfile.REGTYPE),
    (("000_000.npy", "006_001.npy"), tarfile.REGTYPE),
    (("000_000.npy", "012_000.npy"), tarfile.REGTYPE),
    (("000_000.npy",), tarfile.REGTYPE),
    (("000_000.npy",), tarfile.SYMTYPE),
    (("000_000.npy",), tarfile.LNKTYPE),
    (("000_000.npy",), tarfile.DIRTYPE),
])
def test_refuses_unsafe_or_incomplete_archive(tiny_native, tmp_path, names, kind):
    with pytest.raises(fcn.DeliveryRefused):
        call(tmp_path, archive_bytes(names, kind=kind))
    assert not (tmp_path / "output.tar").exists()
    assert not list(tmp_path.glob("fcn-delivery-*"))


@pytest.mark.parametrize("body", [b"not a tar", b"", b"x" * 100])
def test_invalid_archive(tiny_native, tmp_path, body):
    with pytest.raises(fcn.DeliveryRefused):
        call(tmp_path, body)


def test_trailing_hidden_archive_refused(tiny_native, tmp_path):
    with pytest.raises(fcn.DeliveryRefused, match="trailing"):
        call(tmp_path, archive_bytes() + archive_bytes())


@pytest.mark.parametrize("array", [np.zeros((2, 2), dtype=np.float32),
                                    np.zeros((1, 1, 2, 2, 2), dtype=np.float64),
                                    np.array([object()], dtype=object)])
def test_invalid_output_array(tiny_native, tmp_path, array):
    with pytest.raises(fcn.DeliveryRefused):
        call(tmp_path, archive_bytes(array=array))


@pytest.mark.parametrize("status,headers", [(500, {}), (302, {"location": "https://example.org"}),
    (200, {"content-type": "text/html"}),
    (200, {"content-type": "application/x-tar", "content-encoding": "gzip"}),
    (200, {"content-type": "application/x-tar", "content-length": "99999999999"})])
def test_transport_refusal(tiny_native, tmp_path, status, headers):
    with pytest.raises(fcn.DeliveryRefused):
        call(tmp_path, b"", status=status, headers=headers)
    assert not (tmp_path / "output.tar").exists()


@pytest.mark.parametrize("deployment", [replace(DEPLOY, version="2.0.0"),
    replace(DEPLOY, profile="FCN3"), replace(DEPLOY, endpoint="https://climate.api.nvidia.com"),
    replace(DEPLOY, endpoint="http://remote.example"), replace(DEPLOY, endpoint="https://user:pass@example.org"),
    replace(DEPLOY, endpoint="https://example.org?key=value"), replace(DEPLOY, checkpoint_sha256="")])
def test_configuration_refuses_before_transport(tmp_path, deployment):
    with pytest.raises(fcn.DeliveryRefused):
        fcn.infer(input_array=tmp_path / "absent.npy", initialization=INIT,
                  deployment=deployment, simulation_length=1, output_archive=tmp_path / "out.tar")


@pytest.mark.parametrize("steps", [0, -1, True, 121, 5])
def test_step_budget(steps):
    with pytest.raises(fcn.DeliveryRefused):
        fcn._configuration(DEPLOY, INIT, steps, fcn.Limits())


def test_nonfinite_input_refused_before_network(tiny_native, tmp_path):
    source = fixture_input(tmp_path)
    data = np.zeros(fcn.INPUT_SHAPE, dtype=np.float32)
    data.flat[0] = np.nan
    np.save(source, data)
    with pytest.raises(fcn.DeliveryRefused, match="non-finite"):
        fcn.infer(input_array=source, initialization=INIT, deployment=DEPLOY,
                  simulation_length=1, output_archive=tmp_path / "out.tar",
                  transport=httpx.MockTransport(lambda _: pytest.fail("network called")))


@pytest.mark.parametrize("kind", [tarfile.XHDTYPE, tarfile.GNUTYPE_LONGNAME,
                                  tarfile.GNUTYPE_SPARSE, tarfile.FIFOTYPE])
def test_extended_or_special_header_refused_without_reading_body(tiny_native, tmp_path, kind):
    member = tarfile.TarInfo("000_000.npy")
    member.type = kind
    member.size = 1_000_000_000
    body = member.tobuf(format=tarfile.USTAR_FORMAT)
    with pytest.raises(fcn.DeliveryRefused, match="unsafe"):
        call(tmp_path, body)


def test_stream_byte_budget(tiny_native, tmp_path):
    def handler(_):
        return httpx.Response(200, stream=Chunks(b"x" * 10241),
                              headers={"content-type": "application/x-tar"})
    with pytest.raises(fcn.DeliveryRefused, match="byte or wall-time"):
        fcn.infer(input_array=fixture_input(tmp_path), initialization=INIT,
            deployment=DEPLOY, simulation_length=1, output_archive=tmp_path / "out.tar",
            limits=fcn.Limits(max_response_bytes=10240), transport=httpx.MockTransport(handler))
    assert not (tmp_path / "out.tar").exists()


def test_transport_failure_cleans_partial_artifact(tiny_native, tmp_path):
    def handler(_):
        raise httpx.ReadTimeout("upstream internal details must not appear")
    with pytest.raises(fcn.DeliveryRefused, match="no artifact published") as failure:
        fcn.infer(input_array=fixture_input(tmp_path), initialization=INIT,
            deployment=DEPLOY, simulation_length=1, output_archive=tmp_path / "out.tar",
            transport=httpx.MockTransport(handler))
    assert "upstream internal" not in str(failure.value)
    assert not list(tmp_path.glob("fcn-delivery-*"))


def test_existing_output_is_preserved(tiny_native, tmp_path):
    output = tmp_path / "out.tar"
    output.write_bytes(b"existing")
    with pytest.raises(fcn.DeliveryRefused, match="already exists"):
        fcn.infer(input_array=tmp_path / "absent.npy", initialization=INIT,
            deployment=DEPLOY, simulation_length=1, output_archive=output,
            transport=httpx.MockTransport(lambda _: pytest.fail("network called")))
    assert output.read_bytes() == b"existing"


def test_deadline_prevents_upload(tiny_native, tmp_path):
    with pytest.raises(fcn.DeliveryRefused, match="deadline"):
        fcn.infer(input_array=fixture_input(tmp_path), initialization=INIT,
            deployment=DEPLOY, simulation_length=1, output_archive=tmp_path / "out.tar",
            limits=fcn.Limits(timeout_seconds=1e-12),
            transport=httpx.MockTransport(lambda _: pytest.fail("network called")))


@pytest.mark.parametrize("stamp", ["2026-01-01", "2026-02-30T00:00:00Z", "2026-01-01T00:00:00.1Z"])
def test_timestamp_refusal(stamp):
    with pytest.raises(fcn.DeliveryRefused):
        fcn._configuration(DEPLOY, replace(INIT, input_time=stamp), 1, fcn.Limits())


def test_progressing_upload_checks_deadline(monkeypatch):
    stream = fcn._DeadlineReader(io.BytesIO(b"input"), deadline=10)
    monkeypatch.setattr(fcn.time, "monotonic", lambda: 9)
    assert stream.read(1) == b"i"
    monkeypatch.setattr(fcn.time, "monotonic", lambda: 11)
    with pytest.raises(fcn.DeliveryRefused, match="upload deadline"):
        stream.read(1)


def test_numpy_header_limit_applies_before_allocation():
    class BoundedProbe(io.BytesIO):
        def read(self, size=-1):
            assert 0 <= size <= 65536, "unbounded header allocation attempted"
            return super().read(size)
    malicious = BoundedProbe(b"\x93NUMPY\x02\x00\xff\xff\xff\xff")
    with pytest.raises(fcn.DeliveryRefused, match="allocation budget"):
        fcn._npy_header(malicious)
