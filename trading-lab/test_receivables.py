from datetime import date
from decimal import Decimal

import pytest

from receivables import Distribution, Receivables


def event(**changes):
    fields = dict(event_id='SPY:2021-12-17:cash', symbol='SPY',
                  ex_date=date(2021, 12, 17), pay_date=date(2022, 1, 31),
                  amount_per_share=Decimal('1.636431'), source='test fixture', verified=True)
    return Distribution(**(fields | changes))


def test_value_is_preserved_when_receivable_becomes_cash():
    ledger = Receivables()
    ledger.accrue(event(), 100, date(2021, 12, 17))
    cash = Decimal(10)
    before = cash + ledger.outstanding
    assert ledger.release(date(2021, 12, 31)) == 0
    assert ledger.outstanding == Decimal('163.643100')
    cash += ledger.release(date(2022, 1, 31))
    assert cash + ledger.outstanding == before
    assert ledger.outstanding == 0
    assert ledger.release(date(2022, 2, 1)) == 0


def test_sale_or_later_split_cannot_change_fixed_entitlement():
    ledger = Receivables()
    shares = 100
    ledger.accrue(event(), shares, event().ex_date)
    shares = 0  # Entire position sold after entitlement.
    assert ledger.release(event().pay_date) == Decimal('163.643100')
    other = Receivables()
    shares = 100
    other.accrue(event(), shares, event().ex_date)
    shares //= 2  # Subsequent reverse split affects positions, not money owed.
    assert other.release(event().pay_date) == Decimal('163.643100')


def test_duplicate_is_idempotent_but_conflict_fails():
    ledger = Receivables()
    assert ledger.accrue(event(), 100, event().ex_date) > 0
    assert ledger.accrue(event(), 100, event().ex_date) == 0
    with pytest.raises(ValueError, match='Conflicting'):
        ledger.accrue(event(), 101, event().ex_date)


@pytest.mark.parametrize('changes', [dict(pay_date=None), dict(pay_date=date(2021, 12, 1)),
                                    dict(verified=False), dict(amount_per_share='NaN'),
                                    dict(amount_per_share='-1')])
def test_bad_event_is_rejected(changes):
    with pytest.raises(ValueError):
        event(**changes)


def test_late_accrual_and_time_reversal_fail():
    ledger = Receivables()
    with pytest.raises(ValueError):
        ledger.accrue(event(), 100, date(2021, 12, 18))
    ledger.release(date(2022, 2, 1))
    with pytest.raises(ValueError):
        ledger.accrue(event(), 100, event().ex_date)
    with pytest.raises(ValueError):
        ledger.release(date(2022, 1, 31))
