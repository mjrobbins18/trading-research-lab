"""Sell-path safety and recovery using a simulated broker; no network calls."""
import copy
import pytest
from order_controller import Controller, Halt, PAPER
from account_guard import permit, ReconciliationError

class FillBroker:
    endpoint = PAPER
    def __init__(self, tmp_path):
        self.account_lock_dir = tmp_path/'locks'
        self.orders = {}
        self.activities = []
        self.cash = 1000
        self.qty = 0
        self.posts = 0
        self.lose_response = False
    def observe(self):
        return dict(account='sell-test', cash=str(self.cash), equity=str(self.cash+self.qty*100),
                    blocked=False, positions=[dict(symbol='BIL',qty=str(self.qty),market_value=str(self.qty*100))] if self.qty else [],
                    orders=[copy.deepcopy(o) for o in self.orders.values() if o['status'] not in ('filled','canceled')],
                    activities=copy.deepcopy(self.activities))
    def submit(self,cid,intent):
        self.posts += 1
        self.orders[cid] = dict(intent,client_order_id=cid,order_id=cid,status='new',filled_qty=0)
        if self.lose_response:raise TimeoutError()
        return copy.deepcopy(self.orders[cid])
    def lookup(self,cid):return copy.deepcopy(self.orders.get(cid))
    def cancel(self,cid):self.orders[cid]['status']='canceled'
    def fill(self,cid,qty,price):
        o=self.orders[cid]
        o['filled_qty']+=qty
        o['status']='filled' if o['filled_qty']==o['qty'] else 'partially_filled'
        signed=qty if o['side']=='buy' else -qty
        self.cash-=signed*price;self.qty+=signed
        self.activities.append(dict(id=str(len(self.activities)),activity_type='FILL',order_id=cid,
                                    symbol='BIL',side=o['side'],qty=str(qty),price=str(price)))

def order(side='sell',**changes):
    return dict(decision_id=side,symbol='BIL',side=side,qty=1,limit_price=99.0,reduce_only=True)|changes

def send(c,i):return c.submit(i,100,99,True,0 if i['side']=='sell' else 1000)

@pytest.fixture
def held(tmp_path):
    b=FillBroker(tmp_path);p=tmp_path/'journal.json';c=Controller(p,b);c.checkpoint()
    r=send(c,order('buy',limit_price=101.0));b.fill(r['client_order_id'],1,100)
    c.recover('buy');c.reconcile_account()
    yield c,b,p
    c.close()

def test_sell_partial_cancel_restart_and_no_duplicate(held):
    c,b,p=held;r=send(c,order());b.fill(r['client_order_id'],.5,100)
    c.recover('sell');c.reconcile_account()
    assert c.state['account_guard']['positions']=={'BIL':'0.5'}
    assert c.cancel('sell')['filled_qty']==.5
    c.close();c=Controller(p,b)
    try:
        before=copy.deepcopy(c.state['account_guard'])
        assert send(c,order())['status']=='canceled'
        c.reconcile_account();assert c.state['account_guard']==before
        assert b.posts==2
    finally:c.close()

def test_full_sell_recovers_after_lost_response(held):
    c,b,p=held;b.lose_response=True
    with pytest.raises(Halt,match='unknown'):send(c,order())
    cid=c.state['intents']['sell']['client_order_id'];b.fill(cid,1,100)
    c.close();c=Controller(p,b)
    try:
        assert send(c,order())['status']=='filled'
        c.reconcile_account();before=copy.deepcopy(c.state['account_guard'])
        send(c,order());c.reconcile_account()
        assert c.state['account_guard']==before
        assert before['positions']=={} and float(before['cash'])==1000
        assert b.posts==2
        with pytest.raises(Halt,match='long position'):send(c,order(decision_id='second-sell'))
        assert b.posts==2
    finally:c.close()

@pytest.mark.parametrize('change',[{'reduce_only':False},{'reduce_only':1},{'symbol':'SPY'}, {'qty':2},{'qty':True},{'side':'short'}])
def test_sell_preflight_blocks(held,change):
    c,b,p=held
    with pytest.raises(Halt):send(c,order(**change))
    assert b.posts==1

@pytest.mark.parametrize('price',[98,99,100])
def test_sell_limit_is_price_floor(held,price):
    c,b,p=held;r=send(c,order());b.fill(r['client_order_id'],1,price);c.recover('sell')
    if price<99:
        before=copy.deepcopy(c.state['account_guard'])
        with pytest.raises(Halt,match='limit intent'):c.reconcile_account()
        assert c.state['account_guard']==before
    else:
        c.reconcile_account();assert c.state['account_guard']['positions']=={}

@pytest.mark.parametrize('mode',['stop','stale','future','closed','open_order','budget','loss','short','external_cash'])
def test_sell_retains_other_gates(held,mode):
    c,b,p=held
    if mode=='stop':(p.parent/'STOP').touch()
    if mode=='open_order':b.orders['external']=dict(status='new')
    if mode=='budget':c.state['intents']['buy']['intent']['limit_price']=950
    if mode=='loss':c.state['account_guard']['initial_equity']='1100'
    if mode=='short':b.qty=-1
    if mode=='external_cash':b.cash+=10
    kwargs=dict(now=100,quote_time=99,market_open=True,cash=900)
    if mode=='stale':kwargs['quote_time']=0
    if mode=='future':kwargs['quote_time']=101
    if mode=='closed':kwargs['market_open']=False
    with pytest.raises(Halt):c.submit(order(),**kwargs)
    assert b.posts==1

def test_sell_fresh_input_gate(held):
    c,b,p=held
    b.market_inputs=lambda symbol:dict(market_open=True,now=100,quote_time=101)
    with pytest.raises(Halt,match='Fresh broker'):send(c,order())
    assert b.posts==1

def test_sell_does_not_replenish_budget(held):
    c,b,p=held;r=send(c,order());b.fill(r['client_order_id'],1,100);c.recover('sell');c.reconcile_account()
    assert sum(r['intent']['qty']*r['intent']['limit_price'] for r in c.state['intents'].values())==200
    with pytest.raises(Halt,match='Cumulative'):send(c,order('buy',decision_id='next',limit_price=801))
    assert b.posts==2
