"""Every layer in the live catalogue, against a running stack.

The stub suites pin one layer each against a store built to suit it. This one
asks the opposite question: take whatever the deployment is actually
advertising right now, and hold every layer of it to the same contract. A layer
added later is covered the moment it appears in ``/layers`` - there is no list
here to forget to update, which is the point.

The contract, for each layer:

* every instant it advertises renders, and renders an image;
* the image is the size that was asked for, so a transposed extent cannot pass
  as a plausible picture of the wrong place;
* the response dates itself, and dates itself to a real published instant;
* provenance travels with the pixels - source, evidence basis, mode, and the
  standing ``operational: false``;
* a layer that declares no map image says so with a status, never with an
  empty image, and never with a 200.

For every rendered-grid layer with at least two published instants, the
derived motion field owes the same honesty:

* ``/flow`` serves the first adjacent frame pair, with its interpolation
  method and shader disclosed in the response headers;
* the ``tangents`` texture that feeds the C1 Hermite construction serves for
  that same pair;
* a pair that is not adjacent, or an instant the layer never published, is
  refused rather than answered with an invented field.

Opt in, because it needs the stack up::

    WEATHER_LAYER_CONTRACT=1 uv run pytest -m layer_contract

or ``make test-layers`` from the experiment root.
"""

from __future__ import annotations

import json
import os
import struct
import urllib.error
import urllib.parse
import urllib.request

import pytest

pytestmark = pytest.mark.layer_contract

BASE = os.environ.get("WEATHER_API_BASE", "http://127.0.0.1:8000/api/experiments/weather/v0")
ENABLED = os.environ.get("WEATHER_LAYER_CONTRACT") == "1"

#: The Avalon core, the extent the map actually opens on.
BOUNDS = {"south": 47.0, "west": -53.6, "north": 48.1, "east": -52.0}
SIZE = 96

#: Provenance every rendered or proxied image owes its reader.
REQUIRED_HEADERS = (
    "X-Weather-Layer-Id",
    "X-Weather-Data-Mode",
    "X-Weather-Operational",
    "X-Weather-Evidence-Basis",
    "X-Weather-Image-Basis",
    "X-Weather-Valid-Time",
)


class Headers(dict):
    """Response headers, matched the way HTTP defines them: case-insensitively.

    Written because the first version of this module compared against the
    canonical spellings and missed every one of them, failing all 30 layers
    with a message that read exactly like 30 real defects.
    """

    def __init__(self, raw):
        super().__init__({str(name).lower(): value for name, value in raw.items()})

    def __contains__(self, name) -> bool:
        return super().__contains__(str(name).lower())

    def __getitem__(self, name):
        return super().__getitem__(str(name).lower())

    def get(self, name, default=None):
        return super().get(str(name).lower(), default)


def _get(path: str):
    request = urllib.request.Request(f"{BASE}{path}")
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            return response.status, response.read(), Headers(response.headers)
    except urllib.error.HTTPError as error:
        return error.code, error.read(), Headers(error.headers)


def _catalogue() -> list[dict]:
    """The live layer index, or an empty list when the stack is not up."""
    if not ENABLED:
        return []
    try:
        status, body, _ = _get("/layers")
    except Exception:
        return []
    if status != 200:
        return []
    return json.loads(body)["layers"]


LAYERS = _catalogue()


def _method_catalogue() -> list[dict]:
    """The live interpolation bench, or an empty list when the stack is not up."""
    if not ENABLED:
        return []
    try:
        status, body, _ = _get("/methods")
    except Exception:
        return []
    if status != 200:
        return []
    return json.loads(body)["methods"]


METHODS_PAYLOAD = _method_catalogue()
ENABLED_METHODS = [method for method in METHODS_PAYLOAD if method.get("enabled")]
RENDERED_GRID_LAYERS = [layer for layer in LAYERS if layer.get("group") == "rendered_grid"]
#: Every (rendered-grid layer, enabled method) pair the deployment offers.
LAYER_METHOD_PAIRS = [(layer, method) for layer in RENDERED_GRID_LAYERS for method in ENABLED_METHODS]
#: The shaders whose construction evaluates the ``residual`` envelope texture.
ENVELOPE_SHADERS = ("residual-advection",)


def _png_size(payload: bytes) -> tuple[int, int] | None:
    if not payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    width, height = struct.unpack(">II", payload[16:24])
    return width, height


def _jpeg_size(payload: bytes) -> tuple[int, int] | None:
    if not payload.startswith(b"\xff\xd8"):
        return None
    offset = 2
    while offset + 9 < len(payload):
        if payload[offset] != 0xFF:
            offset += 1
            continue
        marker = payload[offset + 1]
        if marker in (0xC0, 0xC1, 0xC2):
            height, width = struct.unpack(">HH", payload[offset + 5:offset + 9])
            return width, height
        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
            offset += 2
            continue
        (length,) = struct.unpack(">H", payload[offset + 2:offset + 4])
        offset += 2 + length
    return None


def _image_size(payload: bytes) -> tuple[int, int] | None:
    return _png_size(payload) or _jpeg_size(payload)


def _ids(layers) -> list[str]:
    return [layer["id"] for layer in layers]


def _is_proxied(layer) -> bool:
    """Drawn by fetching upstream per request, rather than from an artifact."""
    return layer.get("evidence_basis") != "published_artifact"


def _instants_to_check(layer) -> list[str]:
    """Which advertised instants this layer is swept over.

    A locally rendered layer reads from a published artifact, so every frame is
    free and all of them are checked. A proxied layer spends a real upstream
    request per frame against a public good, so it is sampled at the ends and
    the middle - enough to catch a layer that is broken, without standing on
    GeoMet's throat to prove a layer that is fine.
    """
    times = layer.get("times") or []
    if not times or not _is_proxied(layer):
        return times
    picks = {0, len(times) // 2, len(times) - 1}
    return [times[index] for index in sorted(picks)]


requires_stack = pytest.mark.skipif(
    not ENABLED or not LAYERS,
    reason="set WEATHER_LAYER_CONTRACT=1 with the Compose stack up",
)


@requires_stack
def test_the_catalogue_offers_layers_to_check():
    assert LAYERS, "the running stack advertised no layers at all"


@requires_stack
@pytest.mark.parametrize("layer", LAYERS, ids=_ids(LAYERS))
def test_a_layer_without_a_map_image_says_so_rather_than_returning_one(layer):
    """``raster_available: false`` must be answered with a status, not pixels."""
    if layer.get("raster_available") is not False:
        pytest.skip("this layer declares a map image")
    times = layer.get("times") or []
    if not times:
        pytest.skip("no advertised instant to ask over")
    status, body, _ = _get(_raster_path(layer["id"], times[-1]))
    assert status != 200, f"{layer['id']} declares no map image but returned one"
    assert _image_size(body) is None
    # It must say why in words, rather than answering with an empty image.
    assert json.loads(body)["detail"]


def _raster_path(layer_id: str, stamp: str) -> str:
    extent = "&".join(f"{key}={value}" for key, value in BOUNDS.items())
    return (
        f"/layers/{urllib.parse.quote(layer_id)}/raster"
        f"?valid_time={urllib.parse.quote(stamp)}&width={SIZE}&height={SIZE}&{extent}"
    )


@requires_stack
@pytest.mark.parametrize("layer", LAYERS, ids=_ids(LAYERS))
def test_every_advertised_instant_renders(layer):
    """The contract that broke GOES-19: advertised means drawable."""
    if layer.get("raster_available") is not True:
        pytest.skip("this layer declares no map image")
    times = _instants_to_check(layer)
    if not times:
        pytest.skip("this layer advertised no instants")
    failures = []
    for stamp in times:
        status, body, _ = _get(_raster_path(layer["id"], stamp))
        if status != 200:
            detail = body[:160].decode(errors="replace")
            failures.append(f"{stamp} -> {status} {detail}")
    assert not failures, (
        f"{layer['id']}: of {len(times)} advertised instant(s) checked, "
        f"{len(failures)} do not render:\n  " + "\n  ".join(failures)
    )


@requires_stack
@pytest.mark.parametrize("layer", LAYERS, ids=_ids(LAYERS))
def test_the_rendered_image_is_the_extent_and_size_that_was_asked_for(layer):
    """A transposed extent answers 200 with a plausible picture of nowhere.

    WMS 1.3.0 with EPSG:4326 is lat,lon; a swapped BBOX is answered 200 with a
    near-empty image and no error at all. Size is the cheap half of catching
    that, and it is the half a test can assert without a reference image.
    """
    if layer.get("raster_available") is not True:
        pytest.skip("this layer declares no map image")
    times = layer.get("times") or []
    if not times:
        pytest.skip("this layer advertised no instants")
    status, body, headers = _get(_raster_path(layer["id"], times[-1]))
    if status != 200:
        pytest.skip(f"covered by the advertised-instant test ({status})")
    size = _image_size(body)
    assert size is not None, f"{layer['id']} returned {headers.get('Content-Type')} that is not a decodable image"
    assert size == (SIZE, SIZE), f"{layer['id']} was asked for {SIZE}x{SIZE} and returned {size[0]}x{size[1]}"


@requires_stack
@pytest.mark.parametrize("layer", LAYERS, ids=_ids(LAYERS))
def test_the_image_carries_its_provenance_and_dates_itself_honestly(layer):
    if layer.get("raster_available") is not True:
        pytest.skip("this layer declares no map image")
    times = layer.get("times") or []
    if not times:
        pytest.skip("this layer advertised no instants")
    status, _, headers = _get(_raster_path(layer["id"], times[-1]))
    if status != 200:
        pytest.skip(f"covered by the advertised-instant test ({status})")
    missing = [name for name in REQUIRED_HEADERS if name not in headers]
    assert not missing, f"{layer['id']} served pixels without {missing}"
    assert headers["X-Weather-Layer-Id"] == layer["id"]
    # Nothing in this experiment is ever operational, without exception.
    assert headers["X-Weather-Operational"] == "false"
    # The instant it dates itself to must be one the layer actually publishes,
    # not the instant that happened to be asked for - with one documented
    # exception: a WMS layer with no time dimension at all (e.g. ECCC's
    # Current-Alerts or AQHI-OBS) is honest when it says "none" and explains
    # why in X-Weather-Time-Semantics, rather than inventing an instant. See
    # wms.py's ProxiedImage.headers() and
    # test_an_untimed_image_says_it_is_current_rather_than_borrowing_a_time in
    # test_wms_proxy.py for that tested, owner-approved behaviour.
    drawn = headers["X-Weather-Valid-Time"]
    if drawn == "none":
        semantics = headers.get("X-Weather-Time-Semantics", "")
        assert "not time-indexed" in semantics, (
            f"{layer['id']} dated its image none without explaining why in "
            f"X-Weather-Time-Semantics ({semantics!r})"
        )
    else:
        published = {stamp.replace("Z", "+00:00") for stamp in times}
        assert drawn in published or drawn.replace("+00:00", "Z") in set(times), (
            f"{layer['id']} dated its image {drawn}, which is not one of its published instants"
        )


@requires_stack
@pytest.mark.parametrize("layer", LAYERS, ids=_ids(LAYERS))
def test_an_instant_the_layer_never_published_is_refused_not_invented(layer):
    """Far outside the window there is no evidence, and none may be drawn."""
    if layer.get("raster_available") is not True:
        pytest.skip("this layer declares no map image")
    status, body, _ = _get(_raster_path(layer["id"], "1994-01-01T00:00:00Z"))
    assert status != 200, f"{layer['id']} drew an image for 1994, which it never published"
    assert _image_size(body) is None


def _flow_path(layer_id: str, frame_from: str, frame_to: str, *, texture: str = "motion", method: str | None = None) -> str:
    extent = "&".join(f"{key}={value}" for key, value in BOUNDS.items())
    selected = f"&method={urllib.parse.quote(method)}" if method else ""
    return (
        f"/layers/{urllib.parse.quote(layer_id)}/flow"
        f"?from={urllib.parse.quote(frame_from)}&to={urllib.parse.quote(frame_to)}"
        f"&width={SIZE}&height={SIZE}&{extent}&texture={texture}{selected}"
    )


def _skip_unless_rendered_grid_pair(layer) -> list[str]:
    """The precondition every flow test shares: a rendered-grid layer with an adjacent pair to ask about."""
    if layer.get("group") != "rendered_grid":
        pytest.skip("flow is derived only for rendered-grid layers")
    times = layer.get("times") or []
    if len(times) < 2:
        pytest.skip("fewer than two advertised instants; no adjacent pair to check")
    return times


@requires_stack
@pytest.mark.parametrize("layer", LAYERS, ids=_ids(LAYERS))
def test_flow_serves_the_first_adjacent_frame_pair(layer):
    """The defect this test exists to catch: interpolation silently dying mid-cycle.

    A model source republishes its surface artifact early in an ingest cycle,
    which gives it a new revision_id. The derived cloud_motion artifact still
    records the surface revision it was built from, and the derive pass that
    would catch it up only runs once the whole cycle finishes - so /flow 404s
    for a live window every cycle, and the web silently degrades to a
    disclosed linear crossfade without anyone noticing. This test is expected
    to fail during that derive-lag window; that is the point of it.
    """
    times = _skip_unless_rendered_grid_pair(layer)
    status, body, _ = _get(_flow_path(layer["id"], times[0], times[1]))
    detail = body[:300].decode(errors="replace")
    assert status == 200, (
        f"{layer['id']}: /flow for the first adjacent frame pair ({times[0]} -> {times[1]}) "
        f"returned {status}: {detail}. Likely cause: the derived cloud-motion artifact is behind "
        "the current surface revision because the derive pass only re-runs after a full ingest "
        "cycle finishes, not the moment a source republishes mid-cycle."
    )


@requires_stack
@pytest.mark.parametrize("layer", LAYERS, ids=_ids(LAYERS))
def test_flow_carries_its_interpolation_provenance(layer):
    """A served flow texture must disclose the method and shader that made it."""
    times = _skip_unless_rendered_grid_pair(layer)
    status, _, headers = _get(_flow_path(layer["id"], times[0], times[1]))
    if status != 200:
        pytest.skip(f"covered by the adjacent-pair test ({status})")
    required = ("X-Weather-Interpolation-Method", "X-Weather-Flow-Shader")
    missing = [name for name in required if name not in headers]
    assert not missing, f"{layer['id']} served a flow texture without {missing}"


@requires_stack
@pytest.mark.parametrize("layer", LAYERS, ids=_ids(LAYERS))
def test_flow_serves_the_tangents_texture_for_the_same_pair(layer):
    """texture=tangents feeds the C1 Hermite construction and must serve alongside the pairwise field."""
    times = _skip_unless_rendered_grid_pair(layer)
    status, body, _ = _get(_flow_path(layer["id"], times[0], times[1], texture="tangents"))
    detail = body[:300].decode(errors="replace")
    assert status == 200, (
        f"{layer['id']}: /flow?texture=tangents for {times[0]} -> {times[1]} returned {status}: {detail}"
    )


@requires_stack
@pytest.mark.parametrize("layer", LAYERS, ids=_ids(LAYERS))
def test_flow_refuses_a_pair_that_is_not_adjacent_or_not_published(layer):
    """A non-adjacent pair, or an instant never published, must be refused, never answered with an invented field."""
    times = _skip_unless_rendered_grid_pair(layer)
    # With three or more published instants, the first and last are a real
    # pair of published instants that are not adjacent. With exactly two,
    # first and last ARE the only (adjacent) pair, so the far side is asked
    # about an instant the layer never published instead.
    frame_to = times[-1] if len(times) >= 3 else "1994-01-01T00:00:00Z"
    status, body, _ = _get(_flow_path(layer["id"], times[0], frame_to))
    assert status != 200, f"{layer['id']} served a flow field for {times[0]} -> {frame_to}, which is not an adjacent published pair"


# ---------------------------------------------------------------- the bench
#
# For every rendered-grid layer and every enabled interpolation method, the
# served fields owe the same honesty the baseline does: a motion texture that
# is either served or refused by name, a per-shader texture that is served
# only for the shader that evaluates it, pixels of the size asked for, and a
# shader header that agrees with the server's own registry. And ``/methods``
# must carry the switches it applied and its fixed-control scores for the
# layer, because those are what the menu ranks on.


def _pair_ids(pairs) -> list[str]:
    return [f"{layer['id']}[{method['id']}]" for layer, method in pairs]


def _first_pair(layer) -> tuple[str, str]:
    times = _skip_unless_rendered_grid_pair(layer)
    return times[0], times[1]


requires_bench = pytest.mark.skipif(
    not ENABLED or not LAYER_METHOD_PAIRS,
    reason="set WEATHER_LAYER_CONTRACT=1 with the Compose stack up and a scored bench",
)


@requires_stack
def test_the_bench_offers_methods_to_check():
    if not RENDERED_GRID_LAYERS:
        pytest.skip("the running stack advertised no rendered-grid layer")
    assert ENABLED_METHODS, "the running stack advertised no enabled interpolation method"
    assert ENABLED_METHODS[0]["id"] == "baseline", "the baseline must stay first: it is the default and the control"


@requires_bench
@pytest.mark.parametrize(("layer", "method"), LAYER_METHOD_PAIRS, ids=_pair_ids(LAYER_METHOD_PAIRS))
def test_every_enabled_method_serves_motion_or_refuses_it_by_name(layer, method):
    """A method is either drawn from its own published fields or refused naming why - never substituted."""
    frame_from, frame_to = _first_pair(layer)
    status, body, headers = _get(_flow_path(layer["id"], frame_from, frame_to, method=method["id"]))
    if status == 404:
        detail = json.loads(body)["detail"]
        assert detail, f"{layer['id']}[{method['id']}]: a 404 with no reason"
        assert layer["id"] in detail
        return
    assert status == 200, f"{layer['id']}[{method['id']}]: /flow returned {status}: {body[:300].decode(errors='replace')}"
    assert _png_size(body) == (SIZE, SIZE), f"{layer['id']}[{method['id']}] was asked for {SIZE}x{SIZE} and returned {_png_size(body)}"
    assert headers["X-Weather-Interpolation-Method"] == method["id"]
    assert headers["X-Weather-Flow-Shader"] == method["shader"], (
        f"{layer['id']}[{method['id']}]: served shader {headers['X-Weather-Flow-Shader']!r} "
        f"disagrees with the registry's {method['shader']!r}"
    )
    assert headers["X-Weather-Operational"] == "false"
    assert float(headers["X-Weather-Flow-Scale"]) > 0


@requires_bench
@pytest.mark.parametrize(("layer", "method"), LAYER_METHOD_PAIRS, ids=_pair_ids(LAYER_METHOD_PAIRS))
def test_the_envelope_texture_is_served_only_for_the_shader_that_evaluates_it(layer, method):
    """``residual`` is 200 for a residual-advection shader and a 404 naming the method for every other."""
    frame_from, frame_to = _first_pair(layer)
    motion_status, _, _ = _get(_flow_path(layer["id"], frame_from, frame_to, method=method["id"]))
    status, body, headers = _get(_flow_path(layer["id"], frame_from, frame_to, texture="residual", method=method["id"]))
    if method["shader"] in ENVELOPE_SHADERS:
        if motion_status != 200:
            pytest.skip(f"the method itself is not served for this pair ({motion_status})")
        assert status == 200, (
            f"{layer['id']}[{method['id']}]: the envelope texture returned {status}: {body[:300].decode(errors='replace')}"
        )
        assert _png_size(body) == (SIZE, SIZE)
        assert headers["X-Weather-Flow-Texture"] == "residual"
        assert headers["X-Weather-Flow-Shader"] == method["shader"]
        assert "envelope" in headers["X-Weather-Render-Semantics"]
        # The served scale follows the derive's own verdict for this layer: a
        # term the fixed-control gate admitted must reach the client with a
        # non-zero envelope, and a term it refused must reach it as EXACTLY
        # zero - a zero envelope is how "reduced to the default" is drawn, and
        # a non-zero one under a refused verdict would be a picture the
        # provenance does not license (live cycle of 2026-09-01: every term
        # refused, every scale 0.0000).
        scale = float(headers["X-Weather-Flow-Scale"])
        _, methods_body, _ = _get("/methods")
        served = json.loads(methods_body)
        verdict = next(
            (
                score
                for item in served["methods"]
                if item["id"] == method["id"]
                for score in item.get("scores", [])
                if score.get("layer_id") == layer["id"]
            ),
            None,
        )
        assert verdict is not None, f"{layer['id']}[{method['id']}]: /methods carries no score for this layer"
        if verdict["reduced_to_default"]:
            assert scale == 0.0, f"{layer['id']}[{method['id']}]: refused by the gate yet served a non-zero envelope (scale {scale})"
        else:
            assert scale > 0, f"{layer['id']}[{method['id']}]: admitted by the gate yet served a zero envelope"
    else:
        assert status == 404, f"{layer['id']}[{method['id']}] served an envelope its shader {method['shader']!r} never evaluates"
        detail = json.loads(body)["detail"]
        assert f"'{method['id']}'" in detail or "predates" in detail or "carries no" in detail, detail


@requires_bench
@pytest.mark.parametrize("layer", RENDERED_GRID_LAYERS, ids=_ids(RENDERED_GRID_LAYERS))
def test_the_bench_publishes_applied_switches_and_fixed_control_scores(layer):
    """What the menu ranks on must be there for every scored method on this layer."""
    _skip_unless_rendered_grid_pair(layer)
    scored = [
        (method, score)
        for method in ENABLED_METHODS
        for score in method.get("scores", [])
        if score.get("layer_id") == layer["id"]
    ]
    if not scored:
        pytest.skip(f"no enabled method has been scored on {layer['id']} yet")
    for method, score in scored:
        where = f"{layer['id']}[{method['id']}]"
        assert isinstance(score.get("applied"), dict), f"{where}: no applied switches published"
        assert isinstance(score.get("reduced_to_default"), bool), f"{where}: reduced_to_default missing"
        assert isinstance(score.get("improvement_over_crossfade"), (int, float)), f"{where}: no crossfade skill"
        assert isinstance(score.get("improvement_over_advection"), (int, float)), f"{where}: no advection skill"
        assert isinstance(score.get("midpoint_ssim"), (int, float)), f"{where}: no midpoint SSIM"
        assert isinstance(score.get("midpoint_sharpness_ratio"), (int, float)), f"{where}: no sharpness ratio"
    for method in ENABLED_METHODS:
        for key in ("plain", "gap", "notes"):
            assert isinstance(method.get(key), str), f"{method['id']}: reader copy {key!r} missing"
