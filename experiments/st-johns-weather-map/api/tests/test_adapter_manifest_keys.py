"""Every adapter manifest speaks catalogue keys, and the split ones stay split.

The defect: three adapters declared a field called ``total_cloud`` and two of
them were not the same quantity. HRDPS cloud is opacity-weighted, GFS cloud is a
geometric maximum-random overlap, GEFS cloud is a six-hour mean, and a METAR's
is one observer's fraction of the celestial dome. Nothing stopped the collision
because a manifest name meant only what its author remembered it to mean.

These tests import the adapter modules for real and read the manifests they
declare, so a re-keying that is right in the catalogue and wrong in an adapter
fails here rather than at the next live run.

Spec-Refs: openspec/changes/field-catalogue-and-families/specs/field-catalogue/spec.md
"""

from __future__ import annotations

import pytest

from ingest.manifest import ManifestError, RequiredField, RunManifest
from registry import fields as catalogue


def manifest_keys(manifest: RunManifest) -> set[str]:
    return {field.name for field in manifest.fields}


def test_the_metar_and_taf_manifests_declare_the_observed_dome_cover():
    from ingest.adapters.awc import METAR_MANIFEST, TAF_MANIFEST

    for manifest in (METAR_MANIFEST, TAF_MANIFEST):
        assert "total_cloud_okta" in manifest_keys(manifest)
        assert "total_cloud" not in manifest_keys(manifest)
    assert catalogue.field("total_cloud_okta").comparability_group == "observed_dome"


def test_the_eccc_datamart_manifests_declare_the_opacity_weighted_cover():
    from ingest.adapters.eccc_datamart import GDPS_VARS, HRDPS_VARS, RDPS_VARS, manifest_for

    assert "total_cloud_opacity" in HRDPS_VARS
    assert "total_cloud_opacity" in RDPS_VARS
    assert "total_cloud_opacity" not in GDPS_VARS  # GDPS publishes no cloud on Datamart
    keys = manifest_keys(manifest_for("eccc-hrdps", HRDPS_VARS))
    assert "total_cloud_opacity" in keys
    assert "total_cloud" not in keys
    assert catalogue.field("total_cloud_opacity").comparability_group == "opacity_weighted_column"


def test_the_gfs_manifest_declares_the_geometric_cover():
    from ingest.adapters.noaa_s3 import GFS_MANIFEST

    keys = manifest_keys(GFS_MANIFEST)
    assert "total_cloud_geometric" in keys
    assert "total_cloud" not in keys
    assert catalogue.field("total_cloud_geometric").comparability_group == "geometric_column"


def test_the_geomet_bindings_declare_the_opacity_weighted_cover():
    from ingest.adapters.eccc_geomet import HRDPS_SURFACE, RDPS_SURFACE

    for bindings in (HRDPS_SURFACE, RDPS_SURFACE):
        variables = {binding.variable for binding in bindings}
        assert "total_cloud_opacity" in variables
        assert "total_cloud" not in variables


def test_the_global_feeds_map_their_cloud_onto_the_geometric_key():
    from ingest.adapters.dwd_icon import DWD_GRIB_RENAME, DWD_VARS
    from ingest.adapters.ecmwf_opendata import ECMWF_GRIB_RENAME, ECMWF_PARAM_MAP

    assert DWD_VARS["total_cloud_geometric"] == "clct"
    assert DWD_GRIB_RENAME["clct"] == "total_cloud_geometric"
    assert ECMWF_PARAM_MAP["tcc"] == "total_cloud_geometric"
    assert ECMWF_GRIB_RENAME["tcc"] == "total_cloud_geometric"


def test_the_three_column_cloud_keys_are_never_comparable_with_one_another():
    keys = ("total_cloud_opacity", "total_cloud_geometric", "total_cloud_mean_6h")
    for left in keys:
        for right in keys:
            verdict = catalogue.comparability(left, right)
            if left == right:
                assert verdict.comparable, (left, right)
            else:
                assert not verdict.comparable, (left, right)
                assert verdict.reason == "definition"


def test_every_manifest_key_every_adapter_declares_resolves_in_the_catalogue():
    """Imports the adapter package for its registration side effects, then walks
    every manifest object the modules hold. A key that does not resolve would
    have raised at import; this asserts the import actually happened and the
    keys are catalogue keys rather than lookalikes."""
    import importlib
    import pkgutil

    import ingest.adapters as adapters

    checked: set[str] = set()
    for info in pkgutil.iter_modules(adapters.__path__):
        module = importlib.import_module(f"ingest.adapters.{info.name}")
        for value in vars(module).values():
            manifests: tuple[RunManifest, ...] = ()
            if isinstance(value, RunManifest):
                manifests = (value,)
            elif isinstance(value, tuple) and value and all(isinstance(item, RunManifest) for item in value):
                manifests = value
            for manifest in manifests:
                for name in manifest_keys(manifest):
                    assert catalogue.has_field(name), f"{info.name} declares uncatalogued {name!r}"
                    checked.add(name)
    assert checked, "no adapter manifests were reachable to check"


def test_a_manifest_that_names_an_uncatalogued_key_cannot_be_built():
    with pytest.raises(ManifestError, match="uncatalogued_field"):
        RunManifest(source_id="eccc-hrdps", fields=(RequiredField("cloud", "percent"),))
