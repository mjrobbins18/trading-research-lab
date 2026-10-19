import copy
import pytest
from score_conflict02 import score

@pytest.fixture
def reference():
    return [dict(case_id='test',decision='partial_resolution',issue_codes=['unsupported_ex_date'],
                 resolved=dict(amount_per_share='0.30',ex_date=None,record_date='2025-01-01',pay_date='2025-02-01',currency=None,security_classes=['A','B'],components=[]),evidence_ids=['E1'],needs_human_review=True)]

def test_equivalent_decimals_and_unordered_classes(reference):
    answer=copy.deepcopy(reference);answer[0]['resolved'].update(amount_per_share='0.3',security_classes=['B','A'])
    assert score(reference,answer)['exact_matches']==1

def test_invented_date_and_missed_issue_fail(reference):
    answer=copy.deepcopy(reference);answer[0]['resolved']['ex_date']='2025-01-01';answer[0]['issue_codes']=[]
    result=score(reference,answer)
    assert result['exact_matches']==0 and result['incorrect_populated_fields']==1 and result['missed_issues']==1

def test_duplicates_and_missing_cases_rejected(reference):
    for answer in ([],reference*2):
        with pytest.raises(ValueError): score(reference,answer)

def test_missing_unknown_field_is_not_a_match(reference):
    answer=copy.deepcopy(reference);del answer[0]['resolved']['currency']
    assert score(reference,answer)['correct_fields']==6
