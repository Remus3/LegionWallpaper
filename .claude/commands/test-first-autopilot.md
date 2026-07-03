# Test-First Spec-to-Ship Autopilot

> **SUBAGENT-FIRST (standing protocol, operator 2026-06-20).** Always use subagents for substantive work; do not build solo in the main thread.
> 1. **Spec first:** a Plan/design subagent (or the Gemini director) emits the spec/plan BEFORE any code; verify it vs ground truth (grep cited file:line, live `ops/runtime/health.json` + the product live-state endpoint (TBD - product not yet defined), git) - never scaffold on assumptions.
> 2. **New session:** interview the Gemini director (or the operator if Gemini is down) for intent + acceptance criteria, re-probe live state, THEN build.
> 3. **Act via subagents:** worktree-isolated build agents on disjoint files (sole merger) + a read-only `verifier` subagent gate before any merge or "done".
> 4. Trivial one-line cosmetic edits may inline (refines R9). See `CLAUDE.md` "Subagent-First Protocol" + memory `feedback_subagent_first_protocol`.

Given a batch spec, drive it strictly test-first to 100% green, then ship it.
Run end to end without checking in. ASCII only, no em/en dashes or smart
quotes in any authored byte. This is the TDD-strict sibling of `ship-batch`:
ship-batch SELECTS and implements a ROADMAP batch; this one takes a spec you
already have and proves it with derived tests before a line of impl exists.

## 0. Pin the spec + ground truth

- Restate the spec as a one-paragraph contract: exact behavior, the inputs,
  the expected outputs. State assumptions explicitly before any code.
- Source every expected number from the LIVE canonical upstream data source,
  never a guess. The canonical source + the repo's data-path helpers are
  TBD - product not yet defined; when set, record them HERE and always fetch
  through the repo's helpers (if an upstream rejects UA-less requests, use
  the repo's UA-aware fetch helper - do not hand-roll a fetch).
- NO hardcoded magic numbers: a test asserts `engine(x) == formula(x)` where
  `formula` is the canonical-source expression evaluated in the test, not a
  literal pasted constant. NO fragile cross-entity comparison asserts (never
  "entity A score > entity B score"); assert on the computed quantity itself.

## 1. RED - scaffold the tests first

- Write the failing tests BEFORE implementation, in `tests/` (follow the
  suite's established naming conventions; component-scoped test dirs are
  TBD until the product core exists).
- Prefer property/derivation tests: recompute the expected value from the
  formula for several input points and assert the engine matches each. Pin
  boundary cases (minimum, maximum, zero, saturation) where the formula has
  known exact values.
- When stubbing a method accessed via the class, wrap it with `@staticmethod`
  correctly.
- Run the new tests and CONFIRM THEY FAIL for the right reason (RED). A test
  that passes before implementation is not testing the spec.

## 2. GREEN - loop Edit / pytest

- Implement the minimal change to satisfy the spec.
- Loop: `python -m pytest tests/<new>.py -q` -> Edit -> repeat until the new
  tests pass.
- Then the FULL gate, which must be 100% green with zero regressions:
  the component suite first (baseline is version-pinned once a core version
  constant exists - TBD; know the current passed + subtests count and do not
  drop it), then `python -m pytest -q` for the wider suite.
- Do not weaken a real assertion to get green. If a prior pin legitimately
  moved because the spec corrects it, rebaseline it deliberately and say so
  in the commit; never silently.

## 3. Ship

- `python -m py_compile` every changed `.py` (silent crash under pythonw.exe
  otherwise).
- Single core VERSION bump (the version constant location is TBD - define it
  when the product core exists; semver: minor for a feature/correctness
  batch, patch for a pure fix) + sweep every pinned `VERSION == "<old>"`
  guard assertion in the tests (the pin IS the guard - a stale pin fails,
  proving the bump was deliberate). Re-run `python -m pytest -q` fully green.
- Conventional commit naming the spec + the version delta; push origin main.
  Confirm the pre-commit reports py_compile OK.
- Verify live: a separately-hosted component is restarted via its documented
  LW-* scheduled-task ritual (TBD - `schtasks /End /TN LW-<Task>` then
  `/Run`; hard fallback `taskkill /F /PID <pid>` then `/Run`; never
  `Stop-Process`) and confirm its health endpoint serves the new version
  (endpoint TBD). If the core app changed: `echo restart > restart_trigger.txt`
  then verify `ops/runtime/health.json` (new pid, alive, last_reload_ok).
- Sync living docs on the version bump (CLAUDE.md / the core product doc /
  README: version + test count; do not rewrite dated ledgers).
  Append a WAKEUP_NOTES.md hand-off (last 2-3 sessions full, archive older
  to docs/history_notes.md).
  `/done`.

## Mirror discipline

The tracked canonical IS this file: `.claude/commands/test-first-autopilot.md`.
LW tracks `.claude/` in git (only machine-local pieces are gitignored), so
there is no `tools/` copy and no `.claude/skills/` mirror - the RC-inherited
multi-copy mirror scheme was collapsed to a single tracked file at port time
(ADR-001). After any edit: keep it ASCII-only and commit it; an uncommitted
or non-ASCII command file is the only drift to watch for.
