import json
from types import SimpleNamespace
from datetime import datetime,timezone
import pytest
import alpaca_order_adapter as adapter
from market_data_policy import load_policy,MarketDataError,quote_eligibility

@pytest.mark.parametrize('age,opened,result',[(0,True,'eligible'),(60,True,'eligible'),(61,True,'stale_or_invalid_quote'),(-.001,True,'future_quote'),(1,False,'market_closed'),(float('nan'),True,'stale_or_invalid_quote')])
def test_quote_reasons(age,opened,result):
    assert quote_eligibility(100,100-age,opened)==result

@pytest.mark.parametrize('feed,diagnostic',[('iex',True),('sip',True),('iex',False)])
def test_diagnostic_adapter_cannot_post(feed,diagnostic):
    b=adapter.PaperBroker.__new__(adapter.PaperBroker);b.data_feed=feed;b.diagnostic_only=diagnostic
    b.call=lambda *a,**k:pytest.fail('Broker call forbidden')
    with pytest.raises(MarketDataError,match='cannot_submit'):b.submit('id',{})

@pytest.mark.parametrize('status,code',[(403,'feed_access_denied'),(401,'feed_access_denied'),(429,'rate_limited'),(503,'market_data_http_error')])
def test_denial_never_falls_back(monkeypatch,status,code):
    now=1792430000;stamp=datetime.fromtimestamp(now,timezone.utc).isoformat()
    monkeypatch.setattr(adapter.time,'time',lambda:now)
    b=adapter.PaperBroker.__new__(adapter.PaperBroker);b.data_feed='sip'
    b.call=lambda *a,**k:{'timestamp':stamp,'is_open':True}
    calls=[]
    def get(*a,**k):
        calls.append(k['params']['feed']);return SimpleNamespace(status_code=status)
    b.session=SimpleNamespace(get=get)
    with pytest.raises(MarketDataError,match=code):b.market_inputs('BIL')
    assert calls==['sip']

def test_policy_cannot_silently_select_iex(tmp_path):
    p=tmp_path/'policy.json';p.write_text(json.dumps(load_policy()|{'execution_feed':'iex'}))
    with pytest.raises(ValueError):load_policy(p)

def test_default_requires_sip(monkeypatch):
    monkeypatch.setattr(adapter,'load_credentials',lambda:{'key_id':'fake','secret_key':'fake'})
    b=adapter.PaperBroker()
    assert b.data_feed=='sip' and not b.diagnostic_only

@pytest.mark.parametrize('offset,round_trip',[(2,0),(0,3)])
def test_clock_health_blocks(monkeypatch,offset,round_trip):
    now=1792430000;times=iter([now,now+round_trip,now+round_trip])
    monkeypatch.setattr(adapter.time,'time',lambda:next(times))
    stamp=lambda n:datetime.fromtimestamp(n,timezone.utc).isoformat()
    b=adapter.PaperBroker.__new__(adapter.PaperBroker)
    b.call=lambda *a,**k:dict(timestamp=stamp(now+offset),is_open=True)
    b.session=SimpleNamespace(get=lambda *a,**k:SimpleNamespace(status_code=200,json=lambda:{'quotes':{'BIL':{'t':stamp(now),'bp':91,'ap':91.01}}}))
    with pytest.raises(MarketDataError,match='clock_health'):b.market_inputs('BIL')

def test_diagnostic_read_only_transport():
    from check_market_data import GetOnly
    s=SimpleNamespace(request=lambda *a,**k:pytest.fail('Network must not be called'))
    t=GetOnly(s)
    for method,url in [('POST','https://paper-api.alpaca.markets/v2/orders'),('GET','https://api.alpaca.markets/v2/account'),('GET','https://data.alpaca.markets.evil/')]:
        with pytest.raises(RuntimeError):t.request(method,url)

def test_collector_reports_access_failure_without_secret():
    from check_market_data import collect
    def denied(symbol):raise MarketDataError('feed_access_denied')
    rows=collect(SimpleNamespace(data_feed='sip',market_inputs=denied))
    assert all(r['reason']=='feed_access_denied' and not r['execution_data_eligible'] for r in rows)

def test_iex_is_not_execution_eligible_even_when_fresh():
    from check_market_data import collect
    rows=collect(SimpleNamespace(data_feed='iex',market_inputs=lambda s:{'eligibility':'eligible'}))
    assert all(not r['execution_data_eligible'] for r in rows)

def test_alerts_on_quote_failure_and_recovery_without_repetition(tmp_path):
    from observer_service import Store
    s=Store(tmp_path/'alerts.sqlite')
    bad={'status':'observed','market':{'BIL':{'market_open':True,'fresh_open_quote':False}}}
    s.record(bad);s.record(bad)
    assert s.deliver()==1
    s.record({'status':'observed','market':{'BIL':{'market_open':True,'fresh_open_quote':True}}})
    assert s.deliver()==2
    s.db.close()

def test_different_failure_reasons_create_distinct_alerts(tmp_path):
    from observer_service import Store
    s=Store(tmp_path/'alerts.sqlite')
    for reason in ('feed_access_denied','clock_health_failed'):
        s.record({'status':'halted','error_type':'MarketDataError','reason':reason})
    assert s.deliver()==2
    s.db.close()
