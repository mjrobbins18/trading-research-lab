import socket
import pytest
from execution_simulator import SimulatedBroker
from order_controller import Controller,Halt
from controller_recovery_probe import run_phase,KEY

@pytest.fixture
def lab(tmp_path,monkeypatch):
    def blocked(*a,**k):raise AssertionError('Network forbidden')
    monkeypatch.setattr(socket.socket,'connect',blocked)
    b=SimulatedBroker(tmp_path);p=tmp_path/'journal.json';c=Controller(p,b);c.checkpoint();c.close()
    return b,p


def test_prepare_submit_lost_response_restart_recover_cancel(lab):
    b,p=lab
    assert run_phase('prepare',p,b)['proposal']['maximum_order_cost_usd']=='1.00'
    assert b.posts==0
    b.lose_response=True
    r=run_phase('submit',p,b)
    assert r['status']=='outcome_unknown_recover_by_client_id'
    b=SimulatedBroker(p.parent)
    assert run_phase('recover',p,b)['record']['status']=='new'
    assert run_phase('submit',p,b)['status']=='already_recorded_do_not_resubmit'
    assert run_phase('cancel',p,b)['record']['status']=='canceled'
    assert run_phase('cancel',p,b)['terminal'] is True
    assert b.posts==1 and b.state['cash']=='1000'


@pytest.mark.parametrize('change',[{'quote_time':0},{'quote_time':101},{'market_open':False},{'ask':1}])
def test_ineligible_market_never_posts(lab,change):
    b,p=lab;b.market.update(change)
    with pytest.raises(Halt):run_phase('submit',p,b)
    assert b.posts==0


def test_no_checkpoint_is_not_created(tmp_path):
    b=SimulatedBroker(tmp_path);p=tmp_path/'journal.json'
    with pytest.raises(Halt,match='checkpoint'):run_phase('prepare',p,b)
    assert not p.exists() and b.posts==0


def test_missing_order_remains_ambiguous(lab):
    b,p=lab;b.lose_response=True;run_phase('submit',p,b);b.hidden=True
    with pytest.raises(Halt,match='do not resubmit'):run_phase('recover',p,b)
    assert b.posts==1


def test_filled_before_cancel_preserves_position(lab):
    b,p=lab;r=run_phase('submit',p,b);b.liquidity(r['record']['client_order_id'],1,1)
    r=run_phase('cancel',p,b)
    assert r['record']['status']=='filled' and r['observation']['positions']==1
    assert b.posts==1
