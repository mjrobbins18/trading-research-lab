"""Explicit schedule and class bindings for the v5 research contract.

Preserves frozen v5 code. Unknown layouts remain review-required.
"""
import re
from copy import deepcopy
from decimal import Decimal
import dividend_events as base


def amount(match,doc,period):
    currency=match['currency']
    if currency=='$' or match['cents']:currency=doc.get('currency_context')
    value=Decimal(match['value']) if match['value'] else Decimal(match['cents'])/100
    return dict(value=format(value,'f'),currency=currency,unit='per_share',period=period,source_span=[match.start(),match.end()])


def fact(raw,qualification=None,cutoff=None):
    value=base.date_value(raw)
    return dict(value=value,status='explicit' if value else 'unresolved',qualification=qualification,cutoff=cutoff)


def wrap(doc,events,issues):
    if not doc.get('issuer'):issues.append('issuer_identity_missing')
    for i,e in enumerate(events,1):
        e.update(event_id=f"{doc['document_id']}:{i}",source_sha256=base.source_digest(doc))
        if e['amount']['currency'] not in ('USD','SEK','DKK'):issues.append('currency_unresolved')
        if any(d['status']=='unresolved' for d in e['dates'].values()):issues.append('date_unresolved')
    return dict(schema_version=5,document_id=doc['document_id'],source_sha256=base.source_digest(doc),events=events,unresolved=sorted(set(issues)),cash_available_confirmed=False)


def event(doc,cls,money,payment,record,basis='source_nominal_unadjusted'):
    return dict(security={'issuer':doc.get('issuer'),'class':cls},amount=deepcopy(money),split_basis=basis,
                dates={'payment':payment,'record':record,'ex_dividend':base.empty_date()})


def schedule(doc):
    text=doc['text'];issues=[]
    table=re.search(r'Record Dates\s*\|\s*Payable Dates\s*\n',text,re.I)
    narrative=re.search(r'complete record-date/payable-date schedule is:\s*',text,re.I)
    if not table and not narrative:return None
    if base.securities(text)!={'common'}:issues.append('security_scope_unresolved')
    money_pattern=r'(?:quarterly (?:installments?|payments?)(?: are each| of)\s+)('+base.MONEY+')'
    amounts=list(re.finditer(money_pattern,text,re.I))
    if len(amounts)!=1:return wrap(doc,[],issues+['installment_amount_unresolved'])
    money=amount(amounts[0],doc,'quarterly')
    # Source offsets refer to the exact complete amount clause, not a fabricated quote.
    rows=[]
    if table:
        for line in text[table.end():].splitlines():
            if not line.strip():continue
            m=re.fullmatch(r'\s*('+base.DATE+r')\s*\|\s*('+base.DATE+r')\s*',line,re.I)
            if not m:issues.append('unrecognized_schedule_row');continue
            rows.append((m[1],m[2]))
    else:
        tail=text[narrative.end():]
        pattern=r'('+base.DATE+r')\s*/\s*('+base.DATE+r')'
        matches=list(re.finditer(pattern,tail,re.I))
        rows=[(m[1],m[2]) for m in matches]
        # Every delimited schedule entry must be parsed; unrelated following prose is allowed.
        if not matches or (matches and tail[:matches[0].start()].strip()) or any(tail[matches[i].end():matches[i+1].start()].strip()!=';' for i in range(len(matches)-1)):
            issues.append('unrecognized_schedule_row')
        if matches:
            trailing=tail[matches[-1].end():]
            if trailing.lstrip().startswith(';'):issues.append('unrecognized_schedule_row')
    count=re.search(r'\b(four|two|three|\d+)\s+quarterly\s+(?:installments|payments)',text,re.I)
    if count:
        value=count[1].lower();n={'four':4,'two':2,'three':3}.get(value)
        if n is None:n=int(value)
        if len(rows)!=n:issues.append('installment_count_mismatch')
    if not rows:issues.append('schedule_empty')
    if len(set(rows))!=len(rows):issues.append('duplicate_schedule_row')
    # Do not infer that an annual post-split amount sets the installment basis.
    basis='source_nominal_unadjusted'
    if re.search(r'pre[- ]split|post[- ]split|stock split|stock-split',text,re.I):issues.append('split_basis_requires_review')
    if 'ex-dividend' in text.lower():issues.append('ex_date_schedule_requires_binding')
    events=[event(doc,'common',money,fact(pay,'scheduled'),fact(record),basis) for record,pay in rows]
    return wrap(doc,events,issues)


def class_notice(doc):
    text=doc['text'];classes=base.securities(text)
    if classes!={'common','preferred_A','preferred_B'}:return None
    # This adapter covers only the named P&G-style common + two preferred classes.
    issues=[]
    money_re=base.MONEY.replace('common(?:-stock)?','common(?:[- ]stock)?')
    amounts=list(re.finditer(money_re,text,re.I))
    if len(amounts)!=1:return wrap(doc,[],['class_amount_unresolved'])
    if not re.search(r'quarterly dividend',text,re.I):issues.append('distribution_period_unresolved')
    money=amount(amounts[0],doc,'quarterly')
    payment,problems=base.dates(text,'payment');issues.extend(problems)
    if payment['status']=='absent':issues.append('payment_binding_missing')
    common=list(re.finditer(r'Common Stock (?:ownership|record cutoff)[^.;]{0,65}?close of business on ('+base.DATE+')',text,re.I))
    preferred=list(re.finditer(r'(?:ownership of the named preferred classes|for the specified preferred shares)[^.;]{0,65}?start of business on ('+base.DATE+')',text,re.I))
    if len(common)!=1 or len(preferred)!=1:return wrap(doc,[],issues+['class_record_binding_unresolved'])
    if 'ex-dividend' in text.lower():issues.append('ex_date_class_requires_binding')
    events=[event(doc,'common',money,deepcopy(payment),fact(common[0][1],cutoff='close_of_business'))]
    for cls in ('preferred_A','preferred_B'):
        events.append(event(doc,cls,money,deepcopy(payment),fact(preferred[0][1],cutoff='start_of_business')))
    return wrap(doc,events,issues)


def extract(doc):
    for adapter in (schedule,class_notice):
        result=adapter(doc)
        if result is not None:return result
    return base.extract(doc)


def validate(proposal,doc):
    # Reuse frozen structural checks, replacing only its source-adapter judgment.
    structural=base.validate(proposal,doc)
    errors=[e for e in structural['errors'] if e!='source_event_binding_mismatch']
    expected=extract(doc)
    review=list(expected['unresolved'])
    if isinstance(proposal,dict) and isinstance(proposal.get('unresolved'),list):
        review.extend(x for x in proposal['unresolved'] if isinstance(x,str))
    if 'unsupported_currency' in structural['review_reasons']:review.append('unsupported_currency')
    if not isinstance(proposal,dict):return base.outcome(errors,review,False)
    if not expected['unresolved'] and proposal.get('events')!=expected['events']:errors.append('source_event_binding_mismatch')
    if expected['unresolved']:review.append('source_adapter_incomplete')
    return base.outcome(errors,review,not errors and not review)
