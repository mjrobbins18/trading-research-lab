# Distribution audit and next implementation

October 16, 2026. The original backtest and archive remain unchanged.

The independent distribution audit found three amount conflicts and one invalid payment date. Price verification remains open.

## Evidence

We compared the frozen Yahoo snapshot with [State Street's historical distribution workbook](https://www.ssga.com/library-content/products/fund-data/etfs/us/spdr-etf-historical-distributions.xlsx).

The comparison includes dividends and reported capital gains. Dates span the existing simulation through September 30, 2026.

| Check | SPY | BIL |
|---|---:|---:|
| Issuer records, including zero distributions | 79 | 231 |
| Nonzero issuer distributions | 79 | 126 |
| Nonzero snapshot distributions | 79 | 127 |
| Amount differences above $0.000501 per share | 1 | 2 |
| Invalid payment dates | 0 | 1 |
| Valid payment delays, calendar days | 40–47 | 3–11 |

The tolerance permits approximately half a three-decimal rounding step. It is an audit threshold, not an investment-materiality threshold.

## Exceptions

| Symbol | Ex-date | Issuer amount | Snapshot amount | Finding |
|---|---|---:|---:|---|
| SPY | 2021-12-17 | $1.636431 | $1.633000 | Amount conflict |
| BIL | 2022-03-01 | $0.000000 | $0.022000 | Payment existence conflict |
| BIL | 2022-09-01 | $0.138459 | $0.139000 | Difference slightly exceeds tolerance |
| BIL | 2008-03-03 | $0.086739 | $0.087000 | Issuer payable date precedes ex-date |

The last record gives February 11, 2008 as its payable date. We did not infer a replacement date.

Most amount differences fit the rounding tolerance. This does not prove that either source is complete or correct.

The issuer workbook contains explicit zero distributions. Its larger row count does not indicate missing payments in Yahoo.

## Accounting decision

The [issuer defines the payable date](https://www.ssga.com/us/en/individual/resources/documents/etf-dividend-distributions) as the payment date. Ex-date entitlement does not mean cash is available immediately.

The next model will record a dividend receivable on the ex-date. Receivables contribute to portfolio value but cannot fund purchases.

On the verified payable date, the receivable becomes cash. That transfer does not create a second investment return.

Selling shares after the ex-date does not remove the existing receivable. Later splits do not change an already fixed dollar entitlement.

Missing or invalid payment dates will stop a production-grade run. An exploratory sensitivity may use explicit assumed delays, but cannot claim verified accounting.

Signal calculations will retain total-return treatment on the ex-date. Portfolio spending will follow payable dates and broker availability rules.

## Next work, in order

1. Resolve the four exceptions with dated issuer notices or another provider.
2. Obtain independently sourced raw OHLC and corporate actions for both ETFs, including the 2017 BIL split.
3. Add receivables and payment-date cash transfers to both simulation implementations.
4. Test entitlement across sales, splits, year-end, missing dates, and duplicate events.
5. Specify broker-compatible order handling and verify it with intraday or auction data.
6. Repeat the frozen comparisons and explain each change in results.

The order model must distinguish queued, submitted, partially filled, filled, canceled, and rejected orders. Restart recovery must reconcile broker state before resubmission.

Sizing must use information available before submission. Opening prices cannot retrospectively determine submitted share quantities.

The current cancellation policy remains frozen for comparison. Any retry policy will receive a separate version and evaluation across all benchmarks.

## Account and spending decision

No existing data account is available. Public issuer records supported this audit without a subscription.

A new provider must demonstrate coverage before purchase. Required fields include raw OHLC, adjustment conventions, splits, ex-dates, amounts, and payable dates.

The period must include 2008 and BIL's 2007 inception. A long headline history does not guarantee full coverage for each symbol.

[Alpha Vantage documents](https://www.alphavantage.co/documentation/) premium daily history and split/dividend fields. Its described daily endpoint does not establish payable-date coverage.

It is a candidate for a sample comparison, not an approved purchase or complete solution. No account creation or expenditure is required yet.

## Records

`distribution-audit/comparison.csv` preserves each comparison and issuer worksheet row number. `distribution-audit/audit.json` records input hashes, scope, and summary counts.

`trading-lab/audit_distributions.py` reproduces the comparison. It reads the input files without modifying them and requires an empty output directory.

The issuer workbook remains in the local research evidence directory. The existing ZIP is the frozen baseline release and excludes this new audit.

We have not rerun performance or claimed that these findings change the strategy's investment conclusion.
