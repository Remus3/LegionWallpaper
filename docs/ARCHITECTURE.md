# Legion Wallpaper - Architecture

_Living document. Update after topology or module changes. See `docs/_archive/` for dated design docs._

> **PRODUCT TBD.** The wallpaper app itself is not yet defined - no engine, no
> module map, no endpoints, no ports. This stub records the INHERITED runtime
> conventions the product will adopt the moment it has a running process. Do
> not invent product architecture here; that starts with the ADR-002 scope
> decision (see `ROADMAP.md`).

---

## Machine

| Machine | Role |
|---|---|
| **Legion** | Single-machine deployment (Windows 10 Pro). Repo at `C:\LegionWallpaper\`. Canonical Python: `C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe` (`pythonw.exe` for daemons/hooks). |

Everything is 1-PC on Legion. No cross-machine topology exists or is planned
until an ADR says otherwise.

---

## Inherited runtime conventions (the shape the product will adopt)

These are process conventions carried over 1:1; none of them are running yet
because there is no product process to run.

- **Supervisor pattern.** A small supervisor daemon (`ops/lw_supervisor.py` -
  TBD, not yet written) owns the main product process lifecycle: PID lock,
  crash restart, and the restart trigger. Registered at logon as the
  `LW-Supervisor` scheduled task ONCE the product exists (see
  `docs/OPERATIONS.md` - NOT YET REGISTERED).
- **`restart_trigger.txt`** at the repo root. Writing `restart` to it asks the
  supervisor to bounce the main process within ~5s. This is THE normal restart
  path - never `Stop-Process` (hangs MCP pipes); `taskkill /F /PID` only as the
  hard fallback.
- **`ops/runtime/health.json`.** The main process heartbeats a small JSON:
  at minimum `pid`, `alive`, `last_reload_ok`, plus mode/status fields as the
  product defines them. Every restart is VERIFIED by reading it back (new pid,
  `alive=true`, `last_reload_ok=true`).
- **`logs/YYYY-MM-DD.log`.** One log file per day, 30-day retention, UTF-8.
- **Atomic writes only.** `tmp.write_text(...); tmp.replace(target)` for every
  runtime-consumed file - anything may be read mid-write.
- **`py_compile` before restart.** Syntax errors crash silently under
  `pythonw.exe`; compile every modified .py before triggering a restart.

## Module map

TBD - product not yet defined. This section gets the real tree after the first
runnable slice ships; until then see `docs/AGENTS.md` for the inherited
agent-framework PATTERN (also unwired).
