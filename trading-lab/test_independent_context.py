from evaluate_independent_context import evaluate
from context_extractor import extract
from run_context_experiment import semantic

DOC={'document_id':'a','text':'Dividend $1.00 per share payable May 1, 2025.'}
ANSWER=extract(DOC)
KEY=semantic(ANSWER)


def test_missing_and_malformed_answers_fail():
    for answer in (None,{},[],[{}],[{'document_id':'a','events':None}]):
        result=evaluate(answer,[DOC],[KEY])
        assert not result['mechanical_pass']
        assert result['semantic_matches']==0


def test_duplicate_ids_never_pass():
    result=evaluate([ANSWER,ANSWER],[DOC],[KEY])
    assert not result['coverage_ok']
    assert not result['mechanical_pass']


def test_valid_candidate_and_extra_record():
    assert evaluate([ANSWER],[DOC],[KEY])['mechanical_pass']
    extra=dict(ANSWER,document_id='unexpected')
    assert not evaluate([ANSWER,extra],[DOC],[KEY])['mechanical_pass']
