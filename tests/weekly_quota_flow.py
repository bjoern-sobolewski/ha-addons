"""Weekly reporting on an isolated Keeper database; no real provider traffic."""
import http.cookiejar
import json
import os
from pathlib import Path
import secrets
import tempfile
import urllib.request

from smoke import docker, eventually, request


SEED = r'''
import sqlite3
from datetime import datetime, timedelta, timezone
c = sqlite3.connect('/data/app.db')
now = datetime.now(timezone.utc).replace(microsecond=0)
reset = now - timedelta(hours=2)
def stamp(t): return t.strftime('%Y-%m-%dT%H:%M:%SZ')
def ordered(t): return t.strftime('%Y-%m-%dT%H:%M:%S.000000000Z')
c.execute("INSERT INTO usage_identities (id,name,auth_type,identity,type,provider,is_deleted) VALUES (9001,'Synthetic weekly',1,'synthetic-weekly-auth','codex','codex',0)")
c.execute("INSERT INTO model_price_settings (model,prompt_price_per1_m,completion_price_per1_m,cache_read_price_per1_m,price_multiplier) VALUES ('weekly-test-model',1,0,0,1)")
for cycle_id,start,end,percentages in [(9001,reset-timedelta(days=7),reset,[80,20]),(9002,reset,reset+timedelta(days=7),[100,98,96,94])]:
    observations = [start+timedelta(minutes=20*i) for i in range(len(percentages))]
    c.execute('INSERT INTO quota_cycles (id,provider,auth_index,quota_key,window_seconds,reset_at_source,window_started_at,reset_at,first_observed_at,last_observed_at,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
              (cycle_id,'codex','synthetic-weekly-auth','rate_limit.primary_window',604800,'absolute',ordered(start),ordered(end),ordered(observations[0]),ordered(observations[-1]),stamp(start),stamp(start)))
    for percent,at in zip(percentages,observations):
        c.execute('INSERT INTO quota_percent_segments (cycle_id,remaining_percent,first_observed_at,last_observed_at,observation_count,created_at,updated_at) VALUES (?,?,?,?,?,?,?)',
                  (cycle_id,percent,ordered(at),ordered(at),1,stamp(at),stamp(at)))
    for i in range(30):
        at = start+timedelta(minutes=1+2*i)
        table = 'usage_events_archive' if cycle_id==9001 else 'usage_events'
        c.execute('INSERT INTO '+table+' (id,event_key,api_group_key,provider,auth_type,auth_index,model,upstream_service_tier,timestamp,input_tokens,total_tokens,failed) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                  (cycle_id*100+i,'synthetic-event-'+str(cycle_id*100+i),'synthetic-private-client-key','codex','oauth','synthetic-weekly-auth','weekly-test-model','priority',stamp(at),1000000,1000000,0))
# Independent account with no quota cycles: performance is stored request metadata.
c.execute("INSERT INTO usage_identities (id,name,auth_type,identity,type,provider,is_deleted) VALUES (9101,'Synthetic performance',1,'synthetic-performance-auth','codex','codex',0)")
event_id = 2000000
for model, mode, small_count, large_count, small_ms, large_ms in [('performance-a','default',50,5,5000,100000),('performance-b','default',5,50,2000,80000),('performance-a','priority',10,10,1000,8000)]:
    for input_tokens, count, latency in [(1000, small_count, small_ms),(40000, large_count, large_ms)]:
        for i in range(count):
            event_id += 1
            table = 'usage_events_archive' if i % 2 else 'usage_events'
            c.execute('INSERT INTO '+table+' (id,event_key,api_group_key,provider,auth_type,auth_index,model,upstream_service_tier,timestamp,input_tokens,output_tokens,total_tokens,failed,generate,stream,latency_ms,ttft_ms,reasoning_effort,executor_type) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                      (event_id,'synthetic-performance-'+str(event_id),'synthetic-private-client-key','codex','oauth','synthetic-performance-auth',model,mode,stamp(now-timedelta(hours=1)),input_tokens,100,input_tokens+100,0,1,1,latency,300,'low','codex-websocket'))
c.commit()
'''


def main():
    image = os.environ.get('KEEPER_WEEKLY_IMAGE', 'ha-keeper-weekly:local')
    name = 'keeper-weekly-' + secrets.token_hex(4)
    volume = name + '-data'
    password, readonly, management = (secrets.token_urlsafe(32) for _ in range(3))
    with tempfile.TemporaryDirectory() as directory:
        options = Path(directory) / 'options.json'
        options.write_text(json.dumps({'cpa_base_url': 'http://127.0.0.1:9', 'management_key': management,
                                      'login_password': password, 'read_only_password': readonly,
                                      'viewer_base_path': '/weekly-test', 'viewer_dashboard_enabled': True, 'timezone': 'UTC'}))
        try:
            docker('volume', 'create', volume)
            docker('create', '--name', name, '-e', 'TZ=UTC', '-v', volume + ':/data',
                   '-p', '127.0.0.1::8080', '-p', '127.0.0.1::8082', image)
            docker('cp', str(options), name + ':/data/options.json')
            docker('start', name)
            lan = 'http://' + docker('port', name, '8080/tcp').splitlines()[0]
            eventually(lambda: request(lan + '/healthz')[0] == 200)
            docker('stop', name)
            docker('run', '--rm', '-v', volume + ':/data', 'python:3.13-alpine', 'python', '-c', SEED)
            docker('start', name)
            lan = 'http://' + docker('port', name, '8080/tcp').splitlines()[0]
            gateway = 'http://' + docker('port', name, '8082/tcp').splitlines()[0]
            eventually(lambda: request(lan + '/healthz')[0] == 200)
            opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
            prefix = gateway + '/weekly-test/api/v1'
            assert request(prefix + '/auth/read-only-login', {'X-CPA-Usage-Keeper-Request': 'fetch'}, {'password': readonly}, opener)[0] == 204
            url = prefix + '/read-only/accounts/9001/weekly-quota'
            assert request(url)[0] == 401
            status, body = request(url, opener=opener)
            assert status == 200, status
            report = json.loads(body)
            assert len(report['cycles']) == 2
            assert all(c['window_seconds'] == 604800 and c['usage']['total_cost_usd'] == 30 for c in report['cycles']), [(c['window_seconds'], c['usage']) for c in report['cycles']]
            mode = report['weekly_value']['modes'][0]
            assert mode['mode'] == 'fast' and mode['total_cost_usd'] == 60
            # Both cycles have eligible samples; the old cycle has one 60-point drop.
            assert mode['ready'] and mode['sample_requests'] == 40
            assert mode['percentage_points'] == 66 and abs(mode['full_allowance_usd'] - 4000/66) < 1e-9
            resets = {item['cycle_id']: item for item in report['weekly_value']['resets']}
            assert resets[9001]['rollover_observed_at'] and report['cycles'][1]['last_remaining_percent'] == 20
            for hidden in (password, readonly, management, 'synthetic-weekly-auth', 'synthetic-private-client-key'):
                assert hidden.encode() not in body
            assert request(url, opener=opener, method='DELETE')[0] in (403, 404, 405)
            assert request(prefix + '/quota/history/synthetic-weekly-auth', opener=opener)[0] == 404
            assert request(prefix + '/read-only/accounts/0/weekly-quota', opener=opener)[0] == 404
            assert request(url + '?window_role=bad', opener=opener)[0] == 400
            performance_url = prefix + '/read-only/accounts/9101/performance?days=30&metric=latency'
            assert request(performance_url)[0] == 401
            status, performance_body = request(performance_url, opener=opener)
            assert status == 200, (status, performance_body)
            performance = json.loads(performance_body)
            assert performance['comparison_groups'] == 3 and performance['common_cells'] == 2
            groups = {(g['model'], g['mode']): g for g in performance['groups']}
            assert groups[('performance-a', 'normal')]['raw']['median'] == 5
            assert groups[('performance-b', 'normal')]['raw']['median'] == 80
            assert groups[('performance-b', 'normal')]['matched']['median'] == 2
            assert groups[('performance-a', 'fast')]['matched']['samples'] == 20
            assert sum(g['requests'] for g in performance['groups']) == 130
            for hidden in (password, readonly, management, 'synthetic-performance-auth', 'synthetic-private-client-key'):
                assert hidden.encode() not in performance_body
            for metric in ('ttft', 'tps', 'phase'):
                status, metric_body = request(performance_url.replace('metric=latency', 'metric=' + metric), opener=opener)
                assert status == 200 and any(g['raw']['median'] is not None for g in json.loads(metric_body)['groups'])
            assert request(performance_url + '&mode=bad', opener=opener)[0] == 400
            assert request(prefix + '/quota/performance/synthetic-performance-auth', opener=opener)[0] == 404
            assert request(performance_url, opener=opener, method='DELETE')[0] in (403, 404, 405)
            print('PASS: packaged weekly value and raw/matched performance, archived timings, metric filters, gateway and read-only isolation')
        finally:
            docker('rm', '-f', name, check=False)
            docker('volume', 'rm', volume, check=False)


if __name__ == '__main__':
    main()
