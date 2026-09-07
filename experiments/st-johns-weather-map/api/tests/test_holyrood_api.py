"""Exact native image delivery; GOV-SPEC-001/002/004/005/006 experiment."""
from datetime import timedelta

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from weather_api.holyrood_api import PREFIX, holyrood_service, router
from test_holyrood_query import service
from test_experimental_holyrood_radar import GIF, RAIN, SNOW, listing
from ingest.experimental.holyrood_radar import BASE_URL

SELECTED = '2026-09-06T04:54:00Z'


def setup_api():
    query, requests, clock, responses = service()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[holyrood_service] = lambda: query
    return TestClient(app), query, requests, clock, responses


def test_metadata_exact_byte_routes_and_closed_schema():
    client, _, requests, _, _ = setup_api()
    response = client.get(PREFIX, params={'valid_time': SELECTED})
    assert response.status_code == 200
    data = response.json()
    assert data['valid_time'] == SELECTED
    assert data['scientific_freshness'] == data['source_quality'] == 'unknown'
    assert data['operational'] is data['primary'] is False
    assert response.headers['cache-control'] == 'no-store'
    for image in data['images']:
        byte_response = client.get(image['image_url'])
        assert byte_response.content == GIF
        assert byte_response.headers['content-type'] == 'image/gif'
        assert byte_response.headers['etag'] == '"' + image['receipt']['sha256'] + '"'
        assert byte_response.headers['cache-control'] == 'no-store'
    assert len(requests) == 3
    schemas = client.get('/openapi.json').json()['components']['schemas']
    assert schemas['HolyroodImagesResponse']['additionalProperties'] is False


@pytest.mark.parametrize('value', [None, '2026-09-06T04:54:00', 'invalid'])
def test_selected_time_required_and_aware_before_acquisition(value):
    client, _, requests, _, _ = setup_api()
    response = client.get(PREFIX, params={} if value is None else {'valid_time': value})
    assert response.status_code == 422
    assert requests == []


def test_exact_older_pair_selection_and_missing_time_refusal():
    client, _, requests, _, responses = setup_api()
    newer_rain, newer_snow = RAIN.replace('0454', '0455'), SNOW.replace('0454', '0455')
    responses[BASE_URL + '/'] = listing(RAIN, SNOW, newer_rain, newer_snow)
    # Newer paired URLs deliberately absent: selecting older must not fetch them.
    assert client.get(PREFIX, params={'valid_time': SELECTED}).status_code == 200
    assert client.get(PREFIX, params={'valid_time': '2026-09-06T04:53:00Z'}).status_code == 503
    assert len(requests) == 4
    # Failure selecting a different time preserves an unexpired retained pair.
    assert client.get(PREFIX, params={'valid_time': SELECTED}).json()['cache_status'] == 'hit'
    assert len(requests) == 4


def test_expired_and_unknown_revision_never_acquire():
    client, _, requests, clock, _ = setup_api()
    assert client.get(f'{PREFIX}/{"0" * 64}/Rain.gif').status_code == 404
    assert not requests
    data = client.get(PREFIX, params={'valid_time': SELECTED}).json()
    clock[0] += timedelta(seconds=60)
    assert client.get(data['images'][0]['image_url']).status_code == 404
    assert len(requests) == 3
    assert client.get(f'{PREFIX}/invalid/Rain.gif').status_code == 422
    assert client.get(f'{PREFIX}/{"0" * 64}/Contingency.gif').status_code == 422
    assert len(requests) == 3


def test_refresh_replaces_exact_pair_and_safe_provider_failure():
    client, _, requests, _, responses = setup_api()
    first = client.get(PREFIX, params={'valid_time': SELECTED}).json()
    responses[BASE_URL + '/' + SNOW] = b'GIF87a' + GIF[6:]
    second = client.get(PREFIX, params={'valid_time': SELECTED, 'refresh': True}).json()
    assert second['cache_status'] == 'refresh'
    assert client.get(first['images'][0]['image_url']).status_code == 404
    assert client.get(second['images'][1]['image_url']).content == b'GIF87a' + GIF[6:]
    responses[BASE_URL + '/'] = httpx.Response(503, text='private upstream details')
    failure = client.get(PREFIX, params={'valid_time': SELECTED, 'refresh': True})
    assert failure.status_code == 503 and 'private' not in failure.text
    assert client.get(second['images'][0]['image_url']).status_code == 200
    assert len(requests) == 7
