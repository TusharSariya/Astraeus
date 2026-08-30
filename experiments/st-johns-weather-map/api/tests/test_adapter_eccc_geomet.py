"""Unit tests for the ECCC GeoMet adapter family.

Everything here is mocked at the HTTP transport, so no test touches the live
service; the one live test is opt-in behind ``WEATHER_LIVE_SMOKE=1``.

The payload shapes below are copied from real responses captured on
2026-08-30 and recorded in ``docs/geomet-layers.md``. Two of them carry the
traps this module exists to survive:

* radar answers ``{"value": 0, "class": "Undetected"}`` where it detected
  nothing, and that zero must never reach an artifact as a precipitation rate;
* the lightning layer answers a bare ``{}``, with no ``features`` key at all.
"""

from __future__ import annotations

import json
import math
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import numpy
import pytest
import xarray
import zarr

from ingest.adapters import eccc_geomet as geomet
from ingest.adapters.eccc_geomet import (
    AQHI_LAYER,
    ALERTS_LAYER,
    LIGHTNING_LAYER,
    PROFILE_LEVELS_HPA,
    RADAR_RAIN_LAYER,
    RADAR_SNOW_LAYER,
    ECCCAqhiGeoMetAdapter,
    ECCCCapAlertsGeoMetAdapter,
    ECCCHrdpsGeoMetAdapter,
    ECCCLightningGeoMetAdapter,
    ECCCRadarGeoMetAdapter,
    GeoMetClient,
    GeoMetNotAnImage,
    GeoMetServiceException,
    TimeOutsideExtent,
    avalon_probe_boxes,
    humidity_profile,
    is_experimental,
    parse_capabilities,
    parse_time_extent,
    parse_title_resolution,
    parse_title_units,
    wind_components,
)
from ingest.contract import AdapterUnavailable, FetchWindow
from ingest.http import USER_AGENT, PoliteClient

UTC = timezone.utc

NOW = datetime(2026, 8, 30, 3, 0, tzinfo=UTC)
WINDOW = FetchWindow(now=NOW)

# Three radar scans ending at the window's present moment: enough to exercise
# the series logic without inflating the mocked request count.
RADAR_EXTENT = "2026-08-30T02:54:00Z/2026-08-30T03:06:00Z/PT6M"
RADAR_TIMES = ("2026-08-30T02:54:00Z", "2026-08-30T03:00:00Z", "2026-08-30T03:06:00Z")
LIGHTNING_EXTENT = "2026-08-30T02:40:00Z/2026-08-30T03:00:00Z/PT10M"
LIGHTNING_TIMES = ("2026-08-30T02:40:00Z", "2026-08-30T02:50:00Z", "2026-08-30T03:00:00Z")
MODEL_EXTENT = "2026-08-30T02:00:00Z/2026-08-30T04:00:00Z/PT1H"
MODEL_TIMES = ("2026-08-30T02:00:00Z", "2026-08-30T03:00:00Z", "2026-08-30T04:00:00Z")
MODEL_REFERENCE = "2026-08-29T18:00:00Z/2026-08-29T18:00:00Z/PT6H"
UPDATE_SEQUENCE = "2026-08-30T03:16:01Z"


# --------------------------------------------------------------------------
# Fixtures: capabilities documents and GetFeatureInfo payloads
# --------------------------------------------------------------------------


def capabilities_xml(name: str, title: str, *, time: str | None = None, reference_time: str | None = None) -> str:
    """A single-layer capabilities document shaped like the live one.

    The layer is nested two groups deep and every group carries its own
    ``<Name>``/``<Title>``, and the leaf carries ``<Style><Name>`` — exactly the
    structure that makes a naive parser attribute a style's name to its layer.
    """
    dimensions = ""
    if time is not None:
        dimensions += f'<Dimension name="time" units="ISO8601" default="{time.split("/")[1]}">{time}</Dimension>'
    if reference_time is not None:
        default = reference_time.split("/")[1]
        dimensions += (
            f'<Dimension name="reference_time" units="ISO8601" default="{default}">{reference_time}</Dimension>'
        )
    return f"""<?xml version='1.0' encoding="UTF-8"?>
<WMS_Capabilities version="1.3.0" updateSequence="{UPDATE_SEQUENCE}" xmlns="http://www.opengis.net/wms">
  <Service><Name>WMS</Name><Title>MSC GeoMet</Title></Service>
  <Capability>
    <Layer>
      <Title>MSC GeoMet — GeoMet-Weather 2.40.3</Title>
      <EX_GeographicBoundingBox>
        <westBoundLongitude>-180</westBoundLongitude>
        <eastBoundLongitude>180</eastBoundLongitude>
        <southBoundLatitude>-90</southBoundLatitude>
        <northBoundLatitude>90</northBoundLatitude>
      </EX_GeographicBoundingBox>
      <Layer>
        <Name>GroupLayer</Name>
        <Title>Group</Title>
        <Layer queryable="1">
          <Name>{name}</Name>
          <Title>{title}</Title>
          <Abstract>captured 2026-08-30</Abstract>
          <EX_GeographicBoundingBox>
            <westBoundLongitude>-152.0</westBoundLongitude>
            <eastBoundLongitude>-40.0</eastBoundLongitude>
            <southBoundLatitude>27.0</southBoundLatitude>
            <northBoundLatitude>70.0</northBoundLatitude>
          </EX_GeographicBoundingBox>
          {dimensions}
          <Style>
            <Name>DEFAULT_STYLE_NAME</Name>
            <Title>Default</Title>
          </Style>
        </Layer>
      </Layer>
    </Layer>
  </Capability>
</WMS_Capabilities>"""


def feature(layer: str, value, *, title: str, time: str, reference_time: str = "N/A", klass=None) -> dict:
    return {
        "type": "FeatureCollection",
        "layer": layer,
        "features": [
            {
                "type": "Feature",
                "id": f"{layer}(-52.6859,47.5391)",
                "geometry": {"type": "Point", "coordinates": [-52.6859, 47.5391]},
                "properties": {
                    "value": value,
                    "class": klass,
                    "title_en": title,
                    "time": time,
                    "dim_reference_time": reference_time,
                },
            }
        ],
    }


EMPTY_COLLECTION = {"type": "FeatureCollection", "features": []}

# Stand-in bytes: the client guards and attributes an image, it never decodes
# pixels, so a real PNG would only make the fixtures harder to read. The magic
# number is kept so a test can still tell an image apart from an XML fault.
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
RENDERED_TILE = PNG_MAGIC + b"mocked 512x512 radar tile"
RENDERED_LEGEND = PNG_MAGIC + b"mocked RADARURPPRECIPR colour ramp"

# The Avalon tile the live GetMap was verified against on 2026-08-30.
TILE_BOUNDS = {"south": 46.8, "west": -53.6, "north": 48.2, "east": -52.0}

RADAR_TITLES = {
    RADAR_RAIN_LAYER: "Radar precipitation rate for rain [mm/h]",
    RADAR_SNOW_LAYER: "Radar precipitation rate for snow [cm/h]",
}
LIGHTNING_TITLE = "Lightning Flash Density over Canada (2.5 km) [flash/km²/min]"

MODEL_LAYER_TITLES = {
    "HRDPS.CONTINENTAL_TT": ("HRDPS.CONTINENTAL - Air temperature at 2m above ground [°C]", 18.165003),
    "HRDPS.CONTINENTAL_TD": ("HRDPS.CONTINENTAL - Dew point temperature at 2m above ground [°C]", 14.2),
    "HRDPS.CONTINENTAL_HR": ("HRDPS.CONTINENTAL - Relative humidity at 2m above ground [%]", 78.0),
    "HRDPS.CONTINENTAL_PN-SLP": ("HRDPS.CONTINENTAL - Sea level pressure [Pa]", 101_300.0),
    "HRDPS.CONTINENTAL_NT": ("HRDPS.CONTINENTAL - Total cloud cover [%]", 55.0),
    "HRDPS.CONTINENTAL_WSPD": ("HRDPS.CONTINENTAL - Wind speed at 10m above surface [m/s]", 10.0),
    "HRDPS.CONTINENTAL_WD": ("HRDPS.CONTINENTAL - Wind direction at 10m above surface [°]", 0.0),
    "HRDPS.CONTINENTAL.DIAG_PR_PT1H": ("HRDPS.DIAG - Precipitation - 1-hour accumulation [mm]", 0.4),
}


class Service:
    """A mocked GeoMet, driven by declared capabilities and payloads."""

    def __init__(self) -> None:
        self.capabilities: dict[str, str] = {}
        self.payloads: dict[str, object] = {}
        self.requests: list[httpx.URL] = []
        self.exceptions: set[str] = set()
        self.renders: dict[str, bytes] = {}
        # What each layer would answer a GetMap for, so the mock can reproduce
        # the live NoMatch rather than being told when to fail.
        self.advertised_times: dict[str, set[str]] = {}

    def advertise(self, name: str, title: str, *, time: str | None = None, reference_time: str | None = None) -> None:
        self.capabilities[name] = capabilities_xml(name, title, time=time, reference_time=reference_time)
        extent = parse_time_extent(time) if time else None
        self.advertised_times[name] = {
            step.strftime("%Y-%m-%dT%H:%M:%SZ") for step in (extent.steps() if extent is not None else ())
        }

    def render(self, layer: str, payload: bytes) -> None:
        self.renders[layer] = payload

    def answer(self, layer: str, payload, *, at: str | None = None) -> None:
        self.payloads[f"{layer}@{at}" if at else layer] = payload

    def _feature_payload(self, layer: str, stamp: str | None):
        if f"{layer}@{stamp}" in self.payloads:
            return self.payloads[f"{layer}@{stamp}"]
        return self.payloads.get(layer, EMPTY_COLLECTION)

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request.url)
        params = request.url.params
        operation = params.get("request")
        if operation == "GetCapabilities":
            layer = params.get("LAYERS")
            if layer not in self.capabilities:
                return httpx.Response(200, text=SERVICE_EXCEPTION.format(code="InvalidLayersParameter"))
            return httpx.Response(200, text=self.capabilities[layer])
        if operation == "GetFeatureInfo":
            layer = params.get("layers")
            if layer in self.exceptions:
                return httpx.Response(200, text=SERVICE_EXCEPTION.format(code="NoMatch"))
            payload = self._feature_payload(layer, params.get("TIME"))
            return httpx.Response(200, text=json.dumps(payload))
        if operation in {"GetMap", "GetLegendGraphic"}:
            # As the live service does: GetMap takes ``LAYERS``, GetLegendGraphic
            # the singular ``LAYER``, and a legend asked for under ``LAYERS``
            # is answered with ``LayerNotDefined`` for the vector layers.
            layer = params.get("layers") if operation == "GetMap" else params.get("LAYER")
            stamp = params.get("TIME")
            unadvertised = stamp is not None and stamp not in self.advertised_times.get(layer, set())
            if layer in self.exceptions or unadvertised:
                # The live behaviour this exists to reproduce: HTTP **200** with
                # a text/xml fault body, not an error status.
                return httpx.Response(
                    200,
                    text=SERVICE_EXCEPTION.format(code="NoMatch"),
                    headers={"Content-Type": "text/xml"},
                )
            return httpx.Response(
                200,
                content=self.renders.get(layer, RENDERED_TILE),
                headers={"Content-Type": params.get("format", "image/png")},
            )
        return httpx.Response(400)

    def client(self) -> GeoMetClient:
        polite = PoliteClient(min_host_interval_seconds=0.0)
        polite._client = httpx.Client(
            transport=httpx.MockTransport(self.handler), headers={"User-Agent": USER_AGENT}
        )
        return GeoMetClient(client=polite, cache_ttl_seconds=3600.0)


SERVICE_EXCEPTION = (
    "<?xml version='1.0'?><ogc:ServiceExceptionReport version=\"1.3.0\" "
    'xmlns:ogc="http://www.opengis.net/ogc">'
    '<ogc:ServiceException code="{code}">Layer not available</ogc:ServiceException>'
    "</ogc:ServiceExceptionReport>"
)


def open_artifact(path: Path) -> xarray.Dataset:
    return xarray.open_zarr(zarr.storage.ZipStore(str(path), mode="r"), consolidated=False)


# --------------------------------------------------------------------------
# Capabilities parsing
# --------------------------------------------------------------------------


def test_capabilities_parsing_reads_both_extents_and_ignores_style_names(tmp_path: Path):
    path = tmp_path / "caps.xml"
    path.write_text(
        capabilities_xml(
            "HRDPS.CONTINENTAL_TT",
            "HRDPS.CONTINENTAL - Air temperature at 2m above ground [°C]",
            time=MODEL_EXTENT,
            reference_time="2026-08-28T18:00:00Z/2026-08-29T18:00:00Z/PT6H",
        ),
        "utf-8",
    )
    layers, update_sequence = parse_capabilities(path)

    assert update_sequence == UPDATE_SEQUENCE
    # The style's <Name> must not have become a layer.
    assert "DEFAULT_STYLE_NAME" not in layers
    assert set(layers) == {"GroupLayer", "HRDPS.CONTINENTAL_TT"}

    layer = layers["HRDPS.CONTINENTAL_TT"]
    assert layer.title == "HRDPS.CONTINENTAL - Air temperature at 2m above ground [°C]"
    assert layer.units == ("°C", "degC", True)
    assert layer.time.start == datetime(2026, 8, 30, 2, tzinfo=UTC)
    assert layer.time.end == datetime(2026, 8, 30, 4, tzinfo=UTC)
    assert layer.time.period == timedelta(hours=1)
    assert layer.reference_time.start == datetime(2026, 8, 28, 18, tzinfo=UTC)
    assert layer.reference_time.default == datetime(2026, 8, 29, 18, tzinfo=UTC)
    assert layer.reference_time.period == timedelta(hours=6)
    assert layer.bounds == {"west": -152.0, "east": -40.0, "south": 27.0, "north": 70.0}


def test_a_layer_without_a_time_dimension_reports_none(tmp_path: Path):
    """``Current-Alerts`` and ``AQHI-OBS`` genuinely have no time dimension."""
    path = tmp_path / "caps.xml"
    path.write_text(capabilities_xml(ALERTS_LAYER, "Current Weather Alerts [experimental]"), "utf-8")
    layers, _ = parse_capabilities(path)
    assert layers[ALERTS_LAYER].time is None
    assert layers[ALERTS_LAYER].reference_time is None


def test_an_unknown_layer_is_an_explicit_failure_not_a_silent_gap():
    service = Service()
    with pytest.raises(AdapterUnavailable, match="InvalidLayersParameter|does not advertise"):
        service.client().capabilities("NOT_A_REAL_LAYER")


def test_capabilities_are_cached_so_one_cycle_asks_once():
    service = Service()
    service.advertise(RADAR_RAIN_LAYER, RADAR_TITLES[RADAR_RAIN_LAYER], time=RADAR_EXTENT)
    client = service.client()
    client.capabilities(RADAR_RAIN_LAYER)
    client.capabilities(RADAR_RAIN_LAYER)
    assert sum(1 for url in service.requests if url.params.get("request") == "GetCapabilities") == 1


# --------------------------------------------------------------------------
# Units
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("title", "raw", "canonical"),
    [
        ("HRDPS.CONTINENTAL - Air temperature at 2m above ground [°C]", "°C", "degC"),
        ("HRDPS.CONTINENTAL - Relative humidity at 2m above ground [%]", "%", "percent"),
        ("HRDPS.DIAG - Precipitation - 1-hour accumulation [mm]", "mm", "mm"),
        ("HRDPS.CONTINENTAL - Wind speed at 10m above surface [m/s]", "m/s", "m s-1"),
        ("Radar precipitation rate for rain [mm/h]", "mm/h", "mm h-1"),
        ("RDPS - Wind direction at 10m above surface [deg true]", "deg true", "degree"),
        (LIGHTNING_TITLE, "flash/km²/min", "flash km-2 min-1"),
    ],
)
def test_recognised_units_are_normalized_in_spelling_only(title, raw, canonical):
    assert parse_title_units(title) == (raw, canonical, True)


def test_an_unrecognised_unit_is_carried_through_unconverted_and_marked():
    raw, canonical, recognised = parse_title_units("Some layer - Something [furlongs/fortnight]")
    assert raw == "furlongs/fortnight"
    # Carried through verbatim: guessing a conversion is the one thing forbidden.
    assert canonical == "furlongs/fortnight"
    assert recognised is False


def test_a_title_with_no_bracketed_unit_yields_no_unit():
    assert parse_title_units("AQHI - Observations") == (None, None, False)


def test_the_experimental_flag_is_not_read_as_a_unit():
    """ECCC's trailing "[experimental]" sits where the unit does; it is not one."""
    assert parse_title_units("RDPS-WEonG - Visibility through liquid fog [m] [experimental]") == ("m", "m", True)
    assert parse_title_units("Current Weather Alerts [experimental]") == (None, None, False)
    assert parse_title_units("HRDPS-WEonG - Visibility through liquid fog [m]") == ("m", "m", True)


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("RDPS-WEonG - Visibility through liquid fog [m] [experimental]", True),
        ("Current Weather Alerts [experimental]", True),
        ("Something [EXPERIMENTAL]", True),
        ("HRDPS-WEonG - Visibility through liquid fog [m]", False),
        ("AQHI - Observations", False),
        ("", False),
        (None, False),
    ],
)
def test_is_experimental_reads_only_the_trailing_flag(title, expected):
    assert is_experimental(title) is expected


@pytest.mark.parametrize(
    ("title", "resolution"),
    [
        ("GOES-East Day Visible/Night IR [1 km]", "1 km"),
        ("GOES-East Snow-Fog/Night Microphysics [1 km]", "1 km"),
        ("GOES-East Natural Color [1 km]", "1 km"),
        ("GOES-East Night IR [2 km]", "2 km"),
        ("Something [0.5 km]", "0.5 km"),
        ("Something [250 m]", "250 m"),
        ("Something [2km]", "2km"),
        ("Something [1 km] [experimental]", "1 km"),
    ],
)
def test_a_resolution_bracket_is_read_as_a_resolution_and_not_as_a_unit(title, resolution):
    """The GOES-East titles end in ``[1 km]``: a pixel size, not what the picture measures."""
    assert parse_title_resolution(title) == resolution
    assert parse_title_units(title) == (None, None, False)


@pytest.mark.parametrize(
    "title",
    [
        "HRDPS-WEonG - Visibility through liquid fog [m]",
        "RDPS-WEonG - Visibility through liquid fog [m] [experimental]",
        "HRDPS.DIAG - Precipitation - 1-hour accumulation [mm]",
        "Radar precipitation rate for rain [mm/h]",
        "AQHI - Observations",
        "Current Weather Alerts [experimental]",
        "",
        None,
    ],
)
def test_a_bare_unit_bracket_is_not_a_resolution(title):
    """``[m]`` has no number: it stays the unit it always was, and no resolution is invented."""
    assert parse_title_resolution(title) is None
    if title and "[m]" in title:
        assert parse_title_units(title) == ("m", "m", True)


def test_a_unit_bracket_followed_by_a_resolution_bracket_keeps_the_unit():
    assert parse_title_units("Something [mm] [1 km]") == ("mm", "mm", True)
    assert parse_title_resolution("Something [mm] [1 km]") == "1 km"


# --------------------------------------------------------------------------
# Time extents
# --------------------------------------------------------------------------


def test_a_time_outside_the_advertised_extent_is_refused_not_snapped():
    extent = parse_time_extent(RADAR_EXTENT)
    assert extent.steps() == tuple(datetime.fromisoformat(stamp.replace("Z", "+00:00")) for stamp in RADAR_TIMES)
    assert extent.nearest(datetime(2026, 8, 30, 3, 1, tzinfo=UTC)) == datetime(2026, 8, 30, 3, 0, tzinfo=UTC)
    with pytest.raises(TimeOutsideExtent):
        extent.nearest(datetime(2020, 1, 1, tzinfo=UTC))


def test_the_client_refuses_an_out_of_extent_time_before_asking_the_service():
    service = Service()
    service.advertise(RADAR_RAIN_LAYER, RADAR_TITLES[RADAR_RAIN_LAYER], time=RADAR_EXTENT)
    client = service.client()
    with pytest.raises(TimeOutsideExtent):
        client.resolve_time(RADAR_RAIN_LAYER, datetime(2020, 1, 1, tzinfo=UTC))
    assert not [url for url in service.requests if url.params.get("request") == "GetFeatureInfo"]


def test_a_layer_with_no_time_dimension_resolves_to_no_time_parameter():
    service = Service()
    service.advertise(AQHI_LAYER, "AQHI - Observations")
    assert service.client().resolve_time(AQHI_LAYER, NOW) is None


def test_an_explicit_value_list_extent_is_parsed():
    extent = parse_time_extent("2026-08-30T00:00:00Z,2026-08-30T01:00:00Z", default="2026-08-30T01:00:00Z")
    assert extent.values == (datetime(2026, 8, 30, tzinfo=UTC), datetime(2026, 8, 30, 1, tzinfo=UTC))
    assert extent.default == datetime(2026, 8, 30, 1, tzinfo=UTC)


# --------------------------------------------------------------------------
# Absence
# --------------------------------------------------------------------------


def test_an_empty_features_array_is_absence_not_a_number():
    service = Service()
    service.advertise(RADAR_RAIN_LAYER, RADAR_TITLES[RADAR_RAIN_LAYER], time=RADAR_EXTENT)
    service.answer(RADAR_RAIN_LAYER, EMPTY_COLLECTION)
    assert service.client().feature_info(RADAR_RAIN_LAYER, 47.5615, -52.7126, valid_time=NOW) is None


def test_a_bare_empty_object_is_absence_not_a_number():
    """The lightning layer answers ``{}`` with no ``features`` key at all."""
    service = Service()
    service.advertise(LIGHTNING_LAYER, LIGHTNING_TITLE, time=LIGHTNING_EXTENT)
    service.answer(LIGHTNING_LAYER, {})
    assert service.client().feature_info(LIGHTNING_LAYER, 47.5615, -52.7126, valid_time=NOW) is None


def test_a_non_numeric_value_is_absence_not_a_number():
    service = Service()
    service.advertise(RADAR_RAIN_LAYER, RADAR_TITLES[RADAR_RAIN_LAYER], time=RADAR_EXTENT)
    service.answer(
        RADAR_RAIN_LAYER,
        feature(RADAR_RAIN_LAYER, None, title=RADAR_TITLES[RADAR_RAIN_LAYER], time=RADAR_TIMES[-1]),
    )
    assert service.client().feature_info(RADAR_RAIN_LAYER, 47.5615, -52.7126, valid_time=NOW) is None


# --------------------------------------------------------------------------
# Rendered images: GetMap and GetLegendGraphic
# --------------------------------------------------------------------------


def render_service(*, reference_time: str | None = None) -> Service:
    service = Service()
    service.advertise(
        RADAR_RAIN_LAYER, RADAR_TITLES[RADAR_RAIN_LAYER], time=RADAR_EXTENT, reference_time=reference_time
    )
    service.render(RADAR_RAIN_LAYER, RENDERED_TILE)
    return service


def test_a_rendered_tile_carries_the_provenance_of_its_own_request():
    service = render_service()
    image = service.client().map_image(RADAR_RAIN_LAYER, TILE_BOUNDS, width=512, height=512, valid_time=NOW)

    assert image.payload == RENDERED_TILE
    assert image.content_type == "image/png"
    assert (image.width, image.height) == (512, 512)
    # The frame is the advertised scan the request was snapped onto, not the
    # wall clock the caller happened to ask with.
    assert image.valid_time == datetime(2026, 8, 30, 3, 0, tzinfo=UTC)
    # Radar is a mosaic: it advertises no reference_time, and that absence is
    # published as absence rather than being filled in from the valid time.
    assert image.reference_time is None

    provenance = image.as_provenance()
    assert provenance["layer"] == RADAR_RAIN_LAYER
    assert provenance["bbox"] == TILE_BOUNDS
    assert provenance["crs"] == "EPSG:4326"
    assert provenance["byte_size"] == len(RENDERED_TILE)
    assert provenance["valid_time"] == "2026-08-30T03:00:00+00:00"
    assert provenance["url"] == image.url
    assert "request=GetMap" in image.url and "TIME=2026-08-30T03%3A00%3A00Z" in image.url


def test_a_layer_that_advertises_a_run_has_that_run_pinned_and_recorded():
    """``DIM_REFERENCE_TIME`` is sent, so the tile states which run drew it."""
    service = render_service(reference_time=MODEL_REFERENCE)
    image = service.client().map_image(RADAR_RAIN_LAYER, TILE_BOUNDS, width=64, height=64, valid_time=NOW)

    assert image.reference_time == datetime(2026, 8, 29, 18, tzinfo=UTC)
    assert "DIM_REFERENCE_TIME=2026-08-29T18%3A00%3A00Z" in image.url


def test_the_getmap_bbox_is_latitude_first_as_wms_1_3_0_requires():
    """The classic WMS bug: EPSG:4326 in 1.3.0 orders the bbox lat,lon.

    Transposing it is answered live with HTTP 200 and a near-empty PNG rather
    than an exception, so nothing downstream would ever notice.
    """
    service = render_service()
    service.client().map_image(RADAR_RAIN_LAYER, TILE_BOUNDS, width=512, height=512, valid_time=NOW)

    maps = [url for url in service.requests if url.params.get("request") == "GetMap"]
    assert len(maps) == 1
    assert maps[0].params["bbox"] == "46.8,-53.6,48.2,-52.0"
    south, west, north, east = (float(piece) for piece in maps[0].params["bbox"].split(","))
    assert (south, north) == (TILE_BOUNDS["south"], TILE_BOUNDS["north"])
    assert (west, east) == (TILE_BOUNDS["west"], TILE_BOUNDS["east"])


def test_a_frame_the_layer_does_not_advertise_is_refused_before_any_getmap():
    """The refusal is :meth:`TimeExtent.nearest`, client-side, not a caught fault."""
    service = render_service()
    with pytest.raises(TimeOutsideExtent):
        service.client().map_image(
            RADAR_RAIN_LAYER, TILE_BOUNDS, width=64, height=64, valid_time=datetime(2020, 1, 1, tzinfo=UTC)
        )
    assert not [url for url in service.requests if url.params.get("request") == "GetMap"]


def test_an_xml_fault_served_as_http_200_is_raised_not_returned_as_pixels():
    """The trap: an unadvertised TIME answers **200** with ``text/xml``.

    A client that checks only the status code publishes a
    ``ServiceExceptionReport`` as a tile. Verified live on 2026-08-30: 477
    bytes, ``Content-Type: text/xml``, ``code="NoMatch" locator="time"``.
    """
    service = render_service()
    client = service.client()
    with pytest.raises(GeoMetServiceException, match="NoMatch"):
        # ``resolve=False`` is the only way past the client-side refusal, which
        # is exactly the situation a caller with its own frame is in.
        client.map_image(
            RADAR_RAIN_LAYER,
            TILE_BOUNDS,
            width=64,
            height=64,
            valid_time=datetime(2020, 1, 1, tzinfo=UTC),
            resolve=False,
        )
    # Nothing was cached, so a retry re-asks rather than serving the fault.
    assert not client._images


def test_a_body_that_is_not_the_requested_image_is_raised_not_returned():
    service = render_service()

    def handler(request: httpx.Request) -> httpx.Response:
        service.requests.append(request.url)
        if request.url.params.get("request") == "GetCapabilities":
            return httpx.Response(200, text=service.capabilities[request.url.params.get("LAYERS")])
        return httpx.Response(200, content=b"<html>maintenance</html>", headers={"Content-Type": "text/html"})

    polite = PoliteClient(min_host_interval_seconds=0.0)
    polite._client = httpx.Client(transport=httpx.MockTransport(handler), headers={"User-Agent": USER_AGENT})
    client = GeoMetClient(client=polite, cache_ttl_seconds=3600.0)

    with pytest.raises(GeoMetNotAnImage, match="text/html"):
        client.map_image(RADAR_RAIN_LAYER, TILE_BOUNDS, width=64, height=64, valid_time=NOW)


def test_the_legend_is_the_services_own_colour_ramp_never_one_we_invented():
    service = render_service()
    service.render(RADAR_RAIN_LAYER, RENDERED_LEGEND)
    image = service.client().legend_graphic(RADAR_RAIN_LAYER, style="RADARURPPRECIPR")

    assert image.payload == RENDERED_LEGEND
    assert image.content_type == "image/png"
    assert image.style == "RADARURPPRECIPR"
    # A legend describes the layer's scale, not one frame of it.
    assert image.valid_time is None and image.bbox is None
    assert image.width is None and image.height is None

    legends = [url for url in service.requests if url.params.get("request") == "GetLegendGraphic"]
    assert len(legends) == 1
    assert legends[0].params["STYLE"] == "RADARURPPRECIPR"
    assert "TIME" not in legends[0].params
    # WMS 1.3.0 GetLegendGraphic takes the singular ``LAYER``. GeoMet tolerates
    # ``LAYERS`` for its raster layers but answers ``LayerNotDefined`` for the
    # vector ones (``AQHI-OBS``, ``Current-Alerts``; verified live 2026-08-30).
    assert legends[0].params["LAYER"] == RADAR_RAIN_LAYER
    assert "LAYERS" not in legends[0].params and "layers" not in legends[0].params
    assert legends[0].params["SLD_VERSION"] == "1.1.0"
    # The capabilities fetch a GetMap needs is not needed for a legend.
    assert not [url for url in service.requests if url.params.get("request") == "GetCapabilities"]


def test_a_render_is_cached_for_the_ttl_like_capabilities():
    """Same TTL cache as capabilities: one worker cycle renders a tile once."""
    service = render_service()
    client = service.client()
    first = client.map_image(RADAR_RAIN_LAYER, TILE_BOUNDS, width=64, height=64, valid_time=NOW)
    second = client.map_image(RADAR_RAIN_LAYER, TILE_BOUNDS, width=64, height=64, valid_time=NOW)

    assert first is second
    assert len([url for url in service.requests if url.params.get("request") == "GetMap"]) == 1
    # A different pixel size is a different request, never a resized cache hit.
    client.map_image(RADAR_RAIN_LAYER, TILE_BOUNDS, width=128, height=128, valid_time=NOW)
    assert len([url for url in service.requests if url.params.get("request") == "GetMap"]) == 2


def test_a_render_the_caller_sized_wrong_is_refused_before_the_request():
    service = render_service()
    client = service.client()
    with pytest.raises(ValueError, match="pixel ceiling"):
        client.map_image(RADAR_RAIN_LAYER, TILE_BOUNDS, width=8192, height=8192, valid_time=NOW)
    with pytest.raises(ValueError, match="south-west to north-east"):
        client.map_image(
            RADAR_RAIN_LAYER,
            {"south": 48.2, "west": -53.6, "north": 46.8, "east": -52.0},
            valid_time=NOW,
        )
    assert not [url for url in service.requests if url.params.get("request") == "GetMap"]


# --------------------------------------------------------------------------
# Radar
# --------------------------------------------------------------------------


def radar_service(*, rain=None, snow=None) -> Service:
    service = Service()
    service.advertise(RADAR_RAIN_LAYER, RADAR_TITLES[RADAR_RAIN_LAYER], time=RADAR_EXTENT)
    service.advertise(RADAR_SNOW_LAYER, RADAR_TITLES[RADAR_SNOW_LAYER], time=RADAR_EXTENT)
    undetected_rain = feature(
        RADAR_RAIN_LAYER, 0, title=RADAR_TITLES[RADAR_RAIN_LAYER], time=RADAR_TIMES[-1], klass="Undetected"
    )
    undetected_snow = feature(
        RADAR_SNOW_LAYER, 0, title=RADAR_TITLES[RADAR_SNOW_LAYER], time=RADAR_TIMES[-1], klass="Undetected"
    )
    for stamp in RADAR_TIMES:
        rain_payload = rain(stamp) if callable(rain) else (rain or undetected_rain)
        snow_payload = snow(stamp) if callable(snow) else (snow or undetected_snow)
        service.answer(RADAR_RAIN_LAYER, _restamp(rain_payload, stamp), at=stamp)
        service.answer(RADAR_SNOW_LAYER, _restamp(snow_payload, stamp), at=stamp)
    return service


def _restamp(payload, stamp: str):
    if not payload.get("features"):
        return payload
    clone = json.loads(json.dumps(payload))
    for item in clone["features"]:
        item["properties"]["time"] = stamp
    return clone


def run_radar(service: Service, workdir: Path):
    adapter = ECCCRadarGeoMetAdapter(service.client())
    candidates = adapter.discover(WINDOW)
    return adapter, adapter.fetch(candidates[0], WINDOW, workdir)


def test_undetected_radar_is_no_echo_and_never_zero_precipitation(tmp_path: Path):
    """The mosaic's own ``"value": 0, "class": "Undetected"`` must not become 0 mm/h."""
    adapter, result = run_radar(radar_service(), tmp_path)

    assert result.complete is True
    assert result.qc_passed is True

    dataset = open_artifact(result.artifacts[0].payload_path)
    # The echo flag is a real observation: the mosaic looked and saw nothing.
    assert list(dataset["radar_echo"].values.ravel()) == [0.0, 0.0, 0.0]
    # The rate is absent, not zero. This is the whole point of the adapter.
    assert bool(numpy.all(numpy.isnan(dataset["precipitation_rate"].values)))
    assert bool(numpy.all(numpy.isnan(dataset["snow_rate"].values)))
    assert 0.0 not in list(dataset["precipitation_rate"].values.ravel())

    provenance = result.artifacts[0].provenance
    assert provenance["undetected_scans"] == len(RADAR_TIMES)
    assert set(provenance["echo_semantics"].values()) == {"no_detected_precipitating_echo"}
    assert "no detected precipitating echo" in dataset["precipitation_rate"].attrs["semantics"]
    assert dataset["radar_echo"].attrs["flag_meanings"].startswith("no_detected_precipitating_echo")


def test_a_detected_echo_publishes_the_rate_it_measured(tmp_path: Path):
    rain = feature(RADAR_RAIN_LAYER, 2.5, title=RADAR_TITLES[RADAR_RAIN_LAYER], time=RADAR_TIMES[-1], klass="1 2.5")
    _adapter, result = run_radar(radar_service(rain=rain), tmp_path)

    dataset = open_artifact(result.artifacts[0].payload_path)
    assert list(dataset["radar_echo"].values.ravel()) == [1.0, 1.0, 1.0]
    assert list(dataset["precipitation_rate"].values.ravel()) == [2.5, 2.5, 2.5]
    assert dataset["precipitation_rate"].attrs["units"] == "mm h-1"
    assert set(result.artifacts[0].provenance["echo_semantics"].values()) == {"precipitating_echo_detected"}
    assert result.complete is True


def test_a_scan_the_service_refuses_leaves_the_echo_flag_unknown_and_fails_the_run(tmp_path: Path):
    service = radar_service()
    service.exceptions.add(RADAR_RAIN_LAYER)
    _adapter, result = run_radar(service, tmp_path)

    dataset = open_artifact(result.artifacts[0].payload_path)
    assert bool(numpy.all(numpy.isnan(dataset["radar_echo"].values)))
    # No echo flag anywhere means the mandatory field is empty: fail closed.
    # A retrieval failure is an incompleteness, not a contract violation, so it
    # lowers ``complete`` and leaves the run "suspect" rather than "failed".
    assert result.complete is False
    assert result.artifacts[0].provenance["quality"]["status"] == "suspect"


# --------------------------------------------------------------------------
# Lightning
# --------------------------------------------------------------------------


def lightning_service(payload=None) -> Service:
    service = Service()
    service.advertise(LIGHTNING_LAYER, LIGHTNING_TITLE, time=LIGHTNING_EXTENT)
    for stamp in LIGHTNING_TIMES:
        service.answer(LIGHTNING_LAYER, _restamp(payload or {}, stamp), at=stamp)
    return service


def test_no_flash_density_publishes_absence_beside_an_observed_flag(tmp_path: Path):
    adapter = ECCCLightningGeoMetAdapter(lightning_service().client())
    result = adapter.fetch(adapter.discover(WINDOW)[0], WINDOW, tmp_path)

    dataset = open_artifact(result.artifacts[0].payload_path)
    assert list(dataset["lightning_observed"].values.ravel()) == [0.0, 0.0, 0.0]
    assert bool(numpy.all(numpy.isnan(dataset["lightning_strike"].values)))
    assert result.complete is True


def test_a_reported_flash_density_is_published_with_its_own_unit(tmp_path: Path):
    payload = feature(LIGHTNING_LAYER, 0.42, title=LIGHTNING_TITLE, time=LIGHTNING_TIMES[-1])
    adapter = ECCCLightningGeoMetAdapter(lightning_service(payload).client())
    result = adapter.fetch(adapter.discover(WINDOW)[0], WINDOW, tmp_path)

    dataset = open_artifact(result.artifacts[0].payload_path)
    assert list(dataset["lightning_strike"].values.ravel()) == [0.42, 0.42, 0.42]
    assert dataset["lightning_strike"].attrs["units"] == "flash km-2 min-1"
    assert dataset["lightning_strike"].attrs["original_units"] == "flash/km²/min"
    assert result.complete is True


# --------------------------------------------------------------------------
# CAP alerts
# --------------------------------------------------------------------------


def alerts_service(payload=None) -> Service:
    service = Service()
    service.advertise(ALERTS_LAYER, "Current Weather Alerts [experimental]")
    service.answer(ALERTS_LAYER, payload or EMPTY_COLLECTION)
    return service


def test_no_alert_in_force_is_a_publishable_answer(tmp_path: Path):
    adapter = ECCCCapAlertsGeoMetAdapter(alerts_service().client())
    result = adapter.fetch(adapter.discover(WINDOW)[0], WINDOW, tmp_path)

    dataset = open_artifact(result.artifacts[0].payload_path)
    # Zero alerts is a measurement here, so the grid is fully populated with 0.
    assert bool(numpy.all(dataset["alerts_in_force"].values == 0.0))
    assert result.complete is True
    assert result.run_time == datetime(2026, 8, 30, 3, 16, 1, tzinfo=UTC)  # the service's updateSequence
    assert result.artifacts[1].payload_path.name.endswith(".geojson")
    assert json.loads(result.artifacts[1].payload_path.read_text())["features"] == []


def test_every_cap_alerts_artifact_declares_the_media_type_of_its_own_bytes(tmp_path: Path):
    """Regression: the two artifacts must not be able to swap media types.

    ``eccc-cap-alerts`` is the only adapter here that publishes two artifacts of
    two different kinds from one run, so it is the only one where a declared
    media type can drift away from the bytes on disk. A reader that opens the
    GeoJSON as Zarr fails with ``BadZipFile``, which reads like a corrupt
    artifact when the artifact is fine — so the declaration is pinned to the
    bytes here rather than to the order the artifacts happen to be listed in.
    """
    adapter = ECCCCapAlertsGeoMetAdapter(alerts_service().client())
    result = adapter.fetch(adapter.discover(WINDOW)[0], WINDOW, tmp_path)

    by_name = {artifact.logical_name: artifact for artifact in result.artifacts}
    assert set(by_name) == {"alerts", "alerts_features"}

    grid = by_name["alerts"]
    assert grid.media_type == "application/zarr+zip"
    # Zipped Zarr, and it reopens: declaring the type is not the same as it
    # being true.
    assert grid.payload_path.read_bytes()[:4] == b"PK\x03\x04"
    assert "alerts_in_force" in open_artifact(grid.payload_path).data_vars

    features = by_name["alerts_features"]
    assert features.media_type == "application/geo+json"
    document = json.loads(features.payload_path.read_text("utf-8"))
    assert document["type"] == "FeatureCollection"


def test_a_partly_queried_avalon_cannot_claim_no_alert_is_in_force(tmp_path: Path):
    """Two declared boxes, one of which the service refused."""
    service = alerts_service()
    adapter = ECCCCapAlertsGeoMetAdapter(service.client(), probe_boxes=avalon_probe_boxes(1, 2))
    candidate = adapter.discover(WINDOW)[0]
    assert len(candidate.detail["counts"]) == 2

    detail = dict(candidate.detail)
    detail["counts"] = {key: value for key, value in list(detail["counts"].items())[:-1]}
    detail["errors"] = ["Current-Alerts over {'south': 46.5}: NoMatch"]
    result = adapter.fetch(type(candidate)(candidate.provider_run_id, candidate.run_time, [], detail), WINDOW, tmp_path)

    assert result.complete is False
    assert result.artifacts[0].provenance["quality"]["status"] != "passed"


def test_the_default_probe_is_one_box_covering_the_avalon_core():
    """A point-sized probe returns nothing for these vector layers, so the
    query geometry has to be the box itself."""
    boxes = avalon_probe_boxes()
    assert boxes == ({"south": 46.5, "north": 48.5, "west": -55.0, "east": -51.0},)
    assert ECCCAqhiGeoMetAdapter().probe_boxes == boxes
    assert ECCCCapAlertsGeoMetAdapter().probe_boxes == boxes


def test_a_vector_query_is_sent_as_the_declared_box_not_a_point():
    service = alerts_service()
    adapter = ECCCCapAlertsGeoMetAdapter(service.client())
    adapter.discover(WINDOW)
    queries = [url for url in service.requests if url.params.get("request") == "GetFeatureInfo"]
    assert len(queries) == 1
    assert queries[0].params["bbox"] == "46.5,-55.0,48.5,-51.0"


# --------------------------------------------------------------------------
# AQHI
# --------------------------------------------------------------------------


def aqhi_feature(station: str, name: str, index: str, moment: str, lon: float, lat: float) -> dict:
    return {
        "type": "Feature",
        "properties": {
            "_id": f"AQ_OBS-{station}-{moment}",
            "id": f"AQ_OBS-{station}-{moment}",
            "properties.aqhi": index,
            "properties.location_id": station,
            "properties.location_name_en": name,
            "properties.observation_datetime": moment,
        },
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
    }


def aqhi_service(features) -> Service:
    service = Service()
    service.advertise(AQHI_LAYER, "AQHI - Observations")
    service.answer(AQHI_LAYER, {"type": "FeatureCollection", "features": features})
    return service


def test_aqhi_is_published_as_its_own_index_never_converted(tmp_path: Path):
    features = [
        aqhi_feature("ABEFS", "St. John's", "1.81", "2026-08-30T03:00:00Z", -52.7252, 47.5658),
        aqhi_feature("ABYRK", "Grand Falls - Windsor", "1.54", "2026-08-30T03:00:00Z", -55.6666, 48.9333),
    ]
    adapter = ECCCAqhiGeoMetAdapter(aqhi_service(features).client())
    result = adapter.fetch(adapter.discover(WINDOW)[0], WINDOW, tmp_path)

    dataset = open_artifact(result.artifacts[0].payload_path)
    assert dataset["air_quality_health_index"].attrs["units"] == "index"
    assert "not PM2.5" in dataset["air_quality_health_index"].attrs["semantics"]
    assert sorted(v for v in dataset["air_quality_health_index"].values.ravel() if not math.isnan(v)) == [1.54, 1.81]
    assert result.complete is True
    assert result.artifacts[0].provenance["quality"]["quantity"] == "air_quality_health_index"


def test_a_station_reporting_outside_the_window_fails_the_run(tmp_path: Path):
    features = [
        aqhi_feature("ABEFS", "St. John's", "1.81", "2026-08-30T03:00:00Z", -52.7252, 47.5658),
        aqhi_feature("STALE", "Stale station", "3.0", "2026-08-20T03:00:00Z", -54.0, 48.0),
    ]
    adapter = ECCCAqhiGeoMetAdapter(aqhi_service(features).client())
    result = adapter.fetch(adapter.discover(WINDOW)[0], WINDOW, tmp_path)

    assert result.complete is False
    assert any("outside" in flag for flag in result.artifacts[0].provenance["flags"])


def test_a_feature_with_no_numeric_index_fails_the_run(tmp_path: Path):
    features = [
        aqhi_feature("ABEFS", "St. John's", "1.81", "2026-08-30T03:00:00Z", -52.7252, 47.5658),
        aqhi_feature("BROKEN", "Broken station", "", "2026-08-30T03:00:00Z", -54.0, 48.0),
    ]
    adapter = ECCCAqhiGeoMetAdapter(aqhi_service(features).client())
    result = adapter.fetch(adapter.discover(WINDOW)[0], WINDOW, tmp_path)

    assert result.complete is False
    assert any("no numeric AQHI" in flag for flag in result.artifacts[0].provenance["flags"])


def test_no_aqhi_observation_at_all_is_unavailable_not_an_empty_artifact(tmp_path: Path):
    adapter = ECCCAqhiGeoMetAdapter(aqhi_service([]).client())
    candidate = adapter.discover(WINDOW)[0]
    with pytest.raises(AdapterUnavailable, match="no AQHI observation inside the window"):
        adapter.fetch(candidate, WINDOW, tmp_path)


# --------------------------------------------------------------------------
# Wind
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("direction", "expected_u", "expected_v"),
    [
        (0.0, 0.0, -10.0),  # a northerly blows toward the south
        (90.0, -10.0, 0.0),  # an easterly blows toward the west
        (180.0, 0.0, 10.0),
        (270.0, 10.0, 0.0),
    ],
)
def test_wind_uses_the_meteorological_convention(direction, expected_u, expected_v):
    u, v = wind_components(10.0, direction)
    assert u == pytest.approx(expected_u, abs=1e-6)
    assert v == pytest.approx(expected_v, abs=1e-6)


# --------------------------------------------------------------------------
# Model adapters (unregistered by default) and the humidity profile
# --------------------------------------------------------------------------


def model_service(*, omit: str | None = None) -> Service:
    service = Service()
    for layer, (title, value) in MODEL_LAYER_TITLES.items():
        if layer == omit:
            continue
        service.advertise(layer, title, time=MODEL_EXTENT, reference_time=MODEL_REFERENCE)
        for stamp in MODEL_TIMES:
            service.answer(layer, feature(layer, value, title=title, time=stamp, reference_time="2026-08-29T18:00:00Z"), at=stamp)
    for level in PROFILE_LEVELS_HPA:
        layer = geomet.HRDPS_PROFILE_TEMPLATE.format(level=level)
        title = f"HRDPS.CONTINENTAL.PRES - Relative humidity at {level} mb [%]"
        service.advertise(layer, title, time=MODEL_EXTENT, reference_time=MODEL_REFERENCE)
        for stamp in MODEL_TIMES:
            service.answer(layer, feature(layer, 70.0, title=title, time=stamp, reference_time="2026-08-29T18:00:00Z"), at=stamp)
    return service


def test_the_hrdps_geomet_adapter_reconstructs_wind_components(tmp_path: Path):
    service = model_service()
    adapter = ECCCHrdpsGeoMetAdapter(service.client())
    result = adapter.fetch(adapter.discover(WINDOW)[0], WINDOW, tmp_path)

    surface = open_artifact(result.artifacts[0].payload_path)
    # WSPD 10 m/s from 000 degrees: a northerly, so v is negative.
    assert surface["wind_u_10m"].values.ravel()[0] == pytest.approx(0.0, abs=1e-6)
    assert surface["wind_v_10m"].values.ravel()[0] == pytest.approx(-10.0, abs=1e-6)
    assert "comes from" in surface["wind_u_10m"].attrs["semantics"]
    # Pa is converted to hPa by normalize_units; the manifest checks the stored unit.
    assert surface["mean_sea_level_pressure"].attrs["units"] == "hPa"
    assert surface["mean_sea_level_pressure"].values.ravel()[0] == pytest.approx(1013.0)
    assert surface["precipitation_accumulation"].attrs["accumulation_interval_hours"] == 1.0
    assert result.complete is True
    assert result.qc_passed is True
    assert result.run_time == datetime(2026, 8, 29, 18, tzinfo=UTC)


def test_a_model_run_missing_a_declared_field_fails_closed(tmp_path: Path):
    """The mirror image: drop one layer and nothing may publish."""
    service = model_service(omit="HRDPS.CONTINENTAL_TD")
    service.advertise(
        "HRDPS.CONTINENTAL_TD", MODEL_LAYER_TITLES["HRDPS.CONTINENTAL_TD"][0], time=MODEL_EXTENT,
        reference_time=MODEL_REFERENCE,
    )
    service.exceptions.add("HRDPS.CONTINENTAL_TD")
    adapter = ECCCHrdpsGeoMetAdapter(service.client())
    result = adapter.fetch(adapter.discover(WINDOW)[0], WINDOW, tmp_path)

    assert result.complete is False
    assert result.artifacts[0].provenance["quality"]["status"] != "passed"
    assert any("dew_point_2m" in flag for flag in result.artifacts[0].provenance["quality"]["flags"])


def test_the_pressure_level_humidity_profile_is_published_with_its_levels(tmp_path: Path):
    service = model_service()
    adapter = ECCCHrdpsGeoMetAdapter(service.client())
    result = adapter.fetch(adapter.discover(WINDOW)[0], WINDOW, tmp_path)

    profile = next(item for item in result.artifacts if item.logical_name == "profile")
    dataset = open_artifact(profile.payload_path)
    assert list(dataset["pressure"].values) == [float(level) for level in PROFILE_LEVELS_HPA]
    assert dataset["relative_humidity"].attrs["units"] == "percent"
    assert profile.provenance["levels_returned"] == list(PROFILE_LEVELS_HPA)
    assert profile.provenance["quality"]["status"] == "passed"


def test_the_humidity_profile_is_usable_without_registering_an_adapter(tmp_path: Path):
    """The profile is the one thing GeoMet gives that Datamart does not, so it
    must not be locked inside an adapter that is not registered."""
    service = model_service()
    profile = humidity_profile(
        service.client(),
        geomet.HRDPS_PROFILE_TEMPLATE,
        (850, 700, 500),
        datetime(2026, 8, 30, 3, tzinfo=UTC),
    )
    assert profile is not None
    assert profile.levels_returned == (850, 700, 500)
    assert profile.dataset["relative_humidity"].values.ravel().tolist() == [70.0, 70.0, 70.0]


def test_a_profile_where_no_level_answered_is_none_not_an_empty_profile():
    service = Service()
    for level in (850, 700):
        layer = geomet.HRDPS_PROFILE_TEMPLATE.format(level=level)
        service.advertise(layer, f"RH at {level} mb [%]", time=MODEL_EXTENT, reference_time=MODEL_REFERENCE)
        service.answer(layer, EMPTY_COLLECTION)
    assert (
        humidity_profile(
            service.client(), geomet.HRDPS_PROFILE_TEMPLATE, (850, 700), datetime(2026, 8, 30, 3, tzinfo=UTC)
        )
        is None
    )


# --------------------------------------------------------------------------
# Registration
# --------------------------------------------------------------------------


def test_geomet_registers_exactly_the_four_ids_nothing_else_claims():
    from ingest.registry import registered_adapters

    registry = registered_adapters()
    for source_id in ("eccc-radar", "eccc-lightning", "eccc-cap-alerts", "eccc-aqhi"):
        assert type(registry[source_id]).__module__.endswith("eccc_geomet")
    # HRDPS and RDPS stay with the Datamart GRIB2 adapter.
    assert geomet.MODEL_SOURCE_OWNER == "eccc_datamart"
    assert type(registry["eccc-hrdps"]).__module__.endswith("eccc_datamart")
    assert type(registry["eccc-rdps"]).__module__.endswith("eccc_datamart")
    assert geomet.HRDPS_ADAPTER is None and geomet.RDPS_ADAPTER is None


def test_a_duplicate_source_id_raises_rather_than_being_skipped():
    """A second adapter class for a taken id must be loud.

    This is the failure the old loader hid: ``register`` raised, the loader
    logged it and moved on, and an entire adapter family silently vanished.
    """
    from ingest.registry import register

    class ImpostorRadarAdapter:
        source_id = "eccc-radar"

    with pytest.raises(ValueError, match="already has a registered adapter"):
        register(ImpostorRadarAdapter())


def test_a_module_that_exists_and_fails_to_import_takes_the_loader_down(monkeypatch):
    import importlib

    from ingest import adapters

    def explode(name: str):
        raise ValueError("eccc-radar already has a registered adapter")

    monkeypatch.setattr(importlib, "import_module", explode)
    with pytest.raises(ValueError, match="already has a registered adapter"):
        adapters._load()


def test_a_module_that_does_not_exist_is_still_tolerated(monkeypatch):
    """Families land independently; an absent module must stay non-fatal."""
    from ingest import adapters

    monkeypatch.setattr(adapters, "_MODULES", ("a_family_that_has_not_landed_yet",))
    assert adapters._load() == []


# --------------------------------------------------------------------------
# Opt-in live smoke
# --------------------------------------------------------------------------


@pytest.mark.live_smoke
@pytest.mark.skipif(os.environ.get("WEATHER_LIVE_SMOKE") != "1", reason="set WEATHER_LIVE_SMOKE=1 to hit GeoMet")
def test_live_geomet_still_advertises_every_pinned_layer():
    """One polite pass over the pinned layers, checking title and units.

    Deliberately capabilities-only plus a single radar reading: this is a
    public good and a smoke test has no business sampling it heavily.
    """
    client = GeoMetClient()
    try:
        for layer, expected_units in (
            (RADAR_RAIN_LAYER, "mm h-1"),
            (RADAR_SNOW_LAYER, "cm h-1"),
            (LIGHTNING_LAYER, "flash km-2 min-1"),
            (ALERTS_LAYER, None),
            (AQHI_LAYER, None),
        ):
            capability = client.capabilities(layer)
            assert capability.name == layer
            _raw, canonical, recognised = capability.units
            if expected_units is None:
                # Neither vector layer states a unit. ``Current-Alerts`` ends
                # its title with "[experimental]", which is a provider flag,
                # not a unit: stripped before the bracket rule, so no unit.
                assert recognised is False
                assert canonical is None
            else:
                assert recognised is True
                assert canonical == expected_units

        # The four WEonG fog-visibility layers the API proxies as imagery.
        # ECCC marks the RDPS pair "[experimental]"; the flag must be reported
        # as such and the unit must still read as metres.
        for layer, expected_experimental in (
            ("HRDPS-WEonG_2.5km_LiquidFogVisibility", False),
            ("HRDPS-WEonG_2.5km_IceFogVisibility", False),
            ("RDPS-WEonG_10km_LiquidFogVisibility", True),
            ("RDPS-WEonG_10km_IceFogVisibility", True),
        ):
            capability = client.capabilities(layer)
            assert capability.name == layer
            _raw, canonical, recognised = capability.units
            assert (canonical, recognised) == ("m", True), capability.title
            assert is_experimental(capability.title) is expected_experimental, capability.title
            assert capability.time is not None and capability.time.period == timedelta(hours=1)

        # One GOES-East satellite layer the API proxies as observed imagery.
        # Its title ends "[1 km]", a resolution: no unit, and every advertised
        # scan is in the past.
        satellite = client.capabilities("GOES-East_1km_DayVis-NightIR")
        assert satellite.name == "GOES-East_1km_DayVis-NightIR"
        assert parse_title_resolution(satellite.title) == "1 km", satellite.title
        assert satellite.units == (None, None, False), satellite.title
        assert satellite.time is not None and satellite.time.period == timedelta(minutes=10)
        assert satellite.time.end <= datetime.now(UTC)

        extent = client.capabilities(RADAR_RAIN_LAYER).time
        assert extent is not None and extent.period == timedelta(minutes=6)
        sample = client.feature_info(RADAR_RAIN_LAYER, 47.5615, -52.7126, valid_time=extent.end)
        # Either a reading or an explicit absence; never anything in between.
        assert sample is None or sample.units == "mm h-1"
    finally:
        client.close()


@pytest.mark.live_smoke
@pytest.mark.skipif(os.environ.get("WEATHER_LIVE_SMOKE") != "1", reason="set WEATHER_LIVE_SMOKE=1 to hit GeoMet")
def test_live_geomet_still_renders_a_tile_a_legend_and_the_nomatch_fault():
    """Three requests: the tile, its ramp, and the fault that masquerades as both.

    The fault is the one worth re-checking against the live service, because the
    day it starts arriving with an error status instead of HTTP 200 is the day
    this module's content-type guard stops being the thing that saves us.
    """
    client = GeoMetClient()
    try:
        tile = client.map_image(RADAR_RAIN_LAYER, TILE_BOUNDS, width=512, height=512)
        assert tile.content_type == "image/png"
        assert tile.payload[:8] == PNG_MAGIC
        assert tile.valid_time is not None

        legend = client.legend_graphic(RADAR_RAIN_LAYER, style="RADARURPPRECIPR")
        assert legend.content_type == "image/png"
        assert legend.payload[:8] == PNG_MAGIC

        # One WEonG fog tile and its ramp. A near-empty PNG is a reading (no
        # fog rendered at that hour), so only the media type is asserted.
        fog = client.map_image("HRDPS-WEonG_2.5km_LiquidFogVisibility", TILE_BOUNDS, width=400, height=200)
        assert fog.content_type == "image/png"
        assert fog.payload[:8] == PNG_MAGIC
        assert fog.valid_time is not None
        fog_legend = client.legend_graphic("HRDPS-WEonG_2.5km_LiquidFogVisibility")
        assert fog_legend.content_type == "image/png"
        assert fog_legend.payload[:8] == PNG_MAGIC

        # One GOES-East scan at the latest advertised instant. Observed
        # imagery: the resolved valid time can never be in the future.
        scan = client.map_image("GOES-East_1km_DayVis-NightIR", TILE_BOUNDS, width=400, height=200)
        assert scan.content_type == "image/png"
        assert scan.payload[:8] == PNG_MAGIC
        assert scan.valid_time is not None and scan.valid_time <= datetime.now(UTC)

        with pytest.raises(GeoMetServiceException, match="NoMatch"):
            client.map_image(
                RADAR_RAIN_LAYER,
                TILE_BOUNDS,
                width=64,
                height=64,
                valid_time=datetime(2020, 1, 1, tzinfo=UTC),
                resolve=False,
            )
    finally:
        client.close()
