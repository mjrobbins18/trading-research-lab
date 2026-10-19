# Observer reliability results

Implemented `trading-lab/observer_service.py` as a bounded, single-cycle observer. The existing order adapter and controller remain unchanged. The wrapper rejects all methods except GET and restricts requests to the paper and market-data hosts. Redirects are disabled.

## Verified behavior

- At most three attempts per read and 60 requests per invocation. Requests are spaced by at least one second within the service. Other clients are outside this limit.
- Timeouts, connection failures, HTTP 429, and selected server errors receive bounded retries. Authentication errors and other responses are not retried. Long or unparsed Retry-After values defer the run. Cooldowns survive restart.
- SQLite commits each observation, state transition, and corresponding alert atomically. Controller locking serializes normal service invocations.
- Continuing failures with the same error type create one alert. Recovery creates another alert. Failed deliveries remain pending, with attempt counts retained.
- Alert delivery uses stable IDs. A destination must deduplicate these IDs because interruption after delivery can cause redelivery. No external alert destination is configured.
- Tests cover process death before commit, interruption after alert delivery, transaction failure, retry exhaustion, restart cooldowns, rejected writes, and preserved account guard state.

Full suite: 492 tests passed. (Suite size at that milestone; the public copy now has more tests.)

## Bounded paper observation

Observed at 2026-10-19 15:27:06 UTC through the new transport:

- Cash and equity: reconciled (paper balance omitted from this public copy).
- Positions, open orders, and unresolved intents: zero.
- Orders submitted: zero. Transport also blocks cancellation.
- SPY quote age: 0.001 seconds; eligible.
- BIL quote age: 466.764 seconds; ineligible.
- Pending alerts: zero.

The observation is saved in a local SQLite state file (not included). This separate service does not append to the older session-coverage audit. The controller can persist normal reconciliation updates; the service does not reset checkpoints, intents, or limits.

## Remaining operational work

The network grant covered this turn only. Persistent scheduler access remains unverified. The existing heartbeat remains paused. Do not describe this manual run as an unattended test.

A bounded scheduled run and an actual notification destination remain necessary before unattended operation. Until then, pending alerts are visible in local state and the command output. Error messages omit request details and credentials; error-type grouping may combine different causes within the same failure episode.

This milestone does not qualify a trading strategy, specialist, or live-money deployment. BIL March 2008 remains excluded from verified payment accounting while awaiting State Street's response.
