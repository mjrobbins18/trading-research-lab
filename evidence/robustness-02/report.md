# Historical robustness: no-go for an efficacy claim

The frozen ten-month strategy does not show consistent advantage. It passes 36 of 96 pairwise risk-adjusted comparisons under the predeclared descriptive rule. This result supports continued research, not deployment or a claim of alpha.

The run covers 144 scenarios: four calendar periods, three strategies, four cost levels, and three execution delays. Each period starts with $100,000 and uses earlier data only to warm up the fixed signal. There is no parameter search. Compute time was 21.39 seconds.

## Results at five basis points per side, without extra delay

Returns are cumulative, not annual. Drawdown includes the initial $100,000. The mixed benchmark targets 49.5% SPY and 49.5% BIL monthly. The SPY benchmark is the existing 99% SPY implementation with monthly reinvestment of available cash; it is not a frictionless total-return index.

| Period | Trend return | SPY return | Mixed return | Trend drawdown | SPY drawdown | Mixed drawdown |
|---|---:|---:|---:|---:|---:|---:|
| 2008–2009, exploratory | 25.11% | -20.10% | -8.52% | -5.62% | -52.02% | -29.45% |
| 2010–2019, exploratory | 78.70% | 245.41% | 94.02% | -21.78% | -19.13% | -9.53% |
| 2020–2022, exploratory | 17.07% | 23.54% | 14.35% | -21.31% | -33.49% | -17.18% |
| 2024–August 2026, validated payment dates | 43.13% | 66.27% | 36.88% | -9.91% | -18.53% | -9.25% |

Across costs and delays, recent trend returns range from 30.49% to 43.76%. This is material execution sensitivity. The recent base case gives lower drawdown than SPY but lower return and lower zero-risk-free Sharpe: 1.19 versus 1.32. The mixed benchmark has Sharpe 1.60 and slightly smaller drawdown. Therefore reduced SPY drawdown alone does not establish an advantage.

Sharpe here uses daily returns and a zero risk-free rate. It is not an excess-return Sharpe against BIL and must not be compared directly with earlier BIL-excess metrics. The decision rule requires higher Sharpe and no worse drawdown against both benchmarks throughout the stresses. This deliberately stringent descriptive gate failed. The 96 comparisons are dependent; they are not independent trials or a significance test.

## Execution and cost interpretation

The new simulator delays every close-sized order by zero, one, or two additional observed sessions. A sale and its subsequent purchase each wait independently. Buy quantities are never sized with future opening prices. Unaffordable opening buys are rejected, as in the frozen implementation. This preserves its behavior and exposes its weaknesses; it does not fix its order policy.

Higher costs can change integer quantities, cancellation outcomes, and market exposure. Seven of 36 period/strategy/delay groups have at least one nonmonotonic ending-value step as costs increase. For example, exploratory 2010–2019 SPY ends at $345,151 with 10 bps and $358,023 with 25 bps. The latter cancels an opening buy and has lower average SPY exposure. That is a different trading path, not evidence that higher transaction costs help.

A separate fixed-exposure diagnostic applies each cost level to the exact zero-cost fill quantities. Its ending wealth falls monotonically in all 36 groups. This isolates the direct cost effect. It can imply infeasible cash balances, so it is an accounting diagnostic only, not another executable strategy. Both outputs are retained instead of replacing the frozen baseline with a more favorable fill model.

A $300 monthly research subscription is reported separately from transaction costs. The protocol charges every calendar month touched after the decision-start date, including a partial initial month. Thus the recent period includes December 2023 and costs $9,900 across 33 months; the earlier report charged 32 months and $9,600. This convention difference is explicit and does not affect trading results. At $100,000 initial capital, $3,600 a year is 3.6% of initial capital; at $25,000 it is 14.4%, and at $250,000 it is 1.44%. External expenses are subtracted from terminal wealth, without resimulating returns or tax effects.

## Evidence and limitations

The protocol was written before this run and its SHA-256 is `3f1f479d1f85db07a291ad8cc5be2204017846aee33f4cc7467d3b91ba6ab1a3`. `results.json` contains every scenario, comparison, fixed-exposure diagnostic, source hash, engine hash, and runtime. Separate ledgers and fill files make each scenario inspectable.

All 48 zero-delay cases exactly match the frozen reference ledger and fills. Seven focused tests pass, including independently delayed sale and purchase, payable cash unavailable to that day's opening order, future-price perturbation, and cash/position constraints. New delayed paths have not been independently implemented in LEAN. Earlier saved LEAN checks apply to the original payment-date base paths, not all these new scenarios.

The first three periods use the frozen long Yahoo snapshot with ex-date cash accounting and known old distribution issues. Their results are exploratory and cannot establish validated historical performance. The recent sample uses the saved payment-date schedule and audited recent data. All snapshots are retrospective; none proves that every datum was available at the time. Calendar regimes were selected with knowledge of history. The test omits taxes, variable spreads, liquidity, market impact, cash interest, settlement restrictions, and actual broker fills. No agent intervention was evaluated.

## Action

Keep the frozen baseline as a research control. Do not grant it trading authority based on these results. A next strategy experiment would need a new predeclared hypothesis, independently validated accounting and execution, and future observations or a genuinely reserved evaluation set. Testing an LLM specialist is separate from demonstrating investment value.
