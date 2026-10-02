"""Render app-owned settings and supervise the proxy and API gateway."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import yaml


def configure(data=Path('/data'), providers=Path('/config/providers.yaml')):
    options = json.loads((data / 'options.json').read_text())
    secret = options.get('management_key', '')
    source = options.get('api_key_source', 'home_assistant')
    if source not in ('home_assistant', 'management_ui'):
        raise ValueError('api_key_source must be home_assistant or management_ui.')
    target = data / 'config.yaml'
    config = yaml.safe_load(target.read_text()) if target.exists() else {}
    if not isinstance(config, dict):
        raise ValueError('Persistent config.yaml must contain a YAML mapping.')
    access = config.get('access', {})
    if not isinstance(access, dict):
        raise ValueError('Persistent access configuration must contain a YAML mapping.')
    # A present but empty list is intentional; never restore revoked keys from HA.
    keys = access['api-keys'] if source == 'management_ui' and 'api-keys' in access else options.get('api_keys', [])
    if not isinstance(keys, list) or not keys or any(not isinstance(k, str) or len(k.strip()) < 24 for k in keys):
        raise ValueError('Configure at least one random client API key of 24 or more characters in the selected key source.')
    if not isinstance(secret, str) or len(secret.strip()) < 24 or secret in keys:
        raise ValueError('Set a separate management key of 24 or more characters in app options.')
    if providers.exists():
        extra = yaml.safe_load(providers.read_text()) or {}
        if not isinstance(extra, dict) or set(extra) - {'api-keys', 'oauth', 'routing', 'requests', 'client', 'multimedia'}:
            raise ValueError('providers.yaml supports api-keys, oauth, routing, requests, client and multimedia sections.')
        for key, value in extra.items():
            config[key] = value
    config['config-version'] = 8
    config['server'] = {'host': '', 'port': 8317, 'tls': {'enable': False}, 'discovery': {'enabled': False}}
    config['access'] = {**access, 'api-keys': keys}
    config['management'] = {'allow-remote': True, 'secret-key': secret, 'disable-control-panel': False}
    config.setdefault('oauth', {})['auth-dir'] = str(data / 'auth')
    config.setdefault('requests', {}).setdefault('streaming', {})['keepalive-seconds'] = options.get('streaming_keepalive_seconds', 15)
    config['observability'] = {
        'logs': {'debug': False, 'logging-to-file': False, 'request-log': False},
        'usage': {'usage-statistics-enabled': True, 'redis-usage-queue-retention-seconds': 3600},
        'pprof': {'enable': False},
    }
    (data / 'auth').mkdir(mode=0o700, exist_ok=True)
    temporary = target.with_suffix('.tmp')
    temporary.write_text(yaml.safe_dump(config, sort_keys=False))
    temporary.chmod(0o600)
    temporary.replace(target)
    os.environ['TZ'] = options.get('timezone', 'Europe/Berlin')
    return target


def main():
    config = configure()
    children = []
    stopping = False

    def stop(signum, frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        children.append(subprocess.Popen(['/CLIProxyAPI/CLIProxyAPI', '-config', str(config)]))
        children.append(subprocess.Popen(['nginx', '-c', '/opt/ha/nginx.conf', '-g', 'daemon off;']))
        while not stopping:
            if any(child.poll() is not None for child in children):
                return 1
            time.sleep(0.25)
        return 0
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError, yaml.YAMLError) as exc:
        # YAML parser exceptions can contain credential material; don't echo them.
        print(str(exc) if isinstance(exc, ValueError) else 'Unable to load app configuration; check the private configuration files.', file=sys.stderr)
        sys.exit(1)
