"""Offline fault-injection broker for bounded buy-limit controller tests.

Explicit ask/quantity events model liquidity; no queue priority or fill probability
is inferred from historical bars. All state lives under a supplied test directory.
"""
import copy
import json
from decimal import Decimal
from pathlib import Path
from order_controller import PAPER, TERMINAL

D = lambda x: Decimal(str(x))

class SimulatedBroker:
    endpoint = PAPER

    def __init__(self, root, cash='1000'):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.account_lock_dir = self.root / 'locks'
        self.path = self.root / 'broker.json'
        self.state = (json.loads(self.path.read_text()) if self.path.exists() else
                      dict(cash=str(cash), orders={}, activities=[], positions={}, posts=0))
        self.market = dict(now=100, quote_time=99, market_open=True, bid=99, ask=100, feed='synthetic')
        self.hidden = False
        self.lose_response = False
        self.save()

    @property
    def posts(self): return self.state['posts']

    def save(self): self.path.write_text(json.dumps(self.state))

    def market_inputs(self, symbol): return dict(self.market)

    def observe(self):
        positions = [dict(symbol=s, qty=q, market_value=str(D(q)*100))
                     for s, q in self.state['positions'].items() if D(q)]
        return dict(account='offline-simulation', cash=self.state['cash'],
                    equity=str(D(self.state['cash'])+sum((D(p['market_value']) for p in positions), D(0))),
                    positions=positions, activities=copy.deepcopy(self.state['activities']),
                    orders=[copy.deepcopy(o) for o in self.state['orders'].values() if o['status'] not in TERMINAL],
                    blocked=False)

    def submit(self, cid, intent):
        self.state['posts'] += 1
        if cid in self.state['orders']: raise AssertionError('Duplicate POST')
        reserved = sum((D(o['qty'])*D(o['limit_price'])-D(o['filled_qty'])*D(o['limit_price'])
                        for o in self.state['orders'].values() if o['status'] not in TERMINAL), D(0))
        status = 'rejected' if D(intent['qty'])*D(intent['limit_price']) > D(self.state['cash'])-reserved else 'new'
        order = dict(intent, order_id=f'order-{self.posts}', client_order_id=cid, status=status, filled_qty=0)
        self.state['orders'][cid] = order
        self.save()
        if self.lose_response: raise TimeoutError('Injected response loss')
        return copy.deepcopy(order)

    def lookup(self, cid):
        return None if self.hidden else copy.deepcopy(self.state['orders'].get(cid))

    def cancel(self, cid):
        o = self.state['orders'][cid]
        if o['status'] not in TERMINAL: o['status'] = 'canceled'
        self.save()

    def liquidity(self, cid, ask, available, slippage_bps=0):
        """Inject one executable liquidity event, with nonnegative adverse slippage."""
        ask, available, slippage_bps = map(D, (ask, available, slippage_bps))
        if not all(x.is_finite() for x in (ask, available, slippage_bps)) or ask <= 0 or min(available, slippage_bps) < 0:
            raise ValueError('Invalid liquidity event')
        o = self.state['orders'][cid]
        price = ask * (1 + slippage_bps / 10000)
        if o['status'] in TERMINAL or price > D(o['limit_price']): return D(0)
        qty = min(available, D(o['qty'])-D(o['filled_qty']))
        if qty == 0: return qty
        if qty*price > D(self.state['cash']): raise AssertionError('Simulation cash invariant')
        o['filled_qty'] = float(D(o['filled_qty'])+qty)
        o['status'] = 'filled' if D(o['filled_qty']) == D(o['qty']) else 'partially_filled'
        self.state['cash'] = str(D(self.state['cash'])-qty*price)
        symbol = o['symbol']
        self.state['positions'][symbol] = str(D(self.state['positions'].get(symbol, 0))+qty)
        self.state['activities'].append(dict(id=f"fill-{len(self.state['activities'])+1}",
            activity_type='FILL', order_id=o['order_id'], symbol=symbol, side=o['side'], qty=str(qty), price=str(price)))
        self.save()
        return qty
