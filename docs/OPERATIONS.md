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
scheduled tasks. Guard test: TBD - add `tests/test_bare_py_ban.py` once the
test suite exists.

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

HTTP health endpoints: TBD - product not yet defined (no ports exist).

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

Naming convention: every LW scheduled task is named `LW-*`. **NONE ARE
REGISTERED YET** - the standard roster below is the plan to arm LATER, each
gated on (a) the product having code + a test suite and (b) an explicit
operator directive. Do not register any of them speculatively.

| Task | Trigger | Context | Description | Status |
|---|---|---|---|---|
| `LW-Supervisor` | At logon | Administrator / HIGHEST | Runs `pythonw.exe ops/lw_supervisor.py` - owns the main process lifecycle, PID lock, restart trigger (supervisor script TBD) | NOT YET REGISTERED |
| `LW-GeminiAudit` | Daily | Administrator | Gemini read-only auditor pass over the repo (`tools/gemini_audit.ps1` - TBD) | NOT YET REGISTERED |
| `LW-WeeklyHygiene` | Weekly Sunday | Administrator | Unattended `/weekly-hygiene` pass via headless Claude (`tools/weekly_hygiene_run.ps1` - TBD) | NOT YET REGISTERED |
| `LW-CIWatchdog` | At startup + periodic (PT2M) | Administrator | Unattended headless-claude red-main CI auto-fixer; self-gates the merge on the ci-fix PR's OWN green CI; isolated worktree. Kill switch: create `ops\runtime\ci_watchdog\HALT` or `Disable-ScheduledTask LW-CIWatchdog` | NOT YET REGISTERED |

Example registration commands (for LATER - do not run today; scripts referenced
do not exist yet):

```
REM NOT YET REGISTERED - example only
schtasks /Create /TN "LW-Supervisor" /SC ONLOGON /RL HIGHEST /F ^
  /TR "\"C:\Users\Administrator\AppData\Local\Programs\Python\Python314\pythonw.exe\" C:\LegionWallpaper\ops\lw_supervisor.py"

REM NOT YET REGISTERED - example only
schtasks /Create /TN "LW-GeminiAudit" /SC DAILY /ST 03:30 /F ^
  /TR "powershell -NoProfile -ExecutionPolicy Bypass -File C:\LegionWallpaper\tools\gemini_audit.ps1"

REM NOT YET REGISTERED - example only
schtasks /Create /TN "LW-WeeklyHygiene" /SC WEEKLY /D SUN /ST 04:17 /F ^
  /TR "powershell -NoProfile -ExecutionPolicy Bypass -File C:\LegionWallpaper\tools\weekly_hygiene_run.ps1"

REM NOT YET REGISTERED - example only
schtasks /Create /TN "LW-CIWatchdog" /SC ONSTART /RI 2 /F ^
  /TR "\"C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe\" C:\LegionWallpaper\tools\ci_watchdog.py"
```

Check state: `Get-ScheduledTask -TaskName "LW-*" | Select TaskName, State`
(expected today: no results).

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
