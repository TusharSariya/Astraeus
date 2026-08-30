import pytest

from weather_api.storage import ArtifactRevision, FixtureArtifactStore, LOCAL_STORAGE_CAP_BYTES, probe_normalized_array


def test_atomic_restart_keeps_previous_complete_run_visible():
    store = FixtureArtifactStore()
    previous = ArtifactRevision("run-1", 1024, complete=True, qc_passed=True)
    store.stage("hrdps", previous)
    store.publish("hrdps")
    store.stage("hrdps", ArtifactRevision("run-2", 2048, complete=False, qc_passed=False))
    assert store.visible["hrdps"] == previous
    store.restart()
    assert store.visible["hrdps"] == previous
    assert store.staged == {}


@pytest.mark.parametrize(
    "artifact",
    [ArtifactRevision("partial", 10, complete=False, qc_passed=True), ArtifactRevision("failed-qc", 10, complete=True, qc_passed=False)],
)
def test_partial_or_failed_qc_artifact_cannot_be_published(artifact):
    store = FixtureArtifactStore()
    store.stage("hrdps", artifact)
    with pytest.raises(ValueError):
        store.publish("hrdps")
    assert "hrdps" not in store.visible


def test_hard_25_gib_storage_cap_is_enforced_before_staging():
    store = FixtureArtifactStore()
    store.stage("context", ArtifactRevision("context-1", LOCAL_STORAGE_CAP_BYTES, True, True))
    with pytest.raises(ValueError, match="25 GiB"):
        store.stage("extra", ArtifactRevision("extra-1", 1, True, True))


def test_numeric_probe_equals_normalized_array_value():
    normalized = [[1.25, 2.5], [3.75, 5.0]]
    assert probe_normalized_array(normalized, 1, 0) == normalized[1][0] == 3.75
    with pytest.raises(IndexError):
        probe_normalized_array(normalized, -1, 0)
