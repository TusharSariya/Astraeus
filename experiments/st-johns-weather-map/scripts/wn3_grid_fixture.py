"""Synthetic grid proof fixtures using the tested production native reader.

Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-006. No provider network.
"""
import sys,json,tempfile
from pathlib import Path
from types import SimpleNamespace
root=Path(__file__).resolve().parents[1]
import argparse
parser=argparse.ArgumentParser(description='Write synthetic WN3 browser replay fixtures; no provider network')
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
args.output.mkdir(parents=True,exist_ok=True)
sys.path[:0]=[str(root/'api/tests'),str(root/'api'),str(root)]
from test_source_grid import transport,service,VALID,NOW
from weather_api.source_grid import frame,FIELD
from weather_api.models import PointResponse,Selection
from weather_api.store import registry_source_records
from weather_api.models import CatalogResponse,DataMode
with tempfile.TemporaryDirectory() as tmp:
    t=transport.__wrapped__(Path(tmp),SimpleNamespace(param=False));s=service(t)
    grid=frame(s,VALID)
    point=PointResponse(data_mode='live',latitude=47.5,longitude=-53,valid_time=VALID,time_selection='directional',fields=list(s.read_point(47.5,-53,VALID,field=FIELD)),selection=Selection(mode='evidence_only',selected_source_id=None,selected_product_id=None,badge='Point data',reason='Synthetic native grid replay'))
    out=args.output
    (out/'fixture-grid.json').write_text(grid.model_dump_json())
    (out/'fixture-point.json').write_text(point.model_dump_json())
    catalog=CatalogResponse(data_mode=DataMode.FIXTURE,generated_at=NOW,sources=registry_source_records())
    (out/'fixture-catalog.json').write_text(catalog.model_dump_json())
