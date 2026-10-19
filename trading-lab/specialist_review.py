"""Offline evidence packet for a read-only ETF trend research specialist.

This is a deterministic audit scaffold, not a trained model or a trading agent.
"""
import argparse,hashlib,json
from pathlib import Path


def review(run,as_of):
    verification=json.loads((run/'verification.json').read_text())
    if verification.get('passed') is not True:raise ValueError('Unreconciled run')
    signals=json.loads((run/'signals.json').read_text())
    ledger=json.loads((run/'ledger.json').read_text())
    if not signals or not ledger:raise ValueError('Missing evidence')
    last=signals[-1]
    if last['date']>as_of or ledger[-1]['date']>as_of:raise ValueError('Future evidence')
    packet={'role':'ETF trend research auditor','as_of':as_of,'data_through':ledger[-1]['date'],
      'baseline_signal':{'date':last['date'],'target':last['target'],'index':last['index'],'average':last['average']},
      'action':'abstain','requested_exposure':0,
      'reason':'Retrospective evidence only. No current market-context packet or demonstrated incremental agent value.',
      'qualification':'Not qualified for allocation decisions',
      'evidence':{name:hashlib.sha256((run/name).read_bytes()).hexdigest() for name in ['verification.json','signals.json','ledger.json','provenance.json']},
      'next_research_action':'Evaluate factual accuracy on dated evidence packets before any allocation experiment.'}
    return packet

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True,type=Path);p.add_argument('--as-of',required=True);p.add_argument('--output',required=True,type=Path)
    a=p.parse_args();result=review(a.run,a.as_of)
    with a.output.open('x') as f:json.dump(result,f,indent=2)
    print('Read-only specialist evidence packet written. No orders or model API calls.')
