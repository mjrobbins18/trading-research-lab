"""Download a separate data sample; never overwrite the baseline or log secrets."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import requests
from credentials import load_token


def fetch(output, distributions=False):
    token = load_token()
    output.mkdir(parents=True, exist_ok=False)
    manifest = {'source': 'Tiingo EOD API', 'retrieved_at': datetime.now(timezone.utc).isoformat(),
                'start': '2007-01-01', 'end': '2026-09-30', 'files': {}}
    for symbol in ('SPY', 'BIL'):
        url = (f'https://api.tiingo.com/tiingo/corporate-actions/{symbol}/distributions' if distributions
               else f'https://api.tiingo.com/tiingo/daily/{symbol}/prices')
        params = ({'startExDate': manifest['start'], 'endExDate': manifest['end']} if distributions
                  else {'startDate': manifest['start'], 'endDate': manifest['end'], 'format': 'json'})
        response = requests.get(url,
            params=params,
            headers={'Authorization': f'Token {token}'}, timeout=60)
        if response.status_code != 200:
            raise SystemExit(f'{symbol}: HTTP {response.status_code}; response body omitted to protect credentials.')
        rows = response.json()
        required = ({'exDate', 'paymentDate', 'distribution'} if distributions else
                    {'date', 'open', 'high', 'low', 'close', 'divCash', 'splitFactor'})
        if not isinstance(rows, list) or not rows or any(not required <= set(row) for row in rows):
            raise SystemExit(f'{symbol}: empty history or unexpected schema')
        path = output / f'{symbol}.json'
        path.write_text(json.dumps(rows, indent=2) + '\n')
        manifest['files'][path.name] = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'rows': len(rows), 'first_date': rows[0]['exDate' if distributions else 'date'],
            'last_date': rows[-1]['exDate' if distributions else 'date']}
    manifest['endpoint_kind'] = 'distributions' if distributions else 'daily_prices'
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print('Downloaded separate SPY and BIL snapshots. Coverage and values still require validation.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--distributions', action='store_true')
    args = parser.parse_args()
    fetch(args.output, args.distributions)
