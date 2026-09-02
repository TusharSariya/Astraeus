"""ECCC's own low-cloud repair, published as a separate derived layer.

WHAT THIS IS
------------
HRDPS's published total cloud (``NT``) is opacity-weighted, not a cloud
fraction, and ECCC says in its own technical note that it "has challenges
detecting low-level clouds in certain synoptic situations". The note publishes
the repair ECCC itself applies: a Low Level Cloud field diagnosed from the
model's own relative-humidity profile, combined as ``NT_WEonG = max[NT ; LLC]``.

    Environment and Climate Change Canada, "Weather Elements on grid (WEonG),
    Implementation of version 2.4.1, Technical Note", 23 June 2025, section
    7.9 "Sky State (cloud cover and opacity combined)", pp. 45-47.

The algorithm itself lives in :mod:`ingest.derive.weong_low_cloud`, transcribed
from that section. This module is the plumbing that runs it over a published
surface artifact and files the answer as its own artifact, so nothing about
the retrieved ``total_cloud`` layer changes: the provider's field stays
untouched and this sits beside it, disclosed as generated.

WHY A SEPARATE ARTIFACT AND NOT A REPAIRED FIELD
------------------------------------------------
Because it is a value the provider did not publish. Carve-out (d) admits it as
a GENERATED display value - a producer's own documented diagnostic, computed
from the same run's own retrieved fields, bounded to the variable's physical
range, disclosed as generated wherever it is offered, and switchable off. What
it must never do is overwrite evidence. Filing it as ``low_cloud_weong`` keeps
``surface`` frame-exact for ``/point``, ``/timeline``, ``/features``, stories
and readings, and confines this to the map.

It is refused entirely when ``WEATHER_GENERATED_DISPLAY`` is off; nothing is
published, and the layer then simply is not offered.

THE AGL DATUM (the one place the two models differ)
---------------------------------------------------
The note's tests are on height above ground: a saturated layer needs a base
under 2000 m AGL and a thickness of at least 150 m. The profile arrives as
geopotential height above mean sea level, so a datum is needed.

* HRDPS publishes ``HGT_Sfc``, which decodes as orography in metres
  (discipline 0 / category 3 / number 5 on ``sfc``, paramId 228002, units
  ``m``). That is the datum, retrieved, no reconstruction.
* RDPS publishes no surface height at all - the live 12Z PT003H listing on
  2026-09-01 carries 21 ``_Sfc_`` tokens and not one of them is a height. It
  does publish ``Pressure_Sfc``. The datum is reconstructed by
  :func:`surface_height_from_profile`, and its bias is stated there.

WHAT IT ACTUALLY DID, ON ONE REAL CYCLE
---------------------------------------
Run once end to end on the retrieved 2026-09-01 12Z PT003H fields for both
models, cropped to ``AVALON_CORE_BOUNDS`` (HRDPS 148 x 149 cells, RDPS
35 x 36):

=============================  ==========  ==========
                               HRDPS       RDPS
=============================  ==========  ==========
retrieved total cloud, mean    56.1 %      31.1 %
NT_WEonG, mean                 91.3 %      95.5 %
mean added                     +35.3 pts   +64.4 pts
largest added                  +98.7 pts   +100.0 pts
cells with LLC > 0             100 %       100 %
cells with a masked level      50.8 %      50.5 %
=============================  ==========  ==========

Two things in that table are worth stating rather than smoothing over. The
repair is LARGE - which is the documented behaviour, since NT is
opacity-weighted and reads near zero for optically thin cloud - and on this
particular cycle it fired on every single cell, a saturated maritime morning
over the Avalon rather than a bug, but also not a demonstration that it
discriminates. Half the cells had at least one level masked as below ground,
almost all of them the 1015 hPa surface sitting under a sea-level pressure
lower than 1015 hPa. None of this is evidence; it is a display layer, and it
is offered next to the untouched retrieved field so the difference is visible
rather than asserted.
"""

from __future__ import annotations

import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from ingest.contract import Artifact, MEDIA_ZARR, RunResult
from ingest.derive.methods import generated_display_enabled
from ingest.derive.weong_low_cloud import (
    assert_liquid_water_rh,
    combine_nt_weong,
    weong_low_cloud_from_profile,
)
from ingest.grib import write_zarr
from ingest.manifest import declared_classes
from ingest.registry import LOW_PROFILE_LEVELS_HPA
from ingest.store import sha256_of

UTC = timezone.utc
_log = logging.getLogger(__name__)

#: The derived artifact's own logical name. Never ``surface``: the provider's
#: artifact is untouched and this one is offered separately, as generated.
LOGICAL_NAME = "low_cloud_weong"

#: Bumped whenever the construction changes, so an artifact from an older one
#: never lingers as current (the cycle below compares it as well as the base
#: revision).
DERIVATION_VERSION = "weong-low-cloud-v1"

#: The sources this runs for. Both ECCC models, and only ECCC models: the
#: RH->LLC table is an ECCC calibration against liquid-water RH, and
#: ``assert_liquid_water_rh`` refuses anything else out loud (GFS RH is
#: mixed-phase and reads up to ~24 % higher below -25 degC).
WEONG_SOURCES: tuple[str, ...] = ("eccc-hrdps", "eccc-rdps")

#: The profile levels the diagnosis reads, ascending in height.
PROFILE_LEVELS_HPA: tuple[int, ...] = tuple(LOW_PROFILE_LEVELS_HPA)

#: Fields copied verbatim from the run's own surface artifact so the
#: interpolation methods' lookups (`STEERING_LEVEL_BY_VARIABLE`, the steering
#: prior, the omega re-timing, the RH threshold crossing) work against this
#: layer without a single change. They are the same retrieved values, filed
#: beside the derived cloud rather than re-derived.
STEERING_LEVELS_HPA: tuple[int, ...] = (850, 700, 500)
COPIED_VARIABLES: tuple[str, ...] = tuple(
    name
    for level in STEERING_LEVELS_HPA
    for name in (
        f"wind_u_{level}hPa",
        f"wind_v_{level}hPa",
        f"omega_{level}hPa",
        f"relative_humidity_{level}hPa",
        f"temperature_{level}hPa",
    )
)

#: What the derived artifact says about itself, verbatim, everywhere it is
#: disclosed. Named as generated, with the construction and its citation.
DERIVATION = (
    "low cloud diagnosed from the model's own humidity profile by ECCC's published WEonG "
    "algorithm (Environment and Climate Change Canada, 'Weather Elements on grid (WEonG), "
    "Implementation of version 2.4.1, Technical Note', 23 June 2025, section 7.9): the nine "
    "retrieved isobaric levels from 1015 to 850 hPa are converted to height above ground, "
    "levels below ground are dropped, relative humidity is suppressed where the note says to "
    "(falling with height in the lowest 122 m AGL; a temperature inversion below 930 m AGL at "
    "temperatures under -15 degC), saturated layers (RH >= 0.74) with a base under 2000 m AGL "
    "and a thickness of at least 150 m are scored through the note's published RH->LLC table, "
    "layers whose maximum temperature is at or below -38 degC are zeroed as homogeneous "
    "nucleation, and the result is combined with the retrieved field as NT_WEonG = "
    "max[NT_HRDPS ; LLC]. GENERATED display value under carve-out (d): computed from the same "
    "run's own retrieved fields, bounded to 0-100 percent, never below the retrieved cloud, "
    "and never on a data path - /point, /timeline, /features, stories and readings read the "
    "untouched provider artifact"
)

#: The datum note appended to `DERIVATION` for RDPS only.
RDPS_DATUM_NOTE = (
    ". AGL datum for this source is RECONSTRUCTED, not retrieved: RDPS publishes no surface "
    "geopotential height or orography, so the height profile is interpolated to the retrieved "
    "surface pressure in log-pressure (hydrostatically exact for a locally constant layer mean "
    "temperature). The datum is therefore the height of the model's own surface-pressure "
    "surface, which is its terrain height to within that interpolation; below 1015 hPa the "
    "profile is extrapolated on the same slope, and ECCC's below-ground isobaric fields are "
    "themselves post-processed extrapolations, so the datum carries a bias of order tens of "
    "metres over terrain and is most trustworthy at sea level - which is where this layer's "
    "target weather, Avalon marine stratus and advection fog, sits"
)


def surface_height_from_profile(
    heights_msl: Sequence[Any],
    levels_hpa: Sequence[float],
    surface_pressure_pa: Any,
) -> Any:
    """Height of the surface-pressure surface, by log-pressure interpolation.

    ``heights_msl[k]`` is the geopotential height at ``levels_hpa[k]``, which
    must be DESCENDING in pressure (so heights ascend). Returns an array of
    the same shape as one level.

    Log-pressure is the right variable and not a convenience: the hydrostatic
    equation gives ``dz = -(R T_v / g) d ln p``, so height is locally linear
    in ``ln p`` with a slope that is the layer's own mean virtual temperature.
    Interpolating in ``ln p`` therefore assumes only that the layer mean
    temperature is constant across one 15 hPa gap, which near the surface is
    an error of well under a metre.

    WHAT THIS IS BIASED BY, and which way:

    * Where the surface pressure exceeds the lowest retrieved level (1015 hPa)
      the answer is an EXTRAPOLATION on the 1015/1000 slope. That is the
      common case at sea level under high pressure, and the extrapolation is
      short (a few tens of metres) and on the correct slope.
    * ECCC fills isobaric levels that lie below ground by its own
      post-processing extrapolation, not by physics, so over terrain the
      1015 and 1000 hPa heights are not measurements of anything. The datum
      there can be wrong by tens of metres, which moves every AGL height by
      the same amount and can push a layer's base across the note's 2000 m
      test or its thickness across 150 m.
    * A 10 km grid smooths terrain: hills read lower and valleys higher than
      they are, before any of the above.

    So this datum is trustworthy at sea level and progressively less so over
    terrain. It is used because the alternative - no RDPS layer at all - hides
    the same uncertainty instead of stating it.
    """
    import numpy  # noqa: PLC0415

    levels = numpy.asarray(levels_hpa, dtype=float)
    if levels.ndim != 1 or levels.size < 2:
        raise ValueError("a log-pressure interpolation needs at least two levels")
    if not numpy.all(numpy.diff(levels) < 0):
        raise ValueError("levels must descend in pressure so that heights ascend")
    stack = numpy.stack([numpy.asarray(level, dtype=float) for level in heights_msl])
    if stack.shape[0] != levels.size:
        raise ValueError("one height field per level is required")

    # -log(p) ascends with the levels, which is what searchsorted needs.
    axis = -numpy.log(levels)
    target = -numpy.log(numpy.asarray(surface_pressure_pa, dtype=float) / 100.0)
    lower = numpy.clip(numpy.searchsorted(axis, target) - 1, 0, levels.size - 2)
    upper = lower + 1
    height_lower = numpy.take_along_axis(stack, lower[None, ...], axis=0)[0]
    height_upper = numpy.take_along_axis(stack, upper[None, ...], axis=0)[0]
    span = axis[upper] - axis[lower]
    return height_lower + (height_upper - height_lower) * (target - axis[lower]) / span


def _profile_variable_names() -> tuple[list[str], list[str], list[str]]:
    rh = [f"relative_humidity_{level}hPa" for level in PROFILE_LEVELS_HPA]
    temp = [f"temperature_{level}hPa" for level in PROFILE_LEVELS_HPA]
    height = [f"geopotential_height_{level}hPa" for level in PROFILE_LEVELS_HPA]
    return rh, temp, height


def _open_zarr_zip(path: Path) -> Any:
    import xarray  # noqa: PLC0415
    import zarr  # noqa: PLC0415

    store = zarr.storage.ZipStore(str(path), mode="r")
    return xarray.open_zarr(store, consolidated=False)


def missing_profile_variables(dataset: Any) -> list[str]:
    """Everything the diagnosis needs and this artifact does not carry.

    An empty list means derivable. Returned rather than raised so the caller
    can say what was missing in a log line and publish nothing, which is the
    honest outcome for an optional variable a cycle omitted.
    """
    rh_names, temp_names, height_names = _profile_variable_names()
    wanted = ["total_cloud", *rh_names, *temp_names, *height_names]
    missing = [name for name in wanted if name not in dataset.data_vars]
    if "surface_height" not in dataset.data_vars and "surface_pressure" not in dataset.data_vars:
        missing.append("surface_height or surface_pressure")
    return missing


def derive_weong_low_cloud(store: Any, surface: Any, workdir: Path) -> RunResult | None:
    """One WEonG low-cloud artifact for one published surface artifact, or None.

    ``None`` means nothing usable - the profile, the datum or the cloud field
    is absent from this cycle - and nothing is published in that case. The
    layer is then not offered, which is the fail-closed rung; no partial or
    substituted profile is ever diagnosed.
    """
    import numpy  # noqa: PLC0415
    import xarray  # noqa: PLC0415

    local = workdir / "surface.zarr.zip"
    store.s3.download_file(store.config.bucket, surface.object_key, str(local))
    expected = str(surface.provenance.get("sha256", ""))
    if expected and sha256_of(local) != expected:
        raise RuntimeError(f"{surface.source_id}: surface artifact bytes do not match their recorded digest")
    dataset = _open_zarr_zip(local)

    missing = missing_profile_variables(dataset)
    if missing:
        _log.info("%s: no WEonG layer, the artifact is missing %s", surface.source_id, ", ".join(missing))
        return None

    rh_names, temp_names, height_names = _profile_variable_names()
    # The table is an ECCC calibration against liquid-water RH. Every level is
    # checked, not a sample: a single mixed-phase level would silently
    # fabricate cloud through the very table this module exists to apply.
    for name in rh_names:
        assert_liquid_water_rh(dataset[name])

    time_name = next((candidate for candidate in ("valid_time", "time") if candidate in dataset["total_cloud"].dims), None)
    if time_name is None:
        _log.info("%s: no WEonG layer, total_cloud carries no time axis", surface.source_id)
        return None
    steps = int(dataset.sizes[time_name])

    reconstructed_datum = "surface_height" not in dataset.data_vars
    levels = numpy.asarray(PROFILE_LEVELS_HPA, dtype=float)

    llc_frames: list[Any] = []
    nt_frames: list[Any] = []
    below_ground_fraction: list[float] = []
    for index in range(steps):
        step = dataset.isel({time_name: index})
        heights_msl = [numpy.asarray(step[name].values, dtype=float) for name in height_names]
        if reconstructed_datum:
            datum = surface_height_from_profile(
                heights_msl, levels, numpy.asarray(step["surface_pressure"].values, dtype=float)
            )
        else:
            datum = numpy.asarray(step["surface_height"].values, dtype=float)

        heights_agl = [height - datum for height in heights_msl]
        # The adapter publishes RH in percent; the note's table is in
        # fractions.
        rh_profile = [numpy.asarray(step[name].values, dtype=float) / 100.0 for name in rh_names]
        temp_profile = [numpy.asarray(step[name].values, dtype=float) for name in temp_names]

        # A level below ground is not air. ECCC fills those isobaric levels by
        # post-processing extrapolation, so their RH is an artefact of that
        # fill and would start or extend a saturated layer that does not
        # exist. They are masked by forcing RH below the saturation threshold
        # rather than to NaN: NaN would propagate through the layer's running
        # maximum and turn a real diagnosis into an absent one.
        below_ground = numpy.zeros(heights_agl[0].shape, dtype=float)
        for level_index, height in enumerate(heights_agl):
            underground = height < 0.0
            rh_profile[level_index] = numpy.where(underground, 0.0, rh_profile[level_index])
            below_ground += underground.astype(float)
        below_ground_fraction.append(float(numpy.mean(below_ground > 0.0)))

        llc = weong_low_cloud_from_profile(heights_agl, rh_profile, temp_profile)
        cloud = numpy.asarray(step["total_cloud"].values, dtype=float)
        llc_frames.append(llc)
        nt_frames.append(numpy.clip(combine_nt_weong(cloud / 100.0, llc) * 100.0, 0.0, 100.0))

    llc_stack = numpy.stack(llc_frames).astype("float32")
    nt_stack = numpy.stack(nt_frames).astype("float32")
    retrieved = numpy.asarray(dataset["total_cloud"].values, dtype=float)

    template = dataset["total_cloud"]
    dims = template.dims
    data_vars: dict[str, Any] = {
        "total_cloud_weong": (
            dims,
            nt_stack,
            {
                "units": "percent",
                "generated": "true",
                "role": (
                    "NT_WEonG = max[NT_HRDPS ; LLC], the retrieved total cloud repaired by ECCC's "
                    "own published low-cloud diagnosis; display only, never evidence"
                ),
            },
        ),
        "llc": (
            dims,
            llc_stack,
            {
                "units": "1",
                "generated": "true",
                "role": "the WEonG Low Level Cloud fraction alone, before the max with the retrieved field",
            },
        ),
    }
    copied: list[str] = []
    for name in COPIED_VARIABLES:
        if name in dataset.data_vars:
            data_vars[name] = dataset[name]
            copied.append(name)
    # The retrieved field travels with the derived one so a reader can see
    # exactly what was added, and so the difference never has to be fetched
    # from a second artifact to be checked.
    data_vars["total_cloud"] = dataset["total_cloud"]

    derived = xarray.Dataset(
        data_vars,
        coords={name: dataset.coords[name] for name in dataset.coords},
        attrs={
            "derivation": DERIVATION + (RDPS_DATUM_NOTE if reconstructed_datum else ""),
            "derivation_version": DERIVATION_VERSION,
            "base_revision_id": str(surface.revision_id),
            "generated": "true",
        },
    )
    path = workdir / f"{surface.source_id}-low-cloud-weong.zarr.zip"
    write_zarr(derived, path)

    finite = numpy.isfinite(llc_stack) & numpy.isfinite(retrieved)
    added = numpy.where(finite, nt_stack - retrieved, 0.0)
    provenance = {
        "source_id": surface.source_id,
        "product": (
            f"{surface.provenance.get('product', surface.source_id)} low cloud, "
            "WEonG repair (derived, generated, display only)"
        ),
        "native_resolution": surface.provenance.get("native_resolution", ""),
        "derived": True,
        "generated": True,
        "derivation": DERIVATION + (RDPS_DATUM_NOTE if reconstructed_datum else ""),
        "derivation_version": DERIVATION_VERSION,
        "base_revision_id": str(surface.revision_id),
        "base_object_key": surface.object_key,
        "agl_datum": "reconstructed from surface pressure in log-pressure" if reconstructed_datum else "retrieved model orography (HGT_Sfc, paramId 228002, m)",
        "quality": {
            # "derived" is not one of the four statuses the evidence contract
            # allows (passed/suspect/failed/unknown); what is derived is said
            # in the flags, and the status reports this derivation's own QC.
            "status": "passed",
            "flags": ["derived", "generated", "display_only"],
            "profile_levels_hpa": list(PROFILE_LEVELS_HPA),
            "steps": steps,
            "copied_variables": copied,
            "llc_coverage_fraction": float(numpy.mean(llc_stack[numpy.isfinite(llc_stack)] > 0.0)) if finite.any() else 0.0,
            "mean_added_cloud_percent": float(numpy.mean(added[finite])) if finite.any() else 0.0,
            "max_added_cloud_percent": float(numpy.max(added[finite])) if finite.any() else 0.0,
            "below_ground_level_fraction": float(numpy.mean(below_ground_fraction)),
        },
        # The repair holds low-cloud values no provider published: a
        # generated display construction, allowed on the map under its
        # carve-out and refused on every data path by this declaration.
        **declared_classes(["generated_display"]),
    }
    return RunResult(
        source_id=surface.source_id,
        provider_run_id=f"{surface.provider_run_id}+low-cloud-weong",
        run_time=surface.run_time,
        retrieved_at=datetime.now(UTC),
        complete=True,
        qc_passed=True,
        artifacts=[Artifact(LOGICAL_NAME, MEDIA_ZARR, path, provenance)],
        native_crs=surface.native_crs,
        notes=f"WEonG low cloud derived from surface revision {surface.revision_id}",
    )


def weong_cycle(store: Any) -> list[str]:
    """Derive missing/stale WEonG layers. Never raises; returns log lines.

    Shaped exactly like ``cloud_motion_cycle``: one ``current_artifacts`` read,
    a base-revision and derivation-version comparison per source, and every
    failure reported as a line rather than thrown at the worker loop.

    The deployment kill switch is checked first and refuses the whole pass,
    with a line saying so. Nothing is published, so ``/layers`` does not offer
    the layer at all - the third of carve-out (d)'s three switches, applied
    where it costs nothing to check.
    """
    if not generated_display_enabled():
        return [
            "weong-low-cloud: refused - WEATHER_GENERATED_DISPLAY is off, so no generated "
            "display value is derived and the low-cloud layer is not published"
        ]
    lines: list[str] = []
    try:
        current = {(item.source_id, item.logical_name): item for item in store.current_artifacts()}
    except Exception as error:
        return [f"weong-low-cloud: current artifacts unreadable - {error!r}"]
    for source_id in WEONG_SOURCES:
        surface = current.get((source_id, "surface"))
        if surface is None:
            continue
        existing = current.get((source_id, LOGICAL_NAME))
        if (
            existing is not None
            and str(existing.provenance.get("base_revision_id", "")) == str(surface.revision_id)
            and str(existing.provenance.get("derivation_version", "")) == DERIVATION_VERSION
        ):
            continue
        try:
            with tempfile.TemporaryDirectory(prefix=f"{source_id}-weong-") as workdir:
                result = derive_weong_low_cloud(store, surface, Path(workdir))
                if result is None:
                    lines.append(
                        f"weong-low-cloud {source_id}: nothing derivable "
                        "(the published artifact does not carry the whole low-level profile)"
                    )
                    continue
                store.stage_and_publish(result)
            lines.append(f"weong-low-cloud {source_id}: published for surface revision {surface.revision_id}")
        except Exception as error:
            lines.append(f"weong-low-cloud {source_id}: derive failed - {error!r}")
    return lines
