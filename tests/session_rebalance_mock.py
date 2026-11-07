"""Deterministic upstream for the real Codex app-server recovery test."""
import json
import uuid
from aiohttp import web

events = []
MARKER = 'REBALANCE_CONTEXT_92817'


async def responses(request):
    account = 'b' if request.headers.get('Authorization', '').endswith('fake-account-b') else 'a'
    socket = web.WebSocketResponse(compress=False)
    assert socket.can_prepare(request).ok, 'Codex recovery test must use WebSockets'
    await socket.prepare(request)
    known = set()
    has_marker = False
    has_tool = False
    async for message in socket:
        if message.type != web.WSMsgType.TEXT:
            continue
        frame = json.loads(message.data)
        previous = frame.get('previous_response_id')
        text = json.dumps(frame.get('input', []))
        has_marker |= MARKER in text
        has_tool |= 'TOOL_CONTEXT_OK' in text
        events.append({'account': account, 'full': not previous, 'marker': has_marker,
                       'tool': has_tool, 'prewarm': frame.get('generate') is False,
                       'input_types': [item.get('type', item.get('role')) for item in frame.get('input', []) if isinstance(item, dict)]})
        if previous and previous not in known:
            await socket.send_json({'type': 'error', 'status': 400, 'error': {
                'code': 'previous_response_not_found', 'type': 'invalid_request_error',
                'param': 'previous_response_id', 'message': 'Resend full context'}})
            continue
        rid = 'resp_' + uuid.uuid4().hex
        known.add(rid)
        result = {'id': rid, 'object': 'response', 'model': 'gpt-6.1-sol',
                  'status': 'in_progress', 'output': []}
        await socket.send_json({'type': 'response.created', 'response': result})
        if frame.get('generate') is False:
            output = []
        elif not has_tool:
            assert has_marker, 'initial conversation context missing'
            output = [{'type': 'function_call', 'id': 'fc_rebalance',
                       'call_id': 'pending_rebalance_tool', 'name': 'rebalance_probe',
                       'arguments': '{}', 'status': 'completed'}]
        else:
            assert has_marker, 'conversation context lost after migration'
            output = [{'type': 'message', 'id': 'msg_' + uuid.uuid4().hex,
                       'role': 'assistant', 'status': 'completed',
                       'content': [{'type': 'output_text', 'text': 'RECOVERED_CONTEXT_OK', 'annotations': []}]}]
        for i, item in enumerate(output):
            await socket.send_json({'type': 'response.output_item.added', 'output_index': i, 'item': item})
            await socket.send_json({'type': 'response.output_item.done', 'output_index': i, 'item': item})
        await socket.send_json({'type': 'codex.rate_limits', 'rate_limits': {
            'primary': {'used_percent': 90 if account == 'a' else 10, 'window_minutes': 300, 'reset_after_seconds': 3600}}})
        await socket.send_json({'type': 'response.completed', 'response': {
            **result, 'status': 'completed', 'output': output,
            'usage': {'input_tokens': 10, 'output_tokens': 2, 'total_tokens': 12}}})
    return socket


app = web.Application()
app.router.add_route('*', '/responses', responses)
app.router.add_get('/stats', lambda _: web.json_response({'events': events}))
web.run_app(app, port=9000, print=None)
