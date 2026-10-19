import json
from types import SimpleNamespace
import pytest
import requests
from observer_service import Store, ReadOnlyTransport, ReadFailure, observe
from test_supervised_runner import setup_runner

URL = 'https://paper-api.alpaca.markets/v2/account'

class Clock:
    value = 100
    def now(self): return self.value
    def sleep(self, duration): self.value += duration

class Session:
    def __init__(self, responses): self.responses = iter(responses); self.calls = []
    def request(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        result = next(self.responses)
        if isinstance(result, Exception): raise result
        return result

def response(code, **headers): return SimpleNamespace(status_code=code, headers=headers)

def transport(tmp_path, responses, budget=60):
    store = Store(tmp_path/'state.sqlite'); clock = Clock(); session = Session(responses)
    return ReadOnlyTransport(session, store, clock.sleep, clock.now, budget), store, clock

@pytest.mark.parametrize('transient', [requests.Timeout('SECRET'), requests.ConnectionError('SECRET'), response(429), response(503)])
def test_transient_retry_recovers(tmp_path, transient):
    t,s,c = transport(tmp_path, [transient, response(200)])
    assert t.get(URL).status_code == 200
    assert len(t.session.calls) == 2 and c.value >= 101

@pytest.mark.parametrize('method,url', [('POST', URL), ('DELETE', URL), ('GET', 'https://api.alpaca.markets/v2/account'), ('GET', 'https://paper-api.alpaca.markets.evil/account')])
def test_write_and_host_rejected_before_io(tmp_path, method, url):
    t,s,c = transport(tmp_path, [])
    with pytest.raises(ReadFailure): t.request(method, url)
    assert not t.session.calls

def test_retry_and_total_budget(tmp_path):
    t,s,c = transport(tmp_path, [response(503)]*4)
    with pytest.raises(ReadFailure): t.get(URL)
    assert len(t.session.calls) == 3
    t.remaining = 0
    with pytest.raises(ReadFailure): t.get(URL)
    assert len(t.session.calls) == 3

@pytest.mark.parametrize('code', [401,403,404,302])
def test_nontransient_not_retried(tmp_path, code):
    t,s,c = transport(tmp_path, [response(code)])
    assert t.get(URL).status_code == code
    assert len(t.session.calls) == 1
    assert t.session.calls[0][1]['allow_redirects'] is False

def test_cooldown_survives_restart(tmp_path):
    t,s,c = transport(tmp_path, [response(429, **{'Retry-After':'120'})])
    with pytest.raises(ReadFailure): t.get(URL)
    s.db.close()
    s = Store(tmp_path/'state.sqlite')
    t = ReadOnlyTransport(Session([]), s, c.sleep, c.now)
    with pytest.raises(ReadFailure): t.get(URL)
    assert not t.session.calls
    assert float(s.get('next_request')) == 220

def test_alert_failure_restart_dedup_and_recovery(tmp_path):
    s = Store(tmp_path/'state.sqlite')
    halted = dict(status='halted', error_type='ReadFailure')
    s.record(halted); s.record(halted)
    def fail(*args): raise RuntimeError('SECRET')
    assert s.deliver(fail) == 1
    s.db.close(); s = Store(tmp_path/'state.sqlite')
    assert s.db.execute('SELECT attempts FROM alerts').fetchone()[0] == 1
    delivered = []
    assert s.deliver(lambda identity,payload: delivered.append(identity)) == 0
    s.record(dict(status='observed'))
    assert s.deliver(lambda identity,payload: delivered.append(identity)) == 0
    assert delivered == ['1','2']

def test_transaction_failure_does_not_advance_transition(tmp_path):
    s = Store(tmp_path/'state.sqlite')
    s.db.execute("CREATE TRIGGER fail BEFORE INSERT ON alerts BEGIN SELECT RAISE(ABORT, 'injected'); END")
    with pytest.raises(Exception): s.record(dict(status='halted'))
    assert s.get('status') is None
    assert s.db.execute('SELECT count(*) FROM observations').fetchone()[0] == 0

def test_readonly_cycle_preserves_account_guard(setup_runner):
    c,b,p = setup_runner
    before = json.loads(c.path.read_text())
    s = Store(p/'service.sqlite')
    assert observe(c,s)['status'] == 'observed'
    assert json.loads(c.path.read_text()) == before and b.posts == 0
    b.observe = lambda: (_ for _ in ()).throw(RuntimeError('SECRET'))
    report = observe(c,s)
    assert report['status'] == 'halted' and report['pending_alerts'] == 1
    assert 'SECRET' not in s.db.execute('SELECT payload FROM observations ORDER BY id DESC').fetchone()[0]

def test_process_death_rolls_back_uncommitted_observation(tmp_path):
    import subprocess
    import sys
    from pathlib import Path
    path = tmp_path/'crash.sqlite'
    s = Store(path); s.record(dict(status='observed')); s.db.close()
    code = """
import os,sys
from observer_service import Store
s=Store(sys.argv[1])
s.db.execute('BEGIN')
s.db.execute("INSERT INTO observations(payload) VALUES ('uncommitted')")
s.put('status','halted')
os._exit(17)
"""
    result = subprocess.run([sys.executable, '-c', code, str(path)], cwd=Path(__file__).parent)
    assert result.returncode == 17
    s = Store(path)
    assert s.get('status') == 'observed:'
    assert s.db.execute('SELECT count(*) FROM observations').fetchone()[0] == 1

def test_interrupt_after_alert_delivery_reuses_identity(tmp_path):
    s = Store(tmp_path/'state.sqlite'); s.record(dict(status='halted'))
    identities = set()
    def interrupted(identity, payload):
        identities.add(identity)
        raise KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt): s.deliver(interrupted)
    s.db.close(); s = Store(tmp_path/'state.sqlite')
    assert s.deliver(lambda identity,payload: identities.add(identity)) == 0
    assert identities == {'1'}
