"""Explicit delayed variant of frozen reference.simulate; zero-delay parity tested."""
import math
import pandas as pd
from reference import signals

def simulate(prices, mode='trend', bps=5, lookback=10, payment_schedule=None,
             trade_start='2007-12-31', end='2026-09-30', delay_sessions=0):
    if delay_sessions not in (0, 1, 2):
        raise ValueError('Unsupported delay')
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
    pending_due = None
    for session, day in enumerate(prices['SPY'].index):
        if day > end:
            break
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
        orders_today = pending if pending_due is not None and session >= pending_due else []
        for s, quantity in orders_today:
            price = bars[s].open * (1 + rate * (1 if quantity > 0 else -1))
            if quantity > 0 and quantity * price > cash + 1e-6:
                fills.append({'date': day, 'symbol': s, 'quantity': 0, 'price': price, 'status': 'Canceled'})
                continue
            shares[s] += quantity
            cash -= quantity * price
            fills.append({'date': day, 'symbol': s, 'quantity': quantity, 'price': price, 'status': 'Filled'})
        if orders_today:
            pending = []
            pending_due = None
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

        if stage == 'buy' and not pending:
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
        if pending and pending_due is None:
            pending_due = session + 1 + delay_sessions
        if cash < -.01 or min(shares.values()) < 0:
            raise AssertionError('Reference cash/position constraint failed')
        ledger.append({'date': day, 'equity': nav, 'cash': cash,
                       'spy': shares['SPY'], 'bil': shares['BIL']})
        if payment_schedule is not None:
            ledger[-1]['receivable'] = outstanding
    return pd.DataFrame(ledger).set_index('date'), pd.DataFrame(fills)

