"""Live HTTP/WS lifecycle, routing, draining and admin isolation using local upstreams."""
from pathlib import Path
import concurrent.futures, http.cookiejar, json, os, secrets, tempfile, time, urllib.request
import yaml
from websockets.sync.client import connect
from websockets.exceptions import ConnectionClosed
from smoke import docker,request,eventually
from live_sse import LiveStream
ROOT=Path(__file__).resolve().parents[1]
def main():
 prefix='routing-'+secrets.token_hex(4);network=prefix+'-net'
 names={k:prefix+'-'+k for k in ('mock','cpa','keeper')};volumes=[prefix+'-cpa',prefix+'-keeper']
 key,management,readonly=(secrets.token_urlsafe(32) for _ in range(3));password='synthetic-routing-preview-password'
 sockets=[];streams=[];pool=concurrent.futures.ThreadPoolExecutor()
 endpoint=lambda name,port:'http://'+docker('port',names[name],f'{port}/tcp').splitlines()[0]
 opener=lambda:urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
 with tempfile.TemporaryDirectory() as directory:
  tmp=Path(directory);config=tmp/'config';config.mkdir()
  (config/'providers.yaml').write_text(yaml.safe_dump({'api-keys':{'codex':[{'name':'Example '+a.upper(),'priority':2 if a=='a' else 1,'keys':[{'api-key':'fake-account-'+a,'websockets':True}],'base-url':'http://mock:9000','models':[{'name':'gpt-5.5','alias':'routing-test'}]} for a in ('a','b')]}}))
  (tmp/'cpa.json').write_text(json.dumps({'api_keys':[key],'management_key':management}))
  (tmp/'keeper.json').write_text(json.dumps({'cpa_base_url':'http://cpa:8317','management_key':management,'login_password':password,'read_only_password':readonly,'viewer_base_path':'/routing-viewer','viewer_dashboard_enabled':True,'viewer_quota_enabled':True,'viewer_api_gateway_enabled':True}))
  try:
   docker('network','create',network)
   for v in volumes:docker('volume','create',v)
   docker('run','-d','--name',names['mock'],'--network',network,'--network-alias','mock','-v',f'{ROOT / "tests"}:/test:ro','python:3.13-alpine','sh','-c','pip install -q aiohttp==3.13.3 && python /test/live_routing_mock.py')
   eventually(lambda:json.loads(docker('exec',names['mock'],'python','-c','import urllib.request;print(urllib.request.urlopen("http://localhost:9000/stats").read().decode())'))['calls']==0,timeout=90)
   docker('create','--name',names['cpa'],'--network',network,'--network-alias','cpa','-v',volumes[0]+':/data','-v',str(config)+':/config:ro','-p','127.0.0.1::8080','-p','127.0.0.1::8317',os.environ.get('CPA_TEST_IMAGE','ha-cpa-routing:local'))
   docker('create','--name',names['keeper'],'--network',network,'-v',volumes[1]+':/data','-p','127.0.0.1::8080','-p','127.0.0.1::8082',os.environ.get('KEEPER_TEST_IMAGE','ha-keeper-routing:local'))
   for name in ('cpa','keeper'):docker('cp',str(tmp/(name+'.json')),names[name]+':/data/options.json')
   docker('start',names['cpa']);api,private=endpoint('cpa',8080),endpoint('cpa',8317)
   auth={'Authorization':'Bearer '+key};admin={'Authorization':'Bearer '+management};headers={'X-CPA-Usage-Keeper-Request':'fetch'}
   eventually(lambda:request(api+'/v1/models',auth)[0]==200)
   docker('start',names['keeper']);keeper,gateway=endpoint('keeper',8080),endpoint('keeper',8082)
   eventually(lambda:request(keeper+'/api/v1/auth/login',headers,{'password':password},session:=opener())[0]==204)
   session=opener();assert request(keeper+'/api/v1/auth/login',headers,{'password':password},session)[0]==204
   route='/api/v1/routing/activity'
   snapshot=lambda:json.loads(request(keeper+route,opener=session)[1])
   assert request(keeper+route)[0]==401
   viewers=[]
   for kind,body in [('api-key',{'apiKey':key}),('read-only',{'password':readonly})]:
    viewer=opener()
    eventually(lambda:request(gateway+'/routing-viewer/api/v1/auth/'+kind+'-login',headers,body,viewer)[0]==204)
    assert request(gateway+'/routing-viewer'+route,opener=viewer)[0]==404
    assert request(keeper+route,opener=viewer)[0] in (401,403)
    viewers.append((kind,viewer))
   assert request(api+'/v8/management/routing/activity',admin)[0]==404
   assert request(private+'/v8/management/routing/activity')[0]==401
   assert not snapshot()['activity']['rows']
   stream=LiveStream(keeper+'/api/v1/live',opener=session);streams.append(stream)
   def socket(instructions=''):
    ws=connect(api.replace('http:','ws:')+'/v1/responses',additional_headers={**auth,'Session_id':'private-fixture-session-'+instructions},open_timeout=20);sockets.append(ws)
    ws.send(json.dumps({'type':'response.create','model':'routing-test','instructions':instructions,'input':[{'role':'user','content':[{'type':'input_text','text':'private-fixture-prompt'}]}]}))
    return ws
   def complete(ws):
    while True:
     event=json.loads(ws.recv(timeout=20));assert event['type']!='error',event
     if event['type']=='response.completed':return event
   busy=socket('hold');assert json.loads(busy.recv(timeout=20))['type']=='response.created'
   tools=socket('tool');complete(tools)
   idle=socket();complete(idle)
   idle.send(json.dumps({'type':'response.create','model':'routing-test','input':[{'role':'user','content':'private-followup-prompt'}]}));complete(idle)
   def held_http():
    req=urllib.request.Request(api+'/v1/responses',data=json.dumps({'model':'routing-test','instructions':'hold','input':'private-http-prompt'}).encode(),headers={**auth,'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=600) as response:return response.status,response.read()
   future=pool.submit(held_http)
   def ready():
    rows=snapshot()['activity']['rows']
    return len(rows)==4 and all(row.get('account') for row in rows)
   eventually(ready)
   stream.wait('routing')
   data=snapshot();rows=data['activity']['rows']
   assert sum(r['active'] for r in rows)==2,rows
   assert sorted(r['state'] for r in rows)==['idle','running','running','waiting_tools'],rows
   assert all(r['account'] and r['model']=='routing-test' for r in rows),rows
   assert all(any(c['status']=='selected' for c in r['candidates']) for r in rows)
   assert any(r.get('work') and r['work'][0]['state']=='generating' for r in rows)
   assert all(r['prompt_preview']['current']==('private-http-prompt' if r['kind']=='http' else 'private-followup-prompt' if r['state']=='idle' else 'private-fixture-prompt') for r in rows),rows
   idle_row=next(r for r in rows if r['state']=='idle')
   assert idle_row['prompt_preview']['initial']=='private-fixture-prompt',idle_row
   tool_row=next(r for r in rows if r['state']=='waiting_tools')
   assert tool_row['activity']['phase']=='waiting_tools',tool_row
   assert tool_row['activity']['tool_names']==['local_probe'],tool_row
   assert next(r for r in rows if r['state']=='running' and r['kind']=='websocket')['activity']['output_events']>=1
   for secret in [key,management,'private-fixture-session','private-tool-id','private-generated-answer','private-tool-output']:
    assert secret not in json.dumps(data),'private request data in telemetry'
   print('PASS: live HTTP/WS requests, idle sockets, pending tools, routing candidates, private SSE and opaque references',flush=True)
   index=next(r['account'] for r in rows if r['kind']=='websocket')
   response=request(keeper+'/api/v1/ai-providers/'+index+'/priority',headers,{'priority':2,'rebalance_sessions':True,'reconnect_websockets':True},session,method='PATCH')
   assert response[0]==200,response[0]
   eventually(lambda:len([r for r in snapshot()['activity']['rows'] if r['draining']])==2)
   data=snapshot();assert any(j['waiting_for_tools']==1 and j['waiting_for_responses']==1 for j in data['rebalances'])
   print('PASS: combined rebalance progress identifies response and tool waits; idle connection retires independently',flush=True)
   if os.environ.get('ROUTING_PREVIEW'):
    target=Path(os.environ['ROUTING_PREVIEW']);target.write_text(json.dumps({'url':keeper+'/live-routing','network':network,'keeper':names['keeper']}))
    print('Preview ready '+keeper+'/live-routing',flush=True)
    stop=target.with_suffix('.stop')
    while not stop.exists():time.sleep(1)
   docker('exec',names['mock'],'python','-c','import urllib.request;urllib.request.urlopen(urllib.request.Request("http://localhost:9000/release",data=b"{}"))')
   complete(busy)
   try:busy.recv(timeout=20);raise AssertionError('missing safe close')
   except ConnectionClosed as e:assert e.rcvd and e.rcvd.code==1012
   tools.send(json.dumps({'type':'response.create','model':'routing-test','input':[{'type':'function_call_output','call_id':'private-tool-id','output':'private-tool-output'}]}));complete(tools)
   assert future.result(timeout=20)[0]==200
   for ws in sockets:ws.close()
   eventually(lambda:not snapshot()['activity']['rows'])
   events_url=keeper+'/api/v1/usage/events?range=24h'
   def previews_ready():
    response=request(events_url,opener=session)
    if response[0]!=200:return False
    events=json.loads(response[1])['events']
    if len(events)<6:return False
    assert 'private-fixture-prompt' not in response[1].decode()
    previews=[json.loads(request(keeper+'/api/v1/usage/events/'+str(e['id'])+'/prompts',opener=session)[1]) for e in events]
    return any(p.get('current')=='private-http-prompt' for p in previews) and sum(p.get('current')=='private-fixture-prompt' for p in previews)>=4 and any(p.get('current')=='private-followup-prompt' and p.get('initial')=='private-fixture-prompt' for p in previews)
   eventually(previews_ready,timeout=120)
   event_id=json.loads(request(events_url,opener=session)[1])['events'][0]['id']
   preview_path='/api/v1/usage/events/'+str(event_id)+'/prompts'
   assert request(keeper+preview_path)[0]==401
   assert request(keeper+preview_path,auth)[0] in (401,403)
   for kind,viewer in viewers:
    assert request(keeper+preview_path,opener=viewer)[0] in (401,403)
    assert request(gateway+'/routing-viewer'+preview_path,opener=viewer)[0]==404
    base='/api/v1/read-only/events' if kind=='read-only' else '/api/v1/key-usage/events'
    for suffix in ('?range=24h','/export?range=24h&format=json','/export?range=24h&format=csv'):
     response=request(gateway+'/routing-viewer'+base+suffix,opener=viewer)
     assert b'private-fixture-prompt' not in response[1] and b'private-http-prompt' not in response[1]
   print('PASS: persisted HTTP/WS/tool-continuation previews; admin-only endpoint; anonymous, bearer, viewer and export isolation',flush=True)
   print('PASS: completed HTTP delivery and disconnected WebSockets leave no active rows',flush=True)
  finally:
   try:docker('exec',names['mock'],'python','-c','import urllib.request;urllib.request.urlopen(urllib.request.Request("http://localhost:9000/release",data=b"{}"))')
   except Exception:pass
   for stream in streams:stream.close()
   for ws in sockets:ws.close()
   pool.shutdown(wait=False,cancel_futures=True)
   for name in reversed(list(names.values())):
    try:docker('rm','-f',name)
    except Exception:pass
   for v in volumes:
    try:docker('volume','rm',v)
    except Exception:pass
   try:docker('network','rm',network)
   except Exception:pass
if __name__=='__main__':main()
