import hashlib
import json

import pytest

from weather_api.gefs_capture import GEFSAuditClient, GEFSReplayClient


def receipt(body: bytes) -> dict[str, object]:
    return {
        "url": "https://noaa.example/object",
        "effective_url": "https://noaa.example/object",
        "request_headers": {},
        "response_headers": {},
        "completed_at": "2026-09-06T12:00:00+00:00",
        "byte_size": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
    }


class Delegate:
    def get_bytes_with_receipt(self, _url, *, max_bytes):
        assert max_bytes >= 3
        return b"idx", receipt(b"idx")

    def download_ranges_with_receipts(self, _url, destination, ranges, *, max_bytes):
        assert list(ranges) == [(0, 2), (3, 4)] and max_bytes >= 5
        destination.write_bytes(b"abcde")
        return 5, [receipt(b"abc"), receipt(b"de")]


def test_audit_client_fsyncs_exact_bodies_and_receipts(tmp_path):
    client = GEFSAuditClient(Delegate(), tmp_path)
    assert client.get_bytes_with_receipt("idx", max_bytes=10)[0] == b"idx"
    destination = tmp_path.parent / "ranges"
    client.download_ranges_with_receipts("object", destination, [(0, 2), (3, 4)], max_bytes=10)
    records = [json.loads(line) for line in (tmp_path / "receipts.jsonl").read_text().splitlines()]
    assert [record["kind"] for record in records] == ["index", "range", "range"]
    assert [(tmp_path / record["body_file"]).read_bytes() for record in records] == [b"idx", b"abc", b"de"]


def test_audit_client_refuses_nonempty_destination(tmp_path):
    (tmp_path / "old").write_bytes(b"evidence")
    with pytest.raises(RuntimeError, match="must be empty"):
        GEFSAuditClient(Delegate(), tmp_path)


def test_replay_requires_exact_sequence_url_range_and_digest(tmp_path):
    audit = GEFSAuditClient(Delegate(), tmp_path)
    audit.get_bytes_with_receipt("https://noaa.example/object", max_bytes=10)
    destination = tmp_path.parent / "ranges"
    audit.download_ranges_with_receipts("https://noaa.example/object", destination, [(0, 2), (3, 4)], max_bytes=10)
    replay = GEFSReplayClient(tmp_path)
    assert replay.get_bytes_with_receipt("https://noaa.example/object", max_bytes=10)[0] == b"idx"
    output = tmp_path.parent / "replayed"
    assert replay.download_ranges_with_receipts("https://noaa.example/object", output, [(0, 2), (3, 4)], max_bytes=10)[0] == 5
    assert output.read_bytes() == b"abcde"
