"""Read-only comparison of issuer distributions with the frozen raw-price CSVs."""
import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd


def audit(workbook, data, output):
    if output.exists() and any(output.iterdir()):
        raise ValueError('Output must be empty')
    output.mkdir(parents=True, exist_ok=True)
    source = pd.read_excel(workbook, sheet_name='dividend')
    source.columns = source.columns.str.strip()
    source['source_row'] = source.index + 2
    source['symbol'] = source.TICKER.str.strip()
    source = source[source.symbol.isin(['SPY', 'BIL'])].copy()
    source['date'] = pd.to_datetime(source['EX-DATE']).dt.strftime('%Y-%m-%d')
    source['pay_date'] = pd.to_datetime(source['PAYABLE DATE']).dt.strftime('%Y-%m-%d')
    components = ['DIVIDEND ($)', 'SHORT TERM CAPITAL GAIN ($)', 'LONG TERM CAPITAL GAIN ($)']
    # Missing optional capital gains mean no reported capital gain. A missing dividend is an error.
    summaries, details = {}, []
    hashes = {str(workbook): hashlib.sha256(workbook.read_bytes()).hexdigest()}
    for symbol in ('SPY', 'BIL'):
        path = data / f'{symbol}.csv'
        hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        prices = pd.read_csv(path)
        rows = source[source.symbol.eq(symbol) & source.date.between(prices.date.min(), prices.date.max())].copy()
        if rows.date.duplicated().any() or rows['DIVIDEND ($)'].isna().any():
            raise ValueError('Duplicate dates or missing issuer dividend')
        rows['issuer_total'] = rows[components].fillna(0).sum(axis=1)
        joined = rows[['symbol', 'date', 'pay_date', 'source_row', 'issuer_total']].merge(
            prices[['date', 'dividend']], on='date', how='outer', validate='one_to_one', indicator=True)
        # Keep every issuer row, including explicit zero distributions, and all source cash events.
        joined = joined[joined.issuer_total.notna() | joined.dividend.ne(0)].copy()
        joined['symbol'] = symbol
        joined['difference'] = joined.dividend - joined.issuer_total
        joined['status'] = 'within_rounding_tolerance'
        # Before the BIL reverse split, restoring raw values also restores a 0.001 rounding step.
        # After the split, Yahoo still reports amounts to three decimals. Permit half that step.
        joined.loc[joined.difference.abs() > .000501, 'status'] = 'amount_conflict'
        joined.loc[joined._merge.ne('both'), 'status'] = 'missing_source_date'
        joined['payment_delay_days'] = (pd.to_datetime(joined.pay_date) - pd.to_datetime(joined.date)).dt.days
        joined['invalid_payment_date'] = joined.payment_delay_days.lt(0) | joined.pay_date.isna()
        nonzero = joined[joined.issuer_total.gt(0) & ~joined.invalid_payment_date]
        summaries[symbol] = {
            'issuer_rows': len(rows), 'issuer_nonzero': int(rows.issuer_total.ne(0).sum()),
            'snapshot_nonzero': int(prices.dividend.ne(0).sum()),
            'status_counts': joined.status.value_counts().to_dict(),
            'invalid_payment_dates': int(joined.invalid_payment_date.sum()),
            'payment_delay_min_days': int(nonzero.payment_delay_days.min()),
            'payment_delay_max_days': int(nonzero.payment_delay_days.max()),
            'payment_delay_median_days': float(nonzero.payment_delay_days.median()),
        }
        details.append(joined.drop(columns='_merge'))
    pd.concat(details).sort_values(['symbol', 'date']).to_csv(output / 'comparison.csv', index=False)
    result = {'source_url': 'https://www.ssga.com/library-content/products/fund-data/etfs/us/spdr-etf-historical-distributions.xlsx',
              'retrieved_date': '2026-10-16', 'hashes': hashes, 'rounding_tolerance_per_share': .000501,
              'summary': summaries, 'scope': 'Distributions only; no independent OHLC or split verification.'}
    (output / 'audit.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(summaries, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--workbook', required=True, type=Path)
    parser.add_argument('--data', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    audit(args.workbook, args.data, args.output)
