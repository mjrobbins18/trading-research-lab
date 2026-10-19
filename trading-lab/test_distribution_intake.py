from copy import deepcopy
import pytest
from distribution_intake import route


def record():
    fields = dict(amount='0.10', ex_date='2022-03-01', record_date='2022-03-02', pay_date='2022-03-07', amount_basis='nominal_per_share')
    return dict(symbol='BIL', ex_date='2022-03-01', sources=[dict(fields, lineage='issuer', source_ref='issuer-file#row1'),dict(fields, lineage='vendor', source_ref='vendor-file#row1')])


def test_matching_record_routes_without_trading_authority():
    r=route([record()])[0]
    assert r['route']=='routine_accounting_candidate'
    assert not r['trading_authorized'] and not r['historical_signal_use_authorized']

@pytest.mark.parametrize('field,value,reason', [
 ('amount','0','payment_existence_conflict'),
 ('amount','0.0215','amount_conflict'),
 ('pay_date','2008-02-11','invalid_date_order'),
 ('record_date','2022-03-03','record_date_conflict'),
 ('amount_basis','split_adjusted','unknown_or_adjusted_amount_basis'),
 ('amount','NaN','missing_or_invalid_field'),
 ('pay_date',None,'missing_or_invalid_field')])
def test_conflicts_route_for_review(field,value,reason):
    r=record();r['sources'][1][field]=value
    result=route([r])[0]
    assert result['route']=='specialist_review' and reason in result['reasons']


def test_duplicate_not_silently_merged():
    r=record()
    assert all('duplicate_event_identity' in x['reasons'] for x in route([r,deepcopy(r)]))


def test_vendor_republication_is_not_independent():
    r=record();r['sources'][1]['lineage']='issuer'
    assert 'shared_or_unknown_source_lineage' in route([r])[0]['reasons']


def test_unknown_metadata_blocks_even_matching_values():
    r=record();r['sources'][0].pop('source_ref')
    assert 'missing_source_provenance' in route([r])[0]['reasons']


def test_tolerance_does_not_erase_tiny_payment_existence_conflict():
    r=record();r['sources'][0]['amount']='0';r['sources'][1]['amount']='0.0000001'
    assert 'payment_existence_conflict' in route([r])[0]['reasons']


def test_open_issue_cannot_be_cleared_by_matching_sources():
    r=record();r['open_issues']=['issuer_correction_pending']
    assert route([r])[0]['route']=='specialist_review'


def test_missing_date_does_not_hide_amount_conflict():
    r=record();r['sources'][0]['amount']='0';r['sources'][1]['pay_date']=None
    result=route([r])[0]
    assert {'amount_conflict','payment_existence_conflict','missing_or_invalid_field'} <= set(result['reasons'])
