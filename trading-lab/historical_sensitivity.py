"""Reproduce predeclared retrospective cost stresses on audited recent data."""
import hashlib,json
from pathlib import Path
import pandas as pd
from reference import load_prices,simulate


def main():
    out=Path('outputs/historical-next-stage');protocol=json.loads((out/'protocol.json').read_text())
    root=Path(protocol['data']);manifest=json.loads((root/'manifest.json').read_text())
    for name in ('SPY.csv','BIL.csv','payments.csv'):
        if hashlib.sha256((root/name).read_bytes()).hexdigest()!=manifest['files'][name]:raise ValueError('Frozen input hash mismatch')
    prices=load_prices(root)
    payments=pd.read_csv(root/'payments.csv')
    schedule={(r.symbol,r.ex_date):r.pay_date for r in payments.itertuples()}
    rows=[];base={}
    for mode in protocol['modes']:
        for bps in protocol['bps_each_side']:
            ledger,fills=simulate(prices,mode,bps,10,schedule,protocol['trade_start'],protocol['end'])
            ledger=ledger.loc[protocol['trade_start']:protocol['end']]
            nav=ledger.equity
            years=(pd.Timestamp(nav.index[-1])-pd.Timestamp(nav.index[0])).days/365.25
            row=dict(mode=mode,bps=bps,ending_value=float(nav.iloc[-1]),
                     cagr=float((nav.iloc[-1]/nav.iloc[0])**(1/years)-1),
                     max_drawdown=float((nav/nav.cummax()-1).min()),
                     filled_orders=int((fills.status=='Filled').sum()),canceled_orders=int((fills.status=='Canceled').sum()))
            if bps==5:
                run=Path('work/release/runs')/(mode+'-pay')
                if not json.loads((run/'verification.json').read_text())['passed']:raise ValueError('Prior verification failed')
                saved=pd.DataFrame(json.loads((run/'ledger.json').read_text())).set_index('date').loc[ledger.index]
                row['maximum_prior_lean_ledger_error']=float((ledger-saved[ledger.columns]).abs().max().max())
                if row['maximum_prior_lean_ledger_error']>1e-6:raise ValueError('Baseline changed')
                base[mode]=nav
            ledger.to_json(out/f'{mode}-{bps}bps-ledger.json',orient='table',indent=2)
            rows.append(row)
    expenses=[dict(mode=m,monthly_expense_usd=cost,total_expense_usd=32*cost,
                   ending_wealth_after_external_expense=float(nav.iloc[-1]-32*cost))
              for m,nav in base.items() for cost in protocol['research_expense_per_month_usd']]
    comparisons=[]
    trend=base['trend']
    for mode in ('spy','bil','mixed'):
        monthly=pd.DataFrame({'trend':trend,'benchmark':base[mode]})
        monthly.index=pd.to_datetime(monthly.index)
        month_end=monthly.resample('ME').last()
        rolling=month_end.pct_change(12).dropna()
        comparisons.append(dict(benchmark=mode,ending_wealth_difference=float(trend.iloc[-1]-base[mode].iloc[-1]),
                                overlapping_12_month_windows=len(rolling),
                                trend_outperformed_windows=int((rolling.trend>rolling.benchmark).sum()),
                                worst_12_month_return_difference=float((rolling.trend-rolling.benchmark).min()),
                                best_12_month_return_difference=float((rolling.trend-rolling.benchmark).max())))
    result=dict(protocol_sha256=hashlib.sha256((out/'protocol.json').read_bytes()).hexdigest(),
                engine_sha256=hashlib.sha256(Path('outputs/trading-lab/reference.py').read_bytes()).hexdigest(),
                scenarios=rows,external_expenses=expenses,comparisons=comparisons,
                limitations=['Retrospective revised snapshots, not point-in-time evidence',
                             'Overlapping windows are dependent and are not significance tests',
                             'No agent intervention or model advantage evaluated',
                             'Only baseline cost paths rechecked against saved LEAN runs'])
    (out/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
