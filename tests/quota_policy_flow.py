"""Synthetic quota-policy verification; uses observed mock traffic only."""
import http.cookiejar
import json
import time
import urllib.request

from websockets.sync.client import connect
from websockets.exceptions import ConnectionClosed
from live_sse import LiveStream
from smoke import eventually, request


def expect_rebalanced_close(ws):
    try:
        ws.recv(timeout=20)
        raise AssertionError('rebalance did not retire the socket')
    except ConnectionClosed as closed:
        assert closed.rcvd and closed.rcvd.code == 1012, 'missing safe reconnect close'


def verify_priority_rebalance(api, private, keeper, gateway, auth, admin, session, viewer, ro, account):
    headers = {'X-CPA-Usage-Keeper-Request': 'fetch'}
    progress = lambda: json.loads(request(keeper + '/api/v1/sessions/rebalances', opener=session)[1])['items']
    assert request(keeper + '/api/v1/sessions/rebalances')[0] == 401
    for restricted in (viewer, ro):
        assert request(gateway + '/test-quota/api/v1/sessions/rebalances', opener=restricted)[0] == 404
    assert request(api + '/v8/management/sessions/rebalances', admin, {'auth_index': account['auth_index']})[0] == 404
    route = keeper + '/api/v1/ai-providers/' + account['auth_index'] + '/priority'
    with connect(api.replace('http:', 'ws:') + '/v1/responses', additional_headers=auth) as active, connect(api.replace('http:', 'ws:') + '/v1/responses', additional_headers=auth) as idle:
        active.send(json.dumps({'type': 'response.create', 'model': 'a/quota-test', 'instructions': '__interrupt_fixture__', 'input': []}))
        assert json.loads(active.recv(timeout=20))['type'] == 'response.created'
        idle.send(json.dumps({'type': 'response.create', 'model': 'b/quota-test', 'input': []}))
        while json.loads(idle.recv(timeout=20))['type'] != 'response.completed':
            pass
        before = progress()
        assert request(route, headers, {'priority': 0}, session, method='PATCH')[0] == 200
        assert progress() == before, 'plain priority save rebalanced existing sessions'
        status, affinity = request(route, headers, {'priority': 0, 'rebalance_sessions': True}, session, method='PATCH')
        assert status == 200
        affinity_job = json.loads(affinity)['rebalance']
        assert affinity_job['affinity_rebalanced'] and not affinity_job['reconnect_websockets'] and affinity_job['waiting'] == 0
        assert idle.ping().wait(2) and active.ping().wait(2), 'affinity-only rebalance closed a socket'
        status, body = request(route, headers, {'priority': 0, 'rebalance_sessions': True, 'reconnect_websockets': True}, session, method='PATCH')
        assert status == 200, 'priority rebalance save failed'
        job = json.loads(body)['rebalance']
        assert job['waiting'] == 1 and job['sessions_rebalanced'] == 1, job
        expect_rebalanced_close(idle)
        active.send(json.dumps({'type': 'response.interrupt', 'response_id': 'resp-interrupt', 'mode': 'discard_partial_items', 'extension': 'preserve-me'}))
        assert json.loads(active.recv(timeout=20))['type'] == 'response.incomplete'
        expect_rebalanced_close(active)
        eventually(lambda: any(j['id'] == job['id'] and j['waiting'] == 0 and j['sessions_rebalanced'] == 2 for j in progress()))
    print('PASS: successful priority save precedes pool-wide rebalance; ordinary save preserves sessions; idle other-account session retires while running response drains; admin-only progress updates', flush=True)


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
    # Earlier failure/SSE checks intentionally cool account b.
    eventually(lambda: request(api + '/v1/responses', auth, {'model': 'b/quota-test', 'input': []})[0] == 200, timeout=90)
    initial_account = items[0]
    verify_priority_rebalance(api, private, keeper, gateway, auth, admin, admin_session, viewer, ro, initial_account)
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
        payload = {'auth_index': a['auth_index'], 'provider': a['provider'], 'thresholds': {window['id']: 77}, 'expected_thresholds': {}, 'rebalance_settings': {'rebalance_sessions': True, 'reconnect_websockets': True}, 'expected_rebalance_settings': a['rebalance_settings']}
        stream = LiveStream(keeper + '/api/v1/live', opener=admin_session)
        try:
            before = counter()
            assert request(keeper + route, headers, payload, admin_session, method='PUT')[0] == 200
            stream.wait('quota')
            protected = next(item for item in read() if item['auth_index'] == a['auth_index'])
            assert protected['excluded'] and protected['reason'] == 'minimum_reached'
            progress = lambda: json.loads(request(keeper + '/api/v1/sessions/rebalances', opener=admin_session)[1])['items']
            eventually(lambda: any(j['reason'] == 'quota_policy_excluded' and j['waiting'] == 1 for j in progress()))
            ws.send(json.dumps({'type': 'response.interrupt', 'response_id': 'resp-interrupt', 'mode': 'discard_partial_items', 'extension': 'preserve-me'}))
            finished = json.loads(ws.recv(timeout=20))
            assert finished['type'] == 'response.incomplete', finished
            expect_rebalanced_close(ws)
            eventually(lambda: any(j['reason'] == 'quota_policy_excluded' and j['waiting'] == 0 and j['sessions_rebalanced'] == 1 for j in progress()))
            # A duplicate editor cannot silently overwrite the newly saved setting.
            assert request(keeper + route, headers, payload, admin_session, method='PUT')[0] == 409
            assert request(api + '/v1/responses', auth, {'model': 'a/quota-test', 'input': []})[0] >= 400
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
            assert protected['rebalance_settings'] == payload['rebalance_settings'], 'restart lost reconnect opt-in'
            clear = {**payload, 'thresholds': {}, 'expected_thresholds': payload['thresholds'], 'rebalance_settings': {'rebalance_sessions': True, 'reconnect_websockets': False}, 'expected_rebalance_settings': payload['rebalance_settings']}
            assert request(keeper + route, headers, clear, admin_session, method='PUT')[0] == 200
            assert request(api + '/v1/responses', auth, {'model': 'a/quota-test', 'input': []})[0] == 200
            assert next(item for item in read() if item['auth_index'] == a['auth_index'])['thresholds'] == {}
            print('PASS: Keeper per-window policy, exact boundary, SSE, conflict protection, HTTP exclusion, automatic safe WebSocket rebalance, independent accounts, restart protection and clearing without provider probes', flush=True)
        finally:
            stream.close()
            request(keeper + '/api/v1/auth/logout', headers, {}, admin_session)
