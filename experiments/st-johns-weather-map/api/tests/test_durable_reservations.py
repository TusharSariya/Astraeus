from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import pytest
from ingest.store import ArtifactStore, ReservationIdentity, ReservationLost, ResourceBudgetExceeded, StoreConfig
UTC = timezone.utc

def identity(workspace: Path) -> ReservationIdentity:
    return ReservationIdentity("10000000-0000-0000-0000-000000000001",7,"host:worker:1","host","10000000-0000-0000-0000-000000000002","9",workspace,datetime(2099,1,1,tzinfo=UTC))

def store() -> ArtifactStore:
    return ArtifactStore(StoreConfig("postgresql://unused","http://unused","bucket","",""))

def test_local_cleanup_failure_is_observable_and_keeps_reservation_revoking(tmp_path,monkeypatch):
    instance=store(); lease=identity(tmp_path/"workspace"); lease.workspace_path.mkdir(); marked=[]
    monkeypatch.setattr("ingest.store.shutil.rmtree",lambda _path: (_ for _ in ()).throw(OSError("busy")))
    monkeypatch.setattr(instance,"_mark_revoking",lambda _lease,detail: marked.append(detail))
    with pytest.raises(ReservationLost,match="capacity remains charged"): instance._finish_reservation(lease)
    assert marked==["local cleanup failed: busy"] and lease.workspace_path.exists()

def test_reaper_requires_positive_proof_that_allocator_stopped(tmp_path):
    with pytest.raises(ReservationLost,match="stop was not proven"): store().reap_reservation(identity(tmp_path/"workspace"),allocator_stopped=False)

class Cursor:
    def __init__(self): self.rows=[]
    def __enter__(self): return self
    def __exit__(self,*_args): return None
    def execute(self,sql,_params=None): self.rows=[] if "SELECT operation_id,fencing_token" in " ".join(sql.split()) else [(0,)]
    def fetchone(self): return self.rows.pop(0) if self.rows else (0,)
    def fetchall(self): rows,self.rows=self.rows,[]; return rows
class Connection:
    def cursor(self): return Cursor()
    def __enter__(self): return self
    def __exit__(self,*_args): return None
@contextmanager
def connection(): yield Connection()

def test_same_host_startup_lock_refuses_a_second_allocator(tmp_path,monkeypatch):
    monkeypatch.setenv("WEATHER_WORKER_HOST_ID","stable-host"); monkeypatch.setenv("WEATHER_RESERVATION_LOCK_DIR",str(tmp_path/"locks"))
    first,second=store(),store(); monkeypatch.setattr(first,"connection",connection); monkeypatch.setattr(second,"connection",connection)
    assert first.reconcile_durable_reservations(tmp_path)==0
    with pytest.raises(ResourceBudgetExceeded,match="prior same-host allocator"): second.reconcile_durable_reservations(tmp_path)
    first._host_lock.close()

class CleanupS3:
    def __init__(self, objects, uploads=()): self.objects=set(objects); self.uploads=list(uploads); self.deleted=[]; self.aborted=[]
    def list_objects_v2(self, *, Prefix, **_kwargs): return {"Contents":[{"Key":k} for k in sorted(self.objects) if k.startswith(Prefix)],"IsTruncated":False}
    def delete_object(self, *, Bucket, Key): self.deleted.append(Key); self.objects.discard(Key)
    def list_multipart_uploads(self, *, Prefix, **_kwargs): return {"Uploads":[u for u in self.uploads if u["Key"].startswith(Prefix)]}
    def abort_multipart_upload(self, *, Bucket, Key, UploadId): self.aborted.append((Key,UploadId)); self.uploads=[u for u in self.uploads if u["UploadId"]!=UploadId]

class RetainedCursor(Cursor):
    def execute(self,sql,_params=None):
        self.rows=[("staging/10000000-0000-0000-0000-000000000001/source/run/id/published",)] if "state IN ('published','superseded')" in sql else []
@contextmanager
def retained_connection():
    connection=Connection(); connection.cursor=lambda: RetainedCursor(); yield connection

def test_remote_cleanup_catches_upload_before_row_and_preserves_published_object(monkeypatch,tmp_path):
    instance=store(); lease=identity(tmp_path/"workspace"); prefix=f"staging/{lease.operation_id}/source/run/id/"
    published=prefix+"published"; orphan=prefix+"upload-before-row"
    client=CleanupS3({published,orphan},({"Key":prefix+"multipart","UploadId":"u1"},))
    instance._client=client; monkeypatch.setattr(instance,"connection",retained_connection)
    instance._cleanup_remote_reservation(lease)
    assert client.objects=={published}; assert client.deleted==[orphan]; assert client.aborted==[(prefix+"multipart","u1")]
