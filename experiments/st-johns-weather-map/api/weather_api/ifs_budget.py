"""One finite input ledger shared by every IFS operation in a selection.

Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-006.
"""
from dataclasses import dataclass, field
import threading
import time


class SelectionStopped(ValueError):
    pass


@dataclass
class SelectionBudget:
    byte_limit: int = 2 * 1024**3
    record_limit: int = 4096
    clock: object = time.monotonic
    lifetime: float = 900
    bytes: int = 0
    records: int = 0
    cancelled: threading.Event = field(default_factory=threading.Event)
    lock: threading.Lock = field(default_factory=threading.Lock)
    receive_lock: threading.Lock = field(default_factory=threading.Lock)
    slots: threading.BoundedSemaphore = field(default_factory=lambda: threading.BoundedSemaphore(2))

    def __post_init__(self):
        self.expires = self.clock() + self.lifetime

    def check(self):
        if self.cancelled.is_set():
            raise SelectionStopped('selection_cancelled')
        if self.clock() >= self.expires:
            raise SelectionStopped('selection_expired')

    def start_record(self):
        with self.lock:
            self.check()
            if self.records >= self.record_limit:
                raise SelectionStopped('record_budget_exhausted')
            self.records += 1

    def allowance(self, limit):
        with self.lock:
            self.check()
            remaining = self.byte_limit - self.bytes
            if remaining <= 0:
                raise SelectionStopped('byte_budget_exhausted')
            return min(limit, remaining)

    def charge(self, count):
        with self.lock:
            self.bytes += count
            if self.bytes > self.byte_limit:
                raise SelectionStopped('byte_budget_exhausted')


# Detailed transfer manifests are bounded independently of scalar/grid responses.
# Evicted or expired manifests explicitly become unavailable; viewing never renews.
from collections import OrderedDict
import json
import secrets
_manifests=OrderedDict()
_manifest_lock=threading.Lock()


def register_receipts(budget,receipts):
    with _manifest_lock:
        identity=getattr(budget,'receipt_id',None)
        if identity is None:
            identity=secrets.token_urlsafe(18);budget.receipt_id=identity
        entry=_manifests.get(identity)
        if entry is None:entry=(budget.expires,budget.clock,{})
        for receipt in receipts:entry[2][json.dumps(receipt,sort_keys=True)]=receipt
        _manifests[identity]=entry
        while sum(sum(len(k) for k in v[2]) for v in _manifests.values())>8*1024**2:_manifests.popitem(last=False)
        return f'/api/experiments/weather/v0/ifs/transfers/{identity}'


def receipt_page(identity,offset):
    with _manifest_lock:
        entry=_manifests.get(identity)
        if entry is None or entry[1]()>=entry[0]:raise SelectionStopped('receipt_manifest_expired')
        values=list(entry[2].values())
        return values[offset:offset+12],offset+12 if offset+12<len(values) else None
