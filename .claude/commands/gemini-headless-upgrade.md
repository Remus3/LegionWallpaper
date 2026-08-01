---
description: Gemini-directed autonomous headless-upgrade loop, merged with the full 13-section orchestrator framework. gemini-3-pro-preview (read-only) is DIRECTOR + AUDITOR; a Python controller (ops/loop/loop_controller.py) is the brain; an AutoHotkey v2 bridge types into THIS Claude window. Invoking this turns the CURRENT session into the ephemeral executor - AHK /clears it and feeds one gemini-authored directive per cycle. Continuity lives on disk (git history + docs/LEDGER.md + the directive chain). Each executor cycle natively runs the orchestrator-merge pattern (1 Claude merger + up to 100 parallel worktree agents on disjoint file sets + read-only verifier gate before merge), the 3b UI-audit ritual, the section 4/4b objective programs (PRIMARY + SECONDARY - TBD until the LW product is defined), the section 5/6 frozen-file grant + ASCII hygiene, section 7/7b multi-agent + deep-dive competitor research (6-point depth checklist), sections 8-13 core audit loop / interrupt / cadence / anti-patterns / done / banner, the paired-artifact commit ritual (TBD), and the two-way Gemini escalation channel. Ceiling + model + cycle cap in ops/loop/config.json.
---

> **SUBAGENT-FIRST (standing protocol, operator 2026-06-20).** Always use subagents for substantive work; do not build solo in the main thread.
> 1. **Spec first:** a Plan/design subagent (or the Gemini director) emits the spec/plan BEFORE any code; verify it vs ground truth (grep cited file:line, live `ops/runtime/health.json` + the product live-state endpoint (TBD - product not yet defined), git) - never scaffold on assumptions.
> 2. **New session:** interview the Gemini director (or the operator if Gemini is down) for intent + acceptance criteria, re-probe live state, THEN build.
> 3. **Act via subagents:** worktree-isolated build agents on disjoint files (sole merger) + a read-only `verifier` subagent gate before any merge or "done".
> 4. Trivial one-line cosmetic edits may inline (refines R9). See `CLAUDE.md` "Subagent-First Protocol" + memory `feedback_subagent_first_protocol`.

Invoking this command hands THIS Claude session over to the autonomous loop. After launch,
AHK will `/clear` this session and type one gemini-authored directive per cycle into it; the
loop's brains are the external Gemini + Python + AHK processes, not a Claude session. The
executor (each cleared cycle) reads `ops/loop/control/directive.md` and runs it under the full
framework in PART B + C below. Run PART A now, then STOP and end the turn.

================================================================================
PART A - LAUNCH SEQUENCE (this session, ONE time)
================================================================================

### A1. Pre-flight (abort if any check fails)
Run this and confirm all four are OK:
```powershell
"GEMINI_API_KEY=$([bool][Environment]::GetEnvironmentVariable('GEMINI_API_KEY','User'))"
"gemini=$([bool](Get-Command gemini -ErrorAction SilentlyContinue))"
"ahk=$(Test-Path 'C:\Program Files\AutoHotkey\v2\AutoHotkey64.exe')"
$w=Get-Process claude -ErrorAction SilentlyContinue | Where-Object {$_.MainWindowTitle}
"claude_windows=$(@($w).Count) (expect exactly 1 - this session)"
```
If `claude_windows` is not 1, tell the operator to close extra Claude windows first (AHK
targets the single window). If any check is false, report it and stop - do NOT launch. A live
gemini liveness signal already exists when `ops/loop/control/controller.log` shows a recent
`gemini=$<n>/<ceiling>` line (the loop made paid gemini calls successfully); any failing
LW-GeminiAudit scheduled task is a SEPARATE nightly task, not the loop's interactive path.

### A2. Launch the loop (detached)
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\LegionWallpaper\ops\loop\launch_loop.ps1" -Mode live
```
This auto-detects the Claude window PID, writes `ops/loop/control/{target_pid.txt,ahk_mode.txt=live}`,
starts the AHK bridge + the controller (config.json), and pre-cleans stale sentinels (incl. a
stale STOP from a prior `max_cycles reached`). (If the loop infrastructure is not yet ported
to this repo, report that and stop - do NOT improvise a launcher.)

### A3. Confirm + yield
- Read `ops/loop/control/controller.log` tail; confirm a fresh `loop start dry_run=False` line.
- Print a one-line banner: ceiling, max_cycles, and the abort path (drop `ops/loop/control/STOP`).
- Then STOP. Take no further actions. Within ~45s the controller finishes the first gemini
  director call, AHK types `/clear` + the directive into THIS window, and the loop runs.

================================================================================
PART B - PER-CYCLE EXECUTOR FRAMEWORK (every cleared directive runs ALL of this)
================================================================================
Canonical long-form: `.claude/commands/headless-upgrade.md`. Run sections in order. Full
authority, no mid-run user gating; the operator is away - make the reasonable default, log it,
proceed. Caveman ULTRA output default (compress ~90 percent; code/paths/numbers byte-exact).

### 1. Pre-flight baseline (FIRST, every cycle)
- Read CLAUDE.md Active priorities + the "Settled - do not re-litigate" section + MEMORY.md
  index + ROADMAP.md top 80 + BACKLOG.md headings + recent 15 commits.
- Probe live state: `ops/runtime/health.json`; further live product probes TBD - product not
  yet defined (add each here as the product ships it).
- A live component stale vs the repo's version constant (TBD) -> bounce it via its documented
  restart ritual: `taskkill /F /PID <pid>` then `schtasks /Run /TN LW-<Task>` (NEVER Stop-Process).
- Git hygiene: `gh run list --limit 6` green baseline (fix red FIRST); `gh pr list` reconcile;
  delete stale merged remote branches; clean stale local worktrees (verify 0 unmerged first,
  unlock + remove --force + prune + branch -D).
- Write/refresh `C:/Users/Administrator/Desktop/LW_HEADLESS_SYNOPSIS_<YYYY-MM-DD>.md` (atomic).
- TaskCreate per phase. Init/resume the slice manifest:
  `"C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe" tools/slice_orchestrator.py init --run-id <YYYY-MM-DD-NN> --head <sha>` then `add` per slice;
  a prior manifest with non-committed slices = RESUME (skip committed, re-verify rest).

### 2. Orchestrator-merge pattern (core framing)
- ONE Claude is the orchestrator + the ONLY merger. Dispatch up to 100 worktree agents in
  parallel per task, each ONE slice on a DISJOINT file set. Dispatch concurrent agents in a
  SINGLE message with multiple Agent blocks (true concurrency).
- Merge order: the foundational / version-bump slice (TBD) FIRST, then dependents, living-docs
  sync LAST. Merge via `git -C "C:/LegionWallpaper" merge --no-ff origin/<branch>` (CWD hazard:
  the shell CWD persists between Bash calls; a merge fired from a worktree dir lands wrong).
- VERIFIER GATE before any merge (ground truth, not the slice agent's word): dispatch the
  read-only `verifier` subagent with the claim + cited test cmd + cited files. Merge only on
  CONFIRM; on REFUTE mark `failed` + re-dispatch - never merge a refuted slice.
- TRUTH-GATE (mechanized): final pre-commit reconciliation of a multi-slice
  round = `"C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe" tools/truth_gate.py --claims <claims.json>` (fresh suite to file, content-level
  claimed-edit re-read via must_contain, gh CI probe, atomic report to
  ops/runtime/truth_gate_report.json). Exit 2 = commit BLOCKED + `quarantined` slices re-dispatch.
- `claim --agent <id> --files <files> --slice <S>` BEFORE dispatch, then checkpoint
  (`set --status in_progress --agent <id>` -> verified -> committed --commit <sha>).
  The in_progress set is REFUSED unless that agent holds every file the slice declares,
  and a slice added without `--files` cannot start - so `add` with the real file list.
  `release --agent <id>` on the way out.
- Bug/data slices follow `root-cause-fix` (failing repro first, sibling sweep, backfill).
- After ALL merges: full relevant test gate, restart as needed, ONE surgical living-docs commit.

### 3. Phase loop discipline (after EVERY phase)
1. Lint: `"C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe" -m py_compile <touched>`; any .py edited -> `"C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe" -m ruff check .` (F541 is the common CI-killer).
2. Test gate green BEFORE commit: full suite
   `"C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe" -m pytest tests/ -q`; component-scoped subsets TBD as the product grows.
3. Restart-aware: core app/routes -> `echo restart > restart_trigger.txt` + confirm health alive/last_reload_ok;
   separately-hosted components -> their documented restart rituals (TBD); static frontend assets -> the
   product's hot-reload mechanism (TBD), say so in chat, or restart if none.
4. Commit + push - HARD PRE-COMMIT GATES (no push until ALL pass): (a) frontend slice -> 3b
   UI-audit RUN + every MUST-FIX resolved in-slice; (b) drift-guard set green THIS run
   (ASCII hygiene + touched guards; further product guards TBD); (c) multi-slice round ->
   truth_gate exit 0. Then: NO `git add -A`; stage only authored files; unstage `_scratch/` + stray
   `.playwright-mcp/*.png`; heredoc message; NO Claude co-author trailer (banned repo-wide by
   CLAUDE.md; the commit-msg hook strips one if the harness adds it).
5. CI after push: `gh run list --limit 4`; red -> FIX before next phase.
6. Synopsis row update (atomic). 7. TaskUpdate phase completed; next in_progress.

### 3b. Frontend slice: visual proof + UI-audit ritual (HARD PRE-COMMIT GATE)
Any slice shipping a frontend change (styles, scripts, panels, root page, new panel/view - exact
paths TBD until the product UI exists) is NOT done - and MUST NOT commit/push - until it has BOTH
a visual capture AND a spec-conformance audit.
1. Visual proof: capture the rendered LW surface on Legion. Canonical capture path: TBD - product
   not yet defined (desktop screenshot of the app window, a served frame endpoint, or a
   mock-fixture-driven render URL; define it when the UI exists and record it HERE).
2. UI-audit agent (5-phase ritual; returns MUST-FIX / SHOULD-FIX / NICE-TO-HAVE):
   - STRUCTURE - panel/grid matches intended layout.
   - TYPOGRAPHY - all declarations on the project scale-spec tokens (spec doc TBD - reserve
     `docs/UI_SCALE_SPEC.md`); no hardcoded px below the floor token unless a documented
     operator-exception with inline rationale.
   - HIT-TARGETS - clickables meet the minimum hit-target token (TBD; prior-project floor 42px).
   - ASCII - 0 non-ASCII bytes introduced (no em/en/smart quotes).
   - HIERARCHY - readable at 1920x1080 baseline without scroll.
   Fix every MUST-FIX in the SAME slice before merge; log SHOULD/NICE as FUTURE.
3. If the Legion capture path is unavailable: the code-side audit still runs; the visual capture
   is OWED - log it as carry-forward in WAKEUP_NOTES + synopsis. Do NOT silently skip and do NOT
   block the run on it.

### 4. SECONDARY objective sweep (slot - TBD)
SECONDARY objective: TBD - set when the LW product is defined. Once set: sweep its levers each
run; ship a fix only when net-positive AND tests green, else record CLEAN no-commit with evidence.
Never trade product fidelity for cost. Generic levers that will likely carry over:
1. TBD - LLM call efficiency (prompt-cache `cache_control` coverage on every `messages.create()` caller).
2. TBD - hot-route `_CACHE` TTL constants.
3. Polling cadences - no sub-500ms network polls.
4. Log spam - every log path under ~1/sec (suppression needles are bare prefixes; trailing space fails).
5. TBD - model tier (cheapest model that meets the bar; escalate only where a charter requires).
6. Scheduled-task catalog - LW-* only; no orphans. 7. TBD - paired-artifact drift parity.

### 4b. PRIMARY objective program (north star slot - TBD)
PRIMARY objective: TBD - set when the LW product is defined. Preserve the skeleton: a one-line
north star + the enumerated surfaces to retire/lift + charter-exempt surfaces. Advance via PARALLEL
orchestrator lanes (concurrent, disjoint file sets):
- Lane A - TBD (primary precompute/derivation lane).
- Lane B - TBD (data/metric-backed generation lane).
- Lane C - TBD (deterministic user-facing surface lane).
- Lane D - TBD (shell/UI lift + agent lane; 3b ritual applies to its frontend slices).
Standing rule regardless of objective: flipping a surface off its current behavior is "done" only
when the replacement is validated against real usage; a WRONG replacement is worse than the status
quo - do not flip blind (the current path stays as the interim floor until validated).

### 5. Frozen-file edits under this run's grant
- Operator-authorized for the CURRENT run ONLY; do NOT carry forward.
- Route AROUND when possible (a single import line in the entrypoint to wire a non-frozen module is
  fine; rewriting a frozen core loop is a separate session).
- Every frozen-file commit body notes "frozen-file edit under operator's headless-upgrade grant".
- Frozen list is authoritative at the TOP of CLAUDE.md (TBD - populate as the product stabilizes;
  entrypoints, supervisors, and the ops/loop + bridge-watcher infrastructure are the expected
  initial members).

### 6. ASCII hygiene (hard rule)
- No em-dash, en-dash, or smart quotes anywhere (.py/.md/.ps1/.css/.js/commit/chat). ` - ` for a clause
  break, `-` otherwise. Nothing non-ASCII is exempt unless documented in CLAUDE.md as operator-approved.
- The /done gate runs `tests/test_smart_quote_hygiene.py tests/test_mojibake_hygiene.py
  tests/test_u2500_hygiene.py`; drift fix = `"C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe" tools/strip_smart_quotes.py --apply`.

### 7. Multi-agent dispatch rules
- Up to 100 concurrent worktree agents per task, disjoint file sets. Each agent prompt MUST carry the
  don't-redo set (CLAUDE.md "Settled" + docs/history_notes.md; concrete list TBD - populate as LW
  topics close) so it never re-researches closed topics.
- Agents return TRIAGED NOW/FUTURE/CLOSED with reasons; synthesize NOW into BACKLOG + issues, do NOT
  auto-implement everything. Verify agent premises against live data. Subagent files (esp. tests) MUST
  pass `ruff` before the agent reports done.

### 7b. Deep-dive competitor research (depth bar - NOT superficial)
A "lift from competitor X" task is a TRUE teardown: name the actual mechanic + math/data + LW
integration point (competitor set TBD - product not yet defined). Prefer DEPTH (one heavyweight
`general-purpose` agent per target) over breadth.
Tooling allowance (NOT subject to the section 4 runtime budget; load deferred MCP via ToolSearch
first): Chrome DevTools MCP / Claude-in-Chrome (render live, evaluate_script, capture XHR), Firecrawl,
nimble competitor-intel/positioning/deep-dive, Playwright MCP, Windows MCP / computer-use for a desktop
app, WebFetch/WebSearch/deep-research. Run/parse competitor binaries in an isolated Legion workspace (a
temp dir / disposable worktree); clean up artifacts. Illustrative not a whitelist; bounds = lawful +
authorized (public sites or operator machines) + non-destructive + secrets/frozen rules hold.
Depth checklist - every finding answers ALL six:
1. WHAT - the specific mechanic/UX/math (algorithm, interaction, data shape, network call).
2. HOW - under the hood (captured XHR payload, formula, state machine, render).
3. HAVE - does LW already do this? grep LW + cite the file.
4. WHERE - concrete LW integration point: file/module + layer (core logic vs route vs UI).
5. EFFORT + RISK - new data / new external or model dependency / schema lift, or presentation-only.
6. LIFT verdict - HIGH/MED/LOW + reason.
Lift legally: re-implement in LW's own code (never vendor unlicensed competitor code; unlicensed
sources are reference-only). Output `docs/COMPETITOR_LIFT_<YYYY-MM-DD>.md`. Then ACT: a HIGH-lift that
is low-risk (presentation over existing core logic, no new dependency/schema lift, testable) ships
IN-RUN as its own slice (+3b proof if UI). A HIGH-lift with new dependency / schema lift /
product-direction call -> BACKLOG + issue (FUTURE), not built blind. MED/LOW always defer.

### 8. Core audit iteration loop
- Core schema lifts run as PARALLEL slices (section 2), prioritizing lifts that unblock the
  section 4b lanes (once defined).
- Stop rule: 11 consecutive no-change iterations. Source of truth for domain data: TBD - pick ONE
  canonical upstream when the product is defined; never scrape unofficial mirrors.
- Each iteration touches ONE lane and either ships a version bump + tests, or records
  "no-change" with reasoning. After each bump: sync version pins across tests + bounce the owning
  process. Prefer parametrized property-style tests (invariants over exact values).

### 9. Interrupt protocol (no verbatim phrase match)
- ANY operator message during the run = interrupt. STOP starting new phases, FINISH the in-flight
  slice (never abandon a half-merged state), then run `/done`. A plain question -> answer in caveman
  ULTRA and resume; ambiguous question-vs-stop -> treat as stop-and-wrap.
- Mid-critical-path (mid-restart, mid-merge) -> finish the critical path FIRST, then handle.
- See PART C for the escalation channel (replaces a blocking AskUserQuestion).

### 10. Headless cadence health
- Desktop synopsis: update every phase complete (atomic); never delete mid-run.
- Living docs (CLAUDE.md item N+1, ROADMAP, BACKLOG, WAKEUP_NOTES, core product doc TBD): synced at
  run END as ONE surgical commit. WAKEUP prune: `"C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe" scripts/wakeup_prune.py --keep 3`.
- Worktree cleanup at run END (remove merged + prune + branch -D). 10h+ -> transition to a full LW
  refactor audit (frozen edits still allowed; tests required). Caveman ULTRA token discipline.

### 11. The /done ritual at run end (paired-artifact commit is CRITICAL)
Run `/done` (existing skill - local check gate, auto-commit + push, CI verify, bg-task stop, bridge
liveness, WAKEUP update + prune, living-doc sync, lessons drain, banner). CRITICAL standing rule
(concrete artifact TBD - product not yet defined): when the LW product defines a mirrored/derived
artifact (a share package, a generated bundle, doc anchors rewritten from source), any run that
touches its source - ESPECIALLY after a version bump or core math change - MUST re-sync and commit +
PUSH the derived artifact in the SAME commit as the source change, never a trailing afterthought:
- Run the artifact's sync tool (TBD - define it with the artifact; give it a `--check` mode).
- The `--check` mode must report in-sync and be wired as a CI guard (a source change that forgets the
  mirror or a doc anchor fails CI).
- A version change -> prepend a dated changelog entry in the artifact; update any authored semantic
  doc halves the auto-rewrite cannot do. Stage the artifact with the rest; credit upstream data
  sources in the commit body. Confirm CI green for the SHA.

### 12. Anti-patterns (do NOT repeat)
No `git add -A` without unstaging `_scratch/`; no skipping `ruff check` (F541 kills CI); no `--amend`;
no `Stop-Process` (use taskkill /F /PID); no uncleaned locked worktrees at run end; no Claude co-author
trailer; no trusting an agent premise unverified; no research agent without a don't-redo list; no
unstated reload/restart mechanism when shipping frontend changes; no feature flags / backwards-compat
shims for what should just BE the new behavior; no WHAT-comments (WHY only); no blocking
AskUserQuestion mid-run (use PART C); no frontend slice marked done without 3b visual capture +
UI-audit (or an explicit OWED carry-forward).

### 13. Final banner (on interrupt or empty queue), then call /done
```
HEADLESS UPGRADE WRAP
  HEAD: <short-sha> (<N> commits this run)
  VERSION: <old> -> <new> | n/a        paired artifact: synced (--check green) | n/a | TBD
  LW: <N> tests
  CI: <N>/<N> green (<N> red)
  objectives: PRIMARY <TBD | progress> / SECONDARY <N levers swept, M shipped | all CLEAN | TBD>
  ui proof: <N pages captured + audited, M owed | n/a>
  worktrees: <cleaned N | none>
  Synopsis: C:/Users/Administrator/Desktop/LW_HEADLESS_SYNOPSIS_<date>.md
  Ready for /done.
```

================================================================================
PART C - TWO-WAY GEMINI ESCALATION (replaces a blocking AskUserQuestion)
================================================================================
The operator is away; NEVER block on AskUserQuestion. When you need a scope decision, hit an
architectural roadblock, or need ROADMAP/BACKLOG reshaped mid-run, use ONE of two channels. Gemini is
READ-ONLY - it DECIDES and DIRECTS; the next Claude cycle does every file write. Do not claim Gemini
"physically implements" anything.

1. SYNCHRONOUS advice (preferred for a question you can resolve mid-cycle without ending it):
   `powershell -NoProfile -File "C:\LegionWallpaper\tools\gemini_ask.ps1" -Question "<terse grounded question>"`
   Read-only Gemini answers on stdout (also saved to `gemini_io/answer_<id>.md`). Take its recommendation,
   log the choice in the synopsis + WAKEUP_NOTES, and PROCEED. Do not wait/block.

2. DURABLE hand-off (for a TRUE blocker that should end the cycle and reshape the next directive):
   - Atomic-write the findings + context + the explicit question to `ops/loop/control/gemini_ask.txt`
     (tmp + os.replace; plain ASCII).
   - Finish the in-flight slice (never a half-merged state), then run the FINAL STEP
     `"C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe" ops/loop/done_sentinel.py --tests <N> --regressions <0|1>` to end the cycle cleanly.
   - The controller consumes `gemini_ask.txt` into the NEXT director call under an `EXECUTOR ESCALATION`
     header (consume-once); the Gemini DIRECTOR resolves it and emits the next directive that encodes the
     decision + instructs the scaffolding + any ROADMAP.md / BACKLOG.md reshape. The per-cycle `/done` +
     `/clear` already run automatically, so continuity is preserved on disk.
   - If you cannot safely proceed AND cannot end the cycle, default to the safest reversible option, log
     it loudly, and record the decision as a FUTURE item - a genuinely operator-only call becomes a
     BACKLOG entry, not a hang.

================================================================================
PART D - LOOP BEHAVIOR / STOP CONDITIONS / TUNING (controller-driven, automatic)
================================================================================

### Per cycle (all automatic)
- gemini DIRECTOR reads git log + docs/LEDGER.md + ROADMAP + last result (+ any EXECUTOR ESCALATION) ->
  writes one orchestrator-pattern directive (TDD, parallel disjoint slices, Claude sole merger,
  verifier-gate each slice, commit-local, no AskUserQuestion, ends with the done_sentinel FINAL STEP).
- AHK types `/clear` + "read+execute ops/loop/control/directive.md" into this window.
- The executor (this session) runs PART B + C, commits locally, runs
  `"C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe" ops/loop/done_sentinel.py --tests <N> --regressions <0|1>` -> writes control/claude.done.
- Controller meters spend from the pinned executor JSONL, then gemini AUDITS the diff. CLEAN -> next
  item; REGRESS (or self-reported regressions) -> next directive is FIX-FIRST.

### Stop conditions (any one writes control/STOP; AHK + controller exit)
- GEMINI spend >= ceiling_usd (config.json, default $15) - caps GEMINI ONLY; Claude/executor spend is
  UNCAPPED per operator. Gemini runs ~cents/cycle, so max_cycles is the real limiter.
- directive absent / gemini returns NO_WORK; claude.done not seen within cycle_deadline_sec (hang);
  2 consecutive cycles with the same git sha (no progress); max_cycles reached; operator drops
  `ops/loop/control/STOP` by hand (instant abort).

### Tuning (operator edits ops/loop/config.json)
`ceiling_usd`, `max_cycles`, `cycle_deadline_sec`, `gemini_model`, `clear_each_cycle`, `directive_suffix`
(e.g. allow push). Dry-test the plumbing with no spend:
`launch_loop.ps1 -Mode dry` (uses config.dry.json + claude_stub.py).
