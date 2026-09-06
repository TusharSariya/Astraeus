"""Regression proofs for the storage-window cleanup findings in the handoff."""
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from ingest.purge import drain_objects
from weather_api.store import LiveStore, drain_purged_objects


class QueueStore:
    def __init__(self):
        self.queued = {'expired'}
        self.objects = {'expired'}
        self.fail = True
        self.in_transaction = False
        self.config = SimpleNamespace(bucket='test')
        self.s3 = self

    @contextmanager
    def connection(self):
        previous = self.queued.copy()
        self.in_transaction = True
        try:
            yield self
        except BaseException:
            self.queued = previous
            raise
        finally:
            self.in_transaction = False

    @contextmanager
    def cursor(self):
        yield self

    def execute(self, sql, params=None):
        if 'claim_purged_objects' in sql:
            self.claimed = sorted(self.queued)[:params[0]]
            self.queued.difference_update(self.claimed)
        elif 'INSERT INTO' in sql:
            self.queued.add(params[0])
        else:
            raise AssertionError(sql)

    def fetchall(self):
        return [(key,) for key in self.claimed]

    def delete_object(self, *, Bucket, Key):
        assert self.in_transaction, 'the queue acknowledgement must not commit before deletion'
        if self.fail:
            raise OSError('temporary object-store outage')
        self.objects.discard(Key)


@pytest.mark.parametrize('drain', [drain_objects, drain_purged_objects])
def test_failed_delete_is_retried_by_the_next_sweep(drain):
    store = QueueStore()
    assert drain(store) == (0, 1)
    assert store.queued == store.objects == {'expired'}
    store.fail = False
    assert drain(store) == (1, 0)
    assert store.queued == store.objects == set()
    assert drain(store) == (0, 0)


def test_interruption_rolls_back_the_unacknowledged_claim(monkeypatch):
    store = QueueStore()
    def interrupted(**kwargs):
        raise KeyboardInterrupt
    monkeypatch.setattr(store, 'delete_object', interrupted)
    with pytest.raises(KeyboardInterrupt):
        drain_objects(store)
    assert store.queued == {'expired'}


def test_stale_disk_files_and_open_handles_are_evicted(tmp_path):
    closed = []
    live = LiveStore(SimpleNamespace(), tmp_path)
    live._datasets['old'] = SimpleNamespace(close=lambda: closed.append('old'))
    for name in ['old', 'previous-process', 'current']:
        (tmp_path / f'{name}.zarr.zip').write_bytes(b'cache')
    live._forget_stale_datasets({'current'})
    assert closed == ['old']
    assert [p.name for p in tmp_path.iterdir()] == ['current.zarr.zip']


def test_non_zarr_downloads_also_evict_old_disk_copies(tmp_path, monkeypatch):
    import hashlib
    from weather_api import store as module
    monkeypatch.setattr(module, 'MAX_CACHED_DATASETS', 2)
    content = b'{}'
    def download(bucket, key, handle):
        handle.write(content)
    backing = SimpleNamespace(config=SimpleNamespace(bucket='test'), s3=SimpleNamespace(download_fileobj=download))
    live = LiveStore(backing, tmp_path)
    for name in ['a', 'b', 'c']:
        live._local_copy(SimpleNamespace(revision_id=name, object_key=name, byte_size=2,
            provenance={'sha256': hashlib.sha256(content).hexdigest()}))
    assert {p.name for p in tmp_path.iterdir()} == {'b.zarr.zip', 'c.zarr.zip'}


def test_periodic_worker_maintenance_purges_without_a_restart(tmp_path, monkeypatch):
    from worker import runtime
    from ingest import scheduler
    from ingest.derive import cloud_motion, weong_layer
    calls = []
    backing = SimpleNamespace(prune=lambda: calls.append('prune'),
                              purge_outside_window=lambda: calls.append('purge'))
    monkeypatch.setattr(runtime, '_store', lambda: backing)
    monkeypatch.setattr(runtime, 'heartbeat_path', lambda: tmp_path / 'heartbeat')
    monkeypatch.setattr(scheduler, 'reconcile_on_start', lambda store: SimpleNamespace(detail='test', may_fetch=True))
    monkeypatch.setattr(runtime, 'Scheduler', lambda *a, **k: SimpleNamespace(
        source_ids=(), progress={}, cycle=lambda **k: None, drain_jobs=lambda **k: None))
    monkeypatch.setattr(cloud_motion, 'cloud_motion_cycle', lambda store: [])
    monkeypatch.setattr(weong_layer, 'weong_cycle', lambda store: [])
    handlers = {}
    monkeypatch.setattr(runtime.signal, 'signal', lambda sig, fn: handlers.update({sig: fn}))
    monkeypatch.setattr(runtime.time, 'monotonic', lambda: 4000)
    monkeypatch.setattr(runtime.time, 'sleep', lambda seconds: handlers[runtime.signal.SIGTERM](None, None))
    assert runtime.run() == 0
    assert calls == ['prune', 'purge']
