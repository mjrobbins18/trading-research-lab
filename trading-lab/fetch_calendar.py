"""One read-only paper calendar request for launch manifests. Never touches orders or account state."""
import argparse
from datetime import date,datetime,timezone
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
import requests
from alpaca_credentials import PAPER_ENDPOINT,load_credentials
URL=PAPER_ENDPOINT+'/v2/calendar'

class CalendarOnly:
    def __init__(self,session):self.session=session
    def request(self,method,url,**kwargs):
        p=urlsplit(url)
        if method!='GET' or p.scheme!='https' or p.netloc!='paper-api.alpaca.markets' or p.path!='/v2/calendar':
            raise PermissionError('Calendar transport permits only GET /v2/calendar on paper')
        return self.session.request(method,url,timeout=20,allow_redirects=False,**kwargs)

def normalize(rows):
    out={}
    for r in rows:
        day,o,c=r['date'],r['open'],r['close']
        date.fromisoformat(day)
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',day) or not all(re.fullmatch(r'([01]\d|2[0-3]):[0-5]\d',t) for t in (o,c)) or o>=c:
            raise ValueError('Malformed calendar row')
        if day in out:raise ValueError('Duplicate calendar date')
        out[day]=dict(date=day,open=o,close=c)
    return list(out.values())

def fetch(transport,start,end):
    a,b=date.fromisoformat(start),date.fromisoformat(end)
    if not 0<=(b-a).days<=14:raise ValueError('Range must be 0 to 14 days')
    r=transport.request('GET',URL,params=dict(start=start,end=end))
    # One attempt only; a failure is recorded, not retried.
    if r.status_code!=200:raise RuntimeError(f'Calendar HTTP {r.status_code}')
    return normalize(r.json())

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--start',required=True);p.add_argument('--end',required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False)
    c=load_credentials();s=requests.Session()
    s.headers.update({'APCA-API-KEY-ID':c['key_id'],'APCA-API-SECRET-KEY':c['secret_key']})
    started=datetime.now(timezone.utc).isoformat()
    result=dict(requested_at=started,endpoint=URL,start=a.start,end=a.end,requests=1,orders_submitted=0,account_endpoints_called=0)
    try:
        rows=fetch(CalendarOnly(s),a.start,a.end)
        (a.output/'calendar.json').write_text(json.dumps(rows,indent=2)+'\n')
        result.update(status='ok',sessions=len(rows))
    except Exception as exc:result.update(status='failed',error_type=type(exc).__name__,error=str(exc)[:80])
    result['completed_at']=datetime.now(timezone.utc).isoformat()
    (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    return int(result['status']!='ok')

if __name__=='__main__':raise SystemExit(main())
