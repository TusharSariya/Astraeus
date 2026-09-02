"""The WEonG low-cloud diagnosis, against the primary source's own numbers.

Every expectation here is transcribed from ECCC's WEonG technical note
(v2.4.1, 23 June 2025, section 7.9), not from a summary of it. The tests that
matter most are the ones that pin the RH->LLC table's half-open bin edges and
the two zeroing scenarios, because those are the constants a later edit could
silently drift.
"""

from __future__ import annotations

import numpy
import pytest
import xarray

from ingest.derive.weong_low_cloud import (
    HOMOGENEOUS_NUCLEATION_MAX_TEMP_C,
    MIN_LAYER_THICKNESS_M,
    RH_TO_LLC_TABLE,
    SATURATION_RH_THRESHOLD,
    assert_liquid_water_rh,
    combine_nt_weong,
    llc_from_max_rh,
    nt_hrdps_from_opacity,
    suppress_near_surface_rh,
    weong_low_cloud_from_profile,
)
from ingest.grib import RH_PHASE_LIQUID_WATER, RH_PHASE_MIXED_LINEAR_253K_273K


def test_the_rh_to_llc_table_is_the_published_one():
    """The note prints half-open intervals; the bin edges belong to the bin above."""
    expected = [
        (0.00, 0.0), (0.73, 0.0), (0.739, 0.0),
        (0.74, 0.1), (0.77, 0.1),
        (0.78, 0.2), (0.79, 0.2),
        (0.80, 0.3), (0.81, 0.3),
        (0.82, 0.4), (0.83, 0.4),
        (0.84, 0.5), (0.85, 0.5),
        (0.86, 0.6), (0.87, 0.6),
        (0.88, 0.7), (0.89, 0.7),
        (0.90, 0.8), (0.91, 0.8),
        (0.92, 0.9), (0.95, 0.9),
        (0.96, 1.0), (1.00, 1.0),
    ]
    for rh, llc in expected:
        assert llc_from_max_rh(rh) == pytest.approx(llc), rh
    # And the table constant itself still says what the note says.
    assert RH_TO_LLC_TABLE[1] == (0.74, 0.1)
    assert RH_TO_LLC_TABLE[-1] == (0.96, 1.0)
    assert SATURATION_RH_THRESHOLD == 0.74


def test_llc_lookup_is_vectorised_and_keeps_absence_absent():
    out = llc_from_max_rh(numpy.array([0.5, 0.74, 0.97, numpy.nan]))
    assert out[0] == 0.0 and out[1] == pytest.approx(0.1) and out[2] == pytest.approx(1.0)
    assert numpy.isnan(out[3])


def test_nt_hrdps_is_opacity_weighted_and_never_exceeds_true_cover():
    """The note's own equation: NT = TCC*[1 - exp(-0.1*(W3+W4))]."""
    assert nt_hrdps_from_opacity(1.0, 0.0, 0.0) == pytest.approx(0.0)
    # Optically thin cloud reads far below its true cover.
    assert nt_hrdps_from_opacity(1.0, 1.0, 0.0) == pytest.approx(1.0 - numpy.exp(-0.1))
    thick = nt_hrdps_from_opacity(0.8, 60.0, 40.0)
    assert thick < 0.8 and thick == pytest.approx(0.8, abs=1e-4)


def test_combine_is_the_max_so_opacity_survives_where_it_is_larger():
    assert combine_nt_weong(0.9, 0.3) == pytest.approx(0.9)
    assert combine_nt_weong(0.0, 0.6) == pytest.approx(0.6)
    numpy.testing.assert_allclose(
        combine_nt_weong(numpy.array([0.1, 0.8]), numpy.array([0.5, 0.5])),
        numpy.array([0.5, 0.8]),
    )


def test_a_thick_saturated_low_layer_becomes_cloud():
    heights = [50.0, 300.0, 600.0, 900.0, 1200.0, 3000.0]
    rh = [0.40, 0.85, 0.91, 0.88, 0.30, 0.20]
    temp = [8.0, 6.0, 4.0, 2.0, 0.0, -10.0]
    # Layer 300-900 m, thickness 600 m >= 150, base 300 < 2000, max RH 0.91 -> 0.8.
    assert weong_low_cloud_from_profile(heights, rh, temp) == pytest.approx(0.8)


def test_a_layer_thinner_than_150_m_is_rejected():
    heights = [50.0, 300.0, 400.0, 3000.0]
    rh = [0.40, 0.95, 0.95, 0.20]
    temp = [8.0, 6.0, 5.0, -10.0]
    assert weong_low_cloud_from_profile(heights, rh, temp) == pytest.approx(0.0)
    # Widening the same layer past the threshold makes it qualify.
    heights[2] = 300.0 + MIN_LAYER_THICKNESS_M
    assert weong_low_cloud_from_profile(heights, rh, temp) == pytest.approx(0.9)


def test_a_layer_based_above_2000_m_is_not_low_cloud():
    heights = [50.0, 2100.0, 2600.0, 4000.0]
    rh = [0.30, 0.97, 0.97, 0.20]
    temp = [8.0, -2.0, -4.0, -20.0]
    assert weong_low_cloud_from_profile(heights, rh, temp) == pytest.approx(0.0)


def test_two_layers_are_scored_separately_and_the_larger_wins():
    heights = [100.0, 400.0, 700.0, 1000.0, 1400.0, 1800.0]
    #            0.75 layer (LLC 0.1)      dry     0.93 layer (LLC 0.9)
    rh = [0.75, 0.75, 0.30, 0.93, 0.93, 0.20]
    temp = [8.0, 6.0, 5.0, 3.0, 1.0, 0.0]
    assert weong_low_cloud_from_profile(heights, rh, temp) == pytest.approx(0.9)
    # If the dry level did not separate them, the single layer's max RH would
    # be 0.93 anyway - the point is that the low thin layer is not merged into
    # the upper one's base, which would push the base test around.
    assert weong_low_cloud_from_profile(heights, [0.75, 0.75, 0.93, 0.93, 0.93, 0.20], temp) == pytest.approx(0.9)


def test_homogeneous_nucleation_zeroes_the_layer():
    heights = [500.0, 900.0, 1300.0, 2500.0]
    rh = [0.20, 0.98, 0.98, 0.20]
    temp = [-30.0, -39.0, -45.0, -50.0]
    assert weong_low_cloud_from_profile(heights, rh, temp) == pytest.approx(0.0)
    # The note says "less than or equal to -38"; -37.9 is still cloud.
    warmer = [-30.0, HOMOGENEOUS_NUCLEATION_MAX_TEMP_C + 0.1, -45.0, -50.0]
    assert weong_low_cloud_from_profile(heights, rh, warmer) == pytest.approx(1.0)


def test_cold_layer_over_ice_covered_water_is_zeroed_only_there():
    heights = [500.0, 900.0, 1300.0, 2500.0]
    rh = [0.20, 0.98, 0.98, 0.20]
    temp = [-18.0, -20.0, -22.0, -30.0]
    assert weong_low_cloud_from_profile(heights, rh, temp, over_ice_covered_water=False) == pytest.approx(1.0)
    assert weong_low_cloud_from_profile(heights, rh, temp, over_ice_covered_water=True) == pytest.approx(0.0)
    # Warmer than -15 degC, the ice-water scenario does not apply.
    mild = [-8.0, -10.0, -12.0, -30.0]
    assert weong_low_cloud_from_profile(heights, rh, mild, over_ice_covered_water=True) == pytest.approx(1.0)


def test_near_surface_rh_decrease_is_suppressed_below_122_m():
    heights = [10.0, 100.0, 250.0, 500.0]
    rh = [0.99, 0.90, 0.20, 0.10]
    temp = [5.0, 4.0, 3.0, 1.0]
    suppressed = suppress_near_surface_rh(heights, rh, temp)
    assert suppressed[0] == pytest.approx(0.99)  # lowest level has no predecessor
    assert suppressed[1] < SATURATION_RH_THRESHOLD  # 100 m, RH falling with height
    # Above 122 m the rule does not apply even when RH still falls.
    heights_high = [10.0, 200.0, 250.0, 500.0]
    assert suppress_near_surface_rh(heights_high, rh, temp)[1] == pytest.approx(0.90)


def test_cold_inversion_is_suppressed_below_930_m_only_below_minus_15():
    heights = [10.0, 400.0, 800.0, 2000.0]
    rh = [0.50, 0.98, 0.98, 0.10]
    cold_inversion = [-25.0, -20.0, -18.0, -30.0]
    suppressed = suppress_near_surface_rh(heights, rh, cold_inversion)
    assert suppressed[1] < SATURATION_RH_THRESHOLD and suppressed[2] < SATURATION_RH_THRESHOLD
    # The same inversion at warm temperatures is left alone: the note limits
    # rule (b) to TT below -15 degC.
    warm_inversion = [-2.0, 1.0, 3.0, -5.0]
    assert suppress_near_surface_rh(heights, rh, warm_inversion)[1] == pytest.approx(0.98)


def test_the_profile_diagnosis_runs_over_a_grid_in_one_call():
    heights = [numpy.full((2, 3), h) for h in (100.0, 400.0, 800.0, 3000.0)]
    rh = [
        numpy.full((2, 3), 0.30),
        numpy.array([[0.95, 0.85, 0.50], [0.75, 0.99, 0.20]]),
        numpy.array([[0.95, 0.85, 0.50], [0.75, 0.99, 0.20]]),
        numpy.full((2, 3), 0.10),
    ]
    temp = [numpy.full((2, 3), t) for t in (6.0, 4.0, 2.0, -20.0)]
    out = weong_low_cloud_from_profile(heights, rh, temp)
    numpy.testing.assert_allclose(out, numpy.array([[0.9, 0.5, 0.0], [0.1, 1.0, 0.0]]))


def test_the_single_level_layer_the_three_pressure_levels_give_never_qualifies():
    """This is the well-posedness finding, asserted rather than only written down.

    Feeding the faithful algorithm the exact profile this repository holds -
    850/700/500 hPa - can never produce cloud, because one saturated level has
    zero thickness and the note requires >= 150 m.
    """
    heights = [1450.0, 3000.0, 5500.0]
    rh = [0.99, 0.20, 0.10]
    temp = [2.0, -8.0, -22.0]
    assert weong_low_cloud_from_profile(heights, rh, temp) == pytest.approx(0.0)


def test_gfs_relative_humidity_is_refused_by_the_table_that_is_not_calibrated_on_it():
    liquid = xarray.DataArray([80.0], attrs={"rh_phase_convention": RH_PHASE_LIQUID_WATER})
    assert_liquid_water_rh(liquid)  # does not raise

    mixed = xarray.DataArray([80.0], attrs={"rh_phase_convention": RH_PHASE_MIXED_LINEAR_253K_273K})
    with pytest.raises(ValueError, match="liquid water"):
        assert_liquid_water_rh(mixed)

    undeclared = xarray.DataArray([80.0], attrs={})
    with pytest.raises(ValueError, match="liquid water"):
        assert_liquid_water_rh(undeclared)


def test_mismatched_profile_lengths_are_refused():
    with pytest.raises(ValueError):
        suppress_near_surface_rh([10.0, 20.0], [0.5], [1.0, 2.0])


# --- the derived layer: profile in, generated artifact out ----------------
#
# From here down the subject is `ingest.derive.weong_layer`, the module that
# runs the algorithm above over a published surface artifact and files the
# answer as its own artifact. What is pinned is the plumbing the algorithm
# cannot check for itself: the AGL datum, the below-ground mask, the
# never-below-the-provider guarantee, and the kill switch.

import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ingest.derive.weong_layer import (
    DERIVATION_VERSION,
    LOGICAL_NAME,
    PROFILE_LEVELS_HPA,
    derive_weong_low_cloud,
    missing_profile_variables,
    surface_height_from_profile,
    weong_cycle,
)
from ingest.grib import ECCC_RH_PHASE_BASIS, write_zarr
from ingest.store import CurrentArtifact, sha256_of

UTC = timezone.utc

#: Geopotential height of each of the nine retrieved levels, US standard
#: atmosphere to the nearest metre. Only the SPACING matters to the note's
#: 150 m thickness test, and this is the real spacing: ~125 m per 15 hPa near
#: the surface, widening to ~235 m per 25 hPa at 850.
STANDARD_HEIGHTS_M = {
    1015: -14.0, 1000: 111.0, 985: 237.0, 970: 365.0, 950: 540.0,
    925: 762.0, 900: 988.0, 875: 1220.0, 850: 1457.0,
}


def profile_dataset(
    *,
    saturated_levels: tuple[int, ...] = (1000, 985, 970),
    datum_m: tuple[float, float] = (0.0, 300.0),
    total_cloud_percent: float = 10.0,
    surface_variable: str = "surface_height",
    steps: int = 2,
) -> xarray.Dataset:
    """Two columns of the same profile over two different terrain heights.

    Column 0 is at sea level, column 1 stands on 300 m of ground, so the two
    lowest saturated levels are UNDERGROUND there. Everything else - humidity,
    temperature, the heights themselves - is identical, which is what makes
    the difference between the two columns attributable to the datum alone.
    """
    base = datetime(2026, 9, 1, 12, tzinfo=UTC)
    stamps = [numpy.datetime64((base + timedelta(hours=step)).replace(tzinfo=None), "ns") for step in range(steps)]
    shape = (steps, 1, 2)
    data: dict[str, tuple] = {}
    for level in PROFILE_LEVELS_HPA:
        rh = 95.0 if level in saturated_levels else 20.0
        data[f"relative_humidity_{level}hPa"] = (
            ("valid_time", "y", "x"),
            numpy.full(shape, rh),
            {"units": "percent", "rh_phase_convention": RH_PHASE_LIQUID_WATER, "rh_phase_basis": ECCC_RH_PHASE_BASIS},
        )
        # Warm enough everywhere that neither zeroing scenario fires: what is
        # under test here is the datum, not the temperature tests.
        data[f"temperature_{level}hPa"] = (("valid_time", "y", "x"), numpy.full(shape, 5.0), {"units": "degC"})
        data[f"geopotential_height_{level}hPa"] = (
            ("valid_time", "y", "x"), numpy.full(shape, STANDARD_HEIGHTS_M[level]), {"units": "gpm"},
        )
    data["total_cloud"] = (("valid_time", "y", "x"), numpy.full(shape, total_cloud_percent), {"units": "percent"})
    if surface_variable == "surface_height":
        surface = numpy.broadcast_to(numpy.array(datum_m).reshape(1, 1, 2), shape).copy()
        data["surface_height"] = (("valid_time", "y", "x"), surface, {"units": "m"})
    else:
        # The same two datums expressed as the surface pressure that stands
        # over them, so the reconstruction has a known right answer.
        pressures = [
            # Heights ascend with the level order, which is what interp needs.
            float(numpy.exp(numpy.interp(
                value,
                [STANDARD_HEIGHTS_M[level] for level in PROFILE_LEVELS_HPA],
                [numpy.log(level) for level in PROFILE_LEVELS_HPA],
            )) * 100.0)
            for value in datum_m
        ]
        data["surface_pressure"] = (
            ("valid_time", "y", "x"),
            numpy.broadcast_to(numpy.array(pressures).reshape(1, 1, 2), shape).copy(),
            {"units": "Pa"},
        )
    # One steering-level copy, so the "methods keep working" promise is
    # checkable rather than asserted.
    data["wind_u_850hPa"] = (("valid_time", "y", "x"), numpy.full(shape, 4.0), {"units": "m s-1"})
    data["omega_850hPa"] = (("valid_time", "y", "x"), numpy.full(shape, -0.1), {"units": "Pa s-1"})
    return xarray.Dataset(data, coords={"valid_time": stamps, "y": [0.0], "x": [0.0, 1.0]})


class FakeStore:
    """Just enough of ArtifactStore for the WEonG derive path."""

    class config:  # noqa: D106 - namespace only
        bucket = "weather-artifacts"

    def __init__(self, payloads: dict, artifacts: list) -> None:
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


def surface_artifact(tmp_path: Path, dataset: xarray.Dataset, *, source_id: str = "eccc-hrdps"):
    payload = tmp_path / f"{source_id}-surface.zarr.zip"
    write_zarr(dataset, payload)
    stamp = datetime(2026, 9, 1, 12, tzinfo=UTC)
    return CurrentArtifact(
        source_id=source_id,
        logical_name="surface",
        revision_id=f"rev-{source_id}-1",
        object_key=f"published/{source_id}/surface",
        media_type="application/zarr+zip",
        byte_size=payload.stat().st_size,
        provenance={"product": source_id.upper(), "sha256": sha256_of(payload), "native_resolution": "2.5 km"},
        published_at=stamp,
        run_time=stamp,
        retrieved_at=stamp,
        provider_run_id="2026090112",
        native_crs="EPSG:4326",
    ), payload


def stored(artifact):
    import zarr

    zip_store = zarr.storage.ZipStore(str(artifact.payload_path), mode="r")
    return xarray.open_zarr(zip_store, consolidated=False), zip_store


def test_a_below_ground_level_is_masked_and_that_is_what_decides_the_layer(tmp_path: Path):
    """The datum is not a detail: it decides whether the layer exists at all.

    Both columns hold the identical saturated block at 1000/985/970 hPa
    (111-365 m MSL, 254 m thick). At sea level that is a layer with a base
    111 m AGL and a thickness over the note's 150 m minimum, so it diagnoses
    cloud. Standing on 300 m of ground, two of those three levels are
    UNDERGROUND - ECCC fills them by post-processing extrapolation, so their
    humidity is an artefact of the fill, not air - and the one level left has
    zero thickness and can never qualify.

    Without the mask the terrain column would read the same cloud as the sea
    column, from two levels of rock.
    """
    artifact, payload = surface_artifact(tmp_path, profile_dataset())
    store = FakeStore({artifact.object_key: payload}, [artifact])
    workdir = tmp_path / "derive"
    workdir.mkdir()
    result = derive_weong_low_cloud(store, artifact, workdir)
    assert result is not None
    derived, zip_store = stored(result.artifacts[0])
    try:
        llc = derived["llc"].values
        # Sea level: RH 0.95 falls in the table's [0.92, 0.96) bin -> LLC 0.9.
        # (0.95 is NOT the top bin; the note closes that one at 0.96.)
        assert llc[:, 0, 0] == pytest.approx(0.9)
        # On 300 m of terrain: nothing, because the mask left one level.
        assert llc[:, 0, 1] == pytest.approx(0.0)
        # Which is exactly what the unmasked algorithm would NOT say.
        unmasked = weong_low_cloud_from_profile(
            [STANDARD_HEIGHTS_M[level] - 300.0 for level in PROFILE_LEVELS_HPA],
            [0.95 if level in (1000, 985, 970) else 0.20 for level in PROFILE_LEVELS_HPA],
            [5.0] * len(PROFILE_LEVELS_HPA),
        )
        assert float(unmasked) == pytest.approx(0.9)
    finally:
        zip_store.close()


def test_the_derived_cloud_is_never_below_the_retrieved_cloud(tmp_path: Path):
    """NT_WEonG = max[NT ; LLC]: a repair that ADDS cloud and never removes it.

    The provider's own field travels in the same artifact, so the claim is
    checkable from one read rather than by fetching two artifacts and trusting
    that they line up.
    """
    artifact, payload = surface_artifact(tmp_path, profile_dataset(total_cloud_percent=40.0))
    store = FakeStore({artifact.object_key: payload}, [artifact])
    workdir = tmp_path / "derive"
    workdir.mkdir()
    result = derive_weong_low_cloud(store, artifact, workdir)
    derived, zip_store = stored(result.artifacts[0])
    try:
        repaired = derived["total_cloud_weong"].values
        retrieved = derived["total_cloud"].values
        assert numpy.all(repaired >= retrieved - 1e-4)
        assert numpy.all((repaired >= 0.0) & (repaired <= 100.0))
        # Sea level: LLC 0.9 beats the retrieved 40 %, so the repair fires.
        assert repaired[:, 0, 0] == pytest.approx(90.0)
        # Terrain: no diagnosis, so the retrieved value stands untouched.
        assert repaired[:, 0, 1] == pytest.approx(40.0)
        # The run's own steering fields rode along, so an interpolation
        # method's lookup finds them on this layer without a change.
        assert "wind_u_850hPa" in derived.data_vars
        assert "omega_850hPa" in derived.data_vars
    finally:
        zip_store.close()

    provenance = result.artifacts[0].provenance
    assert result.artifacts[0].logical_name == LOGICAL_NAME
    assert provenance["derived"] is True and provenance["generated"] is True
    assert "WEonG" in provenance["derivation"] and "section 7.9" in provenance["derivation"]
    assert provenance["derivation_version"] == DERIVATION_VERSION
    assert provenance["base_revision_id"] == "rev-eccc-hrdps-1"
    assert provenance["base_object_key"] == artifact.object_key
    assert provenance["agl_datum"].startswith("retrieved model orography")
    quality = provenance["quality"]
    assert quality["llc_coverage_fraction"] == pytest.approx(0.5)
    # 50 points added over the sea column, none over the terrain column.
    assert quality["mean_added_cloud_percent"] == pytest.approx(25.0)
    assert quality["max_added_cloud_percent"] == pytest.approx(50.0)
    assert quality["profile_levels_hpa"] == list(PROFILE_LEVELS_HPA)


def test_the_rdps_datum_is_reconstructed_in_log_pressure_and_says_so(tmp_path: Path):
    """RDPS publishes no surface height, so the datum is interpolated.

    The fixture builds the surface pressure that stands over each column's
    known terrain height, so the reconstruction has an exact right answer and
    the derived layer must land on the same two columns as the HRDPS case.
    """
    dataset = profile_dataset(surface_variable="surface_pressure")
    assert "surface_height" not in dataset.data_vars
    artifact, payload = surface_artifact(tmp_path, dataset, source_id="eccc-rdps")
    store = FakeStore({artifact.object_key: payload}, [artifact])
    workdir = tmp_path / "derive"
    workdir.mkdir()
    result = derive_weong_low_cloud(store, artifact, workdir)
    derived, zip_store = stored(result.artifacts[0])
    try:
        assert derived["llc"].values[:, 0, 0] == pytest.approx(0.9)
        assert derived["llc"].values[:, 0, 1] == pytest.approx(0.0)
    finally:
        zip_store.close()
    provenance = result.artifacts[0].provenance
    assert provenance["agl_datum"].startswith("reconstructed")
    # The bias is disclosed with the value, not left in a docstring.
    assert "RECONSTRUCTED" in provenance["derivation"]
    assert "extrapolated" in provenance["derivation"]


def test_log_pressure_interpolation_is_exact_on_its_own_assumption():
    """Height linear in ln p is the hydrostatic form, so it must be recovered.

    ``dz = -(R T_v / g) d ln p``: for a constant layer mean temperature the
    height IS linear in ``ln p``, so a profile built that way must come back
    exactly. This pins the axis direction too - getting it backwards would
    still interpolate, just to the wrong level.
    """
    levels = numpy.array([1000.0, 900.0, 800.0])
    heights = [numpy.full((2,), value) for value in (0.0, 800.0, 1600.0)]
    # ln p is evenly spaced here, so 900 hPa is exactly the midpoint.
    at_900 = surface_height_from_profile(heights, levels, numpy.full((2,), 90000.0))
    numpy.testing.assert_allclose(at_900, 800.0)
    # A pressure between two levels interpolates in ln p, not in p.
    at_950 = surface_height_from_profile(heights, levels, numpy.full((2,), 95000.0))
    expected = 800.0 * (numpy.log(1000.0) - numpy.log(950.0)) / (numpy.log(1000.0) - numpy.log(900.0))
    numpy.testing.assert_allclose(at_950, expected)
    # Below the lowest retrieved level the answer is an extrapolation on the
    # same slope, which is the common sea-level case under high pressure.
    at_1020 = surface_height_from_profile(heights, levels, numpy.full((2,), 102000.0))
    assert float(at_1020[0]) < 0.0
    with pytest.raises(ValueError, match="descend"):
        surface_height_from_profile(heights, numpy.array([800.0, 900.0, 1000.0]), numpy.full((2,), 90000.0))


def test_an_incomplete_profile_publishes_nothing_rather_than_a_partial_diagnosis(tmp_path: Path):
    dataset = profile_dataset().drop_vars(["relative_humidity_925hPa", "surface_height"])
    missing = missing_profile_variables(dataset)
    assert "relative_humidity_925hPa" in missing
    assert "surface_height or surface_pressure" in missing
    artifact, payload = surface_artifact(tmp_path, dataset)
    store = FakeStore({artifact.object_key: payload}, [artifact])
    workdir = tmp_path / "derive"
    workdir.mkdir()
    assert derive_weong_low_cloud(store, artifact, workdir) is None
    # And the cycle says so rather than failing silently.
    lines = weong_cycle(store)
    assert store.published == []
    assert any("nothing derivable" in line for line in lines)


def test_mixed_phase_humidity_is_refused_before_a_single_value_is_diagnosed(tmp_path: Path):
    dataset = profile_dataset()
    dataset["relative_humidity_950hPa"].attrs["rh_phase_convention"] = RH_PHASE_MIXED_LINEAR_253K_273K
    artifact, payload = surface_artifact(tmp_path, dataset)
    store = FakeStore({artifact.object_key: payload}, [artifact])
    workdir = tmp_path / "derive"
    workdir.mkdir()
    with pytest.raises(ValueError, match="liquid water"):
        derive_weong_low_cloud(store, artifact, workdir)
    # The cycle turns that into a line, never an exception at the worker.
    lines = weong_cycle(store)
    assert store.published == []
    assert any("derive failed" in line for line in lines)


def test_the_cycle_publishes_once_and_then_skips_an_up_to_date_layer(tmp_path: Path):
    artifact, payload = surface_artifact(tmp_path, profile_dataset())
    store = FakeStore({artifact.object_key: payload}, [artifact])
    lines = weong_cycle(store)
    assert len(store.published) == 1
    assert any("published for surface revision rev-eccc-hrdps-1" in line for line in lines)

    existing = CurrentArtifact(
        source_id="eccc-hrdps",
        logical_name=LOGICAL_NAME,
        revision_id="rev-weong-1",
        object_key="published/eccc-hrdps/low_cloud_weong",
        media_type="application/zarr+zip",
        byte_size=1,
        provenance={"base_revision_id": "rev-eccc-hrdps-1", "derivation_version": DERIVATION_VERSION},
        published_at=artifact.published_at,
        run_time=artifact.run_time,
        retrieved_at=artifact.retrieved_at,
        provider_run_id="2026090112+low-cloud-weong",
        native_crs="EPSG:4326",
    )
    fresh = FakeStore({artifact.object_key: payload}, [artifact, existing])
    assert weong_cycle(fresh) == []
    assert fresh.published == []

    # A version bump re-derives even for an unchanged surface, so an artifact
    # from an older construction never lingers as current.
    stale = CurrentArtifact(**{**existing.__dict__, "provenance": {
        "base_revision_id": "rev-eccc-hrdps-1", "derivation_version": "weong-low-cloud-v0",
    }})
    moved_on = FakeStore({artifact.object_key: payload}, [artifact, stale])
    weong_cycle(moved_on)
    assert len(moved_on.published) == 1


def test_the_kill_switch_publishes_nothing_and_says_why(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """`WEATHER_GENERATED_DISPLAY=off` refuses the whole pass, out loud.

    This is the middle of carve-out (d)'s three switches. Nothing is derived,
    so nothing is published, so `/layers` cannot offer the layer at all - the
    absence IS the switch, and the log line is what makes it legible rather
    than looking like a failure.
    """
    artifact, payload = surface_artifact(tmp_path, profile_dataset())
    store = FakeStore({artifact.object_key: payload}, [artifact])
    monkeypatch.setenv("WEATHER_GENERATED_DISPLAY", "off")
    lines = weong_cycle(store)
    assert store.published == []
    assert len(lines) == 1
    assert "WEATHER_GENERATED_DISPLAY is off" in lines[0]
    assert "not published" in lines[0]
    # Any other value leaves it on: the default is on because a construction
    # that is never derived is never measured.
    monkeypatch.setenv("WEATHER_GENERATED_DISPLAY", "on")
    weong_cycle(store)
    assert len(store.published) == 1
