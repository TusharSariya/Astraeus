"""Native source selection and criterion evidence, independent of score budgets."""
from __future__ import annotations

import math
from datetime import datetime
from typing import Literal, Mapping, Sequence

from pydantic import Field
from registry import grading

from ..models import EvidenceField, StrictModel


class SkippedSource(StrictModel):
    source_id: str
    reason: str


class SelectedInput(StrictModel):
    field: str
    evidence: EvidenceField | None = None
    reason: str | None = None
    skipped: list[SkippedSource] = Field(default_factory=list)
    fell_to_next_source: bool = False


class CriterionEvidence(StrictModel):
    name: str
    field: str
    kind: Literal['hard_stop', 'grade']
    input: SelectedInput
    threshold_defaults: dict[str, float]
    thresholds_in_force: dict[str, float]
    comparison: str | None
    outcome: Literal['fired', 'clear', 'unknown', 'evaluated']
    reason: str | None = None
    loss: float | None = Field(default=None, ge=0, le=1)
    weight_declared: float | None = Field(default=None, ge=0, le=1)
    evaluated_weight: float | None = Field(default=None, ge=0, le=1)
    weight_held: float | None = Field(default=None, ge=0, le=1)


def select_input(field: str, instant: datetime, readings: Sequence[EvidenceField], precedence: Sequence[str]) -> SelectedInput:
    """Choose the first exact, single-valued source; retain failed QC for inspection.

    The owning query service enforces native source acquisition/staleness bounds.
    Multiple eligible rows from one source are ambiguous, never arbitrarily
    collapsed across members, runs, phases or reports.
    """
    skipped = []
    absent = None
    for source in precedence:
        candidates = [row for row in readings if row.key == field and row.provenance.source_id == source and row.provenance.valid_time == instant]
        values = [row for row in candidates if row.value is not None and row.provenance.run_stale is not True]
        if len(values) == 1:
            return SelectedInput(field=field, evidence=values[0], skipped=skipped, fell_to_next_source=bool(skipped))
        if absent is None and len(candidates) == 1:
            absent = candidates[0]
        reason = 'ambiguous_native_identity' if len(values) > 1 else 'no_exact_usable_frame'
        skipped.append(SkippedSource(source_id=source, reason=reason))
    return SelectedInput(field=field, evidence=absent, reason='no_exact_usable_frame', skipped=skipped)


def unusable(selected: SelectedInput, units: str) -> str | None:
    row = selected.evidence
    if selected.reason:
        return selected.reason
    if row is None:
        return 'field_not_returned'
    if row.value is None:
        return row.absence_state or 'null'
    if isinstance(row.value, bool) or not isinstance(row.value, (int, float)) or not math.isfinite(row.value):
        return 'non_numeric_value'
    refusals = {'derivation_refused', 'provenance_unmodelled', 'uncatalogued_field', 'contract_incomplete', 'statistic_refused'} & set(row.provenance.quality.flags)
    if refusals:
        return ','.join(sorted(refusals))
    if row.provenance.evidence_class not in ('retrieved', 'derived_here'):
        return 'inadmissible_evidence_class'
    if row.provenance.normalized_units != units:
        return 'unit_mismatch'
    if row.provenance.quality.status == 'failed':
        return 'quality_failed'
    return None


def criterion(profile: Mapping, spec: Mapping, selected: SelectedInput, *, hard_stop: bool, overrides: Mapping | None = None) -> CriterionEvidence:
    """Evaluate only the declared comparison/curve; no normalization or window rule."""
    thresholds = profile['thresholds']
    if hard_stop:
        names = [spec['threshold']]
        comparison = thresholds[names[0]]['comparison']
        grade = {'curve': 'step', 'comparison': comparison, 'parameters': {'threshold': names[0]}}
    else:
        grade = spec['grade']
        names = list(grade['parameters'].values())
        comparison = grade.get('comparison')
    # Resolve even absent rows so invalid overrides never slip past a gap.
    grading.parameters(grade, thresholds, overrides)
    units = {thresholds[name]['units'] for param, name in grade['parameters'].items() if param not in ('k', 'low_cap')}
    fields = {thresholds[name].get('field') for param, name in grade['parameters'].items() if param not in ('k', 'low_cap')}
    if len(units) != 1 or fields != {spec['field']} or selected.field != spec['field']:
        raise ValueError('criterion anchors/input do not match its native field and units')
    reason = unusable(selected, next(iter(units)))
    fraction = None if reason else grading.loss(selected.evidence.value, grade, thresholds, overrides)
    weight = None if hard_stop else profile['weights'][spec['weight']]
    return CriterionEvidence(name=spec['name'], field=spec['field'], kind='hard_stop' if hard_stop else 'grade',
        input=selected, threshold_defaults={name: thresholds[name]['default'] for name in names},
        thresholds_in_force={name: (overrides or {}).get(name, thresholds[name]['default']) for name in names},
        comparison=comparison, outcome='unknown' if reason else ('fired' if fraction else 'clear') if hard_stop else 'evaluated',
        reason=reason, loss=None if hard_stop else fraction, weight_declared=weight,
        evaluated_weight=None if hard_stop else (weight if reason is None else 0),
        weight_held=None if hard_stop or reason else weight * (1 - fraction))
