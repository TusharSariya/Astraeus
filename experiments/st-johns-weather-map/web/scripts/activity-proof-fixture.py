"""Emit constructed evaluator responses outside Git for the browser proof.

Run from experiments/st-johns-weather-map with uv run --project api python
web/scripts/activity-proof-fixture.py /tmp/activity-browser-fixture.json.
This exercises real profiles/evaluator with synthetic inputs, never live admission.
"""
import json
import runpy
import sys
from pathlib import Path
root=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(root))
fixtures=runpy.run_path(str(root/'api/tests/test_activity_delivery.py'))
service=fixtures['ActivityService'](fixtures['Reader'](),utcnow=lambda:fixtures['AT'])
Path(sys.argv[1]).write_text(json.dumps(service.read(fixtures['FOCUS'])))
