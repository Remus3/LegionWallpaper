# Legion Wallpaper - Operations Reference

_Living document. Full ops command set for Legion sessions. Product TBD - the
generic conventions below are live now; product-specific commands land here as
the product ships._

---

## Python interpreter

Canonical interpreter (the ONLY one to use for LW work):

```
C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe
```

Bare `py` is BANNED on every Legion runnable/doc surface: PEP 514 resolves it
to a pymanager runtime (`AppData\Local\Python\pythoncore-3.14-64`) with ZERO
third-party packages, so a launcher-spelled pytest run silently executes a
pytest-less interpreter (a past incident on this machine zeroed a test suite).
Always spell the canonical absolute path (quoted) in commands, hooks, docs, and
scheduled tasks. Guard test: not yet written - add `tests/test_bare_py_ban.py`
(the test suite exists as of 2026-07-17; the guard file is still absent).

Use `pythonw.exe` for background daemons and hooks (no console window). Use
`python.exe` for scripts that need stdout.

---

## Quick health check

```powershell
# Full health JSON (TBD until a producer exists - see docs/ARCHITECTURE.md)
python -c "import json; print(json.dumps(json.loads(open(r'ops/runtime/health.json').read()), indent=2))"

# Log tail (today)
python -c "import time; from pathlib import Path; print(Path('logs/'+time.strftime('%Y-%m-%d')+'.log').read_text(encoding='utf-8',errors='replace')[-4000:])"
```

HTTP health endpoints: the two read-only servers each expose `/api/health` -
run dashboard on `127.0.0.1:8900` (`tools/lw_rundash.py`) and pipeline monitor
on `127.0.0.1:8901` (`tools/lw_monitor.py`). Both are started on demand, not
supervised; the product's own health producer is still TBD.

---

## Restart LW

**Normal restart** (supervisor picks up within ~5s - supervisor is TBD, not yet
written or registered):

```
echo restart > restart_trigger.txt
```

**Verify:** read `ops/runtime/health.json` - confirm new `pid`, `alive=true`,
`last_reload_ok=true`. A restart without this read-back does not count as
verified.

**Hard fallback** (if the supervisor is also dead):

```powershell
taskkill /F /PID <pid>        # never Stop-Process - hangs MCP pipe
schtasks /Run /TN "LW-Supervisor"   # NOT YET REGISTERED - see roster below
```

**Do NOT use** `Stop-Process` or a restart .bat from an interactive shell - use
`taskkill /F /PID`.

---

## Scheduled tasks (Legion)

Naming convention: every LW scheduled task is named `LW-*`. **Three are
registered**: `LW-Wallpaper` (2026-07-18), `LW-WeeklyHygiene` and
`LW-CIWatchdog` (both 2026-08-02). Only `LW-Supervisor` is unarmed, and it is
blocked on a MISSING SCRIPT rather than on operator approval - the roster review
of 2026-08-02 settled the approvals. Do not register a row whose target file
does not exist: an armed task pointing at a missing script fails on every
trigger, silently, forever.

| Task | Trigger | Context | Description | Status |
|---|---|---|---|---|
| `LW-Wallpaper` | At logon + time trigger, repeat PT3M | Administrator / LeastPrivilege | Runs `pythonw.exe tools/lw_wallpaper_rotate.py tick` - desktop wallpaper deck rotator, every image once before any repeat (LEDGER 34) | REGISTERED 2026-07-18 |
| `LW-Supervisor` | At logon | Administrator / HIGHEST | Runs `pythonw.exe ops/lw_supervisor.py` - owns the main process lifecycle, PID lock, restart trigger (supervisor script TBD) | BLOCKED ON SCRIPT - `ops/lw_supervisor.py` does not exist, so this is gated on the file, not on operator approval; registering it today arms a task that fails every logon |
| `LW-GeminiAudit` | Daily | Administrator | Gemini read-only auditor pass over the repo (`tools/gemini_audit.ps1` - exists) | **DROPPED 2026-08-02 - do not register.** `gemini-removal` retired the vendor this task exists to run; the loop's auditor role now runs read-only Claude. The script stays on disk as the rollback path, so this row stays here as a record rather than being deleted. |
| `LW-WeeklyHygiene` | Weekly Sunday 04:17 | Administrator | Unattended `/weekly-hygiene` pass via headless Claude (`tools/weekly_hygiene_run.ps1`) | **REGISTERED 2026-08-02** (operator direction). Verified `Ready`. Its `-Model` default was `claude-sonnet-4-6`, not a current model id - fixed to `claude-sonnet-5` in the same change, because arming a weekly task nobody watches with a stale id fails silently every Sunday. |
| `LW-CIWatchdog` | Boot + PT2M repeat (XML) | Administrator / LeastPrivilege | `tools/ci_watchdog.py` - unattended headless-claude red-main CI auto-fixer, one pass per invocation. Acts ONLY on a settled `failure` (queued/pending/unavailable/not-evaluated all wait); 2 attempts per failing sha; isolated worktree; self-gates the merge on the fix branch's OWN green CI at its OWN head sha. Kill switch: create `ops\runtime\ci_watchdog\HALT` (an empty file counts) or `Disable-ScheduledTask LW-CIWatchdog` | **REGISTERED 2026-08-02** (operator direction). Verified `Ready`. |

Registration commands. The `LW-WeeklyHygiene` line is the one that was actually
RUN (2026-08-02); the other two are held until their target script exists, and
`LW-GeminiAudit` is retired outright.

```
REM REGISTERED 2026-08-02 - this exact command was run
schtasks /Create /TN "LW-WeeklyHygiene" /SC WEEKLY /D SUN /ST 04:17 /F ^
  /TR "powershell -NoProfile -ExecutionPolicy Bypass -File C:\LegionWallpaper\tools\weekly_hygiene_run.ps1"

REM BLOCKED ON SCRIPT - ops\lw_supervisor.py does not exist
schtasks /Create /TN "LW-Supervisor" /SC ONLOGON /RL HIGHEST /F ^
  /TR "\"C:\Users\Administrator\AppData\Local\Programs\Python\Python314\pythonw.exe\" C:\LegionWallpaper\ops\lw_supervisor.py"

REM REGISTERED 2026-08-02 - by its OWN tool, not by schtasks flags.
REM A bare `/SC ONSTART /RI 2` is REJECTED outright ("/RI ... not applicable for
REM the scheduled types: ONSTART, ONLOGON, ONIDLE, ONEVENT"), the same wall
REM lw_wallpaper_rotate hit, so the trigger goes through XML:
"C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe" C:\LegionWallpaper\tools\ci_watchdog.py --install
"C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe" C:\LegionWallpaper\tools\ci_watchdog.py --uninstall

REM Inspect without acting (prints CI state, stored attempts, halt, decision):
"C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe" C:\LegionWallpaper\tools\ci_watchdog.py --status

REM RETIRED 2026-08-02 by gemini-removal - do NOT run this
REM schtasks /Create /TN "LW-GeminiAudit" /SC DAILY /ST 03:30 /F ^
REM   /TR "powershell -NoProfile -ExecutionPolicy Bypass -File C:\LegionWallpaper\tools\gemini_audit.ps1"
```

Unregister (the kill path for anything armed above):

```
schtasks /Delete /TN "LW-WeeklyHygiene" /F
```

`LW-Wallpaper` is registered by its own tool, not by hand:

```
"C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe" C:\LegionWallpaper\tools\lw_wallpaper_rotate.py install
"C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe" C:\LegionWallpaper\tools\lw_wallpaper_rotate.py uninstall
```

It writes a Task Scheduler XML (`ops/runtime/lw_wallpaper_task.xml`) and
feeds it to `schtasks /Create /XML`, because bare flags cannot express the
trigger - `/RI` is rejected for `/SC ONLOGON`. Note that a `LogonTrigger`'s
`Repetition` only starts when that trigger FIRES, so the XML also carries a
`TimeTrigger` at install time; a logon-only task registers `Ready` with
`Next Run Time: N/A` and sits idle until the next logon. This applies to any
future `LW-*` task that wants a repeat from the moment it is armed.

**Exactly ONE trigger in a task may carry a `Repetition`.** Task Scheduler
runs every repeating trigger's pattern independently, so a second one halves
the real interval. Measured 2026-08-13: `LW-Wallpaper` carried `PT3M` on both
its `LogonTrigger` and its `TimeTrigger` and ticked every 1.54 min, wrapping a
468 image deck in ~12 h instead of ~23 h; `LW-CIWatchdog` had the same shape
at `PT2M`. The `TimeTrigger` owns the cadence (it resumes its pattern across
reboots on its own); the logon/boot trigger stays a one-shot kick. Audit with:

```
Get-ScheduledTask -TaskName 'LW-*' | ForEach-Object { $n=$_.TaskName; $x=Export-ScheduledTask -TaskName $n; "$n repetitions=$(([regex]::Matches($x,'<Repetition>')).Count)" }
```

Check state: `Get-ScheduledTask -TaskName "LW-*" | Select TaskName, State`
(expected today: `LW-Wallpaper`, `LW-WeeklyHygiene` and `LW-CIWatchdog` all
Ready, nothing else).

---

## Pre-flight before any restart

```powershell
# 1. py_compile all modified files
python -m py_compile <file.py>

# 2. Atomic write (don't hand-roll):
#    tmp.write_text(...); tmp.replace(target)

# 3. Batch related runtime edits, then restart ONCE
```

---

## Useful commands

```powershell
# Scheduled-task state (LW roster)
Get-ScheduledTask -TaskName "LW-*" | Select TaskName, State

# Hard kill (fallback only)
taskkill /F /PID <pid>

# Compile check before any restart
"C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe" -m py_compile <file.py>
```

---

## Useful file locations

| Path | What it is |
|---|---|
| `ops/runtime/health.json` | Live PID + alive flag + last_reload_ok (TBD - no producer yet) |
| `restart_trigger.txt` | Supervisor restart trigger (repo root) |
| `logs/YYYY-MM-DD.log` | Daily log (30-day retention) |
| `docs/LEDGER.md` | Append-only per-item completion ledger |
| `WAKEUP_NOTES.md` | Session hand-off notes (newest-first) |
| `docs/adr/` | Decision records |
| `moon_sync_inbox/` | Cross-repo channel with Riot Commander (gitignored on BOTH sides). RC's mirror is `C:\Riot Commander\moon_sync_inbox\`. Read it at session start whenever the shared `ops/loop/slots.py` / `winmutex.py` are in play - a change to either is a joint act, never unilateral. Both sessions independently invented a channel on 2026-07-26 before finding the other's; this table entry exists so the next one does not. |

## Machine state - PowerShell 7 (standing reference)

_Relocated verbatim from WAKEUP_NOTES.md 2026-07-27. It is durable machine
reference, not session history, and WAKEUP is pruned every few sessions - a
standing reference living there gets archived by design._

- **PowerShell 7 - INSTALLED BY RIOT COMMANDER 2026-07-26. LW migration = NO-OP.**
  Authority doc: `C:\Users\Administrator\Desktop\POWERSHELL_7_MIGRATION.md` (RC,
  machine-wide). Read it before touching any call site; do not re-derive.
  - Live state verified 2026-07-26: `C:\Program Files\PowerShell\7\pwsh.exe` =
    **7.6.4 Core**, MSI machine-scope, on machine PATH. `powershell.exe` is
    untouched 5.1 and stays forever. Side-by-side; nothing auto-switched.
  - MSI not winget: the winget manifest ships only an MSIX, whose exe path carries
    the version (breaks pinned scheduled tasks on upgrade) and whose stable-looking
    launcher is a per-user app-execution alias. Do NOT "fix" this with winget.
  - **LW has ZERO migration work.** Probed 2026-07-26: `LW-Wallpaper` executes
    `pythonw.exe` (not `powershell.exe`), so RC doc sec 4a does not apply. No LW
    `.vbs`/`.bat`/`.cmd` shim names powershell. The only authored call sites are
    `ops/loop/loop_controller.py`, `tools/precommit_gate.py`, `tools/truth_gate.py`,
    `tools/weekly_hygiene_run.ps1` - all agent/hook-invoked, none pinned to a shell
    binary that needs changing. Nothing to switch; revisit only if LW registers a
    powershell-executing task.
  - **Agent sessions stay on 5.1** (RC doc sec 4c): Claude Code's PowerShell tool
    invokes `powershell.exe` and no setting selects the binary. So KEEP WRITING
    5.1-COMPATIBLE POWERSHELL - no `&&`/`||`, no ternary, no `??`. Escape hatch if
    ever needed: `& 'C:\Program Files\PowerShell\7\pwsh.exe' -NoProfile -File <s>`.
  - **The no-em-dash ASCII rule STANDS - do not relax it.** RC measured that PS7
    parses a no-BOM UTF-8 `.ps1` containing an em-dash with 0 errors, so that one
    5.1 failure mode is gone under pwsh. It remains LIVE anywhere `powershell.exe`
    is named explicitly, it is an independent operator style rule, and it is
    mechanically gated by `tools/precommit_gate.py`. PS7 removes a failure mode,
    not the rule.
