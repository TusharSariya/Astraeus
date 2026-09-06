from __future__ import annotations

from pathlib import Path

import numpy
import pytest
import xarray

from ingest.adapters.goes_abi_dmw import DMWF_BANDS, DMWVF_BANDS, DMWF_PRODUCT, parse_dmw_key, read_band_vectors
from ingest.adapters.goes_glm import FieldOfViewRefusal, parse_glm_key, read_detections

BOUNDS = {"south": 45.0, "west": -58.0, "north": 50.5, "east": -46.0}


def test_dmw_preserves_good_and_degraded_vectors_with_flags(tmp_path: Path):
    path = tmp_path / "dmw.nc"
    size = 3
    dataset = xarray.Dataset(
        {
            "lat": ("nMeasures", [47.5, 48.0, 10.0]), "lon": ("nMeasures", [-52.7, -53.0, 10.0]),
            "wind_speed": ("nMeasures", [12.0, 15.0, 20.0], {"valid_range": [3.0, 155.0]}),
            "wind_direction": ("nMeasures", [180.0, 200.0, 90.0], {"valid_range": [0.0, 360.0]}),
            "pressure": ("nMeasures", [700.0] * size), "temperature": ("nMeasures", [250.0] * size),
            "DQF": ("nMeasures", [0, 4, 0], {"flag_values": [0, 4], "flag_meanings": "good_wind_qf pressure_failure_qf"}),
            "local_zenith_angle": ("nMeasures", [58.0] * size), "solar_zenith_angle": ("nMeasures", [70.0] * size),
            "time": ("nMeasures", numpy.array(["2026-09-05T20:00:21", "2026-09-05T20:00:22", "2026-09-05T20:00:23"], dtype="datetime64[ns]")),
        },
        attrs={"time_coverage_start": "2026-09-05T20:00:20.7Z", "time_coverage_end": "2026-09-05T20:09:51.5Z", "platform_ID": "G19", "dataset_name": "OR_ABI-L2-DMWF-M6C14_G19_s20262482000207_e20262482009515_c20262482024344.nc", "title": "ABI L2 Derived Motion Winds"},
    )
    dataset.to_netcdf(path)
    features, stats = read_band_vectors(path, "C14", bounds=BOUNDS)
    assert len(features) == 2 and stats["in_box_good_vectors"] == 1
    assert [item["properties"]["dqf_meaning"] for item in features] == ["good_wind_qf", "pressure_failure_qf"]


def _glm(path: Path, *, visible: bool = True) -> Path:
    outside_lat, outside_lon = 10.0, 10.0
    variables = {
        "flash_lat": ("number_of_flashes", [outside_lat]), "flash_lon": ("number_of_flashes", [outside_lon]),
        "flash_energy": ("number_of_flashes", [1e-12]), "flash_area": ("number_of_flashes", [100.0]),
        "flash_quality_flag": ("number_of_flashes", [0], {"flag_values": [0, 1], "flag_meanings": "good_quality_qf degraded_qf"}),
        "flash_id": ("number_of_flashes", [1]),
        "flash_time_offset_of_first_event": ("number_of_flashes", numpy.array(["2026-09-05T20:30:20"], dtype="datetime64[ns]")),
        "flash_time_offset_of_last_event": ("number_of_flashes", numpy.array(["2026-09-05T20:30:21"], dtype="datetime64[ns]")),
        "group_lat": ("number_of_groups", [outside_lat]), "group_lon": ("number_of_groups", [outside_lon]),
        "group_energy": ("number_of_groups", [1e-12]), "group_area": ("number_of_groups", [100.0]),
        "group_quality_flag": ("number_of_groups", [0], {"flag_values": [0], "flag_meanings": "good_quality_qf"}),
        "group_id": ("number_of_groups", [2]), "group_parent_flash_id": ("number_of_groups", [1]),
        "group_time_offset": ("number_of_groups", numpy.array(["2026-09-05T20:30:20"], dtype="datetime64[ns]")),
        "event_lat": ("number_of_events", [outside_lat]), "event_lon": ("number_of_events", [outside_lon]),
        "event_energy": ("number_of_events", [1e-12]), "event_id": ("number_of_events", [3]),
        "event_parent_group_id": ("number_of_events", [2]),
        "event_time_offset": ("number_of_events", numpy.array(["2026-09-05T20:30:20"], dtype="datetime64[ns]")),
        "lat_field_of_view_bounds": ("bounds", [57.6, -57.6] if visible else [20.0, -20.0]),
        "lon_field_of_view_bounds": ("bounds", [-156.0, 6.0] if visible else [-20.0, 20.0]),
    }
    xarray.Dataset(variables, attrs={"time_coverage_start": "2026-09-05T20:30:20Z", "time_coverage_end": "2026-09-05T20:30:40Z", "platform_ID": "G19", "dataset_name": "OR_GLM-L2-LCFA_G19_s20262482030200_e20262482030400_c20262482030420.nc"}).to_netcdf(path)
    return path


def test_glm_empty_box_is_complete_observation_with_global_counts(tmp_path: Path):
    features, stats = read_detections(_glm(tmp_path / "glm.nc"), bounds=BOUNDS)
    assert features == []
    assert stats["counts"] == {"flashes": 1, "in_box_flashes": 0, "in_box_good_flashes": 0, "groups": 1, "in_box_groups": 0, "in_box_good_groups": 0, "events": 1, "in_box_events": 0}


def test_glm_refuses_empty_answer_when_file_does_not_view_box(tmp_path: Path):
    with pytest.raises(FieldOfViewRefusal):
        read_detections(_glm(tmp_path / "glm.nc", visible=False), bounds=BOUNDS)


def test_point_product_key_parsers_are_product_and_platform_exact():
    dmw = "ABI-L2-DMWF/2026/248/20/OR_ABI-L2-DMWF-M6C14_G19_s20262482000207_e20262482009515_c20262482024344.nc"
    assert parse_dmw_key(dmw) == (DMWF_PRODUCT, "C14", "20262482000207")
    assert parse_dmw_key(dmw.replace("G19", "G18")) is None
    glm = "GLM-L2-LCFA/2026/248/20/OR_GLM-L2-LCFA_G19_s20262482030200_e20262482030400_c20262482030420.nc"
    assert parse_glm_key(glm) == "20262482030200"
    assert parse_glm_key(glm.replace("G19", "G18")) is None


def test_complete_dmw_band_inventories_match_the_public_product_hierarchy():
    assert DMWF_BANDS == ("C02", "C07", "C08", "C09", "C10", "C14")
    assert DMWVF_BANDS == ("C08",)
