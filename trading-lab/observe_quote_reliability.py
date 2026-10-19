"""Bounded read-only feed observation with classified reconnects. No orders."""
import argparse
import json
from pathlib import Path
import time
from check_quote_stream import run
from check_market_data import collect, GetOnly
from check_quote_recovery import recovery_status
from alpaca_order_adapter import PaperBroker

RETRYABLE={'transient_transport_error','pong_timeout','authentication_timeout'}


def stream_attempt(feed,seconds,emit):
    return run(feed,seconds,emit,max_quotes=100000)


def reconnect_probe(seconds,emit,attempt=stream_attempt,sleep=time.sleep):
    # Three connections maximum. Each attempt creates new health state.
    for index in range(3):
        result=attempt('sip',seconds,lambda row:emit({'attempt':index+1,**row}))
        if result['status']=='observation_complete':return result
        if result.get('reason') not in RETRYABLE or index==2:return result
        delay=2**index
        emit({'event':'retry_scheduled','attempt':index+1,'delay_seconds':delay,
              'reason':result['reason'],'execution_qualified':False})
        sleep(delay)
    raise AssertionError('unreachable')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--windows',type=int,default=5)
    p.add_argument('--seconds',type=int,default=60)
    a=p.parse_args()
    if not 1<=a.windows<=5 or not 5<=a.seconds<=60:p.error('Use 1–5 windows of 5–60 seconds')
    with a.output.open('x') as f:
        def emit(row):f.write(json.dumps(row)+'\n');f.flush()
        broker=PaperBroker(diagnostic_feed='sip');broker.session=GetOnly(broker.session)
        for window in range(1,a.windows+1):
            emit({'event':'window_started','window':window,'started_at':time.time()})
            stream=reconnect_probe(a.seconds,lambda row:emit({'window':window,**row}))
            if stream['status']!='observation_complete':
                emit({'event':'observation_halted','window':window,'reason':stream.get('reason')})
                print(json.dumps({'status':'halted','reason':stream.get('reason')}));return 1
            rest=collect(broker)
            emit({'event':'rest_observation','window':window,'rows':rest})
            summary={'event':'window_result','window':window,'ended_at':time.time(),
                     'counts':stream['counts'],'symbols':recovery_status(stream,rest,time.time()),
                     'execution_qualified':False}
            emit(summary);print(json.dumps(summary),flush=True)
            if any(r['status']!='observed' for r in rest):return 1
        emit({'event':'observation_complete','windows':a.windows,'execution_qualified':False})
    return 0


if __name__=='__main__':raise SystemExit(main())
