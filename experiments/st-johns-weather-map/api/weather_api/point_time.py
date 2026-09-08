"""Opt-in directional selection over declared native availability.

No selection cache: native caches retain resolved native time/run identities;
client request keys include the policy. Legacy callers never enter this path.
"""
import logging
from fastapi import HTTPException
from .models import DataMode, PointResponse, Selection
from .native_runs import RunUnavailable
from .source_delivery import NativeFrame, source_readers, source_capabilities
from . import wms
LOGGER = logging.getLogger(__name__)


def choose_native_time(times, selected, kind, *, max_age=None):
    if kind not in ('observation', 'forecast'):
        raise RunUnavailable('Source does not declare its time policy')
    eligible = [stamp for stamp in times if (stamp <= selected if kind == 'observation' else stamp >= selected)]
    if max_age is not None:
        eligible = [stamp for stamp in eligible if abs(selected - stamp) <= max_age]
    if not eligible:
        raise RunUnavailable('No eligible native reading within source availability')
    return max(eligible) if kind == 'observation' else min(eligible)


def directional_point(latitude, longitude, selected, product, **selectors):
    from .app import configured_mode, LIVE_MODE, requested_time
    def response(fields=(), reason='No reading at selected time'):
        return PointResponse(data_mode=DataMode.LIVE if any(f.value is not None for f in fields) else DataMode.UNAVAILABLE,
            latitude=latitude, longitude=longitude, valid_time=selected, time_selection='directional', fields=list(fields),
            selection=Selection(mode='evidence_only', selected_source_id=None, selected_product_id=None,
                badge='Point data' if fields else 'Point data unavailable', reason=reason),
            notices=['Selected instant retained separately from each returned native valid time; directional policy; no interpolation'])
    if configured_mode() != LIVE_MODE:
        return response(reason='Directional point evidence requires live mode; no synthetic weather is substituted')
    readers = source_readers()
    matches = [(reader, cap) for reader in readers.values() for cap in source_capabilities(reader.source_id)
               if cap.point and cap.point_product and cap.point_product.upper() == (product or '').upper()]
    if len({reader.source_id for reader, _ in matches}) != 1:
        return response(reason='Point capability unavailable or ambiguous for this product')
    reader, cap = matches[0]
    if not cap.directional_time_selection:
        return response(reason='Native time selection unavailable: this source exposes exact-time reads without directional discovery')
    try:
        requested_time(selected)  # Retain the existing ordinary point coverage window.
    except HTTPException:
        return response(reason='Selected time outside supported source point window')
    if reader.source_id != 'noaa-gefs' and any(value is not None for value in selectors.values()):
        raise HTTPException(status_code=422, detail='This directional point capability does not support ensemble selectors')
    try:
        with wms.budgeted():
            resolver = getattr(reader, 'resolve_point_time', None)
            frame = resolver(selected) if resolver else selected
            native = frame.valid_time if isinstance(frame, NativeFrame) else frame
            options = {'run': frame.run_id} if isinstance(frame, NativeFrame) and frame.run_id != 'latest' else {}
            if reader.source_id == 'noaa-gefs':
                from .source_contract import SourceVariant
                if selectors.get('statistic'):
                    options['variant'] = SourceVariant(kind='derived_statistic', statistic=selectors['statistic'],
                        quantile=selectors.get('quantile'), threshold=selectors.get('threshold'), comparison=selectors.get('comparison'))
                    if selectors.get('member'):
                        options['member_filter'] = selectors['member']
                elif selectors.get('member'):
                    options['variant'] = SourceVariant(kind='member', member=selectors['member'])
            fields = reader.read_point(latitude, longitude, native, **options)
        accepted = []
        for field in fields:
            p = field.provenance
            correct_side = p.valid_time <= selected if cap.point_time_kind == 'observation' else p.valid_time >= selected
            if p.source_id != reader.source_id or not correct_side or p.freshness.status == 'stale' or p.run_stale is True or p.quality.status == 'failed' or p.coverage.status == 'outside':
                continue
            if resolver and p.valid_time != native:
                continue
            if reader.source_id == 'eccc-radar':
                from .radar_delivery import MAX_AGE
                if selected - p.valid_time > MAX_AGE:
                    continue
            accepted.append(field)
        reason = 'Native observation at or before selection' if cap.point_time_kind == 'observation' else 'Native forecast at or after selection'
        if not any(field.value is not None for field in accepted):
            reason = 'Source unavailable for selected native point' if any('source_failure' in field.provenance.quality.flags for field in fields) else 'No reading at selected time within native availability'
        return response(accepted, reason=reason)
    except wms.UpstreamBudgetExhausted:
        raise HTTPException(status_code=429, detail='GeoMet upstream request budget exhausted') from None
    except Exception as error:
        LOGGER.info('Directional point unavailable for %s: %s', reader.source_id, type(error).__name__)
        return response(reason='No reading at selected time within native availability' if isinstance(error, RunUnavailable) else 'Source unavailable for selected native point')
