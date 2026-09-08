"""GOV-SPEC-004/006: GEFS selected-lead and API-first delivery contracts."""
from datetime import timedelta

import pytest

from test_gefs_query import RUN, discovery_body
from weather_api.gefs_delivery import point_capabilities
from weather_api.gefs_query import GEFSQueryCoordinator, GEFSQueryService, demand_operation_bounds, declared_members


def coordinator(*, discover=None, clock=lambda: 0):
    calls, loads = [], []
    def index(url):
        calls.append(url)
        return (discover or discovery_body)(url)
    service = GEFSQueryService(lambda key: loads.append(key),
        preflight=lambda _: demand_operation_bounds())
    reader = GEFSQueryCoordinator(service, now=lambda: RUN + timedelta(hours=6),
        clock=clock, discover_index=index)
    return reader, calls, loads


def test_selected_run_has_only_exact_native_lead_and_no_payload_or_previous_probe():
    reader, calls, loads = coordinator()
    selected = RUN + timedelta(hours=10, minutes=17)
    candidate = reader.selected_lead_run(selected)
    assert candidate.provider_run_id == "2026090618"
    assert candidate.run_time == RUN + timedelta(hours=6)
    assert candidate.detail["lead_hours"] == 3
    assert candidate.detail["valid_times"] == (RUN + timedelta(hours=9),)
    assert candidate.detail["members_declared"] == declared_members()
    assert candidate.detail["availability_scope"] == "selected_lead_control_index_only"
    assert candidate.urls == calls and calls[0].endswith("f003.idx")
    assert len(calls) == 1 and loads == []


def test_failed_latest_exposes_only_proven_predecessor():
    def discover(url):
        if "/18/" in url:
            raise OSError("unpublished")
        return discovery_body(url)
    reader, calls, loads = coordinator(discover=discover)
    candidate = reader.selected_lead_run(RUN + timedelta(hours=6))
    assert candidate.provider_run_id == "2026090612"
    assert candidate.detail["lead_hours"] == 6
    assert candidate.detail["valid_times"] == (RUN + timedelta(hours=6),)
    assert len(calls) == 2 and loads == []


def test_selected_metadata_is_detached_and_hits_do_not_extend_expiry():
    clock = [0]
    reader, calls, loads = coordinator(clock=lambda: clock[0])
    selected = RUN + timedelta(hours=9)
    first = reader.selected_lead_run(selected)
    first.detail["availability_receipt"]["response_headers"]["invented"] = "bad"
    first.detail["bounds"]["north"] = 99
    clock[0] = 599
    second = reader.selected_lead_run(selected)
    assert "invented" not in second.detail["availability_receipt"]["response_headers"]
    assert second.detail["bounds"]["north"] == 50.5
    assert len(calls) == 1
    clock[0] = 600
    reader.selected_lead_run(selected)
    assert len(calls) == 2 and loads == []


def test_unavailable_selected_lead_cannot_become_inventory():
    def absent(_url):
        raise OSError("unpublished")
    reader, calls, loads = coordinator(discover=absent)
    for _ in range(2):
        with pytest.raises(ValueError):
            reader.selected_lead_run(RUN + timedelta(hours=9))
    assert len(calls) == 2 and loads == []


def test_descriptor_distinguishes_members_and_local_statistics_without_series():
    capabilities = point_capabilities()
    assert len(capabilities) == 7
    for capability in capabilities:
        assert capability.product_id == "pgrb2ap5"
        assert capability.point_product == "GEFS"
        assert capability.native_series is False
        assert capability.run_selection == "latest"
        assert tuple(v.member for v in capability.variants if v.kind == "member") == declared_members()
        assert [(v.kind, v.statistic) for v in capability.variants if v.member is None] == [
            ("derived_statistic", "ensemble_mean"), ("derived_statistic", "ensemble_spread")]
    cloud = next(c for c in capabilities if c.field == "total_cloud_mean_6h")
    assert "averaging interval" in cloud.time_semantics
