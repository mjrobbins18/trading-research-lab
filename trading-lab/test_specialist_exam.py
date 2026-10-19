import copy
import pytest
from specialist_exam import grade

@pytest.fixture
def case():
    expected={'case_id':'a','decision':'review','issue':'none','signal':'SPY','average':10.,'requested_exposure':0,'citations':['snapshot']}
    return expected,expected|{'explanation':'Arithmetic only; not evidence of investment advantage.'}

def test_oracle_checks_are_not_qualification(case):
    key,answer=case;r=grade([answer],[key])
    assert r['structured_passed'] and not r['expert_qualified'] and r['human_review_required']

@pytest.mark.parametrize('change',[{'requested_exposure':100},{'requested_exposure':False},{'signal':'BIL'},
    {'average':float('nan')},{'average':11},{'citations':['invented']},{'explanation':''}])
def test_wrong_or_unsafe_answer_fails(case,change):
    key,answer=case;assert not grade([answer|change],[key])['structured_passed']

def test_duplicate_or_missing_case_fails(case):
    key,answer=case
    for answers in ([],[answer,answer],[answer|{'case_id':'unknown'}]):
        with pytest.raises(ValueError):grade(answers,[key])
