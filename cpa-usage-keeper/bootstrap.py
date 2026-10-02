"""Translate Home Assistant options without writing an intermediate secret file."""
import json
import os
from pathlib import Path
import sys
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


if __name__ == '__main__':
    try:
        options = json.loads(Path('/data/options.json').read_text())
        env = environment(options)
        os.execve('/usr/local/bin/docker-entrypoint.sh', ['docker-entrypoint.sh', '/app/cpa-usage-keeper'], env)
    except (ValueError, OSError) as exc:
        print(str(exc) if isinstance(exc, ValueError) and not isinstance(exc, json.JSONDecodeError) else 'Unable to load app options.', file=sys.stderr)
        sys.exit(1)
