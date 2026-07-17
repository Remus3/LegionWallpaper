# LW Orchestration Plan - directive-chain work rows

Work-row ledger for the headless loop (director refill rows R<N>) and curated
orchestrated sessions. Append-only, newest last. The director reads this to
avoid duplicate work; executors flip Status and stamp the commit sha.

Columns: ID | Title | Status (WIP / DONE / BLOCKED) | Commit | Notes

| ID | Title | Status | Commit | Notes |
|----|-------|--------|--------|-------|
| R1 | Hygiene ROADMAP.md | DONE | 7afb92f | 2026-07-16 md-hygiene night run, cycle 1 |
| R2 | Hygiene BACKLOG.md | DONE | 8562788 | 2026-07-16 md-hygiene night run, cycle 2 |
| R3 | Hygiene WAKEUP_NOTES.md | DONE | 58b30c4 | 2026-07-16 md-hygiene night run, cycle 3 |
| R4 | Hygiene README.md | DONE | none (CLEAN) | 2026-07-16 cycle 4 - no-change: all 14 cross-refs exist, gitignore claim true, ASCII_OK, no DONE/expired/redundant content |
| R5 | Hygiene GEMINI.md | DONE | none (CLEAN) | 2026-07-16 cycle 5 - no-change: 5/5 cross-refs exist, ASCII_OK, PROVISIONAL status deliberate (paired w/ GEMINI_AUDIT_CONFIG.md, no lift evidence), no DONE/expired/redundant content |
