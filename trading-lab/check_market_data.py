"""Bounded read-only feed health evidence; never imports or calls an order controller."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import time
from alpaca_order_adapter import PaperBroker
from market_data_policy import MarketDataError

class GetOnly:
    def __init__(self,session):self.session=session
    def request(self,method,url,**kwargs):
        if method!='GET' or not url.startswith(('https://paper-api.alpaca.markets/','https://data.alpaca.markets/')):
            raise RuntimeError('Diagnostic transport forbids this request')
        return self.session.request(method,url,**kwargs)
    def get(self,url,**kwargs):return self.request('GET',url,**kwargs)

def collect(broker,symbols=('SPY','BIL')):
    rows=[]
    for symbol in symbols:
        row=dict(symbol=symbol,feed=broker.data_feed,checked_at=datetime.now(timezone.utc).isoformat())
        try:
            m=broker.market_inputs(symbol)
            row.update(status='observed',market=m,execution_data_eligible=broker.data_feed=='sip' and m['eligibility']=='eligible')
        except MarketDataError as e:row.update(status='unavailable',reason=e.code,execution_data_eligible=False)
        except Exception as e:row.update(status='unavailable',reason='transport_or_payload_error',error_type=type(e).__name__,execution_data_eligible=False)
        rows.append(row)
    return rows

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--feed',choices=('sip','iex'),default='sip')
    p.add_argument('--samples',type=int,default=1)
    p.add_argument('--interval',type=float,default=10)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if not 1<=a.samples<=30 or not 5<=a.interval<=60:p.error('Use 1–30 samples and 5–60 second intervals')
    # Refuse to overwrite evidence; create the output before making network calls.
    with a.output.open('x') as f:
        b=PaperBroker(diagnostic_feed=a.feed);b.session=GetOnly(b.session)
        all_rows=[]
        for index in range(a.samples):
            rows=collect(b);all_rows.extend(rows)
            for row in rows:f.write(json.dumps(row)+'\n');print(json.dumps(row),flush=True)
            f.flush()
            if any(r.get('reason')=='feed_access_denied' for r in rows):break
            if index+1<a.samples:time.sleep(a.interval)
    return 0 if all(r['execution_data_eligible'] for r in all_rows) else 1

if __name__=='__main__':raise SystemExit(main())
