"""Preserve raw semantic and review-disposition comparisons for frozen v6 runs."""
import argparse
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import dividend_events_v6 as v6

def semantics(events):
    result=[]
    for event in deepcopy(events):
        event.pop('evidence',None)
        event['amount']['value']=str(Decimal(event['amount']['value']).normalize())
        result.append(event)
    return sorted(result,key=lambda e:json.dumps(e,sort_keys=True))

def compare(actual,reference,doc):
    validation=v6.validate(actual,doc)
    try:matches=semantics(actual['events'])==semantics(reference['events'])
    except (KeyError,TypeError,ValueError,ArithmeticError):matches=False
    return dict(semantic_match=matches,event_count=len(actual.get('events',[])),
      unresolved_present=bool(actual.get('unresolved')),reference_unresolved_present=bool(reference.get('unresolved')),
      unresolved_disposition_match=bool(actual.get('unresolved'))==bool(reference.get('unresolved')),validation=validation)

def run(directory):
    docs=json.loads((directory/'documents.json').read_text())
    candidate={a['document_id']:a for a in json.loads((directory/'candidate.json').read_text())}
    reference={a['document_id']:a for a in json.loads((directory/'reference.json').read_text())}
    eligibility=json.loads((directory/'reference-eligibility.json').read_text())
    if set(candidate)!=set(reference) or set(reference)!={d['document_id'] for d in docs}:raise ValueError('Missing or extra document proposals')
    rows=[];parser=[]
    for doc in docs:
        key=doc['document_id'];a=v6.extract(doc);parser.append(a)
        rows.append(dict(document_id=key,reference_eligibility=eligibility[key],
          parser=compare(a,reference[key],doc),candidate=compare(candidate[key],reference[key],doc)))
    summary={}
    for arm in ('parser','candidate'):
        eligible=[row for row in rows if row['reference_eligibility']['primary_eligible']]
        passes=[row for row in rows if row[arm]['validation']['status']=='consistent_research_record']
        summary[arm]=dict(documents=len(rows),eligible_documents=len(eligible),
          semantic_matches=sum(row[arm]['semantic_match'] for row in eligible),
          unresolved_disposition_matches=sum(row[arm]['unresolved_disposition_match'] for row in eligible),
          consistent_records=len(passes),semantic_disagreements_among_consistent_records=sum(not r[arm]['semantic_match'] for r in passes),
          semantically_matching_rejected_proposals=sum(r[arm]['semantic_match'] and r[arm]['validation']['status']=='rejected' for r in rows),
          review_required=sum(r[arm]['validation']['status']=='review_required' for r in rows),
          rejected=sum(r[arm]['validation']['status']=='rejected' for r in rows))
    output=dict(summary=summary,rows=rows,reference_human_reviewed=False,trading_authorized=False)
    (directory/'parser.json').write_text(json.dumps(parser,indent=2)+'\n')
    (directory/'results.json').write_text(json.dumps(output,indent=2)+'\n')
    print(json.dumps(summary,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);run(p.parse_args().directory)
