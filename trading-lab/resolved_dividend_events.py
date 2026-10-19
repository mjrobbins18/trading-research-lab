"""Apply explicitly sourced metadata to immutable packets and bind its provenance.

Claims are research annotations from a separately supplied evidence bundle. This
checks scope and contradictions, not truth of the referenced external source.
"""
import json,hashlib,re
from copy import deepcopy
from datetime import date
import dividend_events as base
import dividend_source_adapters as adapters


def fingerprint(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def checked_claims(doc,bundle):
    if not isinstance(bundle,dict) or bundle.get('document_id')!=doc['document_id'] or bundle.get('packet_sha256')!=fingerprint(doc):raise ValueError('Resolution source identity mismatch')
    claims=bundle.get('claims')
    if not isinstance(claims,list):raise ValueError('Resolution claims must be a list')
    seen=set()
    for claim in claims:
        if not isinstance(claim,dict) or set(claim)!={'field','value','security_class','evidence','support_type'}:raise ValueError('Resolution claim schema')
        if claim['field'] not in ('currency_context','security_class','split_basis','payment_date','record_date'):raise ValueError('Unsupported resolution field')
        if claim['support_type'] not in ('direct','cross_source_inference'):raise ValueError('Unsupported support type')
        evidence=claim['evidence']
        if not isinstance(evidence,list) or not evidence:raise ValueError('Evidence required')
        for e in evidence:
            if not isinstance(e,dict) or set(e)!={'url','locator','summary','retrieved_at'} or not all(isinstance(v,str) and v.strip() for v in e.values()) or not e['url'].startswith('https://'):raise ValueError('Evidence provenance incomplete')
        key=(claim['field'],claim['security_class'])
        if key in seen:raise ValueError('Duplicate or conflicting resolution')
        seen.add(key)
        if claim['security_class'] not in (None,'common','ADR','ordinary_A','ordinary_B','preferred_A','preferred_B'):raise ValueError('Resolution security scope')
        field=claim['field'];value=claim['value']
        if field=='currency_context' and (value not in ('USD','SEK','DKK') or claim['security_class'] is not None):raise ValueError('Currency context scope')
        if field=='security_class' and (value!='common' or claim['security_class']!='common'):raise ValueError('Only explicit common scope resolution supported')
        if field=='split_basis' and (value not in ('pre_split','post_split') or claim['security_class'] is None):raise ValueError('Split basis scope')
        if field.endswith('_date'):
            if claim['security_class'] is None or not isinstance(value,str) or date.fromisoformat(value).isoformat()!=value:raise ValueError('Full date and security required')
    return claims


def compatible_date(text,role,value):
    pattern=(rf'payable\s+(?:(?:on or after|on)\s+)?(?P<date>{base.DATE})' if role=='payment' else
             rf'(?:record(?:ed)?(?: date)?|ownership recorded)\s+(?:(?:as of|at|is|on)\s+)?(?:the\s+)?(?:(?:close|start) of business\s+)?(?:on\s+)?(?P<date>{base.DATE})')
    raw=[m['date'] for m in re.finditer(pattern,text,re.I)]
    if not raw:return False
    for part in raw:
        original=base.date_value(part)
        completed=original or base.date_value(part+' '+value[:4])
        if completed!=value:return False
    return True


def prepare(doc,bundle):
    claims=checked_claims(doc,bundle);enriched=deepcopy(doc)
    for c in claims:
        if c['field']=='currency_context':
            if enriched.get('currency_context') not in (None,c['value']):raise ValueError('Currency contradiction')
            enriched['currency_context']=c['value']
    result=adapters.extract(enriched);issues=set(result['unresolved'])
    for c in claims:
        field,value,cls=c['field'],c['value'],c['security_class']
        if field=='currency_context':continue
        matched=[e for e in result['events'] if e['security']['class']==cls]
        if not matched:raise ValueError('Resolution has no matching extracted event')
        if field=='security_class':
            if any(e['security']['class']!=value for e in result['events']):raise ValueError('Mixed source security cannot be relabeled')
            issues.discard('security_scope_unresolved')
        elif field=='split_basis':
            for e in matched:e['split_basis']=value
            if len(matched)==len(result['events']):issues.discard('split_basis_requires_review')
        elif field.endswith('_date'):
            role='payment' if field=='payment_date' else 'record'
            if len(matched)!=1:raise ValueError('Date resolution requires unique event')
            f=matched[0]['dates'][role]
            if f['value'] is not None and f['value']!=value:raise ValueError('Date contradiction')
            if f['status']=='absent':raise ValueError('Cannot invent an absent date relationship')
            if not compatible_date(doc['text'],role,value):raise ValueError('Supplement contradicts original date components')
            f.update(value=value,status='explicit')
    if result['events'] and not any(f['status']=='unresolved' for e in result['events'] for f in e['dates'].values()):issues.discard('date_unresolved')
    result['unresolved']=sorted(issues)
    binding=fingerprint({'packet':doc,'resolution':bundle})
    result['source_sha256']=binding
    for e in result['events']:e['source_sha256']=binding
    return result,enriched


def extract(doc,bundle):return prepare(doc,bundle)[0]


def validate(proposal,doc,bundle):
    try:expected,enriched=prepare(doc,bundle)
    except (ValueError,TypeError,KeyError):return base.outcome(['invalid_resolution_bundle'],[],False)
    if not isinstance(proposal,dict):return base.outcome(['proposal_schema'],[],False)
    # Structural checks retain the frozen v5 schema. The full source+resolution
    # fingerprint is checked separately, then only hashes are translated locally.
    candidate=deepcopy(proposal)
    errors=[]
    if candidate.get('source_sha256')!=expected['source_sha256']:errors.append('resolution_binding_changed')
    candidate['source_sha256']=base.source_digest(enriched)
    for e in candidate.get('events',[]) if isinstance(candidate.get('events'),list) else []:
        if isinstance(e,dict):
            if e.get('source_sha256')!=expected['source_sha256']:errors.append('event_resolution_binding_changed')
            e['source_sha256']=base.source_digest(enriched)
    structure=base.validate(candidate,enriched)
    errors.extend(x for x in structure['errors'] if x!='source_event_binding_mismatch')
    review=list(expected['unresolved'])
    if isinstance(proposal.get('unresolved'),list):review.extend(x for x in proposal['unresolved'] if isinstance(x,str))
    if 'unsupported_currency' in structure['review_reasons']:review.append('unsupported_currency')
    # Even when another field remains unresolved, do not accept altered known claims.
    if proposal.get('events')!=expected['events']:errors.append('resolved_event_binding_mismatch')
    result=base.outcome(errors,review,not errors and not review)
    result.update(resolution_provenance_checked=True,external_evidence_independently_verified=False)
    return result
