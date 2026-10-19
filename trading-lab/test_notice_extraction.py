import pytest
from notice_extractor import extract
from score_notice_extraction import score


def example():
    d={'document_id':'test','text':'The quarterly cash dividend of $0.25 per share is payable on May 15, 2025 to shareholders of record on May 1, 2025.','explicit_publication_date':'2025-04-01'}
    k={'document_id':'test','amount_usd_per_share':.25,'pay_date':'2025-05-15','record_date':'2025-05-01','ex_date':None,'publication_date':'2025-04-01'}
    return d,k

def test_explicit_dates_only():
    d,k=example();a=extract(d)
    assert all(a[f]==v for f,v in k.items())
    assert a['ex_date'] is None

def test_unknown_not_guessed():
    a=extract({'document_id':'test','text':'Payment is expected next month.','explicit_publication_date':None})
    assert a['pay_date'] is None and a['publication_date'] is None

def test_ambiguous_amount_abstains():
    d,k=example();d['text']+=' Another dividend of $0.30 per share was proposed.'
    assert extract(d)['amount_usd_per_share'] is None

def test_split_supported_and_null_metrics():
    d,k=example();r=score([extract(d)],[k],[d])
    assert r['correct_fields']==5 and r['correct_supported_fields']==4

def test_inferred_exdate_fails():
    d,k=example();a=extract(d);a['ex_date']='2025-05-01'
    r=score([a],[k],[d]);assert r['unsupported_values']==1 and not r['mechanical_pass']

def test_fake_evidence_fails():
    d,k=example();a=extract(d);a['evidence']={'pay_date':'made up'}
    assert score([a],[k],[d],True)['evidence_span_errors']

def test_duplicate_documents_fail():
    d,k=example();a=extract(d)
    with pytest.raises(ValueError):score([a,a],[k],[d])
