"""Bounded reuse of the existing ACMF/ACHAF scientific decoder.
Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-006 (experiment).
"""
import json
import os
import sys
from pathlib import Path
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['OMP_NUM_THREADS'] = '1'
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ingest.adapters.goes_abi import process_granules, parse_scan_stamp
from ingest.grib import write_zarr
from ingest.contract import ATLANTIC_CONTEXT_BOUNDS

if __name__ == '__main__':
    request = json.loads(sys.stdin.buffer.read(16384))
    import xarray as xr
    from datetime import datetime
    stamp=parse_scan_stamp(request['stamp'])
    with xr.open_dataset(request['mask']) as mask:
        if mask.attrs.get('platform_ID')!='G19':raise ValueError('ACMF platform mismatch')
    height=Path(request['height']) if request['height'] else None
    if height:
        try:
            with xr.open_dataset(height) as ds:
                native=datetime.fromisoformat(ds.attrs['time_coverage_start'].replace('Z','+00:00'))
                if ds.attrs.get('platform_ID')!='G19' or abs((native-stamp).total_seconds())>1:height=None
        except (OSError,ValueError,KeyError):height=None
    dataset, stats = process_granules(Path(request['mask']), height, bounds=ATLANTIC_CONTEXT_BOUNDS)
    if abs((stats['scan_start']-parse_scan_stamp(request['stamp'])).total_seconds()) > 1:
        raise ValueError('ACMF scan identity mismatch')
    write_zarr(dataset, Path(sys.argv[1]))
