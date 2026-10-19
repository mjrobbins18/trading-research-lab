import pytest
from check_quote_recovery import recovery_status


def row(**changes):
    return {'symbol':'BIL','status':'observed','feed':'sip','market':{
        'feed':'sip','quote_time':100.,'market_open':True,'eligibility':'eligible',**changes}}


def test_independent_rest_available_without_stream_event():
    result=recovery_status({'last_health':{'symbols':{'BIL':{'reason':'missing_quote'}}}},[row()],101)['BIL']
    assert result['rest_eligible_now']
    assert result['stream_reason_at_disconnect']=='missing_quote'
    assert not result['execution_qualified']


@pytest.mark.parametrize('changes,now',[
    ({},161),({},99),({'market_open':False},101),({'feed':'iex'},101),
    ({'eligibility':'clock_health_failed'},101)])
def test_rest_cannot_bypass_eligibility(changes,now):
    assert not recovery_status({},[row(**changes)],now)['BIL']['rest_eligible_now']


def test_unavailable_rest_does_not_reuse_prior_result():
    assert recovery_status({},[row()],101)['BIL']['rest_eligible_now']
    bad={'symbol':'BIL','status':'unavailable','feed':'sip','reason':'feed_access_denied'}
    assert not recovery_status({},[bad],102)['BIL']['rest_eligible_now']
