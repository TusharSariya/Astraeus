from __future__ import annotations

import sys
from pathlib import Path

EXPERIMENT_ROOT = Path(__file__).resolve().parent.parent.parent

# ``ingest`` and ``registry`` ship beside ``api`` in the repository and in both
# images; the API adds the same path at runtime.
if str(EXPERIMENT_ROOT) not in sys.path:
    sys.path.insert(0, str(EXPERIMENT_ROOT))


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def fixture_only_deployment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default every test to the explicit fixture deployment.

    The mode is now a deliberate, single environment variable, so the default
    has to be stated rather than inherited: a test that forgets it would see the
    fail-closed unavailable behaviour, not fixtures.
    """
    from weather_api.store import DATA_MODE_ENV, reset_live_store

    monkeypatch.setenv(DATA_MODE_ENV, "fixture")
    reset_live_store()
    yield
    reset_live_store()


@pytest.fixture
def data_mode(monkeypatch: pytest.MonkeyPatch):
    """Test seam for flipping ``WEATHER_DATA_MODE`` mid-test."""
    from weather_api.store import DATA_MODE_ENV, reset_live_store

    def switch(value: str | None) -> None:
        if value is None:
            monkeypatch.delenv(DATA_MODE_ENV, raising=False)
        else:
            monkeypatch.setenv(DATA_MODE_ENV, value)
        reset_live_store()

    return switch
