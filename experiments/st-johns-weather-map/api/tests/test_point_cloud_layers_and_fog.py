"""What ``/point`` says about METAR cloud layers and fog, and what it withholds.

Two rules are pinned here. A flag-coded cloud cover is served as the meaning
the artifact declared for the flag (``"OVC"``), never as a bare integer, and a
flag outside the declared table is None. And the present-weather codes are
sampled only to derive ``fog_state``: they are never served raw, and with no
provider fog diagnostic the derived state is only ever ``evidence_present``
or ``unknown`` - an absent FG code is not a finding of no fog.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import numpy
import pytest
import xarray

from tests.test_live_sampling import LATITUDE, LONGITUDE, STAMP, StubStore, artifact, rectilinear
from weather_api.store import CLOUD_LAYER_VARIABLES, FOG_DERIVATION, FOG_DERIVATION_VERSION, FOG_INPUTS, live_point_fields

UTC = timezone.utc
DIMS = ("valid_time", "latitude", "longitude")

COVER_ATTRS = {
    "units": "code",
    "original_units": "code",
    "flag_values": list(range(10)),
    "flag_meanings": "SKC CLR NSC FEW SCT BKN OVC VV OVX CAVOK",
}
FLAG_ATTRS = {"units": "flag", "original_units": "present_weather_group", "flag_values": [0, 1], "flag_meanings": "absent present"}


def metar_dataset(
    *,
    fog: float = 0.0,
    vicinity: float = 0.0,
    mist: float = 0.0,
    visibility: float = 6437.0,
    cover_code: float = 6.0,
    base_m: float = 243.84,
) -> xarray.Dataset:
    """A one-step CYYT-style point artifact on the rectilinear test grid."""
    base = rectilinear(value=17.0)
    shape = base["temperature_2m"].shape

    def full(value: float) -> numpy.ndarray:
        return numpy.full(shape, value, dtype="float64")

    return base.assign(
        {
            "visibility": (DIMS, full(visibility), {"units": "m", "original_units": "SM"}),
            "cloud_layer_1_cover_code": (DIMS, full(cover_code), COVER_ATTRS),
            "cloud_layer_1_cover": (DIMS, full(100.0), {"units": "percent", "original_units": "okta_fraction"}),
            "cloud_layer_1_base": (DIMS, full(base_m), {"units": "m", "original_units": "ft"}),
            "cloud_layer_2_cover_code": (DIMS, full(numpy.nan), COVER_ATTRS),
            "weather_fog_code": (DIMS, full(fog), FLAG_ATTRS),
            "weather_fog_vicinity_code": (DIMS, full(vicinity), FLAG_ATTRS),
            "weather_mist_code": (DIMS, full(mist), FLAG_ATTRS),
        }
    )


def metar_artifact() -> Any:
    item = artifact(source_id="awc-metar-speci", logical_name="surface")
    item.provenance.update(
        {
            "sha256": "unused-in-stub",
            "adapter_version": "awc-metar-v2",
            "original_units": {"cloud_layer_1_base": "ft", "visibility": "SM"},
        }
    )
    return item


def point_fields(dataset: xarray.Dataset) -> dict[str, Any]:
    store = StubStore([(metar_artifact(), dataset)])
    fields, _consensus, _sources = live_point_fields(store, LATITUDE, LONGITUDE, STAMP)
    by_name: dict[str, Any] = {}
    for item in fields:
        by_name.setdefault(item.field, item)
    return by_name


@pytest.fixture(autouse=True)
def _registered_derivation_methods(derivation_registry):
    """Every derivation served here is an enabled derivation-registry entry.

    A ``derived_here`` value is refused unless its method is registered and
    enabled, so the entries are stood up for this module rather than each
    test being about the registry.
    """

# --- fog_state is derived, disclosed, and never ``not_indicated`` ------------

def test_an_fg_code_yields_fog_evidence_with_the_derivation_disclosed():
    fields = point_fields(metar_dataset(fog=1.0))
    fog = fields["fog_state"]
    assert fog.value == "evidence_present"
    assert fog.provenance.derivation == FOG_DERIVATION
    assert fog.provenance.derivation_version == FOG_DERIVATION_VERSION == "fog-state-present-weather-v1"
    assert fog.provenance.normalized_units == "category"
    assert fog.provenance.source_id == "awc-metar-speci"
    assert fog.provenance.data_mode.value == "live"


def test_an_absent_fg_code_is_unknown_not_a_finding_of_no_fog():
    """No provider diagnostic exists, so ``not_indicated`` cannot be earned."""
    fog = point_fields(metar_dataset(fog=0.0, visibility=16093.0))["fog_state"]
    assert fog.value == "unknown"


def test_a_missing_fog_code_is_unknown():
    fog = point_fields(metar_dataset(fog=numpy.nan, vicinity=numpy.nan))["fog_state"]
    assert fog.value == "unknown"


def test_vicinity_fog_alone_counts_as_fog_evidence():
    """VCFG: fog near, not at, the station. Counted as evidence (orchestrator
    default, disclosed in the derivation string)."""
    fog = point_fields(metar_dataset(fog=0.0, vicinity=1.0))["fog_state"]
    assert fog.value == "evidence_present"
    assert "VCFG" in fog.provenance.derivation


def test_mist_alone_is_not_fog_evidence():
    fog = point_fields(metar_dataset(fog=0.0, mist=1.0))["fog_state"]
    assert fog.value == "unknown"


def test_the_live_fog_state_is_never_not_indicated():
    for kwargs in ({"fog": 0.0}, {"fog": 0.0, "vicinity": 0.0, "mist": 0.0, "visibility": 30000.0}, {"fog": numpy.nan}):
        assert point_fields(metar_dataset(**kwargs))["fog_state"].value in {"evidence_present", "unknown"}


def test_raw_present_weather_codes_are_never_served_as_fields():
    fields = point_fields(metar_dataset(fog=1.0, vicinity=1.0, mist=1.0))
    assert FOG_INPUTS.isdisjoint(fields)
    assert "fog_state" in fields


# --- cloud layers are served as retrieved, flag meaning and all --------------

def test_a_cover_flag_is_served_as_its_declared_meaning_string():
    fields = point_fields(metar_dataset(cover_code=6.0))
    cover = fields["cloud_layer_1_cover_code"]
    assert cover.value == "OVC"
    assert cover.provenance.normalized_units == "code"
    assert cover.provenance.derivation is None, "read as published, not derived"
    assert fields["cloud_layer_1_cover"].value == 100.0


def test_a_flag_outside_the_declared_table_is_none_not_an_integer():
    cover = point_fields(metar_dataset(cover_code=42.0))["cloud_layer_1_cover_code"]
    assert cover.value is None


def test_a_cloud_base_carries_its_provider_unit_in_provenance():
    base = point_fields(metar_dataset(base_m=243.84))["cloud_layer_1_base"]
    assert base.value == pytest.approx(243.84)
    assert base.provenance.normalized_units == "m"
    assert base.provenance.original_units == "ft"


def test_an_unreported_layer_slot_is_a_null_reading_not_a_zero():
    slot_two = point_fields(metar_dataset())["cloud_layer_2_cover_code"]
    assert slot_two.value is None


def test_no_low_middle_high_strata_are_derived_from_the_layers():
    """Bucketing is withheld pending an owner decision; nothing here does it."""
    fields = point_fields(metar_dataset())
    assert {"cloud_low", "cloud_middle", "cloud_high"}.isdisjoint(fields)


def test_every_per_slot_variable_maps_to_a_field_of_the_same_name():
    from weather_api.store import FIELD_BY_VARIABLE

    assert len(CLOUD_LAYER_VARIABLES) == 18
    for name in CLOUD_LAYER_VARIABLES:
        assert FIELD_BY_VARIABLE[name] == name


def test_the_derived_fog_state_keeps_the_sampled_cell_lineage():
    fog = point_fields(metar_dataset(fog=1.0))["fog_state"]
    assert fog.provenance.sampled_latitude is not None
    assert fog.provenance.sample_method == "rectilinear"
    assert fog.provenance.valid_time == datetime(2026, 8, 30, 3, 0, tzinfo=UTC)
