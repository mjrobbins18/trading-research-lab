"""Bounded $1 SPY paper-order recovery probe using the existing controller journal.

Each invocation performs one phase. No new checkpoints or automatic resubmission.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from account_guard import number
from alpaca_order_adapter import PaperBroker
from order_controller import Controller, Halt, TERMINAL
from supervised_runner import cycle

ROOT = Path(__file__).resolve().parents[2]
KEY = 'execution-readiness-03-recovery-01'
INTENT = dict(decision_id=KEY, symbol='SPY', side='buy', qty=1, limit_price=1.0)


def run_phase(phase, journal, broker):
    c = Controller(journal, broker)
    try:
        if phase not in ('prepare', 'submit', 'recover', 'cancel'):
            raise ValueError('Unknown phase')
        if phase in ('recover', 'cancel'):
            if KEY not in c.state['intents']: raise Halt('No persisted probe intent')
            if c.state['intents'][KEY]['intent'] != INTENT: raise Halt('Probe intent mismatch')
            record = c.cancel(KEY) if phase == 'cancel' else c.recover(KEY)
            observation = cycle(c)
            return dict(phase=phase, record=record, observation=observation,
                        terminal=record['status'] in TERMINAL)
        observation = cycle(c)
        spent = sum((number(r['intent']['qty'])*number(r['intent']['limit_price'])
                     for r in c.state['intents'].values()), number(0))
        if KEY in c.state['intents']:
            return dict(phase=phase, status='already_recorded_do_not_resubmit', record=c.recover(KEY))
        if observation['positions'] or observation['open_orders']:
            raise Halt('Probe requires a flat account with no open orders')
        if observation['stop_file_present']: raise Halt('Stop file present')
        if spent + 1 > 1000: raise Halt('Insufficient remaining research budget')
        market = broker.market_inputs('SPY')
        if not market['market_open'] or not 0 <= market['now']-market['quote_time'] <= 60:
            raise Halt('Fresh open-market quote required')
        if number(market['ask']) <= 10: raise Halt('Cannot establish distant limit')
        if number(observation['cash']) < 1: raise Halt('Insufficient reconciled cash')
        proposal = dict(intent=INTENT, maximum_order_cost_usd='1.00',
                        remaining_submission_budget_usd=str(1000-spent),
                        observation=observation, quote=market)
        if phase == 'prepare': return dict(phase=phase, status='prepared', proposal=proposal)
        # Caller chooses the broker adapter's deliberate response-loss mode.
        try:
            record = c.submit(INTENT,market['now'],market['quote_time'],market['market_open'],float(observation['cash']))
        except Halt:
            record = c.state['intents'].get(KEY)
            if record is None or record['status'] != 'unknown': raise
            return dict(phase=phase, status='outcome_unknown_recover_by_client_id', record=record, proposal=proposal)
        return dict(phase=phase, status='submitted', record=record, proposal=proposal)
    finally:
        c.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('prepare','submit','recover','cancel'))
    args = parser.parse_args()
    root = ROOT/'outputs/controller-recovery-probe-03'
    root.mkdir(parents=True, exist_ok=True)
    try:
        result = run_phase(args.phase, ROOT/'work/account-guard/controller.json',
                           PaperBroker(drop_response=args.phase=='submit'))
        code = 0
    except Exception as exc:
        # Requests exceptions can contain credentials. Persist only their type.
        result = dict(phase=args.phase, status='halted', error_type=type(exc).__name__)
        if isinstance(exc,Halt): result['reason']=str(exc)
        code = 1
    result['checked_at'] = datetime.now(timezone.utc).isoformat()
    # Append separate evidence for each invocation; never overwrite earlier phases.
    with (root/'audit.jsonl').open('a') as stream:
        stream.write(json.dumps(result)+'\n')
    print(json.dumps(result))
    return code

if __name__ == '__main__': raise SystemExit(main())
