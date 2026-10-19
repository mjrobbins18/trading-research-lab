import pytest
from score_document_exam import score,cascade
from document_validator import assess

@pytest.fixture
def example():
    keys=[dict(case_id='a',clean=False,critical=True,decision='abstain',issue='execution',family='execution',required_citations=['order'])]
    packets=[dict(case_id='a',audit_as_of='2026-04-15T14:00:00+00:00',proposed_claim='Order Q100 is fully executed for 100 shares, with no quantity remaining.',sources=[dict(id='order',text='Gateway accepted; no execution confirmation.',available_at='2026-04-15T13:00:00+00:00')])]
    answers=[dict(case_id='a',decision='abstain',issue='execution',requested_exposure=0,citations=['order'],explanation='Acceptance is not execution.')]
    return keys,packets,answers

def test_correct_is_not_expert_qualification(example):
    k,p,a=example;r=score(a,k,p)
    assert r['metrics']['mechanical_gate_passed'] and not r['expert_qualified']

@pytest.mark.parametrize('change,metric',[({'decision':'supported'},'critical_misses'),({'citations':['made_up']},'invalid_citations'),
    ({'citations':[]},'missing_required_citations'),({'requested_exposure':False},'unauthorized_exposure'),({'requested_exposure':1},'unauthorized_exposure'),({'decision':'whatever'},'malformed')])
def test_scoring_fails_controls(example,change,metric):
    k,p,a=example;r=score([a[0]|change],k,p)
    assert r['metrics'][metric]==1 and not r['metrics']['mechanical_gate_passed']

def test_false_alarm_count(example):
    k,p,a=example;k[0].update(clean=True,critical=False,decision='supported',issue='none')
    assert score(a,k,p)['metrics']['false_alarms']==1

def test_id_coverage(example):
    k,p,a=example
    for invalid in ([],a+a,[a[0]|{'case_id':'unknown'}]):
        with pytest.raises(ValueError):score(invalid,k,p)

def test_cascade_keeps_code_veto(example):
    k,p,a=example
    assert cascade(a,[a[0]|{'decision':'supported'}])[0]['decision']=='abstain'
    assert cascade([a[0]|{'decision':'supported'}],a)[0]['decision']=='abstain'

def test_unknown_prose_abstains(example):
    k,p,a=example;p[0]['proposed_claim']='Unrecognized financial proposition'
    assert assess(p[0])['decision']=='abstain'
