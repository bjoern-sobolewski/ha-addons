"""Packaged CPAMC policy, Keeper privacy, action handles and restart regression."""
from pathlib import Path
import http.cookiejar
import json
import os
import secrets
import tempfile
import time
import urllib.request
from smoke import docker, request, eventually

ROOT = Path(__file__).resolve().parents[1]


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
            docker('stop', '-t', '20', names['cpa'])
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
