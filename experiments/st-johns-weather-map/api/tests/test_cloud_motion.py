"""Derived cloud-motion artifacts: flow recovery, consistency, fail-closed.

The motion fields exist only for display-time advection-corrected
interpolation. What is pinned here: DIS recovers a known translation; the
consistency score is high where the two directions agree; the derive step
publishes with full derivation provenance; anything unusable publishes
NOTHING (the client then crossfades - absence is the disclosed fallback).
"""

from __future__ import annotations

import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy
import pytest
import xarray

pytest.importorskip("cv2")

from ingest.derive.methods import (
    METHODS,
    BaselineMethod,
    MethodContext,
    generated_display_enabled,
    method_by_id,
    method_catalogue,
)
from ingest.derive.methods.residual_advection import RESIDUAL_GAIN
from ingest.derive.cloud_motion import (
    CLOUD_MOTION_SOURCES,
    DEFAULT_METHOD_ID,
    LOGICAL_NAME,
    MIN_HELD_OUT_IMPROVEMENT,
    VERSION,
    enabled_methods,
    _consistency,
    _dis_flow,
    _interpolation_skill,
    _prior_corrected,
    _segment_tangents,
    _supported_flow,
    _warp_nearest,
    cloud_motion_cycle,
    derive_cloud_motion,
    motion_logical_name,
)
from ingest.grib import write_zarr
from ingest.store import CurrentArtifact, sha256_of

UTC = timezone.utc


def blob_field(rows: int = 96, cols: int = 96, *, centre=(48, 48), sigma: float = 9.0) -> numpy.ndarray:
    row_index, col_index = numpy.mgrid[0:rows, 0:cols]
    distance2 = (row_index - centre[0]) ** 2 + (col_index - centre[1]) ** 2
    return 100.0 * numpy.exp(-distance2 / (2 * sigma**2))


def test_dis_recovers_a_known_translation():
    previous = blob_field()
    following = numpy.roll(numpy.roll(previous, 3, axis=0), 5, axis=1)  # +3 rows, +5 cols
    flow = _dis_flow(previous, following)
    core = blob_field() > 20.0
    assert float(numpy.median(flow[..., 0][core])) == pytest.approx(5.0, abs=1.0)
    assert float(numpy.median(flow[..., 1][core])) == pytest.approx(3.0, abs=1.0)


def test_zero_flow_warp_is_the_identity():
    field = blob_field()
    unchanged = _warp_nearest(field, numpy.zeros(field.shape + (2,), dtype="float32"))
    assert numpy.array_equal(unchanged, field)


def test_consistency_is_high_where_directions_agree():
    previous = blob_field()
    following = numpy.roll(previous, 4, axis=1)
    flow01 = _dis_flow(previous, following)
    flow10 = _dis_flow(following, previous)
    core = blob_field() > 20.0
    confidence = _consistency(flow01, flow10)
    assert float(numpy.median(confidence[core])) > 0.6


def test_consistency_is_judged_relative_to_the_distance_claimed():
    # The same two-cell round-trip error against a fifteen-cell displacement
    # and against a stationary cell. An absolute tolerance scored both zero,
    # which is what sent three quarters of the map down the crossfade path
    # while advection was still beating persistence there.
    def round_trip_error(dx: float, error: float) -> float:
        forward = uniform_flow(dx, 0.0, shape=(32, 32))
        backward = uniform_flow(-dx + error, 0.0, shape=(32, 32))
        return float(numpy.median(_consistency(forward, backward)))

    assert round_trip_error(15.0, 2.0) > 0.5  # fast cell, small relative miss: trusted
    assert round_trip_error(0.0, 2.0) == 0.0  # stationary cell, same miss: not trusted
    # A perfect round trip is fully trusted whatever the speed.
    assert round_trip_error(15.0, 0.0) == pytest.approx(1.0)


def test_an_untrusted_hole_inherits_the_motion_around_it():
    flow = uniform_flow(4.0, 1.0, shape=(24, 24))
    confidence = numpy.ones((24, 24))
    confidence[10:14, 10:14] = 0.0  # a patch DIS could not verify
    filled, support = _supported_flow(flow, confidence)
    # The hole keeps moving with its neighbourhood instead of standing still.
    assert float(numpy.median(filled[11:13, 11:13, 0])) == pytest.approx(4.0, abs=0.3)
    assert float(numpy.median(support[11:13, 11:13])) > 0.5
    # Trusted cells are untouched.
    assert numpy.allclose(filled[0:5, 0:5], flow[0:5, 0:5])


def test_a_wholly_untrusted_field_keeps_the_crossfade_fallback():
    flow = uniform_flow(4.0, 1.0, shape=(24, 24))
    _, support = _supported_flow(flow, numpy.zeros((24, 24)))
    # Nothing stood behind any fill: the display weight stays at zero and the
    # client crossfades, which is the disclosed fallback.
    assert float(support.max()) < 0.01


def uniform_flow(dx: float, dy: float, shape=(8, 8)) -> numpy.ndarray:
    flow = numpy.zeros(shape + (2,), dtype="float64")
    flow[..., 0] = dx
    flow[..., 1] = dy
    return flow


def test_tangents_share_the_knot_velocity_under_acceleration():
    # Displacements 2 then 4 cells: the interior knot's central-difference
    # velocity is 3 - segment 0 ends and segment 1 starts at the SAME
    # velocity, which is exactly the C1 property that removes the snap.
    forward = [uniform_flow(2, 0), uniform_flow(4, 0)]
    backward = [uniform_flow(-2, 0), uniform_flow(-4, 0)]
    trust = [numpy.ones((8, 8)), numpy.ones((8, 8))]
    segments = _segment_tangents(forward, backward, trust)
    (start0, end0), (start1, end1) = segments
    assert numpy.allclose(start0[..., 0], 2.0)  # one-sided at the sequence start
    assert numpy.allclose(end0[..., 0], 3.0)
    assert numpy.allclose(start1[..., 0], 3.0)  # shared with the previous segment
    assert numpy.allclose(end1[..., 0], 4.0)  # one-sided at the sequence end


def test_distrusted_knots_collapse_to_the_segment_flow():
    forward = [uniform_flow(2, 0), uniform_flow(4, 0)]
    backward = [uniform_flow(-2, 0), uniform_flow(-4, 0)]
    distrust = [numpy.zeros((8, 8)), numpy.zeros((8, 8))]
    segments = _segment_tangents(forward, backward, distrust)
    for (start, end), flow in zip(segments, forward):
        # v = F everywhere: the cubic collapses exactly to linear advection.
        assert numpy.allclose(start, flow)
        assert numpy.allclose(end, flow)


def test_a_wild_knot_estimate_is_clamped_near_the_segment_flow():
    # The neighbouring pair claims a huge reversal; the tangent must stay
    # within half the flow magnitude (plus the one-cell floor) of the flow,
    # so a bad flow cannot bow the Hermite arc far outside the endpoints.
    forward = [uniform_flow(2, 0), uniform_flow(-40, 0)]
    backward = [uniform_flow(-2, 0), uniform_flow(40, 0)]
    trust = [numpy.ones((8, 8)), numpy.ones((8, 8))]
    (start0, end0), _ = _segment_tangents(forward, backward, trust)
    deviation = numpy.hypot(end0[..., 0] - 2.0, end0[..., 1])
    assert float(deviation.max()) <= max(0.5 * 2.0, 1.0) + 1e-9


def test_the_steering_prior_reaches_only_cells_the_imagery_left_unsupported():
    # Imagery says 4 cells east and is trusted; the model wind says 12 cells
    # north. Where the imagery is trusted the flow is untouched - the prior
    # never overrides what was actually observed to move.
    flow = uniform_flow(4.0, 0.0, shape=(24, 24))
    prior = uniform_flow(0.0, 12.0, shape=(24, 24))
    corrected, carried = _prior_corrected(flow, numpy.ones((24, 24)), prior)
    assert numpy.allclose(corrected, flow, atol=1e-6)
    assert carried == pytest.approx(0.0, abs=1e-6)


def test_a_stationary_field_refuses_the_steering_wind():
    # The Avalon's own failure mode: cloud forming and dissipating in place
    # while wind blows through it. A trusted image flow reporting no motion
    # must not be overwritten by the model's wind, however strong.
    still = uniform_flow(0.0, 0.0, shape=(24, 24))
    blowing = uniform_flow(10.0, 0.0, shape=(24, 24))
    corrected, carried = _prior_corrected(still, numpy.ones((24, 24)), blowing)
    assert numpy.allclose(corrected, still, atol=1e-6)
    assert carried == pytest.approx(0.0, abs=1e-6)
    # Nor does distrusting the stillness let the wind in on its own: with no
    # trusted image flow anywhere, nothing corroborates the model, and an
    # uncorroborated wind is not evidence about cells the imagery could not
    # read. The display falls back to the crossfade instead.
    unfilled, weight = _prior_corrected(still, numpy.zeros((24, 24)), blowing)
    assert numpy.allclose(unfilled, still, atol=1e-6)
    assert weight == pytest.approx(0.0, abs=1e-6)

    # What does let it in: a field whose trusted part moves the way the model
    # says, with holes the imagery could not read.
    observed = uniform_flow(10.0, 0.0, shape=(24, 24))
    support = numpy.ones((24, 24))
    support[8:16, 8:16] = 0.0
    corrected, carried = _prior_corrected(observed * numpy.where(support[..., None] > 0, 1.0, 0.0), support, blowing)
    assert float(corrected[10:14, 10:14, 0].min()) > 1.0  # the hole now moves
    assert carried > 0.0


def test_an_uncorroborated_steering_wind_barely_reaches_the_field():
    # The prior is weighted by how well it agrees with the flow that IS
    # trusted. A wind pointing the opposite way to the observed motion is not
    # evidence about the unobserved cells either.
    flow = uniform_flow(6.0, 0.0, shape=(24, 24))
    support = numpy.full((24, 24), 0.5)
    agreeing, agreeing_weight = _prior_corrected(flow, support, uniform_flow(6.0, 0.0, shape=(24, 24)))
    opposing, opposing_weight = _prior_corrected(flow, support, uniform_flow(-6.0, 0.0, shape=(24, 24)))
    assert opposing_weight < agreeing_weight
    assert float(numpy.abs(opposing[..., 0] - flow[..., 0]).max()) < 6.0


def test_leave_one_out_beats_a_crossfade_on_a_moving_field():
    # Frames 0 and 2 are interpolated to the midpoint and checked against the
    # real frame 1 that was held out. On a field that genuinely moves, the
    # construction must predict the held-out frame better than a dissolve of
    # its neighbours does - this is the number that says "believable".
    frames = [blob_field(64, 64, centre=(32, 16 + 8 * step)) for step in range(3)]
    skill = _interpolation_skill(frames)
    assert skill is not None
    assert skill["held_out_frames"] == 1
    assert skill["midpoint_mae_percent"] < skill["midpoint_crossfade_mae_percent"]
    assert skill["improvement_over_crossfade"] > 0.1
    # And it beats the same construction with the motion reversed, which is
    # the test that the DIRECTION carries information rather than the blend
    # simply being smoother than a dissolve.
    assert skill["improvement_over_reversed_flow"] > 0.1


def test_leave_one_out_is_absent_not_zero_when_nothing_can_be_held_out():
    assert _interpolation_skill([blob_field(), blob_field()]) is None


class FakeStore:
    """Just enough of ArtifactStore for the derive path."""

    class config:  # noqa: D106 - namespace only
        bucket = "weather-artifacts"

    def __init__(self, payloads: dict[str, Path], artifacts: list[CurrentArtifact]) -> None:
        self._payloads = payloads
        self._artifacts = artifacts
        self.published: list = []

        outer = self

        class S3:
            def download_file(self, bucket: str, key: str, destination: str) -> None:
                shutil.copyfile(outer._payloads[key], destination)

        self.s3 = S3()

    def current_artifacts(self):
        return list(self._artifacts)

    def stage_and_publish(self, result):
        self.published.append(result)
        return []


def surface_artifact(
    tmp_path: Path, *, frames: int = 3, variable: str = "total_cloud", data: numpy.ndarray | None = None
) -> tuple[CurrentArtifact, Path]:
    base = datetime(2026, 8, 31, 12, tzinfo=UTC)
    if data is None:
        data = numpy.stack([numpy.roll(blob_field(), 4 * step, axis=1) for step in range(frames)])
    frames = int(data.shape[0])
    stamps = [numpy.datetime64((base + timedelta(hours=step)).replace(tzinfo=None), "ns") for step in range(frames)]
    dataset = xarray.Dataset(
        {variable: (("valid_time", "y", "x"), data, {"units": "percent"})},
        coords={"valid_time": stamps},
    )
    payload = tmp_path / "surface.zarr.zip"
    write_zarr(dataset, payload)
    artifact = CurrentArtifact(
        source_id="eccc-hrdps",
        logical_name="surface",
        revision_id="rev-surface-1",
        object_key="published/eccc-hrdps/surface",
        media_type="application/zarr+zip",
        byte_size=payload.stat().st_size,
        provenance={"product": "ECCC-HRDPS", "sha256": sha256_of(payload)},
        published_at=base,
        run_time=base,
        retrieved_at=base,
        provider_run_id="2026083112",
        native_crs="EPSG:4326",
    )
    return artifact, payload


def test_derive_publishes_flow_with_full_derivation_provenance(tmp_path: Path):
    artifact, payload = surface_artifact(tmp_path)
    store = FakeStore({artifact.object_key: payload}, [artifact])
    workdir = tmp_path / "derive"
    workdir.mkdir()
    result = derive_cloud_motion(store, artifact, ("total_cloud",), workdir)
    assert result is not None
    assert result.provider_run_id == "2026083112+cloud-motion"
    derived = result.artifacts[0]
    assert derived.logical_name == LOGICAL_NAME
    assert derived.provenance["derived"] is True
    # A display construction says so in the declaration a data path reads,
    # which is what keeps it off /point now that admission is by class.
    assert derived.provenance["evidence_classes"] == ["generated_display"]
    assert derived.provenance["base_revision_id"] == "rev-surface-1"
    assert derived.provenance["derivation_version"] == VERSION
    assert "not evidence" in derived.provenance["derivation"]
    quality = derived.provenance["quality"]["per_variable"]["total_cloud"]
    assert quality["pairs"] == 2
    # The flow explains the change far better than persistence would.
    assert quality["mae_full_warp_percent"][0] < quality["mae_persistence_percent"][0]
    # A steadily translating field must actually be advected on screen: the
    # display weight, not just the flow, is what the reader sees.
    assert quality["advect_weight_median"] > 0.5
    assert quality["advect_weight_above_half_fraction"] > 0.5
    assert quality["leave_one_out"]["improvement_over_reversed_flow"] > MIN_HELD_OUT_IMPROVEMENT

    import zarr

    zip_store = zarr.storage.ZipStore(str(derived.payload_path), mode="r")
    try:
        stored = xarray.open_zarr(zip_store, consolidated=False)
        for suffix in ("u01", "v01", "u10", "v10", "confidence", "advect_weight", "vs_u", "vs_v", "ve_u", "ve_v"):
            assert f"total_cloud_{suffix}" in stored.data_vars
        # Every enabled method is published, on its own axis, and the default
        # is first so a reader that ignores the axis still gets the baseline.
        published = [str(value) for value in stored["method"].values]
        assert published == [method.id for method in enabled_methods()]
        assert published[0] == DEFAULT_METHOD_ID
        baseline = stored.isel(method=published.index(DEFAULT_METHOD_ID))
        # Constant velocity (a 4-cell roll per frame): the Hermite tangents
        # agree with the segment flow, so playback matches linear advection.
        core = blob_field() > 20.0
        assert float(numpy.median(numpy.abs(
            baseline["total_cloud_vs_u"].values[0][core] - baseline["total_cloud_u01"].values[0][core]
        ))) < 1.0
        assert stored.sizes["pair"] == 2
        assert stored.attrs["derivation_version"] == VERSION
    finally:
        zip_store.close()


def test_motion_that_fails_the_held_out_test_is_vetoed_to_a_crossfade(tmp_path: Path):
    # Three unrelated fields: no motion field can explain the change, so
    # interpolating across a held-out frame cannot beat a plain dissolve of
    # its neighbours. Every pair's display weight goes to zero and the client
    # crossfades, disclosed, rather than dragging pixels around convincingly.
    # (The per-pair warp-vs-persistence floor does not catch this on its own:
    # DIS minimises exactly that quantity, so it can always find a warp that
    # lowers it, even between two fields with nothing in common.)
    base = datetime(2026, 8, 31, 12, tzinfo=UTC)
    generator = numpy.random.default_rng(11)
    data = numpy.stack([generator.uniform(0.0, 100.0, (96, 96)) for _ in range(3)])
    stamps = [numpy.datetime64((base + timedelta(hours=step)).replace(tzinfo=None), "ns") for step in range(3)]
    dataset = xarray.Dataset(
        {"total_cloud": (("valid_time", "y", "x"), data, {"units": "percent"})},
        coords={"valid_time": stamps},
    )
    payload = tmp_path / "noise.zarr.zip"
    write_zarr(dataset, payload)
    artifact, _ = surface_artifact(tmp_path)
    noisy = CurrentArtifact(**{**artifact.__dict__, "provenance": {**artifact.provenance, "sha256": sha256_of(payload)}})
    store = FakeStore({noisy.object_key: payload}, [noisy])
    workdir = tmp_path / "derive"
    workdir.mkdir()
    result = derive_cloud_motion(store, noisy, ("total_cloud",), workdir)
    assert result is not None

    import zarr

    zip_store = zarr.storage.ZipStore(str(result.artifacts[0].payload_path), mode="r")
    try:
        stored = xarray.open_zarr(zip_store, consolidated=False)
        assert float(stored["total_cloud_advect_weight"].values.max()) == 0.0
    finally:
        zip_store.close()


def test_a_single_frame_derives_nothing(tmp_path: Path):
    artifact, payload = surface_artifact(tmp_path, frames=1)
    store = FakeStore({artifact.object_key: payload}, [artifact])
    workdir = tmp_path / "derive"
    workdir.mkdir()
    assert derive_cloud_motion(store, artifact, ("total_cloud",), workdir) is None


def test_a_wrong_digest_refuses_to_derive(tmp_path: Path):
    artifact, payload = surface_artifact(tmp_path)
    tampered = CurrentArtifact(**{**artifact.__dict__, "provenance": {**artifact.provenance, "sha256": "0" * 64}})
    store = FakeStore({artifact.object_key: payload}, [tampered])
    workdir = tmp_path / "derive"
    workdir.mkdir()
    with pytest.raises(RuntimeError, match="digest"):
        derive_cloud_motion(store, tampered, ("total_cloud",), workdir)


def motion_row(artifact, provenance: dict) -> CurrentArtifact:
    return CurrentArtifact(
        source_id="eccc-hrdps",
        logical_name=LOGICAL_NAME,
        revision_id="rev-motion-1",
        object_key="published/eccc-hrdps/cloud_motion",
        media_type="application/zarr+zip",
        byte_size=1,
        provenance=provenance,
        published_at=artifact.published_at,
        run_time=artifact.run_time,
        retrieved_at=artifact.retrieved_at,
        provider_run_id="2026083112+cloud-motion",
        native_crs="EPSG:4326",
    )


def test_cycle_skips_an_up_to_date_motion_artifact(tmp_path: Path):
    artifact, payload = surface_artifact(tmp_path)
    motion = motion_row(artifact, {"base_revision_id": "rev-surface-1", "derivation_version": VERSION})
    store = FakeStore({artifact.object_key: payload}, [artifact, motion])
    lines = cloud_motion_cycle(store)
    assert store.published == []
    assert lines == []


def test_cycle_rederives_when_the_construction_version_moved_on(tmp_path: Path):
    # Same surface revision, but the current artifact came from an older
    # derivation: the version bump re-derives so old motion never lingers.
    artifact, payload = surface_artifact(tmp_path)
    motion = motion_row(artifact, {"base_revision_id": "rev-surface-1", "derivation_version": "cloud-motion-dis-v1"})
    store = FakeStore({artifact.object_key: payload}, [artifact, motion])
    lines = cloud_motion_cycle(store)
    assert len(store.published) == 1
    assert any("published for surface revision rev-surface-1" in line for line in lines)


def test_cycle_derives_when_the_surface_moved_on(tmp_path: Path):
    artifact, payload = surface_artifact(tmp_path)
    store = FakeStore({artifact.object_key: payload}, [artifact])
    lines = cloud_motion_cycle(store)
    assert len(store.published) == 1
    assert any("published for surface revision rev-surface-1" in line for line in lines)


def test_a_vetoed_method_has_its_own_fields_zeroed_not_just_the_advection_weight():
    """The veto must silence a method, not invert it.

    Both vetoes work by zeroing `advect_weight`, which silences anything fenced
    by it. But a method that acts where advection FAILED is naturally fenced by
    `1 - advect_weight`, and for those the same veto is an amplifier: the pair
    the derive just judged unfit to advect gets that method's contribution at
    full strength. `vetoed_suffixes` is what closes that, and this test is here
    because the failure is silent, inverted, and would look like the method
    working unusually hard exactly where it should be quiet.
    """
    from ingest.derive.cloud_motion import _derive_one_method

    class FencedByTheInverse(BaselineMethod):
        id = "test-fenced-by-the-inverse"
        extra_suffixes = ("test_residual",)
        vetoed_suffixes = ("test_residual",)

        def motion(self, context):
            motions = super().motion(context)
            for item in motions:
                item.extra["test_residual"] = numpy.ones_like(item.advect_weight)
            return motions

    # Two frames of independent noise: the warp cannot beat persistence and the
    # held-out reconstruction cannot beat its own reversal, so both vetoes fire.
    generator = numpy.random.default_rng(11)
    frames = [generator.uniform(0.0, 100.0, (32, 32)) for _ in range(4)]
    context = MethodContext(
        variable="total_cloud", frames=frames, indices=(0, 1, 2, 3), interval_seconds=3600.0
    )
    pairs = [(None, None, frames[index], frames[index + 1]) for index in range(3)]
    fields, _ = _derive_one_method(FencedByTheInverse(), context, pairs)

    assert float(numpy.max(fields["advect_weight"])) == 0.0, "the veto did not fire; this test proves nothing"
    assert float(numpy.max(fields["test_residual"])) == 0.0, (
        "a vetoed method's own field survived the veto at full strength: fenced by "
        "1 - advect_weight it now draws hardest on exactly the pairs judged unfit"
    )


# --- H4: one real derive, read back from the published artifact ----------
#
# Not unit tests. Each of these runs `derive_cloud_motion` over a synthetic
# artifact and reads the stored zarr and the published provenance, so what is
# pinned is what a client would actually be served rather than what a method
# object returns in isolation.


def growing_in_place_frames(size: int = 96) -> numpy.ndarray:
    """Three frames: one blob that TRANSLATES, one that forms in place.

    Both halves are load-bearing. The moving blob is what carries the motion
    veto - a field that does not move cannot beat its own reversal, the derive
    zeroes every stored field for the pair, and the envelope would never reach
    the artifact whatever the residual measured. The stationary blob is the one
    regime advection provably cannot express, and it grows FRONT-LOADED (three
    quarters of the change by the held-out middle frame), because a field that
    grew linearly is predicted exactly by the crossfade and the harness would
    correctly refuse the term - the right outcome there, and no use as a
    fixture here.
    """
    row_index, col_index = numpy.mgrid[0:size, 0:size]

    def gaussian(centre, sigma: float):
        return 100.0 * numpy.exp(
            -((row_index - centre[0]) ** 2 + (col_index - centre[1]) ** 2) / (2 * sigma**2)
        )

    return numpy.stack([
        numpy.clip(gaussian((30, 20 + 8 * step), 8.0) + weight * gaussian((68, 64), 12.0), 0.0, 100.0)
        for step, weight in enumerate((0.0, 0.75, 1.0))
    ])


def stored_dataset(derived) -> tuple[Any, Any]:
    import zarr  # noqa: PLC0415

    zip_store = zarr.storage.ZipStore(str(derived.payload_path), mode="r")
    return xarray.open_zarr(zip_store, consolidated=False), zip_store


def test_a_real_derive_publishes_exactly_the_registered_methods_on_the_axis(tmp_path: Path):
    # The `method` axis is a wire contract: the client indexes it by id, and a
    # method that is registered but silently missing from the artifact 404s
    # into the crossfade with no explanation. Pinned against the registry
    # rather than a hard-coded list so adding a method cannot leave the
    # artifact behind - and against the five ids by name so DELETING one
    # cannot pass unnoticed either.
    artifact, payload = surface_artifact(tmp_path)
    store = FakeStore({artifact.object_key: payload}, [artifact])
    workdir = tmp_path / "derive"
    workdir.mkdir()
    result = derive_cloud_motion(store, artifact, ("total_cloud",), workdir)
    assert result is not None
    stored, zip_store = stored_dataset(result.artifacts[0])
    try:
        published = [str(value) for value in stored["method"].values]
        assert published == [method.id for method in enabled_methods()]
        assert published == [
            "baseline",
            "error-variance-blend",
            "residual-advection",
            "residual-generative",
            "height-steering",
            "goes-transfer",
        ]
        assert published[0] == DEFAULT_METHOD_ID
        # Every method's own stored fields exist on every method's slot, so a
        # client reading `gen_a` under `baseline` gets an explicit zero rather
        # than a ragged artifact or another method's numbers.
        for suffix in ("res_s", "gen_a", "gen_b", "vis0", "vis1"):
            assert f"total_cloud_{suffix}" in stored.data_vars
    finally:
        zip_store.close()


def test_the_derive_publishes_a_drawable_envelope_for_residual_advection(tmp_path: Path):
    # The whole of section D in one assertion: on a layer where the residual
    # earns its place, `gen_a` reaches the artifact NON-ZERO, so the shader has
    # something to add and the map draws something the baseline cannot. This
    # test is here because the previous shipped version of this construction
    # stored a field no client branch ever read - it was a menu entry that drew
    # the baseline under another name.
    artifact, payload = surface_artifact(tmp_path, data=growing_in_place_frames())
    store = FakeStore({artifact.object_key: payload}, [artifact])
    workdir = tmp_path / "derive"
    workdir.mkdir()
    result = derive_cloud_motion(store, artifact, ("total_cloud",), workdir)
    assert result is not None
    derived = result.artifacts[0]

    per_method = derived.provenance["quality"]["per_variable"]["total_cloud"]["per_method"]
    options = per_method["residual-advection"]["options"]
    # Whatever the decision, both sides of it are published: the claim is
    # checkable from provenance alone.
    assert options["residual_applied"] is True
    assert options["held_out_improvement_with_residual"] > options["held_out_improvement_without_residual"]
    assert options["residual_admission"]["admitted"] is True
    assert options["residual_admission_against_negated"]["admitted"] is True

    stored, zip_store = stored_dataset(derived)
    try:
        published = [str(value) for value in stored["method"].values]
        mine = stored["total_cloud_gen_a"].values[published.index("residual-advection")]
        theirs = stored["total_cloud_gen_a"].values[published.index(DEFAULT_METHOD_ID)]
        assert float(numpy.abs(mine).max()) > 1.0, (
            "the envelope reached the artifact as zeros: the method is a menu entry that "
            "draws the baseline"
        )
        # gen_b is zero for this non-generative sibling by construction: the
        # envelope is the symmetric 4 g s t(1-t), no timing term.
        assert numpy.allclose(stored["total_cloud_gen_b"].values[published.index("residual-advection")], 0.0)
        # And the algebra of the contract, read off the stored fields rather
        # than asserted about the code: gen_a = 4 * RESIDUAL_GAIN * res_s.
        residual = stored["total_cloud_res_s"].values[published.index("residual-advection")]
        assert numpy.allclose(mine, 4.0 * RESIDUAL_GAIN * residual, atol=1e-4)
        # A method that does not declare the field gets an explicit zero.
        assert numpy.allclose(theirs, 0.0)
    finally:
        zip_store.close()


def test_a_vetoed_pair_reaches_the_client_with_no_envelope_at_all(tmp_path: Path):
    # The inverse-fencing failure, end to end. The envelope is ADDITIVE: it
    # survives `advect_weight = 0` untouched, so a pair the derive just judged
    # unfit to advect would otherwise be handed to the client with the residual
    # at full strength - drawing hardest exactly where the derive said trust
    # nothing. `vetoed_suffixes` is what closes that, and this reads the
    # published artifact rather than the method object to prove it.
    generator = numpy.random.default_rng(11)
    noise = numpy.stack([generator.uniform(0.0, 100.0, (96, 96)) for _ in range(3)])
    artifact, payload = surface_artifact(tmp_path, data=noise)
    store = FakeStore({artifact.object_key: payload}, [artifact])
    workdir = tmp_path / "derive"
    workdir.mkdir()
    result = derive_cloud_motion(store, artifact, ("total_cloud",), workdir)
    assert result is not None

    stored, zip_store = stored_dataset(result.artifacts[0])
    try:
        published = [str(value) for value in stored["method"].values]
        slot = published.index("residual-advection")
        assert float(stored["total_cloud_advect_weight"].values[slot].max()) == 0.0, (
            "the veto did not fire on three unrelated fields; this test proves nothing"
        )
        for suffix in ("res_s", "gen_a", "gen_b"):
            assert float(numpy.abs(stored[f"total_cloud_{suffix}"].values[slot]).max()) == 0.0, (
                f"{suffix} survived the veto: the client draws a generated term on a pair "
                "the derive refused to advect"
            )
    finally:
        zip_store.close()


def test_the_kill_switch_takes_a_generative_method_out_of_the_derive(monkeypatch):
    """The middle of carve-out (d)'s three switches, on the derive side.

    ``WEATHER_GENERATED_DISPLAY=off`` must mean a generative method is not
    derived AT ALL - no slot on the `method` axis, no zeroed field - rather
    than derived and hidden, because a field that exists is a field a client
    can read. A local dummy stands in for the generative sibling so this
    holds the moment that module lands and does not depend on it.
    """
    class Generated(BaselineMethod):
        id = "test-generative"
        generative = True

    monkeypatch.setattr("ingest.derive.methods.METHODS", (*METHODS, Generated()))

    monkeypatch.delenv("WEATHER_GENERATED_DISPLAY", raising=False)
    assert generated_display_enabled() is True
    assert "test-generative" in [method.id for method in enabled_methods()]

    for value in ("off", "OFF", " off ", "0", "false", "no"):
        monkeypatch.setenv("WEATHER_GENERATED_DISPLAY", value)
        assert generated_display_enabled() is False
        published = [method.id for method in enabled_methods()]
        assert "test-generative" not in published
        # And nothing else moves: the switch refuses generated values, it does
        # not disable the bench.
        assert published == [method.id for method in METHODS if method.enabled and not method.generative]
        assert published[0] == DEFAULT_METHOD_ID

    # Anything else - unset, empty, a typo - means enabled, because a
    # construction that is never derived is never measured. The reader's own
    # default-off is enforced in the menu, not here.
    for value in ("", "on", "yes", "true", "maybe"):
        monkeypatch.setenv("WEATHER_GENERATED_DISPLAY", value)
        assert generated_display_enabled() is True
        assert "test-generative" in [method.id for method in enabled_methods()]


# --- the registry as the API and the menu see it -------------------------

def test_the_registry_is_exactly_the_six_shipped_constructions():
    # Acceptance 1, as a test: six methods, baseline first. Six modules were
    # DELETED on 2026-09-01 rather than registered disabled - a construction
    # that measured worse is absent, not switched off - so an id reappearing
    # here means a deletion was reverted, not that a method was re-enabled.
    assert [method.id for method in METHODS] == [
        "baseline",
        "error-variance-blend",
        "residual-advection",
        "residual-generative",
        "height-steering",
        "goes-transfer",
    ]
    assert METHODS[0].id == DEFAULT_METHOD_ID and METHODS[0].enabled
    for retired in (
        "intermediate-flow", "visibility-blend", "scale-cascade",
        "flow-net", "full-advection", "development-residual",
    ):
        assert method_by_id(retired) is None
    # Exactly one shipped method is generative, and it is the one the kill
    # switch governs: `residual-generative` may draw a value in neither frame
    # (carve-out (d)); `residual-advection` stays inside the bracket.
    assert [method.id for method in METHODS if method.generative] == ["residual-generative"]


def test_every_menu_entry_carries_the_reader_copy_the_api_serves():
    # `/methods` serves `plain`, `gap` and `notes` straight from these class
    # attributes, and the menu renders all three. An entry missing any of them
    # renders as a bare title with no way for a reader to tell what it does or
    # what it cannot show - which is the specific failure the plain/gap copy
    # exists to prevent.
    catalogue = {entry["id"]: entry for entry in method_catalogue()}
    assert list(catalogue) == [method.id for method in METHODS]
    for entry in catalogue.values():
        for field in ("plain", "gap", "notes", "title", "summary", "shader"):
            assert entry[field].strip(), f"{entry['id']} has no {field}"
        assert entry["plain"].endswith(".") and entry["gap"].endswith(".")
        # The science note is a citation, not a restatement of the plain copy.
        assert len(entry["notes"]) > len(entry["plain"])
        assert entry["generation_disabled"] is False
        assert isinstance(entry["requirements"], list)
    # The gap sentences that say a method reduces to the default today must
    # keep saying it: the on-map "reduced to the default" note is keyed on the
    # same fact, and the two disagreeing is a lie to the reader.
    assert "draw exactly entry 1" in catalogue["height-steering"]["gap"]
    assert "draws exactly entry 1" in catalogue["goes-transfer"]["gap"]
    # Every note carries the "not the same quantity" warning about TCDC, so a
    # reader comparing HRDPS and GFS cloud is told they are different fields.
    for entry in catalogue.values():
        assert "Not the same quantity" in entry["notes"]


def test_the_catalogue_marks_a_generative_entry_disabled_by_the_deployment(monkeypatch):
    # What `/methods` has to say when the kill switch is off: the method is
    # still registered - the menu can name it and say why it is unavailable -
    # but this deployment derives and offers nothing from it.
    class Generated(BaselineMethod):
        id = "test-generative"
        generative = True

    monkeypatch.setattr("ingest.derive.methods.METHODS", (*METHODS, Generated()))
    monkeypatch.setenv("WEATHER_GENERATED_DISPLAY", "off")
    catalogue = {entry["id"]: entry for entry in method_catalogue()}
    assert catalogue["test-generative"]["generation_disabled"] is True
    assert catalogue["baseline"]["generation_disabled"] is False


def test_the_display_weight_is_support_and_nothing_else():
    # Section B's absorption of `full-advection`: the weight is the support
    # gate alone. The development-agreement factor that used to multiply it
    # measured worse on every layer and is gone, so a cell with a trustworthy
    # vector behind it advects at FULL strength however imperfectly the two
    # half-warps agree - which is what stopped the map looking like a
    # cross-dissolve everywhere but the flat interiors.
    from ingest.derive.flow_ops import SUPPORT_FLOOR, _display_weight

    assert float(_display_weight(numpy.array([[1.0]]))[0, 0]) == 1.0
    assert float(_display_weight(numpy.array([[SUPPORT_FLOOR]]))[0, 0]) == pytest.approx(1.0)
    assert float(_display_weight(numpy.array([[0.0]]))[0, 0]) == 0.0
    assert float(_display_weight(numpy.array([[SUPPORT_FLOOR / 2]]))[0, 0]) == pytest.approx(0.5)
    # One argument. A signature that still took the two frames would mean the
    # photometric term could come back without anyone noticing.
    import inspect

    assert list(inspect.signature(_display_weight).parameters) == ["support"]


# --- one motion artifact per (source, artifact), not per source ----------
#
# A source now publishes more than one grid with cloud frames in it: the
# retrieved `surface` grid, and the derived `low_cloud_weong` layer. Each
# needs its own motion, because the WEonG layer's cloud is a different field
# from the provider's and a displacement fitted to one picture is not a
# displacement of the other.


def test_the_motion_source_table_is_keyed_by_source_and_artifact():
    assert ("eccc-hrdps", "surface") in CLOUD_MOTION_SOURCES
    assert CLOUD_MOTION_SOURCES[("eccc-hrdps", "low_cloud_weong")] == ("total_cloud_weong",)
    assert CLOUD_MOTION_SOURCES[("eccc-rdps", "low_cloud_weong")] == ("total_cloud_weong",)
    # GFS has no WEonG layer: the RH->LLC table is an ECCC calibration and the
    # derive refuses GFS humidity out loud rather than mis-applying it.
    assert not any(source == "noaa-gfs" and base != "surface" for source, base in CLOUD_MOTION_SOURCES)


def test_the_surface_motion_name_is_unchanged_and_a_derived_one_is_suffixed():
    """Backwards compatibility is the point of the first half of this.

    Every motion artifact ever published, and every client that reads one,
    calls the surface layer's motion `cloud_motion`. Renaming it would 404 the
    whole map into a crossfade on the first deploy.
    """
    assert motion_logical_name("surface") == LOGICAL_NAME == "cloud_motion"
    assert motion_logical_name("low_cloud_weong") == "cloud_motion_low_cloud_weong"


def weong_layer_artifact(tmp_path: Path) -> tuple[CurrentArtifact, Path]:
    """A published WEonG layer, shaped like what `weong_layer` writes."""
    base, payload = surface_artifact(
        tmp_path / "weong", variable="total_cloud_weong", data=growing_in_place_frames()
    )
    return CurrentArtifact(**{
        **base.__dict__,
        "logical_name": "low_cloud_weong",
        "revision_id": "rev-weong-1",
        "object_key": "published/eccc-hrdps/low_cloud_weong",
        "provider_run_id": "2026083112+low-cloud-weong",
    }), payload


def test_the_cycle_derives_motion_for_the_derived_layer_under_its_own_name(tmp_path: Path):
    (tmp_path / "weong").mkdir()
    surface, surface_payload = surface_artifact(tmp_path)
    weong, weong_payload = weong_layer_artifact(tmp_path)
    store = FakeStore(
        {surface.object_key: surface_payload, weong.object_key: weong_payload},
        [surface, weong],
    )
    lines = cloud_motion_cycle(store)
    assert len(store.published) == 2, lines

    by_name = {result.artifacts[0].logical_name: result for result in store.published}
    assert set(by_name) == {"cloud_motion", "cloud_motion_low_cloud_weong"}
    derived = by_name["cloud_motion_low_cloud_weong"]
    # It derives from the WEonG layer's OWN revision, so /flow's revision
    # check compares the right two things and a stale surface cannot make a
    # fresh derived layer look stale.
    assert derived.artifacts[0].provenance["base_revision_id"] == "rev-weong-1"
    assert derived.artifacts[0].provenance["base_object_key"] == weong.object_key
    quality = derived.artifacts[0].provenance["quality"]["per_variable"]
    # Motion for the derived variable, and only for it: the retrieved
    # `total_cloud` is not in this artifact's table.
    assert set(quality) == {"total_cloud_weong"}
    assert quality["total_cloud_weong"]["methods"] == [method.id for method in enabled_methods()]

    # And the surface artifact's motion is untouched by any of it.
    assert by_name["cloud_motion"].artifacts[0].provenance["base_revision_id"] == "rev-surface-1"


def test_an_absent_derived_layer_costs_nothing_and_says_nothing(tmp_path: Path):
    """The kill switch, seen from the motion pass.

    `WEATHER_GENERATED_DISPLAY=off` means `weong_cycle` publishes no layer, so
    there is no `low_cloud_weong` artifact for this pass to find. That is the
    ordinary state, not a failure, so it produces no line - the noise would be
    indistinguishable from a real derive failure on every cycle of every
    deployment that has the switch off.
    """
    surface, payload = surface_artifact(tmp_path)
    store = FakeStore({surface.object_key: payload}, [surface])
    lines = cloud_motion_cycle(store)
    assert len(store.published) == 1
    assert store.published[0].artifacts[0].logical_name == "cloud_motion"
    assert not any("low_cloud_weong" in line for line in lines)
