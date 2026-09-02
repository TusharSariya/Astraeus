from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable

import httpx
import pytest
from fastapi.testclient import TestClient

import sys as _sys

import weather_api.app  # noqa: F401  (registers the module for monkeypatching)
from registry.source_data import registry
from weather_api.app import PREFIX, app
from weather_api.fixtures import NEWFOUNDLAND, SOURCES, now, timeline, window_end, window_start
from weather_api.store import Sample, schedulable_source_ids

UTC = timezone.utc
NDT = timedelta(hours=-2, minutes=-30)
NST = timedelta(hours=-3, minutes=-30)

api_module = _sys.modules["weather_api.app"]

client = TestClient(app)


def request_at(pick: Callable[[datetime, datetime], datetime]) -> httpx.Response:
    """Ask for a point at a window-relative time, tolerating an hour rolling over.

    The window moves with the clock, so the boundary has to be computed from
    the same helper the API uses rather than written down as a date.
    """
    for _ in range(3):
        reference = now()
        moment = pick(window_start(reference), window_end(reference))
        response = client.get(f"{PREFIX}/point", params={"valid_time": moment.isoformat()})
        if now() == reference:
            break
    return response


@pytest.mark.parametrize("endpoint", ["catalog", "timeline", "layers", "point", "profile", "sources/status", "health", "ready"])
def test_get_endpoints(endpoint):
    response = client.get(f"{PREFIX}/{endpoint}")
    assert response.status_code == 200, response.text
    assert response.json()["data_mode"] == "fixture"
    assert response.json()["operational"] is False


def test_catalog_is_the_whole_registry_and_never_claims_an_active_source():
    """The catalogue is ``registry/source_data.py``, not a hand-written subset.

    The six-record fixture catalogue used to carry an id (``cyyt-metar``) that
    does not exist in the registry at all, so a caller could not resolve it.
    """
    payload = client.get(f"{PREFIX}/catalog").json()
    assert payload["experimental"] is True
    assert payload["data_mode"] == "fixture"
    assert payload["operational"] is False
    ids = [source["id"] for source in payload["sources"]]
    assert ids == [record["id"] for record in registry()["sources"]]
    assert len(ids) == 64
    assert "active" not in {source["state"] for source in payload["sources"]}
    assert all(source["status_reason"] and source["fixture_status"] for source in payload["sources"])
    assert {source["id"] for source in payload["sources"] if source["schedulable"]} == schedulable_source_ids()


def test_the_fixture_catalogue_only_names_real_registry_ids():
    """Fixture provenance must not dangle: every fixture source id resolves.

    ``cyyt-metar`` was never a registry id; the real one is ``awc-metar-speci``.
    """
    assert {source.id for source in SOURCES} <= {record["id"] for record in registry()["sources"]}


def test_timeline_has_exact_now_minus_three_to_plus_twenty_four_window_and_local_offsets():
    payload = client.get(f"{PREFIX}/timeline").json()
    start = datetime.fromisoformat(payload["start"])
    end = datetime.fromisoformat(payload["end"])
    assert (end - start).total_seconds() == 27 * 3600
    assert len(payload["items"]) == 28
    stamps = [datetime.fromisoformat(item["valid_time_utc"]) for item in payload["items"]]
    assert stamps[0] == start and stamps[-1] == end
    assert all(later - earlier == timedelta(hours=1) for earlier, later in zip(stamps, stamps[1:]))
    for item, stamp in zip(payload["items"], stamps):
        local = datetime.fromisoformat(item["valid_time_newfoundland"])
        assert local == stamp.astimezone(NEWFOUNDLAND)
        assert local.utcoffset() in {NDT, NST}
    assert "CYYT METAR/SPECI" in payload["items"][3]["available_products"]
    assert all("CYYT METAR/SPECI" not in item["available_products"] for item in payload["items"][4:])


def test_newfoundland_offsets_are_zoneinfo_driven_across_dst():
    """The -02:30/-03:30 split must come from the tz database, not a constant."""
    summer = timeline(datetime(2026, 7, 1, 15, tzinfo=UTC))
    winter = timeline(datetime(2026, 1, 15, 15, tzinfo=UTC))
    assert {item.valid_time_newfoundland.utcoffset() for item in summer} == {NDT}
    assert {item.valid_time_newfoundland.utcoffset() for item in winter} == {NST}
    assert all(item.valid_time_newfoundland == item.valid_time_utc.astimezone(NEWFOUNDLAND) for item in summer + winter)


def test_naive_valid_time_is_rejected():
    response = client.get(f"{PREFIX}/point", params={"valid_time": now().replace(tzinfo=None).isoformat()})
    assert response.status_code == 422
    assert "UTC offset" in response.json()["detail"]


def test_every_point_field_carries_complete_provenance_and_unknown_semantics():
    payload = client.get(f"{PREFIX}/point").json()
    required = {"data_mode", "operational", "source_id", "provider", "product", "forecast_centre", "valid_time", "retrieval_time", "vertical_level", "original_units", "normalized_units", "native_resolution", "native_crs", "quality", "coverage", "freshness", "licence", "attribution", "adapter_version", "contributing_evidence", "contributors"}
    assert all(required <= set(item["provenance"]) for item in payload["fields"])
    assert all(item["provenance"]["data_mode"] == "fixture" and item["provenance"]["operational"] is False for item in payload["fields"])
    assert all(item["provenance"]["freshness"]["status"] == "unknown" for item in payload["fields"])
    by_field = {item["field"]: item for item in payload["fields"]}
    assert by_field["fog_state"]["value"] == "unknown"
    assert by_field["radar_echo"]["value"] == "no_detected_precipitating_echo"
    assert by_field["relative_humidity"]["provenance"]["derivation_version"] == "metpy-1.7.1-liquid-v1"
    consensus = by_field["temperature"]["provenance"]
    assert payload["selection"]["selected_source_id"] == "multi-centre"
    assert payload["selection"]["selected_product_id"] == "experimental-consensus"
    assert {item["source_id"] for item in consensus["contributors"]} == {"eccc-hrdps", "noaa-gfs"}
    assert {item["licence"] for item in consensus["contributors"]} == {"Open Government Licence - Canada", "US public domain"}


@pytest.mark.parametrize(("params", "badge"), [({"consensus_evidence": False}, "HRDPS primary - consensus unavailable"), ({"consensus_evidence": False, "hrdps_fresh": False}, "RDPS fallback"), ({"consensus_evidence": False, "hrdps_fresh": False, "rdps_fresh": False}, "forecast unavailable")])
def test_point_explicit_fallbacks(params, badge):
    payload = client.get(f"{PREFIX}/point", params=params).json()
    assert payload["selection"]["badge"] == badge
    by_field = {item["field"]: item for item in payload["fields"]}
    temperatures = [by_field["temperature"]]
    if badge == "forecast unavailable":
        assert payload["selection"]["selected_source_id"] is None
        assert payload["selection"]["selected_product_id"] is None
        assert all(by_field[name]["value"] is None for name in ("temperature", "relative_humidity", "dew_point"))
        assert all(by_field[name]["provenance"]["source_id"] == "forecast-unavailable" for name in ("temperature", "relative_humidity", "dew_point"))
        assert all(by_field[name]["provenance"]["quality"]["status"] == "unknown" for name in ("temperature", "relative_humidity", "dew_point"))
        assert all(by_field[name]["provenance"]["coverage"]["status"] == "unknown" for name in ("temperature", "relative_humidity", "dew_point"))
    else:
        expected_product = "HRDPS" if badge.startswith("HRDPS") else "RDPS"
        assert temperatures[0]["provenance"]["product"] == expected_product
        expected_source_id = "eccc-hrdps" if expected_product == "HRDPS" else "eccc-rdps"
        assert payload["selection"]["selected_source_id"] == expected_source_id
        assert by_field["relative_humidity"]["provenance"]["source_id"] == expected_source_id


def test_profile_is_numeric_but_cross_section_is_explicitly_unavailable_without_spatial_arrays():
    profile = client.get(f"{PREFIX}/profile").json()
    assert [level["pressure_hpa"] for level in profile["levels"]] == [1000, 850, 700, 500, 300]
    response = client.post(f"{PREFIX}/cross-section", json={"path": [{"latitude": 47.56, "longitude": -52.71}, {"latitude": 47.0, "longitude": -51.1}], "fields": ["relative_humidity"]})
    assert response.status_code == 501
    assert "spatial arrays" in response.json()["detail"]
    unsupported = client.post(f"{PREFIX}/cross-section", json={"path": [{"latitude": 47.56, "longitude": -52.71}, {"latitude": 47.0, "longitude": -51.1}], "fields": ["rendered_pixel"]})
    assert unsupported.status_code == 422


def test_refresh_job_is_fixture_only_and_validates_sources():
    response = client.post(f"{PREFIX}/refresh", json={"source_ids": ["eccc-hrdps"]})
    assert response.status_code == 202
    job = response.json()
    assert job["state"] == "queued"
    assert job["operational_ingestion"] is False
    assert client.get(f"{PREFIX}/jobs/{job['id']}").json() == job
    assert client.post(f"{PREFIX}/refresh", json={"source_ids": ["not-real"]}).status_code == 422
    assert client.get(f"{PREFIX}/jobs/not-real").status_code == 404


@pytest.mark.parametrize(
    "source_id",
    ["google-weathernext-2", "raw-cwop-pws", "nl-511", "eccc-radiosonde"],
)
def test_refresh_rejects_a_source_the_scheduler_could_never_run(source_id):
    """A blocked or unwired registry id is not a job.

    Registry eligibility is necessary but insufficient: ``eccc-radiosonde``
    is implementing with known freshness but has no registered adapter.

    Spec-Refs: experiments/st-johns-weather-map/openspec/specs/source-registry-catalogue/spec.md
    """
    response = client.post(f"{PREFIX}/refresh", json={"source_ids": [source_id]})
    assert response.status_code == 422
    assert "not schedulable" in response.json()["detail"]
    assert source_id in response.json()["detail"]


def test_source_status_reports_registry_state_and_never_claims_live_activity():
    """Registry state is the ceiling and no source is ever reported active."""
    payload = client.get(f"{PREFIX}/sources/status").json()
    assert payload["data_mode"] == "fixture"
    assert payload["operational"] is False
    by_id = {item["source_id"]: item for item in payload["statuses"]}
    assert set(by_id) == {record["id"] for record in registry()["sources"]}
    assert all(item["state"] != "active" for item in payload["statuses"])
    assert all(item["state"] == record["status"] for record in registry()["sources"] for item in [by_id[record["id"]]])
    assert all(item["last_retrieval"] is None and item["freshness"]["status"] == "unknown" for item in payload["statuses"])


def test_a_fixture_deployment_is_ready_but_says_so():
    payload = client.get(f"{PREFIX}/ready").json()
    assert payload["ready"] is True
    assert payload["checks"]["live_store"] is False
    assert payload["data_mode"] == "fixture"


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [(46.5, -55.0), (46.5, -51.0), (48.5, -55.0), (48.5, -51.0)],
)
def test_avalon_fixture_coverage_boundaries_are_inclusive(latitude, longitude):
    assert client.get(f"{PREFIX}/point", params={"latitude": latitude, "longitude": longitude}).status_code == 200


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [(46.499, -52.7), (48.501, -52.7), (47.5, -55.001), (47.5, -50.999), (0, 0)],
)
def test_coordinates_outside_avalon_fixture_never_return_evidence(latitude, longitude):
    response = client.get(f"{PREFIX}/point", params={"latitude": latitude, "longitude": longitude})
    assert response.status_code == 422
    assert "outside" in response.json()["detail"]


@pytest.mark.parametrize(
    "pick",
    [
        lambda start, end: start - timedelta(seconds=1),
        lambda start, end: end + timedelta(seconds=1),
        lambda start, end: end + timedelta(days=365),
    ],
    ids=["before-start", "after-end", "far-future"],
)
def test_times_outside_the_rolling_window_never_return_fresh_evidence(pick):
    response = request_at(pick)
    assert response.status_code == 422
    assert "outside the available window" in response.json()["detail"]


@pytest.mark.parametrize(
    "pick",
    [lambda start, end: start, lambda start, end: end],
    ids=["window-start", "window-end"],
)
def test_rolling_window_boundaries_are_inclusive(pick):
    response = request_at(pick)
    assert response.status_code == 200, response.text
    assert datetime.fromisoformat(response.json()["valid_time"]).tzinfo is not None


def test_window_is_exactly_three_hours_back_and_twenty_four_forward():
    reference = now()
    assert reference.minute == reference.second == reference.microsecond == 0
    assert reference - window_start(reference) == timedelta(hours=3)
    assert window_end(reference) - reference == timedelta(hours=24)


def test_profile_and_cross_section_enforce_same_space_time_boundaries():
    assert client.get(f"{PREFIX}/profile", params={"latitude": 0, "longitude": 0}).status_code == 422
    response = client.post(f"{PREFIX}/cross-section", json={"path": [{"latitude": 47.56, "longitude": -52.71}, {"latitude": 0, "longitude": 0}]})
    assert response.status_code == 422


def test_openapi_contains_every_planned_endpoint():
    paths = client.get("/openapi.json").json()["paths"]
    expected = {"catalog", "timeline", "layers", "point", "profile", "cross-section", "sources/status", "refresh", "jobs/{job_id}", "health", "ready", "space-weather"}
    assert {f"{PREFIX}/{name}" for name in expected} <= set(paths)


# --- the truth boundary --------------------------------------------------
# Everything below asserts the rule the fixture fallthrough used to break: in
# live mode a failure must produce nulls and provenance, never a fixture number.

FIXTURE_TEMPERATURES = {16.0, 15.5, 15.2, 15.0, 14.8, 14.0}


class BrokenStore:
    """A live store whose every read raises, as an outage would."""

    skipped: list = []

    def sample_point(self, *args, **kwargs):
        raise RuntimeError("object store unreachable")

    def sample_profile(self, *args, **kwargs):
        raise RuntimeError("object store unreachable")

    def published_products(self):
        raise RuntimeError("object store unreachable")

    def current(self):
        raise RuntimeError("object store unreachable")

    def source_activity(self):
        raise RuntimeError("object store unreachable")


class EmptyStore(BrokenStore):
    """A reachable live store with nothing published."""

    def sample_point(self, *args, **kwargs):
        return []

    def sample_profile(self, *args, **kwargs):
        return {}

    def published_products(self):
        return {}

    def current(self):
        return []

    def source_activity(self):
        return {}


def use_live_store(monkeypatch, data_mode, store) -> None:
    data_mode("live")
    monkeypatch.setattr(api_module, "live_store", lambda: store)


@pytest.fixture(autouse=True)
def _registered_derivation_methods(derivation_registry):
    """Every derivation these endpoints serve is an enabled registry entry.

    A ``derived_here`` value is refused unless its method is registered and
    enabled, so the entries are stood up for this module rather than each
    endpoint test being about the registry.
    """


def assert_no_evidence_was_invented(payload: dict) -> None:
    assert payload["data_mode"] == "unavailable"
    assert payload["operational"] is False
    assert payload["fields"], "an unavailable response still names every field it cannot supply"
    for item in payload["fields"]:
        assert item["value"] is None
        provenance = item["provenance"]
        assert provenance["data_mode"] == "unavailable"
        assert provenance["operational"] is False
        assert provenance["quality"]["status"] == "unknown"
        assert provenance["coverage"]["status"] == "unknown"
        assert provenance["freshness"]["status"] == "unknown"
        assert "no_retrieval" in provenance["quality"]["flags"]
    assert payload["notices"], "an outage has to be named"


@pytest.mark.parametrize(("store", "flag"), [(BrokenStore(), "live_store_error"), (EmptyStore(), "no_published_artifact")], ids=["store-raises", "nothing-published"])
def test_a_live_failure_reports_unavailable_instead_of_a_fixture_number(monkeypatch, data_mode, store, flag):
    use_live_store(monkeypatch, data_mode, store)
    response = client.get(f"{PREFIX}/point")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert_no_evidence_was_invented(payload)
    assert any(flag in item["provenance"]["quality"]["flags"] for item in payload["fields"])
    assert payload["selection"]["selected_source_id"] is None
    values = {item["value"] for item in payload["fields"]}
    assert values == {None}
    assert not (FIXTURE_TEMPERATURES & {value for value in values if isinstance(value, float)})


def test_a_live_failure_leaves_the_profile_unavailable_rather_than_synthetic(monkeypatch, data_mode):
    use_live_store(monkeypatch, data_mode, BrokenStore())
    payload = client.get(f"{PREFIX}/profile").json()
    assert payload["data_mode"] == "unavailable"
    assert [level["pressure_hpa"] for level in payload["levels"]] == [1000, 850, 700, 500, 300]
    for level in payload["levels"]:
        for item in level["fields"]:
            assert item["value"] is None
            assert item["provenance"]["data_mode"] == "unavailable"
    assert payload["notices"]


@pytest.mark.parametrize("value", [None, "", "  ", "true", "FIXTURES", "Live "], ids=["missing", "empty", "blank", "old-flag", "typo", "trailing-space"])
def test_a_missing_or_malformed_data_mode_fails_closed_to_unavailable(data_mode, value):
    """Failing open to fixtures is exactly the defect; the default is nothing."""
    data_mode(value)
    payload = client.get(f"{PREFIX}/point").json()
    assert payload["data_mode"] == "unavailable"
    assert all(item["value"] is None for item in payload["fields"])
    assert all(item["provenance"]["data_mode"] == "unavailable" for item in payload["fields"])
    assert client.get(f"{PREFIX}/ready").json()["ready"] is False
    assert client.get(f"{PREFIX}/timeline").json()["data_mode"] == "unavailable"
    assert client.get(f"{PREFIX}/layers").json() == {**client.get(f"{PREFIX}/layers").json(), "layers": []}


def test_fixture_mode_stamps_every_single_field_as_fixture():
    """Fixture mode is retained, but it must be unmistakable field by field."""
    for params in ({}, {"product": "GFS"}, {"consensus_evidence": False, "hrdps_fresh": False, "rdps_fresh": False}):
        payload = client.get(f"{PREFIX}/point", params=params).json()
        assert payload["data_mode"] == "fixture"
        assert payload["fields"]
        assert all(item["provenance"]["data_mode"] == "fixture" for item in payload["fields"])
    profile = client.get(f"{PREFIX}/profile").json()
    assert profile["data_mode"] == "fixture"
    assert all(item["provenance"]["data_mode"] == "fixture" for level in profile["levels"] for item in level["fields"])


def test_product_selection_never_claims_a_source_that_published_nothing(monkeypatch, data_mode):
    """Selecting GFS when only HRDPS is published must not hand back HRDPS.

    Selecting HRDPS keeps the *observations* published beside it - the METAR
    visibility a reader lost when the header changed - each still labelled with
    its own source. Another model (RDPS) is not an observation and stays out.
    """

    class HrdpsWithNeighbours(EmptyStore):
        def sample_point(self, latitude, longitude, valid_time):
            return [
                Sample(
                    source_id="eccc-hrdps", logical_name="surface", variable="temperature_2m", value=9.25,
                    units="degC", evidence_class="retrieved", level="2 m above ground", valid_time=valid_time, run_time=None,
                    retrieved_at=None, native_crs="EPSG:4326", provenance={},
                ),
                _sample("eccc-rdps", "temperature_2m", 11.5, "degC", valid_time),
                _sample("awc-metar-speci", "visibility", 9656.0, "m", valid_time),
                _sample("awc-metar-speci", "cloud_layer_1_cover", 25.0, "percent", valid_time),
                _sample("awc-metar-speci", "cloud_layer_1_base", 609.6, "m", valid_time),
            ]

    use_live_store(monkeypatch, data_mode, HrdpsWithNeighbours())
    hrdps = client.get(f"{PREFIX}/point", params={"product": "HRDPS"}).json()
    assert hrdps["data_mode"] == "live"
    assert hrdps["selection"]["selected_source_id"] == "eccc-hrdps"
    assert hrdps["selection"]["badge"] == "HRDPS selected model"
    by_source = {}
    for item in hrdps["fields"]:
        by_source.setdefault(item["provenance"]["source_id"], []).append(item)
    # HRDPS's own values are exactly what HRDPS published, nothing borrowed in.
    assert [item["value"] for item in by_source["eccc-hrdps"]] == [9.25]
    # The METAR observations survive, and every one of them says it is METAR's.
    metar = {item["field"]: item["value"] for item in by_source["awc-metar-speci"]}
    assert metar["visibility"] == 9656.0
    assert metar["cloud_layer_1_cover"] == 25.0 and metar["cloud_layer_1_base"] == 609.6
    # A competing model is not an observation: RDPS's 11.5 appears nowhere.
    assert "eccc-rdps" not in by_source
    assert 11.5 not in {item["value"] for item in hrdps["fields"]}
    assert any("awc-metar-speci" in notice and "alongside HRDPS" in notice for notice in hrdps["notices"])

    payload = client.get(f"{PREFIX}/point", params={"product": "GFS"}).json()
    assert_no_evidence_was_invented(payload)
    assert 9.25 not in {item["value"] for item in payload["fields"]}
    assert any("noaa-gfs" in notice for notice in payload["notices"])
    assert all(item["provenance"]["source_id"] == "noaa-gfs" for item in payload["fields"])
    assert any("no_published_artifact:noaa-gfs" in item["provenance"]["quality"]["flags"] for item in payload["fields"])

    # An unknown product is still refused outright.
    assert client.get(f"{PREFIX}/point", params={"product": "NOPE"}).status_code == 422


def test_observations_kept_under_a_product_are_decided_by_registry_category_not_id_shape(monkeypatch, data_mode):
    """Only sources the registry files as observations ride along; nothing is inferred from an id."""
    from weather_api.app import OBSERVATION_CATEGORIES
    from weather_api.store import source_category

    assert source_category("awc-metar-speci") == "aviation"
    assert source_category("eccc-swob") == "surface_observation"
    assert source_category("eccc-radar") == "radar"
    assert source_category("eccc-rdps") == "deterministic_forecast"
    assert source_category("no-such-source") is None
    assert {"aviation", "surface_observation", "radar", "satellite"} <= OBSERVATION_CATEGORIES
    assert "deterministic_forecast" not in OBSERVATION_CATEGORIES
    assert "ensemble" not in OBSERVATION_CATEGORIES

    class HrdpsAndAnUnknownSource(EmptyStore):
        def sample_point(self, latitude, longitude, valid_time):
            return [
                _sample("eccc-hrdps", "temperature_2m", 9.25, "degC", valid_time),
                _sample("no-such-source", "visibility", 100.0, "m", valid_time),
            ]

    use_live_store(monkeypatch, data_mode, HrdpsAndAnUnknownSource())
    payload = client.get(f"{PREFIX}/point", params={"product": "HRDPS"}).json()
    assert {item["provenance"]["source_id"] for item in payload["fields"]} == {"eccc-hrdps"}
    assert not any("alongside" in notice for notice in payload["notices"])


def test_a_taf_never_rides_along_as_an_observation(monkeypatch, data_mode):
    """TAF is filed under ``aviation`` like METAR but is a forecast: it stays out by name."""
    from weather_api.app import FORECASTS_FILED_AS_OBSERVATIONS
    from weather_api.store import source_category

    assert source_category("awc-taf") == "aviation"
    assert "awc-taf" in FORECASTS_FILED_AS_OBSERVATIONS

    class HrdpsMetarAndTaf(EmptyStore):
        def sample_point(self, latitude, longitude, valid_time):
            return [
                _sample("eccc-hrdps", "temperature_2m", 9.25, "degC", valid_time),
                _sample("awc-metar-speci", "visibility", 16093.0, "m", valid_time),
                _sample("awc-taf", "visibility", 9656.0, "m", valid_time),
            ]

    use_live_store(monkeypatch, data_mode, HrdpsMetarAndTaf())
    payload = client.get(f"{PREFIX}/point", params={"product": "HRDPS"}).json()
    assert {item["provenance"]["source_id"] for item in payload["fields"]} == {"eccc-hrdps", "awc-metar-speci"}
    assert any("awc-metar-speci" in notice and "awc-taf" not in notice for notice in payload["notices"])


def _sample(source_id: str, variable: str, value: float | None, units: str, valid_time: datetime) -> Sample:
    return Sample(
        source_id=source_id, logical_name="surface", variable=variable, value=value, units=units, evidence_class="retrieved",
        level="surface", valid_time=valid_time, run_time=None, retrieved_at=None, native_crs="EPSG:4326", provenance={},
    )


def test_wind_is_served_as_speed_and_direction_with_its_derivation_disclosed(monkeypatch, data_mode):
    """Stored u/v components reach the reader as speed and a from-direction, never silently."""

    class HrdpsWind(EmptyStore):
        def sample_point(self, latitude, longitude, valid_time):
            return [
                _sample("eccc-hrdps", "temperature_2m", 9.25, "degC", valid_time),
                _sample("eccc-hrdps", "wind_u_10m", -3.0, "m s-1", valid_time),
                _sample("eccc-hrdps", "wind_v_10m", 0.0, "m s-1", valid_time),
            ]

    use_live_store(monkeypatch, data_mode, HrdpsWind())
    payload = client.get(f"{PREFIX}/point", params={"product": "HRDPS"}).json()
    assert payload["data_mode"] == "live"
    by_field = {item["field"]: item for item in payload["fields"]}
    assert "wind_u" not in by_field and "wind_v" not in by_field
    speed, direction = by_field["wind_speed"], by_field["wind_direction"]
    assert speed["value"] == 3.0 and speed["provenance"]["normalized_units"] == "m s-1"
    assert direction["value"] == 90.0 and direction["provenance"]["normalized_units"] == "degree"
    for item in (speed, direction):
        assert item["provenance"]["source_id"] == "eccc-hrdps"
        assert "MetPy" in item["provenance"]["derivation"]
        assert item["provenance"]["derivation_version"] == "metpy-1.7.1-wind-v1"


def test_derived_relative_humidity_is_reported_in_percent_for_rdps(monkeypatch, data_mode):
    class RdpsOnly(EmptyStore):
        def sample_point(self, latitude, longitude, valid_time):
            return [
                _sample("eccc-rdps", "temperature_2m", 14.5, "degC", valid_time),
                _sample("eccc-rdps", "dew_point_2m", 11.0, "degC", valid_time),
            ]

    use_live_store(monkeypatch, data_mode, RdpsOnly())
    payload = client.get(f"{PREFIX}/point", params={"product": "RDPS"}).json()
    humidity = next(item for item in payload["fields"] if item["field"] == "relative_humidity")
    assert humidity["provenance"]["derivation_version"] == "metpy-1.7.1-liquid-v1"
    assert humidity["provenance"]["original_units"] == "percent"
    assert humidity["provenance"]["normalized_units"] == "percent"


def test_a_selected_product_is_named_in_the_reason_even_when_nothing_at_all_is_stored(monkeypatch, data_mode):
    """At the edge of the window the generic reason used to fire first and drop the product."""
    use_live_store(monkeypatch, data_mode, EmptyStore())
    payload = client.get(f"{PREFIX}/point", params={"product": "REPS", "valid_time": window_end().isoformat()}).json()
    assert_no_evidence_was_invented(payload)
    assert "REPS" in payload["selection"]["reason"]
    assert all(item["provenance"]["source_id"] == "eccc-reps" for item in payload["fields"])
    assert any("no_published_artifact:eccc-reps" in item["provenance"]["quality"]["flags"] for item in payload["fields"])


def test_the_timeline_lists_only_hours_that_actually_have_a_published_artifact(monkeypatch, data_mode):
    """The hardcoded ["HRDPS", "GFS", "REPS"] per hour was a claim, not coverage."""
    use_live_store(monkeypatch, data_mode, EmptyStore())
    payload = client.get(f"{PREFIX}/timeline").json()
    assert payload["data_mode"] == "unavailable"
    assert len(payload["items"]) == 28
    assert all(item["available_products"] == [] for item in payload["items"])
    assert payload["notices"]

    covered = now()

    class OneHour(EmptyStore):
        def published_products(self):
            return {"eccc-hrdps": {covered}}

    use_live_store(monkeypatch, data_mode, OneHour())
    payload = client.get(f"{PREFIX}/timeline").json()
    assert payload["data_mode"] == "live"
    populated = [item for item in payload["items"] if item["available_products"]]
    assert [item["available_products"] for item in populated] == [["eccc-hrdps"]]


def test_a_frame_landing_off_the_hour_still_populates_its_hour(monkeypatch, data_mode):
    """Radar publishes at :18 and lightning at :12, never at :00.

    The timeline is an hourly index, so it has to say which HOUR holds a
    published frame. Keying it on the exact artifact stamp meant only a frame
    that happened to land on the hour ever matched, and 25 of 28 hours read as
    empty while their evidence sat a few minutes away.
    """
    hour = now()

    class OffTheHour(EmptyStore):
        def published_products(self):
            return {
                "eccc-radar": {hour + timedelta(minutes=18), hour + timedelta(minutes=42)},
                "eccc-lightning": {hour - timedelta(hours=1) + timedelta(minutes=12)},
            }

    use_live_store(monkeypatch, data_mode, OffTheHour())
    payload = client.get(f"{PREFIX}/timeline").json()
    assert payload["data_mode"] == "live"
    at_hour = {
        datetime.fromisoformat(item["valid_time_utc"]).astimezone(UTC): item["available_products"]
        for item in payload["items"]
    }
    # Both of radar's sub-hour frames fold into the same hour, and only once.
    assert at_hour[hour] == ["eccc-radar"]
    assert at_hour[hour - timedelta(hours=1)] == ["eccc-lightning"]
    assert len([item for item in payload["items"] if item["available_products"]]) == 2


def test_layers_are_unavailable_rather_than_the_fixture_list_when_nothing_is_published(monkeypatch, data_mode):
    use_live_store(monkeypatch, data_mode, EmptyStore())
    # Live-proxied imagery is a separate offer with its own tests; with it out
    # of the way, an empty store must produce nothing rather than the fixtures.
    monkeypatch.setattr(api_module, "_proxied_forecast_layers", lambda: ([], []))
    payload = client.get(f"{PREFIX}/layers").json()
    assert payload["data_mode"] == "unavailable"
    assert payload["layers"] == []
    assert payload["notices"]


def test_live_readiness_requires_the_store_and_a_current_evidence_boundary(monkeypatch, data_mode):
    """``ready: true`` with ``live_store: false`` was the original lie."""
    data_mode("live")
    monkeypatch.setattr(api_module, "live_store", lambda: None)
    payload = client.get(f"{PREFIX}/ready").json()
    assert payload["ready"] is False
    assert payload["checks"]["live_store"] is False
    assert payload["checks"]["evidence_boundary"] is False
    assert payload["data_mode"] == "unavailable"

    use_live_store(monkeypatch, data_mode, EmptyStore())
    payload = client.get(f"{PREFIX}/ready").json()
    assert payload["ready"] is False, "a reachable store with nothing published is not ready"
    assert payload["checks"]["live_store"] is True
    assert payload["checks"]["evidence_boundary"] is False

    covered = now()

    class Covered(EmptyStore):
        def published_products(self):
            return {"eccc-hrdps": {covered}}

    use_live_store(monkeypatch, data_mode, Covered())
    payload = client.get(f"{PREFIX}/ready").json()
    assert payload["ready"] is True
    assert payload["data_mode"] == "live"


def test_a_live_source_status_never_promotes_a_source_to_active(monkeypatch, data_mode):
    retrieved = datetime.now(UTC)

    class Retrieving(EmptyStore):
        def source_activity(self):
            return {"eccc-hrdps": retrieved}

    use_live_store(monkeypatch, data_mode, Retrieving())
    payload = client.get(f"{PREFIX}/sources/status").json()
    by_id = {item["source_id"]: item for item in payload["statuses"]}
    assert payload["data_mode"] == "mixed"
    assert by_id["eccc-hrdps"]["state"] == "implementing"
    assert by_id["eccc-hrdps"]["freshness"]["status"] == "fresh"
    assert by_id["eccc-hrdps"]["data_mode"] == "live"
    assert all(item["state"] != "active" for item in payload["statuses"])
    assert by_id["noaa-gfs"]["data_mode"] == "unavailable"
    assert by_id["noaa-gfs"]["last_retrieval"] is None


def test_a_refresh_cannot_be_faked_into_a_fixture_job_when_the_live_store_is_down(monkeypatch, data_mode):
    data_mode("live")
    monkeypatch.setattr(api_module, "live_store", lambda: None)
    response = client.post(f"{PREFIX}/refresh", json={"source_ids": ["eccc-hrdps"]})
    assert response.status_code == 503
