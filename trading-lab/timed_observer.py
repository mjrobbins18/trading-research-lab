"""Bounded read-only observer worker and independent watchdog. Not enabled by default."""
import argparse
from datetime import datetime,timezone
import fcntl
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
from zoneinfo import ZoneInfo
from session_observation_report import score
ROOT=Path(__file__).resolve().parents[2]
ET=ZoneInfo('America/New_York')
PRE_OPEN,POST_CLOSE=300,120

def plan_digest(plan):return hashlib.sha256(json.dumps(plan,sort_keys=True).encode()).hexdigest()
def calendar_manifest(plan,entry):
    """Bind one fixed plan to one broker calendar entry. The entry's provenance is not authenticated here."""
    score(plan,[],plan['open_at'])
    day=entry['date']
    opened,closed=(int(datetime.fromisoformat(f'{day}T{entry[k]}').replace(tzinfo=ET).timestamp()) for k in ('open','close'))
    if (opened,closed)!=(plan['open_at'],plan['close_at']):raise ValueError('Plan does not match broker calendar session')
    return dict(plan_sha256=plan_digest(plan),session_date=day,calendar_entry=dict(date=day,open=entry['open'],close=entry['close']),
        open_at=opened,close_at=closed,launch_not_before=opened-PRE_OPEN,launch_not_after=closed+POST_CLOSE,
        boundary_samples=plan.get('boundary_samples') is True,verified_against_calendar=True,
        alert_delivery='outbox_only',orders_authorized=False)
def check_manifest(plan,manifest):
    # Recomputing the whole manifest rejects any edited field, not only the digest.
    if manifest!=calendar_manifest(plan,manifest['calendar_entry']):raise ValueError('Launch manifest does not match plan')

class Run:
    def __init__(self,path,plan):
        score(plan,[],plan['open_at'])
        if plan['close_at']-plan['open_at']>23400:raise ValueError('Maximum one regular session')
        self.plan=plan;self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(self.path,timeout=5)
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('''CREATE TABLE IF NOT EXISTS config (id INTEGER PRIMARY KEY, payload TEXT);
        CREATE TABLE IF NOT EXISTS slots (scheduled INTEGER PRIMARY KEY, started REAL, result TEXT);
        CREATE TABLE IF NOT EXISTS boundary (phase TEXT PRIMARY KEY, started REAL, result TEXT);
        CREATE TABLE IF NOT EXISTS alerts (id INTEGER PRIMARY KEY, kind TEXT, created REAL, delivered INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS deliveries (alert_id INTEGER PRIMARY KEY, claimed REAL, outcome TEXT, message_id TEXT, recorded REAL);
        CREATE TABLE IF NOT EXISTS health (id INTEGER PRIMARY KEY, kind TEXT);''')
        payload=json.dumps(plan,sort_keys=True)
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO config VALUES (1,?)',(payload,))
            if self.db.execute('SELECT payload FROM config WHERE id=1').fetchone()[0]!=payload:
                raise ValueError('Run plan changed; retain original run')
    def close(self):self.db.close()
    def alert(self,kind,now):
        with self.db:
            old=self.db.execute('SELECT kind FROM health WHERE id=1').fetchone()
            if not old or old[0]!=kind:
                if kind!='healthy' or old:
                    self.db.execute('INSERT INTO alerts(kind,created) VALUES (?,?)',(kind,now))
                self.db.execute('INSERT OR REPLACE INTO health VALUES (1,?)',(kind,))
    def tick(self,now,execute,clock=time.time):
        if not math.isfinite(now):raise ValueError('Invalid clock')
        start,end=self.plan['open_at'],self.plan['close_at']
        boundary=self.plan.get('boundary_samples') is True
        if start<=now<end:table,key='slots',int(start+(now-start)//60*60)
        elif boundary and start-PRE_OPEN<=now<start:table,key='boundary','pre_open'
        elif boundary and end<=now<end+POST_CLOSE:table,key='boundary','post_close'
        else:return 'outside_session'
        column='scheduled' if table=='slots' else 'phase'
        # A global worker lock also prevents overlapping children from separate processes.
        with Path(str(self.path)+'.worker.lock').open('a') as lock:
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:return 'worker_busy'
            with self.db:
                changed=self.db.execute(f'INSERT OR IGNORE INTO {table} VALUES (?,?,NULL)',(key,now)).rowcount
            if not changed:return 'already_attempted'
            try:
                child=execute(45)
                report=json.loads(child.stdout)
                if not isinstance(report,dict) or report.get('orders_submitted')!=0:raise ValueError('Invalid observer result')
                result={k:report[k] for k in ('status','market','stop_file_present','open_orders','unresolved_intents','error_type') if k in report}
                result['status']='observed' if child.returncode==0 and report.get('status')=='observed' else 'halted'
                result['reconciled']=result['status']=='observed'
            except Exception as exc:result=dict(status='halted',reconciled=False,error_type=type(exc).__name__)
            # Boundary samples carry no scheduled_at, so the regular-session scorer never counts them.
            result.update({'scheduled_at':key} if table=='slots' else {'phase':key})
            result.update(started_at=now,completed_at=clock(),orders_submitted=0,decision_eligible=False)
            with self.db:self.db.execute(f'UPDATE {table} SET result=? WHERE {column}=?',(json.dumps(result),key))
            return result
    def watchdog(self,now):
        if not math.isfinite(now):raise ValueError('Invalid clock')
        start,end=self.plan['open_at'],self.plan['close_at']
        rows=self.db.execute('SELECT scheduled,started,result FROM slots ORDER BY scheduled').fetchall()
        completed=[json.loads(r[2]) for r in rows if r[2] is not None]
        if any(not math.isfinite(r['completed_at']) or r['completed_at']<r['started_at'] or r['completed_at']>now for r in completed):kind='clock_failure'
        elif any(r['status']!='observed' for r in completed):kind='review_required'
        elif now<start:kind='before_session'
        elif now>=end+120:kind='session_complete'
        else:
            last=max((r['completed_at'] for r in completed),default=start)
            kind='missing_observation' if now-last>120 else 'healthy'
        # A stopped or crashed child cannot clear the missing-slot check.
        due=range(int(start),int(min(end,now-120))+1,60) if now>=start+120 else []
        done={r['scheduled_at'] for r in completed}
        missing=[t for t in due if t<end and t not in done]
        if missing and kind in ('healthy','session_complete'):kind='missing_observation'
        self.alert(kind,now)
        return dict(status=kind,missing_slots=missing,orders_submitted=0,external_alert_delivered=False)
    def report(self,now):
        rows=[json.loads(r[0]) for r in self.db.execute('SELECT result FROM slots WHERE result IS NOT NULL')]
        result=score(self.plan,rows,now)
        if self.plan.get('boundary_samples') is True:
            # A claimed sample whose result never landed is reported as missing.
            found={p:json.loads(r) for p,r in self.db.execute('SELECT phase,result FROM boundary WHERE result IS NOT NULL')}
            result['boundary_samples']={p:found.get(p,'missing') for p in ('pre_open','post_close')}
        return result
    def claim_alert(self,now):
        """Claim the oldest unclaimed alert for one external send. A claim is never released or repeated."""
        with self.db:
            row=self.db.execute('SELECT id,kind,created FROM alerts WHERE id NOT IN (SELECT alert_id FROM deliveries) ORDER BY id LIMIT 1').fetchone()
            if not row or not self.db.execute('INSERT OR IGNORE INTO deliveries(alert_id,claimed) VALUES (?,?)',(row[0],now)).rowcount:return None
        created=datetime.fromtimestamp(row[2],timezone.utc).isoformat(timespec='seconds')
        return dict(alert_id=row[0],kind=row[1],created=row[2],
            subject=self.subject(row[0],row[1]),
            body=f'Observer health changed to {row[1]} at {created}. No trade was placed. This alert reports observer health only; it does not authorize trading.')
    def subject(self,alert_id,kind):return f'Investment Agent alert {kind} run {plan_digest(self.plan)[:8]} #{alert_id}'
    def record_alert(self,alert_id,outcome,message_id,now):
        if outcome not in ('accepted','error') or (outcome=='accepted' and not message_id):raise ValueError('Outcome must be accepted with a message ID, or error')
        with self.db:
            if not self.db.execute('UPDATE deliveries SET outcome=?,message_id=?,recorded=? WHERE alert_id=? AND outcome IS NULL',
                (outcome,message_id,now,alert_id)).rowcount:raise ValueError('Alert is not claimed or already recorded')
            if outcome=='accepted':self.db.execute('UPDATE alerts SET delivered=1 WHERE id=?',(alert_id,))
    def outbox(self):
        rows=self.db.execute('SELECT a.id,a.kind,a.created,d.alert_id,d.outcome,d.message_id FROM alerts a LEFT JOIN deliveries d ON d.alert_id=a.id ORDER BY a.id')
        return [dict(alert_id=i,kind=k,created=c,subject=self.subject(i,k),outcome=o or ('pending' if d is None else 'claimed_unrecorded'),message_id=m) for i,k,c,d,o,m in rows]

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('role',choices=['worker','watchdog','report','manifest','alerts'])
    p.add_argument('--plan',type=Path,required=True);p.add_argument('--state',type=Path,required=True)
    p.add_argument('--manifest',type=Path);p.add_argument('--calendar',type=Path)
    p.add_argument('--claim',action='store_true');p.add_argument('--record',type=int);p.add_argument('--outcome');p.add_argument('--message-id')
    a=p.parse_args()
    plan=json.loads(a.plan.read_text())
    if a.role=='manifest':
        # Offline: the calendar file must come from a separate read of the broker calendar.
        day=datetime.fromtimestamp(plan['open_at'],ET).date().isoformat()
        entries=[e for e in json.loads(a.calendar.read_text()) if e.get('date')==day]
        if len(entries)!=1:raise SystemExit('Calendar has no unique entry for the plan date')
        print(json.dumps(calendar_manifest(plan,entries[0]),indent=2));return
    live=a.role in ('worker','watchdog')
    if live and (plan.get('enabled') is not True or plan.get('calendar_verified') is not True):
        raise SystemExit('Disabled: requires an enabled, calendar-verified bounded plan')
    if live:
        if not a.manifest:raise SystemExit('Disabled: live roles require a calendar launch manifest')
        try:check_manifest(plan,json.loads(a.manifest.read_text()))
        except (ValueError,KeyError,TypeError) as exc:raise SystemExit(f'Disabled: {exc}')
    if live and not plan['open_at']-PRE_OPEN<=time.time()<plan['close_at']+POST_CLOSE:
        raise SystemExit('Outside bounded launch window')
    if a.role=='alerts' and not a.state.exists():raise SystemExit('No run state')
    run=Run(a.state,plan)
    def execute(timeout):
        return subprocess.run([sys.executable,str(ROOT/'outputs/trading-lab/observer_service.py'),
            '--journal',str(ROOT/'work/account-guard/controller.json'),'--state',str(a.state.parent/'observer.sqlite')],
            capture_output=True,text=True,timeout=timeout,cwd=ROOT)
    try:
        if a.role=='report':print(json.dumps(run.report(time.time())));return
        if a.role=='alerts':
            if a.claim:print(json.dumps(run.claim_alert(time.time())))
            elif a.record is not None:run.record_alert(a.record,a.outcome,a.message_id,time.time())
            else:print(json.dumps(run.outbox()))
            return
        # Each role is a separate bounded process. No daemon installation occurs here.
        while time.time()<plan['close_at']+120:
            now=time.time()
            if a.role=='worker':run.tick(now,execute)
            else:run.watchdog(now)
            time.sleep(min(5,max(0,plan['close_at']+120-time.time())))
        if a.role=='watchdog':print(json.dumps(run.watchdog(time.time())))
    finally:run.close()

if __name__=='__main__':main()
