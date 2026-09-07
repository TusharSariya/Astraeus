"""Activity v1 curves selected in #49/#64; no per-profile scoring code.

Anchors are named profile thresholds. Validation is shared by the registry audit
and request-time overrides so changing an anchor cannot bypass its ordering.
"""
from __future__ import annotations

import math
import operator
from dataclasses import dataclass
from typing import Mapping

CITATION = 'desktop-evidence-api-contract/activity-verdict; Wayfinder #49 and #64; ADR 0002'
COMPARISONS = {'ge': operator.ge, 'gt': operator.gt, 'le': operator.le, 'lt': operator.lt}


@dataclass(frozen=True)
class Curve:
    name: str
    parameters: tuple[str, ...]
    optional: tuple[str, ...] = ()
    citation: str = CITATION


CURVES = {
    'step': Curve('step', ('threshold',)),
    'linear': Curve('linear', ('start', 'full')),
    'exponential': Curve('exponential', ('start', 'scale'), ('k',)),
    'band': Curve('band', ('low_full', 'low_start', 'high_start', 'high_full'), ('low_cap',)),
}


def parameters(grade: Mapping, thresholds: Mapping, overrides: Mapping | None = None) -> dict[str, float]:
    """Resolve anchors without accepting inline numeric field-unit parameters."""
    if overrides and set(overrides) - set(thresholds):
        raise ValueError('override names an undeclared threshold')
    curve = CURVES.get(grade.get('curve'))
    if curve is None:
        raise ValueError('unregistered grading curve')
    anchors = grade.get('parameters', {})
    if not isinstance(anchors, Mapping) or set(anchors) - set(curve.parameters + curve.optional) or set(curve.parameters) - set(anchors):
        raise ValueError(f'{curve.name}: incorrect curve parameters')
    result = {}
    for name, key in anchors.items():
        if not isinstance(key, str) or key not in thresholds:
            raise ValueError(f'{name}: parameter must name a declared threshold')
        spec = thresholds[key]
        if name in ('k', 'low_cap') and overrides and key in overrides:
            raise ValueError(f'{key}: dimensionless shape parameter is not overridable')
        value = (overrides or {}).get(key, spec.get('default'))
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f'{key}: threshold must be finite')
        if name in ('k', 'low_cap') and spec.get('units') != '1':
            raise ValueError(f'{key}: shape parameter must use units 1')
        result[name] = float(value)
    validate(grade.get('curve'), result, grade.get('comparison'))
    return result


def validate(curve: str, p: Mapping[str, float], comparison: str | None) -> None:
    if curve not in CURVES:
        raise ValueError('unregistered grading curve')
    if (curve != 'band' or comparison is not None) and comparison not in COMPARISONS:
        raise ValueError('invalid comparison')
    if curve == 'linear' and not math.isfinite(p['full'] - p['start']):
        raise ValueError('linear anchor span must be finite')
    if curve == 'linear' and not (p['start'] < p['full'] if comparison in ('ge', 'gt') else p['start'] > p['full']):
        raise ValueError('linear anchors contradict comparison')
    if curve == 'exponential' and (p['scale'] <= 0 or p.get('k', 2) <= 0):
        raise ValueError('exponential scale and k must be positive')
    if curve == 'band' and not (p['low_full'] < p['low_start'] <= p['high_start'] < p['high_full'] and 0 <= p.get('low_cap', 1) <= 1):
        raise ValueError('band anchors or low_cap are invalid')


def loss(value: float, grade: Mapping, thresholds: Mapping, overrides: Mapping | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('grading requires a finite native value')
    p = parameters(grade, thresholds, overrides)
    curve, comparison = grade['curve'], grade.get('comparison')
    if curve == 'step':
        return float(COMPARISONS[comparison](value, p['threshold']))
    if curve == 'linear':
        return max(0., min(1., (value - p['start']) / (p['full'] - p['start'])))
    if curve == 'exponential':
        distance = (value - p['start']) * (1 if comparison in ('ge', 'gt') else -1)
        if distance <= 0:
            return 0.
        # Saturation avoids overflow; it does not extrapolate beyond full loss.
        try:
            power = (distance / p['scale']) ** p.get('k', 2)
        except OverflowError:
            return 1.
        return -math.expm1(-power)
    if value < p['low_start']:
        return min(p.get('low_cap', 1.), max(0., (p['low_start'] - value) / (p['low_start'] - p['low_full'])))
    return max(0., min(1., (value - p['high_start']) / (p['high_full'] - p['high_start'])))
