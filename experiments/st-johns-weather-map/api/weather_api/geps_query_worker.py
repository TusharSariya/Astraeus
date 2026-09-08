"""Bounded child for one exact-time experimental GEPS reduction request."""
import json
import sys
import tempfile
import zipfile
from pathlib import Path

from ingest.http import PoliteClient
from weather_api.geps_query import GEPSRequestKey, GEPSSelectedLoader


def main():
    output = Path(sys.argv[1])
    key = GEPSRequestKey.from_dict(json.loads(sys.stdin.buffer.read(8193)))
    with tempfile.TemporaryDirectory(prefix="geps-child-", dir=output.parent) as directory:
        client = PoliteClient(attempts=1, timeout_seconds=15)
        try:
            entry = GEPSSelectedLoader(Path(directory), client)(key)
        finally:
            client.close()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as bundle:
            bundle.writestr("result.json", json.dumps({"request": key.as_dict(), "provenance": entry.provenance}))
            bundle.writestr("artifact.zip", entry.payload)


if __name__ == "__main__":
    main()
