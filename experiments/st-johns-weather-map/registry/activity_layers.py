"""Declared #48 built-in stack catalogue, independent of current delivery.

The RAQDPS entry is deliberately only declared (#172). This mapping does not
admit a source, promise imagery, or manufacture a Layer response.
"""
DECLARED_ACTIVITY_LAYERS = {
    'eccc-lightning-lightning': 'Lightning',
    'eccc-radar-radar': 'Radar',
    'eccc-cap-alerts-alerts_features': 'CAP alerts',
    'eccc-raqdps-pm2_5_surface': 'RAQDPS surface PM2.5 (admission pending #172)',
    'geomet-live-hrdps-pr': 'HRDPS precipitation accumulation',
    'geomet-live-hrdps-wspd': 'HRDPS wind speed',
    'geomet-live-hrdps-tt': 'HRDPS temperature',
    'eccc-aqhi-demand-observations': 'AQHI observations',
    'eccc-hrdps-surface-total-cloud': 'HRDPS total cloud opacity',
    'noaa-gfs-demand-cloud-high': 'GFS high cloud',
    'noaa-gfs-demand-cloud-middle': 'GFS middle cloud',
    'noaa-gfs-demand-cloud-low': 'GFS low cloud',
    'geomet-live-hrdps-weong-fog-liquid': 'HRDPS WEonG liquid fog visibility',
    'geomet-live-goes-east-nightir-2km': 'GOES night IR',
    'geomet-live-goes-east-snowfog-nightmicro': 'GOES night microphysics',
    'geomet-live-goes-east-naturalcolor': 'GOES natural colour',
}
