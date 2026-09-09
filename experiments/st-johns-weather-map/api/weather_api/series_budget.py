"""Shared finite response-cache accounting for both experimental Series APIs."""
import threading
import time

_lock = threading.Lock()
_entries = {}
LIMIT = 8 * 1024 * 1024


def reserve(identity, size, expires):
    with _lock:
        now = time.monotonic()
        for key, (_, expiry) in list(_entries.items()):
            if expiry <= now:
                del _entries[key]
        if size + sum(v[0] for k, v in _entries.items() if k != identity) > LIMIT:
            return False
        _entries[identity] = (size, expires)
        return True


def release(identity):
    with _lock:
        _entries.pop(identity, None)
