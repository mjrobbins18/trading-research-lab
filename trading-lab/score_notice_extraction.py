"""Paired extraction scoring against a frozen source-only reference key."""
from decimal import Decimal
import hashlib,json
from pathlib import Path

FIELDS=('amount_usd_per_share','pay_date','record_date','ex_date','publication_date')


def score(answers,key,docs,require_evidence=False):
    expected={k['document_id']:k for k in key};sources={d['document_id']:d for d in docs}
    if not isinstance(answers,list) or any(not isinstance(a,dict) for a in answers):raise ValueError('Answer list required')
    ids=[a.get('document_id') for a in answers]
    if any(not isinstance(i,str) for i in ids) or len(ids)!=len(set(ids)) or set(ids)!=set(expected):raise ValueError('Document coverage mismatch')
    rows=[];evidence_errors=[];citation_errors=[]
    for a in answers:
        e=expected[a['document_id']];d=sources[a['document_id']]
        if a.get('citation')!=a['document_id']:citation_errors.append(a['document_id'])
        for f in FIELDS:
            v=a.get(f);correct=f in a and v==e[f]
            if f=='amount_usd_per_share' and e[f] is not None:
                correct=type(v) in (int,float) and Decimal(str(v)).is_finite() and abs(Decimal(str(v))-Decimal(str(e[f])))<=Decimal('0.0000000001')
            rows.append(dict(document_id=a['document_id'],field=f,expected=e[f],actual=v,correct=correct,
                             supported=e[f] is not None,unsupported_value=e[f] is None and v is not None))
            if require_evidence and v is not None:
                evidence=a.get('evidence',{});span=evidence.get(f) if isinstance(evidence,dict) else None
                valid=isinstance(span,str) and bool(span.strip()) and span in d['text']
                if f=='publication_date' and span=='metadata:explicit_publication_date' and d.get('explicit_publication_date')==v:valid=True
                if not valid:evidence_errors.append({'document_id':a['document_id'],'field':f})
    supported=[r for r in rows if r['supported']]
    return dict(fields=rows,total_fields=len(rows),correct_fields=sum(r['correct'] for r in rows),
                supported_fields=len(supported),correct_supported_fields=sum(r['correct'] for r in supported),
                missing_supported_fields=sum(r['supported'] and r['actual'] is None for r in rows),
                unsupported_values=sum(r['unsupported_value'] for r in rows),citation_errors=citation_errors,
                evidence_span_errors=evidence_errors,
                mechanical_pass=all(r['correct'] for r in rows) and not citation_errors and not evidence_errors,
                limitation='Exact substring checks do not establish semantic entailment. Human source review is still required.')


def main():
    root=Path('outputs/authentic-extraction');run=root/'run-01'
    frozen=json.loads((run/'manifest.json').read_text())
    for name,h in frozen['hashes'].items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest()!=h:raise ValueError('Frozen file changed')
    docs=json.loads((root/'documents.json').read_text());key=json.loads(Path('work/authentic-extraction-author/key.json').read_text())
    result={name:score(json.loads((run/(name+'-answers.json')).read_text()),key,docs,name=='specialist') for name in ('code','specialist')}
    excluded={(x['document_id'],x['field']) for x in frozen['ambiguous_fields']}
    for name in ('code','specialist'):
        clear=[r for r in result[name]['fields'] if (r['document_id'],r['field']) not in excluded]
        parsed=[r for r in clear if r['supported'] and r['field']!='publication_date']
        result[name]['unambiguous_summary']={'correct_fields':sum(r['correct'] for r in clear),'total_fields':len(clear),
            'correct_supported_fields':sum(r['correct'] for r in clear if r['supported']),
            'supported_fields':sum(r['supported'] for r in clear),
            'correct_populated_text_fields':sum(r['correct'] for r in parsed),'populated_text_fields':len(parsed),
            'unsupported_values':sum(r['unsupported_value'] for r in clear)}
        result[name]['ambiguous_fields_separately_reported']=[r for r in result[name]['fields'] if (r['document_id'],r['field']) in excluded]
    result['answer_hashes']={name:hashlib.sha256((run/(name+'-answers.json')).read_bytes()).hexdigest() for name in ('code','specialist')}
    result['scope']='Six selected authentic short source excerpts; no claim of independent document sampling or historical archive availability.'
    (run/'comparison.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({name:{k:v for k,v in result[name].items() if k!='fields'} for name in ('code','specialist')},indent=2))

if __name__=='__main__':main()
