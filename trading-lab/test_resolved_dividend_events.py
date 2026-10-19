from copy import deepcopy
import pytest
from resolved_dividend_events import extract,validate,fingerprint


def doc():return dict(document_id='test',issuer='Example',text='The quarterly dividend is 48.5 cents for each common share, payable Dec. 16 to holders of record at close of business Nov. 29.')
def claim(field,value,cls=None):return dict(field=field,value=value,security_class=cls,support_type='direct',evidence=[dict(url='https://example.com/official-dividends',locator='2024 row',summary='USD and complete event dates explicitly stated',retrieved_at='2026-10-16')])
def bundle(d):return dict(document_id=d['document_id'],packet_sha256=fingerprint(d),claims=[claim('currency_context','USD'),claim('payment_date','2024-12-16','common'),claim('record_date','2024-11-29','common')])


def test_resolved_metadata_bound_and_original_unchanged():
    d=doc();original=deepcopy(d);b=bundle(d);a=extract(d,b)
    assert d==original
    assert a['events'][0]['amount']['currency']=='USD'
    assert a['events'][0]['dates']['payment']['value']=='2024-12-16'
    assert validate(a,d,b)['passed']
    assert validate(a,d,b)['human_review_pending']
    assert not validate(a,d,b)['external_evidence_independently_verified']


@pytest.mark.parametrize('mutation',['source','amount','date','currency','provenance'])
def test_binding_tamper(mutation):
    d=doc();b=bundle(d);a=extract(d,b)
    if mutation=='source':d['text']+=' Revised.'
    if mutation=='amount':a['events'][0]['amount']['value']='9.99'
    if mutation=='date':a['events'][0]['dates']['payment']['value']='2024-12-17'
    if mutation=='currency':b['claims'][0]['value']='DKK'
    if mutation=='provenance':b['claims'][0]['evidence'][0]['summary']='Changed evidence'
    assert validate(a,d,b)['status']=='rejected'


def test_wrong_date_components_rejected():
    d=doc();b=bundle(d);b['claims'][1]['value']='2024-12-17'
    with pytest.raises(ValueError):extract(d,b)


@pytest.mark.parametrize('mutation',['missing_evidence','duplicate','wrong_class','invalid_date','wrong_document'])
def test_invalid_claims(mutation):
    d=doc();b=bundle(d)
    if mutation=='missing_evidence':b['claims'][0]['evidence']=[]
    if mutation=='duplicate':b['claims'].append(deepcopy(b['claims'][0]))
    if mutation=='wrong_class':b['claims'][1]['security_class']='ADR'
    if mutation=='invalid_date':b['claims'][1]['value']='2024-02-30'
    if mutation=='wrong_document':b['document_id']='other'
    assert validate({},d,b)['status']=='rejected'


def test_currency_only_leaves_missing_years_unresolved():
    d=doc();b=bundle(d);b['claims']=b['claims'][:1]
    a=extract(d,b);assert validate(a,d,b)['status']=='review_required'
