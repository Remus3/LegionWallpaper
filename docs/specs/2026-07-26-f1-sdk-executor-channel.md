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

Baseline at build time: tasks clean (36 non-Microsoft, none window-capable, after the
2026-07-26 RC-GeminiAudit / RC-WeeklyHygiene S4U fix); gui bridge n/a (channel key not yet
present, pre-F1); **13 subprocess sites missing the flag** across `tools/drift_guard.py`,
`tools/repair_mojibake.py`, `tools/repo_insights.py`, `tools/strip_em_dashes.py`,
`tools/strip_smart_quotes.py`, `tools/truth_gate.py` and `ops/loop/claude_stub.py`. Those
are PRE-EXISTING and unrelated to F1; they are logged here as a known-dirty baseline, to be
cleared in a separate per-site sweep (a blanket mechanical edit is not appropriate - each
site needs a read to confirm the flag is correct for that call).

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

Each phase is one session, TDD, commit + push. No phase claims done without the stated
evidence run fresh.

**P1 - seam, no behavior change.** Extract `executor.py` with `AhkExecutor` as a verbatim
lift; controller calls `executor.run(...)`. `channel` defaults to `ahk`.
ACCEPT: full suite green; one dry run (`config.dry.json`, `claude_stub.py`) completes the
same number of cycles with byte-identical `control/` artifacts vs a pre-change run.

**P2 - SdkExecutor against the stub.** Fake `claude` shim on PATH that echoes a canned
result JSON. Covers: success, `is_error`, malformed stdout, timeout + taskkill, budget
exhaustion, schema-violating output.
ACCEPT: 6 new tests green; no live API spend.

**P3 - slots + mutexes.** `slots.py`, `winmutex.py`, `RUNNING.lock`, `run_id`.
ACCEPT: `tests/test_loop_concurrency.py` - N=8 threads against `max_slots=2` never exceed
2 concurrent holders; a lock whose pid is dead is reaped within one backoff; abandoned
mutex logs and proceeds; two controllers in one repo -> second exits nonzero.

**P4 - live single-repo run.** LW only, `channel: sdk`, `max_cycles: 2`, cheap directive
(docs Tier-0).
ACCEPT: 2 cycles complete with zero AHK process running (verify: no AutoHotkey in the
process list during the run); `total_cost_usd` recorded per cycle and within 10 percent of
the transcript-derived number computed as a one-off cross-check; both cycles commit + push.

**P5 - live concurrent run - THE acceptance test for this spec.** LW loop and RC loop
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
- **`bypassPermissions` is a genuine authority grant.** The executor writes, commits and
  pushes unattended - it already did via AHK, but the GUI at least had a human-visible
  window. Compensating control: `--max-budget-usd` per cycle, the pre-existing truth_gate
  and precommit_gate hooks (which run under `-p` too), and the same-sha / no-progress
  guards.
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
