import pytest
from alpaca_order_adapter import PaperBroker


def broker(pages,changed=False):
    b=PaperBroker.__new__(PaperBroker)
    calls=[]
    account=dict(id='fake-account',cash='1000',equity='1000',long_market_value='0',short_market_value='0',
                 status='ACTIVE',trading_blocked=False,account_blocked=False)
    def call(method,path,**kwargs):
        calls.append((method,path,kwargs))
        if path=='/v2/account':
            return account|({'cash':'999'} if changed and len(calls)>1 else {})
        if path=='/v2/positions':return []
        if path=='/v2/orders':return []
        if path=='/v2/account/activities':return pages.pop(0)
        raise AssertionError(path)
    b.call=call
    return b,calls


def test_activity_pagination_uses_last_id():
    first=[{'id':str(i)} for i in range(100)]
    b,calls=broker([first,[{'id':'last'}]])
    result=b.observe()
    assert len(result['activities'])==101
    pages=[kw['params'] for _,path,kw in calls if path.endswith('activities')]
    assert pages[1]['page_token']=='99'
    assert result['account']!='fake-account'
    assert all(method=='GET' for method,_,_ in calls)


def test_nonatomic_account_change_stops_observation():
    b,_=broker([[]],changed=True)
    with pytest.raises(RuntimeError,match='changed'):b.observe()


def test_stalled_pagination_stops():
    page=[{'id':str(i)} for i in range(100)]
    b,_=broker([page,page])
    with pytest.raises(RuntimeError,match='stalled'):b.observe()

@pytest.mark.parametrize('clock_age,bid,ask,http,valid',[
    (0,99,100,200,True),(11,99,100,200,False),(-3,99,100,200,False),
    (0,101,100,200,False),(0,0,100,200,False),(0,float('nan'),100,200,False),
    (0,99,100,429,False),
])
def test_market_input_validation(monkeypatch,clock_age,bid,ask,http,valid):
    from datetime import datetime,timezone
    from types import SimpleNamespace
    import alpaca_order_adapter
    now=1792173600
    monkeypatch.setattr(alpaca_order_adapter.time,'time',lambda:now)
    stamp=lambda epoch:datetime.fromtimestamp(epoch,timezone.utc).isoformat()
    b=PaperBroker.__new__(PaperBroker)
    b.call=lambda *a,**kw:dict(timestamp=stamp(now-clock_age),is_open=True)
    def get(url,**kw):
        assert url=='https://data.alpaca.markets/v2/stocks/quotes/latest'
        assert kw['params']=={'symbols':'SPY','feed':'sip'}
        assert kw['allow_redirects'] is False
        return SimpleNamespace(status_code=http,json=lambda:dict(quotes={'SPY':dict(t=stamp(now-1),bp=bid,ap=ask,bs=1,**{"as":1},bx="V",ax="V",c=["R"])}))
    b.session=SimpleNamespace(get=get)
    if valid:
        assert b.market_inputs('SPY')['quote_time']==now-1
    else:
        with pytest.raises(RuntimeError):b.market_inputs('SPY')
