"""Research-only dividend schedule extraction. No broker integration."""
import re
from decimal import Decimal
from qualified_extractor import MONTH, iso

DATE = MONTH + r'\s+\d{1,2}(?:,?\s+\d{4})?'
MONEY = r'(?:\$(?P<dollars>\d+(?:\.\d+)?)|(?P<cents>\d+(?:\.\d+)?)\s+cents)\s+per\s+(?:common\s+)?share'
PAY = r'payable\s+(?:(?:on\s+or\s+after|on)\s+)?(?P<date>' + DATE + ')'
RECORD = r'\brecord\s+(?:(?:as\s+of|at)\s+)?(?:the\s+)?(?:(?:close|start)\s+of\s+business\s+)?(?:on\s+)?(?P<date>' + DATE + ')'


def date_fact(raw, evidence, kind):
    cutoff = 'close_of_business' if 'close of business' in evidence.lower() else ('start_of_business' if 'start of business' in evidence.lower() else None)
    if kind == 'scheduled' and re.search(r'on\s+or\s+after', evidence, re.I):
        kind = 'earliest'
    try:
        value = iso(raw)
        status = 'explicit'
    except ValueError:
        value = None
        status = 'ambiguous'
    return dict(value=value, kind=kind, status=status, cutoff=cutoff, evidence=evidence)


def absent():
    return dict(value=None,kind='not_stated',status='absent',cutoff=None,evidence=None)


def resolve(pattern, text, kind):
    matches = list(re.finditer(pattern, text, re.I))
    if not matches:
        return absent()
    facts = [date_fact(m['date'],m.group(0),kind) for m in matches]
    if len({(f['value'],f['kind'],f['status'],f['cutoff']) for f in facts}) > 1:
        return dict(value=None,kind=kind,status='ambiguous',cutoff=None,evidence=[f['evidence'] for f in facts])
    return facts[0]


def amount(text):
    installment=re.search(r'quarterly installments? of ('+MONEY+')',text,re.I)
    matches=[installment] if installment else list(re.finditer(MONEY,text,re.I))
    values=[Decimal(m['dollars']) if m['dollars'] else Decimal(m['cents'])/100 for m in matches]
    if not matches:
        return dict(value=None,status='absent',evidence=None)
    if len(set(values))!=1:
        return dict(value=None,status='ambiguous',evidence=[m.group(0) for m in matches])
    return dict(value=float(values[0]),status='explicit',evidence=matches[0].group(0))


def extract(doc):
    text=doc['text']; events=[]
    # Table support requires both column headers and preserves every supplied row.
    table=re.search(r'Record Dates\s*\|\s*Payable Dates\s*\n(?P<rows>(?:[^\n]+\n?)+)',text,re.I)
    money=amount(text)
    if table:
        for line in table['rows'].splitlines():
            row=re.fullmatch(r'\s*('+DATE+r')\s*\|\s*('+DATE+r')\s*',line,re.I)
            if row:
                span=table.group(0)
                events.append(dict(amount=money,pay_date=date_fact(row[2],span,'scheduled'),record_date=date_fact(row[1],span,'record'),ex_date=absent()))
    else:
        events.append(dict(amount=money,pay_date=resolve(PAY,text,'scheduled'),record_date=resolve(RECORD,text,'record'),ex_date=resolve(r'ex-dividend date\s+(?:is\s+)?(?P<date>'+DATE+')',text,'ex_dividend')))
    return dict(document_id=doc['document_id'],events=events,publication_date=doc.get('explicit_publication_date'),cash_available_confirmed=False)


def validate(answer, doc):
    """Evidence and schema checks, not an independent semantic reference."""
    errors=[]
    if not isinstance(answer,dict):return {'passed':False,'errors':['answer_schema']}
    if answer.get('document_id')!=doc['document_id']:errors.append('identity')
    if answer.get('cash_available_confirmed') is not False:errors.append('cash_claim')
    if answer.get('publication_date')!=doc.get('explicit_publication_date'):errors.append('publication_metadata')
    events=answer.get('events')
    if not isinstance(events,list) or not events:return {'passed':False,'errors':errors+['events_schema']}
    for i,event in enumerate(events):
        if not isinstance(event,dict) or set(event)!={'amount','pay_date','record_date','ex_date'}:
            errors.append(f'{i}:event_schema');continue
        money=event['amount']
        if not isinstance(money,dict) or set(money)!={'value','status','evidence'}:
            errors.append(f'{i}:amount_schema');continue
        spans=money['evidence'] if isinstance(money['evidence'],list) else [money['evidence']]
        if money['status'] not in ('explicit','ambiguous','absent'):errors.append(f'{i}:amount_status')
        if money['status']=='absent' and (money['value'] is not None or money['evidence'] is not None):errors.append(f'{i}:amount_absent')
        if money['status']=='ambiguous' and money['value'] is not None:errors.append(f'{i}:amount_ambiguity')
        if money['status']!='absent':
            if not spans or any(not isinstance(s,str) or not s or s not in doc['text'] for s in spans):errors.append(f'{i}:amount_span')
            if money['value'] is not None:
                if type(money['value']) not in (int,float):errors.append(f'{i}:amount_type')
                elif not any(isinstance(s,str) and amount(s)['value']==money['value'] for s in spans):errors.append(f'{i}:amount_number_or_unit')
        for field,kind in [('pay_date','scheduled'),('record_date','record'),('ex_date','ex_dividend')]:
            f=event[field];prefix=f'{i}:{field}'
            if not isinstance(f,dict) or set(f)!={'value','kind','status','cutoff','evidence'}:
                errors.append(prefix+':schema');continue
            if f['status']=='absent':
                if f!=absent():errors.append(prefix+':absent')
                continue
            if f['status'] not in ('explicit','contextual','ambiguous'):errors.append(prefix+':status')
            if f['kind'] not in ({'scheduled','earliest'} if field=='pay_date' else {kind}):errors.append(prefix+':kind')
            if f['cutoff'] not in (None,'close_of_business','start_of_business'):errors.append(prefix+':cutoff')
            if f['status']=='ambiguous' and f['value'] is not None:errors.append(prefix+':ambiguity')
            if f['status']!='ambiguous' and f['value'] is None:errors.append(prefix+':missing_value')
            spans=f['evidence'] if isinstance(f['evidence'],list) else [f['evidence']]
            if not spans or any(not isinstance(s,str) or not s or s not in doc['text'] for s in spans):
                errors.append(prefix+':span');continue
            joined=' '.join(spans)
            if field=='pay_date' and re.search(r'on\s+or\s+after',joined,re.I) and f['kind']!='earliest':errors.append(prefix+':lost_qualifier')
            for wording,cutoff in [('close of business','close_of_business'),('start of business','start_of_business')]:
                if wording in joined.lower() and f['cutoff']!=cutoff:errors.append(prefix+':lost_cutoff')
            values=[]
            for m in re.finditer(DATE,joined,re.I):
                try:values.append(iso(m.group(0)))
                except ValueError:pass
            if f['value'] is not None and f['value'] not in values:errors.append(prefix+':unsupported_date_or_year')
    return {'passed':not errors,'errors':errors,'cash_available_confirmed':False}
