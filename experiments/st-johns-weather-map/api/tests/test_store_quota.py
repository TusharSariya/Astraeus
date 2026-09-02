"""The 64 GiB hot quota, and the fact that there is nowhere to spill to.

The cap is one number in ``weather_api.config``. Three places have to agree
with it - the compose default, the MinIO bootstrap and the staging projection -
and the bug this file guards against is any one of them quietly keeping the old
25 GiB while the others move.
"""

from __future__ import annotations

import re
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

import pytest

from ingest.store import LOCAL_STORAGE_CAP_BYTES, ArtifactStore, QuotaExceeded, StoreConfig, _parse_cap
from weather_api import config
from weather_api.store import assert_room_for

EXPERIMENT_ROOT = Path(__file__).resolve().parent.parent.parent
T0 = datetime(2026, 9, 2, 12, tzinfo=UTC)


# --- the configured cap is 64 GiB, everywhere ----------------------------

def test_the_quota_is_64_gib_in_the_one_definition():
    assert config.STORAGE_CAP == "64GiB"
    assert config.STORAGE_CAP_BYTES == 64 * 1024**3 == 68_719_476_736


def test_the_store_default_cap_is_the_same_64_gib():
    """The fallback a store falls back to must not be the superseded number."""
    assert LOCAL_STORAGE_CAP_BYTES == config.STORAGE_CAP_BYTES


def test_the_unit_suffix_parse_survives_and_reads_64_gib():
    assert _parse_cap("64GiB") == config.STORAGE_CAP_BYTES
    assert _parse_cap(None) == config.STORAGE_CAP_BYTES
    assert _parse_cap("512MiB") == 512 * 1024**2
    assert _parse_cap("1GB") == 1000**3
    assert _parse_cap("1024") == 1024


def test_a_store_configured_from_the_environment_carries_the_64_gib_cap():
    store = StoreConfig.from_env(
        {
            "WEATHER_DATABASE_URL": "postgresql://x",
            "WEATHER_MINIO_ENDPOINT": "http://x",
            "WEATHER_MINIO_BUCKET": "b",
            "WEATHER_STORAGE_CAP": config.STORAGE_CAP,
        }
    )
    assert store.cap_bytes == config.STORAGE_CAP_BYTES


def test_compose_and_the_bootstrap_default_to_the_same_64_gib_quota():
    """The deployed cap comes from these two files, not from a Python constant."""
    compose = (EXPERIMENT_ROOT / "compose.yaml").read_text(encoding="utf-8")
    bootstrap = (EXPERIMENT_ROOT / "infra" / "minio" / "bootstrap.sh").read_text(encoding="utf-8")
    defaults = set(re.findall(r"WEATHER_STORAGE_CAP[:=]-?\s*\$?\{?WEATHER_STORAGE_CAP:-([0-9A-Za-z]+)\}?", compose))
    assert defaults == {"64GiB"}, defaults
    assert 'CAP="${WEATHER_STORAGE_CAP:-64GiB}"' in bootstrap
    assert "25GiB" not in compose and "25GiB" not in bootstrap


def test_the_storage_policy_states_64_gib_and_no_cold_tier():
    policy = (EXPERIMENT_ROOT / "infra" / "STORAGE.md").read_text(encoding="utf-8")
    assert "64GiB" in policy or "64 GiB" in policy
    assert "25GiB" not in policy and "25 GiB" not in policy
    assert "no cold tier" in policy.lower()


# --- reaching the cap fails closed ---------------------------------------

class _Cursor:
    def __init__(self, answers: dict[str, Any], events: list[str]) -> None:
        self._answers, self._events, self._last = answers, events, ""

    def __enter__(self) -> _Cursor:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def execute(self, sql: str, params: Any = None) -> None:
        text = " ".join(sql.split()).lower()
        self._last = "reclaimable" if "reclaimable_bytes" in text else "used" if "sum(byte_size)" in text else text
        self._events.append(self._last)

    def fetchone(self) -> tuple[Any, ...]:
        return (self._answers.get(self._last, 0),)

    def fetchall(self) -> list[tuple[Any, ...]]:
        return []


@pytest.fixture
def store_holding(monkeypatch: pytest.MonkeyPatch):
    def build(*, used: int, reclaimable: int, cap: int | None = None) -> tuple[ArtifactStore, list[str]]:
        events: list[str] = []
        instance = ArtifactStore(
            StoreConfig(
                database_url="postgresql://unused", endpoint="http://unused",
                bucket="b", access_key="k", secret_key="s",
                cap_bytes=cap if cap is not None else config.STORAGE_CAP_BYTES,
            )
        )

        @contextmanager
        def connection() -> Iterator[Any]:
            class _Connection:
                def cursor(self) -> _Cursor:
                    return _Cursor({"used": used, "reclaimable": reclaimable}, events)

                def __enter__(self) -> Any:
                    return self

                def __exit__(self, *_exc: object) -> None:
                    return None

            yield _Connection()

        monkeypatch.setattr(instance, "connection", connection)
        return instance, events

    return build


def test_a_projection_over_the_quota_is_refused_as_exceeded_naming_64_gib(store_holding):
    store, _events = store_holding(used=config.STORAGE_CAP_BYTES - 1024, reclaimable=0)

    with pytest.raises(QuotaExceeded) as raised:
        assert_room_for(store, 1 << 30, now=T0)

    message = str(raised.value)
    assert "64GiB" in message
    assert "cold tier" in message


def test_a_projection_that_fits_is_allowed(store_holding):
    store, _events = store_holding(used=1 << 30, reclaimable=0)
    assert_room_for(store, 1 << 30, now=T0)  # does not raise


def test_replaced_bytes_are_credited_back_in_the_projection(store_holding):
    store, _events = store_holding(used=config.STORAGE_CAP_BYTES, reclaimable=0)
    # Without the credit this is over the cap by exactly the replaced revision.
    assert_room_for(store, 1 << 20, replacing_bytes=2 << 20, now=T0)


def test_no_evict_of_an_in_window_frame_satisfies_a_projection(store_holding):
    """Only bytes already outside the window may be counted as reclaimable.

    A store that is full of in-window evidence has nothing to free. Answering
    otherwise would trade a frame a request could name for room to fetch more,
    which is an eviction of visible data under another name.
    """
    store, events = store_holding(used=config.STORAGE_CAP_BYTES, reclaimable=0)

    with pytest.raises(QuotaExceeded):
        assert_room_for(store, 1, now=T0)

    # It asked the database what is reclaimable rather than assuming anything
    # on disk could go.
    assert "reclaimable" in events


def test_bytes_already_outside_the_window_do_count_as_room(store_holding):
    """A frame that has already aged out is not visible evidence."""
    store, _events = store_holding(used=config.STORAGE_CAP_BYTES, reclaimable=4 << 30)
    assert_room_for(store, 1 << 30, now=T0)  # does not raise


def test_no_evict_of_a_visible_revision_is_ever_planned_when_the_quota_is_exceeded(store_holding):
    """Nothing in the refusal path deletes; it raises before any upload.

    The store double records every statement it is sent. A projection that
    resolved the cap by removing something would have to send a DELETE, and
    there is none - the only statements are the two questions it asks.
    """
    store, events = store_holding(used=config.STORAGE_CAP_BYTES, reclaimable=0)

    with pytest.raises(QuotaExceeded):
        assert_room_for(store, 1 << 20, now=T0)

    assert all(not event.startswith("delete") for event in events)
    assert set(events) <= {"used", "reclaimable"}
