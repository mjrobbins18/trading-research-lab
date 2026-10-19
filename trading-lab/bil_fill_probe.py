"""One-share BIL paper fill test; fixed identity, $100 ceiling, existing journal."""
import argparse
from datetime import datetime, timezone
from decimal import ROUND_CEILING
import json
from pathlib import Path
from account_guard import number
from alpaca_order_adapter import PaperBroker
from order_controller import Controller,Halt
from supervised_runner import cycle

ROOT=Path(__file__).resolve().parents[2]
KEY='bil-fill-probe-01'

def run(phase,journal,broker):
    c=Controller(journal,broker)
    try:
        if phase not in ('prepare','submit','recover','cancel'):raise ValueError('Unknown phase')
        if phase in ('recover','cancel'):
            if KEY not in c.state['intents']:raise Halt('No existing fill-test intent')
            r=c.cancel(KEY) if phase=='cancel' else c.recover(KEY)
            observation=cycle(c)
            return dict(phase=phase,record=r,observation=observation,account_guard=c.state['account_guard'])
        observation=cycle(c)
        if KEY in c.state['intents']:
            return dict(phase=phase,status='already_recorded_do_not_resubmit',record=c.recover(KEY))
        if observation['positions'] or observation['open_orders'] or observation['stop_file_present']:
            raise Halt('Flat, reconciled account without stop file required')
        m=broker.market_inputs('BIL')
        if not m['market_open'] or not 0<=m['now']-m['quote_time']<=60:
            raise Halt('Fresh open-market BIL quote required')
        bid,ask=number(m['bid']),number(m['ask'])
        if not 0<bid<=ask or ask-bid>number('.05'):raise Halt('Invalid or wide BIL quote')
        limit=(ask+number('.01')).quantize(number('.01'),rounding=ROUND_CEILING)
        if limit>100:raise Halt('BIL test price ceiling exceeded')
        spent=sum((number(r['intent']['qty'])*number(r['intent']['limit_price']) for r in c.state['intents'].values()),number(0))
        if spent+limit>1000 or limit>number(observation['cash']):raise Halt('Test budget or cash insufficient')
        intent=dict(decision_id=KEY,symbol='BIL',side='buy',qty=1,limit_price=float(limit))
        proposal=dict(intent=intent,quote=m,observation=observation,remaining_budget_before=str(1000-spent))
        if phase=='prepare':return dict(phase=phase,status='prepared',proposal=proposal)
        record=c.submit(intent,m['now'],m['quote_time'],m['market_open'],float(observation['cash']))
        return dict(phase=phase,record=record,proposal=proposal)
    finally:c.close()

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('phase',choices=('prepare','submit','recover','cancel'));a=p.parse_args()
    try:
        result=run(a.phase,ROOT/'work/account-guard/controller.json',PaperBroker());code=0
    except Exception as exc:
        result=dict(phase=a.phase,status='halted',error_type=type(exc).__name__);code=1
        if isinstance(exc,Halt):result['reason']=str(exc)
    result['checked_at']=datetime.now(timezone.utc).isoformat()
    # Do not print the full historical account checkpoint.
    if 'account_guard' in result:
        g=result.pop('account_guard');result['reconciled_state']={k:g[k] for k in ('cash','positions')}
        result['seen_activity_count']=len(g['seen'])
    root=ROOT/'outputs/bil-fill-probe-01';root.mkdir(parents=True,exist_ok=True)
    with (root/'audit.jsonl').open('a') as f:f.write(json.dumps(result)+'\n')
    print(json.dumps(result));return code

if __name__=='__main__':raise SystemExit(main())
