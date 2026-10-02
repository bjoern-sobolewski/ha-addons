"""Translate Home Assistant options without writing an intermediate secret file."""
import json
import os
from pathlib import Path
import sys
import subprocess
import ipaddress
import re
from urllib.parse import urlsplit


def environment(options):
    url = options.get('cpa_base_url', '').rstrip('/')
    parsed = urlsplit(url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.path not in ('', '/') or parsed.query or parsed.fragment or parsed.username:
        raise ValueError('Set cpa_base_url to the private CPA root URL, including port 8317, without /v1.')
    if len(options.get('management_key', '').strip()) < 24:
        raise ValueError('Set the same management key as the CLIProxyAPI app (24 or more characters).')
    if len(options.get('login_password', '').strip()) < 16:
        raise ValueError('Set a separate Keeper login password of 16 or more characters.')
    return {
        **os.environ,
        'CPA_BASE_URL': url,
        'CPA_MANAGEMENT_KEY': options['management_key'],
        'LOGIN_PASSWORD': options['login_password'],
        'AUTH_ENABLED': 'true',
        'API_KEY_VIEWER_QUOTA_ENABLED': 'true' if options.get('viewer_quota_enabled', False) is True else 'false',
        'APP_HOST': '0.0.0.0',
        'APP_PORT': '8080',
        'APP_BASE_PATH': '',
        'WORK_DIR': '/data',
        'TZ': options.get('timezone', 'Europe/Berlin'),
        'LOG_RETENTION_DAYS': str(options.get('log_retention_days', 7)),
        'BACKUP_RETENTION_DAYS': str(options.get('backup_retention_days', 7)),
        'LOG_FILE_ENABLED': 'true',
        'BACKUP_ENABLED': 'true',
        'CPA_REQUEST_LOG_ACCESS_ENABLED': 'false',
        'TLS_SKIP_VERIFY': 'false',
    }


def api_gateway_location(options):
    if options.get('viewer_api_gateway_enabled', False) is not True:
        return '# API forwarding disabled\n'
    # The companion HA CPA app has a fixed API-only listener on port 8080.
    # Never forward public traffic to its management listener from CPA_BASE_URL.
    parsed = urlsplit(options['cpa_base_url'])
    host = parsed.hostname
    if ':' in host:
        ipaddress.IPv6Address(host)
        host = '[' + host + ']'
    elif not re.fullmatch(r'[A-Za-z0-9_.-]+', host):
        raise ValueError('Set cpa_base_url to a valid private CPA hostname.')
    origin = f'{parsed.scheme}://{host}:8080'
    return '''location /v1/ {
      client_max_body_size 64m;
      proxy_pass ORIGIN;
      proxy_http_version 1.1;
      proxy_set_header Host $http_host;
      proxy_set_header X-Forwarded-Proto $http_x_forwarded_proto;
      proxy_set_header X-Forwarded-For $remote_addr;
      proxy_set_header Upgrade $http_upgrade;
      proxy_set_header Connection $connection_upgrade;
      proxy_buffering off;
      proxy_request_buffering off;
      proxy_read_timeout 3600s;
      proxy_send_timeout 3600s;
    }
    '''.replace('ORIGIN', origin)


if __name__ == '__main__':
    stage = 'loading options'
    try:
        options = json.loads(Path('/data/options.json').read_text())
        env = environment(options)
        stage = 'preparing gateway configuration'
        gateway_dir = Path('/run/keeper-gateway')
        gateway_dir.mkdir(mode=0o700, exist_ok=True)
        locations = Path('/opt/ha/viewer-locations.conf').read_text() if options.get('viewer_dashboard_enabled', False) is True else '# Viewer dashboard disabled\n'
        (gateway_dir / 'viewer.conf').write_text(locations)
        (gateway_dir / 'api.conf').write_text(api_gateway_location(options))
        stage = 'starting gateway'
        subprocess.run(['nginx', '-c', '/opt/ha/nginx.conf'], check=True)
        stage = 'starting Keeper'
        os.execve('/usr/local/bin/docker-entrypoint.sh', ['docker-entrypoint.sh', '/app/cpa-usage-keeper'], env)
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(str(exc) if isinstance(exc, ValueError) and not isinstance(exc, json.JSONDecodeError) else f'Unable to start app while {stage} ({type(exc).__name__}).', file=sys.stderr)
        sys.exit(1)
