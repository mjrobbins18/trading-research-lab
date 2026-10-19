"""Frozen, prose-aware deterministic comparator for a narrow authored document exam.

Handwritten domain/phrase rules, no model, no answer-key reads. Unknown language
abstains. This is not a general document parser or independent dataset benchmark.
"""
import json,re
from datetime import datetime
from pathlib import Path
from decimal import Decimal


def assess(packet):
    claim=packet['proposed_claim'];sources=[s for s in packet['sources'] if s['id']!='routing']
    text=' '.join(s['text'] for s in sources)
    decision='abstain';issue='unparsed'
    if 'distribution receivable' in claim:
        issue='entitlement'
        ex=re.search(r'ex-date April (\d+)',text)
        bought=re.search(r'bought (\d+) shares (?:on April (\d+)|at the opening on April (\d+))',text)
        rate=re.search(r'USD ([\d.]+) per share',text)
        amount=re.search(r'\$([\d.]+)',claim)
        if all((ex,bought,rate,amount)):
            day=int(bought[2] or bought[3]);entitled=day<int(ex[1])
            decision='supported' if entitled and Decimal(bought[1])*Decimal(rate[1])==Decimal(amount[1]) else 'abstain'
    elif 'spendable cash' in claim:
        issue='cash_timing'
        if 'added USD' in text and 'to available cash, with no hold' in text:decision='supported'
    elif 'index value' in claim:
        issue='future_revision';proposed=re.search(r'index value of ([\d.]+)',claim)
        eligible=[s for s in sources if datetime.fromisoformat(s['available_at'])<=datetime.fromisoformat(packet['audit_as_of'])]
        for s in eligible:
            v=re.search(r'Original release .*?index ([\d.]+)\.',s['text'])
            if proposed and v and Decimal(proposed[1])==Decimal(v[1]):decision='supported'
    elif 'agree on the per-share' in claim:
        issue='conflict';cents=re.search(r'Final amount: ([\d.]+) US cents',text);dollars=re.search(r'Final amount: USD ([\d.]+)',text)
        if cents and dollars and Decimal(cents[1])/100==Decimal(dollars[1]):decision='supported'
    elif 'authenticated broker export' in claim:
        issue='provenance'
        copied=re.search(r'Copied from export (\w+)',text);retrieved=re.search(r'retrieved export (\w+)',text)
        if copied and retrieved and copied[1]==retrieved[1] and 'Exact file hash matched' in text:decision='supported'
    elif 'includes both price P&L' in claim:
        issue='return_accounting'
        total=re.search(r'reported USD ([\d.]+)',claim)
        price=re.search(r'price-change P&L of USD ([\d.]+)',text)
        distribution=re.search(r'All period distributions sum to USD ([\d.]+)',text)
        if total and price and distribution and Decimal(total[1])==Decimal(price[1])+Decimal(distribution[1]):decision='supported'
    elif 'fully executed' in claim:
        issue='execution'
        desired=re.search(r'fully executed for (\d+) shares',claim)
        quantities=re.findall(r'(\d+) (?:shares in trade A|in trade B)',text)
        if desired and len(quantities)==2 and sum(map(int,quantities))==int(desired[1]) and 'No remaining quantity' in text:decision='supported'
    elif 'completed month-end' in claim:
        issue='month_completion'
        if 'recorded after the March 31 close' in text and datetime.fromisoformat(packet['audit_as_of']).month>3:decision='supported'
    elif 'already available' in claim:
        issue='timezone'
        if all(datetime.fromisoformat(s['available_at'])<=datetime.fromisoformat(packet['audit_as_of']) for s in sources):decision='supported'
    elif 'supported final distribution' in claim:
        issue='supersession'
        if 'issuer-approved final notice replaces the preliminary estimate' in text and 'earlier amount is withdrawn' in text:decision='supported'
    return dict(case_id=packet['case_id'],decision=decision,issue='none' if decision=='supported' else issue,
                requested_exposure=0,citations=[s['id'] for s in sources],
                explanation='Frozen domain/phrase rules support this claim.' if decision=='supported' else 'Frozen domain/phrase rules did not establish this claim.')

if __name__=='__main__':
    import time
    started=time.perf_counter();packets=json.loads(Path('outputs/specialist-comparison/candidate-packets.json').read_text())
    answers=[assess(p) for p in packets]
    Path('outputs/specialist-comparison/run-01/code-answers.json').write_text(json.dumps(answers,indent=2)+'\n')
    Path('outputs/specialist-comparison/run-01/code-timing.json').write_text(json.dumps({'elapsed_seconds':time.perf_counter()-started,'external_model_calls':0},indent=2)+'\n')
    print('Plain-code comparison completed. No answer key or model accessed.')
