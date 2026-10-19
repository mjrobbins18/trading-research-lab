"""Offline fixed-slot observation scoring; never infers continuous quote coverage."""
import math
from collections import Counter

def score(plan, rows, as_of):
    start,end,step=plan['open_at'],plan['close_at'],plan['cadence_seconds']
    if not all(isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x) for x in (start,end,step,as_of)):
        raise ValueError('Finite times required')
    if end<=start or step!=60 or (end-start)%step:raise ValueError('Invalid regular-session grid')
    slots=list(range(int(start),int(end),60))
    if start!=int(start) or end!=int(end):raise ValueError('Whole-second schedule required')
    grouped={t:[] for t in slots};outside=0
    for r in rows:
        t=r.get('scheduled_at')
        if t not in grouped:outside+=1;continue
        grouped[t].append(r)
    due=[t for t in slots if t+120<=as_of]
    results=[];reasons=Counter();eligible=Counter();unsafe=0
    for t in due:
        rs=grouped[t];reason='observed';good={s:False for s in ('SPY','BIL')}
        if not rs:reason='missing'
        elif len(rs)!=1:reason='duplicate_slot'
        else:
            r=rs[0];a,b=r.get('started_at'),r.get('completed_at')
            valid=all(isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x) for x in (a,b))
            if not valid or not t<=a<=b<=as_of:reason='invalid_timing'
            elif b-t>=120:reason='missed_deadline'
            elif r.get('status')!='observed':reason='observation_failed'
            elif r.get('reconciled') is not True:reason='reconciliation_unverified'
            elif r.get('orders_submitted')!=0:reason='unexpected_order_activity'
            elif r.get('stop_file_present') or r.get('open_orders') or r.get('unresolved_intents'):reason='account_not_ready'
            else:
                m=r.get('market',{})
                for symbol in good:
                    q=m.get(symbol,{});age=q.get('quote_age_seconds')
                    good[symbol]=(q.get('feed')=='sip' and q.get('market_open') is True
                       and isinstance(age,(int,float)) and not isinstance(age,bool) and math.isfinite(age) and 0<=age<=60)
            if r.get('decision_eligible') is True and (reason!='observed' or not all(good.values())):unsafe+=1
        reasons[reason]+=1
        for symbol,value in good.items():eligible[symbol]+=int(value)
        results.append(dict(scheduled_at=t,status=reason,quote_eligible=good))
    available=reasons['observed'];fraction=available/len(due) if due else None
    complete=as_of>=end+120
    return dict(regular_slots=len(slots),due_slots=len(due),pending_slots=len(slots)-len(due),complete=complete,
        statuses=dict(reasons),observation_availability=fraction,quote_eligible_slots=dict(eligible),
        quote_eligibility_fraction={s:eligible[s]/len(due) if due else None for s in ('SPY','BIL')},
        unsafe_decisions=unsafe,outside_grid_rows=outside,slots=results,
        observation_gate_passed=bool(complete and fraction is not None and fraction>=.99 and unsafe==0 and outside==0
            and not any(reasons[k] for k in ('duplicate_slot','invalid_timing','reconciliation_unverified','unexpected_order_activity','observation_failed','account_not_ready'))),
        continuous_quote_coverage_measured=False,unattended_trading_qualified=False)
