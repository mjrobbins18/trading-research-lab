from copy import deepcopy
import pytest
from context_extractor import extract,validate


def doc(text):return dict(document_id='test',text=text,explicit_publication_date='2025-01-01')


@pytest.mark.parametrize('phrase,kind',[('on','scheduled'),('on or after','earliest')])
def test_payment_relation(phrase,kind):
    d=doc(f'Dividend of 51 cents per common share, payable {phrase} March 1, 2025 to holders of record at the close of business February 14, 2025.')
    a=extract(d);e=a['events'][0]
    assert e['amount']['value']==.51
    assert e['pay_date']['kind']==kind
    assert e['record_date']['cutoff']=='close_of_business'
    assert validate(a,d)['passed']


def test_missing_year_not_inferred():
    d=doc('Dividend $1.00 per share, payable July 1 to shareowners of record June 13.')
    a=extract(d)
    assert a['events'][0]['pay_date']['status']=='ambiguous'
    assert a['events'][0]['pay_date']['value'] is None
    a['events'][0]['pay_date'].update(value='2025-07-01',status='explicit')
    assert not validate(a,d)['passed']


def test_all_rows_and_quarterly_amount():
    d=doc('Annual dividend $1.00 per share in quarterly installments of $0.25 per share.\nRecord Dates | Payable Dates\nMarch 1, 2025 | March 15, 2025\nJune 1, 2025 | June 15, 2025\nSeptember 1, 2025 | September 15, 2025\nDecember 1, 2025 | January 15, 2026')
    a=extract(d)
    assert len(a['events'])==4
    assert all(e['amount']['value']==.25 for e in a['events'])
    assert a['events'][-1]['pay_date']['value']=='2026-01-15'
    assert validate(a,d)['passed']


def test_conflicting_payment_dates():
    a=extract(doc('Payable March 1, 2025. Payable March 2, 2025.'))
    assert a['events'][0]['pay_date']['status']=='ambiguous'
    assert a['events'][0]['pay_date']['value'] is None


@pytest.mark.parametrize('mutation',['qualifier','unit','number','cash','bad_schema'])
def test_reject_corruption(mutation):
    d=doc('Dividend $1.00 per share payable on or after March 1, 2025.')
    a=deepcopy(extract(d));e=a['events'][0]
    if mutation=='qualifier':e['pay_date']['kind']='scheduled'
    if mutation=='unit':e['amount']['evidence']='$1.00'
    if mutation=='number':e['amount']['value']=2
    if mutation=='cash':a['cash_available_confirmed']=True
    if mutation=='bad_schema':e['pay_date']='2025-03-01'
    assert not validate(a,d)['passed']


def test_invalid_calendar_date_remains_unresolved():
    a=extract(doc('Payable February 30, 2025.'))
    assert a['events'][0]['pay_date']['value'] is None
    assert a['events'][0]['pay_date']['status']=='ambiguous'
