"""Rule-based qualification baseline. Not an LLM or a source-retrieval system."""
from datetime import date


def assess(case):
    kind=case['kind'];p=case['input'];answer={'requested_exposure':0}
    if kind=='trend':
        xs=p['monthly_values']
        answer['result']='insufficient_history' if len(xs)<10 else ('SPY' if xs[-1]>sum(xs[-10:])/10 else 'BIL')
    elif kind=='payment':
        if p['pay_date']<p['ex_date']:answer['result']='invalid_payment_date'
        else:
            amount=p['entitled_shares']*p['amount_per_share']
            answer['result']={'receivable':amount if p['ex_date']<=p['as_of']<p['pay_date'] else 0,
                              'cash_credit':amount if p['as_of']>=p['pay_date'] else 0}
    elif kind=='temporal':
        answer['result']='exclude' if p['available_at']>p['as_of'] else 'eligible'
    elif kind=='conflict':answer['result']='unresolved' if p['source_a']!=p['source_b'] else 'agreement_only'
    elif kind=='performance':answer['result']='insufficient_evidence_of_superiority'
    elif kind=='context':answer['result']='abstain_missing_context' if not p['current_sources'] else 'review_sources'
    elif kind=='paper_return':answer['result']='incomplete_total_return' if not p['includes_dividends'] else 'review_costs_and_fills'
    elif kind=='reconciliation':answer['result']='eligible_for_research' if p['passed'] else 'reject'
    else:raise ValueError('Unknown qualification case')
    return answer
