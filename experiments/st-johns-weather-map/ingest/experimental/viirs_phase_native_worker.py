"""Bounded VIIRS raw native metadata/value probe; no scientific admission."""
from pathlib import Path
import json
import os
import sys
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['OMP_NUM_THREADS'] = '1'
import netCDF4
import numpy as np


def serial(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    return value


def inspect(path, key, row, column):
    with netCDF4.Dataset(path) as ds:
        ds.set_auto_maskandscale(False)
        if (ds.getncattr('Metadata_Link') != key.rsplit('/', 1)[-1]
                or ds.getncattr('satellite_name') != 'NOAA-20'
                or ds.getncattr('title') != 'JRR_CloudPhase'
                or ds.getncattr('cdm_data_type') != 'swath'
                or ds.getncattr('history_package') != 'Delivery Package v3r2'):
            raise ValueError('Native product identity mismatch')
        shape = (len(ds.dimensions['Rows']), len(ds.dimensions['Columns']))
        if not (0 < shape[0] <= 1024 and 0 < shape[1] <= 3200 and row < shape[0] and column < shape[1]):
            raise ValueError('Native swath shape or index exceeds bounds')
        fields = ('Latitude', 'Longitude', 'CloudPhase', 'CloudType', 'CloudPhaseFlag', 'CloudTypePacked')
        expected = {'Latitude': 'degrees_north', 'Longitude': 'degrees_east', 'CloudPhase': '1', 'CloudType': '1', 'CloudPhaseFlag': '1', 'CloudTypePacked': '1'}
        cell = {}
        for name in fields:
            variable = ds.variables[name]
            tail = (1,) if name == 'CloudPhaseFlag' else (6,) if name == 'CloudTypePacked' else ()
            if variable.shape != shape + tail or variable.units != expected[name]:
                raise ValueError('Native field shape/units mismatch: ' + name)
            if name not in ('Latitude', 'Longitude') and variable.dtype != np.dtype('int8'):
                raise ValueError('Native categorical/quality dtype mismatch: ' + name)
            raw = variable[row, column]
            fill = variable.getncattr('_FillValue')
            cell[name] = {'raw': serial(raw), 'is_fill': serial(np.asarray(raw) == fill),
                          'attributes': {a: serial(variable.getncattr(a)) for a in variable.ncattrs()}}
        coordinates = {}
        for name in ('Latitude', 'Longitude'):
            v = ds.variables[name]
            values = v[:]
            valid = np.isfinite(values) & (values != v.getncattr('_FillValue'))
            coordinates[name] = {'minimum': float(values[valid].min()) if valid.any() else None,
                                 'maximum': float(values[valid].max()) if valid.any() else None}
        return {'source_dataset_name': ds.getncattr('Metadata_Link'), 'row': row, 'column': column,
                'shape': shape, 'cell': cell, 'coordinate_extent': coordinates,
                'metadata': {a: serial(ds.getncattr(a)) for a in ds.ncattrs()},
                'granule_quality': {'raw': serial(ds.variables['granule_level_quality_flag'][...]),
                                    'attributes': {a: serial(ds.variables['granule_level_quality_flag'].getncattr(a)) for a in ds.variables['granule_level_quality_flag'].ncattrs()}},
                'native_variable_inventory': list(ds.variables),
                'time_semantics': 'file scan interval and full object stamps retained; no pixel time inferred'}


if __name__ == '__main__':
    output, key, row, column = Path(sys.argv[1]), sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
    raw = output.with_name('native.nc')
    try:
        body = sys.stdin.buffer.read(24 * 1024 * 1024 + 1)
        if len(body) > 24 * 1024 * 1024:
            raise ValueError('Native granule exceeds ceiling')
        raw.write_bytes(body)
        del body
        result = inspect(raw, key, row, column)
        payload = json.dumps(result, allow_nan=False)
        if len(payload.encode()) > 64 * 1024:
            raise ValueError('Native metadata exceeds ceiling')
        output.write_text(payload)
    finally:
        raw.unlink(missing_ok=True)
