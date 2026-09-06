"""The GFZ Hp30 adapter: bounded request, declared licence, feed instants.

Fixture-driven and offline. The one test that touches the network is the
``live_smoke`` tripwire at the bottom, which is opt-in and was run once for
the capture receipted at
``docs/research/wayfinder/space-weather-receipts/gfz-hp30.json``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import numpy
import pytest

from ingest.adapters.gfz import GFZ_JSON_URL, GFZHp30Adapter, GFZHp60Adapter, GFZKpAdapter
from ingest.contract import AdapterUnavailable, FetchWindow
from ingest.http import USER_AGENT, PoliteClient

from tests.test_space_weather_series import ZipStore, artifact

UTC = timezone.utc

FIXTURE = Path(__file__).parent / "fixtures" / "space_weather" / "gfz_hp30.json"
#: An hour after the fixture's newest instant (2026-09-05T00:30Z), so the
#: whole fixture sits inside a 24 h window and nothing is stale.
NOW = datetime(2026, 9, 5, 1, 30, tzinfo=UTC)
WINDOW = FetchWindow(now=NOW)


@pytest.fixture(autouse=True)
def local_hp30_child(monkeypatch):
    """Exercise the child protocol on Darwin; Linux tests retain kernel enforcement."""
    from ingest import gfz_hp30_isolated
    from ingest.isolation import BoundedProcessError
    def run(action, raw, destination):
        if action == "probe": return type("Result",(),{"stdout":b""})()
        output=destination or Path("/tmp/unused-gfz-hp30")
        result=subprocess.run([sys.executable,"-m","ingest.gfz_hp30_isolated",action,str(output)],input=raw,capture_output=True,
            env={**os.environ,"PYTHONPATH":str(Path(gfz_hp30_isolated.__file__).resolve().parents[1])})
        if result.returncode: raise BoundedProcessError(result.stderr.decode())
        return type("Result",(),{"stdout":result.stdout})()
    monkeypatch.setattr(GFZHp30Adapter,"_run_isolated",staticmethod(run))


def payload(**overrides):
    body = json.loads(FIXTURE.read_text(encoding="utf-8"))
    body.update(overrides)
    return body


class Recorder:
    """Every request the adapter made, so the bound can be asserted."""

    def __init__(self) -> None:
        self.urls: list[str] = []


def make_client(body, *, status: int = 200, headers: dict[str, str] | None = None) -> tuple[PoliteClient, Recorder]:
    raw = body if isinstance(body, bytes) else json.dumps(body).encode()
    recorder = Recorder()

    def handler(request: httpx.Request) -> httpx.Response:
        recorder.urls.append(str(request.url))
        return httpx.Response(status, content=raw, headers=headers or {})

    client = PoliteClient(min_host_interval_seconds=0.0, attempts=1)
    client._client = httpx.Client(transport=httpx.MockTransport(handler), headers={"User-Agent": USER_AGENT})
    return client, recorder


def discovered(body=None, *, window: FetchWindow = WINDOW, **client_kwargs):
    client, recorder = make_client(payload() if body is None else body, **client_kwargs)
    adapter = GFZHp30Adapter(client=client)
    return adapter, adapter.discover(window), recorder


# --- the bounded request --------------------------------------------------


def test_discover_asks_for_the_window_and_no_more():
    _adapter, candidates, recorder = discovered()
    assert len(recorder.urls) == 1
    parsed = urlparse(recorder.urls[0])
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == GFZ_JSON_URL
    query = {key: value[0] for key, value in parse_qs(parsed.query).items()}
    assert query == {
        "start": "2026-09-04T01:30:00Z",
        "end": "2026-09-05T01:30:00Z",
        "index": "Hp30",
    }
    # The same parameters travel into the receipt, so the capture reproduces.
    assert candidates[0].detail["receipt"].request_parameters == query


def test_discover_never_asks_wider_than_twenty_four_hours():
    wide = FetchWindow(now=NOW, back_hours=240.0)
    _adapter, _candidates, recorder = discovered(window=wide)
    query = {key: value[0] for key, value in parse_qs(urlparse(recorder.urls[0]).query).items()}
    assert query["start"] == "2026-09-04T01:30:00Z"


def test_discover_carries_records_receipt_and_valid_times():
    _adapter, candidates, _recorder = discovered()
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.provider_run_id == "gfz-hp30-202609050030"
    assert candidate.run_time == datetime(2026, 9, 5, 0, 30, tzinfo=UTC)
    assert isinstance(candidate.detail["raw"], bytes)
    assert len(candidate.detail["valid_times"]) == 10
    assert candidate.detail["valid_times"][0] == "2026-09-04T20:00:00Z"
    assert candidate.detail["valid_times"][-1] == "2026-09-05T00:30:00Z"
    receipt = candidate.detail["receipt"]
    assert receipt.byte_count > 0 and len(receipt.sha256) == 64
    assert "payload" not in receipt.as_dict()


# --- refusals -------------------------------------------------------------


@pytest.mark.parametrize("missing", ["Hp30", "datetime", "meta"])
def test_a_payload_missing_a_required_key_is_unavailable(missing: str):
    body = payload()
    del body[missing]
    with pytest.raises(AdapterUnavailable, match="schema drift"):
        discovered(body)


def test_a_licence_other_than_cc_by_40_is_refused():
    body = payload(meta={"license": "CC BY-NC 4.0", "source": "GFZ Potsdam"})
    with pytest.raises(AdapterUnavailable, match="CC BY 4.0"):
        discovered(body)


def test_misaligned_arrays_are_refused():
    body = payload()
    body["Hp30"] = body["Hp30"][:5]
    with pytest.raises(AdapterUnavailable, match="misaligned"):
        discovered(body)


def test_an_empty_selection_is_unavailable():
    with pytest.raises(AdapterUnavailable, match="no values"):
        discovered(payload(Hp30=[], datetime=[]))


def test_a_stale_feed_names_its_newest_instant():
    late = FetchWindow(now=datetime(2026, 9, 8, 0, 0, tzinfo=UTC))
    with pytest.raises(AdapterUnavailable, match="stale behind HTTP 200.*2026-09-05T00:30:00Z"):
        discovered(window=late)


def test_a_non_object_payload_is_unavailable():
    with pytest.raises(AdapterUnavailable, match="non-object"):
        discovered([1, 2, 3])


def test_a_non_json_body_is_unavailable():
    with pytest.raises(AdapterUnavailable, match="not JSON"):
        discovered(b"<html>service unavailable</html>")


def test_a_404_is_unavailable():
    with pytest.raises(AdapterUnavailable, match="unavailable"):
        discovered(status=404)


def test_an_oversize_body_is_unavailable():
    body = {"Hp30": [0.0] * 200000, "datetime": ["2026-09-05T00:00:00Z"] * 200000, "meta": {"license": "CC BY 4.0"}}
    with pytest.raises(AdapterUnavailable, match="ceiling"):
        discovered(body)


def test_a_repeated_instant_is_refused():
    body = payload()
    body["datetime"][1] = body["datetime"][0]
    with pytest.raises(AdapterUnavailable, match="repeated instant"):
        discovered(body)


def test_no_artifact_file_is_written_when_discovery_refuses(tmp_path: Path):
    with pytest.raises(AdapterUnavailable):
        discovered(payload(meta={"license": "other"}))
    assert not list(tmp_path.iterdir())


# --- the artifact ---------------------------------------------------------


def test_fetch_writes_the_pinned_series(tmp_path: Path):
    import xarray
    import zarr

    adapter, candidates, _recorder = discovered()
    result = adapter.fetch(candidates[0], WINDOW, tmp_path)

    assert result.source_id == "gfz-hp30"
    assert result.complete is True and result.qc_passed is True
    assert len(result.artifacts) == 1
    written = result.artifacts[0]
    assert written.logical_name == "hp30"
    assert written.payload_path == tmp_path / "hp30.zarr.zip"
    assert written.payload_path.exists()

    dataset = xarray.open_zarr(zarr.storage.ZipStore(str(written.payload_path), mode="r"), consolidated=False)
    assert list(dataset.dims) == ["valid_time"]
    assert "latitude" not in dataset.coords and "longitude" not in dataset.coords
    values = dataset["hp30_index"].values
    assert values.shape == (10,)
    assert values[0] == pytest.approx(0.333)
    # The gap in the fixture stays a gap.
    assert numpy.isnan(values[8])
    assert dataset["hp30_index"].attrs["units"] == "dimensionless"
    assert dataset["hp30_index"].attrs["original_units"] == "Hp30 index"
    assert "long_name" in dataset["hp30_index"].attrs
    # The instants are the feed's own, not the wall clock.
    assert str(dataset["valid_time"].values[0]).startswith("2026-09-04T20:00:00")
    assert str(dataset["valid_time"].values[-1]).startswith("2026-09-05T00:30:00")


def test_provenance_states_scope_licence_and_the_absent_status(tmp_path: Path):
    adapter, candidates, _recorder = discovered()
    result = adapter.fetch(candidates[0], WINDOW, tmp_path)
    provenance = result.artifacts[0].provenance

    assert provenance["source_id"] == "gfz-hp30"
    assert provenance["producer"] == "GFZ German Research Centre for Geosciences"
    assert provenance["adapter_version"] == "gfz-hp30-v1"
    assert provenance["measurement_scope"] == "planetary"
    assert provenance["evidence_classes"] == ["retrieved"]
    assert "intermediary" not in provenance
    assert provenance["licence"] == "CC BY 4.0"
    assert provenance["meta"] == {"license": "CC BY 4.0", "source": "GFZ Potsdam"}
    assert provenance["status_declared"] is False
    assert "none is invented" in provenance["status_note"]
    assert provenance["request_window"] == {
        "start": "2026-09-04T01:30:00Z",
        "end": "2026-09-05T01:30:00Z",
        "index": "Hp30",
    }

    retrieval = provenance["retrieval"]
    assert len(retrieval) == 1
    assert retrieval[0]["byte_count"] > 0 and len(retrieval[0]["sha256"]) == 64
    assert retrieval[0]["request_parameters"]["index"] == "Hp30"
    serialized = json.dumps(provenance)
    assert "0.333" not in serialized  # no payload values travel in provenance


def test_read_series_serves_what_the_adapter_wrote(tmp_path: Path):
    adapter, candidates, _recorder = discovered()
    result = adapter.fetch(candidates[0], WINDOW, tmp_path)
    store = ZipStore([(artifact("gfz-hp30", "hp30"), result.artifacts[0].payload_path)])

    series = store.read_series("gfz-hp30", "hp30")
    assert series is not None
    values = series.variables["hp30_index"].values
    assert values[0] == pytest.approx(0.333)
    assert values[8] is None  # the gap stays a gap through the reader too
    assert len(values) == 10


# --- current Kp and Hp60 experimental dispositions -----------------------


@pytest.mark.parametrize(
    ("adapter_type", "fixture_name", "index", "logical_name", "field", "expected", "status_declared"),
    [
        (GFZKpAdapter, "gfz_kp.json", "Kp", "kp", "kp_index", 1.667, True),
        (GFZHp60Adapter, "gfz_hp60.json", "Hp60", "hp60", "hp60_index", 1.0, False),
    ],
)
def test_current_product_value_unit_time_and_source_round_trip(
    tmp_path: Path,
    adapter_type,
    fixture_name: str,
    index: str,
    logical_name: str,
    field: str,
    expected: float,
    status_declared: bool,
):
    body = json.loads((FIXTURE.parent / fixture_name).read_text(encoding="utf-8"))
    client, recorder = make_client(body)
    adapter = adapter_type(client=client)
    candidate = adapter.discover(WINDOW)[0]
    query = {key: value[0] for key, value in parse_qs(urlparse(recorder.urls[0]).query).items()}
    assert query["index"] == index
    assert candidate.detail["receipt"].request_parameters == query

    result = adapter.fetch(candidate, WINDOW, tmp_path)
    store = ZipStore([(artifact(adapter.source_id, logical_name), result.artifacts[0].payload_path)])
    series = store.read_series(adapter.source_id, logical_name)
    assert series is not None
    assert series.source_id == adapter.source_id
    assert series.times[-1] == datetime(2026, 9, 5, 0, 0, tzinfo=UTC)
    assert series.variables[field].units == "dimensionless"
    assert series.variables[field].values[-1] == pytest.approx(expected)
    provenance = result.artifacts[0].provenance
    assert provenance["status_declared"] is status_declared
    assert provenance["retrieval"][0]["request_parameters"]["index"] == index
    if index == "Kp":
        assert series.variables["kp_status"].units == "flag"
        assert series.variables["kp_status"].values[-1] == "pre"


def test_current_kp_refuses_missing_or_misaligned_status():
    body = json.loads((FIXTURE.parent / "gfz_kp.json").read_text(encoding="utf-8"))
    body.pop("status")
    client, _ = make_client(body)
    with pytest.raises(AdapterUnavailable, match="schema drift"):
        GFZKpAdapter(client=client).discover(WINDOW)

    body["status"] = ["pre"]
    client, _ = make_client(body)
    with pytest.raises(AdapterUnavailable, match="status array is misaligned"):
        GFZKpAdapter(client=client).discover(WINDOW)


def test_current_products_are_not_scheduler_registered():
    from ingest.registry import registered_adapters

    assert "gfz-kp-current" not in registered_adapters()
    assert "gfz-hp60-current" not in registered_adapters()


# --- live smoke -----------------------------------------------------------


@pytest.mark.live_smoke
@pytest.mark.skipif(os.environ.get("WEATHER_LIVE_SMOKE") != "1", reason="set WEATHER_LIVE_SMOKE=1 to contact GFZ")
def test_live_gfz_hp30_shape_is_pinned(tmp_path: Path):
    """The schema-drift tripwire: run once, and the run is the receipt."""
    adapter = GFZHp30Adapter(client=PoliteClient())
    window = FetchWindow(now=datetime.now(UTC))
    candidate = adapter.discover(window)[0]
    assert candidate.detail["raw"]
    assert candidate.detail["meta"]["license"] == "CC BY 4.0"

    result = adapter.fetch(candidate, window, tmp_path)
    provenance = result.artifacts[0].provenance
    assert result.artifacts[0].logical_name == "hp30"
    assert provenance["measurement_scope"] == "planetary"
    assert provenance["status_declared"] is False
    assert provenance["retrieval"][0]["byte_count"] > 0
