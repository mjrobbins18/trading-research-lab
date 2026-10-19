from copy import deepcopy
import pytest
from dividend_events import extract,validate,date_value


def doc(text,currency='USD'):
    return {'document_id':'fixture','issuer':'Example issuer','text':text,'currency_context':currency}


def normal():
    return doc('The quarterly dividend is $1.355 for each common-stock share. The annualized dividend is $5.42 per share. The dividend is payable June 28, 2024 to holders of record at close of business June 7, 2024.')


def test_quarterly_not_annualized():
    d=normal();a=extract(d)
    assert a['events'][0]['amount']['value']=='1.355'
    assert a['events'][0]['amount']['period']=='quarterly'
    assert validate(a,d)['passed']


@pytest.mark.parametrize('field,value',[('value','5.42'),('currency','SEK'),('period','annualized'),('unit','per_ADR')])
def test_amount_relationship_corruption(field,value):
    d=normal();a=extract(d);a['events'][0]['amount'][field]=value
    assert validate(a,d)['status']=='rejected'


@pytest.mark.parametrize('class_name',['ADR','preferred_A','ordinary_B'])
def test_wrong_security_class(class_name):
    d=normal();a=extract(d);a['events'][0]['security']['class']=class_name
    assert validate(a,d)['status']=='rejected'


def test_record_cutoff_does_not_contaminate_payment():
    d=normal();a=extract(d);dates=a['events'][0]['dates']
    assert dates['payment']['cutoff'] is None
    assert dates['record']['cutoff']=='close_of_business'
    assert validate(a,d)['passed']
    dates['payment']['cutoff']='close_of_business'
    assert not validate(a,d)['passed']


@pytest.mark.parametrize('currency',['SEK','DKK','USD'])
def test_original_currency_and_expected_payment(currency):
    d=doc(f'The interim dividend is {currency} 1.43 per common share. It is expected to disburse 1 April 2025 to holders of record 27 March 2025.')
    a=extract(d)
    assert a['events'][0]['amount']['currency']==currency
    assert a['events'][0]['dates']['payment']['qualification']=='expected'
    assert validate(a,d)['passed']
    a['events'][0]['dates']['payment']['qualification']='scheduled'
    assert validate(a,d)['status']=='rejected'


def test_cents_for_each_share():
    d=doc('The quarterly dividend is 48.5 cents for each common share, payable December 16, 2024 to holders of record at close of business November 29, 2024.')
    a=extract(d)
    assert a['events'][0]['amount']['value']=='0.485'
    assert validate(a,d)['passed']


def test_earliest_not_exact():
    d=doc('The quarterly dividend is $1.00 per common share, payable on or after May 15, 2024 to holders of record April 19, 2024.')
    a=extract(d);assert validate(a,d)['passed']
    a['events'][0]['dates']['payment']['qualification']='scheduled'
    assert validate(a,d)['status']=='rejected'


@pytest.mark.parametrize('text',[
 'Common Stock and Series A preferred shares receive a quarterly dividend of $1.00 per share, payable May 15, 2024 to holders of record April 19, 2024.',
 'A quarterly dividend of $1.00 per common share is payable July 1 to holders of record June 13.',
 'Common stock receives four quarterly payments of $0.25 per share. The complete payment schedule follows.',
 'The quarterly common-share distribution has complicated terms.',
 'A quarterly dividend of $0.25 per common share on a post-split basis is payable July 1, 2025 to holders of record June 13, 2025.'
])
def test_unsupported_cannot_be_cleared_by_candidate(text):
    d=doc(text);a=extract(d);a['unresolved']=[]
    result=validate(a,d)
    assert result['status']=='review_required'
    assert not result['passed']


def test_bare_dollar_without_currency_context_requires_review():
    d=normal();d.pop('currency_context')
    assert validate(extract(d),d)['status']=='review_required'


def test_adr_not_ordinary_share():
    d=doc('The quarterly distribution is USD 0.25 per ADR, payable July 1, 2025 to holders of record June 13, 2025.')
    a=extract(d);assert validate(a,d)['passed']
    assert a['events'][0]['amount']['unit']=='per_ADR'


def test_source_change_and_duplicate_event():
    d=normal();a=extract(d);changed=dict(d,text=d['text']+' Revised.')
    assert validate(a,changed)['status']=='rejected'
    a['events'].append(deepcopy(a['events'][0]))
    assert validate(a,d)['status']=='rejected'


@pytest.mark.parametrize('bad',[None,{},[],{'schema_version':5,'events':[{}]}])
def test_malformed_response_fails_closed(bad):
    assert validate(bad,normal())['status']=='rejected'


@pytest.mark.parametrize('raw,expected',[('14 August 2026','2026-08-14'),('Aug. 14, 2026','2026-08-14'),('17 August',None),('February 30, 2025',None)])
def test_dates(raw,expected):assert date_value(raw)==expected


def test_currency_metadata_change_is_bound():
    d=normal();a=extract(d);changed=dict(d,currency_context='DKK')
    assert validate(a,changed)['status']=='rejected'


def test_adr_amount_in_share_units_requires_review():
    d=doc('The quarterly ADR dividend is USD 0.25 per share, payable July 1, 2025 to holders of record June 13, 2025.')
    assert validate(extract(d),d)['status']=='review_required'


def test_invalid_calendar_value_rejected_even_on_unsupported_source():
    d=doc('The quarterly dividend is $1.00 per common share, payable July 1 to holders of record June 13.')
    a=extract(d);a['events'][0]['dates']['payment'].update(status='explicit',value='2025-02-30')
    assert validate(a,d)['status']=='rejected'
