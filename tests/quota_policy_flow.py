"""Synthetic quota-policy verification; uses observed mock traffic only."""
import http.cookiejar
import json
import time
import urllib.request

from websockets.sync.client import connect
from live_sse import LiveStream
from smoke import eventually, request


def verify_quota_policy(api, private, keeper, gateway, auth, admin, password, viewer, ro, counter, restart_cpa):
    headers = {'X-CPA-Usage-Keeper-Request': 'fetch'}
    admin_session = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    assert request(keeper + '/api/v1/auth/login', headers, {'password': password}, admin_session)[0] == 204
    route = '/api/v1/quota/policies'
    read = lambda: json.loads(request(keeper + route, opener=admin_session)[1])['items']
    items = read()
    assert len(items) == 2 and all(not item['thresholds'] and not item['excluded'] for item in items)
    assert request(keeper + route)[0] == 401
    for session in (viewer, ro):
        assert request(gateway + '/test-quota' + route, opener=session)[0] == 404
    assert request(api + '/v8/management/quota/policies', admin)[0] == 404
    # Bind a WebSocket while the account is still eligible.
    with connect(api.replace('http:', 'ws:') + '/v1/responses', additional_headers=auth, open_timeout=20) as ws:
        ws.send(json.dumps({'type': 'response.create', 'model': 'a/quota-test', 'input': []}))
        while json.loads(ws.recv(timeout=20)).get('type') != 'response.completed':
            pass
        ws.send(json.dumps({'type': 'response.create', 'model': 'a/quota-test', 'instructions': '__interrupt_fixture__', 'input': []}))
        active = json.loads(ws.recv(timeout=20))
        assert active['type'] == 'response.created'
        items = read()
        a = next(item for item in items if any(abs((w['remaining_percent'] or 0) - 77) < .01 for w in item['windows']))
        window = next(w for w in a['windows'] if abs((w['remaining_percent'] or 0) - 77) < .01)
        payload = {'auth_index': a['auth_index'], 'provider': a['provider'], 'thresholds': {window['id']: 77}, 'expected_thresholds': {}}
        stream = LiveStream(keeper + '/api/v1/live', opener=admin_session)
        try:
            before = counter()
            assert request(keeper + route, headers, payload, admin_session, method='PUT')[0] == 200
            stream.wait('quota')
            protected = next(item for item in read() if item['auth_index'] == a['auth_index'])
            assert protected['excluded'] and protected['reason'] == 'minimum_reached'
            ws.send(json.dumps({'type': 'response.interrupt', 'response_id': 'resp-interrupt', 'mode': 'discard_partial_items', 'extension': 'preserve-me'}))
            finished = json.loads(ws.recv(timeout=20))
            assert finished['type'] == 'response.incomplete', finished
            # A duplicate editor cannot silently overwrite the newly saved setting.
            assert request(keeper + route, headers, payload, admin_session, method='PUT')[0] == 409
            assert request(api + '/v1/responses', auth, {'model': 'a/quota-test', 'input': []})[0] >= 400
            ws.send(json.dumps({'type': 'response.create', 'model': 'a/quota-test', 'input': []}))
            denied = json.loads(ws.recv(timeout=20))
            assert denied['type'] == 'error' and denied['error']['code'] == 'quota_policy_excluded', denied
            assert counter() == before, 'protected HTTP/duplex requests reached provider'
            # The other account remains available, with its independently observed windows.
            other = next(item for item in read() if item['auth_index'] != a['auth_index'])
            assert not other['excluded'] and not other['thresholds']
            # Earlier SSE assertions deliberately failed a request on b. Allow its
            # existing transient-error cooldown to expire independently of policy.
            eventually(lambda: request(api + '/v1/responses', auth, {'model': 'b/quota-test', 'input': []})[0] == 200, timeout=90)
            # Existing settings persist through CPA restart; its empty observation cache fails closed.
            # Docker may reassign anonymous host ports on restart.
            api, private = restart_cpa()
            eventually(lambda: request(api + '/v1/models', auth)[0] == 200)
            recovered = json.loads(request(private + '/v8/management/quota/policies', admin)[1])['items']
            protected = next(item for item in recovered if item['auth_index'] == a['auth_index'])
            assert protected['thresholds'] == payload['thresholds'] and protected['excluded'] and protected['reason'] == 'quota_unknown'
            before = counter()
            assert request(api + '/v1/responses', auth, {'model': 'a/quota-test', 'input': []})[0] >= 400
            assert counter() == before
            clear = {**payload, 'thresholds': {}, 'expected_thresholds': payload['thresholds']}
            assert request(keeper + route, headers, clear, admin_session, method='PUT')[0] == 200
            assert request(api + '/v1/responses', auth, {'model': 'a/quota-test', 'input': []})[0] == 200
            assert next(item for item in read() if item['auth_index'] == a['auth_index'])['thresholds'] == {}
            print('PASS: Keeper per-window policy, exact boundary, SSE, conflict protection, HTTP/pinned-WebSocket exclusion, independent accounts, restart protection and clearing without provider probes', flush=True)
        finally:
            stream.close()
            request(keeper + '/api/v1/auth/logout', headers, {}, admin_session)
