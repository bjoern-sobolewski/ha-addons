"""Verify selected-account traffic capture, shared caches, and reporting permissions."""
from pathlib import Path
import http.cookiejar, json, os, secrets, tempfile, time
import yaml
from websockets.sync.client import connect
from smoke import docker, request, eventually

ROOT=Path(__file__).resolve().parents[1]
CPA_QUOTA_IMAGE=os.environ.get('CPA_QUOTA_IMAGE','ha-cpa-quota:local')
KEEPER_QUOTA_IMAGE=os.environ.get('KEEPER_QUOTA_IMAGE','ha-keeper-quota:local')
def main():
 prefix='quota-flow-'+secrets.token_hex(4);network=prefix+'-net'
 names={k:prefix+'-'+k for k in ('mock','cpa','keeper')};volumes=[prefix+'-cpa',prefix+'-keeper']
 key,management,password,readonly=(secrets.token_urlsafe(32) for _ in range(4))
 def endpoint(name,port):return 'http://'+docker('port',names[name],f'{port}/tcp').splitlines()[0]
 with tempfile.TemporaryDirectory() as directory:
  tmp=Path(directory);config=tmp/'config';config.mkdir()
  (config/'providers.yaml').write_text(yaml.safe_dump({'api-keys':{'codex':[{'name':'test-'+a,'keys':[{'api-key':'fake-account-'+a,'websockets':True}],'base-url':'http://mock:9000','prefix':a,'models':[{'name':'gpt-5.5','alias':'quota-test'}]} for a in ('a','b')]},'requests':{'payload':{'override':[{'models':[{'name':'*','protocol':'codex'}],'params':{'service_tier':'priority'}}]}}}))
  (tmp/'cpa.json').write_text(json.dumps({'api_keys':[key],'management_key':management}))
  (tmp/'keeper.json').write_text(json.dumps({'cpa_base_url':'http://cpa:8317','management_key':management,'login_password':password,'read_only_password':readonly,'viewer_base_path':'/test-quota','viewer_dashboard_enabled':True,'viewer_quota_enabled':True,'viewer_api_gateway_enabled':True}))
  try:
   docker('network','create',network)
   for v in volumes:docker('volume','create',v)
   docker('run','-d','--name',names['mock'],'--network',network,'--network-alias','mock','-v',f'{ROOT / "tests"}:/test:ro','python:3.13-alpine','sh','-c','pip install -q aiohttp==3.13.3 && python /test/quota_mock.py')
   # The fixture installs its dependency at startup. Do not send failing traffic
   # or let Keeper snapshot partially initialized metadata before it is ready.
   eventually(lambda:json.loads(docker('exec',names['mock'],'python','-c','import urllib.request;print(urllib.request.urlopen("http://localhost:9000/stats").read().decode())'))['calls']==0,timeout=90)
   docker('create','--name',names['cpa'],'--network',network,'--network-alias','cpa','-v',volumes[0]+':/data','-v',str(config)+':/config:ro','-p','127.0.0.1::8080','-p','127.0.0.1::8317',CPA_QUOTA_IMAGE)
   docker('create','--name',names['keeper'],'--network',network,'-v',volumes[1]+':/data','-p','127.0.0.1::8080','-p','127.0.0.1::8082',KEEPER_QUOTA_IMAGE)
   for name in ('cpa','keeper'):docker('cp',str(tmp/(name+'.json')),names[name]+':/data/options.json')
   docker('start',names['cpa'])
   api,private=endpoint('cpa',8080),endpoint('cpa',8317)
   auth={'Authorization':'Bearer '+key};admin={'Authorization':'Bearer '+management}
   eventually(lambda:request(api+'/v1/models',auth)[0]==200)
   docker('start',names['keeper'])
   keeper,gateway=endpoint('keeper',8080),endpoint('keeper',8082)
   body=lambda account:{'model':account+'/quota-test','input':'Reply briefly.','stream':False}
   # Configure WebSocket-capable runtime API credentials in the isolated configuration.
   for account in ('a','b'):
    eventually(lambda:request(api+'/v1/responses',auth,body(account))[0]==200,timeout=90)
   cached=lambda:json.loads(request(private+'/v0/management/quota/observations',admin)[1])['items']
   initial=cached();assert len(initial)==2 and sorted(int(i['headers']['X-Codex-Primary-Used-Percent'][0]) for i in initial)==[17,71]
   assert all(i['source']=='api_response_headers' for i in initial)
   assert request(private+'/v0/management/quota/observations',auth)[0]==401
   assert request(api+'/v0/management/quota/observations',admin)[0]==404
   assert request(gateway+'/test-quota/api/v1/quota/observations',admin)[0]==404
   captured=[i['observed_at'] for i in initial];time.sleep(.2);assert [i['observed_at'] for i in cached()]==captured
   viewer=__import__('urllib.request',fromlist=['build_opener']).build_opener(__import__('urllib.request',fromlist=['HTTPCookieProcessor']).HTTPCookieProcessor(http.cookiejar.CookieJar()))
   ro=__import__('urllib.request',fromlist=['build_opener']).build_opener(__import__('urllib.request',fromlist=['HTTPCookieProcessor']).HTTPCookieProcessor(http.cookiejar.CookieJar()))
   headers={'X-CPA-Usage-Keeper-Request':'fetch'}
   eventually(lambda:request(gateway+'/test-quota/api/v1/auth/api-key-login',headers,{'apiKey':key},viewer)[0]==204)
   assert request(gateway+'/test-quota/api/v1/auth/read-only-login',headers,{'password':readonly},ro)[0]==204
   view=lambda:json.loads(request(gateway+'/test-quota/api/v1/key-quota',opener=viewer)[1])['accounts']
   allview=lambda:json.loads(request(gateway+'/test-quota/api/v1/read-only/key-quota',opener=ro)[1])['accounts']
   eventually(lambda:len([a for a in view() if a['rows']])==2,timeout=90)
   assert sorted(round(a['rows'][0]['remaining_percent']) for a in view() if a['rows'])==[29,83]
   with connect(api.replace('http:','ws:')+'/v1/responses',additional_headers={'Authorization':'Bearer '+key},open_timeout=20) as ws:
    ws.send(json.dumps({'type':'response.create','model':'a/quota-test','input':[{'role':'user','content':[{'type':'input_text','text':'Reply briefly.'}]}]}))
    got_quota=False
    while True:
     event=json.loads(ws.recv(timeout=20));assert event.get('type')!='error',event;got_quota |= event.get('type')=='codex.rate_limits'
     if event.get('type')=='response.completed':break
   assert got_quota,'upstream WebSocket event not forwarded'
   # Capture after overrides, independently of client auto and response default,
   # on both HTTP and WebSocket requests, including the read-only API/export.
   events=lambda:json.loads(request(gateway+'/test-quota/api/v1/read-only/events?range=today',opener=ro)[1])['events']
   eventually(lambda:len(events())>=3)
   assert all(e.get('upstream_service_tier')=='priority' and e.get('response_service_tier')=='default' for e in events())
   assert all(e.get('service_tier')=='auto' for e in events())
   exported=json.loads(request(gateway+'/test-quota/api/v1/read-only/events/export?range=today&format=json',opener=ro)[1])
   assert '"upstream_service_tier": "priority"' in json.dumps(exported)
   eventually(lambda:any(i['source']=='websocket_event' and i['headers'].get('X-Codex-Primary-Used-Percent')==['23'] for i in cached()))
   eventually(lambda:any(any(r.get('source')=='websocket_event' and round(r.get('remaining_percent',-1))==77 for r in a['rows']) for a in view()))
   assert allview()==view()
   for account in view():
    for row in account['rows']:assert row['captured_at'] and row['source'] and row['stale'] is False
   rendered=json.dumps(view())
   for secret in (key,management,password,readonly,'fake-account-a','fake-account-b','synthetic-secret-cookie','auth_index'):assert secret not in rendered
   assert request(gateway+'/test-quota/api/v1/read-only/key-quota',opener=viewer)[0]==403
   lanro=__import__('urllib.request',fromlist=['build_opener']).build_opener(__import__('urllib.request',fromlist=['HTTPCookieProcessor']).HTTPCookieProcessor(http.cookiejar.CookieJar()))
   assert request(keeper+'/api/v1/auth/read-only-login',headers,{'password':readonly},lanro)[0]==204
   assert request(keeper+'/api/v1/quota/refresh',headers,{'auth_indexes':['anything']},lanro)[0]==403
   assert request(keeper+'/api/v1/usage/provider-quota',opener=lanro)[0]==403
   counter=lambda:json.loads(docker('exec',names['mock'],'python','-c','import urllib.request;print(urllib.request.urlopen("http://localhost:9000/stats").read().decode())'))['calls']
   count=counter();times=[r['captured_at'] for a in view() for r in a['rows']]
   for _ in range(3):
    time.sleep(10);view();allview();cached()
   assert counter()==count,'cache polling invoked the provider'
   assert times==[r['captured_at'] for a in view() for r in a['rows']],'reads refreshed capture time'
   print('PASS: HTTP headers and WebSocket events update separate accounts and windows in CPA and Keeper; capture time, cache reads, sanitization, roles, and routing verified',flush=True)
  except Exception:
   # Only counts/type/eligibility flags: never dump credential metadata or keys.
   try:
    counts=docker('exec',names['keeper'],'python3','-c','import sqlite3,json;c=sqlite3.connect("file:/data/app.db?mode=ro",uri=True);print(json.dumps(c.execute("SELECT auth_type,type,is_deleted,disabled,count(*) FROM usage_identities GROUP BY auth_type,type,is_deleted,disabled").fetchall()))')
    print('Keeper synthetic identity eligibility counts: '+counts,flush=True)
   except Exception:pass
   for name in names.values():
    logs=docker('logs',name,check=False)
    for secret in (key,management,password,readonly):logs=logs.replace(secret,'[test credential]')
    print(name+': '+logs[-3000:],flush=True)
   raise
  finally:
   for name in names.values():docker('rm','-f',name,check=False)
   for v in volumes:docker('volume','rm',v,check=False)
   docker('network','rm',network,check=False)
if __name__=='__main__':main()
