"""Offline research extraction or proposal validation; no broker or network access."""
import argparse
import json
from pathlib import Path
import dividend_events_v63 as implementation

def run(documents,proposals=None):
    if not isinstance(documents,list):raise ValueError('Documents must be a JSON list')
    by_id=None
    if proposals is not None:
        if not isinstance(proposals,list):raise ValueError('Proposals must be a JSON list')
        by_id={p['document_id']:p for p in proposals}
        if len(by_id)!=len(proposals) or set(by_id)!={d['document_id'] for d in documents}:raise ValueError('Proposal identities must match documents exactly')
    return dict(implementation_revision='6.3',mode='extract' if by_id is None else 'validate',trading_authorized=False,
      records=[dict(document_id=d['document_id'],proposal=(p:=implementation.extract(d) if by_id is None else by_id[d['document_id']]),validation=implementation.validate(p,d)) for d in documents])

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--documents',type=Path,required=True)
    p.add_argument('--proposals',type=Path)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.resolve() in {a.documents.resolve(),a.proposals.resolve() if a.proposals else None}:p.error('Output must not overwrite an input')
    result=run(json.loads(a.documents.read_text()),json.loads(a.proposals.read_text()) if a.proposals else None)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps({'records':len(result['records']),'output':str(a.output),'trading_authorized':False}))
