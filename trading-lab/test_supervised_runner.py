import copy
import json
import pytest
from order_controller import Controller,Halt
from test_order_controller import Broker,intent,submit
from supervised_runner import cycle,run

class ObservedBroker(Broker):
    def __init__(self,root):
        super().__init__();self.account_lock_dir=root/'locks';self.activities=[];self.positions=[];self.cash='1000'
        self.market=dict(now=100,quote_time=99,market_open=True,bid=99,ask=100,feed='iex')
    def observe(self):
        return super().observe()|dict(activities=copy.deepcopy(self.activities),positions=copy.deepcopy(self.positions),cash=self.cash)
    def market_inputs(self,symbol):return dict(self.market)
    def submit(self,cid,order):
        result=super().submit(cid,order)
        self.orders[cid]['order_id']='broker-id'
        return self.lookup(cid)

@pytest.fixture
def setup_runner(tmp_path):
    b=ObservedBroker(tmp_path);c=Controller(tmp_path/'journal.json',b);c.checkpoint()
    yield c,b,tmp_path
    c.close()

def test_restart_keeps_checkpoint_and_appends_run_identity(setup_runner):
    c,b,p=setup_runner;audit=p/'audit.jsonl'
    assert run(c,audit,cycles=2,sleep=lambda _:None)==0
    before=c.state['account_guard'];c.close()
    c=Controller(p/'journal.json',b)
    try:
        assert run(c,audit,cycles=1)==0
        assert c.state['account_guard']==before
    finally:c.close()
    rows=[json.loads(x) for x in audit.read_text().splitlines()]
    assert len(rows)==3 and rows[0]['run_id']==rows[1]['run_id']!=rows[2]['run_id']
    assert b.posts==0

def test_unknown_submission_recovers_without_post(setup_runner):
    c,b,p=setup_runner;b.timeout=True
    with pytest.raises(Halt):submit(c)
    b.orders[next(iter(b.orders))]['order_id']='broker-id'
    c.close();c=Controller(p/'journal.json',b)
    try:
        assert cycle(c)['unresolved_intents']==1
        assert b.posts==1
    finally:c.close()

def test_partial_fill_then_restart_is_idempotent(setup_runner):
    c,b,p=setup_runner;r=submit(c)
    b.orders[r['client_order_id']].update(filled_qty=.4,status='partially_filled')
    b.cash='999.6';b.positions=[dict(symbol='SPY',qty='.4',market_value='.4')]
    b.activities=[dict(id='fill',activity_type='FILL',order_id='broker-id',symbol='SPY',qty='.4',price='1',side='buy')]
    assert cycle(c)['positions']==1
    c.close();c=Controller(p/'journal.json',b)
    try:
        cycle(c)
        assert c.state['account_guard']['cash']=='999.6'
        assert c.state['account_guard']['positions']=={'SPY':'0.4'}
        assert b.posts==1
    finally:c.close()

def test_missing_fill_activity_stops(setup_runner):
    c,b,p=setup_runner;r=submit(c)
    b.orders[r['client_order_id']].update(filled_qty=.4,status='partially_filled')
    with pytest.raises(Halt,match='disagree'):cycle(c)

def test_outside_open_order_stops(setup_runner):
    c,b,p=setup_runner;b.orders['outside']=dict(status='new',client_order_id='outside')
    assert run(c,p/'audit',cycles=3,sleep=lambda _:pytest.fail('Retried after halt'))==1
    assert b.posts==0

def test_error_details_are_not_logged(setup_runner,capsys):
    c,b,p=setup_runner
    def fail():raise RuntimeError('SECRET sentinel')
    b.observe=fail
    assert run(c,p/'audit',cycles=1)==1
    assert 'SECRET' not in (p/'audit').read_text()+capsys.readouterr().out

@pytest.mark.parametrize('change',[{'quote_time':0},{'quote_time':101},{'market_open':False}])
def test_stale_future_closed_are_observed_but_not_trade_ready(setup_runner,change):
    c,b,p=setup_runner;b.market.update(change)
    assert cycle(c)['market']['SPY']['fresh_open_quote'] is False
    with pytest.raises(Halt,match='Fresh broker'):submit(c)
    assert b.posts==0

def test_stop_file_preserves_observation(setup_runner):
    c,b,p=setup_runner;(p/'STOP').touch()
    assert cycle(c)['stop_file_present'] is True
    assert b.posts==0

@pytest.mark.parametrize('cycles,interval',[(0,5),(31,5),(1,0),(1,61)])
def test_bounded_runtime(setup_runner,cycles,interval):
    c,b,p=setup_runner
    with pytest.raises(ValueError):run(c,p/'audit',cycles=cycles,interval=interval)
