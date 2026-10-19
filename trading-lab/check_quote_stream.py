"""Bounded diagnostic WebSocket probe. Never submits or cancels orders."""
import argparse
import json
import logging
from pathlib import Path
import time
from websockets.sync.client import connect
from websockets.exceptions import ConnectionClosed, InvalidStatus
from alpaca_credentials import load_credentials
from market_data_policy import MarketDataError, quote_timestamp_ns, await_event_time
from quote_stream_health import QuoteHealth

ERRORS={401:'not_authenticated',402:'authentication_failed',404:'authentication_timeout',
        405:'symbol_limit',406:'connection_limit',407:'slow_client',409:'feed_access_denied'}

def messages(raw):
    data=json.loads(raw)
    if not isinstance(data,list) or not all(isinstance(x,dict) for x in data):
        raise MarketDataError('invalid_stream_payload')
    for m in data:
        if m.get('T')=='error':raise MarketDataError(ERRORS.get(m.get('code'),'stream_error'))
    return data


def run(feed,seconds,emit,connector=connect,credentials=None,max_quotes=10000):
    if feed not in ('sip','iex','test') or not 5<=seconds<=60:raise ValueError('Invalid probe bounds')
    if isinstance(max_quotes,bool) or not isinstance(max_quotes,int) or not 1<=max_quotes<=100000:
        raise ValueError('Invalid message budget')
    symbols=['FAKEPACA'] if feed=='test' else ['SPY','BIL']
    health=QuoteHealth(feed,symbols);creds=credentials or load_credentials()
    # Disable protocol debug logging: authentication frames contain secrets.
    logger=logging.Logger('private-quote-probe');logger.disabled=True
    deadline=time.monotonic()+seconds
    counts={'quotes':0,'accepted':0,'rejected':0}
    try:
        with connector('wss://stream.data.alpaca.markets/v2/'+feed,open_timeout=5,
                       close_timeout=2,ping_interval=None,max_queue=32,logger=logger) as ws:
            health.connect()
            welcome=messages(ws.recv(timeout=5))
            if not any(m.get('T')=='success' and m.get('msg')=='connected' for m in welcome):
                raise MarketDataError('missing_connection_ack')
            ws.send(json.dumps({'action':'auth','key':creds['key_id'],'secret':creds['secret_key']}))
            ack=messages(ws.recv(timeout=5))
            if not any(m.get('T')=='success' and m.get('msg')=='authenticated' for m in ack):
                raise MarketDataError('missing_authentication_ack')
            health.authenticate()
            ws.send(json.dumps({'action':'subscribe','quotes':symbols}))
            emit({'event':'authenticated','feed':feed})
            next_ping=0
            while time.monotonic()<deadline:
                if time.monotonic()>=next_ping:
                    waiter=ws.ping()
                    if not waiter.wait(timeout=min(2,max(.01,deadline-time.monotonic()))):
                        raise MarketDataError('pong_timeout')
                    health.pong(time.monotonic());next_ping=time.monotonic()+5
                try:batch=messages(ws.recv(timeout=min(1,max(.01,deadline-time.monotonic()))))
                except TimeoutError:batch=[]
                for m in batch:
                    if m.get('T')=='subscription':
                        health.subscribe(m.get('quotes',[]))
                        if health.subscribed!=set(symbols):raise MarketDataError('subscription_incomplete')
                        emit({'event':'subscribed','symbols':symbols})
                    elif m.get('T')=='q':
                        if counts['quotes']>=max_quotes:raise MarketDataError('probe_message_limit')
                        counts['quotes']+=1
                        received_at=time.time()
                        try:
                            event_time=quote_timestamp_ns(m.get("t"))/1e9
                            evaluated_at,held=await_event_time(event_time,time.time,time.monotonic,time.sleep,
                                                             max_wait=min(.25,max(0,deadline-time.monotonic())))
                        except MarketDataError as exc:
                            if exc.code=="clock_changed_during_hold":raise
                            evaluated_at,held=received_at,0
                        result=health.quote(m,evaluated_at)
                        try: event_age=received_at-quote_timestamp_ns(m.get("t"))/1e9
                        except MarketDataError: event_age=None
                        emit({"event":"quote_evaluation","symbol":m.get("S"),"received_at":received_at,
                              "event_timestamp":m.get("t"),"event_age_seconds":event_age,
                              "evaluated_at":evaluated_at,"hold_seconds":held,"result":result})
                        counts['accepted' if result=='accepted' else 'rejected']+=1
                # One snapshot per loop, without raw frames or authentication data.
                emit({'event':'health',**health.snapshot(time.time(),time.monotonic())})
            result={'status':'observation_complete','counts':counts,
                    'last_health':health.snapshot(time.time(),time.monotonic()),'execution_qualified':False}
    except MarketDataError as exc:
        result={'status':'halted','reason':exc.code,'counts':counts,'execution_qualified':False}
    except InvalidStatus as exc:
        code=exc.response.status_code
        reason=('rate_limited' if code==429 else 'feed_access_denied' if code in (401,403)
                else 'transient_transport_error' if code in (502,503,504) else 'stream_handshake_failed')
        result={'status':'halted','reason':reason,'counts':counts,'execution_qualified':False}
    except (ConnectionClosed, TimeoutError, OSError) as exc:
        result={'status':'halted','reason':'transient_transport_error','error_type':type(exc).__name__,
                'counts':counts,'execution_qualified':False}
    except Exception as exc:
        result={'status':'halted','reason':'transport_or_payload_error','error_type':type(exc).__name__,
                'counts':counts,'execution_qualified':False}
    finally:
        health.disconnect()
        emit({'event':'disconnected',**health.snapshot(time.time(),time.monotonic())})
    emit({'event':'finished',**result});return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--feed',choices=('sip','iex','test'),default='sip')
    p.add_argument('--seconds',type=int,default=15)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    with a.output.open('x') as f:
        def emit(row):f.write(json.dumps(row)+'\n');f.flush()
        result=run(a.feed,a.seconds,emit)
    print(json.dumps(result))
    return 0 if result['status']=='observation_complete' else 1

if __name__=='__main__':raise SystemExit(main())
