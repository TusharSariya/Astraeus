"""Hand-calculated boundary examples for the accepted #49/#64 curves."""
import math

import pytest

from registry.grading import loss, parameters


def curve(name, values, comparison='ge'):
    return {'curve': name, 'comparison': comparison, 'parameters': {k: k for k in values}}, {
        k: {'default': value, 'units': '1' if k in ('k', 'low_cap') else 'percent'} for k, value in values.items()
    }


def test_temperature_band_boundaries_and_comfort():
    grade, thresholds = curve('band', dict(low_full=-27, low_start=0, high_start=20, high_full=30))
    assert [loss(v, grade, thresholds) for v in (-40, -27, -13.5, 0, 10, 20, 25, 30, 40)] == [1, 1, .5, 0, 0, 0, .5, 1, 1]


def test_landscape_low_cap_does_not_reduce_high_side():
    grade, thresholds = curve('band', dict(low_full=0, low_start=20, high_start=70, high_full=100, low_cap=.5))
    assert [loss(v, grade, thresholds) for v in (-10, 0, 10, 15, 20, 70, 85, 100)] == [.5, .5, .5, .25, 0, 0, .5, 1]


def test_aurora_loss_direction_and_linear_clamping():
    grade, thresholds = curve('linear', {'start': 5, 'full': 1}, 'le')
    assert [loss(v, grade, thresholds) for v in (0, 1, 3, 5, 9)] == [1, 1, .5, 0, 0]


@pytest.mark.parametrize('comparison,expected', [('ge', 1), ('gt', 0), ('le', 1), ('lt', 0)])
def test_step_keeps_comparison_inclusivity(comparison, expected):
    grade, thresholds = curve('step', {'threshold': 5}, comparison)
    assert loss(5, grade, thresholds) == expected


def test_exponential_native_direction_and_large_values():
    grade, thresholds = curve('exponential', {'start': 10, 'scale': 5})
    assert loss(9, grade, thresholds) == 0
    assert loss(15, grade, thresholds) == pytest.approx(1 - math.exp(-1))
    assert loss(1e308, grade, thresholds) == 1
    grade['comparison'] = 'le'
    assert loss(5, grade, thresholds) == pytest.approx(1 - math.exp(-1))


def test_overrides_cannot_invert_anchors_or_change_shape_parameters():
    grade, thresholds = curve('linear', {'start': 10, 'full': 30})
    with pytest.raises(ValueError, match='anchors'): parameters(grade, thresholds, {'start': 40})
    grade, thresholds = curve('band', dict(low_full=0, low_start=20, high_start=70, high_full=100, low_cap=.5))
    with pytest.raises(ValueError, match='not overridable'): parameters(grade, thresholds, {'low_cap': 1})
    with pytest.raises(ValueError, match='finite'): loss(float('nan'), grade, thresholds)
    grade['parameters']['low_full'] = 0
    with pytest.raises(ValueError, match='declared threshold'): parameters(grade, thresholds)


def test_unknown_overrides_and_nonfinite_anchor_spans_are_refused():
    grade, thresholds = curve('linear', {'start': -1e308, 'full': 1e308})
    with pytest.raises(ValueError, match='span'): parameters(grade, thresholds)
    grade, thresholds = curve('linear', {'start': 0, 'full': 1})
    with pytest.raises(ValueError, match='undeclared'): parameters(grade, thresholds, {'mystery': 3})
