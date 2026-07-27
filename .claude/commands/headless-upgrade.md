---
description: Headless autonomous-run skill. Folds in /done /clear /continue /compact /memory /audit /test /iterate /new-tech. Full authority, no mid-run user gating (doctrine carried from the operator's prior projects with a 100 percent acceptance track record). Orchestrator pattern - one Claude merges; up to 100 worktree agents in parallel per task. Caveman ULTRA default. PRIMARY north star - TBD, set when the Legion Wallpaper product is defined (section 4b holds the slot). SECONDARY sweep - TBD, set when the product is defined (section 4 holds the slot). Hard-coded with the durable don't-redo set, interrupt protocol, worktree cleanup, and the Desktop synopsis heartbeat.
---

> **SUBAGENT-FIRST (standing protocol, operator 2026-06-20).** Always use subagents for substantive work; do not build solo in the main thread.
> 1. **Spec first:** a Plan/design subagent (or the Gemini director) emits the spec/plan BEFORE any code; verify it vs ground truth (grep cited file:line, live `ops/runtime/health.json` + the product live-state endpoint (TBD - product not yet defined), git) - never scaffold on assumptions.
> 2. **New session:** interview the Gemini director (or the operator if Gemini is down) for intent + acceptance criteria, re-probe live state, THEN build.
> 3. **Act via subagents:** worktree-isolated build agents on disjoint files (sole merger) + a read-only `verifier` subagent gate before any merge or "done".
> 4. Trivial one-line cosmetic edits may inline (refines R9). See `CLAUDE.md` "Subagent-First Protocol" + memory `feedback_subagent_first_protocol`.

The operator has authorized a long unattended autonomous run with:
- Frozen-file edits allowed (the grant is for THIS run only; do NOT carry forward into later sessions).
- LW-wide test coverage at every stage gate.
- Orchestrator multi-agent dispatch: one Claude is the merger; up to 100 worktree agents run in parallel per task, partitioned to disjoint file sets.
- A standing PRIMARY objective: TBD - set when the LW product is defined. Section 4b holds the program slot; every run advances the program once it exists.
- A standing SECONDARY objective: TBD - set when the LW product is defined. Section 4 holds the sweep slot (a likely candidate: runtime cost/latency savings WITHOUT degrading the product).
- A living synopsis maintained atomically on the Legion Desktop.
- Full authority - no mid-run user gating. The operator is away; make the reasonable default, log it, proceed.
- Full computer access + open tool usage: any connected MCP server, CLI, skill, or fleet machine may be used when it serves a legitimate, lawful, non-destructive task. The tool lists in this skill are illustrative, NOT a whitelist - load deferred tools via ToolSearch and reach for whatever fits.
- Interrupt protocol: ANY operator entry during the run = interrupt signal (not a verbatim phrase match). Finish the in-flight slice, then run /done.

This skill is the durable record of how to run that loop cleanly. Run sections in order.

### 1. Pre-flight baseline (do this FIRST, every time)

- Read `CLAUDE.md` Active priorities + the "Settled - do not re-litigate" section + `MEMORY.md` index + `ROADMAP.md` top 80 lines + `BACKLOG.md` headings + recent 15 commits.
- Probe live state: `ops/runtime/health.json` (pid, alive, last_reload_ok). Further live product probes (state endpoints, component health ports): TBD - product not yet defined; add each probe here as the product ships it.
- If a live component's reported version is stale vs the repo's version constant (TBD - define the constant location when the product core exists), bounce that component via its documented restart ritual: `taskkill /F /PID <pid>` then `schtasks /Run /TN LW-<Task>`. NEVER `Stop-Process` (CLAUDE.md hard rule - it hangs the MCP pipe).
- Git hygiene before any new work:
  - `gh run list --limit 6` - baseline must be green; if a recent push is red, fix the red FIRST.
  - `gh pr list` - reconcile/close any open PRs.
  - Delete stale remote branches that are fully merged: a branch is safe to drop when `git log origin/main..origin/<branch>` is empty. `git push origin --delete <branch>`.
  - Clean stale local worktrees left by prior orchestrator runs (they accrete and bloat disk - a prior-project run reached 7.3G across 49 locked worktrees). Verify 0 unmerged first (`git branch --no-merged main`), then `git worktree unlock` + `git worktree remove --force` each, `git worktree prune`, and `git branch -D` the merged worktree/slice branches.
- Write the initial synopsis to `C:/Users/Administrator/Desktop/LW_HEADLESS_SYNOPSIS_<YYYY-MM-DD>.md` (atomic Write). Header carries: HEAD sha, core version constant (TBD until defined), LW test count, CI status, item count, scope, stop rules, phase log table.
- TaskCreate for each phase in the run so progress is visible.
- Init the resumable slice manifest so a crash (API 400 / socket drop / cascade-cancel) never wipes the run: `"C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe" tools/slice_orchestrator.py init --run-id <YYYY-MM-DD-NN> --head <sha>`, then `add` one entry per planned slice. The manifest at `ops/runtime/slice_manifest.json` is the durable checkpoint; on a relaunch `"C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe" tools/slice_orchestrator.py resume` lists only the non-committed slices to redo. The wrapper `tools/headless_run.ps1` automates relaunch-on-crash + this resume handoff. (If this tooling is not yet present in this repo, bootstrapping it is the first slice of the run.)
- If a prior manifest already exists with non-committed slices, this is a RESUME: skip the committed ones, re-verify the rest against ground truth, continue from there - do NOT re-init over it.

### 2. Orchestrator-merge pattern (the core framing)

- ONE Claude is the orchestrator and the only merger. Dispatch up to 100 worktree agents in parallel per task, each owning ONE slice partitioned to a DISJOINT file set so branches merge without conflict.
- Dispatch concurrent agents in a SINGLE message with multiple Agent tool blocks (operator's "parallel" instruction = true concurrency, not sequential).
- Each agent returns its branch (commit-bearing) or a verdict (read-only audit slices return NOW/FUTURE/CLOSED triage, not commits).
- Merge order matters: the foundational slice that others depend on (e.g. a core version-bump slice - TBD until the product core exists) merges FIRST, then dependent slices, then the living-docs sync commit LAST.
- Merge via `git merge --no-ff origin/<branch>` from the repo ROOT.
- CWD HAZARD: the shell CWD persists between Bash calls. Run `cd "C:/LegionWallpaper"` before each `git merge`, or use `git -C "C:/LegionWallpaper" merge ...`. A merge fired from a worktree dir lands on the wrong branch.
- **Verifier gate before any merge (ground truth, not the slice agent's word).** A slice agent's "green: N tests pass" is a CLAIM, not a fact - the pipe replays stale results and agents have cited non-existent test files in past runs. Before merging a slice, dispatch the read-only `verifier` subagent (`Agent` tool, `subagent_type: "verifier"`) with the claim + the cited test command + the cited files. It re-runs the suite fresh, confirms the cited files exist, cross-checks counts, and returns CONFIRM or REFUTE. Merge only on CONFIRM; on REFUTE re-dispatch the slice (mark it `failed` in the manifest) - never merge a refuted slice. The verifier has no Edit/Write tools so it cannot mutate anything; it only reports. **Truth-gate (mechanized layer):** for the FINAL pre-commit reconciliation of a multi-slice round, the verifier (or merger) runs `"C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe" tools/truth_gate.py --claims <claims.json>` - it re-runs the real suite to a file (stale-pipe-proof), re-reads every claimed file and confirms the claimed CONTENT is present (`must_contain` snippets, not just existence), probes CI for HEAD via `gh run list --commit`, and writes `ops/runtime/truth_gate_report.json` atomically. Exit 2 = REFUSE: commit is BLOCKED, `quarantined` lists the slices to re-dispatch with their discrepancy lines as added context. Exit 0 = PROCEED. (Bootstrap the tool if absent - same rule as the slice manifest.)
- **Checkpoint each slice in the manifest as it advances**: `"C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe" tools/slice_orchestrator.py set --id <S> --status in_progress` when dispatched, `--status verified` after the verifier CONFIRMs, `--status committed --commit <sha>` after the merge + push land. A crash after a committed mark means that slice is durable and is skipped on resume.
- Bug-fix or data/pollution slices follow the `root-cause-fix` skill (failing repro first, sibling-case sweep, corrupted-row backfill) so a narrow first fix does not force a second pass.
- After ALL merges land: run the full relevant test gate, restart as needed, then a single surgical living-docs sync commit.

### 3. Phase loop discipline

Each phase/slice is one focused vertical slice. After EVERY phase:

1. **Lint locally before push**: `"C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe" -m py_compile <touched files>`; if any Python file was edited, also `"C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe" -m ruff check .`. F541 (f-string no placeholder) is the most common CI-killer; catch it locally.
2. **Test gate**: run the relevant test subset green BEFORE committing. Full suite: `"C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe" -m pytest tests/ -q`. Component-scoped subsets: TBD - define per component as the product grows (mirror the pattern: one pytest command per major component, plus any snapshot/visual suite).
3. **Restart-aware**: editing server routes / the core app -> `echo restart > restart_trigger.txt` then confirm health.json alive + last_reload_ok; editing a separately-hosted component -> its documented restart ritual (TBD - `taskkill /F /PID <pid>` + `schtasks /Run /TN LW-<Task>`); editing static frontend assets -> use the product's hot-reload mechanism if one exists (TBD) and say so in chat, or restart if none.
4. **Commit + push - HARD PRE-COMMIT GATES (no commit may push until ALL pass)**: (a) frontend slice -> the 3b UI-audit subagent has RUN and every MUST-FIX is resolved in-slice (a page once shipped pre-audit in a prior project; never again); (b) the drift-guard set is green in THIS run's output (ASCII hygiene + any guard the slice touches; further product drift guards TBD); (c) multi-slice rounds -> `"C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe" tools/truth_gate.py --claims <claims.json>` exited 0 (PROCEED) - exit 2 blocks the commit and quarantines slices for re-dispatch. Then: do NOT `git add -A`; explicitly stage only the files you authored. Unstage `_scratch/` and any stray `.playwright-mcp/*.png`. Write the commit message via heredoc. NO Claude co-author trailer - `Co-Authored-By: Claude ...` is banned repo-wide (CLAUDE.md hard rule); `.githooks/commit-msg` strips it if the harness appends one.
5. **CI check after push**: `gh run list --limit 4`. If the just-pushed run goes red, FIX before starting the next phase. Pausing to fix < compounding broken state.
6. **Synopsis sync**: update the Desktop synopsis table row for the phase with status + short-SHA (atomic Write).
7. **TaskUpdate** to mark the phase completed; set the next phase in_progress.

### 3b. Frontend slice: visual proof + UI-audit agent (per the UI-audit ritual)

HARD PRE-COMMIT GATE: any slice that ships a frontend change (styles, scripts, panels, index/root page, a new panel or view - exact paths TBD until the product UI exists) is NOT done - and MUST NOT commit/push - until it has BOTH a visual capture AND a spec-conformance audit. Tests + a successful reload prove the code loads; they do not prove the render is correct or on-spec.

1. **Visual proof (Legion capture)**: after the reload, capture the rendered LW surface on Legion. Canonical capture path: TBD - product not yet defined (define it when the UI exists: a desktop screenshot of the app window, a served frame endpoint, or a mock-fixture-driven render URL; for a page that needs data, drive it with a mock fixture and hard-reload before capture). Attach the capture as the slice's visual proof.
2. **UI-audit agent (keep within spec)**: dispatch an Explore/audit subagent to check the shipped surface against spec. It runs the 5-phase ritual and returns MUST-FIX / SHOULD-FIX / NICE-TO-HAVE:
   - STRUCTURE - panel/grid matches the intended layout
   - TYPOGRAPHY - all declarations on the project scale-spec tokens (spec doc TBD - reserve `docs/UI_SCALE_SPEC.md`); no hardcoded px below the floor token unless a documented operator-exception carrying an inline rationale comment
   - HIT-TARGETS - clickables meet the minimum hit-target token (TBD; the prior-project floor was 42px)
   - ASCII - 0 non-ASCII bytes introduced (no em/en/smart quotes)
   - HIERARCHY - readable at the 1920x1080 baseline without scroll
   Fix every MUST-FIX in the SAME slice before merge; log SHOULD/NICE as FUTURE.
3. **If the Legion capture path is unavailable** (no capture endpoint and no desktop screenshot access): the UI-audit still runs (it is code-side), but the visual capture is OWED. Log it explicitly as a carry-forward in WAKEUP_NOTES + the synopsis ("visual capture owed for page <X>"); do NOT silently skip it and do NOT block the run on it.

### 4. SECONDARY objective sweep (standing slot - TBD)

SECONDARY objective: TBD - set when the LW product is defined. (A likely candidate: find runtime cost/latency savings WITHOUT degrading the product.) Until the objective is set, this section is a slot; once set, sweep its levers each run; ship a fix only when net-positive AND tests green, otherwise record CLEAN no-commit with evidence.

Lever skeleton (drop concrete levers in when the product is defined; generic candidates that will likely carry over):

1. TBD - LLM call efficiency (if LW makes model calls: prompt-cache `cache_control` markers on every `messages.create()` caller, covered or exempt).
2. TBD - hot-route caching (module-level `_CACHE` TTL constants on hot routes, once routes exist).
3. Polling cadences - no sub-500ms network polls; UI-local timers are fine.
4. Log spam - keep every log path under ~1/sec via a suppression list; needles are bare prefixes (a trailing space silently fails the substring match).
5. TBD - model tier (cheapest model that meets the bar for any live-call surface; escalate only where a charter requires it).
6. Scheduled-task catalog - LW-* tasks only; no orphans. (Document tasks; do not register new ones without operator intent.)
7. TBD - paired-artifact drift parity (define once the product has generated/mirrored artifacts that can drift).

Never trade product fidelity for cost. A degrade is not a saving.

### 4b. PRIMARY objective program (north star slot - TBD)

PRIMARY objective: TBD - set when the LW product is defined. This section preserves the program skeleton so the objective drops in later; every run advances the program once it exists.

Skeleton to fill in when the product is defined:
- A one-line north star (the shape from the operator's prior projects: drive a costly live dependency to ZERO by migrating to precomputed deterministic paths).
- The explicit list of call sites / surfaces the program retires or lifts (file paths, enumerated).
- Any charter-exempt surfaces that are out of scope for the program.

Each run advances the program via PARALLEL orchestrator lanes (dispatch them concurrently, disjoint file sets, per section 2):

**Lane A - TBD.** (Slot: the primary precompute/derivation lane.)

**Lane B - TBD.** (Slot: the data/metric-backed generation lane.)

**Lane C - TBD.** (Slot: the deterministic user-facing surface lane.)

**Lane D - TBD.** (Slot: the shell/UI lift + agent lane. Frontend slices in this lane follow the section 3b visual-proof + UI-audit ritual.)

Standing process rules that survive regardless of what the objective becomes:
- Retiring or flipping a surface off its current behavior is only "done" when the replacement path produces output the operator would accept in real usage - validate against real or replayed usage before flipping. A replacement that is WRONG is worse than the status quo; do not flip blind. Until a surface's replacement path is validated, leave its current path in place.
- Foundation/schema lifts that unblock these lanes run as their own parallel slices under section 8.

### 5. Frozen-file edits under this run's grant

- The grant is operator-authorized for the CURRENT run only. Do NOT extend into future sessions. The grant does NOT carry forward.
- When you DO touch a frozen file, route AROUND when possible. Adding a single import line in the entrypoint to wire a non-frozen module is fine; rewriting a frozen core loop is a separate dedicated session.
- Every frozen-file commit body explicitly notes "frozen-file edit under operator's headless-upgrade grant".
- The frozen list is authoritative at the TOP of `CLAUDE.md` (TBD - populate as the product stabilizes; entrypoints, supervisors, and bridge/loop infrastructure are the expected initial members).

### 6. ASCII hygiene (hard rule)

- No em-dash, no en-dash, no smart quotes anywhere in authored text (.py / .md / .ps1 / .css / .js / commit messages / chat output).
- Use ` - ` (spaced hyphen) for a clause break, `-` otherwise.
- Any operator-approved non-ASCII rendering sentinel must be documented in CLAUDE.md before it is exempt; nothing is exempt by default.
- Pytest guard catches Python; check `.md`/`.css`/`.js` by `grep -P "[\xE2\x80\x93\xE2\x80\x94\xE2\x80\x98\xE2\x80\x99\xE2\x80\x9C\xE2\x80\x9D]"` before commit when in doubt.

### 7. Multi-agent dispatch rules

- Cap: up to 100 concurrent worktree agents per task. Partition to disjoint file sets.
- Each agent prompt MUST carry the don't-redo set so it does not re-research closed topics. Source of truth: the `CLAUDE.md` "Settled - do not re-litigate" section + `docs/history_notes.md`. (The concrete closed-topic list is TBD - populate it as LW topics close; never dispatch a research agent with an empty don't-redo list once entries exist.)
- Agents return TRIAGED NOW/FUTURE/CLOSED with reasons. Synthesize NOW items into BACKLOG.md + open issues; do NOT auto-implement everything.
- Verify agent premises against live data before acting - research agents have shipped wrong premises in past runs that a single live probe would have caught.
- Subagent-generated files (esp. tests) MUST pass `ruff` before the agent reports done (CLAUDE.md subagent-quality rule; subagent test files have broken CI before).

### 7b. Deep-dive competitor research (depth bar - NOT superficial)

When a task is "see what can be lifted from competitor X" (or a competitor-lift research lane; the competitor set is TBD - product not yet defined), the bar is a TRUE teardown, not a homepage skim. A finding like "they have feature Y" is a FAILURE - it must name the actual mechanic, the math/data behind it, and the LW integration point. Prefer DEPTH over breadth: one heavyweight agent per target doing a full teardown, not many shallow ones.

**Tooling allowance** - research agents may use the full MCP/scraping toolbelt freely. This tool spend is NOT subject to the section 4 budget (that budget governs LW RUNTIME spend, not one-off research). Load any deferred MCP tool via ToolSearch first (`select:<name>` or keyword search) - they are not pre-loaded. Use the agentType `general-purpose` (tools: *) so the agent can reach these and Write the report:
- Chrome DevTools MCP (`mcp__plugin_chrome-devtools-mcp_chrome-devtools__*`) or Claude-in-Chrome - render the LIVE page, `evaluate_script` against the DOM, and capture the network/XHR (`list_network_requests` + `get_network_request`) to see the ACTUAL API shapes + payloads powering the UX.
- Firecrawl (`firecrawl-scrape` / `firecrawl-crawl` / `firecrawl-agent`) - bulk structured extraction + crawl doc/feature sections.
- nimble `competitor-intel` / `competitor-positioning` / `company-deep-dive` - purpose-built teardown with before/after tracking.
- Playwright MCP - interaction-driven pages (click through tiers, trigger a calc, capture the result).
- Windows MCP / computer-use - a competitor DESKTOP app; screenshot + inspect what the live tool actually renders.
- WebFetch / WebSearch / the `deep-research` skill - sourcing + cross-reference.
- Isolated execution: when a target needs something RUN or PARSED (a competitor .exe, a downloaded data file, a headless render, a parser script), do it in an isolated Legion workspace - a temp dir or a disposable git worktree, kept off LW's runtime paths - via Windows MCP / computer-use. Keep it away from `data/` and the live LW process so the runtime env stays uncontaminated. Clean up any artifacts you create when done.
- The toolbelt above is ILLUSTRATIVE, not a whitelist. Reach for ANY connected tool / MCP server / CLI / skill that serves a legitimate parse-or-render task, listed here or not. The only bounds: lawful + authorized target (public sites/tools, or the operator's own machines) + non-destructive + the standing secrets and frozen-file rules. No credential theft, no malware, no destructive ops.

**Depth checklist - every finding must answer ALL six:**
1. WHAT - the specific mechanic / UX / math (the algorithm, the interaction, the data shape, the network call - not "feature Y exists").
2. HOW - it works under the hood (captured XHR payload, the formula, the state machine, the render).
3. HAVE - does LW already do this? grep LW + cite the file (some may already be covered).
4. WHERE - the concrete LW integration point: specific file/module + layer (core logic vs route vs UI).
5. EFFORT + RISK - new data / new external or model dependency / schema lift, or just a presentation layer over existing core logic.
6. LIFT verdict - HIGH / MED / LOW, with the reason.

**Lift appropriately (legal):** reimplement the mechanic / UX / math in LW's own code. Do NOT vendor competitor code without a license (unlicensed sources are reference-only - never copy). The output is a re-implementation plan, not pasted code.

**Rules:** each agent carries the don't-redo set (CLAUDE.md "Settled" + the closed-negatives recorded in memory/history). Verify every scraped claim against the live source before recording - marketing copy is not implementation. Output a dated `docs/COMPETITOR_LIFT_<YYYY-MM-DD>.md` with per-target HIGH/MED/LOW + mechanic + LW integration point + effort. Then ACT on the verdicts under the run's full-authority grant: a HIGH-lift that is low-risk (a presentation layer over existing core logic, no new external/model dependency, no schema lift, fully testable) gets implemented IN-RUN as its own slice with tests + the section 3b visual proof if it touches UI. A HIGH-lift that is high-effort or carries a new dependency / schema lift / product-direction call becomes a BACKLOG entry + open issue for the operator to gate - log it as FUTURE, do not build it blind. MED/LOW always defer to BACKLOG. The docs artifact records every verdict either way.

### 8. Core audit iteration loop

- Core/engine schema lifts run as PARALLEL orchestrator slices (section 2), not only the serial audit loop - dispatch independent lifts concurrently on disjoint core modules. Prioritize lifts that unblock the section 4b lanes (once defined).
- Stop rule: 11 consecutive no-change iterations.
- Source of truth for domain data: TBD - product not yet defined. When set, pick ONE canonical upstream and never scrape unofficial mirrors or aggregators.
- Each iteration touches ONE lane (one coherent slice of the core math/logic) and either ships a core version bump + tests, or records "no-change" with explicit reasoning.
- After each version bump, sync the version pins across the affected tests + bounce the owning process via its documented restart ritual (TBD).
- When ADDING tests, prefer parametrized property-style (parameterize over input-tuple cross products) over single-pin checks. Mathematical invariants > exact values.

### 9. Interrupt protocol (no verbatim phrase match)

- ANY operator message that arrives during the run is an interrupt signal. It does NOT have to say "wrap up" or any specific phrase. Treat any entry as: STOP starting new phases, FINISH the in-flight slice (never abandon a half-merged state), then run `/done`.
- If the operator's message is plainly a question (not a stop), answer it in caveman ULTRA and resume. If intent is ambiguous between question and stop, treat it as stop-and-wrap (safer; the next session can resume from WAKEUP_NOTES).
- NO blocking AskUserQuestion mid-run - the operator is away; a forced question hangs the run. Pick the reasonable default, log the choice in the synopsis + WAKEUP_NOTES, and proceed. A scope decision that genuinely needs the operator becomes a FUTURE item, not a block.
- If a message lands mid-critical-path (mid-restart, mid-merge), finish the critical path FIRST, then handle the interrupt.

### 10. Headless cadence health

- Living synopsis on Desktop: update every phase complete (atomic Write); never delete the file mid-run; final state survives as the durable record.
- Living docs (CLAUDE.md item N+1, ROADMAP.md, BACKLOG.md, WAKEUP_NOTES.md, core product doc TBD): synced at run END as a single surgical commit, NOT per phase.
- WAKEUP_NOTES prune: `"C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe" "C:/LegionWallpaper/scripts/wakeup_prune.py" --keep 3` (no-op when already <=3 sessions; bootstrap the script if absent). Older sessions archive to `docs/history_notes.md`.
- Worktree cleanup at run END: remove merged worktrees + `git worktree prune` + `git branch -D` merged slice branches, so disk stays lean for the next run (the orchestrator pattern is what bloats it).
- 10h+ extension: if still running past 10 hours, transition to a full LW refactor audit (multi-agent codebase split). Frozen-file edits still allowed; tests required.
- Token budget: caveman ULTRA is the default for fleet-wide overnight (per the SessionStart hook). Compress chat output ~90 percent; keep code tokens / paths / numbers / error strings byte-exact.

### 11. The /done ritual at run end

Run `/done` (existing skill). It handles the local check gate, auto-commit + push, GitHub CI verification, background-task stop, bridge-loop liveness, WAKEUP_NOTES update + prune, living-doc sync, incoming-lessons drain, session-size check, and the final banner. DO NOT skip; the WAKEUP_NOTES update is what unblocks the next session's bootstrap.

### 12. Anti-patterns (caught from past runs - do NOT repeat)

- Do NOT `git add -A` without unstaging `_scratch/` first.
- Do NOT skip the `ruff check` local lint - F541 has killed CI.
- Do NOT amend commits; always create new commits (CLAUDE.md hard rule).
- Do NOT `Stop-Process` - it hangs the MCP pipe; use `taskkill /F /PID <pid>` (CLAUDE.md hard rule).
- Do NOT leave locked worktrees uncleaned at run end; they bloat disk run over run.
- Do NOT emit a Claude co-author trailer at all (CLAUDE.md hard rule); the commit-msg hook strips one if the harness adds it.
- Do NOT trust an agent's premise without verifying against live data.
- Do NOT dispatch a research agent without an explicit don't-redo list.
- Do NOT skip stating the reload/restart mechanism in chat when shipping frontend changes.
- Do NOT add a feature flag or backwards-compat shim for changes that should just BE the new behavior (CLAUDE.md: no feature flags).
- Do NOT add comments that say WHAT the code does. Comments are for WHY only.
- Do NOT block on AskUserQuestion mid-run; the operator is away.
- Do NOT mark a frontend slice done without a visual capture + UI-audit (or an explicit OWED carry-forward when the Legion capture path is unavailable).

### 13. Final banner

When an interrupt fires (or the work queue is empty), emit one tight banner:

```
HEADLESS UPGRADE WRAP
  HEAD: <short-sha> (<N> commits this run)
  VERSION: <old> -> <new> | n/a (core version constant TBD)
  LW: <N> tests
  CI: <N>/<N> green (<N> red)
  objectives: PRIMARY <TBD | progress note> / SECONDARY <N levers swept, M shipped | all CLEAN | TBD>
  ui proof: <N pages captured + audited, M owed | n/a>
  worktrees: <cleaned N | none>
  Synopsis: C:/Users/Administrator/Desktop/LW_HEADLESS_SYNOPSIS_<date>.md
  Ready for /done.
```

Then call `/done`.
