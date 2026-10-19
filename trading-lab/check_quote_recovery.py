"""Bounded read-only stream restart and independent SIP REST recovery evidence."""
import argparse
import json
from pathlib import Path
import time
from check_quote_stream import run
from check_market_data import GetOnly, collect
from alpaca_order_adapter import PaperBroker
from market_data_policy import quote_eligibility


def recovery_status(stream, rest, now):
    """Report independent REST availability without relabeling stream health."""
    result={}
    for row in rest:
        symbol=row['symbol'];m=row.get('market',{})
        stream_row=stream.get('last_health',{}).get('symbols',{}).get(symbol,{})
        eligible=(row.get('status')=='observed' and row.get('feed')=='sip'
                  and m.get('feed')=='sip' and m.get('eligibility')=='eligible'
                  and quote_eligibility(now,m.get('quote_time',float('nan')),m.get('market_open',False))=='eligible')
        result[symbol]={'stream_reason_at_disconnect':stream_row.get('reason','stream_unavailable'),
                        'rest_eligible_now':eligible,'rest_event_timestamp':m.get('quote_time'),
                        'execution_qualified':False}
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--cycles',type=int,default=3)
    p.add_argument('--seconds',type=int,default=15)
    a=p.parse_args()
    if not 1<=a.cycles<=3 or not 5<=a.seconds<=30:p.error('Use 1–3 cycles of 5–30 seconds')
    with a.output.open('x') as f:
        def emit(row):f.write(json.dumps(row)+'\n');f.flush()
        broker=PaperBroker(diagnostic_feed='sip');broker.session=GetOnly(broker.session)
        for cycle in range(a.cycles):
            emit({'event':'cycle_started','cycle':cycle+1})
            stream=run('sip',a.seconds,lambda row:emit({'cycle':cycle+1,**row}))
            # Each run closes its socket and discards its quote cache. REST is
            # separately labeled; it cannot make a disconnected stream healthy.
            rest=collect(broker)
            emit({'event':'rest_observation','cycle':cycle+1,'rows':rest})
            status=recovery_status(stream,rest,time.time())
            summary={'event':'cycle_result','cycle':cycle+1,'stream_status':stream['status'],
                     'symbols':status,'execution_qualified':False}
            emit(summary);print(json.dumps(summary),flush=True)
            if stream['status']!='observation_complete' or any(r['status']!='observed' for r in rest):
                return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
