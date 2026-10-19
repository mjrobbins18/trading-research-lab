"""Probe frozen validator limitations without changing benchmark answers."""
import json
from copy import deepcopy
from pathlib import Path
from context_extractor import validate
from run_context_experiment import semantic

root=Path('outputs/context-extraction')
docs={d['document_id']:d for d in json.loads((root/'documents.json').read_text())}
answers={a['document_id']:a for a in json.loads((root/'run-01/code-answers.json').read_text())}
keys={a['document_id']:a for a in json.loads((root/'reference.json').read_text())}
probes=[]
def probe(name,docid,mutate):
    answer=deepcopy(answers[docid]);mutate(answer)
    result=validate(answer,docs[docid])
    probes.append(dict(name=name,document_id=docid,validator_rejected=not result['passed'],reference_rejected=semantic(answer)!=keys[docid],errors=result['errors']))

if __name__=='__main__':
    import argparse
    ap=argparse.ArgumentParser();ap.add_argument('--guard',action='store_true');use_guard=ap.parse_args().guard
    if use_guard:
        from context_guard import validate
    probe('flatten_earliest','pg-july-2025',lambda a:a['events'][0]['pay_date'].update(kind='scheduled'))
    probe('invent_missing_year','ko-july-2025',lambda a:a['events'][0]['pay_date'].update(value='2025-10-01',status='explicit'))
    probe('wrong_amount','wmt-2023',lambda a:a['events'][0]['amount'].update(value=2.28))
    probe('unsupported_cash','pg-july-2025',lambda a:a.update(cash_available_confirmed=True))
    probe('drop_installment','wmt-2023',lambda a:a['events'].pop())
    probe('wrong_table_column','wmt-2023',lambda a:a['events'][0]['pay_date'].update(value='2023-03-17'))
    probe('crop_qualifier','pg-july-2025',lambda a:a['events'][0]['pay_date'].update(kind='scheduled',evidence='August 15, 2025'))
    probe('false_absence','explicit-ex',lambda a:a['events'][0]['ex_date'].update(value=None,kind='not_stated',status='absent',cutoff=None,evidence=None))
    result={'scope':'Post-benchmark development regression' if use_guard else 'Post-run adversarial probes; not additional independent benchmark cases','probes':probes,'validator_rejected':sum(p['validator_rejected'] for p in probes),'reference_rejected':sum(p['reference_rejected'] for p in probes),'total':len(probes)}
    (root/'run-01'/('guard-audit.json' if use_guard else 'validation-audit.json')).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
