"""GOV-SPEC-001/002/004/005/006 native outlook experimental readback."""
import json
from datetime import timedelta
from dataclasses import replace
import pytest
from ingest.adapters.eccc_hazards import ECCCThunderstormOutlookAdapter
from weather_api.thunderstorm_outlook_query import ThunderstormOutlookQuery, OutlookUnavailable
from test_adapter_eccc_hazards import client, collection, NOW

FEATURE = {'type': 'Feature', 'id': 'report-v2', 'geometry': {'type':'Polygon','coordinates':[[[-53,47],[-52,47],[-52,48],[-53,47]]]}, 'properties': {'publication_datetime': NOW.isoformat(), 'validity_datetime': NOW.isoformat(), 'expiration_datetime': (NOW+timedelta(hours=6)).isoformat(), 'file_id':'native-file', 'amendment':2, 'metobject.gust.value':80, 'metobject.gust.unit':'km/h'}}


def setup(document=None):
    documents={'thunderstorm_outlook': document or collection([FEATURE])}
    adapter=ECCCThunderstormOutlookAdapter(client(documents))
    calls=[]
    discover=adapter.discover
    def observed(window):
        calls.append(window)
        return discover(window)
    adapter.discover=observed
    clock=[NOW]
    ticks=[0.0]
    query=ThunderstormOutlookQuery(adapter=adapter,clock=lambda:clock[0],monotonic=lambda:ticks[0])
    return query,documents,calls,clock,ticks


def test_native_exact_report_preserves_geometry_versions_intervals_units_and_cache():
    query,_,calls,_,_=setup()
    entry=query.snapshot()
    assert query.report(revision=entry.revision,feature_id='report-v2',publication_time=NOW)==FEATURE
    assert query.snapshot().cache_status=='hit' and len(calls)==1
    metadata=entry.metadata()
    assert metadata['operational'] is metadata['primary'] is False
    assert metadata['reports'][0]['amendment']==2
    assert metadata['scientific_freshness']=='unknown'
    report=query.report(revision=entry.revision,feature_id='report-v2',publication_time=NOW)
    report['properties']['amendment']=99
    assert query.report(revision=entry.revision,feature_id='report-v2',publication_time=NOW)==FEATURE


def test_empty_snapshot_has_no_invented_report_or_source_time():
    query,_,_,_,_=setup(collection([]))
    entry=query.snapshot()
    assert entry.metadata()['reports']==[] and entry.metadata()['observed_empty'] is True
    with pytest.raises(OutlookUnavailable):
        query.report(revision=entry.revision,feature_id='none',publication_time=NOW)


@pytest.mark.parametrize('change', ['next','truncated','duplicate','missing-id'])
def test_incomplete_or_ambiguous_native_collection_refused(change):
    document=collection([FEATURE])
    if change=='next': document['links']=[{'rel':'next','href':'https://untrusted.invalid'}]
    if change=='truncated': document['numberMatched']=2
    if change=='duplicate': document=collection([FEATURE,FEATURE])
    if change=='missing-id': document=collection([{k:v for k,v in FEATURE.items() if k!='id'}])
    query,_,_,_,_=setup(document)
    with pytest.raises(OutlookUnavailable): query.snapshot()
    assert query._entry is None


def test_exact_time_and_revision_refusal_is_cache_only():
    query,_,calls,_,_=setup()
    entry=query.snapshot()
    for revision,stamp in [('unknown',NOW),(entry.revision,NOW+timedelta(minutes=1))]:
        with pytest.raises(OutlookUnavailable): query.report(revision=revision,feature_id='report-v2',publication_time=stamp)
    assert len(calls)==1


def test_refresh_replacement_and_failed_refresh_retention():
    query,documents,calls,_,_=setup()
    first=query.snapshot()
    changed=json.loads(json.dumps(FEATURE)); changed['properties']['amendment']=3
    documents['thunderstorm_outlook']=collection([changed])
    second=query.snapshot(refresh=True)
    assert second.revision!=first.revision
    with pytest.raises(OutlookUnavailable): query.retained(first.revision)
    documents['thunderstorm_outlook']={'bad':True}
    with pytest.raises(OutlookUnavailable): query.snapshot(refresh=True)
    assert query.retained(second.revision).body==second.body and len(calls)==3


@pytest.mark.parametrize('rollback',[False,True])
def test_expiry_never_refreshes_or_extends_retention(rollback):
    query,_,calls,clock,ticks=setup()
    entry=query.snapshot()
    clock[0]+=timedelta(seconds=-120 if rollback else 60)
    ticks[0]+=60
    with pytest.raises(OutlookUnavailable): query.retained(entry.revision)
    assert len(calls)==1
