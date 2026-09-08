"""Cancellable CAMS AOD acquisition child, including both HTTP requests and decode."""
from dataclasses import asdict
from datetime import datetime
import json
import sys

from ingest.http import PoliteClient
from weather_api.openmeteo_cams_aod_query import CamsAodSelection, OpenMeteoCamsAodQueryService


def main():
    data = json.loads(sys.stdin.buffer.read(4097))
    key = CamsAodSelection(data["latitude"], data["longitude"],
                           datetime.fromisoformat(data["start"]), datetime.fromisoformat(data["end"]))
    with PoliteClient(attempts=1, timeout_seconds=15) as client:
        service = OpenMeteoCamsAodQueryService(client=client)
        entry = service._acquire(key)
    print(json.dumps(asdict(entry), default=str))


if __name__ == "__main__":
    main()
