"""Verify whitelist catalogs, validation and durable edits in an isolated CPA package."""
import json
import os
from pathlib import Path
import secrets
import tempfile

import yaml

from smoke import docker, eventually


def main():
    resource_prefix = 'model-whitelist-' + secrets.token_hex(4)
    volume = resource_prefix + '-data'
    container = resource_prefix + '-cpa'
    client_key, management_key = (secrets.token_urlsafe(32) for _ in range(2))
    admin_headers = {'Authorization': 'Bearer ' + management_key}
    filename = 'synthetic-whitelist.json'
    with tempfile.TemporaryDirectory() as directory:
        temporary = Path(directory)
        configuration = temporary / 'config'
        configuration.mkdir()
        (configuration / 'providers.yaml').write_text(yaml.safe_dump({
            'oauth': {'model-alias': {'codex': [
                {'name': 'gpt-6-astra', 'alias': 'gpt-6-astra-fast', 'fork': True},
            ]}},
        }))
        (temporary / 'options.json').write_text(json.dumps({
            'api_keys': [client_key], 'management_key': management_key,
        }))
        try:
            docker('volume', 'create', volume)
            # No upstream connectivity: fixture credentials must stay local.
            docker('create', '--name', container, '--network', 'none',
                   '-v', volume + ':/data', '-v', str(configuration) + ':/config:ro',
                   os.environ.get('CPA_TEST_IMAGE', 'ha-cpa-whitelist:local'))
            docker('cp', str(temporary / 'options.json'), container + ':/data/options.json')
            docker('start', container)

            # Use the container loopback because its network is intentionally disabled.
            def management(path, body=None, method='GET'):
                script = (
                    'import json,urllib.request,urllib.error;'
                    f'body={repr(json.dumps(body) if body is not None else None)};'
                    f'req=urllib.request.Request("http://127.0.0.1:8317/v8/management/{path}",'
                    f'headers={admin_headers!r},data=None if body is None else body.encode(),method={method!r});'
                    '\ntry:\n response=urllib.request.urlopen(req,timeout=8)'
                    '\nexcept urllib.error.HTTPError as error:\n response=error'
                    '\nprint(json.dumps([response.status,json.loads(response.read() or b"null")]))'
                )
                return json.loads(docker('exec', container, 'python3', '-c', script))

            def models():
                status, body = management('credentials/models?name=' + filename)
                assert status == 200
                return {model['id'] for model in body['models']}

            eventually(lambda: management('credentials')[0] == 200)
            credential = {
                'type': 'codex', 'email': 'synthetic@example.test',
                'access_token': 'synthetic-unused-token', 'expired': '2099-01-01T00:00:00Z',
                'allowed_models': ['gpt-6-astra'], 'note': 'preserve this note',
            }
            assert management('credentials?name=' + filename, credential, 'POST')[0] == 200
            expected_models = {'gpt-6-astra', 'gpt-6-astra-fast'}
            eventually(lambda: models() == expected_models)
            print('PASS: account advertises only whitelisted Astra and its Fast alias', flush=True)
            def fields(values):
                return management('credentials/fields', {'name': filename, **values}, 'PATCH')
            for invalid in ('gpt-6-astra', ['*'], ['gpt-6-astra', 7]):
                assert fields({'allowed_models': invalid})[0] == 400
                assert models() == expected_models
            assert fields({'excluded_models': ['gpt-6-astra']})[0] == 200
            eventually(lambda: models() == set())
            assert fields({'excluded_models': []})[0] == 200
            eventually(lambda: models() == expected_models)
            print('PASS: invalid edits are rejected and exclusions still take precedence', flush=True)
            docker('restart', container)
            eventually(lambda: models() == expected_models)
            saved = json.loads(docker('exec', container, 'cat', '/data/auth/' + filename))
            assert saved['allowed_models'] == ['gpt-6-astra']
            assert saved['note'] == credential['note']
            assert saved['access_token'] == credential['access_token']
            assert fields({'allowed_models': []})[0] == 200
            eventually(lambda: 'gpt-6-sol' in models())
            docker('restart', container)
            eventually(lambda: 'gpt-6-sol' in models())
            print('PASS: whitelist persists across restart; clearing restores normal routing', flush=True)
        finally:
            docker('rm', '-f', '-v', container, check=False)
            docker('volume', 'rm', volume, check=False)


if __name__ == '__main__':
    main()
