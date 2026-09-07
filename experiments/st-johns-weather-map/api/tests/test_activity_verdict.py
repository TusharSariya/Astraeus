"""Constructed aggregation fixtures, not field admission or real profile scores."""
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest

from weather_api.fixtures import point_fields
from weather_api.models import Freshness, Quality
from weather_api.profiles.evidence import criterion, select_input
from weather_api.profiles.verdict import aggregate_verdict

AT = datetime(2026, 9, 7, 12, tzinfo=UTC)
PROFILE = {'thresholds': {'start': {'field': 'temperature_2m', 'default': 20, 'units': 'degC', 'comparison': 'ge'},
                          'full': {'field': 'temperature_2m', 'default': 30, 'units': 'degC', 'comparison': 'ge'}},
           'weights': {'a': .6, 'b': .4}}


def reading(value=25, *, status='passed', age=30):
    row = point_fields(AT)[0][0].model_copy(deep=True)
    row.value = value
    row.provenance.quality = Quality(status=status, flags=['fixture_native_flag'])
    row.provenance.freshness = Freshness(status='unknown' if age is None else 'fresh', age_seconds=age, threshold_seconds=600)
    return select_input('temperature_2m', AT, [row], [row.provenance.source_id])


def graded(name, value=25, **kwargs):
    return criterion(PROFILE, {'name': name, 'field': 'temperature_2m', 'weight': name,
                              'grade': {'curve': 'linear', 'comparison': 'ge', 'parameters': {'start': 'start', 'full': 'full'}}},
                     reading(value, **kwargs), hard_stop=False)


def stop(value):
    return criterion(PROFILE, {'name': 'constructed_stop', 'field': 'temperature_2m', 'threshold': 'full'}, reading(value), hard_stop=True)


def evaluate(*, rows=None, stops=(), **kwargs):
    return aggregate_verdict(weights=PROFILE['weights'], hard_stops=stops,
                             grade=lambda: rows if rows is not None else [graded('a'), graded('b')],
                             outside_window=kwargs.pop('outside_window', False), **kwargs)


@pytest.mark.parametrize('state,arguments', [
    ('scored', {}),
    ('outside_window', {'outside_window': True}),
    ('unscorable', {'rows': [graded('a', None), graded('b')]}),
    ('unchecked', {'stops': [stop(None)]}),
    ('stopped', {'stops': [stop(30)]}),
    ('unresolved', {'outside_window': None, 'unresolved_fields': ['sun_altitude']}),
])
def test_six_states_and_score_withholding(state, arguments):
    result = evaluate(**arguments)
    assert result.state == state
    assert result.score == (50 if state in ('scored', 'outside_window') else None)


def test_fired_stop_prevents_grading_and_preserves_lower_conditions():
    grade = Mock(side_effect=AssertionError('grading must not run'))
    result = aggregate_verdict(weights=PROFILE['weights'], hard_stops=[stop(30), stop(None).model_copy(update={'name': 'second'})],
                               grade=grade, outside_window=True, unresolved_fields=['sun_azimuth'])
    grade.assert_not_called()
    assert result.state == 'unresolved'
    assert result.flags == ['unresolved', 'stopped', 'unchecked', 'outside_window']
    assert result.criteria == [] and result.score is None
    assert result.coverage.evaluated is None
    assert result.coverage.reason == 'grading_prevented_by_hard_stop'


def test_unknown_stop_allows_inspection_but_withholds_score_and_retains_other_flags():
    result = evaluate(stops=[stop(None)], rows=[graded('a', None), graded('b')], outside_window=True)
    assert result.state == 'unchecked'
    assert result.flags == ['unchecked', 'unscorable', 'outside_window']
    assert len(result.criteria) == 2 and result.coverage.evaluated == .4 and result.score is None


def test_weighted_loss_and_limiting_ties_follow_profile_order_not_callback_order():
    # a loses .6 * .5 = .30; b loses .4 * .75 = .30. Total loss .60 -> 40.
    result = evaluate(rows=[graded('b', 27.5), graded('a', 25)])
    assert result.score == 40 and result.limiting_criterion == 'a'
    assert [row.name for row in result.criteria] == ['a', 'b']


def test_coverage_floor_is_inclusive_and_score_uses_only_evaluated_weight():
    result = evaluate(rows=[graded('a', 25), graded('b', None)])
    assert result.score == 50 and result.state == 'scored'
    assert result.coverage.model_dump() == {'declared': 1, 'reachable': 1, 'evaluated': .6, 'floor': .6, 'reason': None}
    blocked = evaluate(rows=[graded('a', 25), graded('b', None)], blocked_criteria=['b'])
    assert blocked.coverage.reachable == .6 and blocked.coverage.evaluated == .6
    assert blocked.score == 50  # Reachability does not renormalize the declared budget.


def test_failed_quality_cannot_improve_score_or_coverage_but_value_remains_inspectable():
    result = evaluate(rows=[graded('a', 20, status='failed'), graded('b', 30, status='suspect')])
    assert result.state == 'unscorable' and result.score is None and result.coverage.evaluated == .4
    assert result.criteria[0].input.evidence.value == 20
    assert result.criteria[0].reason == 'quality_failed'
    assert result.quality.status == 'suspect' and result.quality.derived


def test_worst_evaluated_quality_and_oldest_freshness_are_preserved_without_new_gate():
    rows = [graded('a', status='suspect', age=60), graded('b', status='unknown', age=1200)]
    rows[1].input.evidence.provenance.freshness.status = 'stale'
    result = evaluate(rows=rows)
    assert result.state == 'scored' and result.score == 50
    assert result.quality.status == 'unknown'
    assert 'fixture_native_flag' in result.quality.flags
    assert result.freshness == rows[1].input.evidence.provenance.freshness
    assert evaluate(rows=[graded('a'), graded('b', age=None)]).freshness.status == 'unknown'


def test_complete_loss_and_zero_loss_preserve_score_bounds():
    assert evaluate(rows=[graded('a', 30), graded('b', 30)]).score == 0
    assert evaluate(rows=[graded('a', 20), graded('b', 20)]).score == 100


@pytest.mark.parametrize('weights', [{'a': .85}, {'a': float('nan')}, {'a': float('inf')}, {'a': True}, {'a': -.1, 'b': 1.1}, {}])
def test_incomplete_or_invalid_budget_is_not_repaired(weights):
    with pytest.raises(ValueError, match='weights'):
        aggregate_verdict(weights=weights, hard_stops=[], grade=lambda: [], outside_window=False)


def test_missing_geometry_cannot_become_in_window_and_omitted_rows_cannot_improve_coverage():
    with pytest.raises(ValueError, match='absent fields'):
        evaluate(outside_window=None)
    with pytest.raises(ValueError, match='every positive'):
        evaluate(rows=[graded('a')])
    with pytest.raises(ValueError, match='every positive'):
        evaluate(rows=[graded('a'), graded('a')])
    with pytest.raises(ValueError, match='eligible evidence'):
        evaluate(blocked_criteria=['b'])
    with pytest.raises(ValueError, match='active profile'):
        evaluate(blocked_criteria=['unknown'])


def test_context_weight_zero_is_not_graded_and_returned_evidence_is_copied():
    rows = [graded('a'), graded('b')]
    result = aggregate_verdict(weights={**PROFILE['weights'], 'context': 0}, hard_stops=[], grade=lambda: rows, outside_window=False)
    result.criteria[0].input.evidence.value = 999
    assert rows[0].input.evidence.value == 25
    assert result.coverage.declared == 1
