"""Registry discovery declarations. No I/O, value acquisition or admission changes.

Subject tags are navigation, never a scientific comparability assertion.
Unknown methods remain unknown rather than being guessed from a source name.
"""
from .models import MapCapability, DiscoveryMetadata

# Exact registry categories, not substring classifiers.
CATEGORY_SUBJECTS = {
    'satellite': ['Satellite imagery', 'Clouds'], 'space_weather': ['Space weather'],
    'radar': ['Precipitation'], 'lightning': ['Lightning'], 'hazard': ['Hazards'],
    'air_quality': ['Air quality'], 'optional_air_quality': ['Air quality'],
    'ocean': ['Marine'], 'wave': ['Marine'], 'surge': ['Marine'],
    'marine': ['Marine'], 'marine_observation': ['Marine'], 'local_buoy': ['Marine'],
    'tide_water_level': ['Marine'], 'hydrology': ['Hydrology'],
    'camera': ['Camera imagery'], 'terrain': ['Terrain/reference'],
    'humidity_profile': ['Humidity'], 'astronomy': ['Astronomy'],
}
FAMILY_SUBJECTS = {
    'cloud_cover': 'Clouds', 'cloud_geometry': 'Clouds', 'cloud_microphysics': 'Clouds',
    'temperature': 'Temperature', 'humidity': 'Humidity', 'precipitation': 'Precipitation',
    'air_quality': 'Air quality', 'space_weather': 'Space weather', 'wind': 'Wind',
    'pressure': 'Pressure', 'radiation': 'Radiation/UV', 'lightning': 'Lightning',
    'visibility': 'Visibility/fog', 'hazard': 'Hazards', 'marine': 'Marine',
    'astronomy_geometry': 'Astronomy', 'terrain': 'Terrain/reference',
    'stability': 'Atmospheric stability', 'vertical_motion': 'Vertical motion',
    'boundary_layer': 'Boundary layer', 'transparency': 'Sky transparency', 'seeing': 'Seeing',
}
CATEGORY_KINDS = {
    'deterministic_forecast': ['Forecast'], 'postprocessed_forecast': ['Forecast'],
    'ensemble': ['Forecast'], 'land_surface_forecast': ['Forecast'], 'nowcasting': ['Nowcast'],
    'analysis': ['Analysis/reanalysis'], 'surface_observation': ['Observation'],
    'humidity_profile': ['Observation'], 'radar': ['Observation'], 'satellite': ['Observation'],
    'lightning': ['Observation'], 'marine_observation': ['Observation'],
    'local_buoy': ['Observation'], 'optional_observation': ['Observation'],
    'camera': ['Observation'], 'terrain': ['Reference'],
}
KIND_OVERRIDES = {
    'google-weathernext-3-statistics': ['Forecast'], 'google-weathernext-2': ['Forecast'],
    'open-meteo-weathernext-2': ['Forecast'], 'awc-metar-speci': ['Observation'],
    'awc-taf': ['Forecast'], 'awc-sigmet-airmet': ['Alert'], 'awc-pirep-airep': ['Observation'],
    'eccc-cap-alerts': ['Alert'], 'noaa-swpc-alerts': ['Alert'], 'ccg-navwarn': ['Alert'],
    'noaa-swpc-ovation': ['Nowcast'], 'noaa-swpc-kp-hourly-prediction': ['Forecast'],
    'eccc-aqhi': ['Observation'], 'eccc-raqdps': ['Forecast'], 'eccc-rdaqa': ['Analysis/reanalysis'],
    'eccc-raqdps-firework': ['Forecast'], 'nl-air-quality-csv': ['Observation'],
    'openmeteo-climate-cmip6': ['Forecast'], 'openmeteo-seasonal-seas5': ['Forecast'],
}
ML_SOURCES = {'google-weathernext-3-statistics', 'google-weathernext-2',
              'open-meteo-weathernext-2', 'ecmwf-aifs-single', 'ecmwf-aifs-ens', 'openmeteo-graphcast'}
SUBJECT_OVERRIDES = {
    'nasa-soho-sdo-goes-suvi-imagery': ['Space weather', 'Satellite imagery'],
    'noaa-goes-glm': ['Lightning', 'Satellite imagery'],
    'noaa-goes-east': ['Satellite imagery', 'Clouds'],
    'openmeteo-uv-index': ['Radiation/UV'],
    'eccc-wildfire-hotspots': ['Hazards', 'Air quality', 'Satellite imagery'],
    'nasa-earthdata-aerosol': ['Air quality', 'Satellite imagery'],
    'viirs-dnb-night-lights': ['Astronomy', 'Satellite imagery'],
}


# Exact declared variable labels supply browsing tags only, never canonical
# field mappings or an assertion that this deployment implements those fields.
VARIABLE_SUBJECTS = {
    **dict.fromkeys(['temperature', 'air_temperature', 'surface_temperature', 'soil_temperature', 'radiative_surface_temperature', 'road_surface_temperature', 'statistically_postprocessed_temperature'], 'Temperature'),
    **dict.fromkeys(['cloud', 'cloud_fraction', 'total_cloud', 'low_cloud', 'middle_cloud', 'high_cloud'], 'Clouds'),
    **dict.fromkeys(['humidity', 'relative_humidity', 'dew_point'], 'Humidity'),
    **dict.fromkeys(['wind', 'wind_speed', 'wind_direction', 'wind_gust_speed', 'satellite_wind'], 'Wind'),
    **dict.fromkeys(['precipitation', 'precipitation_probability', 'precipitation_rate', 'precipitation_accumulation', 'precipitation_analysis'], 'Precipitation'),
    **dict.fromkeys(['pressure', 'mean_sea_level_pressure'], 'Pressure'),
    **dict.fromkeys(['smoke', 'aerosol_optical_depth'], 'Air quality'),
    **dict.fromkeys(['snow_state', 'snow_depth', 'snow_water_equivalent', 'icing'], 'Snow/ice'),
    **dict.fromkeys(['solar', 'sunshine', 'direct_radiation', 'diffuse_radiation', 'direct_normal_irradiance'], 'Radiation/UV'),
    'lightning_probability': 'Lightning', 'visibility': 'Visibility/fog', 'hazard': 'Hazards',
    'turbulence': 'Hazards', 'advisories': 'Hazards', 'road_conditions': 'Road conditions',
    'surface_condition': 'Road conditions', 'camera_metadata_and_views': 'Camera imagery',
    'soil_moisture': 'Soil moisture', 'soil_liquid_water_content': 'Soil moisture',
    'surface_fluxes': 'Surface fluxes', 'vertical_velocity': 'Vertical motion',
}


def map_capabilities(source_id):
    from . import wms
    from .models import catalogue_key_for
    from registry import fields
    result = []
    for spec in wms.PROXIED_LAYERS:
        if spec.source_id != source_id:
            continue
        key = catalogue_key_for(spec.field)
        subjects = [FAMILY_SUBJECTS.get(fields.family_of(key), fields.family_of(key))] if key else []
        if spec.group == 'satellite':
            subjects = ['Satellite imagery', 'Clouds']
        if spec.layer_id == 'geomet-live-goes-east-snowfog-nightmicro':
            subjects += ['Snow/ice', 'Visibility/fog']
        result.append(MapCapability(layer_id=spec.layer_id, title=spec.title, subjects=subjects))
    declared = {
        'noaa-gfs': [(f'noaa-gfs-demand-{suffix}', f'GFS {title} cloud', 'GFS', ['Clouds']) for suffix, title in [('total-cloud', 'total'), ('cloud-low', 'low'), ('cloud-middle', 'middle'), ('cloud-high', 'high')]],
        'eccc-cap-alerts': [('eccc-cap-alerts-current', 'Current CAP alerts', 'CAP', ['Hazards'])],
        'noaa-swpc-ovation': [('noaa-swpc-aurora-oval', 'Aurora oval', 'OVATION', ['Space weather'])],
        'eccc-aqhi': [('eccc-aqhi-demand-observations', 'AQHI observations', None, ['Air quality'])],
        'eccc-swob': [('eccc-swob-demand-observations', 'Surface observations', None, [])],
    }
    result.extend(MapCapability(layer_id=i, title=t, product=p, subjects=s) for i,t,p,s in declared.get(source_id, []))
    return result


def discovery_metadata(record, source_fields, capabilities):
    source_id, category = record['id'], record['category']
    subjects = set(SUBJECT_OVERRIDES.get(source_id, CATEGORY_SUBJECTS.get(category, [])))
    subjects.update(FAMILY_SUBJECTS.get(f.family, f.family.replace('_', ' ').capitalize())
                    for f in source_fields if str(f.storage) != 'not-published')
    subjects.update(VARIABLE_SUBJECTS[name] for variable in record.get('variables', []) for name in variable.get('names', []) if name in VARIABLE_SUBJECTS)
    methods = ['Machine learning'] if source_id in ML_SOURCES else (
        ['Numerical model'] if category in {'deterministic_forecast', 'ensemble'} else
        ['Statistical processing'] if category == 'postprocessed_forecast' else
        ['Remote sensing'] if category in {'satellite', 'radar'} else
        ['Instrument measurement'] if category in {'surface_observation', 'humidity_profile', 'marine_observation', 'local_buoy'} else [])
    maps = map_capabilities(source_id)
    subjects.update(subject for capability in maps for subject in capability.subjects)
    forms = set()
    for capability in capabilities:
        for variant in capability.variants:
            form = {'member': 'Members', 'provider_statistic': 'Provider statistics', 'deterministic': 'Deterministic', 'observation': 'Not applicable'}.get(variant.kind)
            if form: forms.add(form)
    if category == 'deterministic_forecast': forms.add('Deterministic')
    kinds = KIND_OVERRIDES.get(source_id, CATEGORY_KINDS.get(category, []))
    if not kinds and any(v.kind == 'observation' for c in capabilities for v in c.variants):
        kinds = ['Observation']
    return DiscoveryMetadata(subjects=sorted(subjects) or ['Unknown'],
        kinds=kinds or ['Unknown'],
        methods=methods or ['Unknown'], ensemble_forms=sorted(forms) or ['Unknown'],
        map_capabilities=maps)
