import copy,json
import pytest
from order_controller import Controller,Halt,PAPER

class Broker:
    endpoint=PAPER
    def __init__(self):self.orders={};self.posts=0;self.timeout=False;self.offline=False;self.cancel_race=False
    def observe(self):
        return {'account':'test','cash':'1000','equity':'1000','positions':[],
                'orders':[o for o in self.orders.values() if o['status'] not in ('canceled','filled')],
                'activities':[], 'blocked':False}
    def submit(self,cid,intent):
        self.posts+=1
        self.orders[cid]={**intent,'client_order_id':cid,'status':'new','filled_qty':0}
        if self.timeout:raise TimeoutError()
        return dict(self.orders[cid])
    def lookup(self,cid):
        if self.offline:raise ConnectionError()
        return copy.deepcopy(self.orders.get(cid))
    def cancel(self,cid):
        self.orders[cid]['status']='filled' if self.cancel_race else 'canceled'
        if self.cancel_race:self.orders[cid]['filled_qty']=1

def intent():return {'decision_id':'2026-10-16-probe','symbol':'SPY','side':'buy','qty':1,'limit_price':1.0}
def submit(c,i=None,**kw):return c.submit(i or intent(),**({'now':100,'quote_time':99,'market_open':True,'cash':1000}|kw))

@pytest.fixture
def setup(tmp_path):
    b=Broker();b.account_lock_dir=tmp_path/'locks';c=Controller(tmp_path/'state.json',b)
    c.checkpoint()
    yield c,b,tmp_path
    c.close()

def test_accepted_but_response_lost_recovers_without_duplicate(setup):
    c,b,p=setup;b.timeout=True
    with pytest.raises(Halt):submit(c)
    c.close();new=Controller(p/'state.json',b)
    try:
        assert submit(new)['status']=='new'
        assert b.posts==1
    finally:new.close()

def test_unknown_absent_does_not_retry(setup):
    c,b,p=setup;b.timeout=True
    with pytest.raises(Halt):submit(c)
    b.orders.clear()
    with pytest.raises(Halt,match='do not resubmit'):submit(c)
    assert b.posts==1

def test_partial_fill_duplicate_and_cancel_preserves_quantity(setup):
    c,b,p=setup;r=submit(c);cid=r['client_order_id']
    b.orders[cid].update(status='partially_filled',filled_qty=.4)
    assert c.recover(intent()['decision_id'])['filled_qty']==.4
    assert c.recover(intent()['decision_id'])['filled_qty']==.4
    r=c.cancel(intent()['decision_id']);assert r['status']=='canceled' and r['filled_qty']==.4
    assert b.posts==1

def test_fill_wins_cancel_race(setup):
    c,b,p=setup;submit(c);b.cancel_race=True
    assert c.cancel(intent()['decision_id'])['status']=='filled'
    assert c.cancel(intent()['decision_id'])['filled_qty']==1

def test_disconnect_does_not_overwrite_known_state(setup):
    c,b,p=setup;submit(c);before=(p/'state.json').read_bytes();b.offline=True
    with pytest.raises(ConnectionError):c.recover(intent()['decision_id'])
    assert (p/'state.json').read_bytes()==before
    assert b.posts==1

@pytest.mark.parametrize('kw',[{'quote_time':0},{'quote_time':101},{'market_open':False},{'cash':0}])
def test_preflight_blocks_without_post(setup,kw):
    c,b,p=setup
    with pytest.raises(Halt):submit(c,**kw)
    assert b.posts==0

def test_lock_blocks_second_writer(setup):
    c,b,p=setup
    with pytest.raises(Halt,match='Another'):Controller(p/'state.json',b)

def test_stop_blocks_new_orders_allows_cancel(setup):
    c,b,p=setup;submit(c);(p/'STOP').touch()
    with pytest.raises(Halt):submit(c,intent()|{'decision_id':'next'})
    assert c.cancel(intent()['decision_id'])['status']=='canceled'

def test_unresolved_intent_blocks_next_decision(setup):
    c,b,p=setup;submit(c)
    with pytest.raises(Halt):submit(c,intent()|{'decision_id':'next'})
    assert b.posts==1

def test_changed_intent_rejected(setup):
    c,b,p=setup;submit(c)
    with pytest.raises(Halt):submit(c,intent()|{'limit_price':2})
    assert b.posts==1

@pytest.mark.parametrize('change',[{'filled_qty':-1},{'filled_qty':2},{'symbol':'BIL'},
                                   {'status':'unknown_vendor_status'},{'status':'filled','filled_qty':.5}])
def test_inconsistent_broker_snapshot_stops(setup,change):
    c,b,p=setup;r=submit(c);b.orders[r['client_order_id']].update(change)
    with pytest.raises(Halt):c.recover(intent()['decision_id'])

def test_cumulative_quantity_cannot_regress(setup):
    c,b,p=setup;r=submit(c);o=b.orders[r['client_order_id']];o.update(status='partially_filled',filled_qty=.5)
    c.recover(intent()['decision_id']);o['filled_qty']=.3
    with pytest.raises(Halt):c.recover(intent()['decision_id'])

def test_reject_live_endpoint(tmp_path):
    b=Broker();b.endpoint='https://api.alpaca.markets'
    with pytest.raises(Halt):Controller(tmp_path/'state.json',b)

def test_corrupt_journal_does_not_reset(tmp_path):
    p=tmp_path/'state.json';p.write_text('{truncated')
    with pytest.raises(ValueError):Controller(p,Broker())
    assert p.read_text()=='{truncated'

def test_cancel_response_lost_then_restart_preserves_partial_fill(setup):
    c,b,p=setup;r=submit(c);cid=r['client_order_id'];key=intent()['decision_id']
    b.orders[cid].update(status='partially_filled',filled_qty=.4)
    c.recover(key)
    cancel_calls=[]
    def cancel_then_timeout(client_id):
        cancel_calls.append(client_id)
        b.orders[client_id]['status']='canceled'
        raise TimeoutError('Simulated lost cancellation response')
    b.cancel=cancel_then_timeout
    with pytest.raises(TimeoutError):c.cancel(key)
    c.close();restarted=Controller(p/'state.json',b)
    try:
        result=restarted.cancel(key)
        assert result['status']=='canceled' and result['filled_qty']==.4
        assert cancel_calls==[cid] and b.posts==1
    finally:restarted.close()

def test_intent_persistence_failure_prevents_submission(setup,monkeypatch):
    c,b,p=setup
    original_save=c.save
    def fail_when_intent_added():
        if c.state['intents']:
            raise OSError('Simulated storage failure')
        original_save()
    monkeypatch.setattr(c,'save',fail_when_intent_added)
    with pytest.raises(OSError):submit(c)
    assert b.posts==0
    assert json.loads((p/'state.json').read_text())['intents']=={}
