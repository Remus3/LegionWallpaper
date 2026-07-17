# Gemini CLI Overnight Auditor - Config (Legion Wallpaper)

> **PROVISIONAL - revisit after calibration.** Nothing here is hard-ruled into
> CLAUDE.md or any frozen file. Authored 2026-06-04 in the RC ancestor project;
> ported to Legion Wallpaper 2026-07-03. All knobs are tunable.

## Division of labor

- **Gemini CLI** = read-only advisor / critic / researcher. Reads the repo,
  writes findings to a review file. NEVER edits source, never commits.
- **Claude (me)** = sole implementer / writer. I parse Gemini's review file,
  verify every claim against ground truth, and am the only agent that touches
  source or version control. Gemini proposes; I dispose.

## Decisions (this round)

| # | Category        | Decision                                                      | Source     |
|---|-----------------|--------------------------------------------------------------|------------|
| 1 | Auth Mode       | API key via `GEMINI_API_KEY` env var (User scope)            | default    |
| 2 | Cadence         | Nightly timer (LW-GeminiAudit scheduled task - NOT YET REGISTERED, see below) | OPERATOR |
| 3 | Scope Lanes     | open-task audit + analyzer triage + architecture critique + research (product lanes TBD) | OPERATOR |
| 4 | Output Channel  | `docs/EXTERNAL_REVIEW_<YYYY-MM-DD>.md`                        | default    |
| 5 | Autonomy        | Supervised digest - findings only, I review before any code  | OPERATOR   |
| 6 | Rate Ceiling    | 1 audit call per trigger; hard cap 10 calls/day (backstop)   | default    |
| 7 | Model           | gemini-3-pro-preview (paid, billing on), diff/backlog-scoped, via `LW_GEMINI_MODEL` | OPERATOR |

## How the loop runs (mechanics, 1:1 from the RC ancestor)

1. `tools/gemini_audit.ps1` runs (nightly task once registered, or by hand).
2. It resolves the commit range: `ops/runtime/gemini_last_audit.txt` marker
   (else `HEAD~10`) .. `HEAD`. No new commits -> exit 0, nothing to audit.
3. It assembles the context digest: `git log --oneline` of the range +
   `git diff --stat` + full `git diff` (truncated at 60k chars) + the HEAD
   (top, highest-priority-first) of `ROADMAP.md` (120 lines) and `BACKLOG.md`
   (80 lines), appended to `tools/gemini_audit_prompt.md`.
4. The prompt is piped via STDIN to the `gemini` CLI, launched read-only
   (`--approval-mode plan --skip-trust`), model from `LW_GEMINI_MODEL`
   (default gemini-2.5-flash), with retry-on-empty and a fallback model
   (`LW_GEMINI_FALLBACK_MODEL`, default gemini-2.5-flash), all bounded by one
   shared wall-clock deadline (`-MaxWaitSec`, default 180s).
5. Findings land in `docs/EXTERNAL_REVIEW_<YYYY-MM-DD>.md` (atomic tmp+move
   write, PROVISIONAL header stamped). The marker file is advanced to HEAD.
   Run log: `logs/gemini_audit.log`.
6. Severity lanes: every finding carries a lane tag ([OPEN-TASK] / [ANALYZER] /
   [ARCHITECTURE] / [RESEARCH], product lanes TBD) + severity high/med/low +
   file:line + suggested direction (never a diff - Claude implements).
7. Consumption: Claude ingests the newest unconsumed review at session start
   per `docs/GEMINI_REVIEW_CONSUMPTION.md` - verify every claim against disk
   NOW, discard what cannot be reproduced, TDD-first on every accepted change,
   nothing auto-applies, track the consumed filename in
   `ops/runtime/gemini_review_consumed.txt`.

### Exit codes

- `0` - review written, or benign skip (no new commits / external Gemini
  emptiness after all retries - degraded-not-broken, logged loudly).
- `2` - `GEMINI_API_KEY` missing in User scope (genuine config fault, stays red).
- `3` - no git repo at `C:\LegionWallpaper` yet (LW-only guard: the audit arms
  when the product has code; a prematurely registered task stays diagnosable).

## Scheduled task (documented, DO NOT register yet)

The LW product is not yet defined and the repo has no code/commits, so the
nightly task is NOT registered. It ARMS when the product has code (git repo
with commits exists). When that day comes, register with:

```
schtasks /Create /TN "LW-GeminiAudit" /SC DAILY /ST 03:00 /RL LIMITED /F /TR "powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\LegionWallpaper\tools\gemini_audit.ps1"
```

Matches the LW-* scheduled-task naming convention and the RC ancestor's
nightly 03:00 night-watch slot. Until registered, run by hand:
`powershell -NoProfile -ExecutionPolicy Bypass -File C:\LegionWallpaper\tools\gemini_audit.ps1`

## Cost (verified 2026-06-04 in the RC ancestor - re-verify before arming)

- Gemini 3 Pro paid: `$2.00/M` in, `$12.00/M` out (<=200K ctx).
- Diff-scoped audit ~ 70K in / 8K out per run -> ~`$0.24`/run.
- Nightly cadence: ~30 runs/mo -> ~`$7`/mo. (Per-commit was considered then
  dropped in favor of the overnight night-watch timer.)
- Full-tree was rejected (~`$97`/mo, re-reviews static code).

## Open design flags

- **Cadence mechanism.** RESOLVED (RC ancestor, 2026-06-04) -> nightly
  `schtasks` timer (`LW-GeminiAudit`, overnight), matching the LW-* task
  pattern. Registration deferred until the product has code (see above).
- **Paid tier.** Enable billing on the AI Studio / Cloud project at key
  creation. Removes the free-tier train-on-prompts behavior (moot here, but a
  bonus). Env-var wiring is identical to free.
- **Diff source.** "the diff" = `git diff` of the merge (changed files +
  surrounding context) + open `ROADMAP.md` / `BACKLOG.md` items, NOT the full
  tree. A `.geminiignore` must still exclude: `_archive/`, `docs/_archive/`,
  `node_modules/`, `.git/`, `*.db` / `*.sqlite*`, `logs/`, `ops/runtime/`,
  secrets (`.env*`, `*.pem`, `*.key`, any key/token files), plus Gemini's own
  channels (`gemini_io/`, `docs/EXTERNAL_REVIEW_*.md`) to avoid self-ingest
  loops. Product-specific exclusions: TBD - product not yet defined.
  NOTE: `.geminiignore` is not yet created in LW - create it with the audit's
  first arming.

## Status

- [x] STEP A - Q&A recorded (carried from the RC ancestor; this file)
- [x] STEP B - pricing + token math (carried; re-verify before arming)
- [x] BREAKPOINT - GEMINI_API_KEY set (User scope) + billing enabled on this
      machine, live-verified 2026-06-04 for the RC ancestor. Same machine, same
      key; re-verify presence before first LW run.
- [ ] STEP C - PARTIAL. tools/gemini_audit.ps1 (stdin-pipe + retry + atomic
      write + no-repo guard) + tools/gemini_audit_prompt.md ported 2026-07-03.
      Read-only enforced by `--approval-mode plan`, workspace via `--skip-trust`.
      Remaining before arming: create `.geminiignore`; set `LW_GEMINI_MODEL`
      (User scope) if a non-default model is wanted; register LW-GeminiAudit
      nightly 03:00 ONLY once the repo has commits; verify the first real
      review lands in docs/EXTERNAL_REVIEW_<date>.md.
- [ ] STEP D - tone/style/memory artifacts
- [ ] EXPANDED - in-session Q/A channel (`tools/gemini_ask.ps1` ->
      `gemini_io/answer_<id>.md`, read-only, validated in the RC ancestor) not
      yet ported to LW; port when the audit arms.

## Expanded scope (operator decision carried from the RC ancestor, 2026-06-04)

Gemini is not only the nightly critic - it is also an **in-session + headless
research / orchestration assistant** for autonomous LW development:

- Gemini reads the repo + answers Claude's questions by writing/updating files;
  Claude reads them. File-based Q/A channel.
- Proposed channel: `gemini_io/` (gitignored) - `ask_<id>.md` (Claude -> Gemini)
  + `answer_<id>.md` (Gemini -> Claude). Plus the nightly
  `docs/EXTERNAL_REVIEW_<date>.md`.
- Used in normal sessions AND headless-upgrade runs for find/research/
  orchestrate tasks. Still read-only - Gemini never writes source or commits.

### AHK self-drive primitive (PORTED 2026-07-16: ops/loop/claude_gui_bridge.ahk)

An AutoHotkey script that focuses the target Claude window, types the
directive lines, and presses Enter - so a headless loop can self-clear and
self-continue between tasks. Ported from the RC ancestor under the
multi-project collision contract (RC commit 81636382): live targeting is
PID-ONLY via `control\target_pid.txt` (no title fallback; bridge aborts
without a pid), the launcher pid-binds to exactly ONE `claude` window whose
title equals config `claude_window_title` ("Image"), each repo's launcher
kills only its own cmdline-scoped `AutoHotkey64` instances, and RC's launcher
self-defers while any LegionWallpaper bridge is alive (LW may start first).
Dry-run mode types into a Notepad window titled `LW-LOOP-DRYRUN`; fired lines
log to `control\ahk_bridge.log`; kill = `control\STOP`.
