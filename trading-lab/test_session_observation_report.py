import pytest
from session_observation_report import score
P=dict(open_at=1000,close_at=1180,cadence_seconds=60)
def row(t):return dict(scheduled_at=t,started_at=t+1,completed_at=t+5,status='observed',reconciled=True,
 orders_submitted=0,decision_eligible=True,market={s:dict(feed='sip',market_open=True,quote_age_seconds=1) for s in ('SPY','BIL')})
def test_complete_grid():
 r=score(P,[row(t) for t in (1000,1060,1120)],1300)
 assert r['observation_gate_passed'] and r['observation_availability']==1
 assert not r['continuous_quote_coverage_measured'] and not r['unattended_trading_qualified']
def test_incomplete_does_not_count_future_as_missing():
 r=score(P,[row(1000)],1120)
 assert r['due_slots']==1 and r['pending_slots']==2 and r['observation_availability']==1
 assert not r['observation_gate_passed']
def test_missing_in_denominator():
 r=score(P,[row(1000)],1300)
 assert r['statuses']['missing']==2 and r['quote_eligibility_fraction']['BIL']==1/3
@pytest.mark.parametrize('age',[-.001,61,float('nan'),True])
def test_bad_quote_never_eligible(age):
 a=row(1000);a['market']['BIL']['quote_age_seconds']=age
 r=score(P,[a],1300);assert r['quote_eligible_slots']['BIL']==0 and r['unsafe_decisions']==1
@pytest.mark.parametrize('change',[dict(started_at=999),dict(completed_at=1120),dict(reconciled=False),dict(orders_submitted=1),dict(status='halted'),dict(stop_file_present=True)])
def test_failed_gate_withholds(change):
 r=score(P,[row(1000)|change],1300)
 assert not r['observation_gate_passed'] and r['unsafe_decisions']==1
def test_duplicate_not_counted_twice():
 r=score(P,[row(1000),row(1000)],1300)
 assert r['statuses']['duplicate_slot']==1 and r['quote_eligible_slots']['SPY']==0
def test_outside_grid_does_not_fill_slot():
 r=score(P,[row(1001)],1300)
 assert r['outside_grid_rows']==1 and r['statuses']['missing']==3
def test_empty_early_report_not_pass():
 r=score(P,[],999);assert r['observation_availability'] is None and not r['observation_gate_passed']
