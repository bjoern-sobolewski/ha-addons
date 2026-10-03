"""Exercise the packaged services with isolated, automatically cleaned Docker resources."""
import http.cookiejar
import json
from pathlib import Path
import secrets
import socket
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


def request(url, headers=None, body=None, opener=None, method=None):
    headers = dict(headers or {})
    if body is not None:
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, headers=headers, data=json.dumps(body).encode() if body is not None else None, method=method)
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
    key, management, password, rotated_key, read_only_password = (secrets.token_urlsafe(32) for _ in range(5))
    with tempfile.TemporaryDirectory() as temporary:
        temp = Path(temporary)
        provider_dir = temp / 'config'
        provider_dir.mkdir()
        (provider_dir / 'providers.yaml').write_text(yaml.safe_dump({'api-keys': {'openai-compatibility': [{'name': 'test', 'base-url': 'http://mock:9000/v1', 'keys': [{'api-key': 'fake-upstream-test-key'}], 'models': [{'name': 'test-model', 'alias': 'test-model'}]}]}}))
        (temp / 'cpa.json').write_text(json.dumps({'api_key_source': 'management_ui', 'api_keys': [key], 'management_key': management}))
        (temp / 'keeper.json').write_text(json.dumps({'cpa_base_url': 'http://cpa:8317', 'management_key': management, 'login_password': password}))
        try:
            docker('network', 'create', network)
            for volume in volumes:
                docker('volume', 'create', volume)
            docker('create', '--name', names['mock'], '--network', network, '--network-alias', 'mock', '-v', f'{ROOT / "tests"}:/test:ro', '--entrypoint', 'python3', 'ha-keeper-test:local', '/test/mock_provider.py')
            docker('create', '--init', '--name', names['cpa'], '--network', network, '--network-alias', 'cpa', '-v', f'{volumes[0]}:/data', '-v', f'{provider_dir}:/config:ro', '-p', '127.0.0.1::8080', '-p', '127.0.0.1::8317', 'ha-cpa-test:local')
            # Force the HTTP fallback so collection also works when CPA disables RESP.
            docker('create', '--init', '--name', names['keeper'], '--network', network, '-e', 'REDIS_QUEUE_ADDR=mock:1', '-v', f'{volumes[1]}:/data', '-p', '127.0.0.1::8080', '-p', '127.0.0.1::8082', 'ha-keeper-test:local')
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
            viewer_gateway = endpoint(names['keeper'], 8082)
            assert request(viewer_gateway + '/keeper/')[0] == 404
            assert request(keeper + '/api/v1/key-quota', opener=opener)[0] == 404
            # Enable explicitly and preserve the same database across restart.
            viewer_path = "/viewer-" + secrets.token_hex(12)
            (temp / 'keeper.json').write_text(json.dumps({'cpa_base_url': 'http://cpa:8317', 'management_key': management, 'login_password': password, 'read_only_password': read_only_password, 'viewer_base_path': viewer_path, 'viewer_quota_enabled': True, 'viewer_dashboard_enabled': True, 'viewer_api_gateway_enabled': True}))
            docker('cp', str(temp / 'keeper.json'), names['keeper'] + ':/data/options.json')
            docker('restart', names['keeper'])
            keeper = endpoint(names['keeper'], 8080)
            viewer_gateway = endpoint(names['keeper'], 8082)
            eventually(lambda: request(keeper + '/healthz')[0] == 200)
            assert int(docker('exec', names['keeper'], 'python3', '-c', query)) >= count
            page_status, page = request(viewer_gateway + viewer_path + '/')
            assert page_status == 200 and b'window.__KEEPER_VIEWER_ONLY__ = true' in page and json.dumps(viewer_path).encode() in page
            assert request(viewer_gateway + '/v1/models', auth)[0] == 200
            assert request(viewer_gateway + '/v1/models')[0] == 401
            assert request(viewer_gateway + '/v1/chat/completions', auth, body)[0] == 200
            stream_status, stream_body = request(viewer_gateway + '/v1/chat/completions', auth, {**body, 'stream': True})
            assert stream_status == 200 and b'data:' in stream_body and b'[DONE]' in stream_body
            # Test an actual 101 upgrade and WebSocket data frame through the
            # packaged public listener, against a deterministic upgrade fixture.
            original_location = docker('exec', names['keeper'], 'cat', '/run/keeper-gateway/api.conf')
            fixture_location = original_location.replace('http://cpa:8080', 'http://mock:8080')
            (temp / 'api-location.conf').write_text(fixture_location)
            docker('cp', str(temp / 'api-location.conf'), names['keeper'] + ':/run/keeper-gateway/api.conf')
            docker('exec', names['keeper'], 'nginx', '-c', '/opt/ha/nginx.conf', '-s', 'reload')
            time.sleep(1)
            from urllib.parse import urlsplit
            gateway_address = urlsplit(viewer_gateway)
            with socket.create_connection((gateway_address.hostname, gateway_address.port), timeout=10) as sock:
                sock.sendall(b'GET /v1/responses HTTP/1.1\r\nHost: test\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\nSec-WebSocket-Version: 13\r\n\r\n')
                received = b''
                while b'smoke-ws' not in received:
                    chunk = sock.recv(4096)
                    assert chunk, 'WebSocket fixture closed without a data frame'
                    received += chunk
                assert b'101 Switching Protocols' in received and b'\x81\x08smoke-ws' in received
            (temp / 'api-location.conf').write_text(original_location)
            docker('cp', str(temp / 'api-location.conf'), names['keeper'] + ':/run/keeper-gateway/api.conf')
            docker('exec', names['keeper'], 'nginx', '-c', '/opt/ha/nginx.conf', '-s', 'reload')
            print('PASS: combined gateway HTTP, SSE and WebSocket upgrade/data forwarding', flush=True)
            # Assets load below the same prefix; all admin paths stay blocked.
            import re
            asset = re.search(rb'src="\./(assets/[^"]+)"', page).group(1).decode()
            assert request(viewer_gateway + viewer_path + '/' + asset)[0] == 200
            assert request(viewer_gateway + '/keeper/')[0] == 404
            for path in ('/api/v1/usage/overview', f'{viewer_path}/api/v1/usage/overview', f'{viewer_path}/api/v1/auth/sessions', f'{viewer_path}/api/v1/quota/cache', f'{viewer_path}/../api/v1/usage/overview', f'{viewer_path}/%2e%2e/api/v1/usage/overview', f'{viewer_path}/api/v1/key-quota/../quota/cache'):
                assert request(viewer_gateway + path, opener=opener)[0] == 404, path
            for path in (f'{viewer_path}/api/v1/auth/login', f'{viewer_path}/api/v1/quota/refresh', f'{viewer_path}/api/v1/quota/reset', f'{viewer_path}/api/v1/key-quota'):
                assert request(viewer_gateway + path, headers={'X-CPA-Usage-Keeper-Request': 'fetch'}, body={'password': password}, opener=opener)[0] == 404, path
            assert request(viewer_gateway + viewer_path + '/api/v1/key-quota')[0] == 401
            cookies = http.cookiejar.CookieJar()
            viewer_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))
            eventually(lambda: request(viewer_gateway + viewer_path + '/api/v1/auth/api-key-login', headers={'X-CPA-Usage-Keeper-Request': 'fetch'}, body={'apiKey': key}, opener=viewer_opener)[0] in (200, 204))
            assert all(cookie.path == f'{viewer_path}/' for cookie in cookies)
            session_status, session_body = request(viewer_gateway + viewer_path + '/api/v1/auth/session', opener=viewer_opener)
            session = json.loads(session_body)
            assert session_status == 200 and session['role'] == 'api_key_viewer' and session['api_key']['quota_enabled'] is True
            quota_status, quota_body = request(viewer_gateway + viewer_path + '/api/v1/key-quota?auth_indexes=private', opener=viewer_opener)
            assert quota_status == 200 and isinstance(json.loads(quota_body)['accounts'], list)
            for secret in (key, management, password, 'fake-upstream-test-key', 'auth_index', 'base_url'):
                assert secret.encode() not in quota_body
            assert request(keeper + '/api/v1/usage/overview', opener=viewer_opener)[0] == 401  # cookie confined to viewer_path
            print('PASS: disabled defaults, viewer login, quota serialization and public gateway method/path isolation', flush=True)
            assert request(viewer_gateway + viewer_path + '/api/v1/read-only/overview', opener=viewer_opener)[0] == 403
            assert request(viewer_gateway + viewer_path + '/api/v1/read-only/overview')[0] == 401
            read_only_cookies = http.cookiejar.CookieJar()
            read_only_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(read_only_cookies))
            assert request(viewer_gateway + viewer_path + '/api/v1/auth/read-only-login', headers={'X-CPA-Usage-Keeper-Request': 'fetch'}, body={'password': password}, opener=read_only_opener)[0] == 401
            assert request(viewer_gateway + viewer_path + '/api/v1/auth/read-only-login', headers={'X-CPA-Usage-Keeper-Request': 'fetch'}, body={'password': read_only_password}, opener=read_only_opener)[0] == 204
            assert all(cookie.path == f'{viewer_path}/' for cookie in read_only_cookies)
            readonly_status, readonly_body = request(viewer_gateway + viewer_path + '/api/v1/read-only/overview?range=7d&api_key_id=999', opener=read_only_opener)
            assert readonly_status == 200 and json.loads(readonly_body)['overview']['usage']['total_requests'] >= 2
            assert json.loads(request(viewer_gateway + viewer_path + '/api/v1/auth/session', opener=read_only_opener)[1])['role'] == 'read_only'
            assert request(viewer_gateway + viewer_path + '/api/v1/read-only/key-quota', opener=read_only_opener)[0] == 200
            for secret in (key, management, password, read_only_password, 'fake-upstream-test-key', 'auth_index', 'base_url'):
                assert secret.encode() not in readonly_body
            # The app enforces the role even without the restricted gateway.
            direct_read_only = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
            assert request(keeper + '/api/v1/auth/read-only-login', headers={'X-CPA-Usage-Keeper-Request': 'fetch'}, body={'password': read_only_password}, opener=direct_read_only)[0] == 204
            for method, path in (('GET', '/usage/overview'), ('GET', '/auth/sessions'), ('PATCH', '/auth-files/status'), ('DELETE', '/auth-files'), ('POST', '/quota/reset'), ('PUT', '/pricing'), ('POST', '/usage/identities/1/stats/reset')):
                assert request(keeper + '/api/v1' + path, headers={'X-CPA-Usage-Keeper-Request': 'fetch'}, body={} if method != 'GET' else None, method=method, opener=direct_read_only)[0] == 403
                assert request(viewer_gateway + viewer_path + '/api/v1' + path, headers={'X-CPA-Usage-Keeper-Request': 'fetch'}, body={} if method != 'GET' else None, method=method, opener=read_only_opener)[0] == 404
            for method in ('POST', 'PATCH', 'PUT', 'DELETE'):
                assert request(viewer_gateway + viewer_path + '/api/v1/read-only/overview', headers={'X-CPA-Usage-Keeper-Request': 'fetch'}, body={}, method=method, opener=read_only_opener)[0] == 404
            for report in ('key-overview', 'key-overview/comparisons', 'key-overview/realtime', 'key-activity', 'key-analysis', 'key-analysis/latency'):
                report_url = viewer_gateway + viewer_path + '/api/v1/read-only/' + report + '?range=today'
                report_status, report_body = request(report_url, opener=read_only_opener)
                assert report_status == 200, (report, report_status)
                report_data = json.loads(report_body)
                assert isinstance(report_data, dict)
                for secret in (key, management, password, read_only_password, 'fake-upstream-test-key', 'auth_index', 'base_url'):
                    assert secret not in report_body.decode()
                assert request(report_url)[0] == 401
                assert request(report_url, opener=viewer_opener)[0] == 403
                assert request(report_url, headers={'X-CPA-Usage-Keeper-Request': 'fetch'}, body={}, opener=read_only_opener)[0] == 404
            for page in ('read-only', 'read-only/realtime', 'read-only/analysis', 'read-only/quota'):
                assert request(viewer_gateway + viewer_path + '/' + page)[0] == 200
            print('PASS: native all-key dashboard APIs/pages, account data filtering and role/write isolation', flush=True)
            print('PASS: read-only all-key reports, secret filtering, client-key separation and server/gateway write denial', flush=True)
            # Exercise the same persisted client-key setting as the management UI.
            management_auth = {'Authorization': 'Bearer ' + management}
            keys_url = private + '/v8/management/config/access/api-keys'
            assert request(keys_url, management_auth, body=[key, rotated_key], method='PUT')[0] == 200
            rotated_auth = {'Authorization': 'Bearer ' + rotated_key}
            eventually(lambda: request(api + '/v1/models', rotated_auth)[0] == 200)
            assert request(keys_url, management_auth, body=[rotated_key], method='PUT')[0] == 200
            eventually(lambda: request(api + '/v1/models', auth)[0] == 401)
            eventually(lambda: request(viewer_gateway + viewer_path + '/api/v1/key-quota', opener=viewer_opener)[0] == 401, timeout=90)
            print('PASS: revoked client token loses viewer quota access', flush=True)
            # Clear stale HA keys after switching to management ownership.
            (temp / 'cpa.json').write_text(json.dumps({'api_key_source': 'management_ui', 'api_keys': [], 'management_key': management}))
            docker('cp', str(temp / 'cpa.json'), names['cpa'] + ':/data/options.json')
            docker('exec', names['cpa'], 'sh', '-c', 'echo test > /data/auth/persistence-marker')
            # Linux Docker cp can leave fixture ownership from the host user.
            # Startup must regenerate configs safely regardless of this owner.
            docker('exec', names['keeper'], 'chown', '1001:1001', '/run/keeper-gateway/api.conf')
            docker('restart', names['cpa'], names['keeper'])
            # Docker can reassign ephemeral host ports when restarting containers.
            api = endpoint(names['cpa'], 8080)
            keeper = endpoint(names['keeper'], 8080)
            eventually(lambda: request(api + '/v1/models', rotated_auth)[0] == 200 and request(keeper + '/healthz')[0] == 200)
            assert request(api + '/v1/models', auth)[0] == 401
            private = endpoint(names['cpa'], 8317)
            assert json.loads(request(private + '/v8/management/config/access/api-keys', management_auth)[1]) == [rotated_key]
            assert int(docker('exec', names['keeper'], 'python3', '-c', query)) >= count
            assert docker('exec', names['cpa'], 'cat', '/data/auth/persistence-marker') == 'test'
            viewer_gateway = endpoint(names['keeper'], 8082)
            assert request(viewer_gateway + viewer_path + '/api/v1/read-only/overview', opener=read_only_opener)[0] == 401
            print('PASS: Keeper restart revokes read-only sessions while preserving usage', flush=True)
            print('PASS: Keeper authentication, HTTP usage ingestion and persistence across restarts', flush=True)
            print('PASS: management API key additions and revocations survive restart with an empty HA key list', flush=True)
            for service in ('cpa', 'keeper'):
                docker('stop', '-t', '25', names[service])
                code = int(docker('inspect', '--format', '{{.State.ExitCode}}', names[service]))
                assert code in (0, 143), (service, code)
            print('PASS: graceful shutdown', flush=True)
        except Exception:
            # Redact disposable credentials from any service logs before displaying.
            for name in names.values():
                logs = docker('logs', '--tail', '40', name, check=False)
                for secret in (key, management, password, rotated_key, read_only_password):
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
