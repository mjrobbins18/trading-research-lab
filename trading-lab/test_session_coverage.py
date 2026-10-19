from session_coverage import summarize


def row(time,opened):
    return dict(checked_at=time,status='observed',market={s:{'market_open':opened} for s in ('SPY','BIL')})

def test_requires_actual_close_between_distinct_sessions():
    a=row('2026-10-16T18:00:00+00:00',True)
    b=row('2026-10-16T21:00:00+00:00',False)
    c=row('2026-10-19T14:00:00+00:00',True)
    assert summarize([a,b,c])['coverage_complete']
    assert not summarize([a,c])['coverage_complete']
    assert not summarize([a,b])['coverage_complete']

def test_same_day_reopen_is_not_multisession():
    assert not summarize([row('2026-10-16T14:00:00+00:00',True),row('2026-10-16T15:00:00+00:00',False),row('2026-10-16T16:00:00+00:00',True)])['coverage_complete']

def test_halt_does_not_count_as_closed():
    result=summarize([row('2026-10-16T18:00:00+00:00',True),dict(status='halted',checked_at='2026-10-16T21:00:00+00:00'),row('2026-10-19T14:00:00+00:00',True)])
    assert not result['coverage_complete'] and result['halted_observations']==1

def test_empty():
    assert summarize([])['latest_status']=='no_observations'
