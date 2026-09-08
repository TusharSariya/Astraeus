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
from .weathernext_delivery import (HistoricalConfiguration, WeatherNextHistoricalDelivery,
    LocalExperimentalConfiguration, WeatherNextLocalExperimentalDelivery)
from .weathernext_native import ObjectIdentity

CONFIG_ENV='WEATHER_WEATHERNEXT_HISTORICAL_CONFIG'
LOCAL_CONFIG_ENV='WEATHER_WEATHERNEXT_LOCAL_CONFIG'
CONFIG_MAX_BYTES=16384


class HistoricalConfigurationUnavailable(RuntimeError):
    pass


class LocalExperimentalConfigurationUnavailable(HistoricalConfigurationUnavailable):
    pass


def _load_configuration(env, configuration_type, error_type, label):
    """Read only the explicitly named nonsecret JSON, bounded before parsing."""
    path=os.environ.get(env)
    if not path:
        raise error_type(f'WeatherNext {label} configuration is missing')
    try:
        with Path(path).open('rb') as file:
            body=file.read(CONFIG_MAX_BYTES+1)
        if len(body)>CONFIG_MAX_BYTES:raise ValueError('configuration bound')
        document=json.loads(body)
        if set(document)!={'initialization','root_identity','gcloud_profile'}:
            raise ValueError('configuration keys')
        from datetime import datetime
        return configuration_type(datetime.fromisoformat(document['initialization']),
            ObjectIdentity(**document['root_identity']),document['gcloud_profile'])
    except Exception:
        raise error_type(f'WeatherNext {label} configuration is invalid or unreadable') from None


def load_historical_configuration():
    return _load_configuration(CONFIG_ENV, HistoricalConfiguration, HistoricalConfigurationUnavailable, 'historical')


def load_local_experimental_configuration():
    return _load_configuration(LOCAL_CONFIG_ENV, LocalExperimentalConfiguration,
                               LocalExperimentalConfigurationUnavailable, 'local experimental')


def _runtime_auth_configuration():
    # Read metadata only; token contents enter only the bounded transport child.
    from .weathernext_gcs import ACCESS_TOKEN_FILE_ENV
    if ACCESS_TOKEN_FILE_ENV in os.environ:
        try:
            path = Path(os.environ[ACCESS_TOKEN_FILE_ENV])
            info = path.lstat()
            import stat
            if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or not 0 < info.st_size <= 16384 or info.st_uid != os.getuid():
                raise ValueError("private token file required")
        except (OSError, ValueError):
            return SourceConfiguration(state='missing_configuration',required_environment=[ACCESS_TOKEN_FILE_ENV],
                reason='The explicitly configured short-lived OAuth token file is missing or invalid; no alternate identity is selected')
        return None
    if shutil.which('gcloud') is None:
        return SourceConfiguration(state='product_unavailable',reason='Configure a private short-lived OAuth token file or the existing gcloud runtime; configuration alone does not establish authentication')
    return None


def historical_configuration_status():
    try:
        if os.environ.get('WEATHER_WEATHERNEXT_AUTO_RUNS') == '1':
            load_local_experimental_configuration()
        else:
            load_historical_configuration()
    except HistoricalConfigurationUnavailable:
        return SourceConfiguration(state='missing_configuration',required_environment=[CONFIG_ENV],
            reason='Select an explicit historical root generation and existing gcloud profile in the bounded nonsecret configuration JSON')
    auth = _runtime_auth_configuration()
    if auth is not None:
        return auth
    if sys.platform!='linux' and shutil.which('docker') is None:
        return SourceConfiguration(state='missing_compute',reason='The historical decoder requires the existing bounded Linux worker runtime')
    return SourceConfiguration(state='ready',reason='Historical root and runtime tools are configured; authentication, exact-object access and sampled coverage are established only on read')


@lru_cache(maxsize=8)
def _service(configuration):
    return WeatherNextHistoricalDelivery(configuration)


def weathernext_historical_service():
    configuration=load_historical_configuration()
    return _service(configuration)


def local_experimental_configuration_status():
    try:
        load_local_experimental_configuration()
    except HistoricalConfigurationUnavailable:
        return SourceConfiguration(state='missing_configuration',required_environment=[LOCAL_CONFIG_ENV],
            reason='Select an explicit local experimental root generation and existing gcloud profile in the bounded nonsecret configuration JSON')
    auth = _runtime_auth_configuration()
    if auth is not None:
        return auth
    if sys.platform!='linux' and shutil.which('docker') is None:
        return SourceConfiguration(state='missing_compute',reason='The local experimental decoder requires the existing bounded Linux worker runtime')
    return SourceConfiguration(state='ready',reason='Local experimental root and runtime tools are configured; authentication, exact-object access and sampled coverage are established only on read')


@lru_cache(maxsize=8)
def _local_service(configuration):
    return WeatherNextLocalExperimentalDelivery(configuration)


def weathernext_local_experimental_service():
    return _local_service(load_local_experimental_configuration())
