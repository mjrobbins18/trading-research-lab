"""Version 2 development parser: preserve timing semantics and source evidence.

Research extraction only. A scheduled or earliest date never confirms posted cash.
"""
import re
from datetime import datetime

MONTH=r'(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?'
DATE=MONTH+r'\s+\d{1,2},?\s+\d{4}'
AMOUNT=r'\$([0-9]+(?:\.[0-9]+)?)\s+per\s+(?:common\s+)?share'


def iso(text):
    m=re.fullmatch(r'([A-Za-z]+)\.?\s+(\d{1,2}),?\s+(\d{4})',text)
    if not m:raise ValueError('Unrecognized date')
    month=['jan','feb','mar','apr','may','jun','jul','aug','sep','oct','nov','dec'].index(m[1][:3].lower())+1
    return datetime(int(m[3]),month,int(m[2])).date().isoformat()


def absent():return dict(value=None,kind='not_stated',status='absent',cutoff=None,evidence=None)


def resolve(matches,kind,status='explicit',payment=False):
    if not matches:return absent()
    observations=[]
    for m in matches:
        span=m.group(0);k='earliest' if payment and re.search(r'on\s+or\s+after',span,re.I) else kind
        cutoff='close_of_business' if re.search(r'close of business',span,re.I) else ('start_of_business' if re.search(r'start of business',span,re.I) else None)
        observations.append(dict(value=iso(m['date']),kind=k,status=status,cutoff=cutoff,evidence=span))
    if len({(x['value'],x['kind'],x['cutoff']) for x in observations})!=1:
        return dict(value=None,kind=kind,status='ambiguous',cutoff=None,evidence=' | '.join(x['evidence'] for x in observations))
    return observations[0]


def extract(doc):
    text=doc['text'];flags=re.I
    # A transition supplies the new amount, not the preceding old amount.
    transitions=list(re.finditer(AMOUNT+r'\s+to\s+'+AMOUNT,text,flags))
    amounts=[(float(m[2]),m.group(0)) for m in transitions]
    if not amounts:
        amounts=[(float(m[1]),m.group(0)) for m in re.finditer(r'dividend\b[^$\n]{0,90}?'+AMOUNT,text,flags)]
    values={a[0] for a in amounts};amount=next(iter(values)) if len(values)==1 else None
    pay=resolve(list(re.finditer(r'payable\s+(?:(?:on\s+or\s+after|on)\s+)?(?P<date>'+DATE+r')',text,flags)),'scheduled',payment=True)
    if pay['status']=='absent':
        pay=resolve(list(re.finditer(r'(?:will\s+pay|will\s+be\s+paid)\b[^\n]{0,110}?\bon\s+(?P<date>'+DATE+r')',text,flags)),'scheduled',payment=True)
    if pay['status']=='absent':
        pay=resolve(list(re.finditer(r'dividend\b[^\n]{0,110}?per\s+share\s+on\s+(?P<date>'+DATE+r')',text,flags)),'scheduled','contextual')
    record=resolve(list(re.finditer(r'(?:shareholders|stockholders)\s+of\s+record\s+(?:(?:as\s+of|at)\s+)?(?:the\s+)?(?:(?:close|start)\s+of\s+business\s+)?(?:on\s+)?(?P<date>'+DATE+r')',text,flags)),'record')
    ex=resolve(list(re.finditer(r'ex-dividend\s+date\s+(?:is\s+|of\s+|will\s+be\s+)?(?P<date>'+DATE+r')',text,flags)),'ex_dividend')
    pub=absent()
    if doc.get('explicit_publication_date'):
        pub=dict(value=doc['explicit_publication_date'],kind='publication',status='explicit',cutoff=None,evidence='metadata:explicit_publication_date')
    return dict(document_id=doc['document_id'],amount_usd_per_share=amount,
                amount_evidence=amounts[0][1] if amount is not None else None,
                pay_date=pay,record_date=record,ex_date=ex,publication_date=pub,citation=doc['document_id'])
