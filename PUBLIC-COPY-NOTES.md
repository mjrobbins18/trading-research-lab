# Public copy: what was excluded and why

This folder is a curated, scrubbed copy of a private research workspace.

| Excluded | Why |
|---|---|
| All local secret files (broker paper keys, data-vendor token, SMS provider credentials) | Credentials. Their values were checked against every file here: zero matches. |
| Broker state: controller journal, account locks, observer SQLite databases, paper-account checks | Paper-account identity and balances tied to the author. |
| Alert destinations, email and SMS test reports, scheduled-email logs | Personal email addresses and phone number. |
| Project checkpoint and session logs | Absolute local paths, personal contact details, account balances. |
| Original price snapshots (`data/`, `runs/`, fills and ledgers) | Licensed vendor data (Yahoo, Tiingo), not redistributable. Tests use generated prices instead (`trading-lab/fixtures/make_synthetic_prices.py`). |
| Specialist exam answer keys and LLM run transcripts | Held-out evaluation material, and not needed to read the result. |
| Python virtualenv, caches, LEAN Docker build files | Environment-specific, rebuildable. |

Changes to copied files:

- Credential and lock-file locations now point to `trading-lab/.local/` (git-ignored) instead of the private workspace.
- Tests read fixtures from `trading-lab/fixtures/` instead of sibling workspace folders.
- `evidence/observer-service-report.md`: paper balance and local database path removed.
- A test docstring that named the human reviewer was made generic.
- `evidence/robustness-02/protocol.json` and `results.json` are unchanged, so their recorded SHA-256 hashes still match. They contain relative input-path labels from the original workspace.
