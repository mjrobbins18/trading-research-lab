"""Explicit market-data policy. IEX is permitted only for diagnostics."""
import json
from pathlib import Path

POLICY_PATH=Path(__file__).with_name('market-data-policy.json')

class MarketDataError(RuntimeError):
    def __init__(self,code):
        self.code=code
        super().__init__(code)

def load_policy(path=POLICY_PATH):
    p=json.loads(Path(path).read_text())
    if p != {'execution_feed':'sip','max_quote_age_seconds':60,'max_clock_round_trip_seconds':2,'max_clock_offset_seconds':1}:
        raise ValueError('Unsupported market-data policy; explicit code review required')
    return p

def quote_eligibility(now,quote_time,market_open):
    age=now-quote_time
    if not market_open:return 'market_closed'
    if age<0:return 'future_quote'
    if not 0<=age<=60:return 'stale_or_invalid_quote'
    return 'eligible'


def quote_timestamp_ns(value):
    """Keep exchange nanoseconds for ordering; reject timestamps without UTC zone."""
    import re
    from datetime import datetime,timezone
    if not isinstance(value,str):raise MarketDataError('invalid_quote_timestamp')
    match=re.fullmatch(r'(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d{1,9}))?(?:Z|\+00:00)',value)
    if not match:raise MarketDataError('invalid_quote_timestamp')
    try:
        seconds=int(datetime.fromisoformat(match[1]).replace(tzinfo=timezone.utc).timestamp())
    except ValueError:raise MarketDataError('invalid_quote_timestamp') from None
    return seconds*1_000_000_000+int((match[2] or '').ljust(9,'0'))


def validate_quote(quote):
    """Conservative research policy: regular quotes, positive displayed sizes."""
    import math
    if not isinstance(quote,dict):raise MarketDataError('invalid_quote_payload')
    timestamp=quote_timestamp_ns(quote.get('t'))
    prices=[]
    for key in ('bp','ap'):
        x=quote.get(key)
        if isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) or x<=0:
            raise MarketDataError('invalid_quote_price')
        prices.append(x)
    if prices[0]>prices[1]:raise MarketDataError('crossed_quote')
    for key in ('bs','as'):
        x=quote.get(key)
        if isinstance(x,bool) or not isinstance(x,int) or x<=0:
            raise MarketDataError('invalid_quote_size')
    for key in ('bx','ax'):
        if not isinstance(quote.get(key),str) or not quote[key].strip():
            raise MarketDataError('missing_quote_exchange')
    # This is a restrictive lab allowlist, not a claim that other codes are wrong.
    if quote.get('c')!=['R']:raise MarketDataError('unsupported_quote_condition')
    return timestamp


def await_event_time(event_time,wall_clock,monotonic,sleep,max_wait=.25):
    """Quarantine a slightly future event; never rewrite or grant negative age.

Return the evaluation wall time and elapsed monotonic delay. A bounded failure
returns the still-future time for the normal eligibility gate to reject.
"""
    import math
    now=wall_clock()
    if not all(math.isfinite(x) for x in (event_time,now,max_wait)) or not 0<=max_wait<=.25:
        raise MarketDataError('invalid_event_time_wait')
    start=monotonic()
    lead=event_time-now
    if not 0<lead<=max_wait:return now,0.0
    previous_elapsed=0.0
    for _ in range(8):
        elapsed=monotonic()-start
        remaining=max_wait-elapsed
        if remaining<=0:break
        sleep(min(event_time-now+.001,remaining))
        after=wall_clock();elapsed=monotonic()-start
        # Large wall-clock steps need investigation, not automatic admission.
        if not math.isfinite(after) or abs((after-now)-(elapsed-previous_elapsed))>.05:
            raise MarketDataError('clock_changed_during_hold')
        now=after
        if now>=event_time:return now,elapsed
        previous_elapsed=elapsed
    return now,max(0.0,monotonic()-start)
