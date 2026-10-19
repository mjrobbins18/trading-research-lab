import json,subprocess,sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo
import pytest
from timed_observer import Run,calendar_manifest,check_manifest,plan_digest
ET=ZoneInfo('America/New_York')
def at(day,hm):return int(datetime.fromisoformat(f'{day}T{hm}').replace(tzinfo=ET).timestamp())
OPEN,CLOSE=at('2026-10-20','09:30'),at('2026-10-20','16:00')
LIVE=dict(open_at=OPEN,close_at=CLOSE,cadence_seconds=60,enabled=True,calendar_verified=True,boundary_samples=True)
ENTRY=dict(date='2026-10-20',open='09:30',close='16:00')
B=dict(open_at=1000,close_at=1180,cadence_seconds=60,enabled=False,calendar_verified=False,boundary_samples=True)
def good(timeout):
 return SimpleNamespace(returncode=0,stdout=json.dumps(dict(status='observed',orders_submitted=0,market={s:dict(feed='sip',market_open=True,quote_age_seconds=1) for s in ('SPY','BIL')})))
@pytest.fixture
def run(tmp_path):
 r=Run(tmp_path/'run.sqlite',B);yield r;r.close()

def test_manifest_matches_broker_calendar():
 m=calendar_manifest(LIVE,ENTRY)
 assert m['plan_sha256']==plan_digest(LIVE) and m['session_date']=='2026-10-20'
 assert m['launch_not_before']==OPEN-300 and m['launch_not_after']==CLOSE+120
 assert m['alert_delivery']=='outbox_only' and m['orders_authorized'] is False
 check_manifest(LIVE,m)
@pytest.mark.parametrize('entry',[ENTRY|{'close':'13:00'},ENTRY|{'open':'09:31'},ENTRY|{'date':'2026-10-21'},{'date':'2026-10-20'}])
def test_manifest_rejects_calendar_mismatch(entry):
 with pytest.raises((ValueError,KeyError)):calendar_manifest(LIVE,entry)
def test_manifest_rejects_changed_plan_or_tampering():
 m=calendar_manifest(LIVE,ENTRY)
 with pytest.raises(ValueError):check_manifest(LIVE|{'close_at':CLOSE+60},m)
 with pytest.raises(ValueError):check_manifest(LIVE,m|{'verified_against_calendar':False})
 with pytest.raises(ValueError):check_manifest(LIVE,m|{'launch_not_after':CLOSE+3600})
def test_early_close_session_is_supported():
 plan=LIVE|{'close_at':at('2026-11-27','13:00'),'open_at':at('2026-11-27','09:30')}
 assert calendar_manifest(plan,dict(date='2026-11-27',open='09:30',close='13:00'))['close_at']==plan['close_at']

def test_boundary_samples_once_each_and_unscored(run):
 assert run.tick(699,lambda t:pytest.fail('too early'))=='outside_session'
 pre=run.tick(701,good,lambda:705)
 assert pre['phase']=='pre_open' and pre['status']=='observed' and pre['decision_eligible'] is False
 assert run.tick(900,lambda t:pytest.fail('repeat'))=='already_attempted'
 assert run.tick(1180,good,lambda:1185)['phase']=='post_close'
 assert run.tick(1250,lambda t:pytest.fail('repeat'))=='already_attempted'
 assert run.tick(1300,lambda t:pytest.fail('late'))=='outside_session'
 r=run.report(1400)
 assert r['due_slots']==3 and r['statuses']=={'missing':3} and r['outside_grid_rows']==0
 assert r['boundary_samples']['pre_open']['status']=='observed' and r['boundary_samples']['post_close']['status']=='observed'
def test_missing_boundary_sample_reported(run):
 run.tick(1001,good,lambda:1005)
 assert run.report(1400)['boundary_samples']=={'pre_open':'missing','post_close':'missing'}
def test_boundary_samples_off_by_default(tmp_path):
 r=Run(tmp_path/'x.sqlite',B|{'boundary_samples':False})
 try:
  assert r.tick(701,lambda t:pytest.fail('pre'))=='outside_session'
  assert 'boundary_samples' not in r.report(1400)
 finally:r.close()
def test_boundary_fault_is_durable(run):
 def fail(t):raise ConnectionError()
 assert run.tick(701,fail,lambda:702)['status']=='halted'
 assert run.report(1400)['boundary_samples']['pre_open']['error_type']=='ConnectionError'

def test_outbox_claims_each_alert_once(run):
 run.watchdog(1121);run.tick(1122,good,lambda:1123)
 a=run.claim_alert(2000)
 assert a['kind']=='missing_observation' and 'No trade was placed' in a['body'] and f"#{a['alert_id']}" in a['subject']
 other=Run(run.path,B)
 try:assert other.claim_alert(2001) is None
 finally:other.close()
 assert run.outbox()[0]['outcome']=='claimed_unrecorded'
 run.record_alert(a['alert_id'],'accepted','msg-1',2002)
 assert run.outbox()[0]|{'created':0}=={'alert_id':a['alert_id'],'kind':'missing_observation','created':0,'subject':a['subject'],'outcome':'accepted','message_id':'msg-1'}
 assert run.db.execute('SELECT delivered FROM alerts').fetchone()[0]==1
def test_outbox_error_is_never_reclaimed(run):
 run.watchdog(1121)
 a=run.claim_alert(2000);run.record_alert(a['alert_id'],'error',None,2001)
 assert run.claim_alert(2002) is None and run.outbox()[0]['outcome']=='error'
 with pytest.raises(ValueError):run.record_alert(a['alert_id'],'accepted','m',2003)
def test_outbox_rejects_unclaimed_and_bad_outcomes(run):
 run.watchdog(1121)
 with pytest.raises(ValueError):run.record_alert(1,'accepted','m',2000)
 a=run.claim_alert(2000)
 with pytest.raises(ValueError):run.record_alert(a['alert_id'],'delivered',None,2001)
 with pytest.raises(ValueError):run.record_alert(a['alert_id'],'accepted',None,2001)
def test_outbox_fifo(run):
 run.watchdog(1121);run.tick(1122,lambda t:(_ for _ in ()).throw(ValueError()),lambda:1123);run.watchdog(1124)
 kinds=[run.claim_alert(2000+i)['kind'] for i in range(2)]
 assert kinds==['missing_observation','review_required'] and run.claim_alert(2003) is None

def cli(*args):return subprocess.run([sys.executable,str(Path(__file__).with_name('timed_observer.py')),*map(str,args)],capture_output=True,text=True)
def test_cli_live_role_requires_matching_manifest(tmp_path):
 plan=tmp_path/'plan.json';plan.write_text(json.dumps(LIVE))
 r=cli('worker','--plan',plan,'--state',tmp_path/'s.sqlite')
 assert r.returncode!=0 and 'manifest' in r.stderr
 bad=tmp_path/'m.json';bad.write_text(json.dumps(calendar_manifest(LIVE,ENTRY)|{'plan_sha256':'0'*64}))
 r=cli('watchdog','--plan',plan,'--state',tmp_path/'s.sqlite','--manifest',bad)
 assert r.returncode!=0 and not (tmp_path/'s.sqlite').exists()
def test_cli_manifest_role_is_offline_and_writes_nothing(tmp_path):
 plan=tmp_path/'plan.json';plan.write_text(json.dumps(LIVE));cal=tmp_path/'cal.json';cal.write_text(json.dumps([ENTRY]))
 r=cli('manifest','--plan',plan,'--state',tmp_path/'s.sqlite','--calendar',cal)
 assert r.returncode==0 and json.loads(r.stdout)['plan_sha256']==plan_digest(LIVE)
 assert not (tmp_path/'s.sqlite').exists()
def test_cli_alert_drain(tmp_path):
 plan=tmp_path/'plan.json';plan.write_text(json.dumps(B));state=tmp_path/'s.sqlite'
 r=Run(state,B);r.watchdog(1121);r.close()
 a=json.loads(cli('alerts','--plan',plan,'--state',state,'--claim').stdout)
 assert a['kind']=='missing_observation'
 assert json.loads(cli('alerts','--plan',plan,'--state',state,'--claim').stdout) is None
 assert cli('alerts','--plan',plan,'--state',state,'--record',a['alert_id'],'--outcome','accepted','--message-id','m1').returncode==0
 assert json.loads(cli('alerts','--plan',plan,'--state',state).stdout)[0]['outcome']=='accepted'

@pytest.fixture(autouse=True)
def no_network(monkeypatch):
 import socket
 def fail(*a,**kw):raise AssertionError('Network forbidden in offline tests')
 monkeypatch.setattr(socket.socket,'connect',fail)
 monkeypatch.setattr(socket,'create_connection',fail)
