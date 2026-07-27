# F1 - SDK executor channel (retire the AHK GUI bridge), concurrency-safe

Status: SPEC (not built). Author date 2026-07-26.
Supersedes the FUTURE-lane sketch F1 in `C:\Riot Commander\docs\LOOP_IMPROVEMENTS_2026-06-27.md`.
Sibling precedent: `C:\Riot Commander\ops\loop\adjudicator.py` (LEDGER 993) did exactly this
refactor for the BRAIN side. This spec does it for the EXECUTOR side, and adds the
machine-wide concurrency contract the adjudicator swap never needed.

## 1. Problem

The loop has two channels to an LLM. Only one is still GUI-bound.

| Channel | Role | Today | GUI-bound |
|---|---|---|---|
| Adjudicator | director + auditor (read-only brain) | gemini CLI / claude CLI, pluggable (RC only) | no |
| Executor | the Claude that writes code | AHK types into a live Claude window | YES |

`ops/loop/claude_gui_bridge.ahk` types the directive into the window named by
`config.json: claude_window_title` ("Image"). That window title is a MACHINE-WIDE
SINGLETON. Two loops cannot run at once: both bridges would type into whichever window
matched, interleaving two directives into one session. Concurrency is not merely untested
here, it is structurally impossible.

Secondary costs of the AHK channel, all documented in the bridge itself:
- the `/clear` -> `clear/` reorder race (`claude_gui_bridge.ahk:58-67`)
- `LINE_PAUSE:=1500` and `Sleep 400/350` pacing hacks, i.e. a typing deadline
- `loop_controller.py:576` `wait_gone(gemini.ready, 120)` - a 120s "did AHK type it" guard
  that exists only because typing can silently fail
- cost is scraped out of transcript .jsonl files (`meter()` / `session_files()`,
  `loop_controller.py:436-470`) because the channel returns no receipt
- completion is a side-channel file the executor must remember to write
  (`done_sentinel.py` -> `control/claude.done`)

## 2. Verified ground truth (probed 2026-07-26, this machine, not assumed)

`claude --help` on the installed CLI carries every flag this spec needs:
`-p/--print`, `--output-format json`, `--input-format text`, `--session-id <uuid>`,
`-r/--resume [value]`, `--fork-session`, `--permission-mode {acceptEdits,auto,
bypassPermissions,manual,dontAsk,plan}`, `--json-schema <schema>`, `--model`,
`--max-budget-usd <amount>`, `--add-dir`, `--settings`, `--setting-sources`,
`--strict-mcp-config`, `--dangerously-skip-permissions`.

A live one-shot call (haiku, `--permission-mode plan`, schema supplied on stdin) returned:

```
{"type":"result","subtype":"success","is_error":false,"num_turns":3,
 "session_id":"8fb2990b-...","total_cost_usd":0.073131,
 "result":"{\"cycle\":7,...}",
 "structured_output":{"cycle":7,"tests_pass":12,"regressions":false},
 "usage":{...},"modelUsage":{...},"permission_denials":[],"stop_reason":"tool_use"}
```

Three consequences, each now evidence-backed rather than hoped for:
1. `total_cost_usd` is returned per call -> the transcript-scraping meter is retired.
2. `structured_output` is schema-validated by the CLI -> `done_sentinel.py` and the
   `claude.done` file handshake are retired.
3. `session_id` is returned -> multi-cycle continuity via `--resume` is available when
   wanted, and a fresh uuid per cycle reproduces `/clear` semantics exactly.

Also confirmed from `--bare` help text: "Skills still resolve via /skill-name", so the
existing directive opener (`/gemini-headless-upgrade and Read ops/loop/control/directive.md
...`) keeps working unchanged in `-p` mode. No prompt rewrite is required.

## 3. Design - one seam, two backends

Mirror `adjudicator.py` exactly, because that refactor is already proven in production.

New `ops/loop/executor.py`:

```
class DoneRecord:  # what the controller needs back from one cycle
    cycle: int
    sha: str
    tests_pass: str
    regressions: bool
    summary: str
    cost_usd: float        # 0.0 for the ahk backend (unknown at call time)
    session_id: str | None
    error: str | None      # None on success

class Executor(Protocol):
    name: str
    def run(self, cycle: int, directive_body: str, deadline_ts: float) -> DoneRecord | None
```

- `AhkExecutor` - lifts `loop_controller.py:560-601` VERBATIM: write `gemini.ready`,
  `wait_gone` for the typed signal, `wait_for` `claude.done`, read + unlink it, call
  `meter()`. Byte-preserving lift, exactly as `GeminiAdjudicator` lifted the PowerShell
  invocation. No behavior change on this path.
- `SdkExecutor` - builds argv, pipes the directive on stdin, parses one JSON result.

`SdkExecutor` argv:

```
claude -p
  --output-format json
  --input-format text
  --model <cfg.executor_model>
  --permission-mode bypassPermissions
  --json-schema <DONE_SCHEMA>
  --max-budget-usd <cfg.cycle_budget_usd>
  --add-dir <repo_root>
  [--session-id <uuid4>]         # when clear_each_cycle: true (fresh context per cycle)
  [--resume <prior session_id>]  # when clear_each_cycle: false (continuity)
```

- prompt body on STDIN, never argv (no command-line length limit, no quoting or newline
  mangling - the whole class of AHK failure disappears)
- `subprocess.run(..., input=body, capture_output=True, timeout=deadline-now,
  creationflags=CREATE_NO_WINDOW)` - the no-console-flash rule applies to every subprocess
- on `TimeoutExpired`: `taskkill /F /T /PID <pid>` (NEVER `Stop-Process`, CLAUDE.md hard
  rule), return `DoneRecord(error="timeout")`
- `is_error: true` or unparseable stdout -> `error` set, cycle recorded as failed; the
  controller's existing N3 semantics (un-auditable cycle is not a hard stop) apply

`DONE_SCHEMA` (replaces `done_sentinel.py` on this path):

```json
{"type":"object",
 "properties":{"sha":{"type":"string"},"tests_pass":{"type":"string"},
               "regressions":{"type":"boolean"},"summary":{"type":"string"}},
 "required":["sha","tests_pass","regressions","summary"]}
```

The directive's FINAL STEP text changes from "run done_sentinel.py" to "return the JSON
object required by the schema". `sha` is still verified controller-side against a fresh
`git rev-parse HEAD` - the same-sha / no-progress guards stay exactly as they are, because
a self-reported sha is not evidence.

Config knob, alongside the existing adjudicator keys:

```json
"channel": "ahk",
"executor_model": "claude-opus-5",
"cycle_budget_usd": 25.0,
"max_concurrent_lanes": 2,
"_channel_note": "ahk = legacy GUI bridge (single-instance, machine-wide). sdk = headless claude -p (concurrent-safe). Flip to ahk to roll back."
```

Default stays `ahk` until phase 4 acceptance passes. Rollback is one key.

## 4. Concurrency contract - LW and RC loops running at the same time

This is a hard requirement, not a nice-to-have. Enumerate every shared resource and either
prove it is already namespaced or add a governor. Anything not on this list is a bug in
the list.

| Resource | Shared today | Under `channel: sdk` |
|---|---|---|
| Claude GUI window title | YES - the blocker | GONE. No window exists. |
| `control_dir` handshake files | no - `<repo>\ops\loop\control` | unchanged, disjoint |
| CLI session store | no - `~\.claude\projects\<repo-slug>` | disjoint; plus per-cycle uuid |
| Transcript .jsonl metering | per-repo dir, but mtime-races if two loops write | RETIRED - cost from the result JSON |
| git index / working tree | no - separate repos | unchanged |
| Worktrees | RC hardcodes `C:\rc-worktrees` | `<base>\<run_id>\<slice>` per run |
| Gemini CLI quota | YES - one metered account | serialize via named mutex (below) |
| Anthropic rate limit | YES - one account | slot governor (below) |
| GPU (LW upscale / cleaning CUDA) | YES - one 5070 | named mutex `Global\LW_GPU` |
| Scheduled tasks spawning CLIs | YES - RC-GeminiAudit 03:00, RC-WeeklyHygiene Sun 04:17 | take a slot like any lane |
| Ports | no - RC 8893/8888, LW none | unchanged |

### 4a. Slot governor (`ops/loop/slots.py`, shared implementation, identical file in both repos)

A machine-wide token bucket in `C:\ProgramData\lw-loop\slots\`. Not per-repo - the point is
to bound TOTAL concurrent executor calls on the Legion box across every caller.

- acquire: try `os.open(slots/<i>.lock, O_CREAT|O_EXCL|O_WRONLY)` for `i` in
  `range(max_slots)`; write `{pid, repo, run_id, cycle, ts}`; first success wins
- stale reap: if a lock's `ts` is older than `cycle_deadline_sec * 2` OR its `pid` is not
  alive (`OpenProcess` probe, not `tasklist` scraping), unlink and retry that index
- release: unlink in a `finally`, always
- block with jittered backoff (`2s + rand(0,2s)`) so two loops do not lockstep
- `max_slots` = `max(cfg.max_concurrent_lanes over callers)`, default 2

Held ONLY around the `claude -p` call itself, never around git or the adjudicator, so a
long merge in one repo does not starve the other.

### 4b. Named mutexes for the two genuinely exclusive resources

`ops/loop/winmutex.py` - thin `CreateMutexW` / `WaitForSingleObject` wrapper via ctypes.

- `Global\LWRC_GEMINI` - held around each adjudicator call. Gemini is one metered account;
  two concurrent director calls burn quota in parallel and can trip RESOURCE_EXHAUSTED,
  which the failover logic would then misread as real exhaustion and stickily swap the
  backend for the rest of the run. Serializing is cheap (director calls are seconds).
- `Global\LW_GPU` - held by any directive step that touches CUDA (LW upscale, cleaning,
  lw-gen). Acquired by the tool, not the loop, so manual runs are protected too.

Abandoned-mutex (`WAIT_ABANDONED`) is treated as acquired-with-warning and logged; a
crashed holder must not deadlock the other repo.

### 4c. Run namespacing

`run_id = uuid4().hex[:8]`, minted at controller start, written to `control/run_id.txt`,
and threaded into: controller log lines, worktree paths, slice branch names
(`loop/<repo>-<run_id>-<slice>`), report filenames, and every slot/mutex payload. Two
concurrent runs in the SAME repo (not a goal, but must not corrupt) then collide only on
`control_dir`, which is guarded by a single `control/RUNNING.lock` holding pid + run_id;
a second controller in the same repo exits with a clear message rather than interleaving.

## 4d. Window-popup guard (SessionStart hook) - BUILT 2026-07-26

"No GUI" is the premise of this whole migration, so it needs a standing detector rather
than a one-time cleanup. `tools/lw_window_guard.py` runs as a SessionStart hook
(`.claude/settings.json`, timeout 30) and prints its findings into session context.

Three checks, matching the three ways the no-console-flash rule regresses:

- **A. Scheduled tasks.** Risk = `Logon Mode: Interactive only` (the operator's session,
  where a window can appear) AND a console-host binary AND no hidden marker. Calibrated
  against live `schtasks /query /fo csv /v` output on 2026-07-26: S4U and ServiceAccount
  tasks report `Interactive/Background` and run in session 0, where no window is possible.
  The console-binary set is an ALLOWLIST (python.exe, powershell.exe, pwsh, cmd, cscript,
  node, git, claude.cmd, npm.cmd), so an unknown `.exe` is assumed to be a GUI app and the
  guard does not cry wolf on MSIAfterburner or StartIsBack.
- **B. Subprocess call sites.** Any `subprocess.run/Popen/call/check_output/check_call` in
  `tools/` or `ops/` without `creationflags=CREATE_NO_WINDOW`. Under a `pythonw.exe`
  parent (every hook and every scheduled task here) a console child allocates its OWN
  window, so a missing flag is a real flash, not a theoretical one.
- **C. GUI-bridge drift.** An AutoHotkey process alive while `config.json` says
  `channel: sdk`. Under the headless channel no bridge should exist at all; one that is
  still running means a stale launcher survived the migration and may be typing into
  whatever window currently matches.

Read-only, exit 0 always - a guard that can block a session start is worse than the drift
it watches. It reports; the operator or a directed session decides.

This makes phase-5 acceptance condition 1 mechanically checkable instead of a claim: a
concurrent LW+RC run is only clean if the guard reports zero window-capable tasks and no
live bridge on both machines' session starts during the run.

An EXPECTED_INTERACTIVE allowlist carries tasks that must stay in the operator's session
because they touch per-session Win32 surfaces that do not exist in session 0. Seeded from
RC's own S4U sweep (2026-07-26: 13 tasks flipped, 3 deliberately held) - `RC-HotkeyListener`
(RegisterHotKey + overlay), `RC-LiveFlipWatcher` (toasts), `RC-Supervisor` (Win32 +
overlay). Each row carries its reason; a row without one is drift wearing a costume.
Measured nuance worth keeping: on this box all three already run `pythonw.exe`, which is
not in the console-binary allowlist, so they never trip check A in the first place. The
allowlist is therefore currently INERT and purely defensive - it earns its keep only if one
of those tasks is ever re-registered against `python.exe`.

Baseline: tasks clean (36 non-Microsoft, none unexpectedly window-capable, after the
2026-07-26 RC-GeminiAudit / RC-WeeklyHygiene S4U fix); gui bridge n/a (channel key not yet
present, pre-F1); subprocess sites **CLEARED 2026-07-26** - all 13 (`tools/drift_guard.py`
x3, `tools/repair_mojibake.py`, `tools/repo_insights.py`, `tools/strip_em_dashes.py`,
`tools/strip_smart_quotes.py`, `tools/truth_gate.py` x4, `ops/loop/claude_stub.py`,
`ops/loop/done_sentinel.py`) now pass `creationflags=NO_WINDOW`. Every site was read before
editing rather than swept mechanically; all 13 turned out to be capture-only spawns (git,
gh, pytest) where suppressing the console is unambiguously correct. The `shell=True` suite
run in `truth_gate.py` takes the flag on its `cmd.exe`. Guard now reports two clean lines.

## 4e. The bootstrap gap: a tracked hooks dir is NOT a cloned gate

`core.hooksPath` is LOCAL config and is NOT cloned. VERIFIED empirically 2026-07-26 by
cloning this repo: the clone has `.githooks/pre-commit` and `.githooks/commit-msg` on disk
and `core.hooksPath` UNSET, so git uses `.git/hooks` (empty) and the tracked gate is inert.
Tracking the hook bodies fixes reviewability and drift, but buys ZERO enforcement until
someone runs the installer. This is a third false-green on top of the two in section 4d -
the hooks are present, correct, and readable in the tree, and they do not run.

Three runners, because a check nobody executes is not a control:
- `tools/drift_guard.py` -> `check_git_hooks()` (per-session, breach not note)
- SessionStart hook -> `install_git_hooks.py --check` (surfaces on a fresh clone at the
  first session rather than at the first `/done`)
- `loop_controller.main()` -> `executor.gate_inactive_reason(ROOT)`, which STOPS the run.
  This is the one that matters: an unattended headless run on a fresh clone would
  otherwise commit and push with no glyph / ruff / trailer gate at all, and nobody reads a
  session-start report during an unattended run. Failing loud beats degrading quietly
  exactly here. It stays silent for a tree with no installer, so it never invents a
  blocker for a repo that never had this tooling.

## 5. What gets deleted, and when

Nothing is deleted in the same change that adds the seam. Deletion is phase 5, after two
green live runs on `channel: sdk`:

- `done_sentinel.py` - keep while `channel: ahk` is reachable; it is the ahk path's only
  completion signal
- `meter()` / `session_files()` / `_price()` / `price_per_mtok` - same, ahk-only after this
- `claude_gui_bridge.ahk`, `claude_window_title`, the 120s typed-signal guard, the
  `stall_recovery_directive` re-type branch (`loop_controller.py:588-596`) - all ahk-only
- `claude_stub.py` stays forever: it is the dry-run test double for BOTH channels

## 6. Build phases + acceptance

**P0 - move precommit_gate into git hooks. DONE 2026-07-26, commit `b6b69e9`.**
Two hooks, not one: `pre-commit --git-hook` (staged content) and `commit-msg
--message-file $1` (the message). The split is measured, not stylistic - a probe hook
proved `.git/COMMIT_EDITMSG` does not exist yet at pre-commit time, so a lone pre-commit
would have silently dropped the commit-message glyph check.
Also folds in operator policy 2026-06-03 (never emit the Claude co-author trailer), which
was NOT being enforced: 84 of the last 200 LW commits carry it. commit-msg STRIPS rather
than blocks, since the trailer is appended by the tool rather than typed by the operator
and blocking would wedge an unattended run over a line no human wrote; only the
Claude/Anthropic trailer matches, a genuine human co-author survives.
`tools/install_git_hooks.py` is the committed source of truth (`.git/hooks/` is untracked)
and `drift_guard.check_git_hooks()` runs `--check` every session. The installer refuses to
overwrite a hook it does not own without `--force` - RC's `pre-commit` carries its Share
mirror sync.
ACCEPTED, run live rather than argued: with an em-dash staged, a nested `claude -p
--permission-mode bypassPermissions` told to commit exited 1 with history empty; the same
channel then had its Claude trailer stripped (committed body `docs: clean one`, no
trailer). drift_guard went BREACH (missing hooks) -> clean after install. 21 TDD tests
written failing first; suite `tests/` 598 passed / 11 skipped.

**P0b - clear the guard's known-dirty baseline** (13 subprocess sites). DONE 2026-07-26,
see section 4d. Ordered ahead of P1 deliberately: a guard that prints ~15 lines at every
session start is one people learn to ignore, which is worse than the drift it watches for.


Each phase is one session, TDD, commit + push. No phase claims done without the stated
evidence run fresh.

**P1 - seam, no behavior change. DONE 2026-07-26.** `ops/loop/executor.py` holds
`DoneRecord`, `directive_payload()` and `AhkExecutor` (verbatim lift); the controller binds
it via the same explicit-importlib pattern as the adjudicator and calls `EXEC.run(cycle,
body, src)`. `build()` defaults to `ahk` and rejects an unknown `channel` LOUDLY - a typo
must never silently fall back to the machine-wide singleton channel during a concurrent
run. The controller keeps everything both channels share (directive.md, cycle.txt,
budget.json, metering); the executor owns only the channel-specific handshake.
ACCEPTED: a hermetic 2-cycle dry run (fixed_directive, so director AND auditor are skipped
and no gemini call happens; pinned empty usage fixture so the meter is deterministic) run
BEFORE and AFTER the extraction produced **byte-identical `control/` artifacts** and a
timestamp-normalized **identical controller log**. Suite `tests/` 612 passed / 11 skipped
(14 new executor tests). ruff clean, drift_guard 0 breaches.
Note for P2: `DoneRecord.cost_usd` / `.session_id` are 0.0 / None on the AHK channel
because that channel returns no receipt - that is precisely what the sdk channel fills in,
and what retires the transcript meter.

**P2 - SdkExecutor against the stub. DONE 2026-07-26.** `SdkExecutor` + `sdk_prompt()` +
`DONE_SCHEMA` in `ops/loop/executor.py`; `build()` now accepts `channel: sdk`. Config gains
`channel` (default `ahk`), `executor_model`, `cycle_budget_usd`.
The shim is injected via `cfg["claude_cmd"]` as an argv LIST rather than placed on PATH -
no `.cmd`/`.ps1` resolution, no PATH mutation, and it doubles as the production affordance
for pinning an explicit interpreter.
Design points worth keeping: `sdk_prompt()` is deliberately NOT `directive_payload()` -
the CYCLE header and leading `/clear` are artifacts of typing into a live window, and a
`-p` call is already a fresh process. The FINAL STEP instruction swaps `done_sentinel.py`
for "return the JSON object required by the schema".
ACCEPT: 14 tests green, zero live API spend. Covers success (cost + session_id + fields),
argv contract, fresh-session-per-cycle vs `--resume` continuity, prompt shape, and every
failure mode: `is_error`, nonzero exit, malformed stdout, missing `structured_output`,
incomplete `structured_output`, budget exhaustion, and timeout + `taskkill /F /T`.
The failure cases carry the weight here: this channel runs unattended under
`bypassPermissions`, so every way a run can end without a usable result must degrade into
a RECORDED FAILED CYCLE, never a fabricated success. A made-up sha would silently defeat
the controller's same-sha no-progress guard, which is the loop's runaway backstop. Cost is
still recorded on failed cycles - the spend was real.
Suite `tests/` 629 passed / 11 skipped.

**P3 - slots + mutexes. DONE 2026-07-26.** `ops/loop/slots.py`, `ops/loop/winmutex.py`,
`RUNNING.lock`, `run_id`. Scopes, which are the whole point: the SLOT is held only around
`EXEC.run` (never around git or the adjudicator, so a long merge here cannot starve the
other repo); `GEMINI_MUTEX` wraps `gemini()` itself; `RUNNING.lock` is claimed once per
run at controller start.
Two guards that are easy to get backwards: everything fails OPEN except one. A stale slot
is reclaimed rather than respected forever, an abandoned mutex is acquired with a warning,
an un-creatable mutex proceeds unserialized with a loud log - a crashed process in one
repo must never deadlock the other. The single exception is `SlotTimeout`, which the
caller treats as a FAILED CYCLE and never as permission to run unslotted.
`pid_alive()` treats an unqueryable pid as ALIVE (one loop may run as a scheduled task and
the other interactively, so access-denied is not death) - it would rather wait than
double-book.
ACCEPT: `tests/test_loop_concurrency.py`, 17 tests. 8 threads against `max_slots=2` peak
at exactly 2 (sampled continuously, never 3); slot released on exception; timeout raises
instead of proceeding; dead-pid lock reaped and its slot reused; live holder NOT reaped;
corrupt lock falls back to mtime so it cannot wedge the bucket; mutex serializes 4 threads
to peak 1 and is reentrant for one thread; second controller in the same repo exits
nonzero; dead controller lock is reclaimed. Runtime 1.09s (a first cut took 121s by
letting a cycle run to its AHK-handshake timeout - the reclaim test now polls for the
claim and kills).
`drift_guard.check_shared_loop_files()` hashes both shared files against RC: NOTE while RC
has not adopted them, BREACH the moment both copies exist and differ.
Suite `tests/` 646 passed / 11 skipped. Live smoke confirms acquire/release around a real
cycle and an empty bucket afterwards.

**P4 - live single-repo run. DONE 2026-07-26** (run_id `b555f088`, commits `b1ad327` +
`e63a1b0`). LW only, `channel: sdk`, `max_cycles: 2`, `clear_each_cycle: true` (operator
call), sonnet for the smoke, Tier-0 doc directive appending one line per cycle to
`docs/_archive/2026-07-26-p4-sdk-smoke.md`.
PASSED: 2 cycles completed, zero AutoHotkey process on the box (confirmed before the run
and structurally impossible during it - the sdk channel never opens a window); each cycle
committed exactly ONE file, in scope, and pushed (local HEAD == origin/main); neither
commit carries a co-author trailer; per-cycle cost returned by the CLI ($0.6583, $0.4541,
total $1.1124); slot acquired and released around each cycle with an empty bucket
afterwards; zero gemini spend (fixed_directive skips director AND auditor).

FAILED AS WRITTEN, and the criterion was wrong, not the channel: "within 10 percent of the
transcript-derived number" treats the thing being RETIRED as the reference. Measured three
ways, the scraper cannot be reconciled to the CLI receipt at all:
- raw sum over transcript usage records: $1.2494 vs $0.6583 reported = **+90 percent**.
  Cause: the transcript repeats usage records per message id (8 ids repeated, 10 extra
  records; one id appears 3x with identical token counts), so the scraper multi-counts.
- deduped by message id: $0.5108 vs $0.6583 = **-22 percent**. It now UNDERCOUNTS, because
  it misses subagent transcripts and leans on a hand-maintained price table that has to be
  correct for every model alias.
- the run's own `claude_info` line read **$159.81**, because `meter()` auto-pinned the
  newest transcript in the project dir - which was the operator's interactive session, not
  the executor's. It billed the wrong conversation entirely.
`total_cost_usd` comes from the CLI itself and is the authority. AMENDED CRITERION for P5:
assert the per-cycle cost is present, positive, and plausibly bounded by
`cycle_budget_usd`; do NOT reconcile it against the scraper. This strengthens the case for
retiring `meter()` in phase 6 rather than weakening it - the cross-check's real result is
that the legacy meter was wrong in three independent ways.

**P5 - PASSED 2026-07-26.** LW run_id `87ca8ca0` (21:17:21-21:19:45, commits `646263d`,
`58896c5`) and RC run_id `e8353658` (21:17:41-21:19:22, commits `4f3ee42c`, `80197c40`),
both `channel: sdk`, 2 cycles each. Judged by `ops/loop/p5_probe.py judge`:

1. PASS - both runs completed, 4 completed-cycle lines each, zero unexpected stops.
2. PASS - worst slot wait 0s on both sides. The commit half of this condition is NOT
   covered by the judge and was checked by hand: each of the four commits touched exactly
   ONE file, each repo's own `docs/_archive/2026-07-26-p5-concurrent-smoke.md`. No commit
   in either repo touched the other's paths.
3. PASS - 125 samples at 2s, occupancy histogram {0: 57, 1: 27, 2: 41}, never 3.
   Critically, **41 samples caught BOTH repos holding a slot at once**, a measured
   simultaneity window of 21:17:22-21:19:14 (112 seconds), e.g. RC on `0.lock` while LW
   held `1.lock`. RC named this caveat before the verdict and was right to: zero
   slot-waits proves NOTHING about overlap, because with `max_slots=2` and one lane each
   neither repo ever has to wait whether or not the other is running. The sampler is the
   only thing that can distinguish real overlap from two runs that missed each other, and
   it is what turns conditions 3 and 4 from vacuous into evidence.
4. PASS - LW 2 gemini windows, RC 2, zero overlaps, zero UNSERIALIZED markers, ACQUIRED and
   RELEASED balanced on both sides.

THE STRONGEST SINGLE PIECE OF EVIDENCE is not the "no overlap" result, which a
non-contending run would also produce. It is that RC's mutex acquire timestamp is
**exactly** LW's release timestamp: LW held GEMINI_MUTEX 21:18:11-21:18:28, RC acquired at
21:18:28 and held to 21:18:43. RC was genuinely BLOCKED and got the mutex the instant LW
let go. The serialization was exercised under real contention, not merely unviolated.

Cost, under the P4-amended criterion (present, positive, bounded by `cycle_budget_usd`,
NOT reconciled against the scraper): LW $0.6476 + $0.6877, RC $0.6622 + $0.56; all four
well under the $10 per-cycle budget.
RC independently reproduced the P4 meter defect in the wild: its controller pinned
`2a46fcf7-...jsonl`, this operator's interactive session, not the executor's. On the sdk
channel that number gates nothing (`executor_usd` carries the CLI receipt), which is
further argument for deleting the pin in phase 6 rather than repairing it.

ORIGINAL SPEC TEXT for this phase: LW loop and RC loop
started within 60s of each other, both `channel: sdk`, 2 cycles each, disjoint Tier-0
doc scopes.
ACCEPT, all four required:
1. both runs reach cycle 2 and exit clean, no stop() from either
2. no commit in either repo touches the other repo's paths, and neither run's log shows a
   slot wait longer than `cycle_deadline_sec`
3. slot occupancy sampled every 5s never exceeds `max_slots`
4. adjudicator calls serialize - the two runs' gemini call windows, from the controller
   logs, never overlap

Then, and only then, phase 6 deletes the ahk-only code listed in section 5.

## 7. Risks and the honest tradeoffs

- **Cost per cycle rises with `clear_each_cycle: true`.** Every cycle is a cold session that
  re-reads CLAUDE.md + living docs (the probe above shows 33k cache-creation tokens for a
  trivial call). The AHK channel amortized that across one long-lived window. Mitigation:
  `--resume` when `clear_each_cycle: false`; measure both at P4 before choosing the
  default. This is a real regression on one axis and should not be papered over.
- **P0 - `bypassPermissions` SILENTLY REMOVES THE REPO'S OWN GATE.** An earlier draft of
  this section called it "a genuine authority grant" and assumed the precommit_gate hook
  "runs under `-p` too". RC measured that assumption on 2026-07-26 and it is FALSE.
  RC's method, and the discriminator that makes it unambiguous: control first - invoked
  `tools/precommit_gate.py` directly with an em-dash staged, exit 2 BLOCKED. Then a nested
  `claude -p --permission-mode bypassPermissions` told to `git commit`: the commit landed
  WITH the banned glyph, on main. The run printed "Running Share/ mirror sync
  (precommit-gated)...", which looks like the gate firing but is `.git/hooks/pre-commit` -
  a GIT hook, which runs regardless of Claude; `grep precommit_gate .git/hooks/pre-commit`
  returns 0 matches. So: git hooks ran, Claude PreToolUse hooks did not. RC reset the
  commit; tree clean at `f5ec4089`.
  RC explicitly did NOT eliminate one confound and neither should this spec: it cannot yet
  separate "bypassPermissions skips hooks" from "headless `-p` does not load project hooks
  at all" (its isolated temp-dir attempt was invalid - settings never loaded there in any
  mode - and was discarded). The actionable conclusion is robust under either reading: the
  SDK executor does not inherit the repo's PreToolUse gate.
  **LW is worse off than RC here.** RC at least had a `.git/hooks/pre-commit` doing the
  Share sync. LW has NO active git hooks at all (`.git/hooks/` holds only `.sample`
  files, verified 2026-07-26), and `precommit_gate.py` exists ONLY as a PreToolUse hook in
  `.claude/settings.json`. Under `channel: sdk` LW's glyph + ruff backstop would be
  entirely absent - unattended, no window, no operator, which is exactly when it is most
  needed.
  **Fix, and it is cheap because the same experiment already proved it:** move the gate
  into `.git/hooks/pre-commit`. Git hooks demonstrably survive `bypassPermissions`, which
  makes the gate channel-independent - AHK, SDK, a human at a terminal, or CI all get it.
  Keep the PreToolUse copy for the fast in-session signal; the git hook is the one that
  must be AUTHORITATIVE. Because `.git/hooks/` is not tracked by git, this needs a
  committed installer (`tools/install_git_hooks.py`) plus a drift_guard check asserting the
  installed hook matches, or it silently un-installs itself on every fresh clone.
  Remaining compensating controls once the gate is restored: `--max-budget-usd` per cycle,
  truth_gate, and the same-sha / no-progress guards.
- **Hooks and MCP load per call.** Each `claude -p` pays MCP server startup. If P4 shows
  the startup tax is material, add `--strict-mcp-config` with a lane-specific
  `--settings` file trimming MCP to what a loop cycle actually needs.
- **Slot governor is a new machine-wide dependency.** A bug there stalls both loops. It is
  therefore fail-open on reap (a stale lock is reclaimed, never respected forever) and its
  tests are phase-gated ahead of any live concurrent run.

## 8. Port order

Build in LW first (smaller loop, cheaper cycles, no live-game coupling), then port
`executor.py` + `slots.py` + `winmutex.py` to RC verbatim. `slots.py` and `winmutex.py`
MUST stay byte-identical across the two repos - they coordinate with each other through
`C:\ProgramData\lw-loop\`, so a divergence is a silent concurrency bug. Add a drift check
to the weekly hygiene pass comparing the two file hashes.

RC gets a bonus on arrival: its already-built `ops/loop/run_lane.ps1` +
`spawn_lanes.ps1` (headless `claude -p` in hidden windows, own worktree, proven on the
2026-07-16 night run) collapse into `SdkExecutor` calls, retiring two PowerShell scripts
whose transport this spec generalizes.
