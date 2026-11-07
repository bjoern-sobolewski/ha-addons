"""Local-only upstream for live activity tests; never contacts a provider."""
import asyncio, json, uuid
from aiohttp import web
held=[]
http_release=asyncio.Event()
calls=0
async def responses(request):
 global calls
 calls+=1
 ws=web.WebSocketResponse(compress=False)
 if not ws.can_prepare(request).ok:
  body=await request.json()
  if body.get('instructions')=='hold': await http_release.wait()
  result={'id':'http-result','object':'response','status':'completed','model':'gpt-5.5','output':[],'usage':{'input_tokens':2,'output_tokens':1,'total_tokens':3}}
  return web.Response(text='data: '+json.dumps({'type':'response.completed','response':result})+'\n\n',content_type='text/event-stream')
 await ws.prepare(request)
 async for message in ws:
  if message.type!=web.WSMsgType.TEXT:continue
  frame=json.loads(message.data);rid='resp_'+uuid.uuid4().hex
  result={'id':rid,'object':'response','status':'in_progress','model':'gpt-5.5','output':[]}
  await ws.send_json({'type':'response.created','response':result})
  if frame.get('instructions')=='hold': held.append((ws,result));continue
  output=[]
  if frame.get('instructions')=='tool':output=[{'type':'function_call','id':'fc-local','call_id':'private-tool-id','name':'local_probe','arguments':'{}','status':'completed'}]
  await ws.send_json({'type':'response.completed','response':{**result,'status':'completed','output':output,'usage':{'input_tokens':2,'output_tokens':1,'total_tokens':3}}})
 return ws
async def release(request):
 for ws,result in held:
  if not ws.closed:await ws.send_json({'type':'response.completed','response':{**result,'status':'completed','output':[],'usage':{'input_tokens':2,'output_tokens':1,'total_tokens':3}}})
 held.clear();http_release.set();return web.json_response({'ok':True})
app=web.Application()
app.router.add_route('*','/responses',responses)
app.router.add_post('/release',release)
app.router.add_get('/stats',lambda _:web.json_response({'calls':calls}))
web.run_app(app,port=9000,print=None)
