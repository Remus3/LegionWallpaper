# /LW-Continue

> **SUBAGENT-FIRST (standing protocol, operator 2026-06-20).** Always use subagents for substantive work; do not build solo in the main thread.
> 1. **Spec first:** a Plan/design subagent (or the Gemini director) emits the spec/plan BEFORE any code; verify it vs ground truth (grep cited file:line, `ops/runtime/health.json` when it exists, git) - never scaffold on assumptions.
> 2. **New session:** interview the Gemini director (or the operator if Gemini is down) for intent + acceptance criteria, re-probe live state, THEN build.
> 3. **Act via subagents:** worktree-isolated build agents on disjoint files (sole merger) + a read-only `verifier` subagent gate before any merge or "done".
> 4. Trivial one-line cosmetic edits may inline (refines R9). See `CLAUDE.md` "Subagent-First Protocol" + memory `feedback_subagent_first_protocol`.

Resume the Legion Wallpaper program after any interrupt (`**/clear`, crash, restart, new session).

ASCII only. No em-dashes or smart quotes. Caveman ULTRA output.

## CONTRACT

1. Bootstrap from the LW docs: read `docs/LW_PLAN.md` (the living source of truth
   for the program - this file IS the state), with `CLAUDE.md` + `WAKEUP_NOTES.md`
   + `ROADMAP.md` for session context. Git history + `docs/LEDGER.md` carry the
   detail. (Until the product is defined, `docs/LW_PLAN.md` may not exist yet -
   in that case fall back to the top open item in `ROADMAP.md` and say so.)
2. Find the FIRST stage not `DONE`/`CLOSED`/`LIVE` (top-to-bottom, first phase ->
   last phase).
3. Recompute the PROGRESS banner: `% = DONE_stages / TOTAL_stages * 100`. If
   stages were added/removed, fix TOTAL first, then the percent. Print one line:
   `Phase X of <total> - Stage Y of N - ~Z% complete`.
4. Sync the background-task pane: ensure one TaskCreate chip per phase exists;
   mark the active phase `in_progress`, completed phases `completed`.
5. If the next stage is an operator GATE (e.g. a design sign-off) and the
   operator has NOT greenlit: do NOT block. Build the new work behind a flag,
   keep the current behavior live, and continue to the next non-DONE stage.

## EXECUTE

For the selected stage, run the per-stage ritual from `docs/LW_PLAN.md`:
- Swarm where the work is parallelizable (worktree-isolated, disjoint files,
  sole merger, verifier-gate before merge) - up to 100 agents, no session cap.
- TDD (failing test first) for logic; py_compile before any restart.
- Tiered verification (R5-R7): full dual suite only on Tier-2 (schema / engine /
  version-bump changes - product-critical surfaces TBD until the product is
  defined); Tier-0/1 run the scoped check once.
- UI stages: 5-phase fixture audit (STRUCTURE / TYPOGRAPHY / HIT-TARGETS / ASCII /
  HIERARCHY) + Claude_Preview vs live state BEFORE commit (live-state source:
  TBD - product not yet defined).
- Risky product seams DEFAULT-OFF behind flags; version bump + service restart +
  package sync land in the SAME commit; live flips get their own gated-sync doc
  (specifics TBD - product not yet defined).
- commit + push + CI green -> `/done` (append `docs/LEDGER.md` as `LW-<stage>`,
  sync `docs/LW_PLAN.md` + ROADMAP).
- Flip the stage row to `DONE` with the commit sha; re-derive the banner.

## POLICY (active for this program)

- No budget; Gemini-credit fallback = best judgment, never default to operator.
- Frozen-file edits AUTHORIZED. Full computer usage AUTHORIZED (download/install/run).
- If Gemini director is unavailable, the executor self-directs from `docs/LW_PLAN.md`.

## DRAIN

When every stage is DONE/CLOSED/LIVE: run the final phase once (delta research +
design re-synthesis, Gemini-gated to make headless), then print the program
completion banner and stop. The headless loop launches via
`ops/loop/launch_loop.ps1 -Mode live`; abort by dropping `ops/loop/control/STOP`.
