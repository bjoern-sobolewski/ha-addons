"""Check oversized Codex compaction through the packaged gateway, without real providers."""
import json
import sys


def mock():
    from aiohttp import web

    counts = {'websocket': 0, 'http': 0}

    async def responses(request):
        assert request.headers.get('Authorization') == 'Bearer fake-oversized-account'
        ws = web.WebSocketResponse(compress=False, max_msg_size=16 * 1024 * 1024)
        if ws.can_prepare(request).ok:
            await ws.prepare(request)
            async for message in ws:
                if message.type == web.WSMsgType.TEXT:
                    counts['websocket'] += 1
                    await ws.send_json({'type': 'response.completed', 'response': {
                        'id': 'warm', 'status': 'completed', 'output': []}})
            return ws
        body = await request.json()
        assert 'previous_response_id' not in body
        assert body['service_tier'] == 'priority'
        counts['http'] += 1
        n = counts['http']
        items = body['input']
        if n == 1:
            assert items[0]['content'] == 'x' * (26 * 1024 * 1024)
            assert items[1]['type'] == 'compaction_trigger'
            output = [{'type': 'compaction', 'id': 'cmp', 'encrypted_content': 'opaque'}]
        elif n == 2:
            assert len(items) == 2 and items[0]['encrypted_content'] == 'opaque'
            output = [{'type': 'function_call', 'id': 'fc', 'call_id': 'call',
                       'name': 'check', 'arguments': '{}', 'status': 'completed'}]
        else:
            assert n == 3, 'unexpected duplicate generation'
            assert len(items) == 4 and items[2]['call_id'] == 'call'
            assert items[3]['type'] == 'function_call_output' and items[3]['output'] == 'done'
            output = []
        event = {'type': 'response.completed', 'response': {
            'id': f'resp-{n}', 'status': 'completed', 'output': output,
            'usage': {'input_tokens': 3, 'output_tokens': 2, 'total_tokens': 5}}}
        return web.Response(text='data: ' + json.dumps(event) + '\n\n', content_type='text/event-stream')

    async def stats(request):
        return web.json_response(counts)

    app = web.Application(client_max_size=64 * 1024 * 1024)
    app.router.add_route('*', '/responses', responses)
    app.router.add_get('/stats', stats)
    web.run_app(app, port=9000, print=None)


def main():
    import os
    from pathlib import Path
    import secrets
    import tempfile
    import yaml
    from websockets.sync.client import connect
    from smoke import docker, eventually, request

    root = Path(__file__).resolve().parents[1]
    image = os.environ.get('CPA_TEST_IMAGE', 'ha-cpa-test:local')
    prefix = 'oversized-flow-' + secrets.token_hex(4)
    network, volume = prefix + '-net', prefix + '-data'
    cpa, upstream = prefix + '-cpa', prefix + '-mock'
    key, management = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    with tempfile.TemporaryDirectory() as directory:
        temp = Path(directory)
        config = temp / 'config'
        config.mkdir()
        (config / 'providers.yaml').write_text(yaml.safe_dump({'api-keys': {'codex': [{
            'name': 'oversized-fixture', 'base-url': 'http://mock:9000',
            'keys': [{'api-key': 'fake-oversized-account', 'websockets': True}],
            'models': [{'name': 'gpt-5.5', 'alias': 'oversized-test'}]}]}}))
        (temp / 'options.json').write_text(json.dumps({'api_keys': [key], 'management_key': management}))
        try:
            docker('network', 'create', network)
            docker('volume', 'create', volume)
            docker('run', '-d', '--name', upstream, '--network', network, '--network-alias', 'mock',
                   '-v', f'{root / "tests"}:/test:ro', 'python:3.13-alpine', 'sh', '-c',
                   'pip install -q aiohttp==3.13.3 && python /test/oversized_flow.py --mock')

            def stats():
                return json.loads(docker('exec', upstream, 'python', '-c',
                    'import urllib.request;print(urllib.request.urlopen("http://localhost:9000/stats").read().decode())'))

            eventually(lambda: stats() == {'websocket': 0, 'http': 0}, timeout=90)
            docker('create', '--init', '--name', cpa, '--network', network, '-v', volume + ':/data',
                   '-v', f'{config}:/config:ro', '-p', '127.0.0.1::8080', image)
            docker('cp', str(temp / 'options.json'), cpa + ':/data/options.json')
            docker('start', cpa)
            api = 'http://' + docker('port', cpa, '8080/tcp').splitlines()[0]
            headers = {'Authorization': 'Bearer ' + key}
            eventually(lambda: request(api + '/v1/models', headers)[0] == 200)

            def turn(ws, **fields):
                ws.send(json.dumps({'type': 'response.create', 'service_tier': 'priority', **fields}))
                while True:
                    event = json.loads(ws.recv(timeout=30))
                    assert event['type'] not in ('error', 'response.failed'), 'upstream request failed'
                    if event['type'] == 'response.completed':
                        return event

            url = api.replace('http://', 'ws://') + '/v1/responses'
            with connect(url, additional_headers=headers, max_size=None) as ws:
                turn(ws, model='oversized-test', generate=False, input=[])
                turn(ws, input=[{'type': 'message', 'role': 'user', 'content': 'x' * (26 * 1024 * 1024)},
                                {'type': 'compaction_trigger'}])
                turn(ws, input=[{'type': 'compaction', 'id': 'cmp', 'encrypted_content': 'opaque'},
                                {'type': 'message', 'role': 'user', 'content': 'continue'}])
                result = turn(ws, previous_response_id='resp-2', input=[
                    {'type': 'function_call_output', 'call_id': 'call', 'output': 'done'}])
                assert result['response']['usage']['total_tokens'] == 5
                assert stats() == {'websocket': 1, 'http': 3}
            with connect(url, additional_headers=headers) as ws:
                turn(ws, model='oversized-test', input=[])
            assert stats() == {'websocket': 2, 'http': 3}
            print('Oversized gateway flow passed: 26 MiB compaction, compacted replay, tool continuation, usage, fresh WebSocket.')
        except Exception:
            for name in (cpa, upstream):
                log = docker('logs', '--tail', '25', name, check=False)[-5000:]
                for secret in (key, management, 'fake-oversized-account'):
                    log = log.replace(secret, '[redacted]')
                print(name + ':\n' + log, file=sys.stderr)
            raise
        finally:
            for name in (cpa, upstream):
                docker('rm', '-f', name, check=False)
            docker('volume', 'rm', volume, check=False)
            docker('network', 'rm', network, check=False)


if __name__ == '__main__':
    mock() if '--mock' in sys.argv else main()
