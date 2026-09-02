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

Evidence rules (owner carve-out 2026-08-31, amended by carve-out (d)
2026-09-01): this artifact is a display derivation. It is published with its
method, version and base revision in provenance, it never feeds ``/point``,
``/timeline`` or any reading, and a pair whose flow cannot be computed is
simply absent - the client then crossfades, disclosed as such. A method that
draws a GENERATED value between frames (``generative = True``) is derived
only while ``WEATHER_GENERATED_DISPLAY`` allows it (``enabled_methods``).
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
    _dis_flow,
    _display_weight,
    _midpoint_composite,
    _prior_corrected,
    _segment_tangents,
    _ssim,
    _steering_prior,
    _supported_flow,
    _warp_linear,
    _warp_nearest,
)
from ingest.derive.methods import (  # noqa: F401 - re-exported for tests
    DEFAULT_METHOD_ID,
    MethodContext,
    PairMotion,
    _interpolation_skill,
    enabled_methods,
    generated_display_enabled,
    method_catalogue,
)
from ingest.grib import write_zarr
from ingest.manifest import declared_classes
from ingest.store import sha256_of

UTC = timezone.utc

#: Cloud variables worth motion fields, keyed by the (source, artifact) the
#: frames are read from. Only the rendered-grid cloud layers consume them;
#: nothing else is derived.
#:
#: Keyed by BOTH parts because a source now publishes more than one artifact
#: with cloud frames in it: the retrieved ``surface`` grid, and the derived
#: ``low_cloud_weong`` layer (``ingest.derive.weong_layer``). Each gets its own
#: motion artifact, derived from its own frames - the WEonG layer's cloud is a
#: different field from the provider's and borrowing the other's flow would be
#: a displacement fitted to the wrong picture.
CLOUD_MOTION_SOURCES: dict[tuple[str, str], tuple[str, ...]] = {
    ("noaa-gfs", "surface"): ("cloud_low", "cloud_middle", "cloud_high", "total_cloud"),
    ("eccc-hrdps", "surface"): ("total_cloud",),
    ("eccc-rdps", "surface"): ("total_cloud",),
    ("eccc-hrdps", "low_cloud_weong"): ("total_cloud_weong",),
    ("eccc-rdps", "low_cloud_weong"): ("total_cloud_weong",),
}

LOGICAL_NAME = "cloud_motion"


def motion_logical_name(base_logical_name: str) -> str:
    """The motion artifact's logical name for the artifact it derives from.

    ``surface`` keeps the bare ``cloud_motion`` it has always had, so every
    published artifact, every stored provenance record and every client that
    predates the derived layers still resolves; anything else is suffixed with
    its base, giving ``cloud_motion_low_cloud_weong``. One rule, one place,
    read identically by the derive and by the API's ``/flow`` lookup.
    """
    if base_logical_name == "surface":
        return LOGICAL_NAME
    return f"{LOGICAL_NAME}_{base_logical_name}"
METHOD = (
    "dense optical flow between adjacent published frames: OpenCV DIS (medium preset) on the "
    "Gaussian-presmoothed percent field, forward and backward, with a forward-backward "
    "consistency score per cell judged relative to the distance the flow claims; cells the "
    "round trip fails inherit the confidence-weighted flow of their trusted neighbourhood "
    "(normalized convolution), with the local trusted density kept as support; per-knot "
    "velocities by QVI central difference of the two adjacent pairs' flows (one-sided at the "
    "sequence ends), stored as cubic Hermite segment tangents so displayed velocity is C1 "
    "across every real frame; the display weight between advection and a plain crossfade is "
    "that support over its floor, so every cell with a trustworthy vector behind it advects at "
    "full strength and only cells with nothing trustworthy behind their fill dissolve (the "
    "photometric development test that used to gate the weight measured worse on growth, decay "
    "and sharpness on every layer and was removed); a variable whose held-out midpoint "
    "reconstruction does not beat the same construction with the motion reversed is published "
    "with a zero weight and crossfades everywhere - that control decides only whether motion is "
    "displayed; methods are ranked against each other, and any optional or generated term is "
    "admitted, on fixed controls (a plain crossfade and a plain advection of the same frames) "
    "with structural similarity and sharpness; where the model publishes the stratum's steering "
    "wind (850/700/500 hPa) that wind may fill cells the imagery leaves unsupported, weighted by "
    "its agreement with the trusted image flow, never where a well-supported image flow reports "
    "the field standing still, and only for a variable whose held-out reconstruction the prior "
    "measurably improves; a method may store a per-cell envelope t(1-t)(gen_a + gen_b t) in "
    "cloud percent, zero at both real instants by construction, added after the advection mix "
    "and clamped to the percent range"
)
VERSION = "cloud-motion-bench-v6"


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
    "vis0": {"units": "1", "role": "per-pixel reliability of the frame-0 warp at the midpoint (inverse error variance; error-variance-blend)"},
    "vis1": {"units": "1", "role": "per-pixel reliability of the frame-1 warp at the midpoint (inverse error variance; error-variance-blend)"},
    # The computed residual and the envelope built from it. These are percent
    # fields, not displacements, so they never inherit the flow attributes.
    "res_s": {
        "units": "percent",
        "role": (
            "computed development residual s = warp(following, -flow01) - previous, capped, "
            "expressed at the trajectory's start; diagnostic only, never served; zeroed with the "
            "display weight wherever the pair or the variable is vetoed"
        ),
    },
    "gen_a": {
        "units": "percent",
        "role": (
            "envelope coefficient a: the display adds t(1-t)(a + b t) after the advection mix, "
            "clamped to [0, 100]; zero at both real instants by construction; residual-advection "
            "stores a = 4 * gain * s (non-generative at gain <= 1/4); a generative method fits "
            "(a, b) to a cited timing target; zeroed with the display weight wherever vetoed"
        ),
    },
    "gen_b": {
        "units": "percent",
        "role": (
            "envelope coefficient b (see gen_a); zero for residual-advection; zeroed with the "
            "display weight wherever vetoed"
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
    reversed, are published with a zero display weight and crossfade. That
    reversed-flow control decides ONLY whether motion is displayed; methods
    are ranked against each other, and any optional or generated term is
    admitted, on the fixed controls the harness scores beside it.
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
    # Silencing a method means zeroing everything that carries its
    # contribution, not only the advection weight. A field fenced by
    # `1 - advect_weight` would otherwise be turned UP to maximum by the very
    # veto meant to switch it off. See `InterpolationMethod.vetoed_suffixes`.
    vetoed = tuple(name for name in getattr(method, "vetoed_suffixes", ()) if name in fields)

    def silence(index: int | slice) -> None:
        fields["advect_weight"][index] = 0.0
        for name in vetoed:
            fields[name][index] = 0.0

    for index, (warped, persisted) in enumerate(zip(mae_warp, mae_persistence)):
        if warped >= persisted:
            silence(index)
    skill = _interpolation_skill(
        context.frames,
        method=method,
        dataset=context.dataset,
        variable=context.variable,
        interval_seconds=context.interval_seconds,
        indices=context.indices,
        cache=context.cache,
    )
    if skill is not None and skill["improvement_over_reversed_flow"] < MIN_HELD_OUT_IMPROVEMENT:
        silence(slice(None))
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
        derived_fields: list[dict[str, Any]] = []
        per_method: dict[str, Any] = {}
        for method in methods:
            active, notes = method.configure(context)
            fields, method_quality = _derive_one_method(active, context, pairs)
            derived_fields.append(fields)
            per_method[method.id] = {**method_quality, "options": {key: value for key, value in notes.items() if key != "skill"}}
        # A method that published a suffix nothing else did leaves the others
        # an explicit zero field rather than a ragged artifact: the client
        # reads a suffix only for the method that declared it. Filled BY SLOT
        # rather than by append order - a suffix only one method declares would
        # otherwise be written at position 0 of the method axis and read back
        # under `baseline`, silently handing every reader one method's stored
        # field under another method's name.
        empty = numpy.zeros((len(pairs),) + frames[0].shape, dtype="float32")
        suffixes: list[str] = []
        for fields in derived_fields:
            suffixes.extend(suffix for suffix in fields if suffix not in suffixes)
        stacks = {
            suffix: [fields.get(suffix, empty) for fields in derived_fields]
            for suffix in suffixes
        }
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
        "quality": {"status": "passed", "flags": ["derived", "display_only"], "per_variable": quality},
        # An interpolation between retrieved frames, drawn and never served:
        # generated_display is the class, and it is what keeps this artifact
        # off /point and /profile now that admission reads the declaration
        # instead of matching a logical name.
        **declared_classes(["generated_display"]),
    }
    return RunResult(
        source_id=surface.source_id,
        provider_run_id=f"{surface.provider_run_id}+cloud-motion",
        run_time=surface.run_time,
        retrieved_at=datetime.now(UTC),
        complete=True,
        qc_passed=True,
        artifacts=[Artifact(motion_logical_name(surface.logical_name), MEDIA_ZARR, path, provenance)],
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
    for (source_id, base_logical_name), variables in CLOUD_MOTION_SOURCES.items():
        surface = current.get((source_id, base_logical_name))
        if surface is None:
            # Nothing published under that name this cycle. For a derived base
            # - the WEonG layer - that is the ordinary state when the kill
            # switch is off or the profile was incomplete, and motion for a
            # layer nobody is offered is not worth a line.
            continue
        existing = current.get((source_id, motion_logical_name(base_logical_name)))
        if (
            existing is not None
            and str(existing.provenance.get("base_revision_id", "")) == str(surface.revision_id)
            # A version bump re-derives even for an unchanged surface: an
            # artifact from an older construction never lingers as current.
            and str(existing.provenance.get("derivation_version", "")) == VERSION
        ):
            continue
        try:
            with tempfile.TemporaryDirectory(prefix=f"{source_id}-{base_logical_name}-cloud-motion-") as workdir:
                result = derive_cloud_motion(store, surface, variables, Path(workdir))
                if result is None:
                    lines.append(f"cloud-motion {source_id}/{base_logical_name}: nothing derivable (no cloud variable with two frames)")
                    continue
                store.stage_and_publish(result)
            lines.append(f"cloud-motion {source_id}/{base_logical_name}: published for {base_logical_name} revision {surface.revision_id}")
        except Exception as error:
            lines.append(f"cloud-motion {source_id}/{base_logical_name}: derive failed - {error!r}")
    return lines
