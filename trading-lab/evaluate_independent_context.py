"""Score first responses without silently dropping malformed or missing records."""
import json,hashlib
from pathlib import Path
from context_guard import validate
from run_context_experiment import semantic

ROOT=Path('outputs/independent-context-evaluation')


def evaluate(answers,documents,references):
    expected_ids={d['document_id'] for d in documents}
    ids=[a.get('document_id') for a in answers if isinstance(a,dict)] if isinstance(answers,list) else []
    valid_ids=[i for i in ids if isinstance(i,str)]
    coverage_ok=(isinstance(answers,list) and len(ids)==len(answers) and len(valid_ids)==len(ids) and len(ids)==len(set(valid_ids)) and set(valid_ids)==expected_ids)
    index={a['document_id']:a for a in answers if isinstance(a,dict) and isinstance(a.get('document_id'),str)} if isinstance(answers,list) else {}
    keys={r['document_id']:r for r in references}
    if set(keys)!=expected_ids or len(keys)!=len(references):raise ValueError('Reference coverage invalid')
    rows=[]
    for doc in documents:
        answer=index.get(doc['document_id']);actual=None
        try:
            actual=semantic(answer)
            checks=validate(answer,doc)
            match=actual==keys[doc['document_id']]
        except (KeyError,TypeError,ValueError,AttributeError,IndexError):
            checks={'passed':False,'errors':['malformed_or_missing_response']};match=False
        rows.append(dict(document_id=doc['document_id'],semantic_match=match,validation=checks,actual=actual,expected=keys[doc['document_id']]))
    return dict(coverage_ok=coverage_ok,documents=len(rows),semantic_matches=sum(r['semantic_match'] for r in rows),validation_failures=sum(not r['validation']['passed'] for r in rows),mechanical_pass=coverage_ok and all(r['semantic_match'] and r['validation']['passed'] for r in rows),human_review_pending=True,trading_qualified=False,rows=rows)


def main():
    manifest=json.loads((ROOT/'run-01/manifest.json').read_text())
    for path,h in manifest['hashes'].items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=h:raise ValueError('Frozen artifact changed: '+path)
    docs=json.loads((ROOT/'candidate/documents.json').read_text())
    key=json.loads(Path('work/independent-context-reference/reference.json').read_text())
    result={}
    for name in ('code','specialist'):
        path=ROOT/'run-01'/(name+'-answers.json')
        try:answers=json.loads(path.read_text())
        except json.JSONDecodeError:answers=None
        result[name]=evaluate(answers,docs,key)
        result[name]['response_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    out=ROOT/'run-01/comparison.json'
    with out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps({n:{k:v for k,v in r.items() if k!='rows'} for n,r in result.items()},indent=2))

if __name__=='__main__':main()
