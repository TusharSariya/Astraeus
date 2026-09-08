"""OSTIA transport and native crop leaf; Linux resource limits owned by parent."""
import json
import sys
from pathlib import Path
from datetime import datetime
from ingest.http import PoliteClient
from weather_api.ostia_query import acquire

if __name__ == '__main__':
    selected = datetime.fromisoformat(sys.stdin.buffer.read(128).decode())
    with PoliteClient(attempts=1, timeout_seconds=15) as client:
        result = acquire(selected, client, workspace=Path.cwd())
    print(json.dumps(result, allow_nan=False))
