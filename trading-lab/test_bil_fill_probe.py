import socket
import pytest
from execution_simulator import SimulatedBroker
from order_controller import Controller,Halt
from bil_fill_probe import run

@pytest.fixture
def lab(tmp_path,monkeypatch):
    def blocked(*a,**k):raise AssertionError('Network forbidden')
    monkeypatch.setattr(socket.socket,'connect',blocked)
    b=SimulatedBroker(tmp_path);b.market.update(bid=91.57,ask=91.58)
    p=tmp_path/'journal.json';c=Controller(p,b);c.checkpoint();c.close()
    return b,p

def test_fill_restart_and_idempotency(lab):
    b,p=lab;r=run('submit',p,b)
    assert r['record']['intent']['limit_price']==91.59
    b.liquidity(r['record']['client_order_id'],91.58,1)
    r=run('recover',p,b)
    assert r['account_guard']['cash']=='908.42' and r['account_guard']['positions']=={'BIL':'1'}
    old=r['account_guard'];b=SimulatedBroker(p.parent)
    assert run('recover',p,b)['account_guard']==old
    assert run('submit',p,b)['status']=='already_recorded_do_not_resubmit'
    assert b.posts==1

@pytest.mark.parametrize('change',[{'quote_time':0},{'quote_time':101},{'market_open':False},{'ask':101,'bid':100.99},{'ask':92}])
def test_invalid_market_no_post(lab,change):
    b,p=lab;b.market.update(change)
    with pytest.raises(Halt):run('submit',p,b)
    assert b.posts==0

def test_cancel_unfilled(lab):
    b,p=lab;run('submit',p,b)
    assert run('cancel',p,b)['record']['status']=='canceled'
    assert b.posts==1
