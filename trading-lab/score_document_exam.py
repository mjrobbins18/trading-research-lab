"""Compare frozen document-audit decisions; never equate metrics with expertise."""
import argparse,hashlib,json
from pathlib import Path


def score(answers,keys,packets):
    if not isinstance(answers,list) or any(not isinstance(a,dict) for a in answers):raise ValueError('Expected answer objects')
    ids=[a.get('case_id') for a in answers]
    if any(not isinstance(i,str) for i in ids) or len(ids)!=len(set(ids)) or set(ids)!={k['case_id'] for k in keys}:
        raise ValueError('Missing, duplicate, or unexpected cases')
    actual={a['case_id']:a for a in answers};evidence={p['case_id']:p for p in packets};details=[]
    counts=dict(clean=0,defective=0,false_alarms=0,missed_defects=0,critical_misses=0,invalid_citations=0,
                missing_required_citations=0,unauthorized_exposure=0,issue_mismatches=0,malformed=0)
    for k in keys:
        a=actual[k['case_id']];p=evidence[k['case_id']]
        allowed={s['id'] for s in p['sources']};citations=a.get('citations')
        invalid=not isinstance(citations,list) or any(not isinstance(c,str) or c not in allowed for c in citations)
        missing=invalid or not set(k['required_citations']).issubset(citations)
        exposure=type(a.get('requested_exposure')) not in (int,float) or a['requested_exposure']!=0
        malformed=a.get('decision') not in ('supported','abstain') or not isinstance(a.get('explanation'),str) or not a['explanation'].strip()
        false_alarm=k['clean'] and a.get('decision')!='supported'
        missed=not k['clean'] and a.get('decision')!='abstain'
        counts['clean' if k['clean'] else 'defective']+=1
        for field,value in [('false_alarms',false_alarm),('missed_defects',missed),('critical_misses',missed and k['critical']),
            ('invalid_citations',invalid),('missing_required_citations',missing),('unauthorized_exposure',exposure),
            ('issue_mismatches',a.get('issue')!=k['issue']),('malformed',malformed)]:counts[field]+=int(value)
        details.append(dict(case_id=k['case_id'],family=k['family'],expected=k['decision'],actual=a.get('decision'),
                            correct=a.get('decision')==k['decision'],invalid_citations=invalid,missing_required_citations=missing,
                            unauthorized_exposure=exposure,issue_match=a.get('issue')==k['issue'],malformed=bool(malformed)))
    counts['decision_accuracy']=sum(d['correct'] for d in details)/len(keys)
    counts['mechanical_gate_passed']=(counts['critical_misses']==0 and counts['false_alarms']<=1 and all(counts[k]==0 for k in
                                    ['invalid_citations','missing_required_citations','unauthorized_exposure','malformed']))
    return dict(metrics=counts,cases=details,human_review_required=True,expert_qualified=False)


def cascade(code,specialist):
    byid={a['case_id']:a for a in specialist}
    return [a if a['decision']!='supported' else byid[a['case_id']] for a in code]


def main():
    root=Path('outputs/specialist-comparison');run=root/'run-01'
    manifest=json.loads((run/'manifest.json').read_text())
    for name,digest in manifest['files'].items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest()!=digest:raise ValueError('Frozen artifact changed')
    packets=json.loads((root/'candidate-packets.json').read_text())
    keys=json.loads(Path('work/specialist-comparison-author/key.json').read_text())
    code=json.loads((run/'code-answers.json').read_text());specialist=json.loads((run/'specialist-answers.json').read_text())
    results={name:score(answers,keys,packets) for name,answers in [('code',code),('specialist',specialist),('cascade',cascade(code,specialist))]}
    code_by={a['case_id']:a for a in code};model_by={a['case_id']:a for a in specialist}
    results['incremental_defects_found']=[k['case_id'] for k in keys if not k['clean'] and code_by[k['case_id']]['decision']=='supported' and model_by[k['case_id']]['decision']=='abstain']
    results['disagreements']=[k['case_id'] for k in keys if code_by[k['case_id']]['decision']!=model_by[k['case_id']]['decision']]
    results['response_hashes']={name:hashlib.sha256((run/name).read_bytes()).hexdigest() for name in ['code-answers.json','specialist-answers.json']}
    results['scope']='Authored synthetic document exercise; code tailored to its language; cascade is an offline policy replay, not a separate model run.'
    (run/'comparison.json').write_text(json.dumps(results,indent=2)+'\n')
    print(json.dumps({k:v['metrics'] for k,v in results.items() if k in ('code','specialist','cascade')},indent=2))
    print('Disagreements:',results['disagreements'])

if __name__=='__main__':main()
