"""Run a pinned LEAN image offline with narrowly scoped mounts; no broker credentials."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--data', type=Path, required=True)
    p.add_argument('--results', type=Path, required=True)
    p.add_argument('--mode', choices=['trend', 'spy', 'bil', 'mixed'], default='trend')
    p.add_argument('--bps', type=int, choices=[5, 10, 25], default=5)
    p.add_argument('--lookback', type=int, choices=[8, 10, 12], default=10)
    p.add_argument('--payment-dates', action='store_true')
    p.add_argument('--recent-period', action='store_true')
    args = p.parse_args()
    source = Path(__file__).resolve().parent
    data, output = args.data.resolve(), args.results.resolve()
    if output.exists() and any(output.iterdir()):
        raise RuntimeError('Results directory must be new/empty; preserve previous experiments')
    output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((data / 'manifest.json').read_text())
    if args.payment_dates and 'payments.csv' not in manifest['files']:
        raise ValueError('Payment schedule must be present and hashed')
    for name, digest in manifest['files'].items():
        if hashlib.sha256((data / name).read_bytes()).hexdigest() != digest:
            raise RuntimeError(f'Data changed: {name}')
    config = {
        'environment': 'backtesting', 'live-mode': False,
        'algorithm-type-name': 'MonthlyTrend', 'algorithm-language': 'Python',
        'algorithm-location': '/project/main.py', 'data-folder': '/Lean/Data',
        'results-destination-folder': '/results', 'debugging': False,
        'parameters': {'mode': args.mode, 'bps': str(args.bps), 'lookback': str(args.lookback)},
        'log-handler': 'QuantConnect.Logging.CompositeLogHandler',
        'messaging-handler': 'QuantConnect.Messaging.Messaging',
        'job-queue-handler': 'QuantConnect.Queues.JobQueue',
        'api-handler': 'QuantConnect.Api.Api',
        'map-file-provider': 'QuantConnect.Data.Auxiliary.LocalDiskMapFileProvider',
        'factor-file-provider': 'QuantConnect.Data.Auxiliary.LocalDiskFactorFileProvider',
        'data-provider': 'QuantConnect.Lean.Engine.DataFeeds.DefaultDataProvider',
        'object-store': 'QuantConnect.Lean.Engine.Storage.LocalObjectStore',
        'data-aggregator': 'QuantConnect.Lean.Engine.DataFeeds.AggregationManager',
        'setup-handler': 'QuantConnect.Lean.Engine.Setup.BacktestingSetupHandler',
        'result-handler': 'QuantConnect.Lean.Engine.Results.BacktestingResultHandler',
        'data-feed-handler': 'QuantConnect.Lean.Engine.DataFeeds.FileSystemDataFeed',
        'real-time-handler': 'QuantConnect.Lean.Engine.RealTime.BacktestingRealTimeHandler',
        'history-provider': ['QuantConnect.Lean.Engine.HistoricalData.SubscriptionDataReaderHistoryProvider'],
        'transaction-handler': 'QuantConnect.Lean.Engine.TransactionHandlers.BacktestingTransactionHandler',
        'job-user-id': '0', 'api-access-token': '', 'job-organization-id': '',
        'maximum-data-points-per-chart-series': 100000,
        'symbol-minute-limit': 100, 'symbol-second-limit': 100, 'symbol-tick-limit': 100,
        'show-missing-data-logs': True,
    }
    (output / 'config.json').write_text(json.dumps(config, indent=2))
    if args.payment_dates or args.recent_period:
        config['parameters'].update({'payment-dates': str(args.payment_dates).lower(), 'start': '2023-01-01',
                                     'end': '2026-08-31', 'trade-start': '2023-12-29'})
        (output / 'config.json').write_text(json.dumps(config, indent=2))
    lock = json.loads((source / 'runtime-lock.json').read_text())
    provenance = {'runtime': lock, 'parameters': config['parameters'],
                  'data_manifest_sha256': hashlib.sha256((data / 'manifest.json').read_bytes()).hexdigest(),
                  'source_sha256': {x.name: hashlib.sha256(x.read_bytes()).hexdigest()
                                    for x in source.glob('*.py')}}
    (output / 'provenance.json').write_text(json.dumps(provenance, indent=2))
    command = ['docker', 'run', '--rm', '--network', 'none', '--cap-drop', 'ALL',
               '--security-opt', 'no-new-privileges', '--memory', '3g',
               '-v', f'{source}:/project:ro', '-v', f'{data}:/research-data:ro',
               '-v', f'{output}:/results']
    for folder in ('daily', 'factor_files', 'map_files'):
        command += ['-v', f'{data}/lean/equity/usa/{folder}:/Lean/Data/equity/usa/{folder}:ro']
    command += [lock['image'], '--config', '/results/config.json']
    with (output / 'console.log').open('w') as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
    log = (output / 'console.log').read_text()
    print(log[-6000:])
    if result.returncode or 'Runtime Error' in log or not (output / 'ledger.json').exists():
        raise SystemExit('Backtest failed; inspect console.log')


if __name__ == '__main__':
    main()
