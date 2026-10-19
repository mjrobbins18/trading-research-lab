"""Research-only dividend receivables. Not yet integrated into LEAN.

Call accrue before ex-date trades, with entitled shares in the same units as
the raw per-share distribution. Call release when cash becomes available.
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal


def money(value):
    result = Decimal(str(value))
    if not result.is_finite() or result < 0:
        raise ValueError('Expected finite nonnegative amount')
    return result


@dataclass(frozen=True)
class Distribution:
    event_id: str
    symbol: str
    ex_date: date
    pay_date: date
    amount_per_share: Decimal
    source: str
    verified: bool

    def __post_init__(self):
        if not self.event_id or not self.symbol or not self.source:
            raise ValueError('Missing event identity or source')
        if not isinstance(self.ex_date, date) or not isinstance(self.pay_date, date):
            raise ValueError('Missing or invalid distribution dates')
        if self.pay_date < self.ex_date:
            raise ValueError('Payment precedes entitlement')
        if self.verified is not True:
            raise ValueError('Unresolved distribution cannot fund a verified simulation')
        object.__setattr__(self, 'amount_per_share', money(self.amount_per_share))


class Receivables:
    def __init__(self):
        self._events = {}
        self._paid = set()
        self._last_release = None

    def accrue(self, event, entitled_shares, today):
        if today != event.ex_date:
            raise ValueError('Accrual must occur on ex-date')
        if self._last_release is not None and today < self._last_release:
            raise ValueError('Cannot accrue in the past')
        entitlement = money(entitled_shares) * event.amount_per_share
        record = (event, entitlement)
        if event.event_id in self._events:
            if self._events[event.event_id] != record:
                raise ValueError('Conflicting duplicate event')
            return Decimal(0)
        self._events[event.event_id] = record
        return entitlement

    @property
    def outstanding(self):
        return sum((amount for key, (_, amount) in self._events.items()
                    if key not in self._paid), Decimal(0))

    def release(self, today):
        if self._last_release is not None and today < self._last_release:
            raise ValueError('Payment clock moved backwards')
        self._last_release = today
        due = [key for key, (event, _) in self._events.items()
               if key not in self._paid and event.pay_date <= today]
        cash = sum((self._events[key][1] for key in due), Decimal(0))
        self._paid.update(due)
        return cash
