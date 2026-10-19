import pytest
import bil_close_probe as probe
from order_controller import Controller,Halt
from test_reduce_only_sell import FillBroker,order,send

@pytest.fixture
def held(tmp_path):
    b=FillBroker(tmp_path);p=tmp_path/'journal.json';c=Controller(p,b);c.checkpoint()
    r=send(c,order('buy',decision_id=probe.BUY_KEY,limit_price=91.59))
    b.fill(r['client_order_id'],1,91.58);c.recover(probe.BUY_KEY);c.reconcile_account();c.close()
    b.market_inputs=lambda symbol:dict(now=100,quote_time=99,market_open=True,feed='sip',bid=91.57,ask=91.58)
    return b,p

def test_prepare_sell_and_recover(held):
    b,p=held
    r=probe.run('prepare',p,b);assert r['proposal']['intent']['limit_price']==91.56 and b.posts==1
    r=probe.run('submit',p,b);b.fill(r['record']['client_order_id'],1,91.57)
    r=probe.run('recover',p,b);assert r['account_guard']['positions']=={}
    r=probe.run('submit',p,b);assert r['status']=='already_recorded_do_not_resubmit' and b.posts==2
    probe.run('recover',p,b);assert b.posts==2

@pytest.mark.parametrize('change',[dict(bid=90,ask=90.01),dict(bid=101,ask=101.01),dict(bid=91,ask=92),dict(market_open=False),dict(quote_time=101)])
def test_invalid_quote_cannot_close(held,change):
    b,p=held;m=b.market_inputs('BIL')|change;b.market_inputs=lambda symbol:m
    with pytest.raises(Halt):probe.run('submit',p,b)
    assert b.posts==1

def test_stop_cannot_close(held):
    b,p=held;(p.parent/'STOP').touch()
    with pytest.raises(Halt):probe.run('submit',p,b)
    assert b.posts==1

def test_no_original_fill_cannot_close(held):
    b,p=held;c=Controller(p,b)
    c.state['intents']['other']=c.state['intents'].pop(probe.BUY_KEY);c.save();c.close()
    with pytest.raises(Halt,match='Original'):probe.run('submit',p,b)
    assert b.posts==1
