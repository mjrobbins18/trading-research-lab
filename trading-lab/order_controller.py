"""Bounded paper-order controller. Durable intents; no automatic ambiguous resubmission.

One journal per account/controller. All callers must share it. Broker adapter must
return cumulative filled quantities, not incremental execution messages.
"""
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import account_guard

PAPER = 'https://paper-api.alpaca.markets'
TERMINAL = {'filled', 'canceled', 'expired', 'rejected'}
OPEN = {'new','accepted','pending_new','partially_filled','pending_cancel','accepted_for_bidding'}


class Halt(RuntimeError):
    pass


class Controller:
    def __init__(self, path, broker):
        self.path = Path(path)
        self.broker = broker
        if broker.endpoint != PAPER:
            raise Halt('Paper endpoint required')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = open(str(self.path)+'.lock','a')
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.lock.close()
            raise Halt('Another controller owns this journal') from None
        try:
            self.state = json.loads(self.path.read_text()) if self.path.exists() else {'intents':{}}
            if not isinstance(self.state.get('intents'),dict):raise Halt('Invalid journal')
        except Exception:
            self.close()
            raise

    def close(self):
        self.lock.close()
        if getattr(self,'account_lock',None):self.account_lock.close()

    def save(self):
        temp = self.path.with_suffix('.tmp')
        with temp.open('w') as f:
            json.dump(self.state,f,indent=2);f.flush();os.fsync(f.fileno())
        os.replace(temp,self.path)
        fd=os.open(self.path.parent,os.O_RDONLY)
        try:os.fsync(fd)
        finally:os.close(fd)

    def checkpoint(self):
        if 'account_guard' in self.state:raise Halt('Checkpoint already exists; do not reset risk history')
        snapshot=self.broker.observe()
        guard=account_guard.checkpoint(snapshot)
        self.bind_account(snapshot['account'])
        self.state['account_guard']=guard
        self.save()

    def bind_account(self,identity):
        if getattr(self,'account_lock',None):
            if self.account_identity!=identity:raise Halt('Account binding mismatch')
            return
        root=Path(getattr(self.broker,'account_lock_dir',Path(__file__).resolve().parent/'.local/account-locks'))
        root.mkdir(parents=True,exist_ok=True)
        handle=(root/(hashlib.sha256(identity.encode()).hexdigest()+'.lock')).open('a+')
        try:
            fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
            handle.seek(0);owner=handle.read()
            if owner and owner!=str(self.path.resolve()):raise Halt('Account belongs to another journal; explicit migration required')
            if not owner:
                handle.write(str(self.path.resolve()));handle.flush();os.fsync(handle.fileno())
        except Exception:
            handle.close();raise Halt('Account lock or journal ownership conflict') from None
        self.account_lock=handle;self.account_identity=identity

    def reconcile_account(self):
        if 'account_guard' not in self.state:raise Halt('Explicit account checkpoint required')
        self.bind_account(self.state['account_guard']['account'])
        snapshot=self.broker.observe()
        known={r['order_id'] for r in self.state['intents'].values() if 'order_id' in r}
        try:
            self.validate_executions(snapshot)
            guard=account_guard.reconcile(self.state['account_guard'],snapshot,known)
        except account_guard.ReconciliationError as exc:
            raise Halt(str(exc)) from None
        self.state['account_guard']=guard
        self.save()
        return snapshot

    def validate_executions(self, snapshot):
        # Validate before committing the account guard, on both observation and
        # submission paths. A known order ID alone does not authenticate a fill.
        records={}
        for record in self.state['intents'].values():
            oid=record.get('order_id')
            if oid is None:
                if record['filled_qty']:raise Halt('Missing broker order identity')
                continue
            if oid in records:raise Halt('Duplicate broker order identity')
            records[oid]=record
        totals={oid:account_guard.number(0) for oid in records}
        for event in snapshot['activities']:
            if event['activity_type']!='FILL' or event['order_id'] not in records:
                continue  # The account guard rejects unrecognized new activities.
            record=records[event['order_id']];intent=record['intent']
            qty,price=account_guard.number(event['qty']),account_guard.number(event['price'])
            limit=account_guard.number(intent['limit_price'])
            outside_limit=(price>limit if intent['side']=='buy' else price<limit)
            if (event['symbol']!=intent['symbol'] or event['side']!=intent['side']
                or intent['side'] not in ('buy','sell')
                or qty<=0 or price<=0 or outside_limit):
                raise Halt('Execution conflicts with original limit intent')
            totals[event['order_id']]+=qty
        for oid,record in records.items():
            if totals[oid]!=account_guard.number(record['filled_qty']):
                raise Halt('Order fills and account activities disagree')

    def submit(self, intent, now, quote_time, market_open, cash):
        if intent['decision_id'] in self.state['intents']:
            old=self.state['intents'][intent['decision_id']]
            if old['intent'] != intent:raise Halt('Decision ID reused with changed order')
            return self.recover(intent['decision_id'])
        if (self.path.parent/'STOP').exists():raise Halt('Stop file present')
        if not market_open or not 0 <= now-quote_time <= 60:raise Halt('Market closed or quote stale/future')
        qty,limit=intent['qty'],intent['limit_price']
        if (intent['symbol'] not in ['SPY','BIL'] or intent['side'] not in ('buy','sell')
            or (intent['side']=='sell' and intent.get('reduce_only') is not True)
            or not isinstance(qty,int) or isinstance(qty,bool) or qty!=1
            or not math.isfinite(limit) or not 0 < limit <= 1000
            or not math.isfinite(cash)
            or (intent['side']=='buy' and qty*limit > cash)):raise Halt('Research order limit exceeded')
        if any(x['status'] not in TERMINAL for x in self.state['intents'].values()):raise Halt('Unresolved intent exists')
        account=self.reconcile_account()
        spent=sum(account_guard.number(r['intent']['qty'])*account_guard.number(r['intent']['limit_price'])
                  for r in self.state['intents'].values())
        try:account_guard.permit(self.state['account_guard'],account,intent,spent)
        except account_guard.ReconciliationError as exc:raise Halt(str(exc)) from None
        # Production adapter refreshes inputs after potentially slow account reads.
        if hasattr(self.broker,'market_inputs'):
            inputs=self.broker.market_inputs(intent['symbol'])
            if not inputs['market_open'] or not 0<=inputs['now']-inputs['quote_time']<=60:
                raise Halt('Fresh broker inputs prohibit submission')
        if (self.path.parent/'STOP').exists():raise Halt('Stop file present')
        key=intent['decision_id']
        cid='lab-'+hashlib.sha256(key.encode()).hexdigest()[:32]
        record={'intent':dict(intent),'client_order_id':cid,'status':'submitting','filled_qty':0.0}
        self.state['intents'][key]=record
        self.save()  # Commit before sending; a timeout never triggers another POST.
        try:
            snapshot=self.broker.submit(cid,intent)
        except Exception:
            record['status']='unknown';self.save();raise Halt('Submission outcome unknown; reconcile by client ID') from None
        return self.apply(key,snapshot)

    def recover(self,key):
        record=self.state['intents'][key]
        snapshot=self.broker.lookup(record['client_order_id'])
        if snapshot is None:raise Halt('Broker has no visible record; do not resubmit')
        return self.apply(key,snapshot)

    def apply(self,key,snapshot):
        r=self.state['intents'][key];i=r['intent']
        if snapshot['client_order_id']!=r['client_order_id'] or any(snapshot[k]!=i[k] for k in ['symbol','side','qty','limit_price']):raise Halt('Broker intent mismatch')
        status=snapshot['status'];filled=float(snapshot['filled_qty'])
        if not math.isfinite(filled) or not r['filled_qty'] <= filled <= i['qty']:raise Halt('Invalid or regressed cumulative fill')
        if status not in OPEN|TERMINAL:raise Halt('Unsupported broker order state')
        if status=='filled' and filled!=i['qty']:raise Halt('Filled status with incomplete quantity')
        if r['status'] in TERMINAL and (status!=r['status'] or filled!=r['filled_qty']):raise Halt('Terminal state changed; investigate')
        if 'order_id' in snapshot:
            if 'order_id' in r and r['order_id']!=snapshot['order_id']:raise Halt('Broker order ID changed')
            r['order_id']=snapshot['order_id']
        r.update(status=status,filled_qty=filled);self.save();return dict(r)

    def cancel(self,key):
        r=self.recover(key)
        if r['status'] not in TERMINAL:
            self.broker.cancel(r['client_order_id'])
            return self.recover(key)  # Cancellation is not assumed until broker confirms.
        return r
