"""Migrate a synthetic packaged v1 Keeper database, then restore it to v1.

This never mounts an existing database. The old release is immutable; override
KEEPER_TEST_IMAGE to select the candidate v2 package. All data and credentials
exist only in disposable Docker resources owned by this invocation.
"""
import copy
import http.cookiejar
import json
import os
from pathlib import Path
import re
import secrets
import tempfile
import time
import urllib.request

from smoke import docker, eventually, request
from weekly_quota_flow import POLICY_SERVER


# Published wrapper 0.1.36: multi-platform OCI index, resolved 2026-11-02.
OLD_IMAGE = (
    'ghcr.io/bjoern-sobolewski/ha-cpa-usage-keeper'
    '@sha256:6e5d2642c56823307623df5c5d3db5d7e68476c1666193b1121c572cac49bedb'
)
FETCH = {'X-CPA-Usage-Keeper-Request': 'fetch'}
VIEWER_PATH = '/migration-test'
MODEL = 'synthetic-migration-model'
KEY = 'synthetic-migration-client-key'
AUTH = 'synthetic-migration-auth'
ALIAS = 'Migration Team \u2713'


SEED = r'''
import json, sqlite3
from datetime import datetime, timedelta, timezone
c = sqlite3.connect('/data/app.db')
now = datetime.now(timezone.utc).replace(microsecond=0)
reset = now - timedelta(hours=2)
def stamp(at): return at.strftime('%Y-%m-%dT%H:%M:%SZ')
def ordered(at): return at.strftime('%Y-%m-%dT%H:%M:%S.000000000Z')
c.execute("INSERT INTO cpa_api_keys (id,api_key,display_key,key_alias,local_ranking_avatar_id,is_deleted,created_at,updated_at) VALUES (9001,?,?,?,17,0,?,?)",
          ('synthetic-migration-client-key','synthetic-***','Migration Team \u2713',stamp(now),stamp(now)))
c.execute("INSERT INTO usage_identities (id,name,auth_type,identity,type,provider,is_deleted) VALUES (9001,'Synthetic migration account',1,'synthetic-migration-auth','codex','codex',0)")
c.execute("INSERT INTO model_price_settings (id,model,pricing_style,prompt_price_per1_m,completion_price_per1_m,cache_read_price_per1_m,cache_creation_price_per1_m,price_multiplier,created_at,updated_at) VALUES (9001,'synthetic-migration-model','openai',1,0,0,0,1,?,?)", (stamp(now),stamp(now)))
c.execute("INSERT INTO model_price_rules (model_price_setting_id,key,value,multiplier,created_at,updated_at) VALUES (9001,'upstream_service_tier','priority',2,?,?)", (stamp(now),stamp(now)))
for cycle,start,end in [(9001,reset-timedelta(days=7),reset),(9002,reset,reset+timedelta(days=7))]:
    c.execute('INSERT INTO quota_cycles (id,provider,auth_index,quota_key,window_seconds,reset_at_source,window_started_at,reset_at,first_observed_at,last_observed_at,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
              (cycle,'codex','synthetic-migration-auth','rate_limit.primary_window',604800,'absolute',ordered(start),ordered(end),ordered(start),ordered(start+timedelta(hours=1)),stamp(start),stamp(start)))
    for percent,at in [(100,start),(60,start+timedelta(hours=1))]:
        c.execute('INSERT INTO quota_percent_segments (cycle_id,remaining_percent,first_observed_at,last_observed_at,observation_count,created_at,updated_at) VALUES (?,?,?,?,?,?,?)',
                  (cycle,percent,ordered(at),ordered(at),1,stamp(at),stamp(at)))
    # Outgoing intent differs from both request and response. The old custom
    # rule prices priority at 2x: known events cost 1, 4, and 0; unknown stays
    # unavailable. Both the hot and archive tables must receive this backfill.
    for offset,model,tier,tokens,failed in [(1,'synthetic-migration-model','default',1000000,0),
                                           (2,'synthetic-migration-model','priority',2000000,0),
                                           (3,'synthetic-unpriced-migration','priority',3000000,0),
                                           (4,'synthetic-migration-model','priority',0,1)]:
        event_id = cycle*100+offset
        at = start+timedelta(minutes=10+offset)
        c.execute('INSERT INTO usage_events (id,event_key,api_group_key,provider,endpoint,auth_type,auth_index,model,service_tier,upstream_service_tier,response_service_tier,executor_type,timestamp,input_tokens,output_tokens,total_tokens,failed,status_code,generate,stream,latency_ms,ttft_ms) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                  (event_id,'synthetic-migration-event-'+str(event_id),'synthetic-migration-client-key','codex','/v1/responses','oauth','synthetic-migration-auth',model,'auto',tier,'default','codex-websocket',stamp(at),tokens,0,tokens,failed,500 if failed else 200,1,1,2000,1000))
# The previous-month row is deliberately distinguishable from request-derived
# current periods. Retain the local ranking snapshot and profile, not just its
# table, along with an application setting that upstream removal used to drop.
last_month = now.replace(day=1)-timedelta(days=1)
ranking_key = last_month.strftime('%Y-%m')
c.execute('INSERT OR REPLACE INTO local_ranking_period_stats (period_kind,period_key,api_key_id,request_count,success_count,failure_count,input_tokens,cache_read_tokens,total_tokens,ttft_sum_ms,ttft_sample_count,latency_sum_ms,latency_sample_count,peak_5m_request_count,peak_5m_total_tokens,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
          ('month',ranking_key,9001,7,6,1,777,0,777,6000,6,14000,7,3,444,stamp(now)))
c.execute("INSERT OR REPLACE INTO app_settings (setting_key,value,value_type,created_at,updated_at) VALUES ('migration.synthetic.marker',?,'json',?,?)",
          (json.dumps({'fixture':1,'ranking_period':ranking_key}),stamp(now),stamp(now)))
c.commit()
assert c.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
c.close()
'''


# Read only legacy fact columns. New fields are checked independently, so an
# intentional schema addition does not hide lost original facts.
SNAPSHOT = r'''
import json, sqlite3
c = sqlite3.connect('file:/data/app.db?mode=ro', uri=True)
def rows(table, columns, order):
    return [list(row) for row in c.execute('SELECT '+columns+' FROM '+table+' ORDER BY '+order)]
facts = {}
event_columns = 'id,event_key,api_group_key,provider,endpoint,auth_type,auth_index,model,service_tier,upstream_service_tier,response_service_tier,executor_type,timestamp,input_tokens,output_tokens,total_tokens,failed,status_code,generate,stream,latency_ms,ttft_ms'
for table in ('usage_events','usage_events_archive'):
    facts[table] = rows(table,event_columns,'id')
for table in ('usage_overview_hourly_stats','usage_overview_daily_stats'):
    facts[table] = list(c.execute('SELECT SUM(request_count),SUM(success_count),SUM(failure_count),SUM(input_tokens),SUM(output_tokens),SUM(total_tokens) FROM '+table).fetchone())
facts['quota_cycles'] = rows('quota_cycles','id,provider,auth_index,quota_key,window_seconds,reset_at_source,window_started_at,reset_at,first_observed_at,last_observed_at,created_at,updated_at','id')
facts['quota_percent_segments'] = rows('quota_percent_segments','id,cycle_id,remaining_percent,first_observed_at,last_observed_at,observation_count,created_at,updated_at','id')
facts['identity'] = rows('usage_identities','id,name,auth_type,identity,type,provider,is_deleted','id')
facts['key_profile'] = rows('cpa_api_keys','id,api_key,display_key,key_alias,local_ranking_avatar_id,is_deleted','id')
facts['marker'] = rows('app_settings',"setting_key,value,value_type","setting_key")
facts['marker'] = [r for r in facts['marker'] if r[0] == 'migration.synthetic.marker']
period = json.loads(facts['marker'][0][1])['ranking_period']
facts['ranking'] = [list(r) for r in c.execute('SELECT period_kind,period_key,api_key_id,request_count,success_count,failure_count,input_tokens,cache_read_tokens,total_tokens,ttft_sum_ms,ttft_sample_count,latency_sum_ms,latency_sample_count,peak_5m_request_count,peak_5m_total_tokens FROM local_ranking_period_stats WHERE period_kind=? AND period_key=? AND api_key_id=9001', ('month',period))]
facts['sessions'] = rows('auth_sessions','token_hash,role,source,alias,cpa_api_key_id','token_hash')
assert c.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
print(json.dumps(facts))
'''


COSTS = r'''
import json, sqlite3
c = sqlite3.connect('file:/data/app.db?mode=ro', uri=True)
result = {}
for table in ('usage_events','usage_events_archive'):
    result[table] = [list(r) for r in c.execute('SELECT id,cost_usd,cost_available FROM '+table+' ORDER BY id')]
for table in ('usage_overview_hourly_stats','usage_overview_daily_stats'):
    result[table] = list(c.execute('SELECT SUM(cost_usd),SUM(unavailable_cost_count),SUM(CASE WHEN cost_usd IS NULL OR unavailable_cost_count IS NULL THEN 1 ELSE 0 END) FROM '+table).fetchone())
result['migration'] = list(c.execute('SELECT init_kind,phase,backup_path,schema_complete,data_complete FROM pricing_migration_state WHERE id=1').fetchone())
print(json.dumps(result))
'''


def volume_python(image, volume, code, backup=None):
    args = ['run', '--rm', '--network', 'none', '-v', volume + ':/data']
    if backup:
        args += ['-v', backup + ':/backup']
    return docker(*args, '--entrypoint', 'python3', image, '-c', code)


def snapshot(name):
    return json.loads(docker('exec', name, 'python3', '-c', SNAPSHOT))


def assert_facts(actual, expected):
    for group in expected:
        assert actual[group] == expected[group], 'Legacy facts changed: ' + group


def costs(name):
    result = json.loads(docker('exec', name, 'python3', '-c', COSTS))
    for table in ('usage_events', 'usage_events_archive'):
        rows = result[table]
        assert len(rows) == 4, 'Missing hot/archive backfilled events'
        for event_id, cost, available in rows:
            offset = event_id % 100
            assert cost is not None and available is not None, 'Incomplete cost backfill'
            assert bool(available) == (offset != 3), 'Unknown pricing became a known zero'
            assert abs(cost - {1: 1, 2: 4, 3: 0, 4: 0}[offset]) < 1e-9, 'Historical cost or outgoing-tier rule changed'
    for table in ('usage_overview_hourly_stats', 'usage_overview_daily_stats'):
        assert result[table] == [10, 2, 0], 'Historical summary costs or unavailable count changed'
    assert result['migration'][3:] == [1, 1], 'Migration data not complete'
    assert result['migration'][2], 'Migration has no protected backup'
    return result


def opener():
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def json_response(url, session=None):
    status, body = request(url, opener=session)
    assert status == 200, 'Unexpected report status: ' + str(status)
    return json.loads(body)


def endpoints(name):
    return tuple('http://' + docker('port', name, str(port) + '/tcp').splitlines()[0] for port in (8080, 8082))


def start_policy(name):
    docker('exec', '-d', name, 'python3', '-c', POLICY_SERVER)
    eventually(lambda: 'version' in docker('exec', name, 'python3', '-c',
        'import urllib.request;print(urllib.request.urlopen("http://127.0.0.1:9001/v8/management/keeper-email-privacy").read().decode())'))


def ready(name, migrated=False):
    lan, gateway = endpoints(name)
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        try:
            if migrated:
                status, body = request(lan + '/api/v1/startup/status')
                if status == 200:
                    phase = json.loads(body)['phase']
                    assert phase != 'failed', 'Keeper reported failed migration startup'
                    if phase == 'ready':
                        costs(name)
                        return lan, gateway
            elif request(lan + '/healthz')[0] == 200:
                return lan, gateway
        except (OSError, json.JSONDecodeError):
            pass
        time.sleep(.5)
    raise AssertionError('Packaged Keeper did not finish startup/migration in 180 seconds')


def check_roles(lan, gateway, sessions, hidden, migrated=False):
    public = gateway + VIEWER_PATH + '/api/v1'
    for origin, session in ((public, sessions['viewer']), (lan + '/api/v1', sessions['direct'])):
        assert json_response(origin + '/auth/session', session)['role'] == 'read_only'
        assert request(origin + '/read-only/overview?range=30d', opener=session)[0] == 200
    assert json_response(lan + '/api/v1/auth/session', sessions['admin'])['role'] == 'admin'
    assert request(public + '/read-only/keys')[0] == 401
    assert ALIAS in request(public + '/read-only/keys', opener=sessions['viewer'])[1].decode()
    overview = json_response(public + '/read-only/overview?range=30d', sessions['viewer'])
    assert overview['overview']['usage']['total_requests'] == 8
    assert abs(overview['overview']['summary']['total_cost'] - 10) < 1e-9
    credentials = '/credentials' if migrated else '/auth-files'
    mutations = [('GET', '/usage/overview'), ('GET', '/auth/sessions'),
                 ('PATCH', credentials + '/status'), ('DELETE', credentials),
                 ('POST', '/quota/reset'), ('PUT', '/pricing/models' if migrated else '/pricing'),
                 ('POST', '/usage/identities/9001/stats/reset')]
    if migrated:
        mutations.append(('POST', '/pricing/recalculations'))
    for method, path in mutations:
        body = {} if method != 'GET' else None
        assert request(lan + '/api/v1' + path, FETCH, body, sessions['direct'], method)[0] == 403, path
        assert request(public + path, FETCH, body, sessions['viewer'], method)[0] == 404, path
    for method in ('POST', 'PATCH', 'PUT', 'DELETE'):
        assert request(public + '/read-only/overview', FETCH, {}, sessions['viewer'], method)[0] == 404
    reports = {}
    for route in ('accounts/9001/weekly-quota', 'events?range=30d', 'events/export?range=30d&format=json',
                  'ranking/local/leaderboards?period=today&metric=total_tokens'):
        status, body = request(public + '/read-only/' + route, opener=sessions['viewer'])
        assert status == 200, 'Migrated viewer report failed: ' + route
        for secret in hidden:
            assert secret.encode() not in body, 'Sensitive field in viewer response'
        reports[route] = json.loads(body)
    weekly = reports['accounts/9001/weekly-quota']
    assert len(weekly['cycles']) == 2
    assert all(c['window_seconds'] == 604800 for c in weekly['cycles'])
    assert sorted(c['usage']['requests'] for c in weekly['cycles']) == [4, 4]
    assert all(abs(c['usage']['total_cost_usd'] - 5) < 1e-9 for c in weekly['cycles']), 'Quota history lost original rule pricing'
    events = reports['events?range=30d']['events']
    assert events and any(event.get('upstream_service_tier') == 'priority' for event in events)
    assert all(event.get('service_tier') == 'auto' and event.get('response_service_tier') == 'default' for event in events)
    return weekly


def failure_diagnostics(names, hidden):
    """Keep CI startup failures actionable without printing fixture credentials."""
    for name in names.values():
        try:
            if not docker('container', 'inspect', name, '--format', '{{.State.Status}}', check=False):
                continue
            logs = docker('logs', name, check=False)
            for secret in hidden:
                logs = logs.replace(secret, '[redacted]')
            logs = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', logs)
            relevant = [line for line in logs.splitlines()
                        if any(word in line.lower() for word in ('migration', 'pricing', 'startup', 'error', 'fatal'))]
            if relevant:
                print('Sanitized startup diagnostics (' + name.rsplit('-', 1)[-1] + '):', flush=True)
                print('\n'.join(relevant[-20:]), flush=True)
        except Exception:
            print('Startup diagnostics unavailable; disposable resources will still be cleaned.', flush=True)


def main():
    image = os.environ.get('KEEPER_TEST_IMAGE', 'ha-keeper-integration:local')
    prefix = 'keeper-migration-' + secrets.token_hex(5)
    network, volume, backup = (prefix + suffix for suffix in ('-net', '-data', '-backup'))
    names = {stage: prefix + '-' + stage for stage in ('old', 'new', 'rollback')}
    password, readonly, management = (secrets.token_urlsafe(32) for _ in range(3))
    hidden = (password, readonly, management, KEY, AUTH)
    sessions = {role: opener() for role in ('viewer', 'direct', 'admin')}
    with tempfile.TemporaryDirectory() as temporary:
        options = Path(temporary) / 'options.json'
        options.write_text(json.dumps({'cpa_base_url': 'http://127.0.0.1:9001', 'management_key': management,
                                      'login_password': password, 'read_only_password': readonly,
                                      'viewer_base_path': VIEWER_PATH, 'viewer_dashboard_enabled': True,
                                      'viewer_quota_enabled': True, 'timezone': 'UTC'}), encoding='utf-8')
        try:
            # Pull by digest, never use a mutable release tag for the old fixture.
            docker('pull', OLD_IMAGE)
            docker('network', 'create', network)
            for item in (volume, backup):
                docker('volume', 'create', item)

            def create(stage, selected_image):
                docker('create', '--init', '--name', names[stage], '--network', network,
                       '-e', 'TZ=UTC', '-v', volume + ':/data', '-p', '127.0.0.1::8080',
                       '-p', '127.0.0.1::8082', selected_image)

            create('old', OLD_IMAGE)
            docker('cp', str(options), names['old'] + ':/data/options.json')
            docker('start', names['old'])
            ready(names['old'])
            docker('stop', names['old'])
            volume_python(OLD_IMAGE, volume, SEED)
            docker('start', names['old'])
            lan, gateway = ready(names['old'])
            # v1 only aggregates hot events. Establish its real eight-request
            # summary/checkpoint before moving four old details to archive,
            # matching a genuine retention cycle instead of an inconsistent DB.
            aggregate_count = "import sqlite3;c=sqlite3.connect('file:/data/app.db?mode=ro',uri=True);print(c.execute('SELECT COALESCE(SUM(request_count),0) FROM usage_overview_hourly_stats').fetchone()[0])"
            eventually(lambda: int(docker('exec', names['old'], 'python3', '-c', aggregate_count)) == 8)
            for role, url, secret in (
                ('viewer', gateway + VIEWER_PATH + '/api/v1/auth/read-only-login', readonly),
                ('direct', lan + '/api/v1/auth/read-only-login', readonly),
                ('admin', lan + '/api/v1/auth/login', password),
            ):
                assert request(url, FETCH, {'password': secret}, sessions[role])[0] == 204
            check_roles(lan, gateway, sessions, hidden)
            docker('stop', names['old'])
            volume_python(OLD_IMAGE, volume, r'''
import sqlite3
c = sqlite3.connect('/data/app.db')
assert c.execute('SELECT SUM(request_count) FROM usage_overview_hourly_stats').fetchone()[0] == 8
assert c.execute("SELECT last_aggregated_usage_event_id FROM usage_aggregation_checkpoints WHERE name='overview'").fetchone()[0] == 900204
c.execute('INSERT INTO usage_events_archive SELECT * FROM usage_events WHERE id < 900200')
c.execute('DELETE FROM usage_events WHERE id < 900200')
assert c.execute('SELECT count(*) FROM usage_events').fetchone()[0] == 4
assert c.execute('SELECT count(*) FROM usage_events_archive').fetchone()[0] == 4
c.commit()
''')
            before = json.loads(volume_python(OLD_IMAGE, volume, SNAPSHOT))
            assert len(before['ranking']) == 1 and before['ranking'][0][3] == 7
            assert len(before['sessions']) == 3 and sorted(r[1] for r in before['sessions']) == ['admin', 'read_only', 'read_only']
            # Copy the entire stopped work directory, including persistent
            # sessions/settings and options. Truncate the stopped WAL first.
            backup_hash = volume_python(OLD_IMAGE, volume, r'''
import hashlib, pathlib, shutil, sqlite3
source, target = pathlib.Path('/data'), pathlib.Path('/backup/preupgrade')
c = sqlite3.connect(source/'app.db'); c.execute('PRAGMA wal_checkpoint(TRUNCATE)'); c.close()
shutil.copytree(source, target)
assert (target/'app.db').read_bytes() == (source/'app.db').read_bytes()
print(hashlib.sha256((target/'app.db').read_bytes()).hexdigest())
''', backup)
            print('PASS: immutable packaged v1 fixture, hot/archive rule pricing, quota history, names/ranking and persisted read-only/admin sessions', flush=True)

            create('new', image)
            docker('start', names['new'])
            lan, gateway = ready(names['new'], migrated=True)
            start_policy(names['new'])
            assert_facts(snapshot(names['new']), before)
            stored = costs(names['new'])
            # Inspect the application's own protected pre-migration backup too.
            protected = docker('exec', names['new'], 'python3', '-c', r'''
import json, pathlib, sqlite3
c = sqlite3.connect('file:/data/app.db?mode=ro',uri=True)
path = c.execute('SELECT backup_path FROM pricing_migration_state WHERE id=1').fetchone()[0]
assert pathlib.Path(path).is_file()
b = sqlite3.connect('file:'+path+'?mode=ro',uri=True)
assert b.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
assert 'cost_usd' not in [r[1] for r in b.execute('PRAGMA table_info(usage_events)')]
assert b.execute('SELECT count(*) FROM usage_events').fetchone()[0] == 4
assert b.execute('SELECT count(*) FROM usage_events_archive').fetchone()[0] == 4
assert b.execute('SELECT count(*) FROM auth_sessions').fetchone()[0] == 3
assert b.execute('SELECT local_ranking_avatar_id FROM cpa_api_keys WHERE id=9001').fetchone()[0] == 17
print('ok')
''')
            assert protected == 'ok'
            weekly = check_roles(lan, gateway, sessions, hidden, migrated=True)
            models = json_response(lan + '/api/v1/pricing/models', sessions['admin'])
            config = next(row for row in models['models'] if row['model'] == MODEL)
            assert config['base_prices']['input'] == 1 and config['model_multiplier'] == 1
            assert config['conditional_multipliers'] == [{'key': 'upstream_service_tier', 'value': 'priority', 'multiplier': 2}]
            changed = copy.deepcopy(config)
            changed['base_prices']['input'] = 9
            status, _ = request(lan + '/api/v1/pricing/models', FETCH, changed, sessions['admin'], 'PUT')
            assert status == 200, 'Explicit pricing save failed'
            edited = json_response(lan + '/api/v1/pricing/models', sessions['admin'])
            assert edited['config_revision'] > models['config_revision']
            assert next(row for row in edited['models'] if row['model'] == MODEL)['base_prices']['input'] == 9
            assert costs(names['new']) == stored, 'Price edit repriced historical events without explicit recalculation'
            assert_facts(snapshot(names['new']), before)
            after_edit = check_roles(lan, gateway, sessions, hidden, migrated=True)
            assert [c['usage'] for c in after_edit['cycles']] == [c['usage'] for c in weekly['cycles']]
            print('PASS: v2 migration completes protected backup and hot/archive cost backfill, preserves unknown costs, tier rules, quota facts, names/ranking and session role isolation', flush=True)

            docker('stop', names['new'])
            docker('start', names['new'])
            lan, gateway = ready(names['new'], migrated=True)
            start_policy(names['new'])
            assert_facts(snapshot(names['new']), before)
            assert costs(names['new']) == stored, 'Reopen changed completed migration or historical prices'
            check_roles(lan, gateway, sessions, hidden, migrated=True)
            assert next(row for row in json_response(lan + '/api/v1/pricing/models', sessions['admin'])['models'] if row['model'] == MODEL)['base_prices']['input'] == 9
            docker('stop', names['new'])
            print('PASS: completed migration reopens idempotently; explicit price edits persist while historical stored/API costs remain unchanged', flush=True)

            # Rollback is restoration of the untouched preupgrade directory,
            # never opening the migrated database with the old executable.
            restored_hash = volume_python(OLD_IMAGE, volume, r'''
import hashlib, pathlib, shutil
target, source = pathlib.Path('/data'), pathlib.Path('/backup/preupgrade')
assert target == pathlib.Path('/data') and source.is_dir()
for item in target.iterdir():
    if item.is_dir() and not item.is_symlink(): shutil.rmtree(item)
    else: item.unlink()
shutil.copytree(source,target,dirs_exist_ok=True)
print(hashlib.sha256((target/'app.db').read_bytes()).hexdigest())
''', backup)
            assert restored_hash == backup_hash, 'Rollback did not restore exact preupgrade database bytes'
            restored = json.loads(volume_python(OLD_IMAGE, volume, SNAPSHOT))
            assert_facts(restored, before)
            assert volume_python(OLD_IMAGE, volume, "import sqlite3;c=sqlite3.connect('file:/data/app.db?mode=ro',uri=True);assert 'cost_usd' not in [r[1] for r in c.execute('PRAGMA table_info(usage_events)')];assert c.execute('SELECT prompt_price_per1_m FROM model_price_settings WHERE id=9001').fetchone()[0]==1;print('ok')") == 'ok'
            create('rollback', OLD_IMAGE)
            docker('start', names['rollback'])
            lan, gateway = ready(names['rollback'])
            assert_facts(snapshot(names['rollback']), before)
            check_roles(lan, gateway, sessions, hidden)
            print('PASS: exact preupgrade backup restored to packaged v1, original prices/facts and persistent sessions work, privileged writes remain denied', flush=True)
        except Exception:
            failure_diagnostics(names, hidden)
            raise
        finally:
            for name in names.values():
                docker('rm', '-f', name, check=False)
            for item in (volume, backup):
                docker('volume', 'rm', item, check=False)
            docker('network', 'rm', network, check=False)


if __name__ == '__main__':
    main()
