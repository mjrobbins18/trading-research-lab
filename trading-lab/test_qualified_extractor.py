import pytest
from qualified_extractor import extract,iso


def doc(text):return dict(document_id='test',text=text,explicit_publication_date=None)

def test_qualified_payment_is_not_exact():
    r=extract(doc('A dividend of $1.05 per share, payable on or after November 17, 2025.'))
    assert r['pay_date']['kind']=='earliest' and r['pay_date']['value']=='2025-11-17'
    assert 'on or after' in r['pay_date']['evidence']

def test_abbreviations_and_record_cutoff():
    r=extract(doc('Dividend of $0.91 per share, payable Dec. 11, 2025 to shareholders of record at the close of business on Nov. 20, 2025.'))
    assert r['pay_date']['value']=='2025-12-11'
    assert r['record_date']['value']=='2025-11-20' and r['record_date']['cutoff']=='close_of_business'
    assert r['ex_date']['value'] is None

def test_old_to_new_amount():
    assert extract(doc('$1.24 per share to $1.30 per share.'))['amount_usd_per_share']==1.30

def test_contextual_date_labeled():
    r=extract(doc('quarterly cash dividend of $0.01 per share on April 2, 2025.'))
    assert r['pay_date']['status']=='contextual'

def test_explicit_pay_verb():
    r=extract(doc('The company will pay its dividend of $0.10 per share on April 2, 2025.'))
    assert r['pay_date']['status']=='explicit'

def test_conflicting_dates_abstain():
    r=extract(doc('Payable May 1, 2025. Payable May 2, 2025.'))
    assert r['pay_date']['status']=='ambiguous' and r['pay_date']['value'] is None

@pytest.mark.parametrize('bad',['February 30, 2025','Jan 0, 2025','Not a date'])
def test_invalid_calendar_date_rejected(bad):
    with pytest.raises(ValueError):iso(bad)

def test_validator_rejects_lost_payment_qualifier():
    from qualified_validator import validate
    d=doc('Dividend of $0.2 per share payable on or after May 2, 2025.')
    a=extract(d);assert validate(a,d)['passed']
    a['pay_date']['kind']='scheduled'
    assert 'pay_date:lost_lower_bound' in validate(a,d)['errors']

def test_validator_never_confirms_cash():
    from qualified_validator import validate
    d=doc('Dividend of $0.2 per share payable May 2, 2025.');a=extract(d)
    r=validate(a,d);assert r['passed'] and not r['cash_available_confirmed']

def test_validator_rejects_date_not_in_evidence():
    from qualified_validator import validate
    d=doc('Dividend of $0.2 per share payable May 2, 2025.');a=extract(d)
    a['pay_date']['value']='2025-05-03'
    assert 'pay_date:date_not_in_evidence' in validate(a,d)['errors']
