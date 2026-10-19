"""Audit a downloaded Tiingo snapshot without modifying either data source."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from reference import signals


def compare(data, tiingo, output):
    output.mkdir(parents=True, exist_ok=False)
    manifest = json.loads((tiingo / 'manifest.json').read_text())
    result, details, original, alternative = {}, [], {}, {}
    for symbol in ('SPY', 'BIL'):
        path = tiingo / f'{symbol}.json'
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != manifest['files'][path.name]['sha256']:
            raise ValueError('Snapshot hash mismatch')
        t = pd.DataFrame(json.loads(path.read_text()))
        t['date'] = pd.to_datetime(t.date, utc=True).dt.strftime('%Y-%m-%d')
        t = t.set_index('date').rename(columns={'divCash': 'dividend', 'splitFactor': 'split_ratio'})
        y = pd.read_csv(data / f'{symbol}.csv').set_index('date')
        for frame in (t, y):
            if frame.index.duplicated().any() or not frame.index.is_monotonic_increasing:
                raise ValueError('Duplicate or unsorted dates')
            if not np.isfinite(frame[['open', 'high', 'low', 'close', 'dividend', 'split_ratio']]).all().all():
                raise ValueError('Missing or non-finite values')
            if (frame[['open', 'high', 'low', 'close', 'split_ratio']] <= 0).any().any():
                raise ValueError('Nonpositive prices or split ratio')
        missing = sorted(set(y.index) - set(t.index))
        extra = sorted(set(t.index) - set(y.index))
        if missing or extra:
            raise ValueError(f'{symbol}: session mismatch: missing={missing}, extra={extra}')
        stats = {'rows': len(t), 'first': t.index[0], 'last': t.index[-1],
                 'tiingo_sha256': digest, 'baseline_sha256': hashlib.sha256((data / f'{symbol}.csv').read_bytes()).hexdigest(),
                 'missing_dates': missing, 'extra_dates': extra, 'fields': {}}
        for field, tolerance in [('open', .010001), ('high', .010001), ('low', .010001),
                                 ('close', .010001), ('dividend', .000501), ('split_ratio', 1e-10)]:
            difference = t[field] - y[field]
            bad = difference.abs() > tolerance
            stats['fields'][field] = {'tolerance': tolerance, 'beyond_tolerance': int(bad.sum()),
                                      'max_abs_difference': float(difference.abs().max())}
            for day in difference.index[bad]:
                details.append({'symbol': symbol, 'date': day, 'field': field,
                                'baseline': y.loc[day, field], 'tiingo': t.loc[day, field],
                                'difference': difference.loc[day]})
        stats['tiingo_splits'] = t.loc[t.split_ratio.ne(1), 'split_ratio'].to_dict()
        result[symbol] = stats
        original[symbol], alternative[symbol] = y, t
    a, b = signals(original), signals(alternative)
    if list(a.index) != list(b.index):
        raise ValueError('Signal date mismatch')
    decisions = pd.DataFrame({'baseline_target': a.target, 'tiingo_target': b.target,
                              'baseline_index': a['index'], 'tiingo_index': b['index']})
    decisions['changed'] = a.target != b.target
    decisions.to_csv(output / 'signals.csv')
    pd.DataFrame(details, columns=['symbol', 'date', 'field', 'baseline', 'tiingo', 'difference']).to_csv(output / 'exceptions.csv', index=False)
    result['signals'] = {'count': len(decisions), 'changed': int(decisions.changed.sum()),
                         'changed_dates': list(decisions.index[decisions.changed])}
    result['scope'] = 'Raw prices, cash dividends, split factors, date coverage, and ten-month signals. Volume and payment dates excluded.'
    (output / 'comparison.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--data', type=Path, required=True)
    p.add_argument('--tiingo', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    compare(args.data, args.tiingo, args.output)
