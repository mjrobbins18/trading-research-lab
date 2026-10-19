from copy import deepcopy
from evaluate_shadow_pilot import compare
from test_dividend_shadow import sample


def test_semantic_formatting_does_not_change_claims():
    docs, proposals = sample()
    reference = deepcopy(proposals[0])
    reference['events'][0]['amount']['value'] = '1.000'
    result = compare(proposals[0], reference, docs[0])
    assert result['semantic_match']
    assert result['extra_claim_count'] == result['missing_claim_count'] == 0


def test_wrong_amount_is_one_missing_and_one_extra_claim():
    docs, proposals = sample()
    bad = deepcopy(proposals[0])
    bad['events'][0]['amount']['value'] = '2.00'
    result = compare(bad, proposals[0], docs[0])
    assert not result['semantic_match']
    assert result['extra_claim_count'] == result['missing_claim_count'] == 1
    assert result['validation']['status'] == 'rejected'


def test_missing_event_has_no_extra_claims():
    docs, proposals = sample()
    bad = deepcopy(proposals[0])
    bad['events'] = []
    result = compare(bad, proposals[0], docs[0])
    assert result['missing_claim_count'] > 0
    assert result['extra_claim_count'] == 0
