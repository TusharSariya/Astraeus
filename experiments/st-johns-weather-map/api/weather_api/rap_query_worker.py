"""Bounded native RAP grid221 decode; no regridding or scientific derivation."""
from datetime import datetime
import json
from pathlib import Path
import sys


def native_crop(latitude, longitude):
    """Keep a one-cell native halo for nearest-cell reads at box boundaries.

    Request eligibility is checked by the coordinator. It must not become a
    mask on provider cells: the nearest cell can be just outside that box.
    """
    import numpy as np
    from .rap_query import BOUNDS
    inside = ((latitude >= BOUNDS["south"]) & (latitude <= BOUNDS["north"])
              & (longitude >= BOUNDS["west"]) & (longitude <= BOUNDS["east"]))
    if not inside.any():
        raise ValueError("RAP native grid excludes evidence box")
    yy, xx = np.where(inside)
    return np.s_[max(0, yy.min()-1):min(latitude.shape[0], yy.max()+2),
                 max(0, xx.min()-1):min(latitude.shape[1], xx.max()+2)]


def decode(request):
    import eccodes as e
    import numpy as np
    from .rap_query import FIELDS, BOUNDS, RECORD_BYTES

    run = datetime.fromisoformat(request["run_time"])
    valid = datetime.fromisoformat(request["valid_time"])
    fields, reference = {}, None
    for name, (_parameter, _level, short, level_type, units) in FIELDS.items():
        path = Path(request["directory"])/f"{name}.grib2"
        if not 0 < path.stat().st_size <= RECORD_BYTES:
            raise ValueError("RAP record byte bound")
        with path.open("rb") as handle:
            gid = e.codes_grib_new_from_file(handle)
            if gid is None:
                raise ValueError("RAP missing GRIB message")
            try:
                expected = dict(shortName=short, units=units, typeOfLevel=level_type,
                    gridType="lambert", Nx=349, Ny=277, stepType="instant",
                    dataDate=int(run.strftime("%Y%m%d")), dataTime=int(run.strftime("%H%M")),
                    validityDate=int(valid.strftime("%Y%m%d")), validityTime=int(valid.strftime("%H%M")),
                    startStep=request["lead"], endStep=request["lead"], centre="kwbc",
                    LoVInDegrees=253., Latin1InDegrees=50., Latin2InDegrees=50.,
                    DxInMetres=32463., DyInMetres=32463.)
                if any(e.codes_get(gid, key) != value for key, value in expected.items()):
                    raise ValueError("RAP native field/time/grid/unit mismatch")
                lat = e.codes_get_array(gid, "latitudes").reshape(277, 349)
                lon = ((e.codes_get_array(gid, "longitudes")+180)%360-180).reshape(277, 349)
                # Check the footprint in native projected space, not global
                # longitude extrema (this grid crosses the dateline).
                import pyproj
                projection = pyproj.Proj(proj="lcc", lat_1=50, lat_2=50,
                                         lon_0=253, R=e.codes_get(gid, "radius"))
                x, y = projection(lon, lat)
                for latitude in np.linspace(BOUNDS["south"], BOUNDS["north"], 64):
                    for longitude in (BOUNDS["west"], BOUNDS["east"]):
                        px, py = projection(longitude, latitude)
                        if not x.min() < px < x.max() or not y.min() < py < y.max():
                            raise ValueError("RAP projected footprint excludes evidence boundary")
                for longitude in np.linspace(BOUNDS["west"], BOUNDS["east"], 64):
                    for latitude in (BOUNDS["south"], BOUNDS["north"]):
                        px, py = projection(longitude, latitude)
                        if not x.min() < px < x.max() or not y.min() < py < y.max():
                            raise ValueError("RAP projected footprint excludes evidence boundary")
                values = e.codes_get_values(gid).reshape(277, 349)
                bitmap = (e.codes_get_array(gid, "bitmap").reshape(277, 349).astype(bool)
                          if e.codes_get(gid, "bitmapPresent") else np.ones_like(values, dtype=bool))
                values = np.where(bitmap, values, np.nan)
                if np.isinf(values).any() or np.any(np.isfinite(values) & (values < 0)):
                    raise ValueError("RAP invalid native values")
                if name == "total_cloud_geometric" and np.any(np.isfinite(values) & (values > 100)):
                    raise ValueError("RAP cloud percent exceeds domain")
            finally:
                e.codes_release(gid)
            extra = e.codes_grib_new_from_file(handle)
            if extra is not None:
                e.codes_release(extra)
                raise ValueError("RAP selected range contains extra messages")
        if reference is not None and not (np.array_equal(lat, reference[0]) and np.array_equal(lon, reference[1])):
            raise ValueError("RAP fields use different native grids")
        reference = lat, lon
        crop = native_crop(lat, lon)
        def clean(array):
            return np.where(np.isfinite(array), array, None).tolist()
        fields[name] = clean(values[crop])
    return dict(source_id="noaa-rap", product="awip32", run_time=run.isoformat(),
        valid_time=valid.isoformat(), grid_type="lambert", native_shape=[277, 349],
        latitude=clean(lat[crop]), longitude=clean(lon[crop]), fields=fields)


if __name__ == "__main__":
    result = decode(json.loads(sys.stdin.buffer.read()))
    Path(sys.argv[1]).write_text(json.dumps(result, allow_nan=False))
