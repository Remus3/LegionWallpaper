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
| R6 | Hygiene docs/ARCHITECTURE.md | DONE | eb1b671 | 2026-07-17 cycle 6 - fixed stale iopaint venv claim (never created; real lane = local py3.11 iopaint per WAKEUP); other TBDs verified accurate; sibling stale ref left at RESTORATION_PLAN.md:249 for future cycle |
| R7 | Hygiene docs/OPERATIONS.md | DONE | 9e48223 | 2026-07-17 cycle 7 - dropped stale TBD tags (gemini_audit.ps1 + weekly_hygiene_run.ps1 exist since f6706d1), fixed registration-preamble claim, rephrased bare-py guard-test condition (suite exists, guard absent); LW-* registry verified empty live |
| R8 | Hygiene docs/RESTORATION_PLAN.md | DONE | 25bafcc | 2026-07-17 cycle 8 - fixed stale iopaint venv refs (sec 2.2 + item 5, sibling of R6; real lane = local py3.11 iopaint 1.6.0, pip-show verified); sec 7 checklist verified on disk (all DONE except ComfyUI) -> rewritten as install-status, original relocated verbatim to history_notes; LEDGER 31 appended; ROADMAP refs unchanged |
| R9 | Archive docs/RESTORATION_PLAN_v1.md | DONE | 973838f | 2026-07-17 cycle 9 - superseded-by-v2 verified (v2 header names v1 as archived predecessor), git mv verbatim to docs/_archive/, repointed the one scope-IN ref (RESTORATION_PLAN.md header); LEDGER/ADR-002/history_notes/FABLE5_PLAYBOOK/loop-config mentions left (scope-OUT immutable) |
