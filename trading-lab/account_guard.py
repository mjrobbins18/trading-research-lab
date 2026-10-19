"""Conservative paper-account reconciliation. Money uses decimal arithmetic."""
import copy
import hashlib
import json
from decimal import Decimal

class ReconciliationError(RuntimeError):
    pass


def number(value):
    x = Decimal(str(value))
    if not x.is_finite():
        raise ReconciliationError('Nonfinite account value')
    return x


def digest(event):
    return hashlib.sha256(json.dumps(event, sort_keys=True).encode()).hexdigest()


def events(snapshot):
    result = {}
    for event in snapshot['activities']:
        key = event['id']
        if key in result:
            raise ReconciliationError('Duplicate activity ID in snapshot')
        result[key] = digest(event)
    return result


def checkpoint(snapshot):
    if snapshot['orders'] or snapshot['positions']:
        raise ReconciliationError('Initial checkpoint requires a flat account with no open orders')
    if snapshot['blocked']:
        raise ReconciliationError('Account is blocked')
    return dict(account=snapshot['account'], cash=str(number(snapshot['cash'])), positions={},
                seen=events(snapshot), initial_equity=str(number(snapshot['equity'])))


def reconcile(state, snapshot, known_order_ids):
    if state['account'] != snapshot['account']:
        raise ReconciliationError('Account binding mismatch')
    if snapshot['blocked']:
        raise ReconciliationError('Account is blocked')
    current = events(snapshot)
    if any(current.get(k) != v for k, v in state['seen'].items()):
        raise ReconciliationError('Activity history missing or revised')
    new = copy.deepcopy(state)
    cash = number(state['cash'])
    positions = {s: number(q) for s, q in state['positions'].items()}
    for event in snapshot['activities']:
        if event['id'] in state['seen']:
            continue
        if event['activity_type'] != 'FILL' or event['order_id'] not in known_order_ids:
            raise ReconciliationError('Unrecognized account activity requires review')
        qty, price = number(event['qty']), number(event['price'])
        if qty <= 0 or price <= 0 or event['side'] not in ('buy', 'sell'):
            raise ReconciliationError('Invalid fill activity')
        signed = qty if event['side'] == 'buy' else -qty
        positions[event['symbol']] = positions.get(event['symbol'], Decimal(0)) + signed
        cash -= signed * price
    positions = {s: q for s, q in positions.items() if q}
    observed = {p['symbol']: number(p['qty']) for p in snapshot['positions'] if number(p['qty'])}
    if positions != observed or abs(cash - number(snapshot['cash'])) > Decimal('.01'):
        raise ReconciliationError('Cash or position reconciliation mismatch')
    new.update(cash=str(cash), positions={s: str(q) for s, q in positions.items()}, seen=current)
    return new


def permit(state, snapshot, intent, spent):
    # Explicit research limits, not an investment recommendation.
    cost = number(intent['qty']) * number(intent['limit_price'])
    if snapshot['orders']:
        raise ReconciliationError('Open account orders block new submissions')
    if any(p['symbol'] not in ('SPY', 'BIL') or number(p['qty']) < 0 for p in snapshot['positions']):
        raise ReconciliationError('Unsupported account position')
    gross = sum((abs(number(p['market_value'])) for p in snapshot['positions']), Decimal(0))
    if intent['side'] not in ('buy', 'sell') or cost <= 0:
        raise ReconciliationError('Invalid order side or amount')
    selling = intent['side'] == 'sell'
    if selling:
        held = number(state['positions'].get(intent['symbol'], 0))
        observed = sum((number(p['qty']) for p in snapshot['positions']
                        if p['symbol'] == intent['symbol']), Decimal(0))
        if (intent.get('reduce_only') is not True or number(intent['qty']) <= 0
            or held != observed or number(intent['qty']) > held):
            raise ReconciliationError('Sell must reduce a reconciled long position')
    if (not selling and gross + cost > 1000) or number(spent) + cost > 1000:
        raise ReconciliationError('Cumulative research exposure limit exceeded')
    if not selling and cost > number(state['cash']):
        raise ReconciliationError('Insufficient reconciled cash')
    if number(snapshot['equity']) < number(state['initial_equity']) - 25:
        raise ReconciliationError('Research loss limit reached')
