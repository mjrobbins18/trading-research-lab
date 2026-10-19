"""Version 5 research events and conservative source-binding validation.

Recognized single-security notices only. Unsupported structures require review.
No broker adapter, currency conversion, split adjustment, or cash authorization.
"""
import hashlib
import json
import re
from datetime import date
from decimal import Decimal

VERSION=5
MONTH=r'(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?'
DATE=rf'(?:{MONTH}\s+\d{{1,2}}(?:,?\s+\d{{4}})?|\d{{1,2}}\s+{MONTH}(?:\s+\d{{4}})?)'
MONEY=r'(?:(?P<currency>USD|SEK|DKK|\$)\s*(?P<value>\d+(?:\.\d+)?)|(?P<cents>\d+(?:\.\d+)?)\s+cents)\s+(?:per|for each)\s+(?:(?:common(?:-stock)?|ordinary|preferred|[AB])\s+)?(?:share|ADR)\b'
PERIOD=r'\b(quarterly|annualized|annual|interim|special|installment)\b'
FIELDS={'payment','record','ex_dividend'}


def digest(text):return hashlib.sha256(text.encode()).hexdigest()


def source_digest(doc):
    return digest(json.dumps({k:doc.get(k) for k in ('document_id','issuer','text','currency_context')},sort_keys=True,ensure_ascii=False))


def date_value(raw):
    parts=re.findall(r'[A-Za-z]+|\d+',raw)
    if len(parts)!=3:return None
    if parts[0].isdigit():day,month,year=parts
    else:month,day,year=parts
    try:
        n=['jan','feb','mar','apr','may','jun','jul','aug','sep','oct','nov','dec'].index(month[:3].lower())+1
        return date(int(year),n,int(day)).isoformat()
    except ValueError:return None


def empty_date():
    return dict(value=None,status='absent',qualification=None,cutoff=None)


def securities(text):
    """Return labels present in source, never infer ADR from a company ticker."""
    classes=set()
    if re.search(r'\bcommon(?:[- ]stock)?\s+(?:shares?|stock)\b|\bCommon Stock\b',text,re.I):classes.add('common')
    if re.search(r'\bADRs?\b|American Depositary',text,re.I):classes.add('ADR')
    for letter in ('A','B'):
        if re.search(r'\b'+letter+r'\s+shares?\b',text):classes.add('ordinary_'+letter)
        if re.search(r'\bSeries\s+'+letter+r'\b',text,re.I):classes.add('preferred_'+letter)
    if re.search(r'\bA\s*(?:/|and)\s*B\s+shares?\b',text):classes.update(('ordinary_A','ordinary_B'))
    if re.search(r'preferred',text,re.I) and not any(c.startswith('preferred_') for c in classes):classes.add('preferred_unspecified')
    return classes


def dates(text,role):
    patterns={
      'payment':rf'(?:payable|payment is|payment date is|expected to (?:be paid|disburse))\s+(?:(?:scheduled for|on or after|on|for)\s+)?(?P<date>{DATE})',
      'record':rf'(?:record(?:ed)?(?: date)?|ownership recorded)\s+(?:(?:as of|at|is|on)\s+)?(?:the\s+)?(?:(?:close|start) of business\s+)?(?:on\s+)?(?P<date>{DATE})',
      'ex_dividend':rf'ex-dividend date\s+(?:is\s+)?(?P<date>{DATE})'}
    matches=list(re.finditer(patterns[role],text,re.I))
    found=[]
    for m in matches:
        span=m.group(0).lower();value=date_value(m['date'])
        qual=('earliest' if 'on or after' in span else 'expected' if 'expected' in span else 'scheduled') if role=='payment' else None
        cutoff=('close_of_business' if 'close of business' in span else 'start_of_business' if 'start of business' in span else None) if role=='record' else None
        found.append(dict(value=value,status='explicit' if value else 'unresolved',qualification=qual,cutoff=cutoff))
    if not found:return empty_date(),[]
    if any(x!=found[0] for x in found[1:]):return dict(value=None,status='unresolved',qualification=None,cutoff=None),['conflicting_'+role]
    return found[0],[]


def extract(doc):
    text=doc['text'];issues=[];classes=securities(text)
    issuer=doc.get('issuer')
    if not isinstance(issuer,str) or not issuer.strip():issues.append('issuer_identity_missing')
    if len(classes)!=1:issues.append('security_scope_unresolved')
    amounts=[]
    for m in re.finditer(MONEY,text,re.I):
        # Attach period to the closest preceding period marker in this clause.
        prefix=text[max(0,m.start()-160):m.start()]
        clause=re.split(r'[;\n]|(?<=[a-z])\.\s+',prefix)[-1]
        periods=list(re.finditer(PERIOD,clause,re.I))
        period=periods[-1][1].lower() if periods else None
        currency=m['currency'];currency='USD' if currency=='$' or m['cents'] else currency
        value=Decimal(m['value']) if m['value'] else Decimal(m['cents'])/100
        # Bare $ and cents need explicit source currency metadata to remove ambiguity.
        if m['currency']=='$' or m['cents']:
            currency=doc.get('currency_context')
        amounts.append(dict(value=format(value,'f'),currency=currency,unit='per_ADR' if re.search('ADR',m.group(0),re.I) else 'per_share',period=period,source_span=[m.start(),m.end()]))
    installments=[a for a in amounts if a['period'] in ('quarterly','interim','special','installment')]
    if len(installments)!=1:issues.append('distribution_amount_unresolved')
    chosen=installments[0] if len(installments)==1 else None
    if chosen and chosen['currency'] not in ('USD','SEK','DKK'):issues.append('currency_unresolved')
    if chosen and len(classes)==1 and (('ADR' in classes)!=(chosen['unit']=='per_ADR')):issues.append('security_unit_unresolved')
    if re.search(r'(?:pre[- ](?:stock[- ])?split|post[- ](?:stock[- ])?split|stock split|split basis)',text,re.I):issues.append('split_basis_requires_review')
    # Multiple schedules cannot be collapsed into one event by this adapter.
    if re.search(r'(?:Record Dates\s*\||complete .*schedule|four quarterly|two installments)',text,re.I):issues.append('multiple_installments_require_binding')
    bindings={}
    for role in sorted(FIELDS):
        bindings[role],problems=dates(text,role);issues.extend(problems)
    if bindings['payment']['status']=='absent':issues.append('payment_binding_missing')
    if bindings['record']['status']=='absent':issues.append('record_binding_missing')
    if any(v['status']=='unresolved' for v in bindings.values()):issues.append('date_unresolved')
    # An explicit ex-date in unsupported syntax is not treated as genuine absence.
    if 'ex-dividend' in text.lower() and bindings['ex_dividend']['status']=='absent':issues.append('ex_date_binding_missing')
    events=[]
    if chosen and len(classes)==1 and issuer:
        security_class=next(iter(classes))
        events=[dict(event_id=doc['document_id']+':1',security={'issuer':issuer,'class':security_class},amount=chosen,
          split_basis='source_nominal_unadjusted',dates=bindings,source_sha256=source_digest(doc))]
    return dict(schema_version=VERSION,document_id=doc['document_id'],source_sha256=source_digest(doc),events=events,
                unresolved=sorted(set(issues)),cash_available_confirmed=False)


def validate(proposal,doc):
    """Fail closed outside adapter coverage. Passing is research consistency only."""
    errors=[];review=[]
    expected=extract(doc)
    if not isinstance(proposal,dict):return outcome(['proposal_schema'],[],False)
    required={'schema_version','document_id','source_sha256','events','unresolved','cash_available_confirmed'}
    if set(proposal)!=required:errors.append('proposal_keys')
    if proposal.get('schema_version')!=VERSION:errors.append('schema_version')
    if proposal.get('document_id')!=doc['document_id']:errors.append('document_identity')
    if proposal.get('source_sha256')!=source_digest(doc):errors.append('source_changed')
    if proposal.get('cash_available_confirmed') is not False:errors.append('cash_claim')
    if not isinstance(proposal.get('unresolved'),list):errors.append('unresolved_schema')
    review.extend(expected['unresolved'])
    if isinstance(proposal.get('unresolved'),list):
        if not all(isinstance(x,str) for x in proposal['unresolved']):errors.append('unresolved_schema')
        else:review.extend(proposal['unresolved'])
    events=proposal.get('events')
    if not isinstance(events,list):errors.append('events_schema');events=[]
    ids=[e.get('event_id') for e in events if isinstance(e,dict)]
    if len(ids)!=len(events) or any(not isinstance(i,str) for i in ids) or len(set(str(i) for i in ids))!=len(ids):errors.append('event_identity')
    for e in events:
        if not isinstance(e,dict) or set(e)!={'event_id','security','amount','split_basis','dates','source_sha256'}:
            errors.append('event_schema');continue
        if not isinstance(e['security'],dict) or set(e['security'])!={'issuer','class'}:errors.append('security_schema')
        elif not isinstance(e['security']['issuer'],str) or not e['security']['issuer'].strip() or e['security']['class'] not in ('common','ADR','ordinary_A','ordinary_B','preferred_A','preferred_B','preferred_unspecified'):errors.append('security_identity')
        if e['split_basis'] not in ('source_nominal_unadjusted','pre_split','post_split'):errors.append('split_basis')
        if not isinstance(e['amount'],dict) or set(e['amount'])!={'value','currency','unit','period','source_span'}:errors.append('amount_schema')
        else:
            a=e['amount']
            try:
                value=Decimal(a['value']) if isinstance(a['value'],str) and re.fullmatch(r'\d+(?:\.\d+)?',a['value']) else Decimal('NaN')
                if not value.is_finite() or value<0:errors.append('amount_value')
            except Exception:errors.append('amount_value')
            if a['currency'] not in ('USD','SEK','DKK',None):review.append('unsupported_currency')
            if a['unit'] not in ('per_share','per_ADR'):errors.append('amount_unit')
            if a['period'] not in ('quarterly','interim','special','installment',None):errors.append('distribution_period')
            span=a['source_span']
            if not isinstance(span,list) or len(span)!=2 or any(type(v)!=int for v in span) or not 0<=span[0]<span[1]<=len(doc['text']):errors.append('amount_span')
        if not isinstance(e['dates'],dict) or set(e['dates'])!=FIELDS:errors.append('dates_schema')
        else:
            for role,f in e['dates'].items():
                if not isinstance(f,dict) or set(f)!={'value','status','qualification','cutoff'}:errors.append('date_schema');continue
                if f['status'] not in ('explicit','unresolved','absent'):errors.append('date_status')
                if f['qualification'] not in (None,'scheduled','earliest','expected'):errors.append('payment_qualification')
                if f['cutoff'] not in (None,'close_of_business','start_of_business'):errors.append('record_cutoff')
                if f['status']=='absent' and f!=empty_date():errors.append('absent_date_fields')
                if f['status']=='unresolved' and f['value'] is not None:errors.append('unresolved_date_value')
                if f['status']=='explicit':
                    try:
                        if not isinstance(f['value'],str) or date.fromisoformat(f['value']).isoformat()!=f['value']:raise ValueError()
                    except (TypeError,ValueError):errors.append('invalid_calendar_date')
                if role!='payment' and f['qualification'] is not None:errors.append('qualification_role')
                if role!='record' and f['cutoff'] is not None:errors.append('cutoff_role')
        if e['source_sha256']!=source_digest(doc):errors.append('event_source_changed')
    # Compare complete relationship, not isolated substring occurrence. On unsupported
    # source syntax the adapter cannot adjudicate a candidate: retain review status.
    if not expected['unresolved'] and events!=expected['events']:errors.append('source_event_binding_mismatch')
    elif expected['unresolved']:review.append('source_adapter_incomplete')
    return outcome(errors,review,not errors and not review)


def outcome(errors,review,passed):
    return dict(status='rejected' if errors else 'review_required' if review else 'consistent_research_record',
      passed=passed,errors=sorted(set(errors)),review_reasons=sorted(set(review)),human_review_pending=True,
      cash_available_confirmed=False,trading_authorized=False)
