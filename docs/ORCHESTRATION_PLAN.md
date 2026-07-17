# LW Orchestration Plan - directive-chain work rows

Work-row ledger for the headless loop (director refill rows R<N>) and curated
orchestrated sessions. Append-only, newest last. The director reads this to
avoid duplicate work; executors flip Status and stamp the commit sha.

Columns: ID | Title | Status (WIP / DONE / BLOCKED) | Commit | Notes

| ID | Title | Status | Commit | Notes |
|----|-------|--------|--------|-------|
| R1 | Hygiene ROADMAP.md | WIP | - | 2026-07-16 md-hygiene night run, cycle 1 |
