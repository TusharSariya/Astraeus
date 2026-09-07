"""Aggregate already-admitted criterion evidence using the selected #64 mechanics.

This seam chooses no field admission, active weight normalization, applicability,
source, geometry or acquisition policy. Its lazy grading callback lets a fired
hard stop prevent grading altogether. Callers must provide an accepted unit-sum
budget and independently resolved geometry/applicability conditions.
"""
from __future__ import annotations

import math
from decimal import Decimal
from typing import Callable, Literal, Mapping, Sequence

from pydantic import Field

from ..models import Freshness, Quality, StrictModel
from .evidence import CriterionEvidence


class VerdictCoverage(StrictModel):
    declared: float = Field(ge=0, le=1)
    reachable: float = Field(ge=0, le=1)
    evaluated: float | None = Field(default=None, ge=0, le=1)
    floor: float = Field(ge=0, le=1)
    reason: str | None = None


class VerdictResult(StrictModel):
    state: Literal['unresolved', 'stopped', 'unchecked', 'unscorable', 'outside_window', 'scored']
    flags: list[str]
    unresolved_fields: list[str]
    score: int | None = Field(default=None, ge=0, le=100)
    limiting_criterion: str | None = None
    hard_stops: list[CriterionEvidence]
    criteria: list[CriterionEvidence]
    coverage: VerdictCoverage
    quality: Quality
    freshness: Freshness


def _evidence_summary(rows: Sequence[CriterionEvidence]) -> tuple[Quality, Freshness]:
    evaluated = [row.input.evidence.provenance for row in rows
                 if row.input.evidence is not None and row.outcome in ('clear', 'fired', 'evaluated')]
    quality = Quality.worst_of([item.quality for item in evaluated],
                              flags=list(dict.fromkeys(flag for item in evaluated for flag in item.quality.flags)))
    ages = [item.freshness for item in evaluated]
    # An unknown age cannot be replaced by the oldest *known* age and called fresh.
    if not ages or any(item.age_seconds is None for item in ages):
        freshness = Freshness(status='unknown')
    else:
        freshness = max(ages, key=lambda item: item.age_seconds).model_copy(deep=True)
    return quality, freshness


def aggregate_verdict(
    *,
    weights: Mapping[str, float],
    hard_stops: Sequence[CriterionEvidence],
    grade: Callable[[], Sequence[CriterionEvidence]],
    outside_window: bool | None,
    unresolved_fields: Sequence[str] = (),
    blocked_criteria: Sequence[str] = (),
    coverage_floor: float = .60,
) -> VerdictResult:
    """Apply first-match state precedence without repairing an incomplete budget.

    ``weights`` is keyed by criterion name in profile-file order. Zero-weight
    context has no row in the grading callback. Blocked criteria are named by
    the caller's admission/access classification, not inferred from absent data.
    All positive criteria, including blocked/absent ones, must retain a row when
    grading runs, so an omitted row cannot silently improve coverage or score.
    """
    if not weights or any(isinstance(value, bool) or not math.isfinite(value) or value < 0 or value > 1 for value in weights.values()):
        raise ValueError('active weights must be finite fractions')
    declared = math.fsum(weights.values())
    if not math.isclose(declared, 1.0, rel_tol=0, abs_tol=1e-12):
        raise ValueError('active positive weights must sum to 1; normalization is not inferred')
    if coverage_floor != .60:
        raise ValueError('the selected coverage floor is 0.60')
    active = {name: value for name, value in weights.items() if value > 0}
    blocked = set(blocked_criteria)
    if not blocked.issubset(active):
        raise ValueError('blocked criteria must name active profile criteria')
    stops = [CriterionEvidence.model_validate(row.model_dump(round_trip=True)) for row in hard_stops]
    if any(row.kind != 'hard_stop' or row.outcome not in ('clear', 'fired', 'unknown') for row in stops):
        raise ValueError('invalid hard-stop evidence')
    if len({row.name for row in stops}) != len(stops):
        raise ValueError('duplicate hard-stop identity')
    fired = any(row.outcome == 'fired' for row in stops)
    unchecked = any(row.outcome == 'unknown' for row in stops)
    unresolved = list(dict.fromkeys(unresolved_fields))
    if outside_window is None and not unresolved:
        raise ValueError('unresolved geometry must name its absent fields')
    reachable = math.fsum(value for name, value in active.items() if name not in blocked)
    rows: list[CriterionEvidence] = []
    evaluated_weight = None
    score = None
    limiting = None
    if not fired:
        supplied = [CriterionEvidence.model_validate(row.model_dump(round_trip=True)) for row in grade()]
        if len(supplied) != len(active) or {row.name for row in supplied} != set(active):
            raise ValueError('grading must retain exactly every positive-weight criterion')
        by_name = {row.name: row for row in supplied}
        rows = [by_name[name] for name in active]
        for row in rows:
            weight = active[row.name]
            if row.kind != 'grade' or row.weight_declared != weight or row.evaluated_weight not in (0, weight):
                raise ValueError('criterion evidence does not match the declared budget')
            if row.outcome == 'evaluated':
                if row.loss is None or row.evaluated_weight != weight or row.input.evidence is None or row.name in blocked:
                    raise ValueError('evaluated criterion lacks eligible evidence or weight')
            elif row.outcome != 'unknown' or row.loss is not None or row.evaluated_weight != 0:
                raise ValueError('unevaluated criterion cannot carry loss or evaluated weight')
        evaluated_weight = math.fsum(row.evaluated_weight for row in rows)
        evaluated_rows = [row for row in rows if row.outcome == 'evaluated']
        if evaluated_rows:
            # Stable max preserves profile order on equal weighted losses.
            limiting = max(evaluated_rows, key=lambda row: Decimal(str(row.weight_declared)) * Decimal(str(row.loss))).name
        if evaluated_weight >= coverage_floor:
            score = round(100 * (1 - math.fsum(row.weight_declared * row.loss for row in evaluated_rows) / evaluated_weight))
    unscorable = evaluated_weight is not None and evaluated_weight < coverage_floor
    conditions = [('unresolved', bool(unresolved)), ('stopped', fired), ('unchecked', unchecked),
                  ('unscorable', unscorable), ('outside_window', outside_window is True)]
    flags = [name for name, applies in conditions if applies]
    state = flags[0] if flags else 'scored'
    if state not in ('scored', 'outside_window'):
        score = None
    quality, freshness = _evidence_summary([*stops, *rows])
    return VerdictResult(state=state, flags=flags, unresolved_fields=unresolved, score=score,
                         limiting_criterion=limiting, hard_stops=stops, criteria=rows,
                         coverage=VerdictCoverage(declared=1, reachable=reachable, evaluated=evaluated_weight,
                                                  floor=coverage_floor, reason='grading_prevented_by_hard_stop' if fired else None),
                         quality=quality, freshness=freshness)
