import copy
import math
from datetime import datetime, timezone

import pandas as pd
import pytest

from prepare_data import factor_rows, parse_chart
from reference import signals, simulate


def prices():
    days = ['2007-03-30', '2007-04-30', '2007-05-31', '2007-06-29',
            '2007-07-31', '2007-08-31', '2007-09-28', '2007-10-31',
            '2007-11-30', '2007-12-31', '2008-01-02', '2008-01-31',
            '2008-02-01', '2008-02-04', '2008-02-29', '2008-03-03']
    result = {}
    for symbol in ('SPY', 'BIL'):
        values = [100. + n for n in range(len(days))] if symbol == 'SPY' else [50.] * len(days)
        result[symbol] = pd.DataFrame({'open': values, 'close': values, 'dividend': 0.,
                                      'split_ratio': 1.}, index=days)
    return result


def test_first_order_uses_next_session_open():
    p = prices()
    p['SPY'].loc['2008-01-02', 'open'] = 109.1
    _, fills = simulate(p)
    assert fills.iloc[0]['date'] == '2008-01-02'
    assert fills.iloc[0]['price'] == pytest.approx(109.1 * 1.0005)
    assert fills.iloc[0]['quantity'] == math.floor(99000 / 109)


def test_equality_goes_to_bills_and_requires_ten_months():
    p = prices()
    p['SPY']['close'] = 100.
    s = signals(p)
    assert s.index[0] == '2007-12-31'
    assert (s.target == 'BIL').all()


def test_future_prices_cannot_change_prior_signals():
    p = prices()
    original = signals(p)
    p['SPY'].loc['2008-02-01':, 'close'] *= 20
    changed = signals(p)
    pd.testing.assert_frame_equal(original.loc[:'2008-01-31'], changed.loc[:'2008-01-31'])


def test_dividend_prevents_false_price_loss():
    p = prices()
    p['SPY']['close'] = 100.
    p['SPY'].loc['2007-12-31':, 'close'] = 99.
    p['SPY'].loc['2007-12-31', 'dividend'] = 1.
    s = signals(p)
    assert s.loc['2007-12-31', 'index'] == pytest.approx(100.)


def test_gap_does_not_create_borrowing():
    p = prices()
    p['SPY'].loc['2008-01-02', 'open'] = 1000.
    ledger, fills = simulate(p)
    assert fills.iloc[0]['status'] == 'Canceled'
    assert ledger.cash.min() >= 0
    assert ledger.loc['2008-01-02', 'spy'] == 0


def test_switch_sells_before_next_session_purchase():
    p = prices()
    p['SPY'].loc['2008-01-31':, ['open', 'close']] = 50.
    _, fills = simulate(p)
    sales = fills[(fills.symbol == 'SPY') & (fills.quantity < 0)]
    purchases = fills[(fills.symbol == 'BIL') & (fills.quantity > 0)]
    assert sales.iloc[0]['date'] == '2008-02-01'
    assert purchases.iloc[0]['date'] == '2008-02-04'


def test_factor_file_encodes_dividend_on_previous_session():
    rows = [{'date': '2024-01-02', 'close': 100., 'dividend': 0., 'split_ratio': 1.},
            {'date': '2024-01-03', 'close': 99., 'dividend': 1., 'split_ratio': 1.}]
    f = factor_rows(rows)
    assert f[-2][0] == '20240102'
    assert f[-2][1] == pytest.approx(.99)
    assert f[-2][3] * (1 - f[-2][1] / f[-1][1]) == pytest.approx(1.)


def payload():
    timestamps = [int(datetime(2024, 1, day, 14, 30, tzinfo=timezone.utc).timestamp()) for day in (2, 3)]
    return {'chart': {'result': [{'timestamp': timestamps,
            'events': {'splits': {'x': {'date': timestamps[1], 'numerator': 1, 'denominator': 2}}},
            'indicators': {'quote': [{'open': [100., 102.], 'high': [100., 102.],
                                     'low': [100., 102.], 'close': [100., 102.], 'volume': [10, 20]}]}}]}}


def test_yahoo_reverse_split_is_restored_before_lean_conversion():
    rows = parse_chart(payload())
    assert rows[0]['close'] == 50.
    assert rows[1]['close'] == 102.
    assert rows[1]['split_ratio'] == .5
    f = factor_rows(rows)
    assert f[0][2] == 2.


def test_missing_price_is_rejected():
    j = payload()
    j['chart']['result'][0]['indicators']['quote'][0]['close'][0] = None
    with pytest.raises(ValueError, match='Missing'):
        parse_chart(j)


def test_same_day_split_dividend_fails_instead_of_guessing():
    rows = [{'date': '2024-01-02', 'close': 50., 'dividend': 0., 'split_ratio': 1.},
            {'date': '2024-01-03', 'close': 100., 'dividend': 1., 'split_ratio': .5}]
    with pytest.raises(ValueError, match='Same-day'):
        factor_rows(rows)
