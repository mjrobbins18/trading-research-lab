import json
from types import SimpleNamespace
import pytest
from fetch_calendar import CalendarOnly,fetch,normalize
ROW=dict(date='2026-10-20',open='09:30',close='16:00',session_open='0400',session_close='2000',settlement_date='2026-10-21')
class Fake:
 def __init__(self,status=200,body=None):self.calls=[];self.status=status;self.body=[ROW] if body is None else body
 def request(self,method,url,**kw):
  self.calls.append((method,url,kw));return SimpleNamespace(status_code=self.status,json=lambda:self.body)

def test_fetch_one_get_and_normalize():
 s=Fake();rows=fetch(CalendarOnly(s),'2026-10-20','2026-10-23')
 assert rows==[dict(date='2026-10-20',open='09:30',close='16:00')]
 (m,u,kw),=s.calls
 assert m=='GET' and u=='https://paper-api.alpaca.markets/v2/calendar' and kw['params']=={'start':'2026-10-20','end':'2026-10-23'}
 assert kw['allow_redirects'] is False and kw['timeout']==20
@pytest.mark.parametrize('method,url',[('POST','https://paper-api.alpaca.markets/v2/calendar'),('GET','https://paper-api.alpaca.markets/v2/orders'),
 ('GET','https://api.alpaca.markets/v2/calendar'),('GET','http://paper-api.alpaca.markets/v2/calendar')])
def test_transport_rejects_anything_else(method,url):
 s=Fake()
 with pytest.raises(PermissionError):CalendarOnly(s).request(method,url)
 assert s.calls==[]
def test_http_error_not_retried():
 s=Fake(status=403)
 with pytest.raises(RuntimeError,match='HTTP 403'):fetch(CalendarOnly(s),'2026-10-20','2026-10-20')
 assert len(s.calls)==1
@pytest.mark.parametrize('row',[ROW|{'open':'9:30'},ROW|{'close':'25:00'},ROW|{'date':'10/20/2026'},{'date':'2026-10-20','open':'09:30'},ROW|{'open':'16:00','close':'09:30'}])
def test_malformed_rows_rejected(row):
 with pytest.raises((ValueError,KeyError,TypeError)):normalize([row])
def test_duplicate_dates_rejected():
 with pytest.raises(ValueError):normalize([ROW,ROW])
def test_bad_range_rejected():
 with pytest.raises(ValueError):fetch(CalendarOnly(Fake()),'2026-10-23','2026-10-20')
 with pytest.raises(ValueError):fetch(CalendarOnly(Fake()),'2026-10-20','2026-12-31')

@pytest.fixture(autouse=True)
def no_network(monkeypatch):
 import socket
 def fail(*a,**kw):raise AssertionError('Network forbidden in offline tests')
 monkeypatch.setattr(socket.socket,'connect',fail)
 monkeypatch.setattr(socket,'create_connection',fail)
