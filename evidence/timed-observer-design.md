# Timed observer and independent watchdog

Implemented and tested offline on October 19, 2026. All 14 focused cases and 706 total tests passed.

No live worker, watchdog, broker observation, order, or notification ran during this work.

## Worker

The worker uses a fixed one-minute grid for one regular session, limited to 6.5 hours.

A durable SQLite slot claim precedes each child invocation. A restart never repeats a claimed slot, even when its result is missing.

A file lock prevents overlapping worker children. Missed slots remain missing; the worker does not replay them later.

The fixed child command runs observer_service.py against the retained account journal. Its transport permits only read-only paper and market-data requests.

Each child has a 45-second timeout. Python terminates and waits for a timed-out child. Arbitrary child stderr is not retained.

The worker stores sanitized results and actual start and completion times. It records no eligible trading decisions.

The observer can update normal reconciliation state. Read-only refers to broker operations; it does not mean local state is immutable.

## Watchdog

The watchdog is a separate CLI role with its own process and database connection. It does not invoke the worker.

It reports missing completions and overdue slots after the 120-second threshold. A later successful observation cannot erase earlier missed slots.

Failed observations require review for the rest of the run. Invalid completion times produce a clock-failure alert.

State transitions create durable alert rows. Repeated identical states do not duplicate alerts. Alert rows remain undelivered.

The watchdog stops at the session boundary plus 120 seconds. It cannot detect a failed host or its own process death.

## Launch controls

Live roles require enabled=true and calendar_verified=true in a fixed run plan. Launches are limited to five minutes before opening through the final reporting deadline.

Changing an existing run plan is rejected. No daemon, launch agent, heartbeat, or other service was installed for these roles.

Plan validation does not authenticate the calendar. A later live preparation must compare session boundaries with the broker calendar before enabling anything.

## Tests

Tests cover one attempt per slot, restart, missing slots, concurrent worker locks, worker faults, clock regression, and unchanged run plans.

A child process exits abruptly with code 73 after claiming its slot. Restart preserves the claim and the watchdog reports missing completion.

A separate test runs a real sleeping subprocess with a short timeout. The timeout becomes a durable failed observation.

The disabled CLI test confirms that no state database is created. Offline tests block socket connections.

## Reporting and remaining integration

The report role uses the fixed-slot scorer. Missing results remain in the denominator. Sampled quote eligibility does not establish continuous coverage.

The next integration step adds pre-open and post-close samples separately from regular-session scoring, plus a bounded launch manifest.

The Gmail connector can send from a scheduled chat, but this local worker cannot call it directly. Alert draining and send recovery remain separate work.

The scheduled Gmail delivery test remains pending. Live session launch and automated alert draining stay disabled until their gates are met.

The real account journal, observer database, and old scheduler markers matched their prior hashes (preservation record not included).

Implementation: trading-lab/timed_observer.py.
Focused tests: trading-lab/test_timed_observer.py.
