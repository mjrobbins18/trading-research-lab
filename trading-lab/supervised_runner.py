"""Bounded, read-only paper runner. No order submission or cancellation path."""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import time
from uuid import uuid4

from order_controller import Controller,Halt,TERMINAL
from alpaca_order_adapter import PaperBroker
from market_data_policy import MarketDataError


def cycle(controller):
    if 'account_guard' not in controller.state:raise Halt('Explicit account checkpoint required')
    controller.bind_account(controller.state['account_guard']['account'])
    # Recover first, so an accepted-but-unacknowledged order has a known broker ID.
    for key in list(controller.state['intents']):
        controller.recover(key)
    account=controller.reconcile_account()
    for record in controller.state['intents'].values():
        if 'order_id' not in record:raise Halt('Missing broker order identity')
    known={r['client_order_id'] for r in controller.state['intents'].values()}
    if any(o['client_order_id'] not in known for o in account['orders']):
        raise Halt('Outside open order requires review')
    market={symbol:controller.broker.market_inputs(symbol) for symbol in ('SPY','BIL')}
    readiness={symbol:bool(m['market_open'] and 0<=m['now']-m['quote_time']<=60) for symbol,m in market.items()}
    return dict(status='observed',cash=account['cash'],equity=account['equity'],
                positions=len(account['positions']),open_orders=len(account['orders']),
                recovered_intents=len(controller.state['intents']),
                unresolved_intents=sum(r['status'] not in TERMINAL for r in controller.state['intents'].values()),
                market={s:dict(feed=m['feed'],market_open=m['market_open'],
                               quote_age_seconds=round(m['now']-m['quote_time'],3),fresh_open_quote=readiness[s])
                        for s,m in market.items()},
                stop_file_present=(controller.path.parent/'STOP').exists(),orders_submitted=0)


def run(controller,audit,cycles=3,interval=10,sleep=time.sleep):
    if not 1<=cycles<=30 or not 5<=interval<=60:raise ValueError('Use 1-30 cycles and 5-60 seconds between cycles')
    audit=Path(audit);audit.parent.mkdir(parents=True,exist_ok=True)
    run_id=uuid4().hex
    for index in range(cycles):
        try:
            report=cycle(controller)
        except Exception as exc:
            # Do not log exception text: requests exceptions can contain request details.
            report={'status':'halted','error_type':type(exc).__name__,'orders_submitted':0}
            if isinstance(exc,MarketDataError):report['reason']=exc.code
            if isinstance(exc,Halt):report['reason']=str(exc)  # Controller messages contain no request data.
        report.update(run_id=run_id,cycle=index+1,checked_at=datetime.now(timezone.utc).isoformat())
        with audit.open('a') as stream:
            stream.write(json.dumps(report,sort_keys=True)+'\n');stream.flush();os.fsync(stream.fileno())
        print(json.dumps(report),flush=True)
        if report['status']=='halted':return 1
        if index+1<cycles:sleep(interval)
    return 0


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--journal',type=Path,default=Path('work/account-guard/controller.json'))
    parser.add_argument('--audit',type=Path,default=Path('outputs/supervised-runner-observations.jsonl'))
    parser.add_argument('--cycles',type=int,default=3)
    parser.add_argument('--interval',type=float,default=10)
    args=parser.parse_args()
    controller=Controller(args.journal,PaperBroker())
    try:return run(controller,args.audit,args.cycles,args.interval)
    finally:controller.close()

if __name__=='__main__':raise SystemExit(main())
