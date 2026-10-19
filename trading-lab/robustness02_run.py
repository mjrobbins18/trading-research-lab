"""Offline predeclared robustness run; never writes frozen inputs."""
import hashlib,json,time
from pathlib import Path
import pandas as pd
from reference import load_prices,simulate as frozen
from robustness02_engine import simulate
OUT=Path('outputs/robustness-02')
def digest(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def metrics(ledger,fills,start,end):
    nav=ledger.equity.loc[start:end]
    daily=nav.pct_change().dropna()
    years=(pd.Timestamp(nav.index[-1])-pd.Timestamp(start)).days/365.25
    peak=nav.cummax().clip(lower=100000)
    return dict(ending_value=float(nav.iloc[-1]),total_return=float(nav.iloc[-1]/100000-1),cagr=float((nav.iloc[-1]/100000)**(1/years)-1),max_drawdown=float((nav/peak-1).min()),sharpe_zero_rf=float(daily.mean()/daily.std()*252**.5),filled_orders=int((fills.status=='Filled').sum()),canceled_orders=int((fills.status=='Canceled').sum()))
def main():
    began=time.monotonic();protocol=json.loads((OUT/'protocol.json').read_text());rows=[];costs=[];hashes={};parity=[]
    for label,start,end,data in protocol['periods']:
        root=Path(data);manifest=json.loads((root/'manifest.json').read_text());prices=load_prices(root);schedule=None
        for name in ('SPY.csv','BIL.csv')+ (('payments.csv',) if 'payments.csv' in manifest['files'] else ()):
            key=str(root/name); hashes[key]=digest(key)
            assert hashes[key]==manifest['files'][name],key
        if 'payments.csv' in manifest['files']:
            payments=pd.read_csv(root/'payments.csv');schedule={(r.symbol,r.ex_date):r.pay_date for r in payments.itertuples()}
        for mode in protocol['modes']:
            for delay in protocol['additional_execution_sessions']:
                for bps in protocol['bps_each_side']:
                    ledger,fills=simulate(prices,mode,bps,10,schedule,start,end,delay)
                    if delay==0:
                        old,oldfills=frozen(prices,mode,bps,10,schedule,start,end)
                        pd.testing.assert_frame_equal(ledger,old.loc[:end]);pd.testing.assert_frame_equal(fills,oldfills[oldfills.date<=end].reset_index(drop=True))
                        parity.append([label,mode,bps])
                    row=dict(period=label,mode=mode,bps=bps,delay_sessions=delay,**metrics(ledger,fills,start,end))
                    row['mean_spy_exposure']=float((ledger.spy.loc[start:end]*prices['SPY'].close.loc[start:end]/ledger.equity.loc[start:end]).mean())
                    months=len(pd.period_range(pd.Timestamp(start)+pd.Timedelta(days=1),end,freq='M'))
                    row['external_research_cost_300_per_month']=months*300
                    row['ending_wealth_after_external_research_cost']=row['ending_value']-months*300
                    rows.append(row)
                    stem=f'{label}-{mode}-{bps}bps-delay{delay}'
                    ledger.loc[start:end].to_json(OUT/(stem+'-ledger.json'),orient='table',indent=2)
                    fills.to_json(OUT/(stem+'-fills.json'),orient='records',indent=2)
                    if bps==0:
                        gross=ledger.equity.loc[start:end];notional=pd.Series(0.,index=gross.index)
                        for r in fills[fills.status=='Filled'].itertuples():
                            notional.loc[r.date]+=abs(r.quantity)*prices[r.symbol].loc[r.date,'open']
                        for fixed_bps in protocol['bps_each_side']:
                            nav=gross-notional.cumsum()*fixed_bps/10000
                            costs.append(dict(period=label,mode=mode,delay_sessions=delay,bps=fixed_bps,ending_value=float(nav.iloc[-1]),fixed_notional=float(notional.sum()),diagnostic_only=True))
    comparisons=[]
    for label,*_ in protocol['periods']:
        for delay in protocol['additional_execution_sessions']:
            for bps in protocol['bps_each_side']:
                scenario={r['mode']:r for r in rows if r['period']==label and r['delay_sessions']==delay and r['bps']==bps}
                t=scenario['trend']
                for bench in ('spy','mixed'):
                    b=scenario[bench];comparisons.append(dict(period=label,bps=bps,delay_sessions=delay,benchmark=bench,return_difference=t['total_return']-b['total_return'],sharpe_difference=t['sharpe_zero_rf']-b['sharpe_zero_rf'],drawdown_difference=t['max_drawdown']-b['max_drawdown'],passes=t['sharpe_zero_rf']>b['sharpe_zero_rf'] and t['max_drawdown']>=b['max_drawdown']))
    result=dict(protocol_sha256=digest(OUT/'protocol.json'),input_hashes=hashes,engine_sha256=digest('outputs/trading-lab/robustness02_engine.py'),frozen_reference_sha256=digest('outputs/trading-lab/reference.py'),runner_sha256=digest(__file__),scenarios=rows,fixed_exposure_cost_diagnostics=costs,comparisons=comparisons,zero_delay_exact_parity_cases=len(parity),decision='no_go_for_efficacy_claim' if not all(r['passes'] for r in comparisons) else 'descriptive_gate_pass_only',elapsed_seconds=time.monotonic()-began)
    (OUT/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('scenarios','comparisons','fixed_exposure_cost_diagnostics')},indent=2))
if __name__=='__main__':main()
