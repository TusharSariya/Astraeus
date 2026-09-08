"""Explicit nonsecret configuration for historical WeatherNext API delivery.

The JSON selects a known run/root generation and an existing gcloud profile.
No credential file, token, ADC discovery, provider request or login occurs here.
"""
from functools import lru_cache
import json
import os
from pathlib import Path
import shutil
import sys

from .source_contract import SourceConfiguration
from .weathernext_delivery import HistoricalConfiguration, WeatherNextHistoricalDelivery
from .weathernext_native import ObjectIdentity

CONFIG_ENV='WEATHER_WEATHERNEXT_HISTORICAL_CONFIG'
CONFIG_MAX_BYTES=16384


class HistoricalConfigurationUnavailable(RuntimeError):
    pass


def load_historical_configuration():
    """Read only the explicitly named nonsecret JSON, bounded before parsing."""
    path=os.environ.get(CONFIG_ENV)
    if not path:
        raise HistoricalConfigurationUnavailable('WeatherNext historical configuration is missing')
    try:
        with Path(path).open('rb') as file:
            body=file.read(CONFIG_MAX_BYTES+1)
        if len(body)>CONFIG_MAX_BYTES:raise ValueError('configuration bound')
        document=json.loads(body)
        if set(document)!={'initialization','root_identity','gcloud_profile'}:
            raise ValueError('configuration keys')
        from datetime import datetime
        return HistoricalConfiguration(datetime.fromisoformat(document['initialization']),
            ObjectIdentity(**document['root_identity']),document['gcloud_profile'])
    except Exception:
        raise HistoricalConfigurationUnavailable('WeatherNext historical configuration is invalid or unreadable') from None


def historical_configuration_status():
    try:
        load_historical_configuration()
    except HistoricalConfigurationUnavailable:
        return SourceConfiguration(state='missing_configuration',required_environment=[CONFIG_ENV],
            reason='Select an explicit historical root generation and existing gcloud profile in the bounded nonsecret configuration JSON')
    if shutil.which('gcloud') is None:
        return SourceConfiguration(state='product_unavailable',reason='The historical runtime requires the gcloud executable; configuration does not establish authentication or ADC')
    if sys.platform!='linux' and shutil.which('docker') is None:
        return SourceConfiguration(state='missing_compute',reason='The historical decoder requires the existing bounded Linux worker runtime')
    return SourceConfiguration(state='ready',reason='Historical root and runtime tools are configured; authentication, exact-object access and sampled coverage are established only on read')


@lru_cache(maxsize=1)
def _service(configuration):
    return WeatherNextHistoricalDelivery(configuration)


def weathernext_historical_service():
    configuration=load_historical_configuration()
    return _service(configuration)
