# orchestrated-run

> **SUBAGENT-FIRST (standing protocol, operator 2026-06-20).** Always use subagents for substantive work; do not build solo in the main thread.
> 1. **Spec first:** a Plan/design subagent (or the Gemini director) emits the spec/plan BEFORE any code; verify it vs ground truth (grep cited file:line, live `ops/runtime/health.json` + the product live-state endpoint (TBD - product not yet defined), git) - never scaffold on assumptions.
> 2. **New session:** interview the Gemini director (or the operator if Gemini is down) for intent + acceptance criteria, re-probe live state, THEN build.
> 3. **Act via subagents:** worktree-isolated build agents on disjoint files (sole merger) + a read-only `verifier` subagent gate before any merge or "done".
> 4. Trivial one-line cosmetic edits may inline (refines R9). See `CLAUDE.md` "Subagent-First Protocol" + memory `feedback_subagent_first_protocol`.

Bootstrap a gemini-directed, orchestrated parallel multi-agent fanout run that
exhausts a multi-session program of work across a set of themes. This is the
generic initializer for the proven director/executor pattern (see
docs/ORCHESTRATION_PLAN.md). gemini-3-pro-preview is the read-only DIRECTOR +
AUDITOR; ops/loop/loop_controller.py is the brain; the AHK bridge types one
directive per cycle into THIS Claude window and /clears between cycles.

ARGS (free-form, optional): the themes / scope for this run. Default themes:
TBD - the LW product is not yet defined; supply themes explicitly until a
default theme set is recorded here. (The skeleton to fill in later: research,
lift work, core schema + surfacing core data in context, UI/UX updates +
per-page audit + visual validation, wiring/surfacing components marked
"not implemented yet".)

ASCII only. No em-dashes, en-dashes, or smart quotes (repo hard rule).

## Steps

1. INVESTIGATE current state. Launch parallel read-only Explore agents (one per
   theme) to map concrete OPEN candidates from ROADMAP.md / BACKLOG.md /
   WAKEUP_NOTES.md / docs/LEDGER.md and from grepping for unsurfaced / deferred
   components. Each agent returns a terse structured list and explicitly flags
   anything CLOSED / "do not re-litigate" so it is NOT planned.

2. DRAFT the session backlog. Order sessions by value x headless-safety. Each
   session = one cycle / one /clear. EXCLUDE anything that needs live product
   usage or operator validation (flag flips, live producers, live captures -
   the concrete exclusion list is TBD until the product is defined) - list
   those in an EXCLUDED section instead.

3. SEED the living plan: write docs/ORCHESTRATION_PLAN.md with (a) the per-cycle
   contract, (b) a session table (ID | Theme | Scope | Status OPEN|WIP|DONE |
   Commit), (c) the EXCLUDED list, (d) an empty Findings log. If the file exists
   from a prior run, reset statuses or append a new phase as appropriate.

4. WIRE the loop (idempotent - skip what is already correct):
   - ops/loop/director_prompt.md: primary work source = docs/ORCHESTRATION_PLAN.md;
     pick the next OPEN session; instruct the executor to flip WIP -> DONE + sha and
     append new findings; keep all hard rules (fanout, verifier-gate, TDD,
     py_compile, no AskUserQuestion, REGRESS-first, escalation-first, final
     done_sentinel line); UI sessions add the 5-phase audit + Claude_Preview check;
     emit NO_WORK when no session is OPEN.
   - ops/loop/loop_controller.py: build_director_context() injects
     docs/ORCHESTRATION_PLAN.md into the director context head-first, capped
     at PLAN_CTX_CAP bytes (the gemini CLI silently returns empty stdout on
     oversized stdin - do NOT lift the caps); keep the session table at the
     TOP of the plan so the capped head always carries it.
   - ops/loop/config.json: directive_suffix instructs commit + push to origin/main
     + /done ritual; max_cycles >= sessions + margin; dry_run=false.

5. VERIFY pre-launch: py_compile any touched .py; confirm config.json parses;
   confirm docs/ORCHESTRATION_PLAN.md session table is well-formed; full suite green.

6. COMMIT + PUSH the setup (so it survives the first /clear), then LAUNCH:
   powershell ops/loop/launch_loop.ps1 -Mode live
   This /clears THIS window and turns it into the ephemeral executor. The loop runs
   until the director emits NO_WORK (plan drained) or max_cycles. Abort by creating
   ops/loop/control/STOP. Live log: ops/loop/control/controller.log.

## Per-cycle contract (the director enforces; restated for humans)

orchestrator multi-agent fanout (disjoint-file worktree subagents in ONE message,
sole merger, run the verifier subagent on each slice before merge, merge only
green+verified) -> TDD failing test first -> py_compile before any restart -> full
pytest suite green -> UI sessions also pass the 5-phase fixture audit + a
Claude_Preview visual check vs the live product state (endpoint TBD) -> commit
(descriptive) -> push origin/main -> /done ritual (docs/LEDGER.md append, ROADMAP +
ORCHESTRATION_PLAN sync) -> "C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe" ops/loop/done_sentinel.py --tests <N> --regressions <0|1>. Full
authority, no user gating; auto-pick the safest option on any fork.
