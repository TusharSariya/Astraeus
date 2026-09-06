"""Per-operation received-byte accounting for bounded upstream acquisition."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Iterator


class ReceivedBytesExceeded(RuntimeError):
    """The complete operation consumed more upstream bytes than admitted."""


@dataclass
class ReceivedByteBudget:
    limit: int
    used: int = 0

    def charge(self, amount: int) -> None:
        if amount < 0:
            raise ValueError("received byte charge cannot be negative")
        projected = self.used + amount
        if projected > self.limit:
            raise ReceivedBytesExceeded(
                f"operation exceeded its {self.limit} received-byte bound at {projected} bytes"
            )
        self.used = projected

    @property
    def remaining(self) -> int:
        return self.limit - self.used


_CURRENT: ContextVar[ReceivedByteBudget | None] = ContextVar("acquisition_received_byte_budget", default=None)


@contextmanager
def acquisition_budget(limit: int) -> Iterator[ReceivedByteBudget]:
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        raise ValueError("received-byte bound must be a positive integer")
    budget = ReceivedByteBudget(limit)
    token = _CURRENT.set(budget)
    try:
        yield budget
    finally:
        _CURRENT.reset(token)


def charge_received(amount: int) -> None:
    budget = _CURRENT.get()
    if budget is not None:
        budget.charge(amount)


def remaining_received() -> int | None:
    budget = _CURRENT.get()
    return None if budget is None else budget.remaining


def directory_bytes(path: Path) -> int:
    """Count task-owned regular files without following links outside it."""
    total = 0
    for item in path.rglob("*"):
        if item.is_file() and not item.is_symlink():
            total += item.stat().st_size
    return total


def retained_memory_bytes(value: object) -> int:
    """Count the reachable Python object graph once per object identity."""
    seen: set[int] = set()

    def size(item: object) -> int:
        identity = id(item)
        if identity in seen:
            return 0
        seen.add(identity)
        total = sys.getsizeof(item)
        if isinstance(item, dict):
            total += sum(size(key) + size(child) for key, child in item.items())
        elif isinstance(item, (list, tuple, set, frozenset)):
            total += sum(size(child) for child in item)
        elif hasattr(item, "__dict__"):
            total += size(vars(item))
        return total

    return size(value)
