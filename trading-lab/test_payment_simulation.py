import pandas as pd
import pytest

from reference import simulate
from test_research import prices


def test_payment_delay_keeps_value_but_changes_spendable_cash():
    p = prices()
    p['SPY'].loc['2008-01-31', 'dividend'] = 2
    instant, _ = simulate(p, mode='spy')
    delayed, _ = simulate(p, mode='spy', payment_schedule={('SPY', '2008-01-31'): '2008-02-04'})
    entitlement = delayed.loc['2008-01-02', 'spy'] * 2
    assert delayed.loc['2008-01-31', 'receivable'] == entitlement
    assert delayed.loc['2008-01-31', 'equity'] == pytest.approx(instant.loc['2008-01-31', 'equity'])
    assert delayed.loc['2008-01-31', 'cash'] == pytest.approx(instant.loc['2008-01-31', 'cash'] - entitlement)
    assert delayed.loc['2008-02-01', 'receivable'] == entitlement
    assert delayed.loc['2008-02-04', 'receivable'] == 0


def test_sale_does_not_erase_receivable():
    p = prices()
    p['SPY'].loc['2008-01-31':, ['open', 'close']] = 50
    p['SPY'].loc['2008-01-31', 'dividend'] = 1
    ledger, fills = simulate(p, payment_schedule={('SPY', '2008-01-31'): '2008-02-04'})
    assert ledger.loc['2008-02-01', 'spy'] == 0
    assert ledger.loc['2008-02-01', 'receivable'] > 0
    assert ledger.loc['2008-02-04', 'receivable'] == 0
    assert ledger.cash.min() >= 0


@pytest.mark.parametrize('schedule', [{}, {('SPY', '2008-01-31'): '2008-01-30'},
                                     {('SPY', '2008-01-31'): None}])
def test_missing_or_invalid_pay_date_fails_before_simulation(schedule):
    p = prices()
    p['SPY'].loc['2008-01-31', 'dividend'] = 1
    with pytest.raises(ValueError):
        simulate(p, payment_schedule=schedule)


def test_no_dividends_is_identical_in_both_modes():
    p = prices()
    before, old_fills = simulate(p)
    after, new_fills = simulate(p, payment_schedule={})
    pd.testing.assert_frame_equal(before, after.drop(columns='receivable'))
    pd.testing.assert_frame_equal(old_fills, new_fills)
