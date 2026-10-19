"""Compare qualified date proposals without treating them as available cash."""
import json,hashlib
from pathlib import Path
from qualified_validator import validate

FACTS=('amount_usd_per_share','pay_date','record_date','ex_date','publication_date')
DATE_KEYS=('value','kind','status','cutoff')


def semantic(value,field):
    if field=='amount_usd_per_share':return value
    if not isinstance(value,dict):return None
    return {k:value.get(k) for k in DATE_KEYS}


def score(answers,key,docs):
    expected={k['document_id']:k for k in key};sources={d['document_id']:d for d in docs}
    if not isinstance(answers,list) or any(not isinstance(a,dict) for a in answers):raise ValueError('Answer objects required')
    ids=[a.get('document_id') for a in answers]
    if any(not isinstance(i,str) for i in ids) or len(ids)!=len(set(ids)) or set(ids)!=set(expected):raise ValueError('Document coverage mismatch')
    rows=[];validations=[]
    for answer in answers:
        k=expected[answer['document_id']];doc=sources[answer['document_id']]
        validations.append({'document_id':answer['document_id'],**validate(answer,doc)})
        for field in FACTS:
            truth=semantic(k[field],field);actual=semantic(answer.get(field),field)
            accepted=[truth]+[semantic(x,field) for x in k.get('accepted_alternatives',{}).get(field,[])]
            correct=field in answer and actual in accepted
            if field=='amount_usd_per_share' and actual is not None and type(actual) not in (int,float):correct=False
            populated=k[field] is not None if field=='amount_usd_per_share' else k[field]['value'] is not None
            rows.append(dict(document_id=answer['document_id'],field=field,expected=truth,actual=actual,
                             correct=correct,populated=populated,accepted_alternatives=accepted[1:]))
    text=[x for x in rows if x['field']!='publication_date' and x['populated']]
    absent=[x for x in rows if not x['populated']]
    pub=[x for x in rows if x['field']=='publication_date' and x['populated']]
    return {'correct_facts':sum(x['correct'] for x in rows),'total_facts':len(rows),
            'correct_populated_text_facts':sum(x['correct'] for x in text),'populated_text_facts':len(text),
            'correct_publication_metadata':sum(x['correct'] for x in pub),'publication_metadata':len(pub),
            'correct_absent_facts':sum(x['correct'] for x in absent),'absent_facts':len(absent),
            'validation_failures':sum(not v['passed'] for v in validations),
            'mechanical_pass':all(x['correct'] for x in rows) and all(v['passed'] for v in validations),
            'facts':rows,'validations':validations,'human_review_pending':True,'cash_availability_confirmed':False}


def main():
    root=Path('outputs/qualified-extraction');run=root/'run-01'
    manifest=json.loads((run/'manifest.json').read_text())
    for name,h in manifest['hashes'].items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest()!=h:raise ValueError('Frozen artifact changed')
    docs=json.loads((root/'documents.json').read_text());key=json.loads(Path('work/qualified-extraction-author/key.json').read_text())
    result={name:score(json.loads((run/(name+'-answers.json')).read_text()),key,docs) for name in ('code','specialist')}
    result['response_hashes']={n:hashlib.sha256((run/(n+'-answers.json')).read_bytes()).hexdigest() for n in ('code','specialist')}
    (run/'comparison.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({n:{k:v for k,v in result[n].items() if k not in ('facts','validations')} for n in ('code','specialist')},indent=2))

if __name__=='__main__':main()
