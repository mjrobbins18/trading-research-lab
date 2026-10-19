"""Independent pandas signal calculation and explicit cash/share ledger.

Does not import the LEAN algorithm or consume LEAN's signal decisions/fills.
"""
import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd


def load_prices(root):
    return {s: pd.read_csv(root / f'{s}.csv').set_index('date') for s in ('SPY', 'BIL')}


def signals(prices, lookback=10):
    spy = prices['SPY']
    gross = ((spy.close + spy.dividend) / (spy.close.shift(1) / spy.split_ratio)).fillna(1)
    index = gross.cumprod() * 100
    months = pd.to_datetime(index.index).to_period('M')
    monthly = index.groupby(months).tail(1)
    average = monthly.rolling(lookback).mean()
    result = pd.DataFrame({'index': monthly, 'average': average}).dropna()
    result['target'] = np.where(result['index'] > result.average, 'SPY', 'BIL')
    return result


def simulate(prices, mode='trend', bps=5, lookback=10, payment_schedule=None,
             trade_start='2007-12-31', end='2026-09-30'):
    # Optional v2 mode: schedule keys are (symbol, ex-date), values are verified
    # ISO payment dates. Amounts still come from the chosen price snapshot.
    if payment_schedule is not None:
        for symbol, frame in prices.items():
            for ex_date in frame.index[frame.dividend.ne(0)]:
                pay = payment_schedule.get((symbol, ex_date))
                if pay is None or pd.isna(pay) or str(pd.Timestamp(pay).date()) != pay or pay < ex_date:
                    raise ValueError(f'Missing or invalid payment date: {symbol} {ex_date}')
    monthly = signals(prices, lookback)
    cash, shares = 100000., {'SPY': 0, 'BIL': 0}
    pending, stage, targets = [], None, {}
    started = False
    ledger, fills = [], []
    rate = bps / 10000
    receivables = []
    for day in prices['SPY'].index:
        bars = {s: frame.loc[day] for s, frame in prices.items() if day in frame.index}
        for s, bar in bars.items():
            if bar.split_ratio != 1:
                new_shares = shares[s] * bar.split_ratio
                if new_shares != math.floor(new_shares):
                    # Explicit research convention; verifier must confirm LEAN's treatment.
                    previous = prices[s].loc[:day].iloc[-2].close
                    cash += (new_shares % 1) * previous / bar.split_ratio
                shares[s] = math.floor(new_shares)
            amount = shares[s] * bar.dividend
            if payment_schedule is None:
                cash += amount
            elif amount:
                receivables.append((payment_schedule[(s, day)], amount))
        for s, quantity in pending:
            price = bars[s].open * (1 + rate * (1 if quantity > 0 else -1))
            if quantity > 0 and quantity * price > cash + 1e-6:
                fills.append({'date': day, 'symbol': s, 'quantity': 0, 'price': price, 'status': 'Canceled'})
                continue
            shares[s] += quantity
            cash -= quantity * price
            fills.append({'date': day, 'symbol': s, 'quantity': quantity, 'price': price, 'status': 'Filled'})
        pending = []
        # Conservative research convention: payable cash becomes available at
        # the close of the first observed session on/after the payable date.
        # It cannot fund that session's opening orders.
        cash += sum(amount for pay, amount in receivables if pay <= day)
        receivables = [(pay, amount) for pay, amount in receivables if pay > day]
        outstanding = sum(amount for _, amount in receivables)
        nav = cash + outstanding + sum(shares[s] * bars[s].close for s in bars)

        def buys():
            available = cash
            out = []
            for s in sorted(targets):
                desired = math.floor(nav * targets[s] / bars[s].close)
                qty = min(max(0, desired - shares[s]), math.floor(available / (bars[s].close * (1 + rate))))
                if qty > 0:
                    out.append((s, qty))
                    available -= qty * bars[s].close * (1 + rate)
            return out

        if stage == 'buy':
            pending = buys()
            stage = None
        if day in monthly.index and trade_start <= day < end:
            targets = ({monthly.loc[day, 'target']: .99} if mode == 'trend' else
                       {'SPY': .495, 'BIL': .495} if mode == 'mixed' else {mode.upper(): .99})
            if pending:
                raise RuntimeError('Overlapping rebalance')
            started = True
            if mode in ('trend', 'mixed'):
                for s in shares:
                    desired = math.floor(nav * targets.get(s, 0) / bars[s].close)
                    if desired < shares[s]:
                        pending.append((s, desired - shares[s]))
            if pending:
                stage = 'buy'
            else:
                pending = buys()
        if cash < -.01 or min(shares.values()) < 0:
            raise AssertionError('Reference cash/position constraint failed')
        ledger.append({'date': day, 'equity': nav, 'cash': cash,
                       'spy': shares['SPY'], 'bil': shares['BIL']})
        if payment_schedule is not None:
            ledger[-1]['receivable'] = outstanding
    return pd.DataFrame(ledger).set_index('date'), pd.DataFrame(fills)


def verify(root, run):
    prices = load_prices(root)
    parameters = json.loads((run / 'provenance.json').read_text())['parameters']
    expected = signals(prices, int(parameters['lookback']))
    actual = pd.DataFrame(json.loads((run / 'signals.json').read_text())).set_index('date')
    if list(actual.index) != list(expected.index):
        raise AssertionError('Signal dates differ')
    if not (actual.target == expected.target).all():
        raise AssertionError('Signal targets differ')
    schedule = None
    if parameters.get('payment-dates') == 'true':
        payments = pd.read_csv(root / 'payments.csv')
        schedule = {(r.symbol, r.ex_date): r.pay_date for r in payments.itertuples()}
    ref, fills = simulate(prices, parameters['mode'], int(parameters['bps']), int(parameters['lookback']),
                          schedule, parameters.get('trade-start', '2007-12-31'), parameters.get('end', '2026-09-30'))
    observed = pd.DataFrame(json.loads((run / 'ledger.json').read_text())).set_index('date')
    if list(ref.index) != list(observed.index):
        raise AssertionError('Ledger dates differ')
    errors = {k: float((ref[k] - observed[k]).abs().max()) for k in ref.columns}
    events = pd.DataFrame(json.loads((run / 'orders.json').read_text()))
    actual_fills = events[events.status.str.upper() == 'FILLED'].reset_index(drop=True)
    reference_fills = fills[fills.status == 'Filled'].reset_index(drop=True)
    if len(actual_fills) != len(reference_fills):
        raise AssertionError(f'Fill count: {len(actual_fills)} != {len(reference_fills)}')
    if len(actual_fills):
        if not (actual_fills.symbol == reference_fills.symbol).all() or not (actual_fills.quantity == reference_fills.quantity).all():
            raise AssertionError('Filled symbols/quantities differ')
        if not (actual_fills.time.str[:10] == reference_fills.date).all():
            raise AssertionError('Fill session mismatch')
        if not np.allclose(actual_fills.price, reference_fills.price, atol=.000001, rtol=0):
            raise AssertionError('Opening fill prices differ')
        submissions = events[events.status.str.upper() == 'SUBMITTED'].set_index('id')
        for _, fill in actual_fills.iterrows():
            if not pd.Timestamp(fill.time) > pd.Timestamp(submissions.loc[fill.id, 'time']):
                raise AssertionError('Fill precedes order submission')
    if sum(events.status.str.upper() == 'CANCELED') != sum(fills.status == 'Canceled'):
        raise AssertionError('Opening gap cancellation counts differ')
    dividend_events = pd.DataFrame(json.loads((run / 'distributions.json').read_text()))
    max_div_error = 0.
    for s, frame in prices.items():
        expected_div = frame[frame.dividend != 0].dividend
        seen = dividend_events[dividend_events.symbol == s].set_index('date').distribution
        if list(seen.index) != list(expected_div.index):
            raise AssertionError(f'{s} dividend dates differ')
        max_div_error = max(max_div_error, float((seen - expected_div).abs().max()))
    report = {'signal_count': len(actual), 'signals_match': True,
              'maximum_signal_index_error': float((actual['index'] - expected['index']).abs().max()),
              'maximum_ledger_errors': errors, 'fill_count': len(actual_fills),
              'opening_fills_match': True, 'maximum_dividend_error': max_div_error,
              'minimum_cash': float(observed.cash.min()),
              'scope': 'Numerical consistency on one public snapshot; not independent source validation'}
    ref.to_csv(run / 'reference-ledger.csv')
    fills.to_csv(run / 'reference-fills.csv', index=False)
    print(json.dumps(report, indent=2))
    if errors['spy'] or errors['bil'] or max(errors['cash'], errors['equity'], errors.get('receivable', 0)) > .10 or max_div_error > .000001:
        raise AssertionError('Ledger/dividend reconciliation exceeds tolerance')
    report['passed'] = True
    (run / 'verification.json').write_text(json.dumps(report, indent=2))
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--data', type=Path, required=True)
    p.add_argument('--run', type=Path, required=True)
    a = p.parse_args()
    verify(a.data, a.run)
