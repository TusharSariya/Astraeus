from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from ingest.contract import AdapterUnavailable, FetchWindow
from ingest.experimental.holyrood_radar import HolyroodDPQPEAdapter, MAX_IMAGE_BYTES
from ingest.http import PoliteClient, USER_AGENT

UTC = timezone.utc
NOW = datetime(2026, 9, 6, 5, tzinfo=UTC)
WINDOW = FetchWindow(NOW)
RAIN = "20260906T0454Z_MSC_Radar-DPQPE_CASHR_Rain.gif"
SNOW = "20260906T0454Z_MSC_Radar-DPQPE_CASHR_Snow.gif"
GIF = b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"


def client(responses: dict[str, bytes]) -> PoliteClient:
    def handler(request: httpx.Request) -> httpx.Response:
        key = request.url.path.rsplit("/", 1)[-1]
        if request.url.path.endswith("/CASHR/"):
            key = "listing"
        return httpx.Response(200, content=responses[key], headers={"content-type": "image/gif" if key != "listing" else "text/html"})
    result = PoliteClient(min_host_interval_seconds=0, attempts=1)
    result._client = httpx.Client(transport=httpx.MockTransport(handler), headers={"User-Agent": USER_AGENT})
    return result


def listing(*names: str) -> bytes:
    return ("<html>" + "".join(f'<a href="{name}">{name}</a>' for name in names) + "</html>").encode()


def test_paired_native_gifs_are_immutable_but_unpublishable(tmp_path: Path) -> None:
    adapter = HolyroodDPQPEAdapter(client({"listing": listing(RAIN, SNOW, RAIN.replace(".gif", "-Contingency.gif")), RAIN: GIF, SNOW: GIF}), base_url="https://fixture.invalid/CASHR")
    candidate = adapter.discover(WINDOW)[0]
    result = adapter.fetch(candidate, WINDOW, tmp_path)
    assert candidate.run_time == datetime(2026, 9, 6, 4, 54, tzinfo=UTC)
    assert not result.complete and result.qc_passed
    assert [item.payload_path.read_bytes() for item in result.artifacts] == [GIF, GIF]
    assert all(item.provenance["image"] == {"width": 1, "height": 1, "frames": 1} for item in result.artifacts)
    assert all(item.provenance["operational"] is False for item in result.artifacts)
    assert all(item.provenance["quality"]["flags"] == ["manifest_unresolved"] for item in result.artifacts)
    assert all(item.provenance["field_dispositions"]["raw_volume"].startswith("unsupported") for item in result.artifacts)
    assert all(item.provenance["field_dispositions"]["contingency_composite"].startswith("excluded") for item in result.artifacts)
    assert all(item.provenance["upstream_sha256"] == item.provenance["artifact_sha256"] for item in result.artifacts)


def test_missing_pair_bad_gif_and_oversize_fail_closed(tmp_path: Path) -> None:
    with pytest.raises(AdapterUnavailable, match="no paired"):
        HolyroodDPQPEAdapter(client({"listing": listing(RAIN), RAIN: GIF}), base_url="https://fixture.invalid/CASHR").discover(WINDOW)
    bad = HolyroodDPQPEAdapter(client({"listing": listing(RAIN, SNOW), RAIN: GIF[:-1], SNOW: GIF}), base_url="https://fixture.invalid/CASHR")
    with pytest.raises(AdapterUnavailable, match="complete bounded GIF"):
        bad.fetch(bad.discover(WINDOW)[0], WINDOW, tmp_path)
    huge = HolyroodDPQPEAdapter(client({"listing": listing(RAIN, SNOW), RAIN: GIF + b"x" * MAX_IMAGE_BYTES, SNOW: GIF}), base_url="https://fixture.invalid/CASHR")
    with pytest.raises(AdapterUnavailable, match="unavailable rain"):
        huge.fetch(huge.discover(WINDOW)[0], WINDOW, tmp_path)
    assert list(tmp_path.iterdir()) == []
