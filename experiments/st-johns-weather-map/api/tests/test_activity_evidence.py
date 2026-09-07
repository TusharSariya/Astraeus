from datetime import UTC, datetime, timedelta

import pytest

from ingest.derive.registry import ACTIVITY_VERDICT, REGISTRY
from weather_api.fixtures import point_fields
from weather_api.models import Freshness, Quality
from weather_api.profiles.evidence import criterion, select_input

AT = datetime(2026, 9, 7, 12, tzinfo=UTC)
ORDER = ('eccc-hrdps', 'eccc-rdps', 'noaa-gfs')
PROFILE = {'thresholds': {'start': {'field': 'temperature_2m', 'default': 20, 'units': 'degC', 'comparison': 'ge'},
                          'full': {'field': 'temperature_2m', 'default': 30, 'units': 'degC', 'comparison': 'ge'}},
           'weights': {'heat': .25}}
GRADE = {'name': 'heat', 'field': 'temperature_2m', 'weight': 'heat',
         'grade': {'curve': 'linear', 'comparison': 'ge', 'parameters': {'start': 'start', 'full': 'full'}}}
STOP = {'name': 'heat_test_stop', 'field': 'temperature_2m', 'threshold': 'full'}


def sample(value=25, source='eccc-hrdps', at=AT):
    row = point_fields(at)[0][0].model_copy(deep=True)
    row.value = value
    row.provenance.source_id = source
    row.provenance.valid_time = at
    return row


def test_exact_source_selection_discloses_skipped_sources_and_never_averages():
    primary = sample(at=AT - timedelta(milliseconds=1))
    secondary = sample(source='eccc-rdps')
    selected = select_input('temperature_2m', AT, [primary, secondary, sample(99, 'noaa-gfs')], ORDER)
    assert selected.evidence == secondary
    assert selected.fell_to_next_source
    assert [item.source_id for item in selected.skipped] == ['eccc-hrdps']
    result = criterion(PROFILE, GRADE, selected, hard_stop=False)
    assert result.loss == .5 and result.evaluated_weight == .25 and result.weight_held == .125
    assert result.input.evidence.provenance.source_id == 'eccc-rdps'


def test_failed_quality_keeps_original_value_without_evaluating_or_hiding_behind_next_source():
    row = sample()
    row.provenance.quality = Quality(status='failed', flags=['fixed_qc_failure'])
    selected = select_input('temperature_2m', AT, [row, sample(20, 'eccc-rdps')], ORDER)
    result = criterion(PROFILE, GRADE, selected, hard_stop=False)
    assert result.reason == 'quality_failed'
    assert result.input.evidence.value == 25
    assert result.loss is None and result.evaluated_weight == 0 and result.weight_held is None
    assert not selected.fell_to_next_source


def test_null_and_ambiguous_native_rows_do_not_become_clear_hard_stops():
    for rows in ([], [sample(None)], [sample(25), sample(30)]):
        selected = select_input('temperature_2m', AT, rows, ORDER)
        result = criterion(PROFILE, STOP, selected, hard_stop=True)
        assert result.outcome == 'unknown' and result.reason
        assert result.weight_held is None


def test_suspect_and_unknown_quality_and_stale_retrieval_remain_inspectable_evaluated_inputs():
    for quality in ('suspect', 'unknown'):
        row = sample()
        row.provenance.quality = Quality(status=quality)
        row.provenance.freshness = Freshness(status='stale', age_seconds=999, threshold_seconds=60)
        result = criterion(PROFILE, GRADE, select_input('temperature_2m', AT, [row], ORDER), hard_stop=False)
        assert result.outcome == 'evaluated' and result.loss == .5
        assert result.input.evidence.provenance.quality.status == quality
        assert result.input.evidence.provenance.freshness.status == 'stale'


def test_native_units_and_anchor_fields_cannot_be_silently_converted():
    row = sample()
    row.provenance.normalized_units = 'K'
    result = criterion(PROFILE, GRADE, select_input('temperature_2m', AT, [row], ORDER), hard_stop=False)
    assert result.reason == 'unit_mismatch' and result.loss is None
    with pytest.raises(ValueError, match='anchors/input'):
        criterion(PROFILE, GRADE, select_input('wind_speed_10m', AT, [], ORDER), hard_stop=False)


def test_registered_entry_is_single_profile_input_switchable_and_refuses_out_of_range(monkeypatch):
    entry = REGISTRY.require(ACTIVITY_VERDICT)
    assert len(entry.inputs) == 1 and entry.inputs[0].kind == 'profile'
    assert entry.reader_switchable and entry.version == '1'
    monkeypatch.setenv('WEATHER_DERIVED_HERE', '1')
    assert REGISTRY.resolve(ACTIVITY_VERDICT, reader_disabled=[ACTIVITY_VERDICT]).code == 'reader_disabled'
    assert entry.output.range_rule == 'null' and (entry.output.minimum, entry.output.maximum) == (0, 100)


@pytest.mark.parametrize('flag', ['derivation_refused', 'provenance_unmodelled', 'contract_incomplete', 'statistic_refused'])
def test_refused_numeric_input_cannot_become_an_evaluated_criterion(flag):
    row = sample()
    row.provenance.quality.flags.append(flag)
    result = criterion(PROFILE, GRADE, select_input('temperature_2m', AT, [row], ORDER), hard_stop=False)
    assert result.reason == flag and result.evaluated_weight == 0
    assert result.input.evidence.value == 25
