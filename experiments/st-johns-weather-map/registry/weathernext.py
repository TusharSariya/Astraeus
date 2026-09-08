"""Explicit WN3 surface statistic identities for the isolated point experiment.

Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-006.
Native definitions: https://developers.google.com/weathernext/guides/models
No inferred cloud overlap, relative humidity, members or pressure-level mappings.
"""
from dataclasses import dataclass

@dataclass(frozen=True)
class SurfaceField:
    key: str
    native: str
    family: str
    level: str
    native_unit: str
    unit: str
    scale: float
    offset: float
    grid: str
    statistic: str
    quantile: float | None

# Each base retains its own comparability group, including precipitation heads.
BASES = (
    ('temperature_2m', 'temperature', '2 m', 'K', 'degC', 1, -273.15),
    ('dewpoint_temperature_2m', 'humidity', '2 m', 'K', 'degC', 1, -273.15),
    ('wind_speed_10m', 'wind', '10 m', 'm s**-1', 'm/s', 1, 0),
    ('wind_speed_100m', 'wind', '100 m', 'm s**-1', 'm/s', 1, 0),
    ('u_component_of_wind_10m', 'wind', '10 m', 'm s**-1', 'm/s', 1, 0),
    ('v_component_of_wind_10m', 'wind', '10 m', 'm s**-1', 'm/s', 1, 0),
    ('u_component_of_wind_100m', 'wind', '100 m', 'm s**-1', 'm/s', 1, 0),
    ('v_component_of_wind_100m', 'wind', '100 m', 'm s**-1', 'm/s', 1, 0),
    ('surface_solar_radiation_downwards_1hr', 'radiation', 'surface', 'J m**-2', 'J/m2', 1, 0),
    ('total_sky_direct_solar_radiation_at_surface_1hr', 'radiation', 'surface', 'J m**-2', 'J/m2', 1, 0),
    ('total_precipitation_1hr', 'precipitation', 'surface', 'm', 'mm', 1000, 0),
    ('imerg_tp_1hr', 'precipitation', 'surface', 'm', 'mm', 1000, 0),
    ('experimental_tp_1hr', 'precipitation', 'surface', 'm', 'mm', 1000, 0),
    ('total_cloud_cover', 'cloud_cover', 'column', '(0 - 1)', 'percent', 100, 0),
    ('low_cloud_cover', 'cloud_cover', 'low cloud', '(0 - 1)', 'percent', 100, 0),
    ('medium_cloud_cover', 'cloud_cover', 'middle cloud', '(0 - 1)', 'percent', 100, 0),
    ('high_cloud_cover', 'cloud_cover', 'high cloud', '(0 - 1)', 'percent', 100, 0),
    ('mean_sea_level_pressure', 'pressure', 'mean sea level', 'Pa', 'hPa', .01, 0),
    ('sea_surface_temperature', 'temperature', 'sea surface', 'K', 'degC', 1, -273.15),
    ('station_head_temperature_2m', 'temperature', '2 m station-trained', 'K', 'degC', 1, -273.15),
    ('station_head_dewpoint_temperature_2m', 'humidity', '2 m station-trained', 'K', 'degC', 1, -273.15),
)
def surface_key(base,stat):
    if base=='temperature_2m' and stat=='mean':return 'temperature_2m'
    stem,_,suffix=base.rpartition('_')
    return f'weathernext3_{stem}_{stat}_{suffix}' if suffix in ('2m','10m','100m') else f'weathernext3_{base}_{stat}'

SURFACE_FIELDS = tuple(SurfaceField(
    surface_key(base,stat),
    f'{base}_{stat}', family, level, native_unit, unit, scale, offset,
    '0p05' if base.startswith('station_head_') else '0p1',
    'ensemble_mean' if stat == 'mean' else 'ensemble_quantile',
    None if stat == 'mean' else int(stat[1:])/100,
) for base,family,level,native_unit,unit,scale,offset in BASES for stat in ('mean','p10','p25','p50','p75','p90'))
BY_KEY = {field.key: field for field in SURFACE_FIELDS}
BY_NATIVE = {field.native: field for field in SURFACE_FIELDS}
