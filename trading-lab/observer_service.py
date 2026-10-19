"""Durable, bounded paper observation; transport rejects all broker writes."""
from market_data_policy import MarketDataError
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import time
from urllib.parse import urlsplit

import requests
from alpaca_order_adapter import PaperBroker
from order_controller import Controller
from supervised_runner import cycle


class ReadFailure(RuntimeError):
    pass


class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE IF NOT EXISTS observations (id INTEGER PRIMARY KEY, payload TEXT);
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY, payload TEXT, delivered INTEGER DEFAULT 0,
                attempts INTEGER DEFAULT 0);
        ''')

    def get(self, key, default=None):
        row = self.db.execute('SELECT value FROM meta WHERE key=?', (key,)).fetchone()
        return row[0] if row else default

    def put(self, key, value):
        self.db.execute('INSERT OR REPLACE INTO meta VALUES (?,?)', (key, str(value)))

    def record(self, report):
        # Observation, transition state and alert are one atomic transaction.
        signature = report['status'] + ':' + report.get('error_type', '')
        if report.get('reason'): signature += ':' + report['reason']
        market = report.get('market', {})
        unhealthy = sorted(s for s,m in market.items() if m['market_open'] and not m['fresh_open_quote'])
        if unhealthy: signature += ':ineligible:' + ','.join(unhealthy)
        payload = json.dumps(report, sort_keys=True)
        with self.db:
            self.db.execute('INSERT INTO observations(payload) VALUES (?)', (payload,))
            previous = self.get('status')
            if signature != previous and (previous is not None or report['status'] == 'halted' or unhealthy):
                self.db.execute('INSERT INTO alerts(payload) VALUES (?)', (payload,))
            self.put('status', signature)

    def deliver(self, sink=None, limit=3):
        # Sink must deduplicate by stable ID: interruption after delivery may repeat it.
        if sink is not None:
            rows = self.db.execute('SELECT id,payload FROM alerts WHERE delivered=0 ORDER BY id LIMIT ?', (limit,)).fetchall()
            for identity, payload in rows:
                with self.db:
                    self.db.execute('UPDATE alerts SET attempts=attempts+1 WHERE id=?', (identity,))
                try:
                    sink(str(identity), json.loads(payload))
                except Exception:
                    break  # Never expose destination exception text or flood retries.
                with self.db:
                    self.db.execute('UPDATE alerts SET delivered=1 WHERE id=?', (identity,))
        return self.db.execute('SELECT count(*) FROM alerts WHERE delivered=0').fetchone()[0]


class ReadOnlyTransport:
    def __init__(self, session, store, sleep=time.sleep, now=time.time, budget=60):
        self.session, self.store, self.sleep, self.now = session, store, sleep, now
        self.remaining = budget

    def request(self, method, url, **kwargs):
        parsed = urlsplit(url)
        if method != 'GET' or parsed.scheme != 'https' or parsed.netloc not in (
                'paper-api.alpaca.markets', 'data.alpaca.markets'):
            raise ReadFailure('Read-only paper transport rejected request')
        kwargs.update(timeout=20, allow_redirects=False)
        for attempt in range(3):
            if self.remaining <= 0:
                raise ReadFailure('Read budget exhausted')
            wait = float(self.store.get('next_request', '0')) - self.now()
            if wait > 60:
                raise ReadFailure('Request cooldown requires later run')
            if wait > 0:
                self.sleep(wait)
            # Persist reservation before issuing request; restart cannot erase cooldown.
            with self.store.db:
                self.store.put('next_request', self.now() + 1)
            self.remaining -= 1
            try:
                response = self.session.request(method, url, **kwargs)
            except (requests.Timeout, requests.ConnectionError):
                response = None
            if response is not None and response.status_code not in (429, 500, 502, 503, 504):
                return response
            delay = 2 ** attempt
            if response is not None:
                retry_after = response.headers.get('Retry-After')
                if retry_after is not None:
                    try:
                        delay = max(delay, float(retry_after))
                        if not 0 <= delay <= 3600:
                            raise ValueError()
                    except ValueError:
                        delay = 3600  # Unparsed header: defer, never retry too early.
            with self.store.db:
                self.store.put('next_request', self.now() + delay)
            if attempt == 2 or delay > 60:
                raise ReadFailure('Transient read retries exhausted or deferred')
        raise ReadFailure('Read failed')

    def get(self, url, **kwargs):
        return self.request('GET', url, **kwargs)


def observe(controller, store):
    try:
        report = cycle(controller)
    except Exception as exc:
        report = dict(status='halted', error_type=type(exc).__name__, orders_submitted=0)
        if isinstance(exc, MarketDataError): report['reason'] = exc.code
    report['checked_at'] = datetime.now(timezone.utc).isoformat()
    store.record(report)
    report['pending_alerts'] = store.deliver()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--journal', type=Path, default=Path('work/account-guard/controller.json'))
    parser.add_argument('--state', type=Path, default=Path('work/observer-service/state.sqlite'))
    args = parser.parse_args()
    # Controller's exclusive journal lock also serializes service runs.
    broker = PaperBroker()
    controller = Controller(args.journal, broker)
    store = None
    try:
        store = Store(args.state)
        broker.session = ReadOnlyTransport(broker.session, store)
        report = observe(controller, store)
        print(json.dumps(report))
        return int(report['status'] != 'observed')
    finally:
        if store is not None:
            store.db.close()
        controller.close()


if __name__ == '__main__':
    raise SystemExit(main())
