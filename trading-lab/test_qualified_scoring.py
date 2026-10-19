import copy
import pytest
from qualified_extractor import extract
from score_qualified_extraction import score


def case():
    d=dict(document_id='t',text='Dividend of $0.2 per share payable on or after May 2, 2025.',explicit_publication_date='2025-04-01')
    a=extract(d)
    return d,a

def test_retained_qualifier_passes_but_does_not_confirm_cash():
    d,a=case();r=score([a],[a],[d])
    assert r['mechanical_pass'] and not r['cash_availability_confirmed']
    assert r['correct_populated_text_facts']==2

def test_flattened_qualifier_fails():
    d,a=case();k=copy.deepcopy(a);a['pay_date']['kind']='scheduled'
    r=score([a],[k],[d])
    assert not r['mechanical_pass'] and r['validation_failures']==1

def test_invented_exdate_fails():
    d,a=case();k=copy.deepcopy(a);a['ex_date']=copy.deepcopy(a['pay_date']);a['ex_date']['kind']='ex_dividend'
    assert not score([a],[k],[d])['mechanical_pass']

def test_duplicate_answers_fail():
    d,a=case()
    with pytest.raises(ValueError):score([a,a],[a],[d])
