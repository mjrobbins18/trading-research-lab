"""Research-only schema v6, implementation revision 6.1, source-nominal amounts; no brokerage dependencies.

Root: schema_version, document_id, source_sha256, events, unresolved,
cash_available_confirmed(False). Event: split_basis (source_nominal_unadjusted), security {type,class}; amount
{value,currency,unit,period}; dates {payment,record,ex_dividend}; evidence
{amount:[start,end], security:[start,end]|None, dates:{role:span|None}}.
Date: {value:ISO|None,status:explicit|absent|unresolved,
qualification:scheduled|earliest|expected|None,cutoff:...|None}.
Unknown security type is 'unknown'; class None means not specified, not a
claim that no subclasses exist. Evidence spans are Python character offsets.
Validation uses field-level evidence and relationship checks, not equality
with extract(). Shared tokenizers are NOT independent semantic proof.
Unsupported syntax and missing knowledge require review. Never confirms cash.
"""
import copy
import hashlib
import json
import re
from decimal import Decimal
from datetime import date
from dividend_events import DATE, date_value, empty_date

ROLES=('payment','record','ex_dividend')
VERSION=6
IMPLEMENTATION_REVISION="6.2"

def source_digest(doc):
    return hashlib.sha256(json.dumps(doc,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

def sentences(text):
    start=0
    for m in re.finditer(r'(?<=[.!?])\s+(?=[A-Z])|\n',text):
        if start<m.start():yield start,m.start(),text[start:m.start()]
        start=m.end()
    if start<len(text):yield start,len(text),text[start:]

def currency_sources(doc):
    # Trusted supplied metadata is an assertion bound by source_digest, not proof.
    codes=set()
    if doc.get('currency_context') in ('USD','SEK','DKK'):codes.add(doc['currency_context'])
    for _,_,clause in sentences(doc['text']):
        def dividend_context(position):
            topics=list(re.finditer(r'\b(dividend|distribution|earnings|revenue|income|profit)\b',clause[:position],re.I))
            return bool(topics and topics[-1][0].lower() in ('dividend','distribution'))
        for token in re.finditer(r'\b(USD|SEK|DKK)\s*\d+(?:\.\d+)?\s+(?:per|for each)\s+(?:(?:common|preferred|ordinary)\s+)?share',clause):
            if dividend_context(token.start()):codes.add(token[1])
        for payment in re.finditer(r'(?:payable|paid|payment|denominated)\s+(?:is\s+)?in U\.?S\.? dollars',clause,re.I):
            if dividend_context(payment.start()):codes.add('USD')
    return codes

def currency(doc):
    codes=currency_sources(doc)
    return next(iter(codes)) if len(codes)==1 else None

def amount_facts(doc):
    result=[]
    for s,e,clause in sentences(doc['text']):
        # Current rate in a from/to statement is the latter per-share amount.
        if re.search(r'already declared and paid|previously paid',clause,re.I):continue
        for m in re.finditer(r'(?:(?:USD|SEK|DKK|\$)\s*(\d+(?:\.\d+)?)|(\d+(?:\.\d+)?)\s+cents)\)?\s+(?:per|for each|a)\s+(?:(?:common(?:-stock)?|ordinary|preferred)\s+)?share',clause,re.I):
            # Bind the period to this amount, not a later annualized total.
            periods=list(re.finditer(r'\b(quarterly|annualized|annual|interim|special)\b',clause[:m.start()],re.I))
            period=periods[-1] if periods else None
            value=Decimal(m[1]) if m[1] else Decimal(m[2])/100
            result.append((dict(value=format(value,'f'),currency=currency(doc),unit='per_share',period=period[1].lower().replace('annualized','annual') if period else 'unknown'),[s,e],[s+m.start(),s+m.end()]))
    return result

def security_facts(text):
    result=[]
    for m in re.finditer(r'\bclass\s+([A-Z])\s+(common|preferred|ordinary)\s+(?:shares?|stock)',text,re.I):
        result.append((dict(type=m[2].lower(),**{'class':m[1].upper()}),[m.start(),m.end()]))
    for m in re.finditer(r'\b(common|preferred|ordinary)\s+(?:shares?|stock)\s+class\s+([A-Z])\b',text,re.I):
        result.append((dict(type=m[1].lower(),**{'class':m[2].upper()}),[m.start(),m.end()]))
    for m in re.finditer(r'\bclass ([A-Z]) and class ([A-Z]) (common|preferred|ordinary) (?:stock|shares)',text,re.I):
        for letter in (m[1],m[2]):result.append((dict(type=m[3].lower(),**{'class':letter.upper()}),[m.start(),m.end()]))
    if result:return result
    for m in re.finditer(r'\b(common|preferred|ordinary)(?:[- ]stock)?\s+(?:shares?|stock|holders)\b|\b(ADRs?)\b',text,re.I):
        if any(start<=m.start()<end and re.search(r'no dividend|not (?:receive|entitled)|excluded from',clause,re.I) for start,end,clause in sentences(text)):continue
        result.append((dict(type=m[1].lower() if m[1] else 'ADR',**{'class':None}),[m.start(),m.end()]))
    if not result:return [(dict(type='unknown',**{'class':None}),None)]
    return result

def date_facts(text):
    result={role:[] for role in ROLES}
    for s,e,clause in sentences(text):
        if re.search(r'\b(meeting|voting)\b',clause,re.I):continue
        matches=list(re.finditer(DATE,clause,re.I))
        for m in matches:
            before=clause[:m.start()];after=clause[m.end():]
            lower=before.lower();roles=[]
            # Shared record/ex date explicitly linked with 'both'.
            if re.match(r'\s+is the payment date',after,re.I):roles=['payment']
            elif re.search(r'record date and ex-dividend date are both\s*$',before,re.I):roles=['record','ex_dividend']
            elif re.search(r'^\s+is also the ex-dividend date',after,re.I):roles=['ex_dividend']
            else:
                anchor=list(re.finditer(r'\b(payment|payable|paid|record(?:ed|s)?|ex-dividend)\b',before,re.I))
                if anchor:
                    last=anchor[-1];tail=before[last.start():]
                    # Keep local relation, not a previous date in same sentence.
                    if not re.search(DATE,tail,re.I):
                        word=last[0].lower()
                        if word in ('payment','payable','paid') and not re.fullmatch(r'(?:payment(?: date)?(?: is)?|payable|paid)\s+(?:(?:scheduled for|due|on or after|no earlier than|expected on|anticipated on|on|for|expected to be|to be)\s+)*',tail,re.I):continue
                        roles=['payment' if word in ('payment','payable','paid') else 'ex_dividend' if word=='ex-dividend' else 'record']
            for role in roles:
                segment=re.split(r';',before)[-1].lower()
                value=date_value(m[0]);qual=None;cutoff=None
                if role=='payment':
                    anchors=list(re.finditer(r'\b(payment|payable|paid)\b',before,re.I))
                    payment_anchor=anchors[-1] if anchors else None
                    segment=before[payment_anchor.start():].lower() if payment_anchor else ''
                    expected_prefix=re.search(r'(?:expected|anticipated) to be\s*$',before[:payment_anchor.start()],re.I) if payment_anchor else False
                    qual='earliest' if re.search(r'on or after|no earlier than|earliest',segment) or re.match(r',?\s+or later\b',after,re.I) else 'expected' if re.search(r'expected|anticipated',segment) or expected_prefix else 'scheduled'
                if role=='record':cutoff='close_of_business' if re.search(r'close[- ]of[- ]business|business close(?:s)?',segment) else 'start_of_business' if 'start of business' in segment else None
                result[role].append((dict(value=value,status='explicit' if value else 'unresolved',qualification=qual,cutoff=cutoff),[s,e],[s+m.start(),s+m.end()]))
    return result

def issues(doc,amounts,securities,dates):
    out=[]
    if currency(doc) is None:out.append('currency_unresolved')
    if len(currency_sources(doc))>1:out.append('conflicting_currency_evidence')
    if re.search(r'no dividend|not (?:receive|entitled)|excluded from',doc['text'],re.I):out.append('excluded_security_scope_requires_review')
    if len({sec['type'] for sec,_ in securities})>1:out.append('mixed_security_types_require_recipient_binding')
    if len({sec['class'] for sec,_ in securities if sec['class'] is not None})>1 and not re.search(r'holders of both class [A-Z] common shares and class [A-Z] common shares|for (?:its )?outstanding class [A-Z] and class [A-Z] common stock',doc['text'],re.I):out.append('multiple_classes_require_recipient_binding')
    if any(sec['type']=='unknown' for sec,_ in securities):out.append('security_type_unresolved')
    if any(sec['class'] is not None for sec,_ in securities) and re.search(r'(?<!class [A-Z] )\b(?:common|preferred|ordinary) shares',doc['text'],re.I):out.append('unbound_security_mentions_require_review')
    if re.search(r'as[- ]converted',doc['text'],re.I):out.append('other_securities_as_converted_amounts_unresolved')
    if re.search(r'split|installments|record dates|payable dates',doc['text'],re.I):out.append('complex_schedule_or_split_requires_review')
    if len(amounts)!=1:out.append('amount_relationship_requires_review')
    elif amounts[0][0]['period']=='unknown':out.append('period_unresolved')
    for role,values in dates.items():
        if len({json.dumps(v,sort_keys=True) for v,_,_ in values})>1:out.append('ambiguous_'+role)
        if any(v['status']=='unresolved' for v,_,_ in values):out.append('unresolved_'+role)
    if not dates['payment']:out.append('payment_relationship_unresolved')
    if not dates['record']:out.append('record_relationship_unresolved')
    if re.search(r'ex[- ]dividend|ex[- ]date',doc['text'],re.I) and not dates['ex_dividend']:out.append('ex_dividend_relationship_unresolved')
    if any(sec['type']=='ADR' for sec,_ in securities):out.append('ADR_unit_relationship_requires_review')
    return out

def facts(doc):
    amounts=amount_facts(doc)
    # Annual rate is never a competing quarterly event.
    primary=[x for x in amounts if x[0]['period']!='annual']
    return primary or amounts,security_facts(doc['text']),date_facts(doc['text'])

def extract(doc):
    amounts,securities,dates=facts(doc);events=[]
    if len(amounts)==1:
        for security,span in {(sec['type'],sec['class']):(sec,sp) for sec,sp in securities}.values():
            event=dict(split_basis='source_nominal_unadjusted',security=security,amount=copy.deepcopy(amounts[0][0]),dates={},evidence=dict(amount=amounts[0][1],security=span,dates={}))
            for role in ROLES:
                vals=dates[role]
                if vals and all(v[0]==vals[0][0] for v in vals):event['dates'][role]=copy.deepcopy(vals[0][0]);event['evidence']['dates'][role]=vals[0][1]
                elif vals:event['dates'][role]=dict(value=None,status='unresolved',qualification=None,cutoff=None);event['evidence']['dates'][role]=None
                else:event['dates'][role]=empty_date();event['evidence']['dates'][role]=None
            events.append(event)
    return dict(schema_version=6,document_id=doc['document_id'],source_sha256=source_digest(doc),events=events,unresolved=issues(doc,amounts,securities,dates),cash_available_confirmed=False)

def contains(span,token,text):
    return isinstance(span,list) and len(span)==2 and all(type(x) is int for x in span) and 0<=span[0]<span[1]<=len(text) and span[0]<=token[0] and span[1]>=token[1]

def same_amount(left,right):
    try:return Decimal(left['value'])==Decimal(right['value']) and all(left[k]==right[k] for k in ('currency','unit','period'))
    except (KeyError,TypeError,ValueError,ArithmeticError):return False

def validate(proposal,doc):
    errors=[];amounts,securities,dates=facts(doc);review=issues(doc,amounts,securities,dates);text=doc['text']
    if not isinstance(proposal,dict):return outcome(['proposal_not_object'],review)
    if set(proposal)!={'schema_version','document_id','source_sha256','events','unresolved','cash_available_confirmed'}:errors.append('root_schema')
    for k,val in [('schema_version',6),('document_id',doc['document_id']),('source_sha256',source_digest(doc)),('cash_available_confirmed',False)]:
        if proposal.get(k)!=val or (k=='cash_available_confirmed' and proposal.get(k) is not False):errors.append('invalid_'+k)
    events=proposal.get('events');unresolved=proposal.get('unresolved')
    if not isinstance(unresolved,list) or any(not isinstance(v,str) for v in unresolved):errors.append('unresolved_schema')
    elif unresolved:review.extend(unresolved)
    if not isinstance(events,list):return outcome(errors+['events_schema'],review)
    seen=[]
    for index,event in enumerate(events):
        prefix='event_'+str(index)+':'
        try:
            if set(event)!={'split_basis','security','amount','dates','evidence'}:raise ValueError('event_schema')
            sec=event['security'];amt=event['amount'];ev=event['evidence']
            if event['split_basis']!='source_nominal_unadjusted':errors.append(prefix+'unsupported_split_basis')
            if set(sec)!={'type','class'} or set(amt)!={'value','currency','unit','period'}:raise ValueError('field_schema')
            if sec['type'] not in ('common','preferred','ordinary','ADR','unknown') or not (sec['class'] is None or isinstance(sec['class'],str) and re.fullmatch('[A-Z]',sec['class'])):raise ValueError('security_schema')
            if sec['type']=='unknown' and sec['class'] is not None:raise ValueError('unknown_class_schema')
            if not isinstance(amt['value'],str) or not re.fullmatch(r'\d+(?:\.\d+)?',amt['value']):raise ValueError('amount_value_schema')
            if amt['currency'] not in (None,'USD','SEK','DKK') or amt['unit']!='per_share' or amt['period'] not in ('quarterly','annual','interim','special','unknown'):raise ValueError('amount_schema')
            if set(event['dates'])!=set(ROLES) or set(ev)!={'amount','security','dates'} or set(ev['dates'])!=set(ROLES):raise ValueError('evidence_schema')
            key=(sec['type'],sec['class']);seen.append(key)
            sf=[x for x in securities if x[0]==sec]
            if not sf:errors.append(prefix+'unsupported_security')
            elif sec['type']=='unknown':
                if ev['security'] is not None:errors.append(prefix+'unknown_security_evidence')
            elif not any(contains(ev['security'],span,text) for _,span in sf):errors.append(prefix+'security_evidence')
            candidates=[x for x in amounts if same_amount(amt,x[0])]
            if not candidates:
                span=ev['amount']
                if not amounts and contains(span,span,text) and re.search(r'(?:USD|SEK|DKK|\$)\s*'+re.escape(amt['value'])+r'\b',text[span[0]:span[1]]) and re.search(r'\bshares?\b',text[span[0]:span[1]],re.I):review.append('amount_unsupported_source_relationship')
                else:errors.append(prefix+'amount_or_period_contradiction')
            elif not any(contains(ev['amount'],token,text) for _,context,token in candidates):errors.append(prefix+'amount_evidence')
            for role in ROLES:
                value=event['dates'][role];span=ev['dates'][role]
                if set(value)!={'value','status','qualification','cutoff'}:raise ValueError('date_schema')
                if value['status'] not in ('explicit','absent','unresolved'):raise ValueError('date_status')
                if value['qualification'] not in (None,'scheduled','earliest','expected') or value['cutoff'] not in (None,'close_of_business','start_of_business'):raise ValueError('date_qualifier')
                if role!='payment' and value['qualification'] is not None or role!='record' and value['cutoff'] is not None:raise ValueError('date_role')
                if value['status']=='explicit':
                    if not isinstance(value['value'],str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',value['value']):raise ValueError('date_value')
                    date.fromisoformat(value['value'])
                    if role=='payment' and value['qualification'] is None:raise ValueError('payment_qualifier')
                elif value['value'] is not None:raise ValueError('date_unknown_value')
                if value['status']=='absent' and value!=empty_date():raise ValueError('absent_date_schema')
                matches=[x for x in dates[role] if x[0]==value]
                if matches:
                    if not any(contains(span,token,text) for _,_,token in matches):errors.append(prefix+role+'_evidence')
                elif value==empty_date() and not dates[role]:
                    if span is not None:errors.append(prefix+role+'_absent_evidence')
                elif value['status']=='unresolved' and value['value'] is None:
                    review.append(role+'_candidate_unresolved')
                elif not dates[role] and value['status']=='explicit' and any(date_value(m[0])==value['value'] and contains(span,[m.start(),m.end()],text) for m in re.finditer(DATE,text,re.I)):
                    review.append(role+'_unsupported_source_relationship')
                else:errors.append(prefix+role+'_source_contradiction')
        except (KeyError,TypeError,ValueError):errors.append(prefix+'schema_invalid')
    expected={(s['type'],s['class']) for s,_ in securities}
    if len(seen)!=len(set(seen)):errors.append('duplicate_security_event')
    if len(amounts)==1 and expected-set(seen):errors.append('missing_security_event')
    return outcome(errors,review)

def outcome(errors,review):
    return dict(status='rejected' if errors else 'review_required' if review else 'consistent_research_record',errors=sorted(set(errors)),review_reasons=sorted(set(review)),human_review_pending=True,cash_available_confirmed=False,trading_authorized=False,independent_semantic_proof=False)
