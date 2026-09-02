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
def derivation_registry(monkeypatch: pytest.MonkeyPatch):
    """Stand the derivation method registry up for tests that serve a derivation.

    Every ``derived_here`` value the API serves names an enabled entry in
    ``ingest.derive.registry``. The registry itself is owned by this change's
    ingest section; this double declares the three entries the API names, in
    the shape ``weather_api.store.derivation_entry`` reads, so the store's own
    admission rules can be exercised whichever way the real registry is built.

    Returns the entry map, so a test can disable an entry or narrow a range.
    """
    import types  # noqa: PLC0415
    from types import SimpleNamespace  # noqa: PLC0415

    from weather_api.store import FOG_STATE_METHOD, RELATIVE_HUMIDITY_METHOD, WIND_METHOD  # noqa: PLC0415

    entries = {
        RELATIVE_HUMIDITY_METHOD: SimpleNamespace(
            name=RELATIVE_HUMIDITY_METHOD,
            version="metpy-1.7.1-liquid-v1",
            citation="Bolton (1980), Monthly Weather Review 108, via MetPy relative_humidity_from_dewpoint",
            inputs=("temperature", "dew_point"),
            output="relative_humidity",
            physical_range=(0.0, 100.0),
            range_rule="clamp",
            enabled=True,
        ),
        WIND_METHOD: SimpleNamespace(
            name=WIND_METHOD,
            version="metpy-1.7.1-wind-v1",
            citation="MetPy wind_speed and wind_direction from u and v components",
            inputs=("wind_u", "wind_v"),
            output="wind_speed_and_direction",
            physical_range=None,
            range_rule="refuse",
            enabled=True,
        ),
        FOG_STATE_METHOD: SimpleNamespace(
            name=FOG_STATE_METHOD,
            version="fog-state-present-weather-v1",
            citation="ICAO Annex 3 present-weather groups; FG and VCFG are fog evidence, BR is mist",
            inputs=("weather_fog_code", "weather_fog_vicinity_code", "visibility"),
            output="fog_state",
            physical_range=None,
            range_rule="refuse",
            enabled=True,
        ),
    }

    module = types.ModuleType("ingest.derive.registry")
    module.get_entry = lambda name: entries.get(name)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ingest.derive.registry", module)

    import ingest.derive  # noqa: PLC0415

    monkeypatch.setattr(ingest.derive, "registry", module, raising=False)
    return entries


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
