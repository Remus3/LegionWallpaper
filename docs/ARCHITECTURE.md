# Legion Wallpaper - Architecture

_Living document. Update after topology or module changes. See `docs/_archive/` for dated design docs._

> **Product:** a staged, self-auditing image restoration pipeline (ADR-002).
> Folder/state scheme: ADR-003. Operational plan: `docs/RESTORATION_PLAN.md`.
> Research substrate: `docs/research/`.

---

## Machine

| Machine | Role |
|---|---|
| **Legion** | Single-machine deployment (Windows 10 Pro, RTX 5070 12GB Blackwell sm_120). Repo at `C:\LegionWallpaper\`. Canonical Python: `C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe` (`pythonw.exe` for daemons/hooks). ML work runs in Python 3.12 side-venvs with torch from the cu128 wheel index. |

Everything is 1-PC on Legion. No cross-machine topology exists or is planned
until an ADR says otherwise.

---

## Pipeline component map

```
images\                              pipeline root (ADR-003; content gitignored
                                     except .gitkeep skeleton)
  0.Originals\                       raw drops (files, no subfolders)
  1.First Pass Scratch\<slug>\       stage=first  (source recovery + single upscale)
  2.First Pass Done\<slug>\
  3.Cleaning Scratch\<slug>\         stage=clean  (detect->gate->mask->LaMa->verify)
  4.Cleaning Done\<slug>\
  5.Final Scratch\<slug>\            stage=final  (masked face/eye repair, debanding)
  6.Final Done\<slug>\
  7.Last Scratch\<slug>\             stage=last   (fresh-eyes regression)
  8.End Review\<slug>\               deep audit queue (deleted on pass after
                                     verified copy to 9 - ADR-003)
  9.Image Backup\<slug>\             append-only archive: verbatim original,
                                     every _initial, _lastdone, manifests
  reference_pictures\                non-pipeline reference corpus

tools\lw_pipeline.py                 THE single writer of pipeline state:
                                     intake / start-stage / save-working /
                                     submit / approve / reject / finalize /
                                     scan / verify. SAFE-MOVE transitions
                                     (copy+fsync+hash-verify+delete), per-image
                                     locks, SHA-256 manifests. Writes
                                     ops/runtime/pipeline_state.json atomically
                                     (tmp+replace) and appends PIPELINE_LOG.md.

tools\lw_monitor.py                  read-only stdlib HTTP monitor on
                                     127.0.0.1:8901 (spec:
                                     docs/research/LW_MONITOR_SPEC.md).
                                     Serves web\monitor.html + /api/pipeline
                                     (tolerant reader of pipeline_state.json),
                                     /api/log, /api/thumb, /api/health,
                                     /api/shutdown. Fail-soft everywhere;
                                     CREATE_NO_WINDOW on any subprocess.

ops\runtime\pipeline_state.json      machine state twin, written atomically by
                                     lw_pipeline.py; monitor reads tolerantly
                                     (unknown fields ignored, stale-cache belt).

PIPELINE_LOG.md                      project root; append-only pipe-delimited
                                     transition log (one line per transition,
                                     format per docs/research/
                                     PIPELINE_STATE_MACHINE.md section 4.1).
                                     Gitignored (personal state).

data\recovery\                       source-recovery caches: hashes.json,
                                     matches.json, saucenao_cache.json,
                                     manual_queue.csv (atomic writes).

.claude\commands\                    stage slash-commands (/first-pass etc.)
                                     driving lw_pipeline.py per stage.
```

Gate ladder (G0 source, G1 upscale, G2 inpaint, G3 Claude vision, G4
operator) and the autonomy calibration ladder live in
`docs/RESTORATION_PLAN.md` sections 3-5; audit calibration ledger is
append-only JSONL under `docs/audit/` (created at first calibration run).

ML environments (plan section 6-7): `.venv-upscale` (torch cu128 + spandrel +
IllustrationJaNai), `C:\Tools\lw-clean\venv` (ultralytics + easyocr +
simple-lama-inpainting), `C:\Tools\iopaint\venv` (pinned iopaint 1.6.0 QA UI),
ComfyUI portable later for the final-stage inpaint service.

---

## Inherited runtime conventions

Process conventions carried over 1:1 from RC (ADR-001):

- **Supervisor pattern.** A small supervisor daemon (`ops/lw_supervisor.py` -
  TBD, not yet written) owns long-running process lifecycle: PID lock,
  crash restart, and the restart trigger. Registered at logon as the
  `LW-Supervisor` scheduled task ONCE armed (see `docs/OPERATIONS.md` -
  NOT YET REGISTERED).
- **`restart_trigger.txt`** at the repo root. Writing `restart` to it asks the
  supervisor to bounce the main process within ~5s. This is THE normal restart
  path - never `Stop-Process` (hangs MCP pipes); `taskkill /F /PID` only as the
  hard fallback.
- **`ops/runtime/health.json`.** Heartbeat JSON for supervised processes:
  at minimum `pid`, `alive`, `last_reload_ok`. Every restart is VERIFIED by
  reading it back. (Producer TBD; the pipeline CLI is run-to-completion and
  does not need one; the monitor exposes `/api/health` instead.)
- **`logs/YYYY-MM-DD.log`.** One log file per day, 30-day retention, UTF-8.
  The monitor additionally logs to `logs/lw_monitor.log` (pythonw has no
  console).
- **Atomic writes only.** `tmp.write_text(...); tmp.replace(target)` for every
  runtime-consumed file - anything may be read mid-write.
- **`py_compile` before restart.** Syntax errors crash silently under
  `pythonw.exe`; compile every modified .py before triggering a restart.
- **CREATE_NO_WINDOW.** Every subprocess authored in LW code passes
  `creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)` - Legion
  focus-steal rule.
