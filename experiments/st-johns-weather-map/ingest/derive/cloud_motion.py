"""Cloud-motion fields between adjacent published cloud frames.

For each cloud variable of a published surface grid, dense optical flow is
computed between every pair of adjacent frames (OpenCV DIS - the estimator
radar nowcasting standardised on) in both directions, with a
forward-backward consistency score. The web client uses these fields for
**display-time advection-corrected interpolation** (Anagnostou & Krajewski;
the pySTEPS advection-correction construction): warp both real frames toward
each other along the motion field and cross-dissolve. The scheme is
endpoint-exact - at the two real instants the real frames show untouched -
and where the flow is zero or unconfident it degrades to a plain crossfade.

Evidence rules (owner carve-out 2026-08-31): this artifact is a display
derivation. It is published with its method, version and base revision in
provenance, it never feeds ``/point``, ``/timeline`` or any reading, and a
pair whose flow cannot be computed is simply absent - the client then
crossfades, disclosed as such.
"""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from ingest.contract import Artifact, MEDIA_ZARR, RunResult
from ingest.grib import write_zarr
from ingest.store import sha256_of

UTC = timezone.utc

#: Cloud variables worth motion fields, per source. Only the rendered-grid
#: cloud layers consume them; nothing else is derived.
CLOUD_MOTION_SOURCES: dict[str, tuple[str, ...]] = {
    "noaa-gfs": ("cloud_low", "cloud_middle", "cloud_high", "total_cloud"),
    "eccc-hrdps": ("total_cloud",),
    "eccc-rdps": ("total_cloud",),
}

LOGICAL_NAME = "cloud_motion"
METHOD = (
    "dense optical flow between adjacent published frames: OpenCV DIS (medium preset) on the "
    "Gaussian-presmoothed percent field, forward and backward, with a forward-backward "
    "consistency score per cell; per-knot velocities by QVI central difference of the two "
    "adjacent pairs' flows (one-sided at the sequence ends), stored as cubic Hermite segment "
    "tangents so displayed velocity is C1 across every real frame"
)
VERSION = "cloud-motion-hermite-v2"
#: Forward-backward disagreement (grid cells) at which confidence reaches 0.
CONSISTENCY_LIMIT_CELLS = 2.0
#: Tangent deviation from the segment flow is clamped to this fraction of the
#: flow magnitude (plus a one-cell absolute floor), so a Hermite arc cannot
#: overshoot far between endpoints when a real acceleration is large.
TANGENT_DEVIATION_FRACTION = 0.5
TANGENT_DEVIATION_FLOOR_CELLS = 1.0


def _dis_flow(previous: Any, following: Any) -> Any:
    """DIS flow from ``previous`` to ``following``; (rows, cols, 2) as (dx, dy) cells."""
    import cv2  # noqa: PLC0415
    import numpy  # noqa: PLC0415

    def prepared(field: Any) -> Any:
        filled = numpy.nan_to_num(numpy.asarray(field, dtype="float64"), nan=0.0)
        scaled = numpy.clip(filled, 0.0, 100.0) * 2.55
        blurred = cv2.GaussianBlur(scaled.astype("float32"), (0, 0), 1.0)
        return numpy.clip(numpy.rint(blurred), 0, 255).astype("uint8")

    dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
    return dis.calc(prepared(previous), prepared(following), None)


def _warp_nearest(field: Any, flow: Any) -> Any:
    """``field`` advected by the full flow, nearest-cell, clamped at edges."""
    import numpy  # noqa: PLC0415

    rows, cols = field.shape
    row_index, col_index = numpy.mgrid[0:rows, 0:cols]
    source_rows = numpy.clip(numpy.rint(row_index - flow[..., 1]).astype("int64"), 0, rows - 1)
    source_cols = numpy.clip(numpy.rint(col_index - flow[..., 0]).astype("int64"), 0, cols - 1)
    return field[source_rows, source_cols]


def _consistency(flow01: Any, flow10: Any) -> Any:
    """1 where the two directions agree, falling to 0 at the disagreement limit."""
    import numpy  # noqa: PLC0415

    rows, cols = flow01.shape[:2]
    row_index, col_index = numpy.mgrid[0:rows, 0:cols]
    target_rows = numpy.clip(numpy.rint(row_index + flow01[..., 1]).astype("int64"), 0, rows - 1)
    target_cols = numpy.clip(numpy.rint(col_index + flow01[..., 0]).astype("int64"), 0, cols - 1)
    returned = flow10[target_rows, target_cols]
    error = numpy.hypot(flow01[..., 0] + returned[..., 0], flow01[..., 1] + returned[..., 1])
    return numpy.clip(1.0 - error / CONSISTENCY_LIMIT_CELLS, 0.0, 1.0).astype("float32")


def _clamped_tangent(velocity: Any, flow: Any) -> Any:
    """``velocity`` pulled toward ``flow`` so its deviation stays bounded.

    The knot velocity is a central-difference estimate from two different
    pairs; where it disagrees wildly with the segment's own displacement the
    Hermite arc would bow far outside the endpoints. Deviation is limited to
    a fraction of the flow magnitude plus a one-cell floor (Fritsch-Carlson
    in spirit). The clamp is per segment, against that segment's own flow:
    where it bites, the two segments sharing the knot each relax toward
    their own linear model - boundedness is bought with a small, bounded
    velocity step, never with an overshooting arc.
    """
    import numpy  # noqa: PLC0415

    deviation = velocity - flow
    magnitude = numpy.hypot(deviation[..., 0], deviation[..., 1])
    cap = numpy.maximum(
        TANGENT_DEVIATION_FRACTION * numpy.hypot(flow[..., 0], flow[..., 1]),
        TANGENT_DEVIATION_FLOOR_CELLS,
    )
    scale = numpy.where(magnitude > cap, cap / numpy.maximum(magnitude, 1e-9), 1.0)
    return flow + deviation * scale[..., None]


def _segment_tangents(flow01: list[Any], flow10: list[Any], confidence: list[Any]) -> list[tuple[Any, Any]]:
    """Per segment, the (start, end) Hermite tangents, anchored per knot.

    Knot k's velocity is the QVI central difference of the two flows anchored
    at frame k: v_k = 1/2 (F_{k->k+1} - F_{k->k-1}), where F_{k->k+1} is pair
    k's forward flow and F_{k->k-1} is pair k-1's backward flow. The sequence
    ends are one-sided (v = the segment's own flow). Where the knot's
    forward-backward consistency is low the velocity relaxes continuously to
    the segment flow, so a distrusted knot renders exactly as the linear
    advection already approved. Velocity is exactly continuous at fully
    trusted, unclamped knots; a distrusted or clamped knot trades that for a
    bounded step toward each segment's own linear model.
    """
    import numpy  # noqa: PLC0415

    pairs = len(flow01)
    segments: list[tuple[Any, Any]] = []
    for index in range(pairs):
        forward = flow01[index]
        # Start knot = frame `index`: central difference needs pair index-1.
        if index == 0:
            start = forward
        else:
            knot = 0.5 * (flow01[index] - flow10[index - 1])
            trust = numpy.minimum(confidence[index], confidence[index - 1])[..., None]
            start = forward + trust * (knot - forward)
        # End knot = frame `index + 1`: central difference needs pair index+1.
        if index + 1 >= pairs:
            end = forward
        else:
            knot = 0.5 * (flow01[index + 1] - flow10[index])
            trust = numpy.minimum(confidence[index], confidence[index + 1])[..., None]
            end = forward + trust * (knot - forward)
        segments.append((_clamped_tangent(start, forward), _clamped_tangent(end, forward)))
    return segments


def _open_zarr_zip(path: Path) -> Any:
    import xarray  # noqa: PLC0415
    import zarr  # noqa: PLC0415

    store = zarr.storage.ZipStore(str(path), mode="r")
    return xarray.open_zarr(store, consolidated=False)


def _frame_stack(dataset: Any, variable: str) -> tuple[list[Any], list[Any]] | None:
    """Sorted (times, 2-D frames) for one variable, or None when unusable."""
    import numpy  # noqa: PLC0415
    import pandas  # noqa: PLC0415

    if variable not in dataset.data_vars:
        return None
    time_name = next((name for name in ("valid_time", "time") if name in dataset[variable].dims), None)
    if time_name is None:
        return None
    data = dataset[variable]
    spatial = [dim for dim in data.dims if dim != time_name]
    if len(spatial) != 2:
        return None
    stamps = [pandas.Timestamp(value).to_pydatetime().replace(tzinfo=UTC) for value in dataset[time_name].values]
    order = numpy.argsort(numpy.asarray([stamp.timestamp() for stamp in stamps]))
    times = [stamps[int(position)] for position in order]
    frames = [numpy.asarray(data.isel({time_name: int(position)}).values, dtype="float64") for position in order]
    return times, frames


def derive_cloud_motion(store: Any, surface: Any, variables: Iterable[str], workdir: Path) -> RunResult | None:
    """One motion artifact for one published surface artifact, or None.

    Reads the surface artifact back from the object store (digest-verified),
    computes per-variable per-pair flow, and returns the RunResult to stage.
    ``None`` means nothing usable (no variable, fewer than two frames, or
    every pair degenerate) - and nothing is published in that case.
    """
    import numpy  # noqa: PLC0415
    import xarray  # noqa: PLC0415

    local = workdir / "surface.zarr.zip"
    store.s3.download_file(store.config.bucket, surface.object_key, str(local))
    expected = str(surface.provenance.get("sha256", ""))
    if expected and sha256_of(local) != expected:
        raise RuntimeError(f"{surface.source_id}: surface artifact bytes do not match their recorded digest")
    dataset = _open_zarr_zip(local)

    data_vars: dict[str, Any] = {}
    quality: dict[str, Any] = {}
    pair_from: list[datetime] = []
    pair_to: list[datetime] = []
    for variable in variables:
        stack = _frame_stack(dataset, variable)
        if stack is None:
            continue
        times, frames = stack
        if len(frames) < 2:
            continue
        pairs = list(zip(times, times[1:], frames, frames[1:]))
        if not pair_from:
            pair_from = [start for start, _, _, _ in pairs]
            pair_to = [end for _, end, _, _ in pairs]
        elif [start for start, _, _, _ in pairs] != pair_from:
            # Variables of one artifact share a time axis; one that does not is
            # refused rather than filed under the wrong pair instants.
            continue
        u01 = numpy.zeros((len(pairs),) + frames[0].shape, dtype="float32")
        v01 = numpy.zeros_like(u01)
        u10 = numpy.zeros_like(u01)
        v10 = numpy.zeros_like(u01)
        confidence = numpy.zeros_like(u01)
        forward_flows: list[Any] = []
        backward_flows: list[Any] = []
        confidences: list[Any] = []
        mae_warp: list[float] = []
        mae_persistence: list[float] = []
        for index, (_, _, previous, following) in enumerate(pairs):
            flow01 = _dis_flow(previous, following)
            flow10 = _dis_flow(following, previous)
            u01[index] = flow01[..., 0]
            v01[index] = flow01[..., 1]
            u10[index] = flow10[..., 0]
            v10[index] = flow10[..., 1]
            confidence[index] = _consistency(flow01, flow10)
            forward_flows.append(flow01.astype("float64"))
            backward_flows.append(flow10.astype("float64"))
            confidences.append(confidence[index].astype("float64"))
            filled_previous = numpy.nan_to_num(previous, nan=0.0)
            filled_following = numpy.nan_to_num(following, nan=0.0)
            mae_warp.append(float(numpy.mean(numpy.abs(_warp_nearest(filled_previous, flow01) - filled_following))))
            mae_persistence.append(float(numpy.mean(numpy.abs(filled_previous - filled_following))))
        tangents = _segment_tangents(forward_flows, backward_flows, confidences)
        vs_u = numpy.stack([start[..., 0] for start, _ in tangents]).astype("float32")
        vs_v = numpy.stack([start[..., 1] for start, _ in tangents]).astype("float32")
        ve_u = numpy.stack([end[..., 0] for _, end in tangents]).astype("float32")
        ve_v = numpy.stack([end[..., 1] for _, end in tangents]).astype("float32")
        attrs = {"units": "grid cells per frame interval", "consistency_limit_cells": CONSISTENCY_LIMIT_CELLS}
        data_vars[f"{variable}_u01"] = (("pair", "y", "x"), u01, attrs)
        data_vars[f"{variable}_v01"] = (("pair", "y", "x"), v01, attrs)
        data_vars[f"{variable}_u10"] = (("pair", "y", "x"), u10, attrs)
        data_vars[f"{variable}_v10"] = (("pair", "y", "x"), v10, attrs)
        data_vars[f"{variable}_confidence"] = (("pair", "y", "x"), confidence, {"units": "1"})
        tangent_attrs = {**attrs, "role": "cubic Hermite segment tangent (QVI central-difference knot velocity)"}
        data_vars[f"{variable}_vs_u"] = (("pair", "y", "x"), vs_u, tangent_attrs)
        data_vars[f"{variable}_vs_v"] = (("pair", "y", "x"), vs_v, tangent_attrs)
        data_vars[f"{variable}_ve_u"] = (("pair", "y", "x"), ve_u, tangent_attrs)
        data_vars[f"{variable}_ve_v"] = (("pair", "y", "x"), ve_v, tangent_attrs)
        quality[variable] = {
            "pairs": len(pairs),
            "mae_full_warp_percent": mae_warp,
            "mae_persistence_percent": mae_persistence,
        }

    if not data_vars:
        return None

    derived = xarray.Dataset(
        data_vars,
        coords={
            "pair_from": ("pair", numpy.array([stamp.replace(tzinfo=None) for stamp in pair_from], dtype="datetime64[ns]")),
            "pair_to": ("pair", numpy.array([stamp.replace(tzinfo=None) for stamp in pair_to], dtype="datetime64[ns]")),
        },
        attrs={"method": METHOD, "derivation_version": VERSION, "base_revision_id": str(surface.revision_id)},
    )
    path = workdir / f"{surface.source_id}-cloud-motion.zarr.zip"
    write_zarr(derived, path)

    provenance = {
        "source_id": surface.source_id,
        "product": f"{surface.provenance.get('product', surface.source_id)} cloud motion (derived, display only)",
        "derived": True,
        "derivation": (
            "display-time interpolation support: " + METHOD + ". Derived here from the published "
            "surface artifact; not provider output, not evidence, never served on a data path."
        ),
        "derivation_version": VERSION,
        "base_revision_id": str(surface.revision_id),
        "base_object_key": surface.object_key,
        "quality": {"status": "derived", "per_variable": quality},
    }
    return RunResult(
        source_id=surface.source_id,
        provider_run_id=f"{surface.provider_run_id}+cloud-motion",
        run_time=surface.run_time,
        retrieved_at=datetime.now(UTC),
        complete=True,
        qc_passed=True,
        artifacts=[Artifact(LOGICAL_NAME, MEDIA_ZARR, path, provenance)],
        native_crs=surface.native_crs,
        notes=f"cloud motion derived from surface revision {surface.revision_id}",
    )


def cloud_motion_cycle(store: Any) -> list[str]:
    """Derive missing/stale motion artifacts. Never raises; returns log lines."""
    lines: list[str] = []
    try:
        current = {(item.source_id, item.logical_name): item for item in store.current_artifacts()}
    except Exception as error:
        return [f"cloud-motion: current artifacts unreadable - {error!r}"]
    for source_id, variables in CLOUD_MOTION_SOURCES.items():
        surface = current.get((source_id, "surface"))
        if surface is None:
            continue
        existing = current.get((source_id, LOGICAL_NAME))
        if (
            existing is not None
            and str(existing.provenance.get("base_revision_id", "")) == str(surface.revision_id)
            # A version bump re-derives even for an unchanged surface: an
            # artifact from an older construction never lingers as current.
            and str(existing.provenance.get("derivation_version", "")) == VERSION
        ):
            continue
        try:
            with tempfile.TemporaryDirectory(prefix=f"{source_id}-cloud-motion-") as workdir:
                result = derive_cloud_motion(store, surface, variables, Path(workdir))
                if result is None:
                    lines.append(f"cloud-motion {source_id}: nothing derivable (no cloud variable with two frames)")
                    continue
                store.stage_and_publish(result)
            lines.append(f"cloud-motion {source_id}: published for surface revision {surface.revision_id}")
        except Exception as error:
            lines.append(f"cloud-motion {source_id}: derive failed - {error!r}")
    return lines
