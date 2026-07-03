# Ship Legion Wallpaper Batch (one pass)

> **SUBAGENT-FIRST (standing protocol, operator 2026-06-20).** Always use subagents for substantive work; do not build solo in the main thread.
> 1. **Spec first:** a Plan/design subagent (or the Gemini director) emits the spec/plan BEFORE any code; verify it vs ground truth (grep cited file:line, `ops/runtime/health.json` when it exists, git) - never scaffold on assumptions.
> 2. **New session:** interview the Gemini director (or the operator if Gemini is down) for intent + acceptance criteria, re-probe live state, THEN build.
> 3. **Act via subagents:** worktree-isolated build agents on disjoint files (sole merger) + a read-only `verifier` subagent gate before any merge or "done".
> 4. Trivial one-line cosmetic edits may inline (refines R9). See `CLAUDE.md` "Subagent-First Protocol" + memory `feedback_subagent_first_protocol`.

One self-contained pass: select the next LW batch, implement it, prove it green,
bump the version, ship it, verify live, hand off. Run end to end without stopping
to check in. ASCII only, no em/en dashes or smart quotes in any authored byte.

## 0. Pre-flight (state, do not trust recollection)

- Read ROADMAP.md "Open items" + BACKLOG.md; pick the next batch (lowest open
  priority, or the explicit "continue" target). Live truth, never the ledger:
  - the authoritative product VERSION constant in source (TBD - product not yet
    defined; when it exists, source is authoritative, NOT pyproject)
  - the live health endpoint, if a service is running (TBD - product not yet
    defined)
- State the batch scope + assumptions explicitly before editing.

## 1. Implement

- Schema/engine/registry changes for the batch only. No drive-by refactor.
- Atomic writes (`tmp.write_text(...); tmp.replace(target)`); consumers may
  poll mid-write.
- Write `.py` as ASCII + LF (the repo .gitattributes pins `*.py eol=lf`; the
  documented CRLF incident came from autocrlf re-adds - author LF).

## 2. Prove green

- Add tests for the new behavior. Property-based over live upstream data/math
  where possible; no hardcoded magic numbers; avoid fragile cross-item comparison
  asserts (assert on computed quantities). Wrap class-accessed stubs with
  `@staticmethod` correctly.
- Targeted suite for the touched module until green, then the wider guard suite
  `python -m pytest -q` before the version bump.

## 3. Bump the product VERSION (with the guard)

(TBD - product not yet defined; the ritual below is the standing rule to apply
once LW has an authoritative VERSION constant.)

- Edit the single authoritative VERSION constant in source (semver; minor for a
  feature batch, patch for a correctness fix).
- Update every pinned assertion - tests that assert `VERSION == "<old>"` exist
  ON PURPOSE. Sweep them in one pass; the pin IS the guard test (a stale pin
  fails, proving the bump was deliberate).
- Re-run `python -m pytest -q` - must be fully green.

## 4. Compile + commit + push

- `python -m py_compile` every changed `.py` (syntax errors crash silently
  under pythonw.exe).
- Conventional commit naming the batch + version delta, e.g.
  `feat(<area>): <batch> (VERSION x.y.z -> x.(y+1).0)`.
- `git push origin main`. Confirm the pre-commit hook reports py_compile OK.

## 5. Verify live (TBD - product not yet defined)

Standing rule preserved for when LW runs services (the RC analog was a scheduled
task-hosted engine service that the supervisor did NOT watch):

- Services run under `LW-*` scheduled tasks (`pythonw.exe tools/<start script>`).
  A service that does not honor `restart_trigger.txt` and is not bounced by the
  supervisor must be restarted explicitly:
  `schtasks /End /TN LW-<Task>` then `schtasks /Run /TN LW-<Task>`
  (hard fallback: `taskkill /F /PID <pid>` then `schtasks /Run /TN LW-<Task>`).
  Never `Stop-Process`.
- Verify the service health endpoint reports the new version and a known
  reference output is unchanged where it should be.
- If the main LW runtime was touched: `echo restart > restart_trigger.txt`, then
  confirm `ops/runtime/health.json` shows a new pid, `alive=true`,
  `last_reload_ok=true`.

Until LW has running services: skip this section and note "no live surface yet"
in the hand-off.

## 6. Hand off

- Sync living docs on the version bump: CLAUDE.md / the core product doc (TBD) /
  README - version + test count. Do not rewrite dated ledgers; only living docs.
- Append a WAKEUP_NOTES.md entry (keep last 2-3 sessions at full fidelity,
  archive older to docs/history_notes.md): batch, version delta, commit hash,
  test totals, live-verify result, any flagged follow-up. ASCII only.
- `/done` if this was the unit of work.

## Mirror discipline

The tracked canonical IS this file: `.claude/commands/ship-batch.md`. LW
tracks `.claude/` in git (only machine-local pieces are gitignored), so there
is no `tools/` copy and no `.claude/skills/` mirror - the RC-inherited
multi-copy mirror scheme was collapsed to a single tracked file at port time
(ADR-001). After any edit: keep it ASCII-only and commit it; an uncommitted
or non-ASCII command file is the only drift to watch for.
