"""Live-proxied map imagery, and the honesty rules that make it admissible.

Serving a GeoMet tile bypasses the ingest spine entirely: nothing is fetched by
the worker, validated against a manifest, QC-gated or published atomically. That
is an approved deviation only while the difference stays visible, so what is
under test here is mostly the visibility:

* a proxied layer says ``evidence_basis: live_proxy`` and never masquerades as
  a stored artifact in ``/layers``, ``/timeline`` or ``/point``;
* a WMS layer name comes from an artifact's own recorded provenance, or the
  layer keeps its 501 - it is never inferred from a layer id;
* the combined radar string is split rather than passed through;
* a time axis comes from ``GetCapabilities``, never from a generated range;
* and a transparent PNG is a reading, not an outage.

Every upstream call is stubbed. The live service is exercised separately.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

import sys as _sys

import weather_api.app  # noqa: F401
from ingest.store import CurrentArtifact
from weather_api import wms
from weather_api.app import PREFIX, app
from weather_api.fixtures import now

UTC = timezone.utc
api_module = _sys.modules["weather_api.app"]
client = TestClient(app)

#: What GeoMet answers for a radar sweep with nothing in it: a real reading.
TRANSPARENT_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 326


def artifact(*, source_id: str, logical_name: str, provenance: dict[str, Any], media_type: str = "application/zarr+zip") -> CurrentArtifact:
    stamp = now()
    return CurrentArtifact(
        source_id=source_id,
        logical_name=logical_name,
        revision_id=f"revision-{source_id}-{logical_name}",
        object_key=f"artifacts/{source_id}/{logical_name}",
        media_type=media_type,
        byte_size=1024,
        provenance=provenance,
        published_at=stamp,
        run_time=stamp,
        retrieved_at=stamp,
        provider_run_id="2026083003",
        native_crs="EPSG:4326",
    )


class ArtifactStore:
    """A reachable live store publishing exactly the artifacts it is given."""

    skipped: list = []

    def __init__(self, artifacts: list[CurrentArtifact]) -> None:
        self._artifacts = artifacts

    def current(self):
        return list(self._artifacts)

    def published_layer_times(self):
        return {}

    def published_products(self):
        return {}

    def sample_point(self, *args, **kwargs):
        return []

    def source_activity(self):
        return {}


@pytest.fixture(autouse=True)
def _no_shared_client_between_tests():
    wms.reset_client()
    yield
    wms.reset_client()


def use_live_store(monkeypatch, data_mode, store) -> None:
    data_mode("live")
    monkeypatch.setattr(api_module, "live_store", lambda: store)


class FakeImage:
    def __init__(self, layer: str, payload: bytes = TRANSPARENT_PNG, *, style: str | None = None, valid_time: datetime | None = None) -> None:
        self.payload = payload
        self.content_type = "image/png"
        self.layer = layer
        self.url = f"https://geo.weather.gc.ca/geomet/?LAYERS={layer}"
        self.style = style
        self.valid_time = valid_time or now()
        self.reference_time = now() - timedelta(hours=4)
        self.byte_size = len(payload)


def stub_render(monkeypatch, *, calls: list[str] | None = None, payload: bytes = TRANSPARENT_PNG):
    def fake(layer, bounds, **kwargs):
        if calls is not None:
            calls.append(layer)
        return FakeImage(layer, payload, style=kwargs.get("style"), valid_time=kwargs.get("valid_time"))

    def fake_legend(layer, **kwargs):
        if calls is not None:
            calls.append(f"legend:{layer}")
        return FakeImage(layer, payload, style=kwargs.get("style"))

    class FakeClient:
        map_image = staticmethod(fake)
        legend_graphic = staticmethod(fake_legend)

    monkeypatch.setattr(wms, "geomet_client", lambda: FakeClient())


# --- layer titles and groups --------------------------------------------

def test_published_layer_titles_and_groups_come_from_recorded_provenance_and_geometry(monkeypatch, data_mode):
    """A reader must be able to tell the alert count grid from the alert
    polygons, and the drawer must not have to guess a group from an id."""
    from weather_api.store import LayerCoverage

    stamp = now()
    alerts_product = "MSC current public alerts (CAP) via GeoMet WMS"
    published = [
        artifact(source_id="eccc-hrdps", logical_name="surface", provenance={"product": "ECCC-HRDPS"}),
        artifact(source_id="awc-metar-speci", logical_name="surface", provenance={"product": "CYYT METAR/SPECI"}),
        artifact(source_id="eccc-cap-alerts", logical_name="alerts", provenance={"product": alerts_product, "layer": "Current-Alerts"}),
        artifact(source_id="eccc-cap-alerts", logical_name="alerts_features", provenance={"product": alerts_product, "layer": "Current-Alerts"}, media_type="application/geo+json"),
        artifact(source_id="eccc-radar", logical_name="radar", provenance={"product": "Canadian radar composite precipitation rate via GeoMet WMS", "layers": {"RADAR_1KM_RRAI": {}}}),
    ]

    def coverage(layer_id: str, source_id: str, logical_name: str, *, gridded: bool) -> LayerCoverage:
        return LayerCoverage(layer_id=layer_id, source_id=source_id, logical_name=logical_name, times=[stamp], cadence_seconds=None, sites=[(47.56, -52.71)], gridded=gridded)

    class Store(ArtifactStore):
        def published_layer_times(self):
            return {
                "eccc-hrdps-surface": coverage("eccc-hrdps-surface", "eccc-hrdps", "surface", gridded=True),
                "awc-metar-speci-surface": coverage("awc-metar-speci-surface", "awc-metar-speci", "surface", gridded=False),
                "eccc-cap-alerts-alerts": coverage("eccc-cap-alerts-alerts", "eccc-cap-alerts", "alerts", gridded=False),
                "eccc-radar-radar": coverage("eccc-radar-radar", "eccc-radar", "radar", gridded=False),
            }

    use_live_store(monkeypatch, data_mode, Store(published))
    monkeypatch.setattr(api_module, "_proxied_forecast_layers", lambda: ([], []))

    payload = client.get(f"{PREFIX}/layers").json()
    by_id = {item["id"]: item for item in payload["layers"]}

    assert by_id["eccc-hrdps-surface"]["group"] == "published_model"
    assert by_id["awc-metar-speci-surface"]["group"] == "observation"
    assert by_id["eccc-radar-radar"]["group"] == "observation"
    assert by_id["eccc-cap-alerts-alerts"]["group"] == "alert"
    assert by_id["eccc-cap-alerts-alerts_features"]["group"] == "alert"

    # Titles are composed from the product the adapter recorded; nothing is
    # looked up in a prose table keyed by id.
    assert by_id["eccc-hrdps-surface"]["title"].startswith("ECCC-HRDPS surface")
    assert by_id["awc-metar-speci-surface"]["title"].startswith("CYYT METAR/SPECI surface")
    count, polygons = by_id["eccc-cap-alerts-alerts"]["title"], by_id["eccc-cap-alerts-alerts_features"]["title"]
    assert count != polygons
    assert count.startswith(alerts_product) and polygons.startswith(alerts_product)
    assert "sampled points" in count and "alert features" in polygons
    # No recorded product: the id-derived title stands rather than a guess.
    assert len({item["title"] for item in payload["layers"]}) == len(payload["layers"])


# --- resolving the WMS layer name ---------------------------------------

def test_the_wms_layer_comes_from_recorded_provenance():
    binding = wms.binding_from_provenance({"geomet_layer": "RADAR_1KM_RRAI"})
    assert binding is not None
    assert binding.wms_layer == "RADAR_1KM_RRAI"
    assert binding.combined is False


def test_an_artifact_that_recorded_no_layer_gets_no_guess():
    assert wms.binding_from_provenance({}) is None
    assert wms.binding_from_provenance({"geomet_layer": "  "}) is None
    assert wms.binding_from_provenance({"product": "TAF", "units": "mixed"}) is None
    assert wms.binding_from_provenance(None) is None


def test_every_key_an_adapter_actually_records_is_read():
    """The vector adapters record ``layer``; the multi-layer ones ``layers``.

    Read as published, verbatim, from the running store: AQHI and CAP write a
    single ``layer`` string, lightning and radar write a ``layers`` mapping
    keyed by WMS layer name. Only one of the three keys is ``geomet_layer``, so
    reading that alone left every published GeoMet layer with no imagery.
    """
    assert wms.binding_from_provenance({"layer": "AQHI-OBS"}).wms_layer == "AQHI-OBS"
    assert wms.binding_from_provenance({"layer": "Current-Alerts"}).wms_layer == "Current-Alerts"
    single = wms.binding_from_provenance({"layers": {"Lightning_2.5km_Density": {"units": "flash"}}})
    assert single.wms_layer == "Lightning_2.5km_Density"
    assert single.combined is False
    both = wms.binding_from_provenance({"layers": {"RADAR_1KM_RRAI": {}, "RADAR_1KM_RSNO": {}}})
    assert both.alternatives == ("RADAR_1KM_RRAI", "RADAR_1KM_RSNO")
    assert both.combined is True
    assert both.wms_layer == "RADAR_1KM_RRAI"


def test_the_combined_radar_string_is_split_rather_than_sent_as_a_layers_value():
    """``"RADAR_1KM_RRAI + RADAR_1KM_RSNO"`` is not a valid LAYERS value."""
    binding = wms.binding_from_provenance({"geomet_layer": "RADAR_1KM_RRAI + RADAR_1KM_RSNO"})
    assert binding is not None
    assert binding.combined is True
    assert binding.alternatives == ("RADAR_1KM_RRAI", "RADAR_1KM_RSNO")
    assert binding.wms_layer == "RADAR_1KM_RRAI"
    assert "+" not in binding.wms_layer


def test_a_layer_with_no_recorded_wms_backing_keeps_its_501(monkeypatch, data_mode):
    published = artifact(source_id="awc-taf", logical_name="taf", provenance={"product": "TAF"})
    use_live_store(monkeypatch, data_mode, ArtifactStore([published]))

    response = client.get(f"{PREFIX}/layers/awc-taf-taf/raster")

    assert response.status_code == 501, response.text
    detail = response.json()["detail"]
    assert "no published map image" in detail
    assert "no layer name is guessed" in detail


def test_an_unknown_layer_is_a_404_not_an_invented_render(monkeypatch, data_mode):
    use_live_store(monkeypatch, data_mode, ArtifactStore([]))
    response = client.get(f"{PREFIX}/layers/not-a-layer/raster")
    assert response.status_code == 404


# --- serving the image ---------------------------------------------------

def test_a_published_layer_serves_a_png_with_its_provenance_on_the_response(monkeypatch, data_mode):
    published = artifact(source_id="eccc-radar", logical_name="rain", provenance={"geomet_layer": "RADAR_1KM_RRAI"})
    use_live_store(monkeypatch, data_mode, ArtifactStore([published]))
    stub_render(monkeypatch)

    response = client.get(f"{PREFIX}/layers/eccc-radar-rain/raster")

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "image/png"
    assert response.headers["x-weather-wms-layer"] == "RADAR_1KM_RRAI"
    assert "geo.weather.gc.ca" in response.headers["x-weather-upstream-url"]
    assert response.headers["x-weather-valid-time"] != "none"
    assert response.headers["x-weather-reference-time"] != "none"
    # The layer's evidence is stored; the picture of it never is.
    assert response.headers["x-weather-evidence-basis"] == "published_artifact"
    assert response.headers["x-weather-image-basis"] == "live_proxy"
    assert response.headers["x-weather-operational"] == "false"


def test_a_transparent_tile_is_reported_as_retrieved_and_not_as_unavailable(monkeypatch, data_mode):
    """Radar with no echo answers ~334 bytes of nothing. That is the answer."""
    published = artifact(source_id="eccc-radar", logical_name="rain", provenance={"geomet_layer": "RADAR_1KM_RRAI"})
    use_live_store(monkeypatch, data_mode, ArtifactStore([published]))
    stub_render(monkeypatch, payload=TRANSPARENT_PNG)

    response = client.get(f"{PREFIX}/layers/eccc-radar-rain/raster")

    assert response.status_code == 200
    assert len(response.content) == len(TRANSPARENT_PNG) < 400
    assert response.headers["x-weather-retrieval-status"] == "retrieved"
    assert "not unavailable" in response.headers["x-weather-render-semantics"]


def test_an_untimed_image_says_it_is_current_rather_than_borrowing_a_time(monkeypatch, data_mode):
    """``Current-Alerts`` has no time dimension; the response must say so, not
    leave a client to stamp the scrubbed time on it."""
    published = artifact(source_id="eccc-cap-alerts", logical_name="alerts", provenance={"layer": "Current-Alerts"})
    use_live_store(monkeypatch, data_mode, ArtifactStore([published]))

    class Untimed(FakeImage):
        def __init__(self, layer, payload=TRANSPARENT_PNG, **kwargs):
            super().__init__(layer, payload)
            self.valid_time = None

    class FakeClient:
        map_image = staticmethod(lambda layer, bounds, **kwargs: Untimed(layer))

    monkeypatch.setattr(wms, "geomet_client", lambda: FakeClient())

    response = client.get(f"{PREFIX}/layers/eccc-cap-alerts-alerts/raster")

    assert response.status_code == 200, response.text
    assert response.headers["x-weather-valid-time"] == "none"
    semantics = response.headers["x-weather-time-semantics"]
    assert "current" in semantics and "not time-indexed" in semantics
    # The transparent-image semantics header is untouched by this.
    assert "not unavailable" in response.headers["x-weather-render-semantics"]


def test_a_timed_image_says_its_time_is_the_valid_time_header(monkeypatch, data_mode):
    published = artifact(source_id="eccc-radar", logical_name="rain", provenance={"geomet_layer": "RADAR_1KM_RRAI"})
    use_live_store(monkeypatch, data_mode, ArtifactStore([published]))
    stub_render(monkeypatch)
    response = client.get(f"{PREFIX}/layers/eccc-radar-rain/raster")
    assert response.headers["x-weather-valid-time"] != "none"
    assert "X-Weather-Valid-Time" in response.headers["x-weather-time-semantics"]


def test_a_failure_to_retrieve_is_an_error_and_substitutes_nothing(monkeypatch, data_mode):
    published = artifact(source_id="eccc-radar", logical_name="rain", provenance={"geomet_layer": "RADAR_1KM_RRAI"})
    use_live_store(monkeypatch, data_mode, ArtifactStore([published]))

    class FailingClient:
        @staticmethod
        def map_image(layer, bounds, **kwargs):
            raise RuntimeError("connection reset")

    monkeypatch.setattr(wms, "geomet_client", lambda: FailingClient())
    response = client.get(f"{PREFIX}/layers/eccc-radar-rain/raster")

    assert response.status_code == 502
    assert "no image was retrieved upstream" in response.json()["detail"]


def test_a_frame_the_layer_does_not_advertise_is_refused_before_the_request(monkeypatch, data_mode):
    published = artifact(source_id="eccc-radar", logical_name="rain", provenance={"geomet_layer": "RADAR_1KM_RRAI"})
    use_live_store(monkeypatch, data_mode, ArtifactStore([published]))

    from ingest.adapters.eccc_geomet import TimeOutsideExtent

    class PickyClient:
        @staticmethod
        def map_image(layer, bounds, **kwargs):
            raise TimeOutsideExtent("that instant is outside the advertised extent")

    monkeypatch.setattr(wms, "geomet_client", lambda: PickyClient())
    response = client.get(f"{PREFIX}/layers/eccc-radar-rain/raster")

    # Not an outage: the frame does not exist, and the two must read differently.
    assert response.status_code == 422
    assert "outside the advertised extent" in response.json()["detail"]


def test_the_combined_radar_layer_is_drawn_from_one_member_and_says_which(monkeypatch, data_mode):
    published = artifact(
        source_id="eccc-radar",
        logical_name="precipitation",
        provenance={"geomet_layer": "RADAR_1KM_RRAI + RADAR_1KM_RSNO"},
    )
    use_live_store(monkeypatch, data_mode, ArtifactStore([published]))
    calls: list[str] = []
    stub_render(monkeypatch, calls=calls)

    response = client.get(f"{PREFIX}/layers/eccc-radar-precipitation/raster")

    assert response.status_code == 200
    assert calls == ["RADAR_1KM_RRAI"]
    assert response.headers["x-weather-wms-layer"] == "RADAR_1KM_RRAI"
    assert "RADAR_1KM_RSNO" in response.headers["x-weather-wms-layer-notice"]


def test_the_legend_is_the_upstream_ramp(monkeypatch, data_mode):
    published = artifact(source_id="eccc-radar", logical_name="rain", provenance={"geomet_layer": "RADAR_1KM_RRAI"})
    use_live_store(monkeypatch, data_mode, ArtifactStore([published]))
    calls: list[str] = []
    stub_render(monkeypatch, calls=calls)

    response = client.get(f"{PREFIX}/layers/eccc-radar-rain/legend?style=RADARURPPRECIPR")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert calls == ["legend:RADAR_1KM_RRAI"]
    assert response.headers["x-weather-style"] == "RADARURPPRECIPR"


# --- the proxied forecast layers ----------------------------------------

class FakeExtent:
    def __init__(self, times, period_seconds=3600):
        self._times = tuple(times)
        self.period = timedelta(seconds=period_seconds)

    def steps(self, *, limit: int = 4096):
        return self._times


class FakeCapability:
    def __init__(self, times, title="Air temperature [degC]", period_seconds=3600):
        self.time = FakeExtent(times, period_seconds) if times else None
        self.title = title

    @property
    def units(self):
        from ingest.adapters.eccc_geomet import parse_title_units

        return parse_title_units(self.title)


def stub_capabilities(monkeypatch, times):
    class FakeClient:
        @staticmethod
        def capabilities(layer, refresh: bool = False):
            return FakeCapability(times)

    monkeypatch.setattr(wms, "geomet_client", lambda: FakeClient())


def forward_hours(count: int = 30) -> list[datetime]:
    base = now() - timedelta(hours=2)
    return [base + timedelta(hours=index) for index in range(count)]


def test_proxied_forecast_layers_carry_future_frames_and_are_marked_live_proxy(monkeypatch, data_mode):
    use_live_store(monkeypatch, data_mode, ArtifactStore([]))
    stub_capabilities(monkeypatch, forward_hours())

    payload = client.get(f"{PREFIX}/layers").json()
    proxied = [layer for layer in payload["layers"] if layer["evidence_basis"] == "live_proxy"]

    assert proxied, "the forward window has to be fillable"
    assert {layer["id"] for layer in proxied} == {spec.layer_id for spec in wms.PROXIED_LAYERS}
    reference = now()
    for layer in proxied:
        spec = wms.forecast_spec(layer["id"])
        assert spec is not None
        # The upstream name and product come from the spec, never inferred.
        assert layer["upstream_wms_layer"] == spec.wms_layer
        assert layer["product"] == spec.product
        assert layer["raster_available"] is True
        assert layer["group"] == (spec.group or "forecast_proxy")
        assert "NOT a published artifact" in layer["semantics"]
        if spec in wms.FORECAST_LAYERS:
            future = [stamp for stamp in layer["times"] if datetime.fromisoformat(stamp).astimezone(UTC) > reference]
            assert future, "a forecast layer with no future frame fills nothing"
    assert payload["operational"] is False


def test_a_proxied_layer_never_appears_as_a_stored_artifact(monkeypatch, data_mode):
    """The whole deviation rests on this: it must not look published."""
    use_live_store(monkeypatch, data_mode, ArtifactStore([]))
    stub_capabilities(monkeypatch, forward_hours())

    layers = client.get(f"{PREFIX}/layers").json()["layers"]
    assert all(layer["evidence_basis"] == "live_proxy" for layer in layers)

    # Neither the timeline nor the point response knows anything about them.
    timeline = client.get(f"{PREFIX}/timeline").json()
    assert all(item["available_products"] == [] for item in timeline["items"])
    point = client.get(f"{PREFIX}/point").json()
    assert point["data_mode"] == "unavailable"
    assert all(item["value"] is None for item in point["fields"])


def test_unreadable_capabilities_produce_no_frames_rather_than_an_invented_range(monkeypatch, data_mode):
    use_live_store(monkeypatch, data_mode, ArtifactStore([]))

    class FailingClient:
        @staticmethod
        def capabilities(layer, refresh: bool = False):
            raise RuntimeError("GeoMet capabilities unavailable")

    monkeypatch.setattr(wms, "geomet_client", lambda: FailingClient())

    payload = client.get(f"{PREFIX}/layers").json()
    proxied = [layer for layer in payload["layers"] if layer["evidence_basis"] == "live_proxy"]
    assert proxied
    assert all(layer["times"] == [] for layer in proxied)
    assert all(layer["raster_available"] is False for layer in proxied)
    assert any("capabilities" in notice for notice in payload["notices"])


def test_frames_outside_the_experiment_window_are_dropped_and_the_full_extent_stated(monkeypatch, data_mode):
    use_live_store(monkeypatch, data_mode, ArtifactStore([]))
    stub_capabilities(monkeypatch, forward_hours(count=48))

    payload = client.get(f"{PREFIX}/layers").json()
    proxied = [layer for layer in payload["layers"] if layer["evidence_basis"] == "live_proxy"][0]

    assert len(proxied["times"]) < 48
    assert any("advertises" in notice and "window" in notice for notice in payload["notices"])


# --- the budget ----------------------------------------------------------

def test_the_original_hrdps_specs_are_unchanged_by_the_new_fields():
    """The defaults on the new fields keep the nine HRDPS specs as they were."""
    hrdps = [spec for spec in wms.FORECAST_LAYERS if spec.wms_layer.startswith("HRDPS.CONTINENTAL_")]
    assert len(hrdps) == 9
    assert all(spec.product == "HRDPS" and spec.semantics is None for spec in hrdps)
    # The thirteen forecast specs are untouched by the satellite additions:
    # no group override, legend still assumed available.
    assert len(wms.FORECAST_LAYERS) == 13
    assert all(spec.group is None and spec.legend is True for spec in wms.FORECAST_LAYERS)
    # A cold /layers pays one capabilities call per proxied spec; the budget
    # must hold all of them or the request returns no proxies at all.
    assert len(wms.PROXIED_LAYERS) == 17 <= wms.MAX_UPSTREAM_CALLS_PER_REQUEST


# --- the satellite proxies ------------------------------------------------

SATELLITE_IDS = {
    "geomet-live-goes-east-dayvis-nightir": ("GOES-East_1km_DayVis-NightIR", "satellite_day_visible_night_ir"),
    "geomet-live-goes-east-snowfog-nightmicro": ("GOES-East_1km_SnowFog-NightMicrophysics", "satellite_snow_fog_night_microphysics"),
    "geomet-live-goes-east-naturalcolor": ("GOES-East_1km_NaturalColor", "satellite_natural_color"),
    "geomet-live-goes-east-nightir-2km": ("GOES-East_2km_NightIR", "satellite_night_ir"),
}


def satellite_scans(hours_back: int = 48, lag_minutes: int = 20) -> list[datetime]:
    """What GeoMet advertises: ten-minute scans from two days ago up to ~now."""
    end = now().replace(second=0, microsecond=0) - timedelta(minutes=lag_minutes)
    count = hours_back * 6
    return [end - timedelta(minutes=10 * index) for index in range(count, -1, -1)]


def stub_satellite_capabilities(monkeypatch, scans):
    forecast = forward_hours()

    class FakeClient:
        @staticmethod
        def capabilities(layer, refresh: bool = False):
            if layer.startswith("GOES-East_1km_"):
                return FakeCapability(scans, title="GOES-East Something [1 km]", period_seconds=600)
            if layer.startswith("GOES-East_2km_"):
                return FakeCapability(scans, title="GOES-East Night IR [2 km]", period_seconds=600)
            return FakeCapability(forecast)

    monkeypatch.setattr(wms, "geomet_client", lambda: FakeClient())


def test_satellite_specs_are_declared_observed_past_only_and_never_forecast():
    specs = {spec.layer_id: spec for spec in wms.SATELLITE_LAYERS}
    assert set(specs) == set(SATELLITE_IDS)
    for layer_id, (wms_layer, field) in SATELLITE_IDS.items():
        spec = specs[layer_id]
        assert spec.wms_layer == wms_layer
        assert spec.field == field
        assert spec.product == "GOES-East"
        assert spec.group == "satellite"
        assert spec.semantics == wms.SATELLITE_SEMANTICS
        assert wms.forecast_spec(layer_id) is spec
    assert "observed" in wms.SATELLITE_SEMANTICS
    assert "never forecast" in wms.SATELLITE_SEMANTICS
    assert "not sampled by /point" in wms.SATELLITE_SEMANTICS
    assert "noaa-goes-east" in wms.SATELLITE_SEMANTICS
    assert "NOT a published artifact" in wms.SATELLITE_SEMANTICS


def test_satellite_layers_offer_only_past_frames_inside_the_window(monkeypatch, data_mode):
    """A PT10M extent over 48 h yields the frames in the window, every one at or before now."""
    use_live_store(monkeypatch, data_mode, ArtifactStore([]))
    scans = satellite_scans()
    stub_satellite_capabilities(monkeypatch, scans)

    payload = client.get(f"{PREFIX}/layers").json()
    by_id = {layer["id"]: layer for layer in payload["layers"]}
    reference = now()
    for layer_id in SATELLITE_IDS:
        layer = by_id[layer_id]
        assert layer["group"] == "satellite"
        assert layer["product"] == "GOES-East"
        assert layer["evidence_basis"] == "live_proxy"
        assert layer["z_index"] < 0
        times = [datetime.fromisoformat(stamp).astimezone(UTC) for stamp in layer["times"]]
        assert times, "the last three hours of scans have to be offered"
        assert all(stamp <= reference for stamp in times), "an observed frame can never sit in the future"
        assert len(times) < len(scans)
        assert 12 <= len(times) <= 19  # roughly three hours of ten-minute scans
        assert layer["cadence_seconds"] == 600
        assert layer["staleness_tolerance_seconds"] == 300
        assert layer["raster_available"] is True
        # ``[1 km]`` is a resolution, not a unit, so the unit is unknown.
        assert layer["units"] == "unknown"
    resolution_notices = [notice for notice in payload["notices"] if "pixel resolution" in notice]
    assert len(resolution_notices) == 4
    assert any("1 km" in notice for notice in resolution_notices)
    assert any("2 km" in notice and "geomet-live-goes-east-nightir-2km" in notice for notice in resolution_notices)
    assert all("not a unit" in notice for notice in resolution_notices)
    window_notices = [notice for notice in payload["notices"] if "goes-east" in notice and "frames fall inside this experiment's window" in notice]
    assert len(window_notices) == 4
    # The forecast proxies are untouched by the satellite stubs.
    for spec in wms.FORECAST_LAYERS:
        assert by_id[spec.layer_id]["group"] == "forecast_proxy"
        assert by_id[spec.layer_id]["units"] == "degC"


def test_a_resolution_bracket_is_never_published_as_a_unit(monkeypatch):
    spec = wms.forecast_spec("geomet-live-goes-east-dayvis-nightir")
    scans = satellite_scans()

    class FakeClient:
        @staticmethod
        def capabilities(layer, refresh: bool = False):
            return FakeCapability(scans, title="GOES-East Day Visible/Night IR [1 km]", period_seconds=600)

    monkeypatch.setattr(wms, "geomet_client", lambda: FakeClient())
    coverage = wms.forecast_coverage(spec)
    assert coverage.units == "unknown"
    assert coverage.resolution == "1 km"
    assert coverage.experimental is False
    assert coverage.notice == (
        "geomet-live-goes-east-dayvis-nightir: ECCC advertises 1 km pixel resolution for "
        "GOES-East_1km_DayVis-NightIR; that is not a unit"
    )
    # The existing [m] unit behaviour is untouched by the resolution rule.
    fog = wms.forecast_spec("geomet-live-hrdps-weong-fog-liquid")

    class FogClient:
        @staticmethod
        def capabilities(layer, refresh: bool = False):
            return FakeCapability(forward_hours(), title="HRDPS-WEonG - Visibility through liquid fog [m]")

    monkeypatch.setattr(wms, "geomet_client", lambda: FogClient())
    plain = wms.forecast_coverage(fog)
    assert (plain.units, plain.resolution, plain.notice) == ("m", None, None)


def test_legend_available_reports_the_probed_fact_on_the_spec(monkeypatch, data_mode):
    """A spec whose GetLegendGraphic probe failed says so; it is never assumed True."""
    use_live_store(monkeypatch, data_mode, ArtifactStore([]))
    stub_satellite_capabilities(monkeypatch, satellite_scans())
    from dataclasses import replace

    probed = tuple(
        replace(spec, legend=False) if spec.layer_id == "geomet-live-goes-east-nightir-2km" else spec
        for spec in wms.PROXIED_LAYERS
    )
    monkeypatch.setattr(wms, "PROXIED_LAYERS", probed)

    by_id = {layer["id"]: layer for layer in client.get(f"{PREFIX}/layers").json()["layers"]}
    assert by_id["geomet-live-goes-east-nightir-2km"]["legend_available"] is False
    assert by_id["geomet-live-goes-east-dayvis-nightir"]["legend_available"] is True
    assert all(by_id[spec.layer_id]["legend_available"] is True for spec in wms.FORECAST_LAYERS)


def test_a_satellite_frame_says_it_was_observed_not_valid(monkeypatch, data_mode):
    use_live_store(monkeypatch, data_mode, ArtifactStore([]))
    calls: list[str] = []
    stub_render(monkeypatch, calls=calls)

    response = client.get(f"{PREFIX}/layers/geomet-live-goes-east-dayvis-nightir/raster")

    assert response.status_code == 200, response.text
    assert calls == ["GOES-East_1km_DayVis-NightIR"]
    assert response.headers["x-weather-time-semantics"] == "observed at the instant in X-Weather-Valid-Time"
    assert response.headers["x-weather-valid-time"] != "none"
    assert response.headers["x-weather-evidence-basis"] == "live_proxy"
    assert response.headers["x-weather-image-basis"] == "live_proxy"
    assert response.headers["x-weather-operational"] == "false"

    # A forecast proxy keeps saying "valid".
    forecast = client.get(f"{PREFIX}/layers/geomet-live-hrdps-tt/raster")
    assert forecast.headers["x-weather-time-semantics"] == "valid at the instant in X-Weather-Valid-Time"


def test_satellite_layers_never_reach_point_or_timeline(monkeypatch, data_mode):
    use_live_store(monkeypatch, data_mode, ArtifactStore([]))
    stub_satellite_capabilities(monkeypatch, satellite_scans())

    point = client.get(f"{PREFIX}/point").json()
    assert point["data_mode"] == "unavailable"
    assert not any(item["field"].startswith("satellite_") for item in point["fields"])
    timeline = client.get(f"{PREFIX}/timeline").json()
    assert all(item["available_products"] == [] for item in timeline["items"])


def test_weong_fog_proxies_are_declared_as_diagnostics_not_sampled_by_point(monkeypatch, data_mode):
    use_live_store(monkeypatch, data_mode, ArtifactStore([]))
    stub_capabilities(monkeypatch, forward_hours())

    payload = client.get(f"{PREFIX}/layers").json()
    by_id = {layer["id"]: layer for layer in payload["layers"]}
    expected = {
        "geomet-live-hrdps-weong-fog-liquid": ("HRDPS-WEonG", "HRDPS-WEonG_2.5km_LiquidFogVisibility", "visibility_through_liquid_fog"),
        "geomet-live-hrdps-weong-fog-ice": ("HRDPS-WEonG", "HRDPS-WEonG_2.5km_IceFogVisibility", "visibility_through_ice_fog"),
        "geomet-live-rdps-weong-fog-liquid": ("RDPS-WEonG", "RDPS-WEonG_10km_LiquidFogVisibility", "visibility_through_liquid_fog"),
        "geomet-live-rdps-weong-fog-ice": ("RDPS-WEonG", "RDPS-WEonG_10km_IceFogVisibility", "visibility_through_ice_fog"),
    }
    for layer_id, (product, wms_layer, field) in expected.items():
        layer = by_id[layer_id]
        assert layer["product"] == product
        assert layer["upstream_wms_layer"] == wms_layer
        assert layer["field"] == field
        assert layer["evidence_basis"] == "live_proxy"
        assert layer["group"] == "forecast_proxy"
        assert layer["semantics"] == wms.WEONG_FOG_SEMANTICS
        assert "not sampled by /point" in layer["semantics"]
        assert "does not feed fog_state" in layer["semantics"]
        assert "eccc-hrdps-weg-prognos" in layer["semantics"]
        assert "RDPS-WEonG has no registry record" in layer["semantics"]
        # The stubbed title carries no "[experimental]" flag, so none is shown.
        assert not layer["title"].startswith("[experimental]")

    # /point knows nothing of them: no field of that name is ever served.
    point = client.get(f"{PREFIX}/point").json()
    assert point["data_mode"] == "unavailable"
    assert not any(item["field"].startswith("visibility_through_") for item in point["fields"])
    assert not any(item["field"] == "fog_state" and item["value"] is not None for item in point["fields"])


def test_an_experimental_title_yields_metres_and_a_notice(monkeypatch, data_mode):
    """ECCC's "[experimental]" flag is disclosed, and is never read as the unit."""
    use_live_store(monkeypatch, data_mode, ArtifactStore([]))
    times = forward_hours()

    class FakeClient:
        @staticmethod
        def capabilities(layer, refresh: bool = False):
            if layer.startswith("RDPS-WEonG"):
                return FakeCapability(times, title="RDPS-WEonG - Visibility through liquid fog [m] [experimental]")
            if layer.startswith("HRDPS-WEonG"):
                return FakeCapability(times, title="HRDPS-WEonG - Visibility through liquid fog [m]")
            return FakeCapability(times)

    monkeypatch.setattr(wms, "geomet_client", lambda: FakeClient())

    coverage = wms.forecast_coverage(wms.forecast_spec("geomet-live-rdps-weong-fog-liquid"))
    assert coverage.units == "m"
    assert coverage.experimental is True
    assert coverage.notice == (
        "geomet-live-rdps-weong-fog-liquid: ECCC marks RDPS-WEonG_10km_LiquidFogVisibility "
        "'[experimental]' in its capabilities title"
    )
    plain = wms.forecast_coverage(wms.forecast_spec("geomet-live-hrdps-weong-fog-liquid"))
    assert (plain.units, plain.experimental, plain.notice) == ("m", False, None)

    payload = client.get(f"{PREFIX}/layers").json()
    by_id = {layer["id"]: layer for layer in payload["layers"]}
    for layer_id in ("geomet-live-rdps-weong-fog-liquid", "geomet-live-rdps-weong-fog-ice"):
        assert by_id[layer_id]["units"] == "m"
        assert by_id[layer_id]["title"].startswith("[experimental] RDPS-WEonG ")
    for layer_id in ("geomet-live-hrdps-weong-fog-liquid", "geomet-live-hrdps-weong-fog-ice"):
        assert by_id[layer_id]["units"] == "m"
        assert not by_id[layer_id]["title"].startswith("[experimental]")
    assert sum("'[experimental]'" in notice for notice in payload["notices"]) == 2


def test_a_request_cannot_fan_out_into_unbounded_upstream_calls():
    with wms.budgeted(limit=3) as budget:
        for _ in range(3):
            budget.spend()
        with pytest.raises(wms.UpstreamBudgetExhausted):
            budget.spend()


def test_concurrent_requests_charge_their_own_budgets_not_each_other():
    """The per-request budget is request-scoped: a burst of raster fetches in
    one request must never exhaust the /layers budget of another."""
    import threading as _threading

    wms.reset_process_budget()
    counting = wms._CountingClient(object())
    results: dict[str, Exception | int] = {}

    def run(name: str, charges: int) -> None:
        try:
            with wms.budgeted(limit=5) as budget:
                for _ in range(charges):
                    counting._charge()
                results[name] = budget.spent
        except Exception as error:  # pragma: no cover - the failure being tested
            results[name] = error

    threads = [_threading.Thread(target=run, args=(f"r{i}", 5)) for i in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    # 4 x 5 = 20 charges: under the old shared binding at least one request
    # would blow its limit of 5; request-scoped budgets each see exactly 5.
    assert results == {"r0": 5, "r1": 5, "r2": 5, "r3": 5}
    wms.reset_process_budget()


def test_a_charge_outside_any_request_budget_only_pays_the_process_budget():
    wms.reset_process_budget()
    counting = wms._CountingClient(object())
    counting._charge()  # must not raise: no request budget is active here
    wms.reset_process_budget()


def test_the_process_budget_bounds_a_scrub_across_many_frames():
    wms.reset_process_budget()
    for _ in range(wms.PROCESS_BUDGET_CALLS):
        wms._spend_process_budget()
    with pytest.raises(wms.UpstreamBudgetExhausted):
        wms._spend_process_budget()
    wms.reset_process_budget()


# --- CRS fidelity and image format ---------------------------------------

class _CapturingHttp:
    """A stand-in PoliteClient that records the one URL it was asked for."""

    def __init__(self) -> None:
        self.urls: list[str] = []

    def get(self, url: str, **kwargs):
        self.urls.append(url)

        class _Response:
            content = TRANSPARENT_PNG
            headers = {"Content-Type": "image/png"}

        return _Response()


def _bare_geomet_client():
    from ingest.adapters.eccc_geomet import GeoMetClient

    http = _CapturingHttp()
    return GeoMetClient(client=http), http


BOUNDS = {"south": 46.5, "west": -55.0, "north": 48.5, "east": -51.0}


def test_epsg_4326_getmap_sends_the_bbox_latitude_first():
    from urllib.parse import parse_qs, urlparse

    client_obj, http = _bare_geomet_client()
    client_obj.map_image("HRDPS.CONTINENTAL_TT", BOUNDS, width=64, height=64, resolve=False)
    params = parse_qs(urlparse(http.urls[0]).query)
    assert params["crs"] == ["EPSG:4326"]
    assert params["bbox"] == ["46.5,-55.0,48.5,-51.0"]


def test_epsg_3857_getmap_sends_mercator_metres_in_x_y_order():
    """EPSG:3857 orders the bbox easting,northing in metres. The expected
    numbers are computed independently here from the standard spherical
    formulas, so a transposed or degree-valued bbox fails loudly."""
    import math
    from urllib.parse import parse_qs, urlparse

    client_obj, http = _bare_geomet_client()
    client_obj.map_image("HRDPS.CONTINENTAL_TT", BOUNDS, width=64, height=64, resolve=False, crs="EPSG:3857")
    params = parse_qs(urlparse(http.urls[0]).query)
    assert params["crs"] == ["EPSG:3857"]
    radius = 6378137.0

    def x(lon: float) -> float:
        return radius * math.radians(lon)

    def y(lat: float) -> float:
        return radius * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))

    sent = [float(piece) for piece in params["bbox"][0].split(",")]
    expected = [x(-55.0), y(46.5), x(-51.0), y(48.5)]
    for got, want in zip(sent, expected):
        assert abs(got - want) < 0.01, (sent, expected)
    # And the image's provenance names the CRS it was really rendered in.
    image = client_obj.map_image("HRDPS.CONTINENTAL_TT", BOUNDS, width=64, height=64, resolve=False, crs="EPSG:3857")
    assert image.as_provenance()["crs"] == "EPSG:3857"
    assert image.as_provenance()["bbox"] == {"south": 46.5, "west": -55.0, "north": 48.5, "east": -51.0}


def test_an_unsupported_getmap_crs_is_refused_client_side():
    client_obj, http = _bare_geomet_client()
    with pytest.raises(ValueError):
        client_obj.map_image("HRDPS.CONTINENTAL_TT", BOUNDS, width=64, height=64, resolve=False, crs="EPSG:26919")
    assert http.urls == []


def stub_capturing_render(monkeypatch, *, content_type_by_format: bool = True):
    """A geomet client whose map_image records its kwargs and answers with the
    content type it was asked for - which is what the real _render enforces."""
    calls: list[dict] = []

    class FakeClient:
        @staticmethod
        def map_image(layer, bounds, **kwargs):
            calls.append({"layer": layer, **kwargs})
            image = FakeImage(layer, valid_time=kwargs.get("valid_time"))
            image.content_type = kwargs.get("image_format", "image/png")
            return image

    monkeypatch.setattr(wms, "geomet_client", lambda: FakeClient())
    return calls


def test_a_satellite_raster_is_requested_and_served_as_jpeg(monkeypatch, data_mode):
    """GOES-East imagery is opaque; JPEG carries the same picture at a third
    the bytes and there is no transparency to lose. The content type on the
    response is what the upstream declared, not an assertion."""
    use_live_store(monkeypatch, data_mode, ArtifactStore([]))
    calls = stub_capturing_render(monkeypatch)

    response = client.get(f"{PREFIX}/layers/geomet-live-goes-east-dayvis-nightir/raster")

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "image/jpeg"
    assert calls[-1]["image_format"] == "image/jpeg"
    assert calls[-1]["transparent"] is False


def test_every_non_satellite_raster_stays_transparent_png(monkeypatch, data_mode):
    published = artifact(source_id="eccc-radar", logical_name="rain", provenance={"geomet_layer": "RADAR_1KM_RRAI"})
    use_live_store(monkeypatch, data_mode, ArtifactStore([published]))
    calls = stub_capturing_render(monkeypatch)

    for layer_id in ("geomet-live-hrdps-tt", "eccc-radar-rain"):
        response = client.get(f"{PREFIX}/layers/{layer_id}/raster")
        assert response.status_code == 200, response.text
        assert response.headers["content-type"] == "image/png"
        assert calls[-1]["image_format"] == "image/png"
        assert calls[-1]["transparent"] is True


def test_the_crs_query_parameter_reaches_the_upstream_request_and_the_headers(monkeypatch, data_mode):
    use_live_store(monkeypatch, data_mode, ArtifactStore([]))
    calls = stub_capturing_render(monkeypatch)

    default = client.get(f"{PREFIX}/layers/geomet-live-hrdps-tt/raster")
    assert calls[-1]["crs"] == "EPSG:4326"
    assert default.headers["x-weather-crs"] == "EPSG:4326"

    mercator = client.get(f"{PREFIX}/layers/geomet-live-hrdps-tt/raster?crs=EPSG:3857")
    assert mercator.status_code == 200, mercator.text
    assert calls[-1]["crs"] == "EPSG:3857"
    # FakeImage carries no crs of its own; the header reports the render's
    # declared CRS wherever the image object states one.


def test_an_unsupported_crs_query_parameter_is_a_422(monkeypatch, data_mode):
    use_live_store(monkeypatch, data_mode, ArtifactStore([]))
    stub_capturing_render(monkeypatch)
    response = client.get(f"{PREFIX}/layers/geomet-live-hrdps-tt/raster?crs=EPSG:26919")
    assert response.status_code == 422
    assert "EPSG:3857" in response.json()["detail"]
