"""Exercise the packaged services with isolated, automatically cleaned Docker resources."""
import http.cookiejar
import json
from pathlib import Path
import secrets
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

import yaml

ROOT = Path(__file__).resolve().parents[1]


def docker(*args, check=True):
    result = subprocess.run(['docker', *args], capture_output=True, text=True, check=check)
    return (result.stdout + result.stderr if args and args[0] == 'logs' else result.stdout).strip()


def request(url, headers=None, body=None, opener=None):
    headers = dict(headers or {})
    if body is not None:
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, headers=headers, data=json.dumps(body).encode() if body is not None else None)
    try:
        with (opener or urllib.request.build_opener()).open(req, timeout=10) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def eventually(check, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if check():
                return
        except (OSError, subprocess.CalledProcessError):
            pass
        time.sleep(1)
    raise AssertionError('Condition did not become true within the startup/ingestion timeout')


def main():
    prefix = 'ha-cpa-smoke-' + secrets.token_hex(4)
    network = prefix + '-net'
    names = {key: prefix + '-' + key for key in ('mock', 'cpa', 'keeper')}
    volumes = [prefix + '-cpa-data', prefix + '-keeper-data']
    key, management, password = (secrets.token_urlsafe(32) for _ in range(3))
    with tempfile.TemporaryDirectory() as temporary:
        temp = Path(temporary)
        provider_dir = temp / 'config'
        provider_dir.mkdir()
        (provider_dir / 'providers.yaml').write_text(yaml.safe_dump({'api-keys': {'openai-compatibility': [{'name': 'test', 'base-url': 'http://mock:9000/v1', 'keys': [{'api-key': 'fake-upstream-test-key'}], 'models': [{'name': 'test-model', 'alias': 'test-model'}]}]}}))
        (temp / 'cpa.json').write_text(json.dumps({'api_keys': [key], 'management_key': management}))
        (temp / 'keeper.json').write_text(json.dumps({'cpa_base_url': 'http://cpa:8317', 'management_key': management, 'login_password': password}))
        try:
            docker('network', 'create', network)
            for volume in volumes:
                docker('volume', 'create', volume)
            docker('create', '--name', names['mock'], '--network', network, '--network-alias', 'mock', '-v', f'{ROOT / "tests"}:/test:ro', '--entrypoint', 'python3', 'ha-keeper-test:local', '/test/mock_provider.py')
            docker('create', '--init', '--name', names['cpa'], '--network', network, '--network-alias', 'cpa', '-v', f'{volumes[0]}:/data', '-v', f'{provider_dir}:/config:ro', '-p', '127.0.0.1::8080', '-p', '127.0.0.1::8317', 'ha-cpa-test:local')
            # Force the HTTP fallback so collection also works when CPA disables RESP.
            docker('create', '--init', '--name', names['keeper'], '--network', network, '-e', 'REDIS_QUEUE_ADDR=mock:1', '-v', f'{volumes[1]}:/data', '-p', '127.0.0.1::8080', 'ha-keeper-test:local')
            docker('cp', str(temp / 'cpa.json'), names['cpa'] + ':/data/options.json')
            docker('cp', str(temp / 'keeper.json'), names['keeper'] + ':/data/options.json')
            for name in names.values():
                docker('start', name)

            def endpoint(name, port):
                mapped = docker('port', name, f'{port}/tcp').splitlines()[0]
                return 'http://' + mapped

            api = endpoint(names['cpa'], 8080)
            private = endpoint(names['cpa'], 8317)
            keeper = endpoint(names['keeper'], 8080)
            auth = {'Authorization': 'Bearer ' + key}
            eventually(lambda: request(api + '/v1/models', auth)[0] == 200)
            assert request(api + '/v1/models')[0] == 401
            assert request(api + '/v1/models', {'Authorization': 'Bearer incorrect'})[0] == 401
            for path in ('/management.html', '/v0/management/config', '/v8/management/config', '/v1/../v8/management/config', '/v1/%2e%2e/v0/management/config'):
                assert request(api + path, {'Authorization': 'Bearer ' + management})[0] == 404, path
            assert request(private + '/v0/management/config')[0] == 401
            assert request(private + '/v0/management/config', {'Authorization': 'Bearer ' + management})[0] == 200
            body = {'model': 'test-model', 'messages': [{'role': 'user', 'content': 'hello'}]}
            status, response = request(api + '/v1/chat/completions', auth, body)
            assert status == 200, (status, response)
            assert json.loads(response)['choices'][0]['message']['content'] == 'ok'
            status, response = request(api + '/v1/chat/completions', auth, {**body, 'stream': True})
            assert status == 200 and b'data:' in response and b'[DONE]' in response
            print('PASS: API authentication, private management, path isolation, model call and SSE stream', flush=True)

            eventually(lambda: request(keeper + '/healthz')[0] == 200)
            assert request(keeper + '/api/v1/usage/overview')[0] == 401
            opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
            status, response = request(keeper + '/api/v1/auth/login', headers={'X-CPA-Usage-Keeper-Request': 'fetch'}, body={'password': password}, opener=opener)
            assert status in (200, 204), (status, response)
            assert request(keeper + '/api/v1/usage/overview?range=30d', opener=opener)[0] == 200
            query = "import sqlite3; c=sqlite3.connect('file:/data/app.db?mode=ro', uri=True); print(c.execute('SELECT count(*) FROM usage_events').fetchone()[0])"
            eventually(lambda: int(docker('exec', names['keeper'], 'python3', '-c', query)) >= 2, timeout=90)
            count = int(docker('exec', names['keeper'], 'python3', '-c', query))
            docker('exec', names['cpa'], 'sh', '-c', 'echo test > /data/auth/persistence-marker')
            docker('restart', names['cpa'], names['keeper'])
            # Docker can reassign ephemeral host ports when restarting containers.
            api = endpoint(names['cpa'], 8080)
            keeper = endpoint(names['keeper'], 8080)
            eventually(lambda: request(api + '/v1/models', auth)[0] == 200 and request(keeper + '/healthz')[0] == 200)
            assert int(docker('exec', names['keeper'], 'python3', '-c', query)) >= count
            assert docker('exec', names['cpa'], 'cat', '/data/auth/persistence-marker') == 'test'
            print('PASS: Keeper authentication, HTTP usage ingestion and persistence across restarts', flush=True)
            for service in ('cpa', 'keeper'):
                docker('stop', '-t', '25', names[service])
                code = int(docker('inspect', '--format', '{{.State.ExitCode}}', names[service]))
                assert code in (0, 143), (service, code)
            print('PASS: graceful shutdown', flush=True)
        except Exception:
            # Redact disposable credentials from any service logs before displaying.
            for name in names.values():
                logs = docker('logs', '--tail', '40', name, check=False)
                for secret in (key, management, password):
                    logs = logs.replace(secret, '[REDACTED]')
                print(name + '\n' + logs)
            raise
        finally:
            for name in names.values():
                docker('rm', '-f', '-v', name, check=False)
            docker('network', 'rm', network, check=False)
            for volume in volumes:
                docker('volume', 'rm', volume, check=False)


if __name__ == '__main__':
    main()
