# Legion Wallpaper

A wallpaper app for the Legion machine. **The product is not yet defined** - engine,
scope, and architecture are all pending the first product ADR (see `ROADMAP.md`).

What this repo DOES carry today is a complete, battle-tested **operating system**
inherited 1:1 from the Riot Commander project: the rules, gates, tiers, rituals,
and verification discipline that project ran under. The process is live from day
one; the product will be built inside it.

## Where things live

| Surface | Path |
|---|---|
| Operating rules (per-session auto-load) | `CLAUDE.md` |
| Harness config, hooks, agents, commands | `.claude/` |
| Living docs (architecture, operations, agents, charters, ADRs) | `docs/` |
| Roadmap (highest priority at TOP) | `ROADMAP.md` |
| Aspirational backlog | `BACKLOG.md` |
| Session hand-off notes (newest-first) | `WAKEUP_NOTES.md` |
| Per-item completion ledger (append-only, newest-first) | `docs/LEDGER.md` |
| Decisions | `docs/adr/` |
| Runtime health (once the product runs) | `ops/runtime/health.json` |
| Daily logs | `logs/YYYY-MM-DD.log` |

## How this repo operates

- **TDD, RED-first.** Every feature or bugfix starts with a failing test. No
  implementation before the test is observed RED.
- **Tiered verification.** Changes are classified by tier; each tier carries a
  mandatory verification gate (docs-only through full-suite + restart + health
  confirm). Never claim success without running the gate.
- **Subagent-first delegation.** Non-trivial work fans out to worktree subagent
  slices; an independent read-only verifier must CONFIRM before the orchestrator
  merges. The orchestrator is the sole merger.
- **Session rituals.** Wake up by reading `WAKEUP_NOTES.md` + `ROADMAP.md`; wrap
  up by appending a ledger entry to `docs/LEDGER.md`, updating `WAKEUP_NOTES.md`
  (newest-first, archive older sessions to `docs/history_notes.md`), and syncing
  the roadmap.
- **Ledger discipline.** Every completed item gets a numbered, append-only,
  newest-first entry in `docs/LEDGER.md`. Never append ledger entries to
  `CLAUDE.md` (it has a hard size budget).
- **Decisions are ADRs.** Anything with lasting consequences gets a numbered
  file in `docs/adr/` (see `docs/adr/TEMPLATE.md`). ADR-001 records this
  inheritance itself.
- **Style hard rule.** 7-bit ASCII only in authored content - no em/en dashes,
  no smart quotes.

Full rules: `CLAUDE.md`. Agent-framework pattern: `docs/AGENTS.md`. Ops commands:
`docs/OPERATIONS.md`.
