from AlgorithmImports import *
import csv
import json
import math
from collections import deque
from pathlib import Path


class OpeningSlippage:
    def __init__(self, bps):
        self.rate = bps / 10000

    def get_slippage_approximation(self, asset, order):
        # MOO slippage must not use the later closing price of a daily bar.
        return asset.open * self.rate


class CashGuardFill(EquityFillModel):
    def __init__(self, algorithm):
        super().__init__()
        self.algorithm = algorithm

    def market_on_open_fill(self, asset, order):
        fill = super().market_on_open_fill(asset, order)
        if fill.status == OrderStatus.FILLED and fill.fill_quantity > 0:
            if float(fill.fill_quantity * fill.fill_price) > float(self.algorithm.portfolio.cash) + 0.000001:
                # Daily-bar simulation policy: reject an unaffordable opening fill.
                # Do not look at the opening price to retroactively resize the order.
                fill.status = OrderStatus.CANCELED
                fill.fill_quantity = 0
                fill.message = 'Opening gap exceeds cash: simulated cash guard'
        return fill


class MonthlyTrend(QCAlgorithm):
    def initialize(self):
        if self.live_mode:
            raise RuntimeError('This algorithm is historical-only')
        self.payment_dates = self.get_parameter('payment-dates') == 'true'
        self.trade_start = self.get_parameter('trade-start') or '2007-12-31'
        self.last_date = self.get_parameter('end') or '2026-09-30'
        self.set_start_date(*map(int, (self.get_parameter('start') or '2007-01-01').split('-')))
        self.set_end_date(*map(int, self.last_date.split('-')))
        self.receivables = []
        self.payments = {}
        if self.payment_dates:
            for row in csv.DictReader(open('/research-data/payments.csv')):
                key = (row['symbol'], row['ex_date'])
                if key in self.payments or row['pay_date'] < row['ex_date']:
                    raise ValueError('Invalid payment schedule')
                self.payments[key] = row['pay_date']
        self.set_cash(100000)
        self.set_time_zone(TimeZones.NEW_YORK)
        self.settings.daily_precise_end_time = True
        self.set_brokerage_model(BrokerageName.ALPACA, AccountType.MARGIN)
        self.mode = self.get_parameter('mode') or 'trend'
        self.lookback = int(self.get_parameter('lookback') or 10)
        self.bps = float(self.get_parameter('bps') or 5)
        if self.mode not in ('trend', 'spy', 'bil', 'mixed') or self.lookback not in (8, 10, 12):
            raise ValueError('Unregistered experiment')
        self.assets = {}
        for name in ('SPY', 'BIL'):
            security = self.add_equity(name, Resolution.DAILY, fill_forward=False,
                                       data_normalization_mode=DataNormalizationMode.RAW)
            # Daily-bar engine buying-power checks can see the session close before
            # a simulated opening fill. Leave brokerage margin capacity available,
            # but CashGuardFill independently forbids purchases beyond actual cash.
            security.set_leverage(2)
            security.set_fee_model(ConstantFeeModel(0))
            security.set_slippage_model(OpeningSlippage(self.bps))
            security.set_fill_model(CashGuardFill(self))
            self.assets[name] = security.symbol
        sessions = list(csv.DictReader(open('/research-data/sessions.csv')))
        dates = [r['date'] for r in sessions]
        self.month_ends = {a for a, b in zip(dates, dates[1:]) if a[:7] != b[:7]}
        self.month_ends.add(dates[-1])  # data contract ends on a completed month
        self.sessions = set(dates)
        self.month_values = deque(maxlen=self.lookback)
        self.previous_close = None
        self.total_return_index = 100.0
        self.targets = None
        self.stage = None
        self.pending = set()
        self.queued_orders = []
        self.started = False
        self.signals, self.orders, self.ledger, self.distributions = [], [], [], []
        self.signal_date = None
        self._dividends_today = {}
        self.dividend_source = {}
        for name in self.assets:
            self.dividend_source[name] = {r['date']: float(r['dividend']) for r in
                csv.DictReader(open(f'/research-data/{name}.csv')) if float(r['dividend'])}
        self.schedule.on(self.date_rules.every_day(self.assets['SPY']),
                         self.time_rules.at(9, 0), self._flush_orders)

    def on_data(self, data):
        spy = self.assets['SPY']
        for symbol, event in data.dividends.items():
            event_day = event.time.date().isoformat()
            exact = self.dividend_source[symbol.value][event_day]
            correction = (exact - float(event.distribution)) * float(self.portfolio[symbol].quantity)
            # LEAN's factor-file dividend reader rounds per-share distributions
            # to cents. Restore source precision on the same ex-date, once only.
            self.portfolio.cash_book['USD'].add_amount(correction)
            if self.payment_dates:
                amount = exact * float(self.portfolio[symbol].quantity)
                pay_date = self.payments[(symbol.value, event_day)]
                self.portfolio.cash_book['USD'].add_amount(-amount)
                self.receivables.append((pay_date, amount))
            self.distributions.append({'date': event_day, 'symbol': symbol.value,
                                       'distribution': exact, 'engine_distribution': float(event.distribution),
                                       'cash_correction': correction, 'time': str(self.time)})
            if symbol == spy:
                self._dividends_today[event_day] = self._dividends_today.get(event_day, 0) + exact
        if not data.bars.contains_key(spy):
            if self.time.date().isoformat() in self.sessions and self.time.hour >= 16:
                raise RuntimeError('Missing SPY bar')
            return
        bar = data.bars[spy]
        day = bar.time.date().isoformat()
        if day not in self.sessions:
            raise RuntimeError('Unexpected trading session')
        dividend = self._dividends_today.pop(day, 0.0)
        close = float(bar.close)
        if self.previous_close is not None:
            self.total_return_index *= (close + dividend) / self.previous_close
        self.previous_close = close
        if self.payment_dates:
            cash_due = sum(amount for pay, amount in self.receivables if pay <= day)
            self.portfolio.cash_book['USD'].add_amount(cash_due)
            self.receivables = [(pay, amount) for pay, amount in self.receivables if pay > day]
        if day >= self.trade_start:
            if not data.bars.contains_key(self.assets['BIL']):
                raise RuntimeError('Missing BIL bar; preserve holdings and stop')
            if self.stage == 'buy' and not self.pending:
                self._submit_buys()
                self.stage = None
        if day in self.month_ends:
            self.month_values.append(self.total_return_index)
            if len(self.month_values) == self.lookback:
                average = sum(self.month_values) / self.lookback
                target = 'SPY' if self.total_return_index > average else 'BIL'
                self.signals.append({'date': day, 'index': self.total_return_index,
                                     'average': average, 'target': target})
                if day >= self.trade_start and day < self.last_date:
                    if self.mode == 'trend':
                        weights = {target: .99}
                    elif self.mode == 'mixed':
                        weights = {'SPY': .495, 'BIL': .495}
                    else:
                        weights = {self.mode.upper(): .99}
                    if self.pending or self.stage or self.queued_orders:
                        raise RuntimeError('Unresolved rebalance at next monthly decision')
                    self.signal_date = day
                    self.targets = weights
                    self.started = True
                    self._rebalance()
        cash = float(self.portfolio.cash)
        if cash < -.01:
            raise RuntimeError(f'Cash borrowing detected: {cash}')
        self.ledger.append({'date': day, 'equity': self._nav(),
                            'cash': cash, 'spy': float(self.portfolio[spy].quantity),
                            'bil': float(self.portfolio[self.assets['BIL']].quantity)})

        if self.payment_dates:
            self.ledger[-1]['receivable'] = sum(amount for _, amount in self.receivables)

    def _nav(self):
        return float(self.portfolio.total_portfolio_value) + sum(amount for _, amount in self.receivables)

    def _rebalance(self):
        if self.mode in ('spy', 'bil'):
            self._submit_buys()  # Reinvest cash without selling existing shares.
            return
        sells = []
        nav = self._nav()
        for name, symbol in self.assets.items():
            desired = math.floor(nav * self.targets.get(name, 0) / float(self.securities[symbol].price))
            delta = desired - int(self.portfolio[symbol].quantity)
            if delta < 0:
                sells.append((symbol, delta))
        if sells:
            self.stage = 'buy'
            for symbol, delta in sells:
                self._order(symbol, delta)
        else:
            self._submit_buys()

    def _submit_buys(self):
        cash = float(self.portfolio.cash)
        nav = self._nav()
        for name in sorted(self.targets):
            symbol = self.assets[name]
            price = float(self.securities[symbol].price)
            desired = math.floor(nav * self.targets[name] / price)
            delta = max(0, desired - int(self.portfolio[symbol].quantity))
            quantity = min(delta, math.floor(cash / (price * (1 + self.bps / 10000))))
            if quantity > 0:
                self._order(symbol, quantity)
                cash -= quantity * price * (1 + self.bps / 10000)

    def _order(self, symbol, quantity):
        self.queued_orders.append((symbol, quantity, self.signal_date))

    def _flush_orders(self):
        queued, self.queued_orders = self.queued_orders, []
        for symbol, quantity, signal_date in queued:
            ticket = self.market_on_open_order(symbol, quantity, tag=f'signal={signal_date}')
            if ticket.status not in (OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.INVALID):
                self.pending.add(ticket.order_id)

    def on_order_event(self, event):
        if event.status == OrderStatus.INVALID:
            raise RuntimeError(f'Order rejected: {event.message}')
        if event.status in (OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.INVALID):
            self.pending.discard(event.order_id)
        self.orders.append({'time': str(self.time), 'id': event.order_id,
                            'symbol': event.symbol.value, 'status': str(event.status),
                            'quantity': float(event.fill_quantity), 'price': float(event.fill_price),
                            'message': event.message})

    def on_end_of_algorithm(self):
        for name in ('signals', 'orders', 'ledger', 'distributions'):
            Path(f'/results/{name}.json').write_text(json.dumps(getattr(self, name), indent=2))
