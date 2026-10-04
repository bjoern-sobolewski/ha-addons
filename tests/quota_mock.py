"""Synthetic upstream HTTP and WebSocket quota; never contacts a real provider."""
from aiohttp import web
import json, time
calls=0

async def responses(request):
    global calls
    calls+=1
    account='b' if request.headers.get('Authorization','').endswith('fake-account-b') else 'a'
    used=71 if account=='b' else 17
    result={'id':'resp-test','object':'response','status':'completed','model':'gpt-5.5','service_tier':'default','output':[],'usage':{'input_tokens':10,'output_tokens':1,'total_tokens':11}}
    socket=web.WebSocketResponse(compress=False)
    if socket.can_prepare(request).ok:
        await socket.prepare(request)
        async for message in socket:
            if message.type==web.WSMsgType.TEXT:
                assert json.loads(message.data).get('service_tier')=='priority'
                used=73 if account=='b' else 23
                await socket.send_json({'type':'codex.rate_limits','rate_limits':{'primary':{'used_percent':used,'window_minutes':300,'reset_after_seconds':3600},'secondary':{'used_percent':5,'window_minutes':10080,'reset_after_seconds':86400}}})
                await socket.send_json({'type':'response.completed','response':result})
        return socket
    assert (await request.json()).get('service_tier')=='priority'
    return web.Response(text='data: '+json.dumps({'type':'response.completed','response':result})+'\n\n',content_type='text/event-stream',headers={'X-Codex-Primary-Used-Percent':str(used),'X-Codex-Primary-Window-Minutes':'300','X-Codex-Primary-Reset-After-Seconds':'3600','Set-Cookie':'synthetic-secret-cookie'})

app=web.Application()
async def stats(request):return web.json_response({'calls':calls})
app.router.add_get('/stats',stats)
app.router.add_route('*','/responses',responses)
web.run_app(app,port=9000,print=None)
