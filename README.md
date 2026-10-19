# I built an AI trading system the rigorous way. It lost to the index, and here's why.

*A personal research project, written up honestly. This is not investment advice, and nothing here recommends a strategy, fund, or allocation.*

## The goal

I wanted to find out whether a person with a good engineering background and AI coding agents could build a trading research setup that is actually trustworthy. I did not want a demo that prints a nice equity curve. I wanted a system whose numbers I would bet on.

So the bar was:

- A backtest I could check independently, line by line.
- Market data I had verified against a second source.
- A paper-trading path that could crash at any moment without placing a duplicate order.
- A monitor that would notice when something stopped working.
- A pass/fail rule written down **before** I saw the results.

I built all of that over a few intense days. The strategy then failed the test I had written for it. This write-up explains what I built, what the numbers said, and what I learned. The last part may be the most useful.

## The strategy

I picked the simplest well-documented idea I could find: a monthly trend rule on the S&P 500. It comes from published research on tactical asset allocation, and there is also published research that disputes it.

Once a month, the rule compares the S&P 500 ETF (SPY) total-return value with its 10-month average. If SPY is above the average, it holds SPY. If not, it holds a Treasury-bill ETF (BIL), which is close to cash. That is the whole rule.

I chose it because it is boring. It has one parameter, few trades, and inputs anyone can check. If I could not evaluate *this* rule correctly, I had no business testing anything cleverer.

## The architecture

### 1. A pinned backtest engine, plus an independent check

The backtest runs in [LEAN](https://github.com/QuantConnect/Lean), QuantConnect's open-source engine. It runs inside a Docker image pinned by digest, with no network access and read-only inputs.

Next to LEAN I wrote a separate reference implementation in plain Python (`trading-lab/reference.py`). It recalculates every monthly signal and keeps its own cash and share ledger. It does not import the LEAN strategy code. After each run, the two ledgers are reconciled. A signal, fill, or cash balance that differs fails the run.

Two implementations that agree do not prove the data is correct. But two that disagree catch a whole class of quiet bugs: off-by-one months, dividends counted twice, purchases funded with money the account does not have yet.

### 2. Verified dividend and payment-date data

Dividends are where backtests often lie a little. Most free data credits the dividend on the ex-date. In reality the cash arrives on the payment date, which for SPY is about six weeks later.

I compared the price snapshot against the fund issuer's published distribution history. The audit found three amount conflicts and one issuer record whose payment date came *before* its ex-date (`evidence/data-validation-update.md`). I did not "fix" these by guessing. I recorded them. The recent test period uses a verified payment-date schedule, and cash is credited when it is actually paid.

I also tested an LLM as a "dividend research specialist" that reads distribution notices and extracts structured events. The extraction work had its own frozen protocols and held-out exams. In the end, deterministic parsing plus strict validation did most of the real work. The model was useful for drafting, but I would not let it change a portfolio.

### 3. A crash-safe paper order controller

`trading-lab/order_controller.py` places orders only on a broker's paper-trading endpoint, and the code refuses any other endpoint. Its main rules:

- Every order starts as a durable **intent** written to a journal *before* anything is sent.
- After a crash, the controller reconciles with the broker before it acts again. It never resends an ambiguous order automatically.
- A reused decision ID with different contents stops the system.
- An account lock stops two processes from controlling the same account.
- Fills must agree with the original limit price and with the broker's activity records.
- There is a hard cumulative spending budget and a `STOP` file that halts everything.

The tests cover process death at awkward moments, duplicate broker order IDs, partial fills, and rejected orders. In the end, one real paper round trip of a single share went through the full path and reconciled to the cent.

### 4. A timed observer and an independent watchdog

A worker takes a read-only sample of account and quote health once a minute during market hours. Each slot is claimed in SQLite before the work starts, so a restart never repeats a slot and never hides a missed one. A separate watchdog process reports missing or overdue samples (`evidence/timed-observer-design.md`).

The public copy includes 737 offline tests, which pass with network access blocked.

## The result

The robustness test ran 144 scenarios: four time periods, three strategies (trend rule, buy-and-hold SPY, and a 50/50 SPY/BIL mix), four cost levels, and three execution delays. The protocol was written and hashed before the run. There was no parameter search.

The headline numbers are for the recent period with verified payment dates (January 2024 to August 2026), at 5 basis points of cost per side:

| | Trend rule | SPY buy-and-hold | 50/50 SPY/BIL |
|---|---:|---:|---:|
| Cumulative return | **43.1%** | **66.3%** | 36.9% |
| Max drawdown | -9.9% | -18.5% | -9.3% |
| Sharpe (daily, zero risk-free rate) | 1.19 | 1.32 | **1.60** |

The trend rule had a smaller drawdown than SPY. That is real, and that is what the rule is meant to do. But it gave up a third of SPY's return and still had a lower Sharpe ratio. The plain 50/50 mix beat it on risk-adjusted terms with a similar drawdown. You could get the "smoother ride" without any timing.

Across all periods and stress cases, the rule passed **36 of 96** predeclared comparisons. My rule needed higher Sharpe *and* no worse drawdown against both benchmarks in every case. It came nowhere close. The 2008–2009 crash was the one dramatic win (+25% versus SPY's -20%). That is exactly the story trend-following is sold on, and exactly the period you are most tempted to over-weight once you know the history.

Execution mattered too. Adding one or two sessions of delay moved the recent return between about 30% and 44%. For a monthly rule with few trades, that is a lot of sensitivity to things you do not control.

The full report is in `evidence/robustness-02/report.md`. Every scenario, hash, and comparison is in `results.json`.

### Research costs ate whatever edge was left

The protocol also charged a $300/month data and research budget. That is $3,600 a year:

- 3.6% a year on a $100,000 account.
- 14.4% a year on a $25,000 account.

The rule did not beat the index before costs. After a realistic research budget, the gap gets much wider. The cheapest strategy here, buying an index fund and leaving it alone, is also the hardest one to beat.

## Why copy-trading and YouTube claims mislead

While I worked on this, I kept seeing ads and videos that promised what my careful system could not deliver. Building it made the reasons clear.

**Survivorship.** You see the accounts that won. The many people who ran the same kind of strategy and lost stopped posting. A leaderboard of "top traders" is a filter on luck as much as skill. With enough people flipping coins, someone flips ten heads in a row, and that person makes the video.

**Small-account math.** A fixed cost that seems small is huge on a small account. A $50 monthly subscription, signal service, or data feed is 2.4% a year on $25,000, before any trading losses. Most retail accounts start with a large hurdle that nobody shows on screen.

**Costs nobody shows.** Spreads, slippage, delayed fills, taxes on short-term gains, and the payment-date timing above all appear in real accounts. They rarely appear in screenshots. My own results changed by about 13 percentage points just from realistic execution delay.

**No predeclared test.** A claim without a rule written down first is a story, not evidence. I wrote my rule first and the strategy still failed. Most public claims never take that risk.

**Tiny samples.** A monthly rule makes about 12 decisions a year. A few months of good results tells you almost nothing about skill, in either direction.

## Lessons, including the uncomfortable ones

**The engineering worked. The strategy did not.** These are separate questions, and I kept them separate. The reconciliation, data audits, and crash-safe controller all did their jobs. They are also why I trust the bad result.

**Scope drift is the real risk.** My original question was "Does this rule beat the index after costs?" That question was answered fairly early. I then spent a lot of time on alert delivery, quote reliability, watchdogs, and scheduled sessions. Each step was reasonable. Together they were a production operations project for a strategy that had not earned production. When I stepped back and checked the work against the original goal, I paused the operations track the same day.

The fix I use now: before each new milestone, ask "Does this help answer the original question, or only make the system more impressive?"

**Write the pass/fail rule first.** It is the only thing that stopped me from finding a story in the numbers afterward. If you do one thing from this write-up, do this.

**AI agents speed up building more than knowing.** Coding agents made it possible to build in days what would have taken weeks. They did not make the market any easier to beat. The most useful thing they did was help me test my own assumptions faster.

**A negative result is a result.** "I checked carefully and the simple index fund won" is useful to know, and much cheaper to learn in a paper account.

## What is in this folder

| Path | Contents |
|---|---|
| `trading-lab/` | Strategy, reference ledger, robustness engine, order controller, observer, dividend extraction, and 737 tests |
| `trading-lab/fixtures/` | Offline test inputs, including **synthetic** SPY/BIL prices on the real trading calendar |
| `evidence/robustness-02/` | Predeclared protocol, full results, and the robustness report |
| `evidence/data-validation-update.md` | Issuer distribution audit |
| `evidence/timed-observer-design.md`, `evidence/observer-service-report.md` | Observer and watchdog design and reliability notes |
| `evidence/trading-research-decision.md`, `evidence/first-strategy-specification.md` | Original strategy selection and specification |

Run the tests (Python 3.12, no network needed):

```sh
cd trading-lab
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -q
```

This public copy has no credentials, account data, or broker state. The original price snapshots came from data vendors and are not redistributed here, so the tests use generated prices. Rerunning the LEAN backtests needs your own data and Docker.

---

*Not investment advice. This is a write-up of a personal research project using a paper (simulated) account. Past or simulated performance does not predict future results.*
