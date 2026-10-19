"""Structural/evidence checks for research proposals, not permission to use cash."""
import math,re
from datetime import date
from qualified_extractor import DATE,iso

FIELDS={'pay_date':{'scheduled','earliest'},'record_date':{'record'},'ex_date':{'ex_dividend'},'publication_date':{'publication'}}


def validate(answer,doc):
    errors=[]
    if answer.get('document_id')!=doc['document_id'] or answer.get('citation')!=doc['document_id']:errors.append('source_identity')
    amount=answer.get('amount_usd_per_share');span=answer.get('amount_evidence')
    if amount is not None:
        if type(amount) not in (float,int) or not math.isfinite(amount) or amount<0:errors.append('amount_value')
        if not isinstance(span,str) or not span or span not in doc['text']:errors.append('amount_evidence')
    for field,kinds in FIELDS.items():
        value=answer.get(field)
        if not isinstance(value,dict):errors.append(field+':schema');continue
        if set(value)!={'value','kind','status','cutoff','evidence'}:errors.append(field+':keys')
        if value.get('status') not in ('explicit','contextual','ambiguous','absent'):errors.append(field+':status')
        if value.get('cutoff') not in (None,'close_of_business','start_of_business'):errors.append(field+':cutoff')
        if value.get('status')=='absent':
            if any(value.get(k) is not None for k in ('value','cutoff','evidence')) or value.get('kind')!='not_stated':errors.append(field+':absent')
            continue
        if value.get('kind') not in kinds:errors.append(field+':kind')
        if value.get('status')=='ambiguous':
            if value.get('value') is not None:errors.append(field+':ambiguous_value')
        else:
            try:
                if date.fromisoformat(value['value']).isoformat()!=value['value']:raise ValueError()
            except (ValueError,TypeError,KeyError):errors.append(field+':date')
        span=value.get('evidence')
        if field=='publication_date' and span=='metadata:explicit_publication_date':
            if value.get('value')!=doc.get('explicit_publication_date'):errors.append(field+':metadata')
            continue
        if not isinstance(span,str) or not span or not all(x in doc['text'] for x in span.split(' | ')):
            errors.append(field+':evidence');continue
        if field=='pay_date' and re.search(r'on\s+or\s+after',span,re.I) and value.get('kind')!='earliest':errors.append(field+':lost_lower_bound')
        if re.search(r'close of business',span,re.I) and value.get('cutoff')!='close_of_business':errors.append(field+':lost_cutoff')
        if re.search(r'start of business',span,re.I) and value.get('cutoff')!='start_of_business':errors.append(field+':lost_cutoff')
        if value.get('value') is not None:
            dates=[]
            for m in re.finditer(DATE,span,re.I):
                try:dates.append(iso(m.group(0)))
                except ValueError:pass
            if value['value'] not in dates:errors.append(field+':date_not_in_evidence')
    return {'passed':not errors,'errors':errors,'cash_available_confirmed':False,'research_only':True}
