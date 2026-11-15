"""Packaged CPAMC policy, Keeper privacy, action handles and restart regression."""
from pathlib import Path
import http.cookiejar
import json
import os
import queue
import socket
import threading
import secrets
import tempfile
import time
import urllib.request
from smoke import docker, request, eventually

ROOT = Path(__file__).resolve().parents[1]


class RequestEventStream:
    """Read native admin frames with bounded waits, including clean closure."""

    def __init__(self, url, opener):
        self.frames = queue.Queue()
        self.response = opener.open(url, timeout=25)
        assert self.response.status == 200
        assert self.response.headers['Content-Type'].startswith('text/event-stream')
        self.thread = threading.Thread(target=self._read, daemon=True)
        self.thread.start()

    def _read(self):
        kind = ''
        try:
            for line in self.response:
                if line.startswith(b'event:'):
                    kind = line[6:].decode().strip()
                elif line.startswith(b'data:'):
                    self.frames.put((kind, json.loads(line[5:])))
        except (OSError, ValueError) as error:
            self.frames.put(('error', str(error)))
        finally:
            self.frames.put(('closed', None))

    def wait(self, kind, timeout=35):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            event, payload = self.frames.get(timeout=max(.01, deadline-time.monotonic()))
            if event == kind:
                return payload
            assert event not in ('error', 'closed'), (event, payload)
        raise AssertionError('Missing native request-event frame: ' + kind)

    def close(self):
        try:
            self.response.fp.raw._sock.shutdown(socket.SHUT_RDWR)
        except (OSError, AttributeError):
            pass
        self.response.close()
        self.thread.join(timeout=2)


def main():
    prefix = 'privacy-' + secrets.token_hex(4)
    network = prefix + '-net'
    names = {kind: prefix + '-' + kind for kind in ('cpa', 'keeper')}
    volumes = [prefix + '-cpa', prefix + '-keeper']
    # Disposable local fixture values; never used with production services.
    management = 'synthetic-privacy-preview-management'
    password = 'synthetic-privacy-preview-password'
    email, masked = 'example.person@example.test', 'exampl**@example.test'
    filename = 'codex-' + email + '.json'
    headers = {'X-CPA-Usage-Keeper-Request': 'fetch'}
    admin = {'Authorization': 'Bearer ' + management}

    def endpoint(kind, port):
        return 'http://' + docker('port', names[kind], f'{port}/tcp').splitlines()[0]

    with tempfile.TemporaryDirectory() as directory:
        tmp = Path(directory)
        authdir = tmp / 'auth'
        authdir.mkdir()
        (authdir / filename).write_text(json.dumps({
            'type': 'codex', 'email': email, 'access_token': 'synthetic-disabled-token',
            'expired': '2099-01-01T00:00:00Z', 'disabled': True, 'hide_email_in_keeper': False,
        }))
        (tmp / 'cpa.json').write_text(json.dumps({'api_keys': ['synthetic-privacy-client'], 'management_key': management}))
        (tmp / 'keeper.json').write_text(json.dumps({
            'cpa_base_url': 'http://cpa:8317', 'management_key': management,
            'login_password': password, 'read_only_password': 'synthetic-read-only-password',
            'viewer_dashboard_enabled': True, 'viewer_base_path': '/privacy-viewer',
        }))
        try:
            docker('network', 'create', network)
            for volume in volumes:
                docker('volume', 'create', volume)
            for kind, image in [('cpa', os.environ.get('CPA_TEST_IMAGE', 'ha-cpa-routing:local')),
                                ('keeper', os.environ.get('KEEPER_TEST_IMAGE', 'ha-keeper-routing:local'))]:
                docker('create', '--name', names[kind], '--network', network, '--network-alias', kind,
                       '-v', volumes[0 if kind == 'cpa' else 1] + ':/data',
                       '-p', '127.0.0.1::8080', '-p', '127.0.0.1::' + ('8317' if kind == 'cpa' else '8082'), image)
                docker('cp', str(tmp / (kind + '.json')), names[kind] + ':/data/options.json')
            docker('cp', str(authdir), names['cpa'] + ':/data/auth')
            docker('start', names['cpa'])
            private, api = endpoint('cpa', 8317), endpoint('cpa', 8080)
            files = lambda: json.loads(request(private + '/v8/management/credentials', admin)[1])['files']
            eventually(lambda: any(f.get('email') == email for f in files()))
            assert request(api + '/v8/management/keeper-email-privacy', admin)[0] == 404
            assert request(private + '/v8/management/keeper-email-privacy')[0] == 401
            docker('start', names['keeper'])
            keeper = endpoint('keeper', 8080)
            session = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
            eventually(lambda: request(keeper + '/api/v1/auth/login', headers, {'password': password}, session)[0] == 204)
            identities = lambda: json.loads(request(keeper + '/api/v1/usage/identities', opener=session)[1])['identities']
            eventually(lambda: any(i['name'] == email for i in identities()))
            identity_id = next(i['id'] for i in identities() if i['name'] == email)

            def set_hidden(value):
                status, _ = request(private + '/v8/management/credentials/fields', admin,
                                    {'name': filename, 'hide_email_in_keeper': value}, method='PATCH')
                assert status == 200

            for invalid in ['true', None, 1, {}]:
                status, _ = request(private + '/v8/management/credentials/fields', admin,
                                    {'name': filename, 'hide_email_in_keeper': invalid}, method='PATCH')
                assert status == 400
            set_hidden(True)

            def insert_event():
                # Only the disposable fixture database is mutated. Native polling
                # discovers the committed ID on its existing heartbeat cadence.
                docker('exec', names['keeper'], 'python3', '-c', r'''
import json, sqlite3, sys
from datetime import datetime, timezone
email, identity_id, event_key = json.loads(sys.argv[1])
c = sqlite3.connect('/data/app.db', timeout=10)
auth_index = c.execute('SELECT identity FROM usage_identities WHERE id=?', (identity_id,)).fetchone()[0]
stamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f000Z')
c.execute('INSERT INTO usage_events (event_key,api_group_key,provider,auth_type,auth_index,model,source,timestamp,input_tokens,output_tokens,total_tokens,failed,generate,stream,latency_ms,cost_usd,cost_available) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
          (event_key,'synthetic-privacy-client','codex','oauth',auth_index,'privacy-test-model',email,stamp,1,1,2,0,1,1,100,0.125,1))
c.commit()
''', json.dumps([email, identity_id, secrets.token_hex(16)]))

            stream_url = keeper + '/api/v1/usage/events/live?range=24h&model=privacy-test-model'
            assert request(stream_url)[0] == 401
            for role, login in [('read-only', {'password': 'synthetic-read-only-password'}),
                                ('api-key', {'apiKey': 'synthetic-privacy-client'})]:
                viewer = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
                assert request(keeper + '/api/v1/auth/' + role + '-login', headers, login, viewer)[0] == 204
                assert request(stream_url, opener=viewer)[0] == 403
            gateway = endpoint('keeper', 8082) + '/privacy-viewer/api/v1'
            assert request(gateway + '/usage/events/live?range=24h', opener=session)[0] == 404
            assert request(gateway + '/read-only/events/live?range=24h', opener=session)[0] == 404
            insert_event()
            stream = RequestEventStream(stream_url, session)
            def assert_masked_frame(kind):
                payload = json.dumps(stream.wait(kind))
                assert email not in payload and masked in payload, (kind, payload)
            try:
                assert_masked_frame('snapshot')
                insert_event()
                assert_masked_frame('append')
                set_hidden(False)
                insert_event()
                assert email in json.dumps(stream.wait('append'))
                set_hidden(True)
                insert_event()
                assert_masked_frame('append')
            finally:
                stream.close()
            print('PASS: native admin stream masks snapshots/appends, follows visibility changes, and denies both viewer roles and public gateways', flush=True)
            row = next(i for i in identities() if i['id'] == identity_id)
            assert row['name'] == masked and email not in json.dumps(row)
            assert row['file_name'].startswith('private-credential-')
            assert request(keeper + '/api/v1/credentials/status', headers,
                           {'names': [row['file_name']], 'disabled': True}, session, method='PATCH')[0] == 200
            for route in ['/usage/identities/' + identity_id, '/usage/identities/page', '/routing/activity',
                          '/usage/events?range=today', '/usage/events/export?range=today&format=csv',
                          '/usage/identities/' + identity_id + '/errors']:
                status, body = request(keeper + '/api/v1' + route, opener=session)
                assert status == 200, (route, status)
                assert email not in body.decode(), route
            for suffix, method in [('', 'GET'), ('/download-token', 'POST'), ('/download-file?token=old', 'GET')]:
                assert request(keeper + '/api/v1/usage/events/1/request-log' + suffix, headers,
                               {} if method == 'POST' else None, session, method=method)[0] == 403
            print('PASS: real CPAMC field saves, strict validation, masked identities/details/exports/routing, private filename actions and raw-log denial', flush=True)

            if os.environ.get('PRIVACY_PREVIEW'):
                target = Path(os.environ['PRIVACY_PREVIEW'])
                target.write_text(json.dumps({'keeper': keeper, 'cpamc': private + '/management.html#/auth-files'}))
                print('Privacy preview ready', flush=True)
                while not target.with_suffix('.stop').exists():
                    time.sleep(1)

            set_hidden(False)
            assert next(i for i in identities() if i['id'] == identity_id)['name'] == email
            # Hide and immediately delete before Keeper can observe the new flag.
            set_hidden(True)
            assert request(private + '/v8/management/credentials', admin, {'names': [filename]}, method='DELETE')[0] == 200
            detail = lambda: request(keeper + '/api/v1/usage/identities/' + identity_id, opener=session)
            assert detail()[0] == 200 and email not in detail()[1].decode()
            for kind in ('cpa', 'keeper'):
                docker('restart', names[kind])
            private, keeper = endpoint('cpa', 8317), endpoint('keeper', 8080)
            eventually(lambda: detail()[0] == 200)
            assert email not in detail()[1].decode() and masked in detail()[1].decode()
            stream = RequestEventStream(keeper + '/api/v1/usage/events/live?range=24h&model=privacy-test-model', session)
            try:
                assert_masked_frame('snapshot')
                docker('stop', '-t', '20', names['cpa'])
                # Policy verification on the next heartbeat must close the
                # established stream before delivering any unverified payload.
                assert stream.wait('closed', timeout=25) is None
            finally:
                stream.close()
            assert detail()[0] == 503 and email not in detail()[1].decode()
            assert request(keeper + '/healthz')[0] == 200
            print('PASS: disabling is explicit, immediate deletion cannot expose history, restarts retain masking, and CPA outage fails closed', flush=True)
        finally:
            for name in reversed(list(names.values())):
                docker('rm', '-f', name, check=False)
            for volume in volumes:
                docker('volume', 'rm', volume, check=False)
            docker('network', 'rm', network, check=False)


if __name__ == '__main__':
    main()
