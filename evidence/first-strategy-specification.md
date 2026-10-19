# First experiment: monthly stock-index trend

Version 0.1 — October 16, 2026. Status: specified, not implemented or backtested.

**Purpose:** test whether a transparent trend filter improves the risk/return tradeoff relative to simpler exposure choices. This is a Faber-inspired ETF adaptation, not an exact replication of the published index study. [Original research](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=962461)

## Rules to freeze before examining results

- Instruments: SPY for US large-cap equity exposure and BIL for short Treasury-bill exposure. These are experimental instruments, not a recommended allocation of the user's savings. [BIL issuer information](https://www.ssga.com/us/en/intermediary/etfs/state-street-spdr-bloomberg-1-3-month-t-bill-etf-bil)
- Observe SPY at the last completed trading session of each calendar month, in New York time.
- Build a total-return index from prices and corporate actions available by that date. Compare its latest month-end value with the arithmetic mean of the last ten month-end values, including the current one.
- Above the average: target 99% SPY. Otherwise, including equality: target 99% BIL. Keep the remainder as a transaction buffer. No short positions or borrowing.
- Do not produce a signal until ten complete monthly observations exist. Missing required inputs produce an error and preserve existing holdings; do not invent a price or silently infer a trading decision.
- Submit the rebalance for the next regular trading session's opening auction, after the signal is known. Do not fill at the close that generated the signal. Simulate opening gaps and costs.
- Sell the outgoing position before purchasing the incoming position; use only available buying power and model any settlement-related delay. For the research harness, a margin-capable account may provide settlement mechanics, but enforce gross exposure at or below 100% and no cash borrowing. Confirm broker behavior before paper deployment.
- Use whole shares, rounded down; retain residual cash. Account for distributions exactly once. A total-return signal series and a raw-price portfolio ledger must not both credit the same income.
- Rebalance monthly to target; no discretionary stops, intramonth news overrides, parameter optimization, or leverage in this baseline.

The 99% allocation, equality rule, BIL substitution, and next-session execution are our explicit implementation choices. They can produce different results from the paper.

## Historical evaluation

Use actual ETF history beginning January 2008, subject to data validation, with prior SPY observations for warm-up. BIL began in May 2007; do not manufacture earlier ETF prices. Earlier index-based studies may be reported separately as contextual evidence.

Development/verification interval: 2008–2015. Later evaluation: 2016–2020 and 2021–2025, reported separately. These are predeclared historical intervals, not perfectly untouched evidence: the strategy was chosen with knowledge of public history. Freeze before computing performance. Report 2026 through the last completed month separately; do not mix incomplete monthly periods into headline comparisons. Genuine prospective evidence starts after the final strategy and agent versions are frozen.

Benchmarks: 99% SPY buy-and-hold with the same starting buffer; 99% BIL buy-and-hold; and a fixed 50/50 SPY/BIL allocation within the same 99% invested budget, rebalanced monthly. All use consistent dates, distributions, fees, and execution assumptions.

Base execution sensitivity: 5 basis points per traded notional per side as a combined spread/slippage allowance; stress at 10 and 25. These are assumed scenarios, not measured cost estimates. Include applicable explicit fees separately. Later replace or corroborate assumptions with observed quotes and paper execution. ETF expenses are already reflected in market returns and must not be deducted twice. Report before personal taxes, with turnover and realized gains available for later tax analysis.

Primary question: does timing improve the risk/return tradeoff after costs? Report CAGR, volatility, maximum drawdown, time under water, excess-return Sharpe using a consistent cash reference, turnover, exposure, and results by period. Lower drawdown alone is insufficient: holding less equity can mechanically reduce it. Compare with the fixed mixed portfolio, too.

Use dependence-aware uncertainty estimates where feasible. Report 8- and 12-month averages only as predeclared sensitivity checks; do not replace the 10-month rule with whichever performs best. Count all variants in the experiment register. Do not declare success from a single favorable period or crisis.

## Verification required before trusting results

- Monthly signals match an independent reference calculation.
- Every fill occurs strictly after its information cutoff.
- Dividend and split examples reconcile to the portfolio ledger.
- Month-end holidays and daylight-saving changes do not shift the observation incorrectly.
- Missing data, order rejection, partial fills, and restart recovery produce explicit states without duplicate orders.
- No leveraged exposure, negative cash borrowing, or live-broker credentials appear in the research runner.

## AI experiment after baseline verification

First run the specialist in observation-only mode. Save source publication and retrieval timestamps, evidence, recommendations, model/prompt version, and cost. Do not call historical text analysis unbiased merely because retrieval is date-filtered.

Before enabling any simulated intervention, specify its exact allowed action, decision frequency, fallback, and primary metric. Keep an unchanged baseline and a deterministic comparison using the same extra data. Failed or late agent runs revert to baseline behavior. The intervention remains an unproven research hypothesis.

No calendar-based live promotion: completing 30 or 90 days of paper operation establishes neither profitability nor adequate statistical power for monthly decisions.
