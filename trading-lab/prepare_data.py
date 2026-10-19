"""Download an exploratory Yahoo snapshot and convert two ETFs to LEAN daily data.

No adjusted-close input is used. Undo Yahoo split normalization before writing
raw-price LEAN bars and separate corporate-action factors.
"""
import argparse
import csv
import hashlib
import io
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from zipfile import ZipFile, ZIP_DEFLATED

import exchange_calendars as xcals
import pandas as pd
import requests

NY = ZoneInfo('America/New_York')
START = '2007-01-01'
END = '2026-10-01'  # exclusive: only completed months


def parse_chart(payload):
    result = payload['chart']['result'][0]
    splits = {datetime.fromtimestamp(x['date'], NY).date().isoformat():
              x['numerator'] / x['denominator']
              for x in result.get('events', {}).get('splits', {}).values()}
    q = result['indicators']['quote'][0]
    dividends = {datetime.fromtimestamp(x['date'], NY).date().isoformat(): x['amount']
                 for x in result.get('events', {}).get('dividends', {}).values()}
    rows = []
    for i, timestamp in enumerate(result['timestamp']):
        day = datetime.fromtimestamp(timestamp, NY).date().isoformat()
        values = [q[k][i] for k in ('open', 'high', 'low', 'close', 'volume')]
        if any(v is None for v in values):
            raise ValueError(f'Missing price/volume at {day}')
        # Yahoo OHLC and dividends are adjusted for subsequent splits. Undo that
        # adjustment, then let LEAN apply each event on its actual session.
        future_ratio = math.prod(ratio for d, ratio in splits.items() if d > day)
        o, h, l, c = [round(float(v) * future_ratio, 4) for v in values[:4]]
        if not (0 < l <= min(o, c) <= max(o, c) <= h):
            raise ValueError(f'Invalid OHLC at {day}')
        rows.append(dict(date=day, open=o, high=h, low=l, close=c,
                         volume=int(values[4]), dividend=dividends.get(day, 0.0) * future_ratio,
                         split_ratio=splits.get(day, 1.0)))
    days = [r['date'] for r in rows]
    if days != sorted(set(days)):
        raise ValueError('Duplicate or unordered sessions')
    if set(dividends) - set(days):
        raise ValueError('Dividend has no corresponding bar')
    return rows


def factor_rows(rows):
    # A factor row belongs to the session BEFORE the ex-date.
    factor, split_factor = 1.0, 1.0
    events = []
    for i in range(len(rows) - 1, 0, -1):
        dividend = rows[i]['dividend']
        previous = rows[i - 1]
        if dividend and rows[i]['split_ratio'] != 1:
            raise ValueError('Same-day split and dividend requires separate verification')
        if dividend:
            if not 0 < dividend < previous['close']:
                raise ValueError('Invalid dividend')
            factor *= 1 - dividend / previous['close']
        split_factor /= rows[i]['split_ratio']
        if dividend or rows[i]['split_ratio'] != 1:
            events.append((previous['date'].replace('-', ''), factor, split_factor, previous['close']))
    return [(rows[0]['date'].replace('-', ''), factor, split_factor, rows[0]['close'])] + list(reversed(events)) + [('20501231', 1, 1, 0)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    calendar = xcals.get_calendar('XNYS', start=START, end=END)
    session_dates = [x.date().isoformat() for x in calendar.sessions if START <= x.date().isoformat() < END]
    manifest = {'purpose': 'Exploratory public snapshot; not independent market-data validation',
                'downloaded_at': datetime.now(timezone.utc).isoformat(), 'start': START, 'end_exclusive': END,
                'files': {}, 'symbols': {}, 'calendar_version': xcals.__version__}
    all_rows = {}
    for symbol in ('SPY', 'BIL'):
        raw = root / f'{symbol}.yahoo.json'
        if not raw.exists():
            response = requests.get(f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}',
                params={'period1': int(pd.Timestamp(START, tz='UTC').timestamp()),
                        'period2': int(pd.Timestamp(END, tz='UTC').timestamp()),
                        'interval': '1d', 'events': 'div,splits'},
                headers={'User-Agent': 'Mozilla/5.0'}, timeout=60)
            response.raise_for_status()
            raw.write_text(response.text)
        rows = parse_chart(json.loads(raw.read_text()))
        expected = [d for d in session_dates if rows[0]['date'] <= d <= '2026-09-30']
        if [r['date'] for r in rows] != expected:
            raise ValueError(f'{symbol}: session coverage does not match XNYS calendar')
        all_rows[symbol] = rows
        with (root / f'{symbol}.csv').open('w') as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        base = root / 'lean' / 'equity' / 'usa'
        for folder in ('daily', 'factor_files', 'map_files'):
            (base / folder).mkdir(parents=True, exist_ok=True)
        daily = '\n'.join(','.join([r['date'].replace('-', '') + ' 00:00'] +
                            [str(round(r[k] * 10000)) for k in ('open', 'high', 'low', 'close')] +
                            [str(r['volume'])]) for r in rows) + '\n'
        with ZipFile(base / 'daily' / f'{symbol.lower()}.zip', 'w', ZIP_DEFLATED) as z:
            z.writestr(f'{symbol.lower()}.csv', daily)
        factors = '\n'.join(f'{d},{pf:.12f},{sf},{p:.4f}' for d, pf, sf, p in factor_rows(rows)) + '\n'
        (base / 'factor_files' / f'{symbol.lower()}.csv').write_text(factors)
        (base / 'map_files' / f'{symbol.lower()}.csv').write_text(
            f"{rows[0]['date'].replace('-', '')},{symbol.lower()},P\n20501231,{symbol.lower()},P\n")
        manifest['symbols'][symbol] = {'rows': len(rows), 'first': rows[0]['date'],
            'last': rows[-1]['date'], 'dividends': sum(r['dividend'] != 0 for r in rows)}
    # Calendar is saved independently from price rows to detect missing observations.
    pd.DataFrame({'date': session_dates}).to_csv(root / 'sessions.csv', index=False)
    for path in sorted(root.rglob('*')):
        if path.is_file() and path.name != 'manifest.json':
            manifest['files'][str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    (root / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest['symbols'], indent=2))


if __name__ == '__main__':
    main()
