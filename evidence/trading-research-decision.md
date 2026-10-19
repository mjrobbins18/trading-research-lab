# Trading research: first strategy and software decision

Research date: October 16, 2026. Scope: personal stock/ETF research, historical simulation, then paper trading.

**Recommendation: use LEAN as the core engine and test a monthly stock-index trend rule first.** Use existing brokerage and data integrations. Add an AI research specialist after the numerical baseline is independently checked. Keep LumiBot as the strongest integrated alternative.

This is a research selection, not a conclusion that the strategy will outperform. This review inspected public papers, documentation, and selected source files. It did not install the engines, run their tests, obtain licensed market data, or reproduce investment returns. Repository branches can change; pin commits before implementation.

## Strategy comparison

| Candidate | Evidence and applicability | Main limitation | Decision |
|---|---|---|---|
| Monthly moving-average timing on a stock index | Faber provides a directly relevant published model and subsequent author update [1]. Simple inputs and few choices make implementation auditable. | Whipsaws, delayed exits, missed recoveries, and disputed statistical superiority. | First experiment: SPY versus a Treasury-bill ETF. |
| Five-asset tactical allocation | The same research examines multiple asset classes [1]. | ETF proxies differ from original indices; commodities and real estate add implementation differences. | Expansion after the single-market implementation passes verification. |
| Global Equities Momentum | Antonacci combines relative and absolute momentum across domestic/international equities and a bond fallback [4]. | More moving parts; the public overview points to a book for complete rules. Author-reported evidence is not independent replication. | Second research candidate; obtain and verify the complete specification first. |
| Sector ETF momentum | QSTrader supplies an inspectable implementation selecting three sectors by six-month returns [5]. | Working example code does not establish independent evidence for its exact parameters or universe. | Useful software example; not selected as an evidence-backed portfolio yet. |

The ordering reflects research tractability and applicability, not a backtested return ranking. Mean reversion and fundamental stock selection remain future disciplines; this review did not establish a specific implementation of either for promotion.

## Evidence register: supporting and opposing findings

**[1] Faber, A Quantitative Approach to Tactical Asset Allocation.** The original study and later update report favorable risk/return characteristics for a simple monthly timing approach. These are author-reported historical findings. The update is post-publication evidence from the same author, not independent replication. [Paper and abstract](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=962461)

**[2] Faber's implementation FAQ.** Confirms month-end evaluation, total-return data, and that the published example differs from the author's actual managed strategies. This is useful for checking interpretation, not additional independent evidence. [Author FAQ](https://mebfaber.com/timing-model/)

**[3] Tactical asset allocation on technical trading rules and data snooping.** This study finds no statistically significant timing outperformance after its data-snooping corrections in the Asian equity markets and portfolio constructions examined. It challenges general claims for timing, but is not a direct replication of our proposed US ETF experiment. Public abstract and conclusion reviewed; full methodology was not independently reproduced. [Journal article](https://www.sciencedirect.com/science/article/pii/S0927538X18300775)

**[4] Antonacci, Global Equities Momentum.** Primary overview of the strategy family. Further diligence requires its complete rules and evidence beyond the author's presentation. [Author overview](https://www.optimalmomentum.com/global-equities-momentum/)

**[5] QSTrader sector momentum example.** Source specifies a 126-business-day lookback, top-three selection, and month-end rebalancing. It is an implementation reference, not an investment study. [Source](https://github.com/mhallsmoore/qstrader/blob/master/examples/momentum_taa.py)

**[6] Hurst, Ooi, and Pedersen, A Century of Evidence on Trend-Following Investing.** Supports studying the broader trend family across markets and long periods. Its diversified long/short implementation is materially different from an unlevered stock ETF/cash rule. Do not transfer its reported performance to our system. [Research](https://www.aqr.com/insights/research/journal-article/a-century-of-evidence-on-trend-following-investing)

**[7] Novy-Marx and Velikov, A Taxonomy of Anomalies and Their Trading Costs.** Shows why turnover and implementation costs belong in strategy selection. The findings do not establish the costs of our orders. [Journal article](https://academic.oup.com/rfs/article-abstract/29/1/104/1844518)

**[8] Bailey and colleagues, The Probability of Backtest Overfitting.** Supports recording all attempted variations and accounting for strategy selection. A final holdout is useful but does not erase prior research selection. [Paper](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253)

**[9] The Memorization Problem: Can We Trust LLMs' Economic Forecasts?** Documents a reason historical language-model evaluations can be contaminated. Restricting retrieved documents does not remove information stored in model parameters. Prospective evaluation is therefore central to our AI experiment. [Research paper](https://arxiv.org/abs/2504.14765)

**Evidence verdict:** sufficient reason to reproduce and challenge monthly trend timing; insufficient reason to call this exact ETF adaptation proven. Independent replication of our exact specification remains outstanding.

## Software comparison

These judgments concern fit for this project. Feature descriptions are documentation claims unless source inspection is explicitly noted. No project received a runtime audit.

| System | Reusable capabilities | Tradeoff | Decision |
|---|---|---|---|
| [LEAN](https://github.com/QuantConnect/Lean) — Apache-2.0 | Event-driven simulation, Python strategies, portfolio/order accounting, configurable models | C# engine and local runtime complexity; data and convenient tooling have separate costs | Select as core engine |
| [LumiBot](https://github.com/Lumiwealth/lumibot) — GPL-3.0 | Python strategies, broker integrations, agent workflows, recorded decisions | Broad feature claims need tests; sample agent prompts are not strategy validation | Strongest fallback if integration work dominates |
| [QSTrader](https://github.com/mhallsmoore/qstrader) — MIT | Modular scheduled equity/ETF backtests | Reviewed material focuses on backtesting; an equivalent paper-broker path was not verified | Optional independent numerical cross-check |
| [TradingAgents](https://github.com/TauricResearch/TradingAgents) — Apache-2.0 | Analyst specialization, debate, research orchestration | Does not establish that its decisions improve our baseline; adds another integration boundary | Later challenger, not initial core |

The license labels are repository metadata, not a review of all dependencies or data redistribution rights.

Why LEAN: the first difficult requirement is faithful accounting and execution simulation. Its documented corporate-action support and existing broker integration fit that priority. Choosing it does not prevent us from later adopting an existing agent runtime.

Why not immediately choose LumiBot: its integration is attractive, but the sampled research/trader strategy places several requirements in agent prompts. The sample alone does not demonstrate independent enforcement of each limit. Verify the runtime before relying on them. Its short demonstration also cannot establish a trading edge. [Inspected sample](https://github.com/Lumiwealth/lumibot/blob/dev/lumibot/example_strategies/ai_researcher_trader.py)

## Concrete implementation findings

1. **LEAN's moving-average example is not our strategy.** The inspected file uses 15/30-day exponential averages and a tolerance. Reuse its engine interfaces, not its strategy definition. [Source](https://github.com/QuantConnect/Lean/blob/master/Algorithm.Python/MovingAverageCrossAlgorithm.py)
2. **An Alpaca adapter already exists.** The project documents a paper environment. No custom brokerage connector is warranted initially. Its README also describes zero backtest slippage and immediate complete market fills; these defaults need explicit replacement or stress testing. [Adapter](https://github.com/QuantConnect/Lean.Brokerages.Alpaca)
3. **Open-source engine does not mean all services are free.** QuantConnect documents paid organization membership for its CLI. Direct engine builds are a separate route. Obtain the actual plan/data quote before committing spending. [CLI requirements](https://www.quantconnect.com/docs/v2/lean-cli/initialization/authentication)
4. **Corporate actions are a separate data dependency.** QuantConnect's security master covers dividends, splits, and symbol changes; it is not the price dataset itself. [Dataset documentation](https://www.quantconnect.com/docs/v2/writing-algorithms/datasets/quantconnect/us-equity-security-master)

## Data recommendation and budget

Prefer the LEAN-compatible US equity dataset plus corporate actions for the first full-history baseline. Documentation describes coverage beginning in 1998; confirm actual SPY/BIL availability and entitlements with a small sample. [Price data](https://www.quantconnect.com/docs/v2/writing-algorithms/datasets/algoseek/us-equities)

Alpaca remains the paper-broker candidate. Its stock-data documentation lists history since 2016, which is too short by itself for our intended financial-crisis test. Its free real-time feed is IEX-only. Do not buy broader real-time data until the selected deployment path shows it is needed. [Alpaca data plans](https://docs.alpaca.markets/us/docs/about-market-data-api)

Planning envelope, not vendor quotes: reserve up to $200/month for platform and data, $100 for model experiments, and $50 for storage/hosting. This $350 allocation is a proposal, not an authorized purchase. If the required historical-data quote exceeds it, compare cloud execution with local licensed data before buying. Start with no paid news feed and no model training infrastructure.

Fixed costs must eventually be compared with intended capital: $350/month is $4,200/year, or 4.2% of a $100,000 account and 16.8% of a $25,000 account, before trading costs and tax. Research spending can be worthwhile without being sustainable production overhead.

## Knowledge collection and specialist qualification

Use the evidence records above as the first compendium entries. For every new claim, store the source, publication date, asset universe, horizon, exact rules, cost assumptions, contrary evidence, implementation link, and replication status. Keep educational material separate from timestamped market observations.

The first specialist's mandate is monthly equity trend research. It must explain whipsaw losses and missed recoveries, distinguish simple from exponential averages and monthly from daily sampling, correctly interpret total returns, and detect impossible signal/fill timing.

Create 30 manually reviewed cases: 10 calculations, 10 evidence critiques, and 10 missing/conflicting-data cases. Proposed qualification requires all critical timing and calculation cases to pass, at least 90% overall, and no invented citations. These are our engineering acceptance criteria, not academically established thresholds. Keep exam cases outside retrieval and tuning data.

## Next implementation milestone

1. Pin the engine and adapter revisions; choose cloud versus local based on verified entitlements and total cost.
2. Fetch a small price/corporate-action sample and audit dividend, holiday, and month-end behavior.
3. Implement the attached strategy specification using LEAN; independently calculate its monthly signals in a small reference calculation.
4. Run historical evaluation and export the daily ledger, all signals, orders, costs, and benchmark results. Document any differences from the source literature.
5. Start a read-only current-context agent that creates timestamped evidence packets. Measure source accuracy, coverage, latency, and cost before allowing it to alter a simulated portfolio.
6. Register one bounded AI intervention, then forward-test unchanged baseline and intervention portfolios together. Compare a deterministic intervention using the same inputs so that the LLM does not get credit merely for access to additional data.

Completion of this research memo selects a starting experiment. It does not qualify the strategy or any agent for capital. A monthly strategy produces few independent decisions: a few months of paper trading can establish operational behavior, but cannot establish durable investment skill.
