"""Independent formalization of the six human-approved source interpretations."""
import json
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
import pytest
import dividend_events_v6 as v6

ROOT=Path(__file__).resolve().parent/'fixtures'
DOCS=json.loads((ROOT/'resolved-independent-evaluation/documents.json').read_text())
REVIEW=json.loads((ROOT/'dividend-v6/reviewed-development-semantics.json').read_text())

def semantic(events):
    result=[]
    for source in events:
        e=deepcopy(source)
        e.pop('evidence',None);e.pop('event_id',None);e.pop('source_sha256',None)
        e['amount']['value']=str(Decimal(e['amount']['value']).normalize())
        result.append(e)
    return sorted(result,key=lambda x:json.dumps(x,sort_keys=True))

@pytest.mark.parametrize('doc',DOCS,ids=[d['document_id'] for d in DOCS])
def test_matches_human_reviewed_interpretation(doc):
    actual=v6.extract(doc)
    assert semantic(actual['events'])==semantic(REVIEW['events_by_document'][doc['document_id']])
    validation=v6.validate(actual,doc)
    assert not validation['errors']
    if doc['document_id'] in REVIEW['required_review_documents']:
        assert validation['status']=='review_required'
    else:
        assert validation['status']=='consistent_research_record'
    assert validation['trading_authorized'] is False
    assert actual['cash_available_confirmed'] is False
