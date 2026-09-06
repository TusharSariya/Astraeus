from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from ingest.contract import AdapterUnavailable, FetchWindow
from ingest.experimental.iers_time import (
    FINALS_MAX_BYTES, TEXT_MAX_BYTES, IERSBulletinAAdapter, IERSLeapSecondAdapter,
    NAIFLeapSecondsKernelAdapter,
)
from weather_api.app import PREFIX, app
from weather_api.store import LiveStore

UTC = timezone.utc
FIXTURES = Path(__file__).parent / "fixtures/iers_time"
WINDOW = FetchWindow(datetime(2026, 9, 6, tzinfo=UTC), back_hours=5 * 24, forward_hours=2 * 24)
CAPTURED = datetime(2026, 9, 6, 3, 57, 17, 963183, tzinfo=UTC)


class Client:
    def __init__(self, body: bytes, identity_body: bytes | None = None, error=None):
        self.body, self.identity_body, self.error, self.calls = body, identity_body, error, []
    def download(self, url, path, *, max_bytes):
        self.calls.append((url, max_bytes))
        if self.error: raise self.error
        selected = self.identity_body if url.endswith("aareadme.txt") and self.identity_body is not None else self.body
        if len(selected) > max_bytes: raise ValueError("too large")
        path.write_bytes(selected)


def body(name): return (FIXTURES / name).read_bytes()


def test_finals_enumerates_all_fields_statuses_units_and_missing_lod(tmp_path):
    adapter = IERSBulletinAAdapter(client=Client(body("finals2000A.trimmed.all")), clock=lambda: CAPTURED)
    candidate = adapter.discover(WINDOW)[0]
    result = adapter.fetch(candidate, WINDOW, tmp_path)
    assert result.retrieved_at == CAPTURED and result.run_time is None
    assert result.complete is False and result.qc_passed is False
    assert "RunManifest contract is not accepted" in result.notes
    assert result.artifacts[0].provenance["operational"] is False
    assert result.artifacts[0].provenance["validation"]["publishable"] is False
    assert set(result.artifacts[0].provenance["field_disposition"]) == {
        "year/month/day", "MJD", "PM flag", "PM-x/error, PM-y/error", "UT1 flag", "UT1-UTC/error",
        "LOD/error", "nutation flag", "dX/error, dY/error", "Bulletin B PM-x, PM-y, UT1-UTC, dX, dY",
    }
    import xarray, zarr
    store = zarr.storage.ZipStore(str(result.artifacts[0].payload_path), mode="r")
    ds = xarray.open_zarr(store, consolidated=False)
    assert list(ds.pm_status.values) == ["I", "I", "I", "P", "P", "P"]
    assert ds.ut1_utc.attrs["units"] == "s" and ds.pm_x.attrs["units"] == "arcsec"
    assert ds.lod.values[:2].tolist() == pytest.approx([0.8016, 0.5626])
    assert all(value != value for value in ds.lod.values[2:])


def test_iers_leaps_preserve_effective_utc_offsets_and_expiry(tmp_path):
    adapter = IERSLeapSecondAdapter(client=Client(body("Leap_Second.trimmed.dat")), clock=lambda: CAPTURED)
    candidate = adapter.discover(WINDOW)[0]
    result = adapter.fetch(candidate, WINDOW, tmp_path)
    assert result.retrieved_at == CAPTURED
    assert result.artifacts[0].provenance["expires_at"] == "2027-06-28T00:00:00Z"
    assert result.artifacts[0].provenance["updated_through_bulletin"] == "72"
    assert result.artifacts[0].provenance["bulletin_issued"] == "July 2026"


def test_naif_lsk_pins_version_constants_and_delta_at(tmp_path):
    adapter = NAIFLeapSecondsKernelAdapter(client=Client(body("naif0012.trimmed.tls"), body("naif-lsk-aareadme.trimmed.txt")), clock=lambda: CAPTURED)
    result = adapter.fetch(adapter.discover(WINDOW)[0], WINDOW, tmp_path)
    provenance = result.artifacts[0].provenance
    assert provenance["kernel_version"] == "naif0012"
    assert provenance["deltet_constants"] == {"DELTA_T_A": 32.184, "K": 0.001657, "EB": 0.01671, "M": [6.239996, 1.99096871e-07]}


@pytest.mark.parametrize("adapter,fixture,mutation,match", [
    (IERSBulletinAAdapter, "finals2000A.trimmed.all", lambda b: b.replace(b" P  0.207634", b" X  0.207634", 1), "unknown IERS"),
    (IERSBulletinAAdapter, "finals2000A.trimmed.all", lambda b: b.replace(b"61284.00", b"61284.50", 1), "MJD disagrees"),
    (IERSBulletinAAdapter, "finals2000A.trimmed.all", lambda b: b[:20], "truncated row"),
    (IERSLeapSecondAdapter, "Leap_Second.trimmed.dat", lambda b: b.replace(b"expires", b"endedxx"), "update or expiry"),
    (IERSLeapSecondAdapter, "Leap_Second.trimmed.dat", lambda b: b.replace(b"56109.0", b"56109.5"), "MJD disagrees"),
    (NAIFLeapSecondsKernelAdapter, "naif0012.trimmed.tls", lambda b: b.replace(b"KPL/LSK", b"KPL/PCK"), "versioned DELTET"),
])
def test_schema_and_identity_fail_closed(adapter, fixture, mutation, match):
    with pytest.raises(AdapterUnavailable, match=match):
        adapter(client=Client(mutation(body(fixture)), body("naif-lsk-aareadme.trimmed.txt") if adapter is NAIFLeapSecondsKernelAdapter else None)).discover(WINDOW)



def test_naif_version_marker_is_required_and_exact():
    kernel = body("naif0012.trimmed.tls")
    for identity in (b"", b"LEAPSECONDS KERNEL VERSION NAIF0011\n"):
        with pytest.raises(AdapterUnavailable, match="versioned DELTET"):
            NAIFLeapSecondsKernelAdapter(client=Client(kernel, identity)).discover(WINDOW)


def test_expired_oversize_and_request_failure_fail_closed():
    expired = datetime(2028, 1, 1, tzinfo=UTC)
    with pytest.raises(AdapterUnavailable, match="expired"):
        IERSLeapSecondAdapter(client=Client(body("Leap_Second.trimmed.dat")), clock=lambda: expired).discover(WINDOW)
    with pytest.raises(AdapterUnavailable, match="request failed"):
        IERSBulletinAAdapter(client=Client(b"x" * (FINALS_MAX_BYTES + 1))).discover(WINDOW)
    with pytest.raises(AdapterUnavailable, match="request failed"):
        NAIFLeapSecondsKernelAdapter(client=Client(b"", error=RuntimeError("503"))).discover(WINDOW)


def test_artifacts_read_back_through_real_reader_and_http(tmp_path, monkeypatch):
    import sys
    adapters = [
        IERSBulletinAAdapter(client=Client(body("finals2000A.trimmed.all")), clock=lambda: CAPTURED),
        IERSLeapSecondAdapter(client=Client(body("Leap_Second.trimmed.dat")), clock=lambda: CAPTURED),
        NAIFLeapSecondsKernelAdapter(client=Client(body("naif0012.trimmed.tls"), body("naif-lsk-aareadme.trimmed.txt")), clock=lambda: CAPTURED),
    ]
    artifacts = [a.fetch(a.discover(WINDOW)[0], WINDOW, tmp_path).artifacts[0] for a in adapters]
    records=[]
    for i,(a,artifact) in enumerate(zip(adapters,artifacts)):
        records.append(SimpleNamespace(revision_id=f"iers-proof-{i}", source_id=a.source_id, logical_name=artifact.logical_name, media_type=artifact.media_type, object_key=f"proof/{i}.zip", byte_size=artifact.byte_size, provenance=artifact.provenance, run_time=None, retrieved_at=CAPTURED, provider_run_id=f"proof-{i}", native_crs="not_applicable", payload_path=artifact.payload_path))
    class S3:
        def head_bucket(self, **_kwargs): return {}
        def download_fileobj(self, _bucket, key, handle):
            record=next(r for r in records if r.object_key==key)
            with record.payload_path.open("rb") as source: shutil.copyfileobj(source, handle)
    class ArtifactStore:
        s3=S3(); config=SimpleNamespace(bucket="test")
        def current_artifacts(self): return records
        def source_activity(self): return {r.source_id:r.retrieved_at for r in records}
    store=LiveStore(ArtifactStore(), tmp_path/"cache")
    api_module=sys.modules["weather_api.app"]
    monkeypatch.setenv("WEATHER_DATA_MODE", "live")
    monkeypatch.setattr(api_module, "live_store", lambda:store)
    response=TestClient(app).get(f"{PREFIX}/experimental/time-inputs")
    assert response.status_code==200
    payload=response.json()
    assert payload["data_mode"]=="live" and payload["operational"] is False
    assert {p["source_id"] for p in payload["products"]}=={a.source_id for a in adapters}
    finals=next(p for p in payload["products"] if p["source_id"]=="iers-bulletin-a-finals2000a")
    assert finals["retrieved_at"]=="2026-09-06T03:57:17.963183Z"
    assert finals["variables"]["ut1_utc"]["values"][3]==pytest.approx(0.0008643)
