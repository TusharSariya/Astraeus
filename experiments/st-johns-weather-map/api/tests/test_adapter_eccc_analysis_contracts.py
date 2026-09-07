"""Contract and failure proof for selected ECCC analysis WCS products."""

from datetime import datetime, timedelta, timezone
import json
import re
from pathlib import Path

import pytest

from ingest.adapters.eccc_analysis_contracts import DEFERRED_PATHS, PRODUCT_CONTRACTS, fetch_unresolved_product, product_contract
from ingest.adapters.eccc_geomet_wcs import GRID_CONTRACTS, WCSResponseError, grid_contract_for


from test_adapter_eccc_geomet_wcs import FixtureHTTP, RUN, VALID


class ChemistryFixtureHTTP(FixtureHTTP):
    """RDAQA fixture mirrors its absent native reference-time dimension."""

    def download(self, url, destination, **kwargs):
        size = super().download(url, destination, **kwargs)
        if "service=wms" in url.lower() and "RDAQA" in url:
            payload = re.sub(rb"<Dimension name='reference_time'.*?</Dimension>", b"", destination.read_bytes())
            destination.write_bytes(payload)
            return len(payload)
        return size


EXPECTED = {
    "raqdps_hourly": ("eccc-raqdps", 12, timedelta(hours=1)),
    "raqdps_statistics": ("eccc-raqdps", 2, timedelta(hours=24)),
    "rdaqa_preliminary": ("eccc-rdaqa", 6, timedelta(hours=1)),
    "rdaqa_final": ("eccc-rdaqa", 6, timedelta(hours=1)),
    "rdaqa_smoke": ("eccc-rdaqa", 2, timedelta(hours=1)),
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
        grid_name = "rdaqa" if name.startswith("rdaqa_") else ("raqdps" if name.startswith("raqdps_") else name)
        assert grid_contract_for(field.coverage_id) == GRID_CONTRACTS[grid_name]


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


def test_selected_air_quality_inventory_is_exhaustive_and_preserves_provider_spelling():
    raqdps = {field.coverage_id for field in product_contract("raqdps_hourly").fields + product_contract("raqdps_statistics").fields}
    assert raqdps == {
        "RAQDPS.SFC_PM2.5", "RAQDPS.EATM_PM2.5", "RAQDPS.SFC_PM10", "RAQDPS.EATM_PM10",
        "RAQDPS.SFC_O3", "RAQDPS.SFC_NO", "RAQDPS.SFC_NO2", "RAQDPS.SFC_SO2",
        "RAQDPS.Sfc_PM2.5-WildfireSmokePlume", "RAQDPS.EAtm_PM2.5-WildfireSmokePlume",
        "RAQDPS.Sfc_PM10-WildfireSmokePlume", "RAQDPS.EAtm_PM10-WildfireSmokePlume",
        "RAQDPS.Sfc_PM2.5-WildireSmokePlume-DAvg", "RAQDPS.Sfc_PM2.5-WildireSmokePlume-DMax",
    }
    assert {field.coverage_id for field in product_contract("rdaqa_preliminary").fields} == {
        f"RDAQA-Prelim_10km_{name}" for name in ("PM2.5", "PM10", "O3", "NO", "NO2", "SO2")
    }
    assert {field.coverage_id for field in product_contract("rdaqa_final").fields} == {
        f"RDAQA_10km_{name}" for name in ("PM2.5", "PM10", "O3", "NO", "NO2", "SO2")
    }
    assert {field.coverage_id for field in product_contract("rdaqa_smoke").fields} == {
        "RDAQA-FW_10km_PM2.5", "RDAQA-FW_10km_PM10"
    }


def test_all_28_fields_declare_phase_vertical_scope_and_statistic_window():
    products = ("raqdps_hourly", "raqdps_statistics", "rdaqa_preliminary", "rdaqa_final", "rdaqa_smoke")
    rows = [(product_contract(name), field) for name in products for field in product_contract(name).fields]
    assert len(rows) == 28
    assert all(contract.product_phase for contract, _field in rows)
    assert all(field.vertical_scope in {"surface", "entire_atmosphere"} for _contract, field in rows)
    assert all(
        field.statistic_window_hours == (24 if contract.product_phase == "forecast_statistic" else None)
        for contract, field in rows
    )


def test_live_receipt_covers_every_selected_field_and_actual_http_time():
    path = Path(__file__).parent / "fixtures/eccc_geomet_wcs/raqdps-rdaqa-2026-09-06.receipt.json"
    receipt = json.loads(path.read_text())
    selected = {field.coverage_id for name in ("raqdps_hourly", "raqdps_statistics", "rdaqa_preliminary", "rdaqa_final", "rdaqa_smoke") for field in product_contract(name).fields}
    assert {row["coverage_id"] for row in receipt["rows"]} == selected
    assert {row["coverage_id"] for row in receipt["comparisons"]} == selected
    assert sum(row["all_cells_compared"] for row in receipt["comparisons"]) == 28_980
    assert all(row["mismatches"] == 0 and row["harness_http_status"] == 200 for row in receipt["comparisons"])
    assert all(row["headers"] and row["raw"]["bytes"] > 0 and len(row["raw"]["sha256"]) == 64 for row in receipt["rows"])
    assert all(datetime.fromisoformat(row["http_completed_at"]).tzinfo is not None for row in receipt["rows"])
    assert receipt["finite_operation_cap_bytes"] == 64 << 20
    assert receipt["received_bytes"] == 664_819
    assert all(row["group_complete"] is False and row["group_qc_passed"] is True for row in receipt["rows"])
    assert all(row["product_phase"] and row["vertical_scope"] in {"surface", "entire_atmosphere"} for row in receipt["rows"])
    assert all(
        row["statistic_window_hours"] == (24 if row["product"] == "raqdps_statistics" else None)
        for row in receipt["rows"]
    )
    by_product = {}
    for row in receipt["rows"]:
        by_product.setdefault(row["product"], set()).add((row["valid_time"], row["run_time"]))
    assert all(len(times) == 1 for times in by_product.values())
    assert by_product["raqdps_hourly"] != by_product["raqdps_statistics"]
    assert path.stat().st_size < 100_000


def test_full_product_fetch_uses_validator_owned_nonpublishable_verdict(tmp_path):
    from ingest.adapters.eccc_geomet_wcs import GeoMetWCSClient
    from test_adapter_eccc_geomet_wcs import FixtureHTTP, RUN, VALID
    client = GeoMetWCSClient(client=ChemistryFixtureHTTP(tmp_path), base_url="https://fixture.invalid/geomet", clock=lambda: VALID)
    result = fetch_unresolved_product(client, "rdaqa_smoke", valid_time=VALID, reference_time=None, workdir=tmp_path)
    assert result.complete is False and result.qc_passed is True
    assert "canonical contracts are absent" in result.notes
    assert result.retrieved_at == VALID
    assert result.run_time is None
    assert all(artifact.provenance["run_time"] is None for artifact in result.artifacts)
    assert len(result.artifacts) == 2
    assert all(artifact.provenance["operational"] is False for artifact in result.artifacts)
    assert all(artifact.provenance["product_phase"] == "firework_contribution_analysis" for artifact in result.artifacts)
    assert all(artifact.provenance["vertical_scope"] == "surface" for artifact in result.artifacts)

@pytest.mark.parametrize(
    ("name", "field_count"),
    [("raqdps_hourly", 12), ("raqdps_statistics", 2), ("rdaqa_preliminary", 6),
     ("rdaqa_final", 6), ("rdaqa_smoke", 2)],
)
def test_every_coherent_product_group_fetches_all_fields_before_refusal(tmp_path, name, field_count):
    from ingest.adapters.eccc_geomet_wcs import GeoMetWCSClient
    from test_adapter_eccc_geomet_wcs import FixtureHTTP, RUN, VALID

    client = GeoMetWCSClient(
        client=ChemistryFixtureHTTP(tmp_path), base_url="https://fixture.invalid/geomet", clock=lambda: VALID
    )
    result = fetch_unresolved_product(
        client, name, valid_time=VALID, reference_time=RUN if name.startswith("raqdps") else None, workdir=tmp_path / name
    )
    assert len(result.artifacts) == field_count
    assert result.complete is False
    assert result.retrieved_at == VALID
    assert len({artifact.provenance["valid_time"] for artifact in result.artifacts}) == 1
    assert result.run_time == (RUN if name.startswith("raqdps") else None)
    assert all(artifact.provenance["operational"] is False for artifact in result.artifacts)


def test_product_group_with_different_selected_times_is_refused(tmp_path, monkeypatch):
    from ingest.contract import Artifact
    from ingest.adapters import eccc_geomet_wcs

    calls = 0
    def fake_fetch(_client, field, **kwargs):
        nonlocal calls
        calls += 1
        path = tmp_path / f"{calls}.zip"
        path.write_bytes(b"fixture")
        hour = calls
        return Artifact(field.variable, "application/zarr+zip", path, {
            "valid_time": f"2026-09-05T{hour:02d}:00:00+00:00",
            "run_time": "2026-09-05T00:00:00+00:00",
            "http_completed_at": f"2026-09-05T12:00:0{calls}+00:00",
        })

    monkeypatch.setattr(eccc_geomet_wcs, "fetch_artifact", fake_fetch)
    result = fetch_unresolved_product(
        object(), "raqdps_statistics", valid_time=VALID, reference_time=RUN, workdir=tmp_path
    )
    assert result.complete is False
    assert "disagree on product time identity" in result.notes


@pytest.mark.parametrize(("name", "valid", "reference", "message"), [
    ("hrdpa", VALID, None, "only RAQDPS/RDAQA"),
    ("rdaqa_final", VALID, RUN, "analysis"),
    ("rdaqa_preliminary", VALID, RUN, "analysis"),
    ("rdaqa_smoke", VALID, RUN, "analysis"),
    ("raqdps_hourly", VALID, None, "reference time"),
    ("raqdps_statistics", VALID, RUN.replace(tzinfo=None), "reference time"),
    ("raqdps_hourly", VALID, VALID + timedelta(hours=1), "cannot follow"),
    ("rdaqa_final", VALID.replace(tzinfo=None), None, "valid time"),
])
def test_invalid_chemistry_identity_fails_before_provider_access(tmp_path, name, valid, reference, message):
    client = ChemistryFixtureHTTP(tmp_path)
    with pytest.raises(ValueError, match=message):
        fetch_unresolved_product(client, name, valid_time=valid, reference_time=reference, workdir=tmp_path)
    assert client.urls == []
