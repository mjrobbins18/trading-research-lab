"""Run frozen local research extraction. Optional external candidate file, no API calls."""
import argparse,hashlib,json,time
from pathlib import Path
from context_extractor import extract,validate

ROOT=Path('outputs/context-extraction')

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def semantic(answer):
    events=[]
    for e in answer['events']:
        events.append({'amount':{k:v for k,v in e['amount'].items() if k!='evidence'},**{f:{k:v for k,v in e[f].items() if k!='evidence'} for f in ('pay_date','record_date','ex_date')}})
    return {'document_id':answer['document_id'],'events':events,'publication_date':answer['publication_date'],'cash_available_confirmed':answer['cash_available_confirmed']}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--candidate',type=Path);args=ap.parse_args()
    manifest=json.loads((ROOT/'run-01/manifest.json').read_text())
    for path,h in manifest['hashes'].items():
        if digest(path)!=h:raise ValueError('Frozen input changed: '+path)
    docs=json.loads((ROOT/'documents.json').read_text());key=json.loads((ROOT/'reference.json').read_text())
    start=time.perf_counter()
    answers=json.loads(args.candidate.read_text()) if args.candidate else [extract(d) for d in docs]
    elapsed=time.perf_counter()-start
    ids=[a['document_id'] for a in answers]
    if len(ids)!=len(set(ids)) or set(ids)!={d['document_id'] for d in docs}:raise ValueError('Document coverage mismatch')
    by_id={a['document_id']:a for a in answers};by_key={a['document_id']:a for a in key}
    rows=[]
    for d in docs:
        a=by_id[d['document_id']];actual=semantic(a);expected=by_key[d['document_id']]
        rows.append({'document_id':d['document_id'],'semantic_match':actual==expected,'actual':actual,'expected':expected,'validation':validate(a,d)})
    result={'method':'external_candidate' if args.candidate else 'deterministic_parser','documents':len(rows),'semantic_matches':sum(r['semantic_match'] for r in rows),'validation_failures':sum(not r['validation']['passed'] for r in rows),'elapsed_seconds':elapsed,'latency_scope':'local file load/scoring input; not model latency' if args.candidate else 'local extraction only','human_review_pending':True,'independent_holdout':False,'trading_qualified':False,'rows':rows}
    prefix='candidate' if args.candidate else 'code'
    for name,value in [(prefix+'-answers.json',answers),(prefix+'-results.json',result)]:
        target=ROOT/'run-01'/name
        if target.exists():raise FileExistsError('Preserve first run: '+str(target))
        target.write_text(json.dumps(value,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='rows'},indent=2))

if __name__=='__main__':main()
