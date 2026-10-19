"""Combined controller/observer rehearsal with isolated journals and blocked sockets."""
import json
import socket
import pytest
import requests
from order_controller import Controller
from observer_service import Store,ReadFailure,ReadOnlyTransport
from observation_rehearsal import Rehearsal
from test_reduce_only_sell import FillBroker

@pytest.fixture
def lab(tmp_path,monkeypatch):
    def forbidden(*a,**kw):raise AssertionError('Network or order operation forbidden')
    monkeypatch.setattr(socket.socket,'connect',forbidden)
    monkeypatch.setattr(socket,'create_connection',forbidden)
    b=FillBroker(tmp_path);b.submit=forbidden;b.cancel=forbidden
    b.market_inputs=lambda s:dict(now=100,quote_time=99,market_open=True,feed='sip')
    c=Controller(tmp_path/'journal.json',b);c.checkpoint()
    store=Store(tmp_path/'state.sqlite');r=Rehearsal(store)
    yield r,c,b,store,tmp_path
    c.close();store.db.close()

def tick(r,c,t=100):return r.tick(c,t,t,t+1)
def alerts(s):return s.db.execute('SELECT id,payload,delivered,attempts FROM alerts ORDER BY id').fetchall()

def test_healthy_and_restart_requires_new_observation(lab):
    r,c,b,s,p=lab
    assert tick(r,c)['eligible']
    c.close();s.db.close()
    c=Controller(p/'journal.json',b);s=Store(p/'state.sqlite');r=Rehearsal(s)
    try:
        assert r.watchdog(110)['reason']=='restart_requires_observation'
        assert tick(r,c,160)['eligible']
        assert b.posts==0
    finally:c.close();s.db.close()

@pytest.mark.parametrize('change,reason',[
    ({'quote_time':0},'ineligible_quote'),({'quote_time':101},'ineligible_quote'),
    ({'market_open':False},'market_closed'),({'feed':'iex'},'wrong_feed')])
def test_quote_fault_recovery_deduplicates_alerts(lab,change,reason):
    r,c,b,s,p=lab;assert tick(r,c)['eligible']
    base=b.market_inputs('BIL');b.market_inputs=lambda symbol:base|change
    assert tick(r,c,160)['reason']==reason
    count=len(alerts(s));assert tick(r,c,220)['reason']==reason and len(alerts(s))==count
    b.market_inputs=lambda symbol:base
    assert tick(r,c,280)['eligible'] and len(alerts(s))>count

def test_integrity_failure_stays_latched_after_restart(lab):
    r,c,b,s,p=lab;tick(r,c);before=(p/'journal.json').read_bytes();b.cash+=10
    assert tick(r,c,160)['reason']=='integrity_review_required'
    assert (p/'journal.json').read_bytes()==before
    b.cash-=10;r=Rehearsal(s)
    assert tick(r,c,220)['reason']=='integrity_review_required'
    assert not r.watchdog(230)['eligible']

def test_missing_cycles_and_slow_completion(lab):
    r,c,b,s,p=lab;tick(r,c)
    assert r.watchdog(221)['reason']=='watchdog_only_no_decision'
    assert r.watchdog(222)['reason']=='missing_observation'
    count=len(alerts(s));r.watchdog(223);assert len(alerts(s))==count
    assert r.tick(c,160,280,281)['reason']=='missed_deadline'
    assert tick(r,c,340)['eligible']

@pytest.mark.parametrize('times',[(100,99,101),(100,101,100),(100,100,101)])
def test_bad_or_duplicate_clock_cannot_decide(lab,times):
    r,c,b,s,p=lab;tick(r,c)
    assert r.tick(c,*times)['reason']=='invalid_clock'

@pytest.mark.parametrize('value',[float('nan'),float('inf'),True])
def test_nonfinite_time_rejected(lab,value):
    r,c,b,s,p=lab
    with pytest.raises(ValueError):r.tick(c,value,100,101)
    with pytest.raises(ValueError):r.watchdog(value)

def test_stop_withholds_without_orders(lab):
    r,c,b,s,p=lab;(p/'STOP').touch()
    assert tick(r,c)['reason']=='stop_file' and b.posts==0

def test_transport_retry_exhaustion_then_fresh_recovery(lab):
    r,c,b,s,p=lab;clock=[0];calls=[]
    class Session:
        def request(self,*a,**kw):calls.append(1);raise requests.Timeout()
    transport=ReadOnlyTransport(Session(),s,now=lambda:clock[0],sleep=lambda x:clock.__setitem__(0,clock[0]+x))
    base=b.market_inputs
    b.market_inputs=lambda symbol:transport.get('https://data.alpaca.markets/v2/stocks/quotes/latest')
    assert tick(r,c)['reason']=='observation_failed' and len(calls)==3
    b.market_inputs=base;assert tick(r,c,160)['eligible']

def test_failed_notification_stays_pending_simulated_ack_clears(lab):
    r,c,b,s,p=lab;r.watchdog(100)
    def failed(*args):raise RuntimeError('simulated destination unavailable')
    assert s.deliver(failed)==1
    assert alerts(s)[0][2:]==(0,1)
    receipts=[]
    assert s.deliver(lambda identity,payload:receipts.append(identity))==0
    assert receipts==['1'] and alerts(s)[0][2:]==(1,2)
    assert all(json.loads(x[1])['orders_submitted']==0 for x in alerts(s))

def test_delivery_failure_blocks_until_simulated_receipt(lab):
    r,c,b,s,p=lab;r.watchdog(90)
    def failed(*args):raise TimeoutError()
    s.deliver(failed)
    assert tick(r,c)['reason']=='notification_failed'
    s.deliver(lambda identity,payload:None,limit=100)
    assert tick(r,c,160)['eligible']

def test_sqlite_failure_cannot_return_eligible(lab):
    r,c,b,s,p=lab
    s.db.execute("CREATE TRIGGER reject_decision BEFORE INSERT ON decisions BEGIN SELECT RAISE(ABORT,'injected'); END")
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError):tick(r,c)
    assert s.db.execute('SELECT count(*) FROM decisions').fetchone()[0]==0
    assert b.posts==0

def test_watchdog_can_run_without_worker(lab):
    r,c,b,s,p=lab;tick(r,c)
    independent=Store(p/'state.sqlite');watch=Rehearsal(independent)
    try:
        assert watch.watchdog(300)['reason']=='missing_observation'
        assert independent.db.execute('SELECT count(*) FROM alerts WHERE delivered=0').fetchone()[0]>0
    finally:independent.db.close()
