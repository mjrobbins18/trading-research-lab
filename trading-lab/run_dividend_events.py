"""Write a new research-only event extraction run; never overwrite earlier runs."""
import argparse,json,hashlib
from pathlib import Path
from dividend_events import extract,validate


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    docs=json.loads(args.input.read_text())
    if not isinstance(docs,list):raise ValueError('Input must contain a document array')
    ids=[d['document_id'] for d in docs]
    if len(set(ids))!=len(ids):raise ValueError('Duplicate source identifiers')
    rows=[]
    for doc in docs:
        proposal=extract(doc)
        rows.append({'document_id':doc['document_id'],'proposal':proposal,'validation':validate(proposal,doc)})
    summary={'documents':len(rows),'status_counts':{s:sum(r['validation']['status']==s for r in rows) for s in ('consistent_research_record','review_required','rejected')},'human_review_pending':True,'trading_authorized':False,'input_sha256':hashlib.sha256(args.input.read_bytes()).hexdigest()}
    args.output.mkdir(parents=True,exist_ok=False)
    (args.output/'results.json').write_text(json.dumps(rows,indent=2)+'\n')
    (args.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
