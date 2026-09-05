"""Contract and failure proof for selected ECCC analysis WCS products."""

from datetime import timedelta

import pytest

from ingest.adapters.eccc_analysis_contracts import DEFERRED_PATHS, PRODUCT_CONTRACTS, product_contract
from ingest.adapters.eccc_geomet_wcs import GRID_CONTRACTS, WCSResponseError, grid_contract_for


EXPECTED = {
    "raqdps": ("eccc-raqdps", 4, timedelta(hours=1)),
    "rdaqa": ("eccc-rdaqa", 2, timedelta(hours=1)),
    "hrdpa": ("eccc-hrdpa", 1, timedelta(hours=6)),
    "rdpa": ("eccc-rdpa", 1, timedelta(hours=6)),
    "hrepa": ("eccc-hrepa", 2, timedelta(hours=6)),
    "hrdlps": ("eccc-hrdlps", 2, None),
    "caldas": ("eccc-caldas", 2, timedelta(hours=3)),
}


def test_every_selected_product_has_an_isolated_field_time_quality_contract():
    assert set(PRODUCT_CONTRACTS) == set(EXPECTED)
    for name, (source_id, field_count, cadence) in EXPECTED.items():
        contract = product_contract(name)
        assert contract.source_id == source_id
        assert len(contract.fields) == field_count
        assert contract.native_cadence == cadence
        assert contract.time_identity
        assert contract.quality_semantics.startswith("unknown")
        assert contract.operational is False
        assert len({field.coverage_id for field in contract.fields}) == field_count


def test_current_smoke_paths_do_not_revive_standalone_firework():
    all_ids = {field.coverage_id for contract in PRODUCT_CONTRACTS.values() for field in contract.fields}
    assert "RAQDPS-FW" not in all_ids
    assert "RAQDPS.Sfc_PM2.5-WildfireSmokePlume" in all_ids
    assert "RDAQA-FW_10km_PM2.5" in all_ids


@pytest.mark.parametrize("name", EXPECTED)
def test_each_selected_coverage_keeps_its_product_grid_identity(name):
    contract = product_contract(name)
    for field in contract.fields:
        assert grid_contract_for(field.coverage_id) == GRID_CONTRACTS[name]


def test_unknown_products_and_unselected_coverages_fail_closed():
    with pytest.raises(ValueError, match="unsupported ECCC analysis product"):
        product_contract("standalone-firework")
    with pytest.raises(WCSResponseError, match="no numeric grid contract"):
        grid_contract_for("UNSELECTED_COVERAGE")


def test_non_wcs_and_superseded_paths_are_explicitly_non_operational():
    assert set(DEFERRED_PATHS) == {
        "wildfire_hotspots", "integrated_nowcasting", "cap_alerts",
        "thunderstorm_outlook", "hurricane_products", "standalone_firework",
    }
    assert all(not path.operational and path.reason for path in DEFERRED_PATHS.values())
    assert "superseded" in DEFERRED_PATHS["standalone_firework"].reason


def test_rdpa_does_not_inherit_rdps_crs_or_units():
    field = product_contract("rdpa").fields[0]
    assert field.disposition == "metadata-only-unresolved-epsg-102978"
    assert GRID_CONTRACTS["rdpa"].spacing_degrees == 0.090298
