"""`/space-weather` and the honesty rules for planetary evidence.

The store is stubbed with in-memory datasets shaped exactly as the SWPC
adapters publish them: the Kp and solar-wind series on a bare time axis with
no coordinates, and the OVATION grid as the one genuinely gridded product.
Under test: observed and forecast Kp stay separate with the provider's own
per-value status, planetary quantities never reach `/point`, the latest Bz is
served with its own instant (a gap is a gap, never zero), staleness and
absence fail closed with notices, and fixture mode invents nothing.
"""

from __future__ import annotations

import sys as _sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy
import xarray
from fastapi.testclient import TestClient

import weather_api.app  # noqa: F401
from ingest.store import CurrentArtifact
from weather_api.app import PREFIX, app
from weather_api.fixtures import now
from weather_api.store import LiveStore, live_point_fields

UTC = timezone.utc
api_module = _sys.modules["weather_api.app"]
client = TestClient(app)

ST_JOHNS = (47.5615, -52.7126)


# --- artifacts and datasets ------------------------------------------------


def make_artifact(source_id: str, logical_name: str, product: str, run_time: datetime, provenance_extra: dict | None = None) -> CurrentArtifact:
    stamp = run_time
    return CurrentArtifact(
        source_id=source_id,
        logical_name=logical_name,
        revision_id=f"revision-{source_id}-{logical_name}",
        object_key=f"artifacts/{source_id}/{logical_name}",
        media_type="application/zarr+zip",
        byte_size=1024,
        provenance={"product": product, "evidence_classes": ["retrieved"], **(provenance_extra or {})},
        published_at=stamp,
        run_time=run_time,
        retrieved_at=stamp,
        provider_run_id=f"{source_id}-{run_time.strftime('%Y%m%d%H%M')}",
        native_crs=None,
    )


def series_dataset(times: list[datetime], variables: dict[str, tuple[list[float], dict]], attrs: dict | None = None) -> xarray.Dataset:
    stamps = numpy.array([numpy.datetime64(t.replace(tzinfo=None), "ns") for t in times])
    data = {
        name: (("valid_time",), numpy.array(values, dtype="float64"), var_attrs)
        for name, (values, var_attrs) in variables.items()
    }
    return xarray.Dataset(data, coords={"valid_time": stamps}, attrs=attrs or {})


def kp_observed_pair(reference: datetime):
    times = [reference - timedelta(hours=6), reference - timedelta(hours=3), reference]
    dataset = series_dataset(times, {
        "kp_index": ([2.33, 3.67, 4.33], {"units": "dimensionless"}),
        "a_running": ([9.0, 15.0, 22.0], {"units": "dimensionless"}),
    })
    return make_artifact("noaa-swpc-kp", "kp_observed", "Planetary K index (observed)", reference), dataset


def kp_forecast_pair(reference: datetime):
    times = [reference, reference + timedelta(hours=3), reference + timedelta(hours=6)]
    dataset = series_dataset(times, {
        "kp_index": ([4.33, 4.0, 5.0], {"units": "dimensionless"}),
        "kp_status": ([0.0, 1.0, 2.0], {"units": "flag", "flag_values": [0, 1, 2], "flag_meanings": "observed estimated predicted"}),
    })
    return make_artifact("noaa-swpc-kp", "kp_forecast", "Planetary K index (3-day outlook, per-value status)", reference), dataset


def solar_wind_pair(reference: datetime, *, bz: list[float] | None = None, offset: timedelta = timedelta(0)):
    values = bz if bz is not None else [-3.89, -4.1, numpy.nan]
    times = [reference - offset - timedelta(minutes=len(values) - 1 - i) for i in range(len(values))]
    dataset = series_dataset(
        times,
        {
            "bz_gsm": (values, {"units": "nT"}),
            "bt": ([4.24, 4.3, 4.2][: len(values)], {"units": "nT"}),
        },
        attrs={"feed_declared_spacecraft": "SOLAR1"},
    )
    return make_artifact("noaa-swpc-rtsw", "solar_wind", "Real-time solar wind magnetic field (1-minute)", times[-1]), dataset


def ovation_pair(valid_time: datetime):
    latitudes = numpy.array([46.0, 47.0, 48.0, 49.0])
    longitudes = numpy.array([-54.0, -53.0, -52.0, -51.0])
    grid = numpy.full((1, 4, 4), 3.0)
    grid[0, 2, 1] = 12.0  # the cell nearest St. John's (48, -53)
    stamps = numpy.array([numpy.datetime64(valid_time.replace(tzinfo=None), "ns")])
    dataset = xarray.Dataset(
        {"aurora_probability": (("valid_time", "latitude", "longitude"), grid, {"units": "percent"})},
        coords={"valid_time": stamps, "latitude": latitudes, "longitude": longitudes},
    )
    artifact = make_artifact(
        "noaa-swpc-ovation", "aurora_grid", "OVATION aurora probability nowcast",
        valid_time, {"native_resolution": "1 deg lat x 1 deg lon (as served)", "native_crs": "EPSG:4326"},
    )
    return artifact, dataset


class StubStore(LiveStore):
    """A live store whose artifacts are already open; no object store touched."""

    def __init__(self, pairs) -> None:
        super().__init__(artifact_store=None, cache_dir=Path("/nonexistent"))
        self._pairs = list(pairs)

    def current(self):
        return [artifact for artifact, _ in self._pairs]

    def open(self, artifact):
        return next(dataset for candidate, dataset in self._pairs if candidate.revision_id == artifact.revision_id)

    def assert_object_store_reachable(self) -> None:
        """The double holds its datasets directly; reachability is not under test."""


def use_store(monkeypatch, data_mode, store) -> None:
    data_mode("live")
    monkeypatch.setattr(api_module, "live_store", lambda: store)
    monkeypatch.setattr(api_module, "_proxied_forecast_layers", lambda: ([], []))


def full_store(reference: datetime) -> StubStore:
    return StubStore([kp_observed_pair(reference), kp_forecast_pair(reference), solar_wind_pair(reference)])


# --- the live response -----------------------------------------------------


def test_space_weather_serves_kp_and_bz_with_provider_status(monkeypatch, data_mode):
    reference = datetime.now(UTC).replace(second=0, microsecond=0)
    use_store(monkeypatch, data_mode, full_store(reference))
    payload = client.get(f"{PREFIX}/space-weather").json()

    assert payload["data_mode"] == "live"
    assert payload["operational"] is False

    observed = payload["kp_observed"]
    assert observed["available"] is True
    assert observed["source_id"] == "noaa-swpc-kp"
    assert [reading["value"] for reading in observed["readings"]] == [2.33, 3.67, 4.33]
    # The observed series carries no provider status labels and no lead hours.
    assert all(reading["status"] is None for reading in observed["readings"])
    assert observed["freshness"]["status"] == "fresh"

    forecast = payload["kp_forecast"]
    assert forecast["available"] is True
    # The provider's own per-value status survives end to end, and nothing
    # shaped like a lead hour is attached anywhere.
    assert [reading["status"] for reading in forecast["readings"]] == ["observed", "estimated", "predicted"]
    assert forecast["readings"][-1]["value"] == 5.0
    assert "lead_hours" not in str(payload)

    wind = payload["solar_wind"]
    assert wind["available"] is True
    assert wind["bz_gsm_nt"] == -4.1
    assert wind["feed_declared_spacecraft"] == "SOLAR1"
    assert "DSCOVR" not in str(payload)
    assert wind["freshness"]["status"] == "fresh"


def test_latest_bz_is_the_newest_finite_record_with_its_own_instant(monkeypatch, data_mode):
    """The newest record is a gap (NaN). The served Bz is the newest *finite*
    record, with THAT record's measurement instant - never a zero, and never
    the gap's timestamp."""
    reference = datetime.now(UTC).replace(second=0, microsecond=0)
    use_store(monkeypatch, data_mode, full_store(reference))
    wind = client.get(f"{PREFIX}/space-weather").json()["solar_wind"]
    assert wind["bz_gsm_nt"] == -4.1
    measured = datetime.fromisoformat(wind["measured_at"]).astimezone(UTC)
    assert measured == reference - timedelta(minutes=1)


def test_all_gap_solar_wind_is_absent_never_zero(monkeypatch, data_mode):
    reference = datetime.now(UTC).replace(second=0, microsecond=0)
    store = StubStore([kp_observed_pair(reference), solar_wind_pair(reference, bz=[numpy.nan, numpy.nan, numpy.nan])])
    use_store(monkeypatch, data_mode, store)
    wind = client.get(f"{PREFIX}/space-weather").json()["solar_wind"]
    assert wind["available"] is False
    assert wind["bz_gsm_nt"] is None
    assert any("gap" in notice and "never zero" in notice for notice in wind["notices"])


def test_stale_solar_wind_is_marked_stale_with_its_age(monkeypatch, data_mode):
    reference = datetime.now(UTC).replace(second=0, microsecond=0)
    store = StubStore([solar_wind_pair(reference, offset=timedelta(hours=2))])
    use_store(monkeypatch, data_mode, store)
    wind = client.get(f"{PREFIX}/space-weather").json()["solar_wind"]
    assert wind["available"] is True
    assert wind["freshness"]["status"] == "stale"
    assert wind["freshness"]["age_seconds"] >= 7000
    assert any("stale" in notice for notice in wind["notices"])


def test_forecast_feed_absent_keeps_the_observed_series(monkeypatch, data_mode):
    reference = datetime.now(UTC).replace(second=0, microsecond=0)
    store = StubStore([kp_observed_pair(reference)])
    use_store(monkeypatch, data_mode, store)
    payload = client.get(f"{PREFIX}/space-weather").json()
    assert payload["data_mode"] == "live"
    assert payload["kp_observed"]["available"] is True
    forecast = payload["kp_forecast"]
    assert forecast["available"] is False
    assert forecast["readings"] == []
    assert any("kp_forecast" in notice for notice in forecast["notices"])


def test_nothing_published_is_absent_series_with_notices(monkeypatch, data_mode):
    use_store(monkeypatch, data_mode, StubStore([]))
    payload = client.get(f"{PREFIX}/space-weather").json()
    assert payload["data_mode"] == "unavailable"
    for key in ("kp_observed", "kp_forecast"):
        assert payload[key]["available"] is False
        assert payload[key]["readings"] == []
        assert payload[key]["notices"]
    assert payload["solar_wind"]["available"] is False
    assert payload["solar_wind"]["bz_gsm_nt"] is None
    assert any("nothing is invented" in notice for notice in payload["notices"])


def test_fixture_mode_fails_closed_with_no_invented_indices():
    payload = client.get(f"{PREFIX}/space-weather").json()
    assert payload["data_mode"] == "unavailable"
    assert payload["kp_observed"]["available"] is False
    assert payload["solar_wind"]["bz_gsm_nt"] is None
    assert any("no fixture space weather exists" in notice for notice in payload["notices"])


def test_unconfigured_mode_fails_closed(data_mode):
    data_mode(None)
    payload = client.get(f"{PREFIX}/space-weather").json()
    assert payload["data_mode"] == "unavailable"
    assert any("fails closed" in notice for notice in payload["notices"])


# --- planetary quantities never reach /point --------------------------------


def test_kp_and_bz_never_appear_in_point_fields():
    reference = now()
    store = StubStore([kp_observed_pair(reference), kp_forecast_pair(reference), solar_wind_pair(reference), ovation_pair(reference)])
    fields, _, _ = live_point_fields(store, *ST_JOHNS, reference)
    names = {item.field for item in fields}
    assert "kp_index" not in names and "bz_gsm" not in names and "bt" not in names and "a_running" not in names and "kp_status" not in names
    # No sample distance was ever attached to a planetary series.
    for item in fields:
        assert item.field == "aurora_probability"


def test_point_serves_aurora_probability_as_a_sampled_cell(monkeypatch, data_mode):
    reference = now()
    store = StubStore([ovation_pair(reference)])
    use_store(monkeypatch, data_mode, store)
    payload = client.get(f"{PREFIX}/point", params={"valid_time": reference.isoformat()}).json()
    by_field = {item["field"]: item for item in payload["fields"]}
    assert "aurora_probability" in by_field
    entry = by_field["aurora_probability"]
    assert entry["value"] == 12.0
    provenance = entry["provenance"]
    assert provenance["source_id"] == "noaa-swpc-ovation"
    assert "OVATION" in provenance["product"]
    # The sampled cell is named: the stored 1-degree cell, not the request.
    assert provenance["sampled_latitude"] == 48.0
    assert provenance["sampled_longitude"] == -53.0
    assert provenance["sample_distance_km"] is not None


# --- read_series shape guards ----------------------------------------------


def test_read_series_refuses_a_gridded_dataset():
    reference = now()
    store = StubStore([ovation_pair(reference)])
    assert store.read_series("noaa-swpc-ovation", "aurora_grid") is None
    assert store.skipped and "horizontal coordinates" in store.skipped[0].reason


def test_read_series_reads_flags_as_meanings():
    reference = now()
    store = StubStore([kp_forecast_pair(reference)])
    series = store.read_series("noaa-swpc-kp", "kp_forecast")
    assert series is not None
    assert series.variables["kp_status"].values == ["observed", "estimated", "predicted"]
    assert series.variables["kp_index"].values == [4.33, 4.0, 5.0]
