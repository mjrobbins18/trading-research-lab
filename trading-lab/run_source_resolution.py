"""Reproduce retrospective enrichment of the frozen eight source packets."""
import json
from pathlib import Path
from resolved_dividend_events import extract, validate, fingerprint

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'outputs/source-resolution'

def run():
    docs=json.loads((ROOT/'outputs/independent-context-evaluation/candidate/documents.json').read_text())
    evidence=json.loads((OUT/'evidence.json').read_text())
    bundles=[];results=[]
    for d in docs:
        r=next(x for x in evidence['resolutions'] if x['document_id']==d['document_id'])
        claims=[]
        def add(field,value,scope=None,kind='direct',summary=None,locator='Dividend discussion'):
            claims.append(dict(field=field,value=value,security_class=scope,support_type=kind,evidence=[dict(url=r['source_urls'][0],locator=locator,summary=summary or r['support_summary'],retrieved_at=r['checked_date'])]))
        key=d['document_id']
        if any(s in key for s in ('pg_','walmart','coca','ibm','pepsico')):
            add('currency_context','USD',kind='cross_source_inference' if any(s in key for s in ('pg_','walmart','pepsico')) else 'direct')
        if 'pg_' in key:
            claims[0]['evidence'].append(dict(url=r['source_urls'][1],locator='Inline XBRL facts f-250/f-251 and unit usdPerShare',summary='Common and preferred 1.0065 facts carry USD/share units in the December 2024 filing. Linking this later reporting period to the earlier notices remains cross-source inference.',retrieved_at='2026-10-16'))
        if 'walmart' in key:
            claims[0]['evidence'].append(dict(url=r['source_urls'][0],locator='Inline XBRL annual dividend 0.83 and usdPerShare unit',summary='Annual 0.83 is explicitly USD/share; four 0.2075 installments are linked by the filing dividend paragraph. Currency mapping to each installment is inferred from that schedule.',retrieved_at='2026-10-16'))
            add('security_class','common','common')
            add('split_basis','post_split','common')
        if 'pepsico' in key:
            claims[0]['evidence'].append(dict(url=r['source_urls'][1],locator='Inline XBRL CommonStockDividendsPerShareDeclared 1.355, usdPerShare',summary='The 1.355 common-share fact has explicit USD/share units. Matching the filing fact to the earlier announcement is supplemental corroboration.',retrieved_at='2026-10-16'))
        if 'coca' in key:
            for field,value in [('payment_date','2024-12-16'),('record_date','2024-11-29')]:add(field,value,'common',locator='Issuer history row: declaration 2024-10-17; official-domain search-index rendering')
        b=dict(document_id=key,packet_sha256=fingerprint(d),claims=claims)
        a=extract(d,b)
        bundles.append(b);results.append(dict(document_id=key,proposal=a,validation=validate(a,d,b),disposition=r['disposition']))
    (OUT/'resolution-bundles.json').write_text(json.dumps(bundles,indent=2)+'\n')
    (OUT/'replay.json').write_text(json.dumps(results,indent=2)+'\n')
    print(json.dumps([dict(document_id=r['document_id'],events=len(r['proposal']['events']),status=r['validation']['status'],review=r['validation']['review_reasons']) for r in results],indent=2))

if __name__=='__main__':run()
