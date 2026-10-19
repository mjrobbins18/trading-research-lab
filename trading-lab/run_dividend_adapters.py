"""Preserve source-adapter runs separately from frozen version5 runs."""
import argparse,json,hashlib
from pathlib import Path
from dividend_source_adapters import extract,validate


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--input',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args()
    docs=json.loads(args.input.read_text())
    if not isinstance(docs,list):raise ValueError('Expected document list')
    ids=[d['document_id'] for d in docs]
    if len(set(ids))!=len(ids):raise ValueError('Duplicate document IDs')
    rows=[]
    for doc in docs:
        proposal=extract(doc)
        rows.append({'document_id':doc['document_id'],'proposal':proposal,'validation':validate(proposal,doc)})
    summary={'documents':len(rows),'events_reconstructed':sum(len(r['proposal']['events']) for r in rows),'status_counts':{s:sum(r['validation']['status']==s for r in rows) for s in ('consistent_research_record','review_required','rejected')},'human_review_pending':True,'trading_authorized':False,'input_sha256':hashlib.sha256(args.input.read_bytes()).hexdigest()}
    args.output.mkdir(parents=True,exist_ok=False)
    for name,obj in [('results.json',rows),('summary.json',summary)]:
        (args.output/name).write_text(json.dumps(obj,indent=2)+'\n')
    print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
