import json
from types import SimpleNamespace
import pytest
from market_data_policy import validate_quote,quote_timestamp_ns,MarketDataError
from quote_stream_health import QuoteHealth
from check_quote_stream import messages,run

BASE=1792430000

def quote(**changes):
    from datetime import datetime,timezone
    stamp=datetime.fromtimestamp(BASE,timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')+'.000000001Z'
    return {'T':'q','S':'BIL','t':stamp,'bp':91.57,'ap':91.58,'bs':1,'as':2,'bx':'V','ax':'V','c':['R']}|changes

def ready():
    h=QuoteHealth('sip',['BIL']);h.connect();h.authenticate();h.subscribe(['BIL']);h.pong(10)
    assert h.quote(quote(),BASE+1)=='accepted'
    return h

@pytest.mark.parametrize('change',[
    {'bs':0},{'as':-1},{'as':True},{'bs':1.5},{'bp':float('nan')},{'ap':True},
    {'bp':92},{'c':[]},{'c':['R','X']},{'c':['X']},{'ax':''},{'t':'2026-10-19T13:00:00'},
    {'t':'not-a-timestamp'}, {'t':None}
])
def test_malformed_and_unsupported_quotes_rejected(change):
    with pytest.raises(MarketDataError):validate_quote(quote(**change))

def test_nanosecond_ordering_preserved():
    q=quote();q2=q|{'t':q['t'].replace('000000001','000000002')}
    assert quote_timestamp_ns(q2['t'])-quote_timestamp_ns(q['t'])==1
    h=ready();assert h.quote(q2,BASE+1)=='accepted'

def test_old_or_duplicate_message_invalidates_cached_quote():
    h=ready();assert h.quote(quote(),BASE+2)=='nonincreasing_quote_timestamp'
    assert h.snapshot(BASE+2,10)['symbols']['BIL']['fresh_quote'] is False

def test_disconnect_reconnect_needs_auth_subscription_and_new_event():
    h=ready();assert h.snapshot(BASE+1,10)['symbols']['BIL']['fresh_quote']
    h.disconnect();assert not h.quotes and not h.snapshot(BASE+1,10)['connection_alive']
    h.connect();h.pong(11)
    with pytest.raises(MarketDataError,match='subscription'):h.quote(quote(),BASE+1)
    h.authenticate();h.subscribe(['BIL'])
    assert not h.snapshot(BASE+1,11)['symbols']['BIL']['fresh_quote']
    assert h.quote(quote(),BASE+1)=='accepted'
    assert h.epoch==2

def test_live_connection_does_not_refresh_old_symbol_event():
    h=ready();h.pong(100)
    snap=h.snapshot(BASE+61,100)
    assert snap['connection_alive'] and snap['symbols']['BIL']['reason']=='stale_or_invalid_quote'

def test_old_pong_blocks_even_fresh_quote():
    h=ready();snap=h.snapshot(BASE+1,21)
    assert not snap['connection_alive'] and not snap['symbols']['BIL']['fresh_quote']

def test_unsubscribe_erases_quote():
    h=ready();h.subscribe([])
    assert not h.quotes and h.snapshot(BASE+1,10)['symbols']['BIL']['reason']=='not_subscribed'

def test_bad_condition_invalidates_prior_good_quote():
    h=ready();assert h.quote(quote(c=['X']),BASE+1)=='unsupported_quote_condition'
    assert not h.quotes

@pytest.mark.parametrize('code,reason',[(409,'feed_access_denied'),(406,'connection_limit'),(407,'slow_client'),(402,'authentication_failed')])
def test_stream_error_mapping_does_not_expose_server_message(code,reason):
    with pytest.raises(MarketDataError,match=reason) as e:messages(json.dumps([{'T':'error','code':code,'msg':'SECRET'}]))
    assert 'SECRET' not in str(e.value)

def test_fake_stream_auth_subscription_and_redacted_output(monkeypatch):
    import check_quote_stream as stream
    clock=[0]
    def monotonic():clock[0]+=.1;return clock[0]
    monkeypatch.setattr(stream.time,'monotonic',monotonic)
    monkeypatch.setattr(stream.time,'time',lambda:BASE+1)
    class Socket:
        def __init__(self):self.sent=[];self.items=iter([
            [{'T':'success','msg':'connected'}],[{'T':'success','msg':'authenticated'}],
            [{'T':'subscription','quotes':['SPY','BIL']}],[quote(),quote(S='SPY')]])
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def send(self,x):self.sent.append(json.loads(x))
        def recv(self,**kw):
            try:return json.dumps(next(self.items))
            except StopIteration:raise TimeoutError()
        def ping(self):return SimpleNamespace(wait=lambda **kw:True)
    ws=Socket();rows=[]
    result=run('sip',5,rows.append,connector=lambda *a,**k:ws,credentials={'key_id':'SECRET','secret_key':'SECRET2'})
    assert result['status']=='observation_complete' and result['counts']['accepted']==2
    assert ws.sent[1]=={'action':'subscribe','quotes':['SPY','BIL']}
    assert 'SECRET' not in json.dumps(rows) and not result['execution_qualified']
