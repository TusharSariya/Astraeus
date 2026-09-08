"""Bounded native RRFS single-message decoder; no transport or registration."""
import base64
from datetime import datetime
import json
from pathlib import Path
import sys

from .rrfs_native import LIMITS, RRFSRequest, decode_temperature


def main():
    encoded = sys.stdin.buffer.read(LIMITS.stdin_bytes + 1)
    if len(encoded) > LIMITS.stdin_bytes:
        raise ValueError("RRFS child input exceeds bound")
    body = json.loads(encoded)
    request = body["request"]
    result = decode_temperature(base64.b64decode(body["payload"], validate=True), RRFSRequest(
        datetime.fromisoformat(request["run_time"]), datetime.fromisoformat(request["valid_time"]),
        request["latitude"], request["longitude"]))
    Path(sys.argv[1]).write_text(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    main()
