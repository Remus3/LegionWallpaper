---
description: End-of-session ritual - auto-commit any pending changes, push, do the /wrap checks, then signal "ready for /clear" so the next session starts fresh without context bloat. Use when work is wrapped and you want a clean exit.
---

> **SUBAGENT-FIRST (standing protocol, operator 2026-06-20).** Always use subagents for substantive work; do not build solo in the main thread.
> 1. **Spec first:** a Plan/design subagent (or the Gemini director) emits the spec/plan BEFORE any code; verify it vs ground truth (grep cited file:line, `ops/runtime/health.json` when it exists, git) - never scaffold on assumptions.
> 2. **New session:** interview the Gemini director (or the operator if Gemini is down) for intent + acceptance criteria, re-probe live state, THEN build.
> 3. **Act via subagents:** worktree-isolated build agents on disjoint files (sole merger) + a read-only `verifier` subagent gate before any merge or "done".
> 4. Trivial one-line cosmetic edits may inline (refines R9). See `CLAUDE.md` "Subagent-First Protocol" + memory `feedback_subagent_first_protocol`.

The user wants to end the session cleanly so the next one starts with a fresh context window. This is /wrap, but with auto-commit instead of "stop and ask". Run all sections in order; surface a tight final banner.

### 0. Local check gate - commit only when green

Versioning is cheap; lost work is not. The operator never passes up a commit + push. So the DEFAULT is: always commit + push when local checks are green. Do NOT leave authored work uncommitted at session end just because a change feels small or unfinished - if it passes its checks, it ships.

- Identify the files authored this session: `git -C "C:/LegionWallpaper" status -s`.
- Run the cheap local gate on the touched surface:
  - `"C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe" -m ruff check .` (must report ALL CHECKS PASSED)
  - `"C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe" -m py_compile <each touched .py>` (syntax - silent-crash guard per CLAUDE.md hard rule)
  - **Authored-source hygiene (ALWAYS run, every /done - CI runs these same guards via `pytest tests/` in the `check` job of `.github/workflows/ci.yml`):** `"C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe" -m pytest tests/test_smart_quote_hygiene.py tests/test_mojibake_hygiene.py tests/test_u2500_hygiene.py -q`. Must be green. No smart quotes / em-en dashes / NBSP / ellipsis / mojibake / U+2500 in authored source. If this fails, it is NEVER "pre-existing / unrelated / not in CI" - it is in CI now (every push/PR via the `check` job; the nightly adds `tools/strip_em_dashes.py --check` as a style drift gate); fix it (`"C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe" tools/strip_em_dashes.py --apply` for smart-quote/dash drift) before the gate is green.
  - Test slice covering the change: full `tests/` for broad edits, the targeted module for narrow ones. (Product-specific suites: TBD - product not yet defined; add them here when the LW engine exists.) **Run the FULL suite locally - do NOT defer it to CI.** Measured 2026-07-26: `pytest tests/ -q` = 577 passed / 11 skipped in **21s**. The machine-wide ritual doc (`DONE_RITUAL_OPTIMIZED.md`) moves the full suite off-machine because Riot Commander's takes ~27 min; at 21s that trade is inverted - dispatching CI would make the wrap slower AND burn metered Actions minutes. Re-measure before adopting the off-machine shape; the threshold is roughly "local suite exceeds the ~17 min CI round trip".
  - `"C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe" tools/drift_guard.py` - per-session drift guard (doc budgets / command-doc SUBAGENT-FIRST parity / memory-index integrity / counted claims / untracked authored docs / cited-SHA resolvability). Exit 0 = clean. Adopted 2026-07-26 from `DONE_RITUAL_OPTIMIZED.md` sec 3. After a version bump pass the OLD version as argv[1] to sweep stale anchors.
- Ground truth, not memory (per CLAUDE.md Verification Discipline): run the gate FRESH this turn, read the pass/fail counts you observe now, and `ls` any test file you cite as added - never carry forward a prior or subagent-reported green. If the work came from parallel slices, the `verifier` subagent's CONFIRM is the gate, not the slice agent's claim.
- GREEN: proceed to commit (section 1).
- RED: fix and re-run. If the failure is pre-existing and unrelated to this session's work, note it ABOVE the banner and commit only the green-verified authored files - never commit over a regression you introduced.

### 0b. External review package sync (TBD - product not yet defined)

Process rule preserved as a placeholder. When Legion Wallpaper gains an external-facing review package or generated mirror (the RC analog was a Share/ package: deterministic source mirror + authored handoff docs), that package MUST stay in lock-step with the live source on every change that touches its subject - this is the durable update path. The rule set to reinstate at that point:

- Detect from `git status -s` whether this session touched the package's subject; skip if not.
- Re-mirror + verify with the package's sync tool (ground truth, not memory); the sync tool owns the mechanical version/anchor literals - never hand-edit them; run its `--check` mode (the exact guard CI runs) until it reports in-sync.
- Keep the authored docs' SEMANTIC half fresh too - update prose the change made stale, add sections for genuinely new subsystems, archive/fold one-off effort docs to their done-state (completed work is named as done, not deleted and not left describing a future).
- Keep authored docs CLEAN (external voice): no item numbers, session refs, operator names, or outside-project names.
- On a version bump: prepend a dated release entry to the package CHANGELOG (newest-first) and credit upstream sources of truth in the entry and the commit body.
- Stage the package with the rest of the authored files in section 1 - the package sync is part of the SAME commit as the source change, never a trailing afterthought.

Until such a package exists: skip this section.

### 1. Auto-commit any pending changes

- `git -C "C:/LegionWallpaper" status -s`
- If output is empty: skip to section 2.
- Otherwise:
  - **Audit before staging**: refuse to auto-commit any path matching `*SECRET*`, `*HANDSHAKE*`, `*PIVOT*`, `*REPLY*`, `*TOKEN*`, `*KEY*`, `.env*`, `local_paths.json`, or anything that looks like credentials. If matched: stop and ask the operator before proceeding.
  - **Frozen-file guard**: per `CLAUDE.md`, several files require explicit user approval before editing. If any modified path is in the frozen list, stop and ask - auto-commit is too dangerous here. Frozen list lives at the top of CLAUDE.md.
  - Stage only the changes you authored this session (`git add <specific files>`). Do NOT use `git add -A` - accidentally commits .env / runtime junk.
  - Draft a one-line commit message summarising the session's work (1-2 sentences, "why" over "what"). If multiple distinct themes: list them as bullets in the body.
  - Commit with NO Claude co-author trailer - the `Co-Authored-By: Claude ... <noreply@anthropic.com>` line is banned repo-wide (CLAUDE.md hard rule, operator policy 2026-06-03). `.githooks/commit-msg` -> `precommit_gate.py --message-file` strips it if the harness appends one anyway; do not add it back.
  - If pre-commit hooks fail: fix and create a new commit (never `--amend`).

### 2. Push

- `git -C "C:/LegionWallpaper" log @{u}.. --oneline` - list local commits not on origin.
- If empty: skip.
- Otherwise: `git -C "C:/LegionWallpaper" push origin <branch>`. No confirmation prompt - pushing is part of the exit ritual.
- Surface the push result (e.g. `23854e1..b56f247 main -> main`) in the final summary.
- Only ask the operator if the push fails (auth, conflict, hook).

### 2b. GitHub CI verification

- After the push lands, confirm CI goes green for the pushed SHA:
  - `gh run list --branch <branch> --limit 1` to find the run id (gh = `C:/Program Files/GitHub CLI/gh.exe`; use the absolute path in older shells).
  - `gh run watch <run-id> --exit-status` - blocks until the run finishes; exit 0 = green.
- Report the CI result in the banner: `green | red | pending`.
- If CI goes RED on a real test/lint failure: surface the failing job ABOVE the banner and add "resolve CI <job> before /clear" to the bottom line. The local gate (section 0) should have caught it, so a red here usually means an env-only delta - investigate before declaring the session cleanly wrapped.
- Do NOT block /clear on flaky-infra red, but do NOT silently ignore a genuine failure either.

### 3. Background tasks started this session

- TaskList - show anything still running.
- Each one: TaskStop. DO NOT leave monitors armed; they're useless after /clear.

### 4. LW restart pending

- Check `C:/LegionWallpaper/restart_trigger.txt` - if non-empty, the LW runtime may still be reloading. Confirm `ops/runtime/health.json` shows `alive=true` AND `last_reload_ok=true` before declaring done. (Skip if `ops/runtime/health.json` does not exist yet - no LW runtime is live until the product is defined.)

### 6. WAKEUP_NOTES update

- The next session will bootstrap from `C:/LegionWallpaper/WAKEUP_NOTES.md` + `MEMORY.md` + git log. Make sure tomorrow-you can pick up cleanly.
- Append a short entry (<=20 lines) describing this session's work: commits shipped, key decisions, what's next. Don't rewrite history; just append.
- Note explicitly any blockers or things tomorrow-you should NOT redo (e.g. "fix X already shipped in <sha> - don't re-investigate").

### 6b. Living-doc sync (ROADMAP / CLAUDE.md / README)

Update the three living docs based on what shipped this session. These are surgical edits - never full rewrites.

**ROADMAP.md**
- Find any item that shipped this session: flip its status marker from open/in-flight to DONE and append the commit short-SHA in parentheses. (ASCII markers only - the repo hard rule forbids emoji status glyphs.)
- Add new open entries for anything that's now next or in-flight.
- Do NOT touch items that are already DONE or haven't been worked on.

**Per-item completion ledger -> `docs/LEDGER.md` (NOT CLAUDE.md)**
- Append the new item entry at the TOP of the `docs/LEDGER.md` body (newest-first), in the existing entry format.
- CLAUDE.md "Active priorities" is a STATIC POINTER - do NOT add item entries to CLAUDE.md (CI size-budgeted < 60KB).
- In CLAUDE.md touch only the `### Settled` summary or a one-line product reference when relevant - never the ledger.

**README.md**
- Update only if something structural changed (new capability, new component, new agent). Light-touch: one bullet or badge line at most.
- If nothing structural changed: skip entirely - don't update the README just to say you ran /done.

**Product-doc changelogs (TBD - product not yet defined)**
- When LW gains a core product doc with a version changelog (RC analog: a per-engine-version changelog doc), the rule is: changelog newest first, ONE line per version bump - never append to a prior version's line. On a version bump, prepend a new bullet; do NOT extend an existing version's bullet. Bump the short status header (version + test count) in the same edit.
- `docs/ARCHITECTURE.md` keeps a short summary + structural bullets + a pointer to the product doc's changelog - do NOT paste the per-version narrative there. Appending to a prior version's line is what produced the unreadable single-line megastring this rule retired.

Commit all touched docs with a message like `docs: sync living docs - <session-topic>`. If none needed editing, skip the commit.

### 6c. WAKEUP_NOTES archiving

Keep WAKEUP_NOTES.md to last 2-3 full sessions only. Headless spawn overhead grows linearly with file size (each `claude --print` cold-loads it).

Run the auto-prune helper:

```
"C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe" "C:/LegionWallpaper/scripts/wakeup_prune.py" --keep 3
```

This moves any session block past the 3 most recent into `docs/history_notes.md` (newest-first, atomic write). It is a no-op when WAKEUP_NOTES already has <=3 sessions, so always-safe to run. Add `--dry-run` first if you want to preview what would move.

Manual follow-ups (only if needed):
- Compaction rule for archive entries older than 5 sessions: compress to a 1-2 line bullet (date, commit SHA, theme). The auto-prune does NOT compact - it only moves. Compact by hand once entries get stale.
- No commit needed for WAKEUP_NOTES changes - already tracked in section 6 above.

### 7. Memory updates

- List new/modified files under `C:/Users/Administrator/.claude/projects/C--LegionWallpaper/memory/` since session start.
- Confirm `MEMORY.md` indexes any new memories; add if missing.

### 8. Live-state safety check (TBD - product not yet defined)

- Process rule preserved as a placeholder: before declaring the session wrapped, probe the live product runtime state and warn the operator if running /clear right now would cut off operator-facing live functionality mid-use (the RC analog was a mid-game coaching check against the live state endpoint).
- When LW has a live runtime with operator-facing state: probe it here and, if the operator is mid-use, warn that /clear will interrupt until the next session starts. Until then: skip.

### 8b. Session-size check (folded from /wrap)

- Find the active session jsonl: `Get-ChildItem "C:/Users/Administrator/.claude/projects/C--LegionWallpaper/" -Filter "*.jsonl" | Sort-Object LastWriteTime -Descending | Select-Object -First 1 Name, @{N='MB';E={[math]::Round($_.Length/1MB,1)}}`
- > 10 MB: add "session file > 10 MB - /clear overdue" to the banner.
- > 20 MB: escalate ABOVE the banner - at this size compaction is lossy and the model is already degraded.

### 9. Final banner

Print a tight banner - exactly this format:

```
==================================================================
  /done complete - context ready for /clear
==================================================================
  - commits this session : <count> (pushed: <push range>)
  - local check gate     : green | red (<failing>)
  - github CI            : green | red (<job>) | pending
  - background tasks     : stopped <count>
  - LW health            : pid=<pid> alive=<bool> reload_ok=<bool> | n/a (no runtime yet)
  - WAKEUP_NOTES         : updated (+<N> lines)
  - living docs          : roadmap/claude.md/readme - <N items updated | skipped>
  - review package       : n/a (TBD - product not yet defined)
  - session file         : <N> MB <ok | /clear overdue>
  - live-state risk      : no | YES - wait until safe to /clear
  - next-session prompt  : printed below
==================================================================
  Type /clear to start a fresh session with reset token budget.
==================================================================
```

If anything failed (commit blocked, push failed, live-state risk, etc.), surface the issue ABOVE the banner and substitute "WARNING: resolve <X> before /clear" on the bottom line.

### 10. Next-session prompt (ALWAYS - never skip)

Every /done ends by handing the next session a running start. After the banner, ALWAYS print a fenced, copy-pasteable prompt block the operator can drop straight into a fresh /clear'ed session. Source it from ground truth this turn, not memory:

- The "what's next" line you just wrote into `WAKEUP_NOTES.md` (section 6).
- The top open item in `ROADMAP.md` (the next open / NEXT).
- Any blocker or do-NOT-redo you flagged this session.

Keep it self-contained - the next session boots with zero context: name the single next task, the key file paths / endpoints / live-state it touches, the acceptance check, and any "already shipped - don't re-investigate" note. One tight block, no preamble:

```
NEXT SESSION
------------
Task: <one-line next task from ROADMAP/WAKEUP>
Context: <key files / endpoints / live-state to probe first>
Acceptance: <how the next session knows it is done>
Do NOT redo: <anything shipped this session that still looks open>
Start with: /clear, then bootstrap from CLAUDE.md + MEMORY.md + WAKEUP_NOTES + git log.
```

This is mandatory. Never end /done without it - even when the only next task is "pick the next ROADMAP item".

### Safety rails

- NEVER force-push, NEVER use `--amend`, NEVER skip hooks (`--no-verify`).
- NEVER auto-commit secrets, frozen files, or runtime junk.
- NEVER run `/clear` from inside the skill - it's a Claude Code built-in handled by the harness, not the model. Just print the banner and let the operator type it.
- If git push needs auth (gh CLI prompt, etc.): stop and ask. Don't keep retrying.
