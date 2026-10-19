from copy import deepcopy
import pytest
from dividend_source_adapters import extract,validate


def doc(text,currency='USD'):
    return {'document_id':'fixture','issuer':'Test issuer','currency_context':currency,'text':text}


def table():
    return doc('Common Stock receives an annual dividend of USD 1.00 per share in four quarterly installments of USD 0.25 per share.\nRecord Dates | Payable Dates\nMarch 1, 2025 | March 15, 2025\nJune 1, 2025 | June 15, 2025\nSeptember 1, 2025 | September 15, 2025\nDecember 1, 2025 | January 15, 2026')


def classes():
    return doc('The quarterly dividend is USD 1.0065 per share for Common Stock and Series A and Series B preferred shares. Payment is on or after May 15, 2024. Common Stock ownership is measured at the close of business on April 19, 2024; ownership of the named preferred classes is measured at the start of business on April 19, 2024.')


def test_full_table():
    d=table();a=extract(d)
    assert len(a['events'])==4
    assert a['events'][-1]['dates']['payment']['value']=='2026-01-15'
    assert all(e['amount']['value']=='0.25' for e in a['events'])
    assert validate(a,d)['passed']


@pytest.mark.parametrize('change',['drop','duplicate','swap_column','annual_amount','change_currency','reorder'])
def test_schedule_corruption(change):
    d=table();a=extract(d)
    if change=='drop':a['events'].pop()
    if change=='duplicate':a['events'].append(deepcopy(a['events'][0]))
    if change=='swap_column':a['events'][0]['dates']['payment']['value']='2025-03-01'
    if change=='annual_amount':a['events'][0]['amount']['value']='1.00'
    if change=='change_currency':a['events'][0]['amount']['currency']='DKK'
    if change=='reorder':a['events'].reverse()
    assert validate(a,d)['status']=='rejected'


def test_class_cutoffs_and_earliest():
    d=classes();a=extract(d)
    assert [e['security']['class'] for e in a['events']]==['common','preferred_A','preferred_B']
    assert [e['dates']['record']['cutoff'] for e in a['events']]==['close_of_business','start_of_business','start_of_business']
    assert all(e['dates']['payment']['qualification']=='earliest' for e in a['events'])
    assert validate(a,d)['passed']


@pytest.mark.parametrize('change',['merge','cutoff','payment','identity'])
def test_class_corruption(change):
    d=classes();a=extract(d)
    if change=='merge':a['events'].pop()
    if change=='cutoff':a['events'][1]['dates']['record']['cutoff']='close_of_business'
    if change=='payment':a['events'][0]['dates']['payment']['qualification']='scheduled'
    if change=='identity':a['events'][1]['security']['class']='ADR'
    assert validate(a,d)['status']=='rejected'


@pytest.mark.parametrize('change',['bad_row','missing_row','missing_year','split','missing_currency'])
def test_incomplete_source_requires_review(change):
    d=table()
    if change=='bad_row':d['text']+='\nTBD | TBD'
    if change=='missing_row':d['text']=d['text'].replace('June 1, 2025 | June 15, 2025\n','')
    if change=='missing_year':d['text']=d['text'].replace('January 15, 2026','January 15')
    if change=='split':d['text']='Post-split amounts. '+d['text']
    if change=='missing_currency':d['text']=d['text'].replace('USD ','$');d['currency_context']=None
    a=extract(d);a['unresolved']=[]
    assert validate(a,d)['status']=='review_required'


def test_inline_schedule():
    d=doc('Common stock. Four quarterly payments are each USD 0.2075 per share. The complete record-date/payable-date schedule is: March 15, 2024 / April 1, 2024; May 10, 2024 / May 28, 2024; Aug. 16, 2024 / Sept. 3, 2024; Dec. 13, 2024 / Jan. 6, 2025.')
    a=extract(d);assert len(a['events'])==4
    assert validate(a,d)['passed']


def test_unrecognized_class_phrase_requires_review():
    d=classes();d['text']=d['text'].replace('start of business','an unspecified time')
    a=extract(d);assert validate(a,d)['status']=='review_required'
