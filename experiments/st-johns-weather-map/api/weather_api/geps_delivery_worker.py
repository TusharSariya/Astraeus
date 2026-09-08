"""Bounded GEPS selection/discovery and all-five native coverage child."""
import json
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from weather_api.geps_delivery import acquire_latest, GEPSDeliveryHTTP


def main():
    output = Path(sys.argv[1])
    selected = datetime.fromisoformat(sys.stdin.buffer.read(128).decode())
    with tempfile.TemporaryDirectory(prefix='geps-delivery-', dir=output.parent) as directory:
        with GEPSDeliveryHTTP(attempts=1, timeout_seconds=15) as client:
            entry = acquire_latest(selected, client, Path(directory))
        with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_STORED) as bundle:
            bundle.writestr('result.json', json.dumps({'request': entry.key.as_dict(), 'provenance': entry.provenance}))
            bundle.writestr('artifact.zip', entry.payload)


if __name__ == '__main__':
    main()
