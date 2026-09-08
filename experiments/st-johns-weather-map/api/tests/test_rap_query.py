"""GOV-SPEC-004/006: isolated RAP selected-frame identity and bounded cache."""
from datetime import UTC, datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
import copy
import pytest

from weather_api.rap_query import RAPQueryCoordinator, RAPUnavailable, selected_records

RUN = datetime(2026, 9, 7, 23, tzinfo=UTC)
INDEX = "1:0:d=2026090723:VIS:surface:anl:\n2:4:d=2026090723:TCDC:entire atmosphere:anl:\n3:8:d=2026090723:TMP:surface:anl:\n"


def result(request):
    return dict(source_id="noaa-rap", product="awip32", run_time=request["run_time"],
        valid_time=request["valid_time"], latitude=[[47.5, 47.5]], longitude=[[-53., -52.5]],
        fields={"visibility": [[1000., None]], "total_cloud_geometric": [[25., 75.]]})


class Transport:
    def __init__(self):
        self.receipts, self.calls = [], []
        self.fail = False

    def read(self, url, *, limit, byte_range=None):
        self.calls.append((url, limit, byte_range))
        if self.fail:
            raise OSError("offline failure")
        body = INDEX.encode() if byte_range is None else b"grib"
        self.receipts.append(dict(url=url, completed_at=RUN.isoformat(), byte_size=len(body)))
        return body


def test_exact_index_records_exclude_other_levels_and_averages():
    assert selected_records(INDEX, 0) == {"visibility": (0, 3), "total_cloud_geometric": (4, 7)}
    for invalid in (INDEX.replace("anl", "0-1 hour ave fcst"), INDEX.replace("entire atmosphere", "boundary layer cloud layer"), INDEX.rsplit("3:", 1)[0]):
        with pytest.raises(RAPUnavailable):
            selected_records(invalid, 0)


def test_native_multifield_wind_offsets_do_not_change_selected_record_ranges():
    wind = "1.1:0:d=2026090723:UGRD:1 hybrid level:anl:\n1.2:0:d=2026090723:VGRD:1 hybrid level:anl:\n"
    selected = "2:4:d=2026090723:VIS:surface:anl:\n3:8:d=2026090723:TCDC:entire atmosphere:anl:\n4:12:d=2026090723:TMP:surface:anl:\n"
    assert selected_records(wind+selected, 0) == {"visibility": (4, 7), "total_cloud_geometric": (8, 11)}
    with pytest.raises(RAPUnavailable, match="multi-field"):
        selected_records(selected.replace("2:4", "2.1:4"), 0)


def test_exact_native_time_and_location_refuse_before_io(tmp_path):
    http = Transport()
    reader = RAPQueryCoordinator(now=lambda: RUN, transport_factory=lambda: http, decoder=result, workspace=tmp_path)
    for selected in (RUN.replace(tzinfo=None), RUN+timedelta(minutes=1), RUN+timedelta(days=3)):
        with pytest.raises(RAPUnavailable):
            reader.query(selected)
    with pytest.raises(RAPUnavailable):
        reader.point_native(40, -53, RUN)
    assert http.calls == []


def test_point_keeps_rap_native_identity_units_nulls_and_repeat_cache(tmp_path):
    http = Transport()
    reader = RAPQueryCoordinator(now=lambda: RUN, transport_factory=lambda: http, decoder=result, workspace=tmp_path)
    point = reader.point_native(47.5, -52.5, RUN)
    assert point["source_id"] == "noaa-rap" and point["product"] == "awip32"
    assert point["sampled_longitude"] == -52.5
    assert point["fields"]["visibility"] == {"value": None, "native_units": "m"}
    assert point["fields"]["total_cloud_geometric"] == {"value": 75., "native_units": "%"}
    assert point["operational"] is False and point["quality"] == "unknown"
    reader.point_native(47.5, -53., RUN)
    assert len(http.calls) == 3
    assert all("rap.t23z.awip32f00" in row[0] for row in http.calls)


def test_coalescing_fixed_expiry_and_failed_refresh(tmp_path):
    http, ticks = Transport(), [0.]
    reader = RAPQueryCoordinator(now=lambda: RUN, clock=lambda: ticks[0], transport_factory=lambda: http, decoder=result, workspace=tmp_path)
    with ThreadPoolExecutor(max_workers=4) as pool:
        entries = list(pool.map(lambda _: reader.query(RUN), range(4)))
    assert len(http.calls) == 3
    entries[0].data["fields"]["visibility"][0][0] = 99
    assert reader.query(RUN).data["fields"]["visibility"][0][0] == 1000
    ticks[0] = 599
    http.fail = True
    with pytest.raises(RAPUnavailable):
        reader.query(RUN, refresh=True)
    assert reader.query(RUN).valid_time == RUN
    ticks[0] = 600
    with pytest.raises(RAPUnavailable):
        reader.query(RUN)
    assert len(http.calls) == 5


def test_decoder_other_model_never_enters_cache(tmp_path):
    http = Transport()
    def wrong(request):
        return {**result(request), "source_id": "noaa-gfs"}
    reader = RAPQueryCoordinator(now=lambda: RUN, transport_factory=lambda: http, decoder=wrong, workspace=tmp_path)
    with pytest.raises(RAPUnavailable):
        reader.query(RUN)
    assert not reader.entries
