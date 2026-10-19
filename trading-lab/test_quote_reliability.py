import json
from types import SimpleNamespace
import pytest
from websockets.exceptions import ConnectionClosed,InvalidStatus
import check_quote_stream as stream
from observe_quote_reliability import reconnect_probe
from test_quote_stream_health import quote,BASE


@pytest.fixture
def clock(monkeypatch):
    tick=[0.]
    def mono():tick[0]+=.1;return tick[0]
    monkeypatch.setattr(stream.time,'monotonic',mono)
    monkeypatch.setattr(stream.time,'time',lambda:BASE+1)


class Socket:
    def __init__(self,events,pong=True):
        self.events=iter(events);self.closed=False;self.pong=pong
    def __enter__(self):return self
    def __exit__(self,*args):self.closed=True
    def send(self,data):pass
    def recv(self,**kwargs):
        event=next(self.events,TimeoutError())
        if isinstance(event,Exception):raise event
        return json.dumps(event)
    def ping(self):return SimpleNamespace(wait=lambda **kwargs:self.pong)


def socket_events(*tail):
    return [[{'T':'success','msg':'connected'}],[{'T':'success','msg':'authenticated'}],
            [{'T':'subscription','quotes':['SPY','BIL']}],*tail]


def probe(connector,rows):
    return stream.run('sip',5,rows.append,connector=connector,
                      credentials={'key_id':'SECRET','secret_key':'SECRET'})


@pytest.mark.parametrize('new_event',[False,True])
def test_drop_after_quote_clears_health_and_reconnect_does_not_reuse_cache(clock,new_event):
    sockets=[Socket(socket_events([quote()],ConnectionClosed(None,None))),Socket(socket_events(*([[quote()]] if new_event else [])))]
    original=list(sockets);rows=[];delays=[]
    def attempt(feed,seconds,emit):
        return stream.run(feed,seconds,emit,connector=lambda *a,**k:sockets.pop(0),
                          credentials={'key_id':'SECRET','secret_key':'SECRET'})
    result=reconnect_probe(5,rows.append,attempt=attempt,sleep=delays.append)
    assert result['status']=='observation_complete' and delays==[1]
    assert result['last_health']['symbols']['BIL']['reason']==('eligible' if new_event else 'missing_quote')
    assert result['counts']['accepted']==int(new_event)
    disconnected=[r for r in rows if r['event']=='disconnected']
    assert len(disconnected)==2 and all(s.closed for s in original)
    assert all(not r['connection_alive'] and not r['symbols']['BIL']['fresh_quote'] for r in disconnected)
    assert 'SECRET' not in json.dumps(rows)


@pytest.mark.parametrize('error,reason',[
    (TimeoutError('SECRET'),'transient_transport_error'),
    (OSError('SECRET'),'transient_transport_error'),
    (InvalidStatus(SimpleNamespace(status_code=429)),'rate_limited'),
    (InvalidStatus(SimpleNamespace(status_code=403)),'feed_access_denied'),
    (InvalidStatus(SimpleNamespace(status_code=503)),'transient_transport_error'),
])
def test_connect_failures_are_classified_and_redacted(clock,error,reason):
    def fail(*a,**kw):raise error
    rows=[];result=probe(fail,rows)
    assert result['reason']==reason and 'SECRET' not in json.dumps(rows)


def test_auth_rejection_stops_without_retry(clock):
    rows=[];calls=[]
    def attempt(feed,seconds,emit):
        calls.append(1)
        ws=Socket([[{'T':'success','msg':'connected'}],[{'T':'error','code':402,'msg':'SECRET'}]])
        return stream.run(feed,seconds,emit,connector=lambda *a,**k:ws,
                          credentials={'key_id':'SECRET','secret_key':'SECRET'})
    result=reconnect_probe(5,rows.append,attempt=attempt,sleep=lambda x:pytest.fail('must not retry'))
    assert result['reason']=='authentication_failed' and len(calls)==1
    assert 'SECRET' not in json.dumps(rows)


@pytest.mark.parametrize('reason',['rate_limited','feed_access_denied','connection_limit','invalid_stream_payload'])
def test_nontransient_failures_do_not_retry(reason):
    calls=[]
    def attempt(*args):calls.append(1);return {'status':'halted','reason':reason}
    reconnect_probe(5,lambda row:None,attempt=attempt,sleep=lambda x:pytest.fail('must not retry'))
    assert len(calls)==1


@pytest.mark.parametrize('reason',['transient_transport_error','pong_timeout','authentication_timeout'])
def test_retry_exhaustion_has_three_attempts_and_bounded_backoff(reason):
    calls=[];delays=[]
    def attempt(*args):calls.append(1);return {'status':'halted','reason':reason}
    result=reconnect_probe(5,lambda row:None,attempt=attempt,sleep=delays.append)
    assert len(calls)==3 and delays==[1,2] and result['status']=='halted'


def test_pong_timeout_blocks_health(clock):
    ws=Socket(socket_events(),pong=False);rows=[]
    result=probe(lambda *a,**k:ws,rows)
    assert result['reason']=='pong_timeout' and ws.closed
    assert rows[-2]['event']=='disconnected' and not rows[-2]['connection_alive']


def test_message_budget_halts_before_excess_quote(clock):
    ws=Socket(socket_events([quote(),quote(S='SPY')]))
    rows=[]
    result=stream.run('sip',5,rows.append,connector=lambda *a,**k:ws,
                      credentials={'key_id':'SECRET','secret_key':'SECRET'},max_quotes=1)
    assert result['reason']=='probe_message_limit' and result['counts']['quotes']==1
    assert ws.closed


@pytest.mark.parametrize('budget',[0,100001,True,1.5])
def test_invalid_message_budget_rejected_before_connection(budget):
    with pytest.raises(ValueError,match='budget'):
        stream.run('sip',5,lambda row:None,max_quotes=budget)


def test_controlled_live_disconnect_wrapper_only_interrupts_once():
    from check_live_quote_disconnect import DisconnectOnce
    now=[0.];rows=[];sockets=[]
    def connect(*a,**k):
        ws=SimpleNamespace(close=lambda:sockets.append('closed'),recv=lambda **kw:'frame')
        return ws
    wrapper=DisconnectOnce(rows.append,connector=connect,monotonic=lambda:now[0])
    with wrapper() as ws:
        assert ws.recv()=='frame'
        now[0]=6
        with pytest.raises(ConnectionAbortedError):ws.recv()
    with wrapper() as ws:
        now[0]=20
        assert ws.recv()=='frame'
    assert wrapper.injected and len(rows)==1 and len(sockets)==3
