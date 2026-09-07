"""Experimental evidence readback: GOV-SPEC-001/002/004/005/006."""
from dataclasses import replace
from datetime import timedelta

import httpx
import pytest

from weather_api.holyrood_presentation import image_metadata, pair_revision, retained_image
from weather_api.holyrood_query import HolyroodUnavailable, decode_image
from test_holyrood_query import service
from test_experimental_holyrood_radar import GIF, RAIN, SNOW
from ingest.experimental.holyrood_radar import BASE_URL


def test_metadata_and_actual_linux_leaf_preserve_exact_original_pair():
    query, requests, _, _ = service(decoder=decode_image)
    evidence = query.read_images()
    metadata = image_metadata(evidence)
    assert metadata['valid_time'] == evidence.valid_time
    assert metadata['operational'] is False
    assert metadata['source_quality'] == 'unknown'
    assert metadata['presentation'] == {
        'encoding': 'image/gif', 'transformation': 'unmodified-producer-image',
        'legend': 'preserved-in-producer-image', 'native_crs': None,
        'georeferencing': 'not-established', 'numeric_pixel_values': 'unavailable',
    }
    assert [item['source_filename'] for item in metadata['images']] == [RAIN, SNOW]
    for phase in ('Rain', 'Snow'):
        image = retained_image(query, revision=metadata['pair_revision'], phase=phase)
        assert image.body == GIF
        assert image.width == image.height == 1
    assert len(requests) == 3
    assert all('body' not in item and 'body' not in item['receipt'] for item in metadata['images'])


def test_missing_or_unknown_revision_and_phase_never_acquire():
    query, requests, _, _ = service()
    with pytest.raises(HolyroodUnavailable):
        retained_image(query, revision='absent', phase='Rain')
    assert not requests
    evidence = query.read_images()
    with pytest.raises(HolyroodUnavailable):
        retained_image(query, revision='absent', phase='Snow')
    with pytest.raises(HolyroodUnavailable):
        retained_image(query, revision=pair_revision(evidence), phase='Contingency')
    assert len(requests) == 3


def test_readback_does_not_extend_expiry_or_refetch_after_expiry():
    query, requests, clock, _ = service()
    evidence = query.read_images()
    clock[0] += timedelta(seconds=59)
    retained_image(query, revision=pair_revision(evidence), phase='Rain')
    assert query.retained_images().retained_until == evidence.retained_until
    clock[0] += timedelta(seconds=1)
    with pytest.raises(HolyroodUnavailable):
        retained_image(query, revision=pair_revision(evidence), phase='Snow')
    assert len(requests) == 3 and query._cached is None


def test_pair_digest_binds_both_phases_and_time():
    query, _, _, _ = service()
    evidence = query.read_images()
    snow = evidence.images[1]
    modified = replace(snow, receipt=replace(snow.receipt, sha256='1' * 64))
    assert pair_revision(replace(evidence, images=(evidence.images[0], modified))) != pair_revision(evidence)
    assert pair_revision(replace(evidence, valid_time=evidence.valid_time + timedelta(minutes=1))) != pair_revision(evidence)


def test_refresh_replacement_never_substitutes_for_advertised_revision():
    query, requests, _, responses = service()
    first = query.read_images()
    # Structurally valid, byte-distinct GIF revision at the same native time.
    responses[BASE_URL + '/' + SNOW] = b'GIF87a' + GIF[6:]
    second = query.read_images(refresh=True)
    assert pair_revision(first) != pair_revision(second)
    with pytest.raises(HolyroodUnavailable):
        retained_image(query, revision=pair_revision(first), phase='Rain')
    assert retained_image(query, revision=pair_revision(second), phase='Snow').body == b'GIF87a' + GIF[6:]
    assert len(requests) == 6


def test_failed_refresh_keeps_exact_retained_pair():
    query, requests, _, responses = service()
    first = query.read_images()
    responses[BASE_URL + '/'] = httpx.Response(503)
    with pytest.raises(HolyroodUnavailable):
        query.read_images(refresh=True)
    assert retained_image(query, revision=pair_revision(first), phase='Rain').body == GIF
    assert len(requests) == 4


def test_retained_readback_honors_monotonic_expiry_after_wall_clock_rollback():
    query, requests, clock, _ = service()
    ticks = [100.0]
    query._monotonic = lambda: ticks[0]
    first = query.read_images()
    clock[0] -= timedelta(seconds=120)
    ticks[0] += 60
    with pytest.raises(HolyroodUnavailable):
        retained_image(query, revision=pair_revision(first), phase='Rain')
    assert len(requests) == 3 and query._cached is None
