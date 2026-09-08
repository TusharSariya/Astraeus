"""Refresh only the selected existing Google identity in the local API tmpfs.

No token enters arguments, stdout, logs, Git, or a host file. This does not log
in, create ADC, expose the shared credential database, or refresh automatically.
The API container must already enable WEATHER_WEATHERNEXT_ACCESS_TOKEN_FILE.
"""
import argparse
import os
import re
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', default='astraeus')
    parser.add_argument('--container', default='astraeus-st-johns-weather-api-1')
    args = parser.parse_args()
    if not re.fullmatch(r'[a-z][a-z0-9-]{0,62}', args.profile):
        parser.error('invalid profile name')
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}', args.container):
        parser.error('invalid container name')
    environment = dict(os.environ, CLOUDSDK_CORE_DISABLE_FILE_LOGGING='true',
                       CLOUDSDK_CORE_LOG_HTTP='false', CLOUDSDK_CORE_DISABLE_USAGE_REPORTING='true')
    try:
        credential = subprocess.run(['gcloud', '--configuration', args.profile, '--quiet',
            'auth', 'print-access-token'], capture_output=True, timeout=30, env=environment)
        token = credential.stdout.strip()
        if credential.returncode or not 0 < len(token) <= 16384 or not re.fullmatch(rb'[A-Za-z0-9._~+/-]+=*', token):
            raise ValueError('authentication failed')
        install = """import os,pathlib,sys
root=pathlib.Path('/tmp/weathernext-auth')
root.mkdir(mode=0o700,exist_ok=True)
if root.is_symlink() or root.stat().st_uid!=os.getuid(): raise RuntimeError('private directory required')
os.chmod(root,0o700)
expected=str(root/'access-token')
if os.environ.get('WEATHER_WEATHERNEXT_ACCESS_TOKEN_FILE')!=expected: raise RuntimeError('runtime not configured')
token=sys.stdin.buffer.read(16385)
if not 0<len(token)<=16384: raise RuntimeError('token bounds')
temporary=root/'access-token.new'
fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,'wb') as file: file.write(token)
os.replace(temporary,root/'access-token')
"""
        result = subprocess.run(['docker', 'exec', '-i', args.container, 'python', '-c', install],
            input=token, capture_output=True, timeout=15)
        if result.returncode:
            raise ValueError('runtime installation failed')
    except Exception:
        raise SystemExit('WeatherNext token refresh failed; credential and provider output were suppressed.') from None
    print('Selected Google identity token installed in local API tmpfs; refresh again after expiry or container recreation.')


if __name__ == '__main__':
    main()
