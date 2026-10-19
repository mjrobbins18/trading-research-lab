# Personal trading research lab

This project runs a monthly SPY/BIL experiment in a pinned LEAN container. It has no live-trading mode.

The project includes an independent signal calculation and a cash/share ledger. These calculations do not import the LEAN strategy.

## Dividend research assistant

The current offline extraction and validation implementation is revision 6.3 (`dividend_events_v63.py`).

It preserves unknown security identity, named share classes, distribution periods, and payment-date qualifications. Its output requires review and does not authorize orders.

## Run the experiment

Requirements: an ARM64 Mac, Docker, and Python 3.12. The pinned image includes LEAN and its Python runtime.

1. Extract the project archive.
2. Open a terminal in the extracted `trading-lab` directory.
3. Create the Python environment:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

4. Run the unit tests (offline; uses the fixtures in `fixtures/`):

```sh
.venv/bin/python -m pytest -q
```

5. Run a new historical experiment:

```sh
.venv/bin/python run_backtest.py --data data --results runs/new-trend --mode trend
```

6. Verify the results:

```sh
.venv/bin/python reference.py --data data --run runs/new-trend
```

The runner requires an empty results directory. It preserves earlier experiments.

The archive includes the original data snapshot. To download a separate snapshot, run:

```sh
.venv/bin/python prepare_data.py --root data-new
```

The downloader uses Yahoo's public chart endpoint. That endpoint can change or become unavailable. It requires network access.

The backtest container has no network access. It receives no brokerage credentials and mounts its inputs as read-only files.

## Files

### Local API credentials

`credentials.py` and `alpaca_credentials.py` prompt for keys and save them under `.local/secrets/` with owner-only permissions. That directory is ignored by Git and is not part of this public copy. A `TIINGO_API_TOKEN` environment variable takes precedence over the saved token.

| File | Purpose |
|---|---|
| `runtime-lock.json` | Container digest, architecture, and runtime versions |
| `prepare_data.py` | Download, audit, and convert public daily data |
| `main.py` | LEAN strategy, order schedule, and simulation controls |
| `reference.py` | Independent signals, portfolio simulation, and reconciliation |
| `test_research.py` | Regression tests for timing, distributions, gaps, and missing data |
| `summarize.py` | Metrics from verified results |
| `data/manifest.json` | Snapshot hashes and session coverage |
| `runs/` | Historical experiments and verification reports |

## Strategy behavior

The trend strategy observes ten monthly SPY total-return values. It chooses SPY above their mean and BIL otherwise.

Decisions occur after month-end closing data arrives. Orders enter the queue for submission at 09:00 New York time the next session.

Sales fill first. Replacement purchases enter the following session's opening auction. This adds one session in cash during switches.

The two buy-and-hold benchmarks reinvest available cash monthly. They do not sell shares to restore the buffer.

The mixed benchmark targets 49.5% SPY and 49.5% BIL each month. The trend strategy targets 99% in its selected ETF.

The base assumption charges five basis points per side through adverse opening fills. Separate explicit fees are zero in this exploratory version.

A large opening gap can make an order unaffordable. The simulation cancels that purchase and waits for the next monthly decision.

The brokerage model retains margin capacity for daily-bar processing. An independent cash constraint prevents actual borrowing at every simulated purchase.

## Accounting and data limits

The source contains historical revisions. This snapshot is not a certified record of information available at each historical date.

The converter reverses Yahoo's split adjustments before it creates raw-price bars. LEAN then applies the corporate actions on their recorded dates.

BIL has a reverse split in this snapshot. The independent ledger verifies its position and cash effects.

Volume remains as reported by Yahoo. This experiment does not use volume for signals, sizing, or liquidity estimates.

LEAN rounds factor-derived dividends to cents per share. The algorithm restores source precision with an explicit cash correction on each event date.

Both ledgers credit distributions on the ex-date. They do not model the delay until the payment date.

Daily bars represent opening fills, but LEAN reports their events when the daily bars arrive. These timestamps are simulation delivery times.

The fill model does not estimate auction capacity or market impact. It does not simulate partial fills, broker outages, or restart recovery.

The data converter rejects missing sessions and malformed prices. It rejects simultaneous split/dividend events rather than guessing their order.

Agreement between two calculations verifies implementation consistency. It does not verify the market-data source or establish investment skill.

## Before paper trading

October 16 audit update: `../evidence/data-validation-update.md` records an independent issuer distribution comparison and the next accounting specification.

The audit found three amount conflicts and one invalid issuer payment date. Prices and splits still require independent verification.

`audit_distributions.py` requires pandas and openpyxl for read-only workbook extraction. It does not modify the frozen simulation inputs.

Required work remains:

- Verify prices and corporate actions against an independent data provider.
- Replace daily-bar execution with a verified opening-auction or intraday model.
- Model dividend payment dates and explicit brokerage fees.
- Add tests for partial fills, rejected orders, duplicate prevention, and restart recovery.
- Verify the broker account's buying-power and settlement behavior.
- Freeze the strategy and agent versions before forward evaluation.

## Provenance

The runner records source hashes, data hashes, experiment parameters, and the container digest.

The source reference in the runtime lock identifies inspected upstream code. It is not a verified mapping from the container to a source commit.

Primary references:

- [LEAN source](https://github.com/QuantConnect/Lean)
- [LEAN dividend reader](https://github.com/QuantConnect/Lean/blob/a54e9cc6cee9030e865d4f401c03c0e2373ba199/Engine/DataFeeds/Enumerators/DividendEventProvider.cs)
- [LEAN dividend calculation](https://github.com/QuantConnect/Lean/blob/a54e9cc6cee9030e865d4f401c03c0e2373ba199/Common/Data/Market/Dividend.cs)
- [Alpaca brokerage integration](https://github.com/QuantConnect/Lean.Brokerages.Alpaca)

The project is for personal research. The archive does not grant additional rights to third-party market data or software.

## Public copy notes

This is a portfolio copy. The original `data/` snapshot and `runs/` directory are not included because they contain licensed vendor prices. Tests that need daily bars use `fixtures/synthetic-prices/`, generated by `fixtures/make_synthetic_prices.py` on the real session calendar. Paper-broker scripts need your own paper credentials and are not exercised by the test suite.
