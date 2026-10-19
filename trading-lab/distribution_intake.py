"""Offline routing of structured distribution evidence; never grants order authority."""
from collections import Counter
from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import json

FIELDS = ('amount', 'ex_date', 'record_date', 'pay_date')


def route(records, tolerance='0.000001'):
    tolerance = Decimal(tolerance)
    if not tolerance.is_finite() or tolerance < 0:
        raise ValueError('Invalid comparison tolerance')
    counts = Counter((r.get('symbol'), r.get('ex_date')) for r in records)
    output = []
    for record in records:
        reasons = []
        symbol, ex_date = record.get('symbol'), record.get('ex_date')
        if not symbol or not ex_date:
            reasons.append('missing_event_identity')
        if counts[(symbol, ex_date)] > 1:
            reasons.append('duplicate_event_identity')
        sources = record.get('sources', [])
        if len(sources) < 2:
            reasons.append('insufficient_source_comparison')
        origins = {s.get('lineage') for s in sources if s.get('lineage')}
        if len(origins) < 2:
            reasons.append('shared_or_unknown_source_lineage')
        parsed = []
        valid_amounts = []
        for source in sources:
            if not source.get('source_ref') or not source.get('lineage'):
                reasons.append('missing_source_provenance')
            try:
                amount = Decimal(str(source['amount']))
                if not amount.is_finite() or amount < 0:
                    raise ValueError('invalid_amount')
                valid_amounts.append(amount)
                dates = {key: date.fromisoformat(source[key]) for key in FIELDS[1:]}
                if source['ex_date'] != ex_date:
                    reasons.append('ex_date_identity_conflict')
                if dates['record_date'] < dates['ex_date'] or dates['pay_date'] < dates['ex_date'] or dates['pay_date'] < dates['record_date']:
                    reasons.append('invalid_date_order')
                # Source amount units must be explicit; never silently split-adjust.
                if source.get('amount_basis') != 'nominal_per_share':
                    reasons.append('unknown_or_adjusted_amount_basis')
                parsed.append((amount, dates))
            except (KeyError, ValueError, TypeError, InvalidOperation):
                reasons.append('missing_or_invalid_field')
        if len(valid_amounts) >= 2:
            amounts = valid_amounts
            if max(amounts) - min(amounts) > tolerance:
                reasons.append('amount_conflict')
            # Zero vs positive can indicate payment existence, even below tolerance.
            if any(v == 0 for v in amounts) and any(v > 0 for v in amounts):
                reasons.append('payment_existence_conflict')
        if len(parsed) >= 2:
            for key in FIELDS[1:]:
                if len({v[1][key] for v in parsed}) != 1:
                    reasons.append(key + '_conflict')
        reasons.extend(record.get('open_issues', []))
        output.append(dict(symbol=symbol, ex_date=ex_date,
                           evidence_sha256=hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest(),
                           route='specialist_review' if reasons else 'routine_accounting_candidate',
                           reasons=sorted(set(reasons)),
                           historical_signal_use_authorized=False,
                           trading_authorized=False,
                           cash_receipt_confirmed=False))
    return output


if __name__ == '__main__':
    import argparse
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    records = json.loads(args.input.read_text())
    routed = route(records)
    result = {'records': routed, 'trading_authorized': False,
              'counts': dict(Counter(r['route'] for r in routed))}
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps(result['counts']))
