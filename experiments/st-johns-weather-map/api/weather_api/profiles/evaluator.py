"""One evaluator over audited, versioned Activity profiles.

Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-006.
Owning contract: desktop-evidence-api-contract/activity-verdict.
Acquisition is separate; this module cannot obtain or synthesize provider values.
"""
from __future__ import annotations

from datetime import datetime
from typing import Mapping, Sequence

from ingest.derive.registry import ACTIVITY_VERDICT, resolve
from registry.grading import parameters

from ..config import VERDICT_SOURCE_PRECEDENCE
from ..models import EvidenceField, Freshness, Quality
from .evidence import SelectedInput, criterion, select_input, unusable
from .overrides import record_overrides
from .verdict import aggregate_verdict

PROFILE_ORDER = ('running', 'astronomy', 'aurora', 'landscape_photography')


def validate_overrides(profiles: Mapping, overrides: Mapping[str, float]) -> None:
    import math
    declared = {name for profile in profiles.values() for name in profile['thresholds']}
    if set(overrides) - declared or any(isinstance(value, bool) or not math.isfinite(value) for value in overrides.values()):
        raise ValueError('Overrides must name declared thresholds with finite values')
    for profile in profiles.values():
        selected = {name: value for name, value in overrides.items() if name in profile['thresholds']}
        for row in profile['graded_criteria']:
            parameters(row['grade'], profile['thresholds'], selected)


def evaluate(profile: Mapping, *, at: datetime, tier: str, readings: Sequence[EvidenceField],
             window: Mapping, overrides: Mapping[str, float], site_id: str | None, resolutions: Mapping[str, int] | None = None) -> dict:
    refusal = resolve(ACTIVITY_VERDICT)
    if refusal:
        return {'profile_id': profile['id'], 'unavailable': refusal.code}
    active_overrides = {name: value for name, value in overrides.items() if name in profile['thresholds']}
    def selected(field):
        admitted = profile['admitted_paths'].get(field, [])
        if field in ('sun_altitude', 'moon_altitude', 'moon_illuminated_fraction'):
            admitted = ['nasa-jpl-de442']
        elif field == 'total_cloud_opacity':
            admitted = ['eccc-hrdps', 'eccc-rdps']
        elif field == 'visibility':
            admitted = ['noaa-gfs']
        order = [source for source in VERDICT_SOURCE_PRECEDENCE[tier] if source in admitted]
        order += [source for source in admitted if source not in VERDICT_SOURCE_PRECEDENCE['core']]
        if not order:
            return SelectedInput(field=field, reason='no_admitted_selected_time_path')
        return select_input(field, at, readings, order)
    unresolved = list(window.get('unresolved_fields', []))
    applicability = []
    unavailable = {}
    applicability_inputs = []
    for row in profile['graded_criteria']:
        if row.get('applicability') == 'moon_above_horizon':
            altitude = selected('moon_altitude')
            reason = unusable(altitude, 'degree')
            applies = None if reason else altitude.evidence.value > 0
            if applies is None:
                unresolved.append('moon_altitude')
                unavailable[row['name']] = 'applicability_unresolved:moon_altitude'
            elif not applies:
                unavailable[row['name']] = 'not_applicable:moon_at_or_below_horizon'
            if not reason:
                applicability_inputs.append(altitude.evidence.provenance)
            applicability.append({'criterion': row['name'], 'applicable': applies, 'input': altitude.model_dump(mode='json'), 'reason': reason})
    hard_stops = [criterion(profile, row, selected(row['field']), hard_stop=True, overrides=active_overrides) for row in profile['hard_stops']]
    def grades():
        rows = []
        for spec in profile['graded_criteria']:
            value = selected(spec['field'])
            if spec['name'] in unavailable:
                value = value.model_copy(update={'reason': unavailable[spec['name']]})
            rows.append(criterion(profile, spec, value, hard_stop=False, overrides=active_overrides))
        return rows
    weights = {row['name']: profile['weights'][row['weight']] for row in profile['graded_criteria']}
    blocked = [row['name'] for row in profile['graded_criteria'] if selected(row['field']).evidence is not None and selected(row['field']).evidence.absence_state == 'blocked']
    result = aggregate_verdict(weights=weights, hard_stops=hard_stops, grade=grades,
        outside_window=window.get('outside_window'), unresolved_fields=unresolved,
        blocked_criteria=blocked, coverage_floor=profile['coverage_floor'])
    # Applicability and geometry participate in quality; they are not extra grades.
    geometry = selected('sun_altitude')
    if not unusable(geometry, 'degree'):
        applicability_inputs.append(geometry.evidence.provenance)
    result.quality = Quality.worst_of([result.quality, *(item.quality for item in applicability_inputs)], flags=result.quality.flags)
    ages = [result.freshness, *(item.freshness for item in applicability_inputs)]
    result.freshness = Freshness(status='unknown') if any(item.age_seconds is None for item in ages) else max(ages, key=lambda item: item.age_seconds)
    sources = {row.input.evidence.provenance.source_id for row in [*result.hard_stops, *result.criteria] if row.input.evidence is not None and row.input.evidence.provenance.source_id != 'nasa-jpl-de442'}
    steps = [(resolutions or {}).get(source) for source in sources]
    resolution = 3600 if tier == 'core' else max(steps) if steps and all(steps) else None
    return {'profile_id': profile['id'], 'profile_version': profile['version'], 'title': profile['title'],
            'method': ACTIVITY_VERDICT, 'method_version': '1', **result.model_dump(mode='json'),
            'tier': tier, 'resolution_seconds': resolution, 'evaluated_at': at.isoformat(), 'window': dict(window),
            'overrides': record_overrides(profile, active_overrides).as_dict(),
            'applicability': applicability, 'intended_weights': profile['intended_weights'],
            'active_weights': profile['weights'], 'admission_residuals': profile['admission_residuals'],
            'blocked_fields': profile['blocked_fields'], 'wanted_not_catalogued': profile['wanted_not_catalogued'],
            'saved_stack': profile['saved_stack'], 'thresholds': profile['thresholds'],
            'site_inputs': [{'field': row['field'], 'state': 'no_site' if site_id is None else 'sector_query_not_implemented'} for row in profile['site_needs']['sectors']]}
