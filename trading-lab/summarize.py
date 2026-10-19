"""Compute comparison metrics from verified daily ledgers, excluding warm-up."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def metrics(frame, start, end, cash_returns):
    earlier = frame.loc[frame.index < start]
    sample = frame.loc[(frame.index >= start) & (frame.index <= end)]
    initial = float(earlier.equity.iloc[-1]) if len(earlier) else 100000.
    returns = sample.equity.pct_change()
    returns.iloc[0] = sample.equity.iloc[0] / initial - 1
    base_date = pd.Timestamp(earlier.index[-1]) if len(earlier) else pd.Timestamp(start) - pd.Timedelta(days=1)
    years = (pd.Timestamp(sample.index[-1]) - base_date).days / 365.25
    wealth = pd.Series([initial] + sample.equity.tolist())
    drawdown = wealth / wealth.cummax() - 1
    excess = returns - cash_returns.reindex(sample.index)
    return {'start': sample.index[0], 'end': sample.index[-1], 'sessions': len(sample),
            'cagr': (float(sample.equity.iloc[-1]) / initial) ** (1 / years) - 1,
            'annual_volatility': float(returns.std(ddof=1) * np.sqrt(252)),
            'maximum_drawdown': float(drawdown.min()),
            'excess_sharpe': float(excess.mean() / excess.std(ddof=1) * np.sqrt(252)) if excess.std() else None,
            'ending_equity': float(sample.equity.iloc[-1]),
            'average_invested_fraction': float((1 - sample.cash / sample.equity).mean())}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--data', type=Path, required=True)
    p.add_argument('--runs', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    bill = pd.read_csv(args.data / 'BIL.csv').set_index('date')
    cash_returns = (bill.close + bill.dividend) / (bill.close.shift(1) / bill.split_ratio) - 1
    periods = {'full': ('2008-01-01', '2026-09-30'), '2008-2015': ('2008-01-01', '2015-12-31'),
               '2016-2020': ('2016-01-01', '2020-12-31'), '2021-2025': ('2021-01-01', '2025-12-31'),
               '2026-YTD': ('2026-01-01', '2026-09-30')}
    rows = []
    for run in sorted(args.runs.iterdir()):
        if not run.is_dir():
            continue
        verification = json.loads((run / 'verification.json').read_text())
        if not verification.get('passed'):
            raise ValueError(f'Unverified run: {run.name}')
        frame = pd.DataFrame(json.loads((run / 'ledger.json').read_text())).set_index('date')
        for period, (start, end) in periods.items():
            rows.append({'experiment': run.name, 'period': period, **metrics(frame, start, end, cash_returns)})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(args.output, index=False)
    print(pd.DataFrame(rows).query('period == "full"').to_string(index=False))


if __name__ == '__main__':
    main()
