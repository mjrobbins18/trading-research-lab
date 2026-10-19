"""Additional source-level checks. Frozen v3 benchmark remains unchanged."""
import re
from context_extractor import DATE,PAY,RECORD,date_fact,validate as structural_validate


def validate(answer,doc):
    result=structural_validate(answer,doc)
    if not result['passed']:return result
    errors=[];text=doc['text'];events=answer['events']
    header=re.search(r'Record Dates\s*\|\s*Payable Dates\s*\n',text,re.I)
    if header:
        rows=[]
        for line in text[header.end():].splitlines():
            m=re.fullmatch(r'\s*('+DATE+r')\s*\|\s*('+DATE+r')\s*',line,re.I)
            if m:rows.append((date_fact(m[1],line,'record'),date_fact(m[2],line,'scheduled')))
        if len(events)!=len(rows):errors.append('table:installment_count')
        for i,(event,(record,pay)) in enumerate(zip(events,rows)):
            for field,expected in [('record_date',record),('pay_date',pay)]:
                if any(event[field][k]!=expected[k] for k in ('value','kind','status','cutoff')):errors.append(f'{i}:{field}:table_mapping')
    else:
        patterns={'pay_date':PAY,'record_date':RECORD,'ex_date':r'ex-dividend date\s+(?:is\s+)?(?P<date>'+DATE+')'}
        for i,event in enumerate(events):
            for field,pattern in patterns.items():
                matches=list(re.finditer(pattern,text,re.I))
                if matches and event[field]['status']=='absent':errors.append(f'{i}:{field}:source_event_omitted')
                if field=='pay_date':
                    for m in matches:
                        f=date_fact(m['date'],m.group(0),'scheduled')
                        if f['kind']=='earliest' and event[field]['value']==f['value'] and event[field]['kind']!='earliest':errors.append(f'{i}:{field}:source_lower_bound')
    return {'passed':not errors,'errors':errors,'cash_available_confirmed':False,'scope':'Known source patterns only; not independent semantic verification'}
