import json,subprocess,multiprocessing
from types import SimpleNamespace
import pytest
from timed_observer import Run
P=dict(open_at=1000,close_at=1180,cadence_seconds=60,enabled=False,calendar_verified=False)
def good(timeout):
 assert timeout==45
 return SimpleNamespace(returncode=0,stdout=json.dumps(dict(status='observed',orders_submitted=0,market={s:dict(feed='sip',market_open=True,quote_age_seconds=1) for s in ('SPY','BIL')})))
@pytest.fixture
def run(tmp_path):
 r=Run(tmp_path/'run.sqlite',P);yield r;r.close()
def test_once_per_slot_across_restart(run):
 assert run.tick(1001,good,lambda:1005)['status']=='observed'
 other=Run(run.path,P)
 try:assert other.tick(1006,lambda t:pytest.fail('repeat'))=='already_attempted'
 finally:other.close()
def test_missed_slots_not_backfilled(run):
 run.tick(1121,good,lambda:1125)
 assert run.watchdog(1240)['missing_slots']==[1000,1060]
 assert run.report(1300)['statuses']['missing']==2
@pytest.mark.parametrize('error',[subprocess.TimeoutExpired('child',45),ConnectionError(),ValueError()])
def test_worker_fault_is_durable_and_latched(run,error):
 def fail(t):raise error
 assert run.tick(1001,fail,lambda:1046)['status']=='halted'
 assert run.watchdog(1050)['status']=='review_required'
 run.tick(1061,good,lambda:1065)
 assert run.watchdog(1070)['status']=='review_required'
def test_independent_watchdog_and_alert_dedupe(run):
 other=Run(run.path,P)
 try:
  assert other.watchdog(1121)['status']=='missing_observation'
  other.watchdog(1122)
  assert other.db.execute('SELECT count(*) FROM alerts').fetchone()[0]==1
  run.tick(1123,good,lambda:1125)
  assert other.watchdog(1126)['status']=='missing_observation' # historical missed slot remains
 finally:other.close()
def test_outside_session_no_child(run):
 assert run.tick(999,lambda t:pytest.fail('early'))=='outside_session'
 assert run.tick(1180,lambda t:pytest.fail('late'))=='outside_session'
def test_complete_report(run):
 for t in (1000,1060,1120):run.tick(t+1,good,lambda:t+5)
 assert run.watchdog(1300)['status']=='session_complete'
 assert run.report(1300)['observation_gate_passed']
def test_changed_plan_rejected(run):
 with pytest.raises(ValueError):Run(run.path,P|{'close_at':1240})
def crash_child(path):
 import os
 r=Run(path,P)
 r.tick(1001,lambda timeout:os._exit(73))
def test_real_process_death_does_not_repeat_slot(run):
 ctx=multiprocessing.get_context('fork');p=ctx.Process(target=crash_child,args=(run.path,));p.start();p.join(5)
 assert p.exitcode==73
 assert run.tick(1002,lambda t:pytest.fail('replayed'))=='already_attempted'
 assert run.watchdog(1121)['status']=='missing_observation'
def test_clock_regression_blocked_by_watchdog(run):
 run.tick(1001,good,lambda:1000)
 assert run.watchdog(1010)['status']=='clock_failure'
def test_worker_lock_blocks_concurrent_invocation(run):
 import fcntl
 from pathlib import Path
 with Path(str(run.path)+'.worker.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  assert run.tick(1001,lambda t:pytest.fail('concurrent'))=='worker_busy'

def test_real_child_timeout(run):
 import sys
 def timeout_child(timeout):
  return subprocess.run([sys.executable,'-c','import time; time.sleep(10)'],capture_output=True,text=True,timeout=.05)
 result=run.tick(1001,timeout_child,lambda:1002)
 assert result['error_type']=='TimeoutExpired'
 assert run.watchdog(1003)['status']=='review_required'

def test_disabled_cli_cannot_launch(tmp_path):
 import sys
 from pathlib import Path
 plan=tmp_path/'plan.json';plan.write_text(json.dumps(P))
 result=subprocess.run([sys.executable,str(Path(__file__).with_name('timed_observer.py')),'worker','--plan',str(plan),'--state',str(tmp_path/'state.sqlite')],capture_output=True,text=True)
 assert result.returncode!=0 and 'Disabled' in result.stderr
 assert not (tmp_path/'state.sqlite').exists()

@pytest.fixture(autouse=True)
def no_network(monkeypatch):
 import socket
 def fail(*a,**kw):raise AssertionError('Network forbidden in offline tests')
 monkeypatch.setattr(socket.socket,'connect',fail)
 monkeypatch.setattr(socket,'create_connection',fail)
