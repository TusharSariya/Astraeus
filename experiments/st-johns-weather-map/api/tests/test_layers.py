"""Run attribution and run staleness on `/layers`.

Two facts travel with every frame and they are not the same fact. Frame
staleness asks whether the instant on the screen is near a published frame; run
staleness asks whether the run that produced that frame is still current. A
day-ten frame from a thirty-hour-old six-hourly run sits comfortably inside its
six-hour tolerance and is still evidence from a run superseded twice.

`run_stale` never withholds a frame. A stale run that is the only evidence is
still the only evidence, and hiding it would answer the instant with nothing.

No PostgreSQL, no numpy, no network here: the store is a fake shaped like
``ingest.store.RetainedArtifact``, the layer time axes are handed in as
``LayerCoverage``, and the proxied layers are stubbed out.
"""

from __future__ import annotations

import sys as _sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from weather_api.app import (
    FIXTURE_RUN_REASON,
    LIVE_PROXY_RUN_REASON,
    MIN_STALENESS_TOLERANCE_SECONDS,
    NO_RUN_CONCEPT_REASON,
    NO_RUN_TIME_REASON,
    PREFIX,
    RUNS_UNREADABLE_REASON,
    UNKNOWN_CADENCE_TOLERANCE_SECONDS,
    app,
    staleness_tolerance_seconds,
)
from weather_api.models import Layer
from weather_api.store import LayerCoverage, StoreUnavailable, run_stale_verdict

api_module = _sys.modules["weather_api.app"]
client = TestClient(app)

#: A six-hourly forecast source with a registry record, so the cadence behind
#: every verdict below is declared rather than invented here.
FORECAST_SOURCE = "noaa-gfs"
LOGICAL = "surface"
LAYER_ID = "noaa-gfs-surface"
SIX_HOURS = 21600

REFERENCE = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)


@dataclass(frozen=True)
class Retained:
    """A retained revision, shaped as ``ingest.store.RetainedArtifact``.

    ``retrieval_run_time`` is the ``model_runs`` column - the retrieval-time
    fallback - and is deliberately unlike the adapter's declared run time, so a
    test that confused the two would fail.
    """

    source_id: str
    provider_run_id: str
    provenance: dict[str, Any]
    logical_name: str = LOGICAL
    revision_id: str = "rev"
    state: str = "published"
    valid_time_start: datetime | None = None
    valid_time_end: datetime | None = None
    published_at: datetime | None = None
    retrieval_run_time: datetime | None = None


@dataclass
class Current:
    """A current artifact, as ``/layers`` reads one."""

    source_id: str = FORECAST_SOURCE
    logical_name: str = LOGICAL
    media_type: str = "application/zarr+zip"
    provenance: dict[str, Any] = field(default_factory=dict)
    revision_id: str = "rev"


def run_of(run_time, *, first_lead=0, last_lead=24, step_hours=6, declare_run_time=True, source_id=FORECAST_SOURCE, logical_name=LOGICAL):
    """One retained run publishing a span of frames from its own run time."""
    stamps = [run_time + timedelta(hours=lead) for lead in range(first_lead, last_lead + 1, step_hours)]
    provenance: dict[str, Any] = {"valid_times": [stamp.isoformat() for stamp in stamps]}
    if declare_run_time:
        provenance["run_time"] = run_time.isoformat()
    return Retained(
        source_id=source_id,
        provider_run_id=f"{source_id}:{run_time.isoformat()}",
        logical_name=logical_name,
        provenance=provenance,
        revision_id=f"rev-{run_time.isoformat()}",
        # Never a run-time claim, and different from the declaration above.
        retrieval_run_time=run_time + timedelta(hours=5),
    )


def iso(moment: datetime) -> str:
    """The instant as the API serialises it, so a comparison is not a format test."""
    return moment.isoformat().replace("+00:00", "Z")


def frames_of(runs):
    """The union of every frame the given runs published, in order."""
    stamps: set[datetime] = set()
    for run in runs:
        stamps.update(datetime.fromisoformat(value) for value in run.provenance["valid_times"])
    return sorted(stamps)


class FakeStore:
    """A reachable store holding exactly the runs it is given."""

    skipped: list[Any] = []
    unmodelled: list[Any] = []

    def __init__(self, runs, *, cadence_seconds=SIX_HOURS, gridded=True, raise_retained=None):
        self._runs = list(runs)
        self._cadence = cadence_seconds
        self._gridded = gridded
        self._raise_retained = raise_retained

    def current(self):
        pairs = {(run.source_id, run.logical_name) for run in self._runs}
        return [Current(source_id=source_id, logical_name=logical_name) for source_id, logical_name in sorted(pairs)]

    def retained_artifacts(self):
        if self._raise_retained is not None:
            raise self._raise_retained
        return list(self._runs)

    def published_layer_times(self):
        """The current revision's own time axis, per layer.

        Only the newest run's frames: that is what the published artifact for
        the layer carries, and it is exactly what makes the short-cycle case
        interesting - the previous run's further leads have to come from the
        retained revisions instead.
        """
        newest: dict[tuple[str, str], Any] = {}
        for run in self._runs:
            key = (run.source_id, run.logical_name)
            held = newest.get(key)
            if held is None or run.provider_run_id > held.provider_run_id:
                newest[key] = run
        coverage = {}
        for (source_id, logical_name), run in newest.items():
            identifier = f"{source_id}-{logical_name}"
            coverage[identifier] = LayerCoverage(
                layer_id=identifier,
                source_id=source_id,
                logical_name=logical_name,
                times=frames_of([run]),
                cadence_seconds=self._cadence,
                sites=[(47.5, -52.7), (47.6, -52.8)],
                gridded=self._gridded,
            )
        return coverage


@pytest.fixture(autouse=True)
def quiet_surroundings(monkeypatch):
    """Everything `/layers` assembles beside the published index, stubbed off.

    The proxied layers reach the network, and the rendered grids, cloud mask and
    aurora oval each open a stored artifact. None of them is under test here;
    what is under test is run attribution, which is applied to whatever the
    index holds.
    """
    monkeypatch.setattr(api_module, "_proxied_forecast_layers", lambda: ([], []))
    monkeypatch.setattr(api_module.grids, "rendered_grid_layers", lambda *a, **k: ([], []))
    monkeypatch.setattr(api_module.goes_satellite, "satellite_layers", lambda *a, **k: ([], []))
    monkeypatch.setattr(api_module.aurora, "aurora_layers", lambda *a, **k: ([], []))
    monkeypatch.setattr(api_module, "last_valid_times", lambda store: {})
    monkeypatch.setattr(api_module, "now", lambda: REFERENCE)


def layers_from(monkeypatch, data_mode, store) -> dict[str, dict[str, Any]]:
    data_mode("live")
    monkeypatch.setattr(api_module, "live_store", lambda: store)
    payload = client.get(f"{PREFIX}/layers").json()
    return {layer["id"]: layer for layer in payload["layers"]}, payload


# --- the rule itself ------------------------------------------------------

def test_run_stale_is_more_than_twice_the_declared_cadence():
    """Twice the cadence: one missed run is a delay, two is a stopped source."""
    run_time = REFERENCE - timedelta(hours=12)
    age, stale, reason = run_stale_verdict(run_time, SIX_HOURS, REFERENCE)
    assert (age, stale, reason) == (12 * 3600, False, None)

    # Exactly twice is not yet stale; the rule is strictly greater.
    assert run_stale_verdict(REFERENCE - timedelta(hours=12, seconds=1), SIX_HOURS, REFERENCE)[1] is True
    assert run_stale_verdict(REFERENCE - timedelta(hours=30), SIX_HOURS, REFERENCE)[1] is True


def test_run_stale_is_null_and_never_false_where_a_half_is_unknown():
    """False would report an unmeasurable run as current, which is a claim."""
    _age, stale, reason = run_stale_verdict(None, SIX_HOURS, REFERENCE)
    assert stale is None and reason == NO_RUN_TIME_REASON

    _age, stale, reason = run_stale_verdict(REFERENCE - timedelta(hours=30), None, REFERENCE)
    assert stale is None and reason


# --- the thirty-hour-old six-hourly run -----------------------------------

def test_a_far_frame_from_a_thirty_hour_old_six_hourly_run_is_run_stale(monkeypatch, data_mode):
    """The case the two facts exist to keep apart.

    Every frame here sits inside the layer's own six-hour tolerance, and the run
    behind them has been superseded twice. The layer says so on the run, on the
    run summary and on every frame.
    """
    run_time = REFERENCE - timedelta(hours=30)
    store = FakeStore([run_of(run_time, last_lead=240)])

    layers, _payload = layers_from(monkeypatch, data_mode, store)
    layer = layers[LAYER_ID]

    assert layer["run_time"] == iso(run_time)
    assert layer["run_stale"] is True
    assert layer["run_stale_reason"] is None
    assert layer["run_cadence_seconds"] == SIX_HOURS
    assert [entry["run_stale"] for entry in layer["frames"]] == [True] * len(layer["times"])
    assert layer["runs"] == [
        {
            "provider_run_id": f"{FORECAST_SOURCE}:{run_time.isoformat()}",
            "run_time": iso(run_time),
            "run_stale": True,
            "frame_count": len(layer["times"]),
        }
    ]


def test_a_run_inside_twice_its_cadence_is_not_run_stale(monkeypatch, data_mode):
    run_time = REFERENCE - timedelta(hours=6)
    store = FakeStore([run_of(run_time, last_lead=240)])

    layers, _payload = layers_from(monkeypatch, data_mode, store)

    assert layers[LAYER_ID]["run_stale"] is False
    assert all(entry["run_stale"] is False for entry in layers[LAYER_ID]["frames"])


# --- a run-stale frame is still served ------------------------------------

def test_a_run_stale_frame_is_still_served_and_still_renderable(monkeypatch, data_mode):
    """`run_stale` is a flag on the frame and never a reason to hide it.

    The frame list is unchanged by the verdict, the layer is still offered, and
    `raster_available` - which is what `/layers/{id}/raster` and `/features`
    answer from - is untouched by staleness.
    """
    run_time = REFERENCE - timedelta(hours=30)
    run = run_of(run_time, last_lead=240)
    store = FakeStore([run])

    layers, _payload = layers_from(monkeypatch, data_mode, store)
    layer = layers[LAYER_ID]

    published = [iso(stamp) for stamp in frames_of([run])]
    assert layer["times"] == published
    assert [entry["valid_time"] for entry in layer["frames"]] == published
    assert layer["run_stale"] is True
    # Nothing about the run's age removed a frame or the layer itself.
    assert len(layer["frames"]) == len(published) > 0


# --- two runs in one index (the short cycle) -------------------------------

def test_two_runs_in_one_index_each_carry_their_own_run_time_and_run_stale(monkeypatch, data_mode):
    """A short newest run keeps the previous run for the leads it lacks.

    The index shows both runs rather than one merged axis: `times` is the union,
    each frame names the run that produced it, and the overlap is credited to
    the newer evidence. Nothing is blended and nothing is extrapolated past
    either run.
    """
    previous = REFERENCE - timedelta(hours=12)
    newest = REFERENCE - timedelta(hours=6)
    long_run = run_of(previous, last_lead=48)
    short_run = run_of(newest, last_lead=12)
    store = FakeStore([long_run, short_run])

    layers, _payload = layers_from(monkeypatch, data_mode, store)
    layer = layers[LAYER_ID]

    assert layer["times"] == [iso(stamp) for stamp in frames_of([long_run, short_run])]

    by_run: dict[str, list[str]] = {}
    for entry in layer["frames"]:
        by_run.setdefault(str(entry["provider_run_id"]), []).append(entry["valid_time"])
    assert set(by_run) == {long_run.provider_run_id, short_run.provider_run_id}

    # The newer run answers for every instant it reaches; the previous run keeps
    # exactly the instants the newer one does not, and nothing they share.
    assert by_run[short_run.provider_run_id] == [iso(stamp) for stamp in frames_of([short_run])]
    assert by_run[long_run.provider_run_id] == [
        iso(stamp) for stamp in frames_of([long_run]) if stamp not in set(frames_of([short_run]))
    ]
    # Nothing is extrapolated past either run: the far end of the index is the
    # far end of the run that reached it.
    assert max(by_run[long_run.provider_run_id]) == iso(max(frames_of([long_run])))

    # Two runs, shown as two, newest first, with their own run times and counts.
    assert [entry["provider_run_id"] for entry in layer["runs"]] == [short_run.provider_run_id, long_run.provider_run_id]
    assert [entry["run_time"] for entry in layer["runs"]] == [iso(newest), iso(previous)]
    assert sum(entry["frame_count"] for entry in layer["runs"]) == len(layer["times"])
    # Every frame carries its own run time, so no client can read one curve.
    assert {entry["run_time"] for entry in layer["frames"]} == {iso(newest), iso(previous)}


def test_the_layer_run_stale_verdict_is_the_newest_runs_when_two_stand_behind_it(monkeypatch, data_mode):
    """The layer-level run is the newest one, and its verdict is that run's."""
    previous = REFERENCE - timedelta(hours=30)
    newest = REFERENCE - timedelta(hours=6)
    store = FakeStore([run_of(previous, last_lead=240), run_of(newest, last_lead=12)])

    layers, _payload = layers_from(monkeypatch, data_mode, store)
    layer = layers[LAYER_ID]

    assert layer["run_time"] == iso(newest)
    assert layer["run_stale"] is False
    # The retained previous run is still stale, and still served.
    stale_frames = [entry for entry in layer["frames"] if entry["run_time"] == iso(previous)]
    assert stale_frames and all(entry["run_stale"] is True for entry in stale_frames)


# --- the null cases -------------------------------------------------------

def test_a_run_that_declares_no_run_time_is_run_stale_null_with_the_reason(monkeypatch, data_mode):
    """The retrieval stamp beside the run is never promoted into a run time."""
    run_time = REFERENCE - timedelta(hours=30)
    store = FakeStore([run_of(run_time, last_lead=48, declare_run_time=False)])

    layers, _payload = layers_from(monkeypatch, data_mode, store)
    layer = layers[LAYER_ID]

    assert layer["run_time"] is None
    assert layer["run_stale"] is None
    assert layer["run_stale_reason"] == NO_RUN_TIME_REASON
    assert all(entry["run_time"] is None and entry["run_stale"] is None for entry in layer["frames"])
    # The frames are served all the same; only the attribution is unknown.
    assert layer["times"]


def test_an_observation_layer_carries_run_stale_null_with_no_run_concept(monkeypatch, data_mode):
    """An observation record has no run, which is not a staleness claim."""
    run_time = REFERENCE - timedelta(hours=30)
    store = FakeStore(
        [run_of(run_time, last_lead=0, source_id="eccc-radar", logical_name="radar")],
        cadence_seconds=360,
        gridded=True,
    )

    layers, _payload = layers_from(monkeypatch, data_mode, store)
    layer = layers["eccc-radar-radar"]

    assert layer["run_stale"] is None
    assert layer["run_stale_reason"] == NO_RUN_CONCEPT_REASON
    assert layer["run_cadence_seconds"] is None
    assert all(entry["run_stale"] is None for entry in layer["frames"])


def test_a_live_proxied_layer_is_run_stale_null_with_its_own_reason(monkeypatch, data_mode):
    """Nothing is retained here for a layer rendered upstream on demand."""
    proxied = Layer(
        id="geomet-proxy-cloud",
        title="proxied cloud",
        kind="raster",
        field="cloud",
        product="GDPS",
        units="percent",
        semantics="live-proxied",
        times=[REFERENCE, REFERENCE + timedelta(hours=1)],
        cadence_seconds=3600,
        staleness_tolerance_seconds=3600,
        evidence_basis="live_proxy",
        group="forecast_proxy",
    )
    monkeypatch.setattr(api_module, "_proxied_forecast_layers", lambda: ([proxied], []))
    store = FakeStore([run_of(REFERENCE - timedelta(hours=6))])

    layers, _payload = layers_from(monkeypatch, data_mode, store)
    layer = layers["geomet-proxy-cloud"]

    assert layer["run_stale"] is None
    assert layer["run_stale_reason"] == LIVE_PROXY_RUN_REASON
    assert [entry["valid_time"] for entry in layer["frames"]] == [iso(stamp) for stamp in proxied.times]
    assert all(entry["provider_run_id"] is None for entry in layer["frames"])


def test_an_unreadable_retention_record_costs_run_stale_and_not_the_frames(monkeypatch, data_mode):
    """Unknown retention is not empty retention, and never withholds a frame."""
    store = FakeStore([run_of(REFERENCE - timedelta(hours=6), last_lead=48)], raise_retained=StoreUnavailable("no connection"))

    layers, payload = layers_from(monkeypatch, data_mode, store)
    layer = layers[LAYER_ID]

    assert layer["run_stale"] is None
    assert layer["run_stale_reason"] == RUNS_UNREADABLE_REASON
    assert layer["runs"] == []
    assert layer["times"], "the layer's own published frames are still offered"
    assert [entry["valid_time"] for entry in layer["frames"]] == layer["times"]
    assert any(RUNS_UNREADABLE_REASON in notice for notice in payload["notices"])


def test_a_fixture_layer_claims_no_run_stale_verdict(data_mode):
    """Fixtures name products; no run stands behind one and none is invented."""
    data_mode("fixture")
    payload = client.get(f"{PREFIX}/layers").json()

    assert payload["data_mode"] == "fixture"
    for layer in payload["layers"]:
        assert layer["run_stale"] is None
        assert layer["run_stale_reason"] == FIXTURE_RUN_REASON
        assert [entry["valid_time"] for entry in layer["frames"]] == layer["times"]


# --- the shape itself -----------------------------------------------------

def test_run_stale_frames_are_one_per_published_time_in_the_same_order(monkeypatch, data_mode):
    """The list is positional, so a client can zip it against ``times``."""
    store = FakeStore([run_of(REFERENCE - timedelta(hours=12), last_lead=48), run_of(REFERENCE - timedelta(hours=6), last_lead=12)])

    layers, _payload = layers_from(monkeypatch, data_mode, store)
    for layer in layers.values():
        assert [entry["valid_time"] for entry in layer["frames"]] == layer["times"]


# --- staleness tolerance: one native interval -----------------------------

def test_tolerance_is_one_native_interval_for_a_six_minute_radar_layer(monkeypatch, data_mode):
    """Six minutes, not the three a half-cadence rule gave it.

    Radar's own resolution is six minutes; inside that there is a sweep that
    genuinely belongs to the requested instant, and refusing it quietly was the
    half-cadence rule answering a question about run currency with a number
    about frame proximity.
    """
    store = FakeStore([run_of(REFERENCE - timedelta(hours=6), source_id="eccc-radar", logical_name="radar")], cadence_seconds=360)

    layers, _payload = layers_from(monkeypatch, data_mode, store)

    assert layers["eccc-radar-radar"]["cadence_seconds"] == 360
    assert layers["eccc-radar-radar"]["staleness_tolerance_seconds"] == 360


def test_tolerance_is_one_native_interval_for_an_hourly_model_layer(monkeypatch, data_mode):
    """An hourly model frame tolerates an hour."""
    store = FakeStore([run_of(REFERENCE - timedelta(hours=6), step_hours=1, last_lead=6)], cadence_seconds=3600)

    layers, _payload = layers_from(monkeypatch, data_mode, store)

    assert layers[LAYER_ID]["cadence_seconds"] == 3600
    assert layers[LAYER_ID]["staleness_tolerance_seconds"] == 3600


def test_tolerance_of_a_three_hourly_planning_layer_resolves_a_hundred_minute_frame_quietly(monkeypatch, data_mode):
    """Three hours, so a frame 100 minutes away is drawn without a fallback note.

    Under half a cadence the same frame sat outside a ninety-minute tolerance
    and had to be disclosed as a fallback, which misreported a planning step
    doing exactly what its own resolution says it does.
    """
    run_time = REFERENCE - timedelta(hours=6)
    store = FakeStore([run_of(run_time, step_hours=3, last_lead=24)], cadence_seconds=10800)

    layers, _payload = layers_from(monkeypatch, data_mode, store)
    layer = layers[LAYER_ID]

    assert layer["cadence_seconds"] == 10800
    tolerance = layer["staleness_tolerance_seconds"]
    assert tolerance == 10800

    published = [datetime.fromisoformat(stamp.replace("Z", "+00:00")) for stamp in layer["times"]]
    asked = published[2] + timedelta(minutes=100)
    nearest = min(published, key=lambda stamp: abs((stamp - asked).total_seconds()))
    distance = abs((nearest - asked).total_seconds())
    assert distance <= tolerance, "a 100-minute offset resolves quietly inside a three-hour interval"


def test_tolerance_falls_back_to_the_bounded_unknown_cadence_value(monkeypatch, data_mode):
    """An underivable cadence still gets a bound, so one frame cannot answer for the window."""
    store = FakeStore([run_of(REFERENCE - timedelta(hours=6))], cadence_seconds=None)

    layers, _payload = layers_from(monkeypatch, data_mode, store)
    layer = layers[LAYER_ID]

    assert layer["cadence_seconds"] is None
    assert layer["staleness_tolerance_seconds"] == UNKNOWN_CADENCE_TOLERANCE_SECONDS == 900


def test_tolerance_of_a_live_proxied_layer_follows_the_same_one_interval_rule(monkeypatch, data_mode):
    """A layer rendered upstream is bounded by its own interval like any other."""
    proxied = Layer(
        id="geomet-proxy-cloud",
        title="proxied cloud",
        kind="raster",
        field="cloud",
        product="GDPS",
        units="percent",
        semantics="live-proxied",
        times=[REFERENCE, REFERENCE + timedelta(hours=1)],
        cadence_seconds=3600,
        staleness_tolerance_seconds=staleness_tolerance_seconds(3600),
        evidence_basis="live_proxy",
        group="forecast_proxy",
    )
    monkeypatch.setattr(api_module, "_proxied_forecast_layers", lambda: ([proxied], []))
    store = FakeStore([run_of(REFERENCE - timedelta(hours=6))])

    layers, _payload = layers_from(monkeypatch, data_mode, store)

    assert layers["geomet-proxy-cloud"]["staleness_tolerance_seconds"] == 3600
    # Nothing about run attribution changed with the number.
    assert layers["geomet-proxy-cloud"]["run_stale_reason"] == LIVE_PROXY_RUN_REASON


def test_tolerance_floor_keeps_a_very_fast_layer_resolvable():
    """A sub-minute cadence still gets the 60 s floor, not its own tiny interval."""
    assert staleness_tolerance_seconds(30) == MIN_STALENESS_TOLERANCE_SECONDS == 60
    assert staleness_tolerance_seconds(0) == UNKNOWN_CADENCE_TOLERANCE_SECONDS
