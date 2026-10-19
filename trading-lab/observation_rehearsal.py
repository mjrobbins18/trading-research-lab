"""Offline decision-eligibility rehearsal. No order submission interface."""
import json
import math
from uuid import uuid4
from observer_service import observe

class Rehearsal:
    """Caller supplies a simulated clock; this is not a running scheduler."""
    def __init__(self, store):
        self.store=store
        self.epoch=uuid4().hex
        self.fresh=False
        store.db.execute('CREATE TABLE IF NOT EXISTS decisions (id INTEGER PRIMARY KEY, payload TEXT)')
        store.db.commit()

    def record(self, now, scheduled, reason):
        decision=dict(now=now,scheduled=scheduled,epoch=self.epoch,
                      eligible=reason=='eligible',reason=reason,orders_submitted=0,
                      order_authority=False)
        # Persist the decision and its alert transition together.
        with self.store.db:
            self.store.db.execute('INSERT INTO decisions(payload) VALUES (?)',(json.dumps(decision),))
            signature='rehearsal:'+reason
            previous=self.store.get('rehearsal_status')
            if previous!=signature and (previous is not None or reason!='eligible'):
                self.store.db.execute('INSERT INTO alerts(payload) VALUES (?)',(json.dumps(decision),))
            self.store.put('rehearsal_status',signature)
        return decision

    def tick(self, controller, scheduled, started, completed):
        # Time validation precedes observation, so bad schedule metadata cannot clear a halt.
        times=(scheduled,started,completed)
        if not all(isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x) for x in times):
            raise ValueError('Finite simulated times required')
        previous=float(self.store.get('rehearsal_completed','-1'))
        if not scheduled<=started<=completed or completed<=previous:
            return self.record(completed,scheduled,'invalid_clock')
        report=observe(controller,self.store)
        reason='eligible'
        if report['status']!='observed':
            reason='observation_failed'
            if report.get('error_type')=='Halt':
                with self.store.db:self.store.put('rehearsal_integrity_halt','1')
        elif report.get('stop_file_present'):reason='stop_file'
        elif report.get('open_orders') or report.get('unresolved_intents'):reason='pending_order'
        elif set(report.get('market',{}))!={'SPY','BIL'}:reason='missing_market'
        elif not all(m.get('feed')=='sip' for m in report['market'].values()):reason='wrong_feed'
        elif not all(m['market_open'] for m in report['market'].values()):reason='market_closed'
        elif not all(m['fresh_open_quote'] for m in report['market'].values()):reason='ineligible_quote'
        if completed-scheduled>=120:reason='missed_deadline'
        if self.store.db.execute('SELECT count(*) FROM alerts WHERE delivered=0 AND attempts>0').fetchone()[0]:
            reason='notification_failed'
        if self.store.get('rehearsal_integrity_halt')=='1':reason='integrity_review_required'
        with self.store.db:self.store.put('rehearsal_completed',completed)
        self.fresh=True
        return self.record(completed,scheduled,reason)

    def watchdog(self, now):
        if not isinstance(now,(int,float)) or isinstance(now,bool) or not math.isfinite(now):
            raise ValueError('Finite simulated time required')
        last=self.store.get('rehearsal_completed')
        if self.store.get('rehearsal_integrity_halt')=='1':reason='integrity_review_required'
        elif last is not None and now<float(last):reason='invalid_clock'
        elif last is not None and now-float(last)>120:reason='missing_observation'
        elif not self.fresh or last is None:reason='restart_requires_observation'
        else:reason='watchdog_only_no_decision'
        return self.record(now,None,reason)
