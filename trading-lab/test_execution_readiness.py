"""Integrated offline scenarios: actual Controller/runner, simulated broker only."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import pytest
from execution_simulator import SimulatedBroker, D
from order_controller import Controller, Halt
from supervised_runner import cycle


def order(key='first', limit=101):
    return dict(decision_id=key, symbol='SPY', side='buy', qty=1, limit_price=limit)


def send(c, intent=None):
    return c.submit(intent or order(), now=100, quote_time=99, market_open=True, cash=1000)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*a, **k): raise AssertionError('Network forbidden in offline tests')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(socket.socket, 'connect_ex', forbidden)


@pytest.fixture
def lab(tmp_path):
    b=SimulatedBroker(tmp_path);c=Controller(tmp_path/'journal.json', b);c.checkpoint()
    yield c,b,tmp_path
    c.close()


def test_gap_above_limit_leaves_order_unfilled(lab):
    c,b,p=lab;r=send(c)
    assert b.liquidity(r['client_order_id'], 105, 10) == 0
    result=cycle(c)
    assert result['cash']=='1000' and result['positions']==0 and result['open_orders']==1
    assert c.state['intents']['first']['filled_qty']==0


@pytest.mark.parametrize('ask,bps,filled,cash', [(99,0,1,'901'),(100,50,1,'899.500'),(100,200,0,'1000')])
def test_slippage_price_improvement_and_limit(lab,ask,bps,filled,cash):
    c,b,p=lab;r=send(c)
    assert b.liquidity(r['client_order_id'],ask,1,bps)==filled
    cycle(c)
    assert D(c.state['account_guard']['cash'])==D(cash)
    assert c.state['intents']['first']['filled_qty']==filled


def test_partial_fills_restart_duplicate_observation_cancel(lab):
    c,b,p=lab;r=send(c);cid=r['client_order_id']
    b.liquidity(cid,100,'.4');cycle(c)
    c.close();c=Controller(p/'journal.json',SimulatedBroker(p))
    try:
        before=c.state['account_guard'].copy();cycle(c)
        assert c.state['account_guard']==before
        c.broker.liquidity(cid,101,'.2');cycle(c)
        c.cancel('first');cycle(c)
        assert c.state['intents']['first']['filled_qty']==.6
        assert D(c.state['account_guard']['cash'])==D('939.8')
        assert c.state['account_guard']['positions']=={'SPY':'0.6'}
        assert c.broker.liquidity(cid,99,1)==0
        assert c.broker.posts==1
    finally:c.close()


def test_insufficient_reconciled_cash_blocks_despite_caller_cash(tmp_path):
    b=SimulatedBroker(tmp_path,cash='50');c=Controller(tmp_path/'journal.json',b);c.checkpoint()
    try:
        with pytest.raises(Halt,match='cash'):send(c)
        assert b.posts==0
    finally:c.close()


def test_rejection_does_not_create_cash_or_position(lab):
    c,b,p=lab
    original=b.submit
    def depleted(cid,i):
        # Broker-side availability changed after preflight; no imaginary fill.
        b.state['cash']='0'
        return original(cid,i)
    b.submit=depleted
    assert send(c)['status']=='rejected'
    assert b.state['positions']=={} and b.state['activities']==[]
    with pytest.raises(Halt,match='reconciliation'):cycle(c)


def test_timeout_hidden_order_then_visible_recovers_once(lab):
    c,b,p=lab;b.lose_response=True
    with pytest.raises(Halt,match='unknown'):send(c)
    b.hidden=True
    with pytest.raises(Halt,match='do not resubmit'):send(c)
    b.hidden=False
    assert send(c)['status']=='new' and b.posts==1


@pytest.mark.parametrize('phase,posts',[('before_post',0),('after_accept',1)])
def test_process_death_retains_intent_without_resubmission(tmp_path,phase,posts):
    # A child dies via os._exit, without cleanup or controller.close().
    script='''
import os,socket,sys
from pathlib import Path
from execution_simulator import SimulatedBroker
from order_controller import Controller
socket.socket.connect=lambda *a,**k: (_ for _ in ()).throw(AssertionError('Network forbidden'))
p=Path(sys.argv[1]);b=SimulatedBroker(p);c=Controller(p/'journal.json',b);c.checkpoint()
if sys.argv[2]=='before_post':
 old=c.save
 def die():
  old()
  if c.state['intents']:os._exit(73)
 c.save=die
else:
 old=b.submit
 def die(cid,i):
  old(cid,i);os._exit(73)
 b.submit=die
c.submit(dict(decision_id='first',symbol='SPY',side='buy',qty=1,limit_price=101),100,99,True,1000)
'''
    env=dict(os.environ,PYTHONPATH=str(Path(__file__).parent.resolve()))
    r=subprocess.run([sys.executable,'-c',script,str(tmp_path),phase],env=env,capture_output=True,timeout=10)
    assert r.returncode==73, r.stderr.decode()
    b=SimulatedBroker(tmp_path);c=Controller(tmp_path/'journal.json',b)
    try:
        if posts:assert send(c)['status']=='new'
        else:
            with pytest.raises(Halt,match='do not resubmit'):send(c)
        assert b.posts==posts
        assert 'first' in json.loads((tmp_path/'journal.json').read_text())['intents']
    finally:c.close()


@pytest.mark.parametrize('age',[-.001,60.001,float('nan'),float('inf')])
def test_refreshed_ineligible_quotes_block(lab,age):
    c,b,p=lab;b.market['quote_time']=100-age
    with pytest.raises(Halt,match='Fresh broker'):send(c)
    assert b.posts==0


def test_quote_boundary_sixty_seconds_is_eligible(lab):
    c,b,p=lab;b.market['quote_time']=40
    assert send(c)['status']=='new'


def test_stop_arrives_during_account_read(lab):
    c,b,p=lab;observe=b.observe
    def stopped():
        (p/'STOP').touch()
        return observe()
    b.observe=stopped
    with pytest.raises(Halt,match='Stop'):send(c)
    assert b.posts==0


@pytest.mark.parametrize('kind',['wrong_symbol','wrong_side','above_limit','excess_quantity'])
def test_known_order_activity_must_match_intent(lab,kind):
    c,b,p=lab;r=send(c);cid=r['client_order_id']
    b.liquidity(cid,100,1)
    a=b.state['activities'][0]
    if kind=='wrong_symbol':
        a['symbol']='BIL';b.state['positions']={'BIL':'1'}
    if kind=='wrong_side':
        a['side']='sell';b.state['positions']={'SPY':'-1'};b.state['cash']='1100'
    if kind=='above_limit':a['price']='102';b.state['cash']='898'
    if kind=='excess_quantity':
        a['qty']='2';b.state['positions']={'SPY':'2'};b.state['cash']='800'
    before=c.state['account_guard'].copy()
    with pytest.raises(Halt):cycle(c)
    assert c.state['account_guard']==before
    assert b.posts==1


def test_new_submission_reconciles_prior_order_fill_totals(lab):
    c,b,p=lab;r=send(c)
    # Terminal order says a share filled but account reports no execution.
    b.state['orders'][r['client_order_id']].update(status='filled',filled_qty=1)
    c.recover('first')
    with pytest.raises(Halt,match='disagree'):send(c,order('second'))
    assert b.posts==1


def test_cash_mismatch_blocks_new_order_and_preserves_checkpoint(lab):
    c,b,p=lab;before=c.state['account_guard'].copy();b.state['cash']='999'
    with pytest.raises(Halt,match='reconciliation'):send(c)
    assert b.posts==0 and c.state['account_guard']==before
