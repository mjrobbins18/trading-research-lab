"""Frozen conservative regex baseline for USD dividend notices.

Consumes supplied source text only; missing/ambiguous fields stay null.
Not a general financial-document parser.
"""
import re,json
from datetime import datetime
from pathlib import Path

MONTH=r'(?:January|February|March|April|May|June|July|August|September|October|November|December)'
DATE=MONTH+r'\s+\d{1,2},?\s+\d{4}'


def unique(matches):
    values=set(matches)
    return next(iter(values)) if len(values)==1 else None


def datevalue(value):
    if not value:return None
    return datetime.strptime(value.replace(',',''),'%B %d %Y').date().isoformat()


def extract(doc):
    text=doc['text']
    amount=unique(re.findall(r'(?:cash\s+|quarterly\s+|regular\s+|monthly\s+)*dividend\s+of\s+\$([\d.]+)\s+per\s+(?:common\s+)?share',text,re.I))
    pay=unique(re.findall(r'payable\s+(?:on\s+)?('+DATE+r')',text,re.I))
    record=unique(re.findall(r'(?:shareholders|stockholders)\s+of\s+record\s+(?:as\s+of\s+)?(?:the\s+close\s+of\s+business\s+)?(?:on\s+)?('+DATE+r')',text,re.I))
    ex=unique(re.findall(r'ex-dividend\s+date\s+(?:is\s+|of\s+|will\s+be\s+)?('+DATE+r')',text,re.I))
    # Publication metadata must be explicitly supplied, never inferred from payment dates.
    pub=doc.get('explicit_publication_date')
    return {'document_id':doc['document_id'],'amount_usd_per_share':float(amount) if amount else None,
            'pay_date':datevalue(pay),'record_date':datevalue(record),'ex_date':datevalue(ex),
            'publication_date':pub,'citation':doc['document_id']}

if __name__=='__main__':
    docs=json.loads(Path('outputs/authentic-extraction/documents.json').read_text())
    result=[extract(d) for d in docs]
    Path('outputs/authentic-extraction/run-01/code-answers.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Frozen code extraction complete; no labels read.')
