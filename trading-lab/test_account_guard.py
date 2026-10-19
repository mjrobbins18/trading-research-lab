import copy
import pytest
from account_guard import checkpoint,reconcile,permit,ReconciliationError
from order_controller import Controller,Halt
from test_order_controller import Broker,intent,submit


def snapshot():
    return dict(account='paper-test',cash='1000',equity='1000',positions=[],orders=[],activities=[],blocked=False)

def filled(qty='.4',price='100',event_id='fill-1'):
    s=snapshot();s['cash']='960';s['positions']=[dict(symbol='SPY',qty=qty,market_value='40')]
    s['activities']=[dict(id=event_id,activity_type='FILL',order_id='owned',qty=qty,price=price,side='buy',symbol='SPY')]
    return s

def test_partial_fill_cash_position_and_duplicate():
    state=checkpoint(snapshot());s=filled()
    updated=reconcile(state,s,{'owned'})
    assert updated['cash']=='960.0' and updated['positions']=={'SPY':'0.4'}
    assert reconcile(updated,s,{'owned'})==updated
    assert state['cash']=='1000'

def test_second_partial_uses_incremental_execution_quantity():
    state=reconcile(checkpoint(snapshot()),filled(),{'owned'})
    s=filled();s['activities'].append(s['activities'][0]|{'id':'fill-2','qty':'.6','cum_qty':'1'})
    s['cash']='900';s['positions'][0].update(qty='1',market_value='100')
    result=reconcile(state,s,{'owned'})
    assert result['cash']=='900.0' and result['positions']['SPY']=='1.0'

@pytest.mark.parametrize('change',[
    {'cash':'959'}, {'positions':[]}, {'account':'another'}, {'blocked':True},
])
def test_inconsistent_account_fails(change):
    with pytest.raises(ReconciliationError):reconcile(checkpoint(snapshot()),filled()|change,{'owned'})

def test_external_fill_requires_review():
    with pytest.raises(ReconciliationError,match='Unrecognized'):reconcile(checkpoint(snapshot()),filled(),set())

@pytest.mark.parametrize('kind',['DIV','JNLC','FEE','SPLIT'])
def test_nontrade_activity_requires_review(kind):
    s=snapshot();s['activities']=[dict(id='new',activity_type=kind,net_amount='1')]
    with pytest.raises(ReconciliationError):reconcile(checkpoint(snapshot()),s,set())

@pytest.mark.parametrize('mode',['missing','revised','duplicate'])
def test_history_integrity(mode):
    s=filled();state=reconcile(checkpoint(snapshot()),s,{'owned'})
    if mode=='missing':s['activities']=[]
    if mode=='revised':s['activities'][0]['price']='99'
    if mode=='duplicate':s['activities']*=2
    with pytest.raises(ReconciliationError):reconcile(state,s,{'owned'})

@pytest.mark.parametrize('change,spent',[
    ({'orders':[{'id':'outside'}]},0),
    ({'positions':[dict(symbol='SPY',qty='10',market_value='1000')]},0),
    ({'equity':'974'},0), ({},1000),
    ({'positions':[dict(symbol='UNKNOWN',qty='1',market_value='1')]},0),
])
def test_risk_limits(change,spent):
    with pytest.raises(ReconciliationError):permit(checkpoint(snapshot()),snapshot()|change,intent(),spent)

def test_no_checkpoint_no_post(tmp_path):
    b=Broker();c=Controller(tmp_path/'state.json',b)
    try:
        with pytest.raises(Halt,match='checkpoint'):submit(c)
        assert b.posts==0
    finally:c.close()

def test_account_preflight_blocks_external_order(tmp_path):
    b=Broker();b.account_lock_dir=tmp_path/'locks';c=Controller(tmp_path/'state.json',b)
    try:
        c.checkpoint();b.orders['outside']={'status':'new'}
        with pytest.raises(Halt,match='Open account'):submit(c)
        assert b.posts==0
    finally:c.close()

def test_different_journal_cannot_reset_account_budget(tmp_path):
    b=Broker();b.account_lock_dir=tmp_path/'locks'
    c=Controller(tmp_path/'one.json',b);c.checkpoint();c.close()
    c=Controller(tmp_path/'two.json',b)
    try:
        with pytest.raises(Halt,match='ownership'):c.checkpoint()
    finally:c.close()

def test_canceled_orders_still_consume_session_budget(tmp_path):
    b=Broker();b.account_lock_dir=tmp_path/'locks';c=Controller(tmp_path/'state.json',b)
    try:
        c.checkpoint();submit(c,intent()|{'limit_price':1000.0});c.cancel(intent()['decision_id'])
        with pytest.raises(Halt,match='Cumulative'):submit(c,intent()|{'decision_id':'next'})
        assert b.posts==1
    finally:c.close()
