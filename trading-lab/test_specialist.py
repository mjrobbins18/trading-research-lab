import json
import pytest
from specialist_review import review


def evidence(tmp_path, passed=True):
    files={'verification.json':{'passed':passed},'signals.json':[{'date':'2026-08-31','target':'SPY','index':120,'average':110}],
           'ledger.json':[{'date':'2026-08-31'}],'provenance.json':{}}
    for name,value in files.items():(tmp_path/name).write_text(json.dumps(value))
    return tmp_path


def test_review_abstains_and_cites_hashes(tmp_path):
    packet=review(evidence(tmp_path),'2026-10-16')
    assert packet['action']=='abstain' and packet['requested_exposure']==0
    assert len(packet['evidence'])==4


def test_future_evidence_rejected(tmp_path):
    with pytest.raises(ValueError,match='Future'):
        review(evidence(tmp_path),'2026-08-01')


def test_failed_reconciliation_rejected(tmp_path):
    with pytest.raises(ValueError,match='Unreconciled'):
        review(evidence(tmp_path,False),'2026-10-16')
