"""Score frozen extraction proposals against an independent model reference."""
import json,hashlib
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
from resolved_dividend_events import extract,validate,fingerprint

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'outputs/resolved-independent-evaluation'

def semantic(proposal):
    events=deepcopy(proposal['events'])
    for e in events:
        e.pop('event_id',None);e.pop('source_sha256',None)
        e['amount'].pop('source_span',None)
        e['amount']['value']=str(Decimal(e['amount']['value']).normalize())
    return sorted(events,key=lambda e:json.dumps(e,sort_keys=True))

def run():
    docs=json.loads((OUT/'documents.json').read_text())
    candidate={a['document_id']:a for a in json.loads((OUT/'candidate.json').read_text())}
    reference={a['document_id']:a for a in json.loads((OUT/'reference.json').read_text())}
    eligibility=json.loads((OUT/'reference-eligibility.json').read_text())
    rows=[];parser=[]
    for d in docs:
        key=d['document_id'];b=dict(document_id=key,packet_sha256=fingerprint(d),claims=[])
        p=extract(d,b);parser.append(p);r=reference[key]
        row=dict(document_id=key,primary_eligible=eligibility[key]['primary_eligible'],eligibility_reason=eligibility[key]['reason'])
        for name,a in [('parser',p),('candidate',candidate[key])]:
            row[name]=dict(semantic_agreement=semantic(a)==semantic(r),events=len(a['events']),unresolved=a['unresolved'],validation=validate(a,d,b))
        row['reference_unresolved']=r['unresolved'];rows.append(row)
    summary={}
    for name in ('parser','candidate'):
        eligible=[r for r in rows if r['primary_eligible']]
        passed=[r for r in rows if r[name]['validation']['passed']]
        summary[name]=dict(primary_documents=len(eligible),primary_semantic_matches=sum(r[name]['semantic_agreement'] for r in eligible),all_semantic_matches=sum(r[name]['semantic_agreement'] for r in rows),validator_passes=len(passed),semantic_mismatches_among_passes=sum(not r[name]['semantic_agreement'] for r in passed))
    result=dict(summary=summary,documents=rows,reference_human_reviewed=False,trading_authorized=False)
    (OUT/'parser.json').write_text(json.dumps(parser,indent=2)+'\n')
    (OUT/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(summary,indent=2))

if __name__=='__main__':run()
