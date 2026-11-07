"""Real installed Codex app-server against two synthetic CPA accounts.

Set CPA_TEST_IMAGE and optionally CODEX_TEST_BINARY. No real provider traffic,
credentials, production policy changes, or Codex configuration writes.
"""
import hashlib
import json
import os
from pathlib import Path
import queue
import secrets
import subprocess
import sys
import tempfile
import threading
import time
import tomllib
import yaml
from smoke import docker, request, eventually

ROOT = Path(__file__).resolve().parents[1]


class Rpc:
    def __init__(self, exe, disabled):
        args = [str(exe), '--no-daemon']
        for key in disabled:
            args += ['-c', f'mcp_servers.{key}.enabled=false']
        args += ['-c', 'features.apps=false', '-c', 'features.hooks=false', '-c', 'model_provider="rebalance-test"', '-c', 'model_providers.rebalance-test={name="Synthetic rebalance test",base_url="http://127.0.0.1:1/v1",wire_api="responses",requires_openai_auth=false,supports_websockets=true}', 'app-server']
        self.proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, text=True, encoding='utf-8')
        self.queue = queue.Queue()
        self.seq = 0
        self.saved = []
        def reader():
            for line in self.proc.stdout:
                try:
                    self.queue.put(json.loads(line))
                except ValueError:
                    pass
        threading.Thread(target=reader, daemon=True).start()
        self.call('initialize', {'clientInfo': {'name': 'session_rebalance_test', 'version': '1.0'},
                                 'capabilities': {'experimentalApi': True}})
        self.send({'method': 'initialized'})

    def send(self, msg):
        self.proc.stdin.write(json.dumps(msg) + '\n')
        self.proc.stdin.flush()

    def call(self, method, params):
        self.seq += 1
        rid = self.seq
        self.send({'id': rid, 'method': method, 'params': params})
        while True:
            msg = self.queue.get(timeout=45)
            if msg.get('id') == rid:
                assert 'error' not in msg, 'Codex RPC rejected ' + method + ': ' + str(msg.get('error', {}).get('message', ''))
                return msg['result']
            self.saved.append(msg)

    def wait(self, predicate, timeout=90):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            msg = self.saved.pop(0) if self.saved else self.queue.get(timeout=max(.1, deadline-time.monotonic()))
            if predicate(msg):
                return msg
            if msg.get('method') == 'error':
                raise AssertionError('Codex emitted an error notification')
        raise TimeoutError('Codex event')

    def close(self):
        self.proc.terminate()
        self.proc.wait(timeout=10)


def main():
    exe = Path(os.environ['CODEX_TEST_BINARY']) if 'CODEX_TEST_BINARY' in os.environ else max(
        (Path.home() / 'AppData/Local/OpenAI/Codex/bin').glob('*/codex.exe'), key=lambda p: p.stat().st_mtime)
    config_path = Path.home() / '.codex/config.toml'
    original = config_path.read_bytes()
    config = tomllib.loads(original.decode('utf-8'))
    prefix = 'rebalance-codex-' + secrets.token_hex(4)
    network = prefix + '-net'
    names = {k: prefix + '-' + k for k in ('mock', 'cpa')}
    volume = prefix + '-data'
    key, management = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    rpc = None
    with tempfile.TemporaryDirectory(prefix='rebalance-codex-') as directory:
        tmp = Path(directory)
        providers = tmp / 'config'
        providers.mkdir()
        provider_config = {'api-keys': {'codex': [
            {'name': 'account-' + a, 'priority': 10 if a == 'a' else 0,
             'keys': [{'api-key': 'fake-account-' + a, 'websockets': True}],
             'base-url': 'http://mock:9000', 'models': [{'name': 'gpt-6.1-sol'}]}
            for a in ('a', 'b')]}}
        if '--duplex' in sys.argv:
            provider_config['oauth'] = {'providers': {'codex': {'response-steering': True}}}
        (providers / 'providers.yaml').write_text(yaml.safe_dump(provider_config))
        (tmp / 'options.json').write_text(json.dumps({'api_keys': [key], 'management_key': management}))
        try:
            docker('network', 'create', network)
            docker('volume', 'create', volume)
            docker('run', '-d', '--name', names['mock'], '--network', network, '--network-alias', 'mock',
                   '-v', str(ROOT / 'tests') + ':/test:ro', '-p', '127.0.0.1::9000', 'python:3.13-alpine',
                   'sh', '-c', 'pip install -q aiohttp==3.13.3 && python /test/session_rebalance_mock.py')
            mock = 'http://' + docker('port', names['mock'], '9000/tcp').splitlines()[0]
            eventually(lambda: request(mock + '/stats')[0] == 200, timeout=90)
            docker('create', '--name', names['cpa'], '--network', network, '-v', volume + ':/data',
                   '-v', str(providers) + ':/config:ro', '-p', '127.0.0.1::8080', '-p', '127.0.0.1::8317',
                   os.environ.get('CPA_TEST_IMAGE', 'ha-cpa-rebalance:local'))
            docker('cp', str(tmp / 'options.json'), names['cpa'] + ':/data/options.json')
            docker('start', names['cpa'])
            api = 'http://' + docker('port', names['cpa'], '8080/tcp').splitlines()[0]
            private = 'http://' + docker('port', names['cpa'], '8317/tcp').splitlines()[0]
            auth = {'Authorization': 'Bearer ' + key}
            admin = {'Authorization': 'Bearer ' + management}
            eventually(lambda: request(api + '/v1/models', auth)[0] == 200)
            rpc = Rpc(exe, config.get('mcp_servers', {}))
            result = rpc.call('thread/start', {
                'model': 'gpt-6.1-sol', 'modelProvider': 'rebalance-test', 'cwd': directory,
                'approvalPolicy': 'never', 'sandbox': 'read-only', 'ephemeral': True,
                'baseInstructions': 'Synthetic session recovery test. Use the provided dynamic tool.',
                'config': {'model_providers.rebalance-test': {
                    'name': 'Synthetic rebalance test', 'base_url': api + '/v1', 'wire_api': 'responses',
                    'experimental_bearer_token': key, 'requires_openai_auth': False,
                    'supports_websockets': True, 'stream_max_retries': 3},
                    'model_reasoning_effort': 'low', 'features.apps': False, 'features.hooks': False},
                'dynamicTools': [{'type': 'function', 'name': 'rebalance_probe',
                                 'description': 'Return synthetic context',
                                 'inputSchema': {'type': 'object', 'properties': {}}}]})
            tid = result['thread']['id']
            turn = rpc.call('turn/start', {'threadId': tid, 'input': [
                {'type': 'text', 'text': 'Remember REBALANCE_CONTEXT_92817. Call rebalance_probe.', 'text_elements': []}]})
            tool = rpc.wait(lambda msg: msg.get('method') == 'item/tool/call')
            print('Codex reached pending dynamic tool', flush=True)
            assert tool['params']['tool'] == 'rebalance_probe'
            observed = json.loads(request(private + '/v8/management/quota/policies', admin)[1])['items']
            account = next(item for item in observed if any(w['remaining_percent'] == 10 for w in item['windows']))
            window = next(w for w in account['windows'] if w['remaining_percent'] == 10)
            assert request(private + '/v8/management/quota/policies', admin, {
                'auth_index': account['auth_index'], 'provider': 'codex',
                'thresholds': {window['id']: 10}, 'expected_thresholds': {}, 'rebalance_settings': {'rebalance_sessions': True, 'reconnect_websockets': True}, 'expected_rebalance_settings': account['rebalance_settings']}, method='PUT')[0] == 200
            progress = lambda: json.loads(request(private + '/v8/management/sessions/rebalances', admin)[1])['items']
            eventually(lambda: any(j['waiting'] == 1 for j in progress()))
            # Codex is blocked in a real tool RPC: rebalance must keep its socket.
            time.sleep(.3)
            assert any(j['waiting'] == 1 and j['sessions_rebalanced'] == 0 for j in progress())
            rpc.send({'id': tool['id'], 'result': {'contentItems': [
                {'type': 'inputText', 'text': 'TOOL_CONTEXT_OK'}], 'success': True}})
            done = rpc.wait(lambda msg: msg.get('method') == 'turn/completed')
            assert done['params']['turn']['status'] == 'completed'
            print('Codex tool continuation completed', flush=True)
            eventually(lambda: any(j['waiting'] == 0 and j['sessions_rebalanced'] == 1 for j in progress()))
            rpc.call('turn/start', {'threadId': tid, 'input': [
                {'type': 'text', 'text': 'Continue and retain the earlier marker and tool result.', 'text_elements': []}]})
            done = rpc.wait(lambda msg: msg.get('method') == 'turn/completed')
            assert done['params']['turn']['status'] == 'completed'
            events = json.loads(request(mock + '/stats')[1])['events']
            if '--duplex' in sys.argv:
                assert 'request forwarded session=' in docker('logs', names['cpa']), 'native duplex path was not exercised'
            assert any(e['account'] == 'a' and e['tool'] for e in events), 'pending tool did not finish on old account'
            assert any(e['account'] == 'b' and e['full'] and e['marker'] and e['tool'] for e in events), 'Codex did not recover full context on the new account'
            print('PASS: installed Codex app-server finished pending tool on old account, drained safely, migrated to eligible account and replayed conversation plus tool context', flush=True)
            print(json.dumps({'codex_version': subprocess.check_output([str(exe), '--version'], text=True).strip(),
                              'synthetic_upstream_frames': len(events), 'accounts_observed': sorted({e['account'] for e in events})}), flush=True)
        except Exception:
            try:
                print(json.dumps({'progress': progress(), 'mock': json.loads(request(mock + '/stats')[1])}), flush=True)
            except Exception:
                pass
            raise
        finally:
            if rpc:
                rpc.close()
            for name in names.values():
                docker('rm', '-f', name, check=False)
            docker('volume', 'rm', volume, check=False)
            docker('network', 'rm', network, check=False)
            assert hashlib.sha256(config_path.read_bytes()).digest() == hashlib.sha256(original).digest(), 'Codex configuration changed'


if __name__ == '__main__':
    main()
