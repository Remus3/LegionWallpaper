# ADR-001: Legion Wallpaper inherits the Riot Commander operating system

**Date:** 2026-07-03
**Status:** Accepted

## Context

Legion Wallpaper is a new project on the Legion machine (repo
`C:\LegionWallpaper\`). The product - some kind of wallpaper app - is not yet
defined. The operator's other project on this machine, Riot Commander (RC,
`C:\Riot Commander\`), evolved a proven operating discipline over hundreds of
ledgered items: TDD RED-first, tiered verification gates, subagent-first
delegation with independent verifier confirmation, session rituals
(wakeup/wrapup), an append-only per-item ledger, ADR-recorded decisions, an
ASCII-only style hard rule, and hardened runtime conventions (supervisor +
restart_trigger.txt + health.json + daily logs + atomic writes +
py_compile-before-restart).

The alternatives were (a) start LW with ad-hoc process and let discipline
accrete organically, or (b) clone RC's operating system 1:1 on day zero and
build the product inside it. Option (a) rediscovers known failure modes;
option (b) costs one bootstrap session.

## Decision

LW adopts the RC operating discipline 1:1, process only - RC product content
is explicitly excluded.

**Inherited:** CLAUDE.md operating rules + size budget (under 60KB, ledger
never appended to it); `.claude/` settings, hooks, agents, commands; GEMINI.md
counterpart rules; the tier system + verification gates; TDD RED-first;
subagent-first worktree delegation with orchestrator-sole-merge + read-only
verifier CONFIRM; session rituals (WAKEUP_NOTES.md newest-first with 2-3
sessions kept + docs/history_notes.md archive; docs/LEDGER.md append-only
newest-first per-item ledger; ROADMAP.md highest-priority-at-top; BACKLOG.md
aspirational lanes); docs/adr/ decision records; runtime conventions
(supervisor pattern, restart_trigger.txt, ops/runtime/health.json,
logs/YYYY-MM-DD.log, atomic writes, py_compile-before-restart,
taskkill-not-Stop-Process); the LW-* scheduled-task naming convention +
standard roster documented NOT-YET-REGISTERED; the agent-framework pattern
(docs/AGENTS.md, wiring TBD); the deep-audit charter as a dormant template;
the 7-bit-ASCII-only authored-content rule; memory conventions.

**Excluded:** every RC product artifact - Daemon Slayer engine, champion/
coaching/match data, dashboards and their ports, Riot/LCU integrations,
tailnet topology, Share mirror, Electron overlay, and all RC-specific data
pipelines. Where an inherited rule referenced RC product specifics, the rule
was kept and the specifics were replaced with explicit "TBD - product not yet
defined" placeholders.

## Consequences

**Good:** Hooks are active and rituals are binding from the first session -
the project never passes through an undisciplined phase; every future item is
ledgered, every decision is an ADR, every restart is verified. Known RC
failure modes (bare `py`, Stop-Process hangs, silent pythonw crashes,
non-atomic writes, unverified success claims) are pre-blocked. The eventual
product build starts inside working scaffolding instead of building it
mid-flight.

**Trade-off:** Day-zero process weight with zero product code - some rules
point at TBD placeholders (health.json has no producer, scheduled tasks are
documented but unregistered, the agent framework is a pattern doc only) and
must be kept honest until the product catches up. Porting also risks
RC-specific residue; a leakage sweep is part of the bootstrap verification.

**Watch for:** The frozen-file list starts EMPTY - files earn freeze status as
the product stabilizes; do not cargo-cult RC's frozen list. TBD placeholders
must be resolved (or consciously re-affirmed) by the ADR-002 product scope
decision and each subsequent product ADR - stale TBDs are process debt. Do not
register any LW-* scheduled task or arm the deep-audit charter without an
explicit operator directive.
