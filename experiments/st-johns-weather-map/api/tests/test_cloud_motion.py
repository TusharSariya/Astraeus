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

import numpy
import pytest
import xarray

pytest.importorskip("cv2")

from ingest.derive.cloud_motion import (
    LOGICAL_NAME,
    VERSION,
    _consistency,
    _dis_flow,
    _segment_tangents,
    _warp_nearest,
    cloud_motion_cycle,
    derive_cloud_motion,
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


def surface_artifact(tmp_path: Path, *, frames: int = 3, variable: str = "total_cloud") -> tuple[CurrentArtifact, Path]:
    base = datetime(2026, 8, 31, 12, tzinfo=UTC)
    stamps = [numpy.datetime64((base + timedelta(hours=step)).replace(tzinfo=None), "ns") for step in range(frames)]
    data = numpy.stack([numpy.roll(blob_field(), 4 * step, axis=1) for step in range(frames)])
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
    assert derived.provenance["base_revision_id"] == "rev-surface-1"
    assert derived.provenance["derivation_version"] == VERSION
    assert "not evidence" in derived.provenance["derivation"]
    quality = derived.provenance["quality"]["per_variable"]["total_cloud"]
    assert quality["pairs"] == 2
    # The flow explains the change far better than persistence would.
    assert quality["mae_full_warp_percent"][0] < quality["mae_persistence_percent"][0]

    import zarr

    zip_store = zarr.storage.ZipStore(str(derived.payload_path), mode="r")
    try:
        stored = xarray.open_zarr(zip_store, consolidated=False)
        for suffix in ("u01", "v01", "u10", "v10", "confidence", "vs_u", "vs_v", "ve_u", "ve_v"):
            assert f"total_cloud_{suffix}" in stored.data_vars
        # Constant velocity (a 4-cell roll per frame): the Hermite tangents
        # agree with the segment flow, so playback matches linear advection.
        core = blob_field() > 20.0
        assert float(numpy.median(numpy.abs(
            stored["total_cloud_vs_u"].values[0][core] - stored["total_cloud_u01"].values[0][core]
        ))) < 1.0
        assert stored.sizes["pair"] == 2
        assert stored.attrs["derivation_version"] == VERSION
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
