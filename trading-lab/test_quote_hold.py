import pytest
from market_data_policy import await_event_time,quote_eligibility,MarketDataError

class Clock:
    def __init__(self):self.wall=100.;self.mono=0.;self.sleeps=[]
    def sleep(self,x):self.sleeps.append(x);self.wall+=x;self.mono+=x
    def hold(self,event):return await_event_time(event,lambda:self.wall,lambda:self.mono,self.sleep)

def test_small_future_event_waits_before_becoming_eligible():
    c=Clock();event=100.023
    assert quote_eligibility(c.wall,event,True)=='future_quote'
    now,held=c.hold(event)
    assert now>=event and 0<held<=.25 and sum(c.sleeps)<=.25
    assert quote_eligibility(now,event,True)=='eligible' and event==100.023

def test_far_future_event_does_not_wait_or_pass():
    c=Clock();now,held=c.hold(101)
    assert held==0 and not c.sleeps and quote_eligibility(now,101,True)=='future_quote'

def test_stalled_wall_clock_remains_ineligible_and_wait_is_bounded():
    c=Clock()
    def stalled(x):c.mono+=x;c.sleeps.append(x)
    now,held=await_event_time(100.02,lambda:c.wall,lambda:c.mono,stalled)
    assert held<=.25 and sum(c.sleeps)<=.25 and quote_eligibility(now,100.02,True)=='future_quote'

@pytest.mark.parametrize('step',[1,-1])
def test_wall_clock_jump_halts(step):
    c=Clock()
    def jump(x):c.mono+=x;c.wall+=x+step
    with pytest.raises(MarketDataError,match='clock_changed'):await_event_time(100.02,lambda:c.wall,lambda:c.mono,jump)

@pytest.mark.parametrize('event',[99.,100.])
def test_past_event_no_wait(event):
    c=Clock();now,held=c.hold(event)
    assert now==100 and held==0 and c.sleeps==[]
