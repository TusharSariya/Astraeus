"""Bounded GeoMet radar point delivery; selected-layer-point-data contract.

No imagery is sampled. Reuse the shared GeoMet transport, discovery cache,
request/process budgets and native GetFeatureInfo parser.
"""
from datetime import UTC, datetime, timedelta
import math
import re
from ingest.registry import get_config

from ingest.adapters.eccc_geomet import RADAR_RAIN_LAYER, RADAR_SNOW_LAYER, RADAR_UNDETECTED_CLASS, ATTRIBUTION, LICENCE, GeoMetServiceException
from registry import fields as catalogue
from .models import Coverage, EvidenceField, Freshness, Provenance, Quality
from .source_contract import SourceCapability, SourceVariant
from .native_runs import RunUnavailable
from . import wms

FIELDS = (("precipitation_rate", RADAR_RAIN_LAYER, "mm h-1"), ("snow_rate", RADAR_SNOW_LAYER, "cm h-1"))
MAX_AGE = timedelta(seconds=get_config("eccc-radar").freshness_threshold_seconds)


class RadarSource:
    source_id, product_id = 'eccc-radar', 'geomet-radar-composite'

    def descriptors(self):
        return tuple(SourceCapability(source_id=self.source_id, product_id=self.product_id,
            field=key, variants=[SourceVariant(kind='observation')], levels=[str(catalogue.field(key).level)],
            point=True, point_product='Radar', native_series=False, run_selection='not_applicable',
            point_time_kind='observation', directional_time_selection=True,
            time_semantics='Published native scan at or before selection, at most 20 minutes old; no forecast run',
            coverage_description='Existing Avalon bounds and returned native cell coverage; empty responses remain missing')
            for key in ('precipitation_rate', 'snow_rate', 'radar_echo'))

    def resolve_point_time(self, selected):
        with wms.budgeted():
            client = wms.geomet_client()
            # Echo requires a common published scan from the two rate layers.
            times = set(client.time_dimension(RADAR_RAIN_LAYER)) & set(client.time_dimension(RADAR_SNOW_LAYER))
            eligible = [stamp for stamp in times if timedelta(0) <= selected - stamp <= MAX_AGE]
            if not eligible:
                raise RunUnavailable('No published radar scan at or before selection within 20 minutes')
            return max(eligible)

    def read_point(self, latitude, longitude, selected, *, run='latest', refresh=False):
        from .app import require_core_coverage
        require_core_coverage(latitude, longitude)
        if run != 'latest' or refresh:
            raise RunUnavailable('Radar uses published scans and the shared finite GeoMet cache')
        values, samples, errors = {}, {}, {}
        with wms.budgeted():
            client = wms.geomet_client()
            for key, layer, units in FIELDS:
                if selected not in client.time_dimension(layer):
                    raise RunUnavailable('Radar requires an exact published native scan')
                try:
                    sample = client.feature_info(layer, latitude, longitude, valid_time=selected, resolve=False)
                    if sample is not None and (sample.valid_time != selected or not sample.units_recognised or sample.units != units or not math.isfinite(sample.value) or sample.value < 0):
                        raise RunUnavailable('Radar response time, units or value differ from the native contract')
                    samples[key] = sample
                    values[key] = sample.value if sample and sample.value > 0 else None
                except Exception as error:
                    if isinstance(error, wms.UpstreamBudgetExhausted):
                        raise
                    code = str(error).split(':')[1].strip() if isinstance(error, GeoMetServiceException) and ':' in str(error) else ''
                    errors[key] = f'geomet_{code}' if re.fullmatch(r'[A-Za-z0-9_]{1,64}', code) else type(error).__name__
                    samples[key], values[key] = None, None
        # Absence of coverage is not an explicit no-echo observation. Preserve
        # the provider's Undetected flag, never manufacture a numeric zero rate.
        positive = any(value is not None and value > 0 for value in values.values())
        undetected = all(sample is not None and sample.value == 0 and (sample.classification or '').strip().lower() == RADAR_UNDETECTED_CLASS for sample in samples.values())
        values['radar_echo'] = 1.0 if positive else 0.0 if undetected else None
        retrieved = datetime.now(UTC)
        result = []
        for key in ('precipitation_rate', 'snow_rate', 'radar_echo'):
            sample = samples.get(key) if key != 'radar_echo' else next((s for s in samples.values() if s is not None), None)
            definition = catalogue.field(key)
            value = values[key]
            result.append(EvidenceField(field=key, key=key, value=value,
                provenance=Provenance(data_mode='live', evidence_class='retrieved', source_id=self.source_id,
                    provider='Environment and Climate Change Canada', product='GeoMet radar composite', forecast_centre='ECCC',
                    run_time=None, valid_time=selected, retrieval_time=retrieved,
                    vertical_level=str(definition.level), original_units=sample.units_raw if sample and key != 'radar_echo' else 'flag' if key == 'radar_echo' else definition.units,
                    normalized_units=definition.units, native_resolution='1 km radar mosaic', native_crs='EPSG:4326',
                    quality=Quality(status='passed' if value is not None else 'unknown', flags=[] if value is not None else ['source_failure', errors[key]] if key in errors else ['native_missing']),
                    coverage=Coverage(status='complete' if value is not None else 'unknown'),
                    freshness=Freshness.evaluate(0, int(MAX_AGE.total_seconds())), licence=LICENCE, attribution=ATTRIBUTION,
                    adapter_version='eccc-geomet-radar-v1', delivery_kind='published_cell',
                    sampled_latitude=sample.latitude if sample else None, sampled_longitude=sample.longitude if sample else None,
                    sample_method='GeoMet GetFeatureInfo native pixel', native_variable=sample.layer if sample else None)))
        return tuple(result)

    def plan_series(self, start, end, *, run='latest'):
        return None
