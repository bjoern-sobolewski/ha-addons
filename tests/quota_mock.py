"""Synthetic upstream HTTP and WebSocket quota; never contacts a real provider."""
from aiohttp import web
import json, time
calls=0

async def responses(request):
    global calls
    calls+=1
    account='b' if request.headers.get('Authorization','').endswith('fake-account-b') else 'a'
    used=71 if account=='b' else 17
    result={'id':'resp-test','object':'response','status':'completed','model':'gpt-5.5','service_tier':'default','output':[],'usage':{'input_tokens':10,'output_tokens':1,'total_tokens':11},'tool_usage':{'image_gen':{'input_tokens':0,'output_tokens':0,'total_tokens':0}}}
    socket=web.WebSocketResponse(compress=False)
    if socket.can_prepare(request).ok:
        await socket.prepare(request)
        interrupt_pending=False
        async for message in socket:
            if message.type==web.WSMsgType.TEXT:
                frame=json.loads(message.data)
                if frame.get('type')=='response.interrupt':
                    assert interrupt_pending, 'interrupt without active turn'
                    assert frame=={'type':'response.interrupt','response_id':'resp-interrupt','mode':'discard_partial_items','extension':'preserve-me'}, 'interrupt was rewritten'
                    interrupt_pending=False
                    await socket.send_json({'type':'response.incomplete','response':{**result,'id':'resp-interrupt','status':'incomplete','incomplete_details':{'reason':'interrupted'}}})
                    continue
                assert frame.get('service_tier')=='priority'
                if frame.get('instructions')=='__interrupt_fixture__':
                    interrupt_pending=True
                    await socket.send_json({'type':'response.created','response':{'id':'resp-interrupt'}})
                    continue
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
