"""Build deterministic synthetic SPY/BIL daily bars for offline tests.

The research runs used licensed vendor prices, which this public copy does not
redistribute. These bars reuse only the real NYSE session calendar and the
public SPY/BIL ex-dividend dates; every price and amount is generated.
"""
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent / 'synthetic-prices'


def build(seed=20261019):
    rng = np.random.default_rng(seed)
    days = pd.read_csv(ROOT / 'sessions.csv').date
    ex_dates = pd.read_csv(ROOT / 'payments.csv')
    specs = {'SPY': (380.0, 0.0005, 0.011, 1.6), 'BIL': (91.5, 0.00015, 0.0003, 0.33)}
    for symbol, (start, drift, vol, payout) in specs.items():
        close = start * np.exp(np.cumsum(rng.normal(drift, vol, len(days))))
        gap = rng.normal(0, vol / 3, len(days))
        open_ = np.round(np.r_[start, close[:-1]] * np.exp(gap), 2)
        close = np.round(close, 2)
        frame = pd.DataFrame({'date': days, 'open': open_,
                              'high': np.round(np.maximum(open_, close) + 0.05, 2),
                              'low': np.round(np.minimum(open_, close) - 0.05, 2),
                              'close': close, 'volume': 1_000_000, 'dividend': 0.0, 'split_ratio': 1.0})
        dates = set(ex_dates[ex_dates.symbol == symbol].ex_date)
        frame.loc[frame.date.isin(dates), 'dividend'] = payout
        frame.to_csv(ROOT / f'{symbol}.csv', index=False)


if __name__ == '__main__':
    build()
