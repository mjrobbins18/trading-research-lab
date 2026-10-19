"""Alpaca paper adapter for the bounded recovery test controller."""
import requests
import hashlib
import time
import math
from datetime import datetime
from alpaca_credentials import load_credentials,PAPER_ENDPOINT
from market_data_policy import load_policy, MarketDataError, quote_eligibility, validate_quote, await_event_time

class PaperBroker:
    endpoint=PAPER_ENDPOINT
    def __init__(self,drop_response=False,diagnostic_feed=None):
        self.policy=load_policy()
        if diagnostic_feed not in (None, "iex", "sip"):raise ValueError("Unsupported diagnostic feed")
        self.data_feed=diagnostic_feed or self.policy["execution_feed"]
        self.diagnostic_only=diagnostic_feed is not None
        c=load_credentials();self.session=requests.Session();self.drop_response=drop_response
        self.session.headers.update({'APCA-API-KEY-ID':c['key_id'],'APCA-API-SECRET-KEY':c['secret_key']})
    def call(self,method,path,**kwargs):
        r=self.session.request(method,self.endpoint+path,timeout=20,allow_redirects=False,**kwargs)
        if r.status_code==404 and method=='GET':return None
        if r.status_code not in (200,201,204):raise RuntimeError(f'Paper API HTTP {r.status_code}')
        return r.json() if r.content else None
    def normalize(self,o):
        if o is None:return None
        return {'order_id':o['id'],'client_order_id':o['client_order_id'],'symbol':o['symbol'],'side':o['side'],
                'qty':float(o['qty']),'limit_price':float(o['limit_price']),
                'filled_qty':float(o['filled_qty']),'status':o['status']}
    def market_inputs(self,symbol):
        if symbol not in ('SPY','BIL'):raise ValueError('Unsupported research symbol')
        started=time.time()
        clock=self.call('GET','/v2/clock')
        clock_received=time.time()
        feed=getattr(self,'data_feed','sip')
        r=self.session.get('https://data.alpaca.markets/v2/stocks/quotes/latest',
                           params={'symbols':symbol,'feed':feed},timeout=20,allow_redirects=False)
        if r.status_code!=200:
            raise MarketDataError('feed_access_denied' if r.status_code in (401,403) else
                                  'rate_limited' if r.status_code==429 else 'market_data_http_error')
        quote=r.json()['quotes'][symbol]
        now=time.time()
        timestamp=lambda value:datetime.fromisoformat(value.replace('Z','+00:00')).timestamp()
        clock_age=now-timestamp(clock['timestamp'])
        clock_rtt=clock_received-started
        clock_offset=(started+clock_received)/2-timestamp(clock['timestamp'])
        if clock_rtt<0 or clock_rtt>2 or abs(clock_offset)>1:
            raise MarketDataError('clock_health_failed')
        bid,ask=float(quote['bp']),float(quote['ap'])
        if not -2<=clock_age<=10:raise RuntimeError('Broker clock stale or local clock skewed')
        if not all(math.isfinite(p) and p>0 for p in (bid,ask)) or bid>ask:
            raise RuntimeError('Invalid market quote')
        if not isinstance(clock['is_open'],bool):raise RuntimeError('Invalid broker market status')
        quote_time=validate_quote(quote)/1_000_000_000
        received_at=now
        now,held=await_event_time(quote_time,time.time,time.monotonic,time.sleep)
        return dict(now=now,quote_time=quote_time,market_open=clock['is_open'],
                    bid=bid,ask=ask,feed=feed,received_at=received_at,evaluated_at=now,hold_seconds=held,
                    quote_age_seconds=now-quote_time,
                    eligibility=quote_eligibility(now,quote_time,clock['is_open']),
                    clock_round_trip_seconds=clock_rtt,clock_offset_seconds=clock_offset,
                    bid_exchange=quote.get('bx'),ask_exchange=quote.get('ax'),
                    quote_conditions=quote.get('c'),bid_size=quote.get('bs'),ask_size=quote.get('as'))
    def observe(self):
        account=self.call('GET','/v2/account')
        positions=self.call('GET','/v2/positions')
        orders=self.call('GET','/v2/orders',params={'status':'open','limit':500})
        if len(orders)>=500:raise RuntimeError('Open order result may be truncated')
        activities=[];token=None
        for _ in range(100):
            params={'direction':'asc','page_size':100}
            if token:params['page_token']=token
            page=self.call('GET','/v2/account/activities',params=params)
            activities.extend(page)
            if len(page)<100:break
            next_token=page[-1]['id']
            if next_token==token:raise RuntimeError('Activity pagination stalled')
            token=next_token
        else:raise RuntimeError('Activity pagination limit reached')
        after=self.call('GET','/v2/account')
        if any(account[k]!=after[k] for k in ('id','cash','long_market_value','short_market_value')):
            raise RuntimeError('Account changed during observation; retry reconciliation')
        return {'account':hashlib.sha256(account['id'].encode()).hexdigest(),
                'cash':account['cash'],'equity':account['equity'],
                'blocked':account['status']!='ACTIVE' or account['trading_blocked'] or account['account_blocked'],
                'positions':positions,'orders':orders,'activities':activities}
    def submit(self,cid,intent):
        if getattr(self,'diagnostic_only',False) or getattr(self,'data_feed','sip')!='sip':
            raise MarketDataError('diagnostic_feed_cannot_submit')
        o=self.call('POST','/v2/orders',json={'symbol':intent['symbol'],'qty':str(intent['qty']),
            'side':intent['side'],'type':'limit','limit_price':str(intent['limit_price']),
            'time_in_force':'day','client_order_id':cid})
        if self.drop_response:raise TimeoutError('Injected lost response after broker acceptance')
        return self.normalize(o)
    def lookup(self,cid):
        return self.normalize(self.call('GET','/v2/orders:by_client_order_id',params={'client_order_id':cid}))
    def cancel(self,cid):
        o=self.call('GET','/v2/orders:by_client_order_id',params={'client_order_id':cid})
        if o is None:raise RuntimeError('No broker order to cancel')
        self.call('DELETE','/v2/orders/'+o['id'])
