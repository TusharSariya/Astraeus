"""Byte-range computation from a ``.idx`` sidecar.

A wrong range means downloading a global GRIB file instead of nine messages,
which is the fastest way to exhaust the 25 GiB cap, so the arithmetic here is
pinned message by message.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy
import pytest
import xarray

from ingest.grib import (
    ByteRange,
    GribError,
    averaging_window_hours,
    byte_ranges,
    crop_to_bbox,
    declare_time_average,
    declare_wmo_total_cloud,
    is_curvilinear,
    normalize_units,
    parse_idx,
    select_records,
    selected_bytes,
    stack_members,
    strip_message_scalars,
    subset_ranges,
)

UTC = timezone.utc

# A NOAA-style sidecar: recordnum:byteoffset:date:param:level:forecasthour:
IDX = """\
1:0:d=2026082912:PRMSL:mean sea level:3 hour fcst:
2:987654:d=2026082912:CLWMR:1 hybrid level:3 hour fcst:
3:1234567:d=2026082912:TMP:2 m above ground:3 hour fcst:
4:1456789:d=2026082912:DPT:2 m above ground:3 hour fcst:
5:1678901:d=2026082912:RH:2 m above ground:3 hour fcst:
6:1890123:d=2026082912:UGRD:10 m above ground:3 hour fcst:
7:2012345:d=2026082912:VGRD:10 m above ground:3 hour fcst:
8:2134567:d=2026082912:VIS:surface:3 hour fcst:
"""

OFFSETS = [0, 987654, 1234567, 1456789, 1678901, 1890123, 2012345, 2134567]


def test_lengths_are_the_gap_to_the_following_offset():
    records = parse_idx(IDX)
    assert [record.offset for record in records] == OFFSETS
    assert [record.length for record in records[:-1]] == [later - earlier for earlier, later in zip(OFFSETS, OFFSETS[1:])]
    assert [record.end for record in records[:-1]] == [later - 1 for later in OFFSETS[1:]]
    assert records[0].run_time == datetime(2026, 8, 29, 12, tzinfo=UTC)
    assert records[2].param == "TMP" and records[2].level == "2 m above ground"


def test_final_record_is_open_ended_because_the_sidecar_never_states_the_file_size():
    last = parse_idx(IDX)[-1]
    assert last.param == "VIS"
    assert last.length is None and last.end is None
    ranges = subset_ranges(IDX, params=["VIS"])
    assert ranges == [ByteRange(2134567, None)]
    assert ranges[0].header == "bytes=2134567-"
    assert selected_bytes(ranges) is None


def test_a_non_final_selection_is_always_bounded():
    """An unbounded range on an early message would pull the rest of the file."""
    for param in ("PRMSL", "CLWMR", "TMP", "DPT", "RH", "UGRD", "VGRD"):
        ranges = subset_ranges(IDX, params=[param])
        assert len(ranges) == 1
        assert ranges[0].end is not None, param
        assert ranges[0].length is not None and ranges[0].length > 0


def test_first_record_range_stops_before_the_second_message():
    ranges = subset_ranges(IDX, params=["PRMSL"])
    assert ranges == [ByteRange(0, 987653)]
    assert selected_bytes(ranges) == 987654


def test_adjacent_messages_collapse_into_one_request():
    ranges = subset_ranges(IDX, params=["TMP", "DPT"], levels=["2 m above ground"])
    assert ranges == [ByteRange(1234567, 1678900)]
    assert selected_bytes(ranges) == 1678901 - 1234567


def test_separated_messages_stay_separate_unless_the_gap_is_allowed():
    tight = subset_ranges(IDX, params=["TMP", "RH"], levels=["2 m above ground"])
    assert [item.as_tuple() for item in tight] == [(1234567, 1456788), (1678901, 1890122)]
    assert selected_bytes(tight) == (1456789 - 1234567) + (1890123 - 1678901)

    merged = subset_ranges(IDX, params=["TMP", "RH"], levels=["2 m above ground"], merge_gap_bytes=1 << 20)
    assert merged == [ByteRange(1234567, 1890122)]
    assert selected_bytes(merged) > selected_bytes(tight)


def test_the_selected_subset_is_a_small_fraction_of_the_indexed_file():
    ranges = subset_ranges(IDX, params=["TMP", "DPT", "UGRD", "VGRD"])
    assert selected_bytes(ranges) is not None
    assert selected_bytes(ranges) < OFFSETS[-1] // 2


def test_selection_filters_are_an_allowlist_on_param_level_and_forecast():
    records = parse_idx(IDX)
    assert [item.param for item in select_records(records, params=["tmp"])] == ["TMP"]
    assert select_records(records, params=["TMP"], levels=["surface"]) == []
    assert select_records(records, params=["TMP"], forecasts=["6 hour fcst"]) == []
    assert select_records(records, params=["NOT_A_PARAM"]) == []
    assert byte_ranges([]) == []


def test_records_are_ordered_by_offset_even_when_the_sidecar_is_not():
    shuffled = "\n".join(reversed(IDX.strip().splitlines()))
    assert [record.offset for record in parse_idx(shuffled)] == OFFSETS


@pytest.mark.parametrize(
    "text",
    ["1:0:d=2026082912:TMP\n", "1:notanumber:d=2026082912:TMP:surface:3 hour fcst:\n", "1:0:d=2026082912:TMP:surface:anl:\n2:0:d=2026082912:DPT:surface:anl:\n"],
    ids=["too-few-fields", "non-numeric-offset", "repeated-offset"],
)
def test_an_unparseable_sidecar_fails_loudly_rather_than_guessing_a_range(text):
    with pytest.raises(GribError):
        parse_idx(text)


def test_a_missing_run_date_stays_unknown():
    records = parse_idx("1:0:no-date:TMP:surface:anl:\n")
    assert records[0].run_time is None


# --- bbox cropping -----------------------------------------------------------
#
# HRDPS and RDPS are published on a rotated lat/lon grid, so cfgrib hands back
# ``latitude``/``longitude`` as 2-D coordinates over anonymous ``y``/``x``
# dimensions. ``crop_to_bbox`` used to assume a sliceable 1-D axis and called
# ``float(latitudes[0])`` on what was really a whole grid row, which raised
# ``only 0-dimensional arrays can be converted to Python scalars`` for every
# ECCC regional field. Both grid shapes are pinned here.

BOUNDS = {"south": 47.0, "north": 48.2, "west": -53.3, "east": -52.2}


def rectilinear(*, descending: bool = False, degrees_east: bool = False) -> xarray.Dataset:
    latitudes = numpy.arange(45.0, 50.01, 0.25)
    longitudes = numpy.arange(-56.0, -49.99, 0.25)
    if descending:
        latitudes = latitudes[::-1]
    if degrees_east:
        longitudes = longitudes % 360
    values = numpy.arange(latitudes.size * longitudes.size, dtype="float32").reshape(latitudes.size, longitudes.size)
    dataset = xarray.Dataset(
        {"t2m": (("latitude", "longitude"), values)},
        coords={"latitude": latitudes, "longitude": longitudes},
    )
    dataset["t2m"].attrs["units"] = "K"
    return dataset


def rotated(rows: int = 40, columns: int = 40) -> xarray.Dataset:
    """A curvilinear grid whose axes are skewed, as a rotated pole makes them."""
    row, column = numpy.meshgrid(numpy.arange(rows), numpy.arange(columns), indexing="ij")
    latitudes = 45.0 + 0.15 * row + 0.01 * column
    longitudes = -56.0 + 0.2 * column - 0.01 * row
    dataset = xarray.Dataset(
        {"t2m": (("y", "x"), numpy.full((rows, columns), 280.0, dtype="float32"))},
        coords={"latitude": (("y", "x"), latitudes), "longitude": (("y", "x"), longitudes)},
    )
    dataset["t2m"].attrs["units"] = "K"
    return dataset


def test_a_rotated_grid_is_recognised_as_curvilinear_and_a_plain_one_is_not():
    assert is_curvilinear(rotated()) is True
    assert is_curvilinear(rectilinear()) is False


@pytest.mark.parametrize("descending", [False, True], ids=["ascending", "descending"])
def test_a_regular_grid_is_cropped_by_coordinate_label(descending):
    cropped = crop_to_bbox(rectilinear(descending=descending), BOUNDS)
    assert float(cropped["latitude"].min()) >= BOUNDS["south"]
    assert float(cropped["latitude"].max()) <= BOUNDS["north"]
    assert float(cropped["longitude"].min()) >= BOUNDS["west"]
    assert float(cropped["longitude"].max()) <= BOUNDS["east"]


def test_a_0_360_longitude_axis_is_wrapped_before_the_crop():
    cropped = crop_to_bbox(rectilinear(degrees_east=True), BOUNDS)
    assert cropped["longitude"].size > 0
    assert float(cropped["longitude"].max()) <= BOUNDS["east"]
    assert numpy.all(numpy.diff(cropped["longitude"].values) > 0)


def test_a_rotated_grid_crops_to_an_index_window_instead_of_raising():
    """The regression: this call used to raise the 0-dimensional TypeError."""
    grid = rotated()
    cropped = crop_to_bbox(grid, BOUNDS)
    assert cropped["latitude"].dims == ("y", "x")
    assert cropped["t2m"].shape[0] < grid.sizes["y"] and cropped["t2m"].shape[1] < grid.sizes["x"]
    # The window is the smallest one containing every in-box cell, so it is a
    # superset of the box; what matters is that no in-box cell was dropped.
    inside = (
        (grid["latitude"] >= BOUNDS["south"])
        & (grid["latitude"] <= BOUNDS["north"])
        & (grid["longitude"] >= BOUNDS["west"])
        & (grid["longitude"] <= BOUNDS["east"])
    )
    kept = (
        (cropped["latitude"] >= BOUNDS["south"])
        & (cropped["latitude"] <= BOUNDS["north"])
        & (cropped["longitude"] >= BOUNDS["west"])
        & (cropped["longitude"] <= BOUNDS["east"])
    )
    assert int(kept.values.sum()) == int(inside.values.sum()) > 0


def test_a_rotated_grid_keeps_the_providers_own_cell_values():
    """Index cropping must not resample; a superset window is not a regrid."""
    grid = rotated()
    cropped = crop_to_bbox(grid, BOUNDS)
    corner = (float(cropped["latitude"].values[0, 0]), float(cropped["longitude"].values[0, 0]))
    matches = numpy.isclose(grid["latitude"].values, corner[0]) & numpy.isclose(grid["longitude"].values, corner[1])
    assert matches.sum() == 1


def test_units_normalize_after_a_rotated_crop():
    normalized = normalize_units(crop_to_bbox(rotated(), BOUNDS))
    assert normalized["t2m"].attrs["units"] == "degC"
    assert normalized["t2m"].attrs["original_units"] == "K"
    assert float(normalized["t2m"].max()) == pytest.approx(280.0 - 273.15)


@pytest.mark.parametrize("grid", [rectilinear(), rotated()], ids=["regular", "rotated"])
def test_a_bbox_outside_the_domain_fails_closed_on_either_grid_shape(grid):
    with pytest.raises(GribError, match="empty grid"):
        crop_to_bbox(grid, {"south": -40.0, "north": -39.0, "west": 100.0, "east": 101.0})


# --- message scalars -----------------------------------------------------
#
# HRDPS and RDPS deliver one field per GRIB file, so each field is decoded on
# its own and arrives carrying the scalar level coordinate cfgrib names after
# the GRIB ``typeOfLevel``. Screen temperature is at ``heightAboveGround = 2``
# and wind is at ``heightAboveGround = 10``. Filing both into a single Dataset
# used to raise ``MergeError: conflicting values for variable
# 'heightAboveGround'``, which killed every HRDPS and RDPS run before anything
# could be published.


def _message(name: str, *, level_type: str, level: float) -> xarray.DataArray:
    """One decoded GRIB message: a 2x2 field plus the scalars cfgrib attaches."""
    return xarray.DataArray(
        numpy.zeros((2, 2)),
        dims=("latitude", "longitude"),
        coords={
            "latitude": [47.0, 48.0],
            "longitude": [-53.0, -52.0],
            level_type: level,
            "time": numpy.datetime64("2026-08-30T00:00:00", "ns"),
            "step": numpy.timedelta64(3, "h"),
            "valid_time": numpy.datetime64("2026-08-30T03:00:00", "ns"),
        },
        attrs={"units": "K", "GRIB_typeOfLevel": level_type},
        name=name,
    )


def test_fields_at_different_levels_file_into_one_dataset():
    """The regression: 2 m temperature and 10 m wind must coexist."""
    fields = {
        "temperature": _message("t2m", level_type="heightAboveGround", level=2.0),
        "wind_speed": _message("si10", level_type="heightAboveGround", level=10.0),
    }
    combined = xarray.Dataset({k: strip_message_scalars(v) for k, v in fields.items()})
    assert set(combined.data_vars) == {"temperature", "wind_speed"}


def test_the_level_a_value_was_read_at_survives_as_an_attribute():
    """Dropping the coordinate must not lose which level the value describes."""
    stripped = strip_message_scalars(_message("t2m", level_type="heightAboveGround", level=2.0))
    assert stripped.attrs["level_type"] == "heightAboveGround"
    assert stripped.attrs["level_value"] == 2.0
    assert stripped.attrs["units"] == "K"


def test_message_scalars_are_removed_but_the_grid_is_untouched():
    stripped = strip_message_scalars(_message("t2m", level_type="heightAboveGround", level=2.0))
    assert "heightAboveGround" not in stripped.coords
    assert "step" not in stripped.coords
    assert list(stripped.dims) == ["latitude", "longitude"]
    assert stripped["latitude"].values.tolist() == [47.0, 48.0]


def test_a_rotated_grids_two_dimensional_coordinates_are_not_scalars():
    """The 2-D latitude/longitude pair must never be mistaken for a scalar."""
    stripped = strip_message_scalars(rotated()["t2m"])
    assert stripped["latitude"].ndim == 2
    assert stripped["longitude"].ndim == 2


def test_a_pressure_level_field_records_its_own_level_type():
    stripped = strip_message_scalars(_message("gh", level_type="isobaricInhPa", level=500.0))
    assert stripped.attrs["level_type"] == "isobaricInhPa"
    assert stripped.attrs["level_value"] == 500.0


# --- WMO-key declaration of total cloud ------------------------------------

def _unknown_cloud(**attr_overrides) -> xarray.Dataset:
    """A CWAO-style total-cloud message as cfgrib decodes it: name and units
    ``unknown``, identity carried only in the coded WMO keys."""
    dataset = xarray.Dataset(
        {"unknown": (("latitude", "longitude"), numpy.array([[0.0, 100.0]]))},
        coords={"latitude": numpy.array([47.5]), "longitude": numpy.array([-52.8, -52.7])},
    )
    attrs = {
        "units": "unknown",
        "GRIB_discipline": 0,
        "GRIB_parameterCategory": 6,
        "GRIB_parameterNumber": 1,
        # ecCodes hands the coded surface 1 back as its abbreviation, exactly
        # as observed live; the numeric form is pinned in the adapter test.
        "GRIB_typeOfFirstFixedSurface": "sfc",
        "GRIB_typeOfSecondFixedSurface": 255,
    }
    attrs.update(attr_overrides)
    dataset["unknown"].attrs = attrs
    return dataset


def test_total_cloud_is_declared_from_its_own_wmo_keys():
    dataset = _unknown_cloud()
    assert declare_wmo_total_cloud(dataset) is True
    attrs = dataset["unknown"].attrs
    assert attrs["units"] == "percent"
    assert attrs["original_units"] == "unknown"
    assert "WMO GRIB2 code table 4.2" in attrs["units_basis"]
    # Values are untouched: the declaration names the field, it never scales it.
    assert dataset["unknown"].values.tolist() == [[0.0, 100.0]]


def test_a_field_with_declared_units_is_left_alone():
    dataset = _unknown_cloud(units="%")
    assert declare_wmo_total_cloud(dataset) is False
    assert dataset["unknown"].attrs["units"] == "%"
    assert "units_basis" not in dataset["unknown"].attrs


@pytest.mark.parametrize(
    "override",
    [
        {"GRIB_parameterCategory": 1},
        {"GRIB_parameterNumber": 3},
        {"GRIB_discipline": 2},
        {"GRIB_typeOfFirstFixedSurface": 8},
        {"GRIB_parameterNumber": None},
    ],
)
def test_the_wrong_identity_keys_declare_nothing(override):
    """A 0-100 value range alone is never enough; the coded identity is."""
    dataset = _unknown_cloud(**override)
    assert declare_wmo_total_cloud(dataset) is False
    assert dataset["unknown"].attrs["units"] == "unknown"


def test_normalize_units_keeps_the_declared_basis_record():
    dataset = _unknown_cloud()
    declare_wmo_total_cloud(dataset)
    normalized = normalize_units(dataset)
    attrs = normalized["unknown"].attrs
    assert attrs["units"] == "percent"
    assert attrs["original_units"] == "unknown"


# --- the member axis --------------------------------------------------------
#
# A member is a first-class coordinate. Time, step and valid time are dropped
# from a decoded message because the assembled artifact carries them on its own
# axes; a member identity is recoverable from nothing, so dropping it is how an
# ensemble silently becomes indistinguishable from a deterministic field.


def _member_field(value: float) -> xarray.DataArray:
    """One member's decoded field: a 2x2 grid, no message scalars left on it."""
    return xarray.DataArray(
        numpy.full((2, 2), value, dtype="float32"),
        dims=("latitude", "longitude"),
        coords={"latitude": [47.0, 48.0], "longitude": [-53.0, -52.0]},
        attrs={"units": "percent"},
    )


def test_the_grib_member_number_survives_stripping_the_message_scalars():
    """The regression this closes: ``number`` used to be dropped in silence."""
    message = _message("t2m", level_type="heightAboveGround", level=2.0)
    message = message.assign_coords(number=5)

    stripped = strip_message_scalars(message)

    assert "number" not in stripped.coords
    assert stripped.attrs["grib_number"] == 5
    # The other message scalars still go, and the grid is still untouched.
    assert "step" not in stripped.coords and "valid_time" not in stripped.coords
    assert list(stripped.dims) == ["latitude", "longitude"]


def test_a_message_with_no_member_number_invents_no_identity():
    stripped = strip_message_scalars(_message("t2m", level_type="heightAboveGround", level=2.0))
    assert "grib_number" not in stripped.attrs


def test_three_members_stack_onto_a_string_member_axis_with_one_control():
    stacked = stack_members(
        {"gec00": _member_field(10.0), "gep01": _member_field(20.0), "gep02": _member_field(30.0)},
        control="gec00",
    )

    assert stacked.dims[0] == "member"
    assert stacked.sizes["member"] == 3
    # The provider's own tokens, as text: ``gec00`` and ``01`` are not integers.
    assert stacked["member"].dtype.kind == "U"
    assert stacked["member"].values.tolist() == ["gec00", "gep01", "gep02"]
    assert stacked["control"].dims == ("member",)
    assert stacked["control"].values.tolist() == [True, False, False]
    assert stacked.sel(member="gep02").values.tolist() == [[30.0, 30.0], [30.0, 30.0]]
    assert stacked.attrs["units"] == "percent"


def test_two_members_that_would_collapse_onto_one_identifier_fail_naming_the_values():
    with pytest.raises(GribError, match="collapse") as raised:
        stack_members({1: _member_field(10.0), "1": _member_field(20.0)}, control=None)
    assert "1" in str(raised.value)


def test_a_family_with_no_control_carries_no_flag_on_any_member():
    """Nothing may default the flag onto the lowest member number."""
    stacked = stack_members({"01": _member_field(1.0), "02": _member_field(2.0)}, control=None)

    assert stacked["control"].values.tolist() == [False, False]
    assert not bool(stacked["control"].values.any())


def test_a_run_whose_control_was_not_retrieved_flags_no_member_instead():
    """A partial run, not a complete run of one fewer member."""
    stacked = stack_members({"1": _member_field(1.0), "2": _member_field(2.0)}, control="0")

    assert stacked["member"].values.tolist() == ["1", "2"]
    assert stacked["control"].values.tolist() == [False, False]


def test_the_two_file_aifs_ens_control_lands_on_the_same_member_axis():
    """The ``cf`` file's field is just another entry in the same mapping."""
    perturbed = {str(index): _member_field(float(index)) for index in range(1, 4)}
    stacked = stack_members({"0": _member_field(0.0), **perturbed}, control="0")

    assert stacked.sizes["member"] == 4
    assert stacked["member"].values.tolist() == ["0", "1", "2", "3"]
    assert stacked["control"].values.tolist() == [True, False, False, False]


def test_a_single_member_still_gets_an_axis_rather_than_a_bare_field():
    stacked = stack_members({"gec00": _member_field(5.0)}, control="gec00")
    assert stacked.sizes["member"] == 1
    assert stacked["control"].values.tolist() == [True]


def test_stacking_an_already_stacked_member_field_is_refused():
    stacked = stack_members({"1": _member_field(1.0)}, control=None)
    with pytest.raises(GribError, match="already carries"):
        stack_members({"1": stacked}, control=None)


def test_stacking_no_members_at_all_is_refused():
    with pytest.raises(GribError):
        stack_members({}, control=None)


# --- the averaging window ---------------------------------------------------
#
# GEFS ``TCDC:entire atmosphere`` is never instantaneous: the ``.idx`` labels it
# ``0-3 hour ave fcst`` at f003 and ``18-24 hour ave fcst`` at f024. The window
# is read from that record, never assumed from the lead.


@pytest.mark.parametrize(
    ("label", "hours"),
    [
        ("0-3 hour ave fcst", 3.0),
        ("0-6 hour ave fcst", 6.0),
        ("6-12 hour ave fcst", 6.0),
        ("18-24 hour ave fcst", 6.0),
        ("234-240 hour ave fcst", 6.0),
        ("378-384 hour ave fcst", 6.0),
    ],
)
def test_the_averaging_window_is_read_from_the_producers_own_record(label, hours):
    assert averaging_window_hours(label) == pytest.approx(hours)


@pytest.mark.parametrize(
    "label",
    ["24 hour fcst", "3 hour fcst", "anl", "", "18-24 hour fcst", "ave fcst", "18-18 hour ave fcst"],
    ids=["lead-only", "short-lead", "analysis", "empty", "range-but-not-averaged", "averaged-but-no-range", "zero-window"],
)
def test_a_label_that_states_no_averaging_window_is_refused(label):
    with pytest.raises(GribError, match="averaging window unstated"):
        averaging_window_hours(label)


def test_a_time_averaged_field_carries_its_averaging_window_and_its_label():
    variable = declare_time_average(_member_field(50.0), window_label="18-24 hour ave fcst")

    assert variable.attrs["cell_methods"] == "time: mean"
    assert variable.attrs["averaging_window_hours"] == pytest.approx(6.0)
    assert variable.attrs["averaging_window_basis"] == "18-24 hour ave fcst"
    assert variable.attrs["units"] == "percent"
    # The declaration names the quantity; it never rescales the values.
    assert variable.values.tolist() == [[50.0, 50.0], [50.0, 50.0]]


def test_a_field_whose_record_states_no_averaging_window_is_not_stamped():
    variable = _member_field(50.0)
    with pytest.raises(GribError, match="averaging window unstated"):
        declare_time_average(variable, window_label="24 hour fcst")
    assert "cell_methods" not in variable.attrs
    assert "averaging_window_hours" not in variable.attrs
