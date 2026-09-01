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
from ingest.derive.flow_ops import (  # noqa: F401 - re-exported for tests and methods
    FB_TOLERANCE_FLOOR_CELLS,
    FB_TOLERANCE_FRACTION,
    MIN_HELD_OUT_IMPROVEMENT,
    STEERING_LEVEL_BY_VARIABLE,
    _consistency,
    _development_agreement,
    _dis_flow,
    _display_weight,
    _midpoint_composite,
    _prior_corrected,
    _segment_tangents,
    _ssim,
    _steering_prior,
    _supported_flow,
    _warp_nearest,
)
from ingest.derive.methods import (  # noqa: F401 - re-exported for tests
    DEFAULT_METHOD_ID,
    MethodContext,
    PairMotion,
    _interpolation_skill,
    enabled_methods,
    method_catalogue,
)
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
    "consistency score per cell judged relative to the distance the flow claims; cells the "
    "round trip fails inherit the confidence-weighted flow of their trusted neighbourhood "
    "(normalized convolution), with the local trusted density kept as support; per-knot "
    "velocities by QVI central difference of the two adjacent pairs' flows (one-sided at the "
    "sequence ends), stored as cubic Hermite segment tangents so displayed velocity is C1 "
    "across every real frame; the display weight between advection and a plain crossfade is the "
    "photometric agreement of the two half-interval warps, gated by that support, so cloud that "
    "grew or decayed in place dissolves rather than being dragged; a variable whose held-out "
    "midpoint reconstruction does not beat the same construction with the motion reversed is "
    "published with a zero weight and crossfades everywhere; where the model publishes the "
    "stratum's steering wind (850/700/500 hPa) that wind may fill cells the imagery leaves "
    "unsupported, weighted by its agreement with the trusted image flow, never where a "
    "well-supported image flow reports the field standing still, and only for a variable whose "
    "held-out reconstruction the prior measurably improves"
)
VERSION = "cloud-motion-bench-v5"


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


#: Stored-field documentation, by suffix. Every method publishes the first
#: six; a method's own ``extra_suffixes`` document themselves.
_FLOW_ATTRS = {
    "units": "grid cells per frame interval",
    "fb_tolerance_fraction": FB_TOLERANCE_FRACTION,
    "fb_tolerance_floor_cells": FB_TOLERANCE_FLOOR_CELLS,
}
_FIELD_ATTRS = {
    "confidence": {"units": "1", "role": "forward-backward agreement of the raw flow, relative to its own magnitude"},
    "advect_weight": {
        "units": "1",
        "role": "display weight: 1 advects, 0 crossfades; zero where the pair's warp does not beat persistence or the variable fails its held-out control",
    },
    # A weight is not a displacement, so these never inherit the flow
    # attributes' "grid cells per frame interval".
    "vis0": {"units": "1", "role": "per-pixel reliability of the frame-0 warp at the midpoint (visibility-blend)"},
    "vis1": {"units": "1", "role": "per-pixel reliability of the frame-1 warp at the midpoint (visibility-blend)"},
    "dev_shape": {
        "units": "1",
        "role": (
            "signed re-timing of the dissolve in [-1, 1] from the model run's own vertical "
            "velocity: positive delivers the change between the two retrieved frames earlier in "
            "the interval, negative later. The shaped mixing fraction stays in [0, 1], so the "
            "displayed value stays between the two retrieved frames at that cell"
        ),
    },
    "vs_u": {**_FLOW_ATTRS, "role": "cubic Hermite segment tangent (QVI central-difference knot velocity)"},
    "vs_v": {**_FLOW_ATTRS, "role": "cubic Hermite segment tangent (QVI central-difference knot velocity)"},
    "ve_u": {**_FLOW_ATTRS, "role": "cubic Hermite segment tangent (QVI central-difference knot velocity)"},
    "ve_v": {**_FLOW_ATTRS, "role": "cubic Hermite segment tangent (QVI central-difference knot velocity)"},
}


def _derive_one_method(
    method: Any, context: MethodContext, pairs: list[tuple[datetime, datetime, Any, Any]]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """One method's stored fields and quality block for one variable.

    The two vetoes apply to every method equally, because they are about
    whether motion is worth displaying at all rather than about how it was
    derived: a pair whose warp cannot beat persistence, and a variable whose
    held-out reconstruction cannot beat the same construction with its motion
    reversed, are published with a zero display weight and crossfade.
    """
    import numpy  # noqa: PLC0415

    motions = method.motion(context)
    if len(motions) != len(pairs):
        raise RuntimeError(
            f"{method.id}: returned {len(motions)} motion fields for {len(pairs)} frame pairs"
        )
    shape = (len(pairs),) + numpy.asarray(context.frames[0]).shape
    fields = {
        suffix: numpy.zeros(shape, dtype="float32")
        for suffix in ("u01", "v01", "u10", "v10", "confidence", "advect_weight")
    }
    for suffix in getattr(method, "extra_suffixes", ()):
        fields[suffix] = numpy.zeros(shape, dtype="float32")
    mae_warp: list[float] = []
    mae_persistence: list[float] = []
    diagnostics: dict[str, list[float]] = {}
    for index, (motion, (_, _, previous, following)) in enumerate(zip(motions, pairs)):
        fields["u01"][index] = motion.flow01[..., 0]
        fields["v01"][index] = motion.flow01[..., 1]
        fields["u10"][index] = motion.flow10[..., 0]
        fields["v10"][index] = motion.flow10[..., 1]
        fields["confidence"][index] = motion.confidence
        fields["advect_weight"][index] = motion.advect_weight
        for suffix, values in motion.extra.items():
            if suffix in fields:
                fields[suffix][index] = values
        for name, value in motion.diagnostics.items():
            diagnostics.setdefault(name, []).append(float(value))
        filled_previous = numpy.nan_to_num(previous, nan=0.0)
        filled_following = numpy.nan_to_num(following, nan=0.0)
        mae_warp.append(float(numpy.mean(numpy.abs(_warp_nearest(filled_previous, motion.flow01) - filled_following))))
        mae_persistence.append(float(numpy.mean(numpy.abs(filled_previous - filled_following))))
    for index, (warped, persisted) in enumerate(zip(mae_warp, mae_persistence)):
        if warped >= persisted:
            fields["advect_weight"][index] = 0.0
    skill = _interpolation_skill(
        context.frames,
        method=method,
        dataset=context.dataset,
        variable=context.variable,
        interval_seconds=context.interval_seconds,
        indices=context.indices,
    )
    if skill is not None and skill["improvement_over_reversed_flow"] < MIN_HELD_OUT_IMPROVEMENT:
        fields["advect_weight"][:] = 0.0
    tangents = _segment_tangents(
        [motion.flow01 for motion in motions],
        [motion.flow10 for motion in motions],
        [motion.support for motion in motions],
    )
    fields["vs_u"] = numpy.stack([start[..., 0] for start, _ in tangents]).astype("float32")
    fields["vs_v"] = numpy.stack([start[..., 1] for start, _ in tangents]).astype("float32")
    fields["ve_u"] = numpy.stack([end[..., 0] for _, end in tangents]).astype("float32")
    fields["ve_v"] = numpy.stack([end[..., 1] for _, end in tangents]).astype("float32")
    quality = {
        "shader": method.shader,
        "mae_full_warp_percent": mae_warp,
        "mae_persistence_percent": mae_persistence,
        # The distribution the display actually mixes on, so the tolerance
        # constants are chosen from data rather than taste.
        "advect_weight_median": float(numpy.median(fields["advect_weight"])),
        "advect_weight_above_half_fraction": float(numpy.mean(fields["advect_weight"] > 0.5)),
        "confidence_median": float(numpy.median(fields["confidence"])),
        "leave_one_out": skill,
    }
    for name, values in diagnostics.items():
        quality[name] = float(numpy.mean(values))
    return fields, quality


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
        interval_seconds = (pairs[0][1] - pairs[0][0]).total_seconds()
        context = MethodContext(
            variable=variable,
            frames=frames,
            indices=tuple(range(len(frames))),
            interval_seconds=interval_seconds,
            dataset=dataset,
        )
        # Every enabled method is derived for every variable, on the same
        # frames of the same cycle, so the held-out scores in provenance rank
        # them directly rather than across cycles that saw different weather.
        methods = enabled_methods()
        stacks: dict[str, list[Any]] = {}
        per_method: dict[str, Any] = {}
        for method in methods:
            active, notes = method.configure(context)
            fields, method_quality = _derive_one_method(active, context, pairs)
            for suffix, values in fields.items():
                stacks.setdefault(suffix, []).append(values)
            per_method[method.id] = {**method_quality, "options": {key: value for key, value in notes.items() if key != "skill"}}
        # A method that published a suffix nothing else did leaves the others
        # an explicit zero field rather than a ragged artifact: the client
        # reads a suffix only for the method that declared it.
        empty = numpy.zeros((len(pairs),) + frames[0].shape, dtype="float32")
        for suffix, values in stacks.items():
            while len(values) < len(methods):
                values.append(empty)
        for suffix, values in stacks.items():
            data_vars[f"{variable}_{suffix}"] = (("method", "pair", "y", "x"), numpy.stack(values), _FIELD_ATTRS.get(suffix, _FLOW_ATTRS))
        quality[variable] = {
            "pairs": len(pairs),
            "methods": [method.id for method in methods],
            "per_method": per_method,
            # The default method's numbers keep their old names and their old
            # place, so a provenance reader that predates the bench still
            # finds what it looked for.
            **{key: value for key, value in per_method.get(DEFAULT_METHOD_ID, {}).items() if key != "options"},
            "steering_prior": per_method.get(DEFAULT_METHOD_ID, {}).get("options", {}),
        }

    if not data_vars:
        return None

    derived = xarray.Dataset(
        data_vars,
        coords={
            "pair_from": ("pair", numpy.array([stamp.replace(tzinfo=None) for stamp in pair_from], dtype="datetime64[ns]")),
            "pair_to": ("pair", numpy.array([stamp.replace(tzinfo=None) for stamp in pair_to], dtype="datetime64[ns]")),
            # The bench axis. An artifact without it predates the bench and is
            # read as the single method `baseline`.
            "method": ("method", numpy.array([method.id for method in enabled_methods()], dtype="<U32")),
        },
        attrs={
            "method": METHOD,
            "derivation_version": VERSION,
            "base_revision_id": str(surface.revision_id),
            "interpolation_methods": ",".join(method.id for method in enabled_methods()),
        },
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
        "interpolation_methods": method_catalogue(),
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
