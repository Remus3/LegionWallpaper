# LW Monitor - Design Spec (from the RC loop-monitor reference)

Date: 2026-07-03
Author: monitor-design agent (research wave, Task 7)
Status: PROPOSED - awaiting ADR + coordination with the state-machine agent
Reference implementation (read-only): `C:\Riot Commander\dashboard\routes_loop_monitor.py`,
`C:\Riot Commander\dashboard\routes_loop_status.py`,
`C:\Riot Commander\tests\test_loop_monitor_route.py`

---

## 1. What the RC reference actually does (verified by reading the source)

The RC "loop monitor" is NOT a separate web asset. The whole page (HTML + CSS + JS)
is one inline `_PAGE` string inside `routes_loop_monitor.py`, served at
`GET /loop-monitor`. A grep of `C:\Riot Commander\web\` for loop-monitor assets
confirms: zero hits - the page is fully self-contained in the route file.

### 1.1 Polling model (extract)

- Pure client-side pull: `load(); setInterval(load, 4000);` - a 4 s fixed poll.
- Each poll fetches BOTH endpoints in parallel:
  `Promise.all([jget('/api/loop-monitor'), jget('/api/loop-status')])`.
- `jget` is fail-soft: `fetch(u, {cache:'no-store'})`, returns `null` on any
  network error or non-OK status. A null renders as a muted "(endpoint down)" /
  "loop-status unavailable" message - the page NEVER throws, never blanks.
- The server side mirrors that: builders are fail-soft (missing file, bad JSON,
  OSError all degrade to empty payload with `ok: true`); HTTP 500 only for a
  truly unexpected top-level exception, guarded by try/except around `send_error`.
- No websockets, no server push, no caching headers relied on - `cache:'no-store'`
  plus a fresh build per request.

### 1.2 Per-item timeline UI (extract)

- Vertical stack of `.card` panels: status summary (state pill, cycle, budget),
  "Running now" (inflight items - the live "stuck on X for Nm" signal),
  "Stalls", "Time by tool" (aggregate table with gradient bars scaled to max),
  "Recent calls" (newest-first table, capped at 30 rows client-side).
- Rows carry semantic classes: `rinf` (green tint = in flight), `rsus`
  (orange tint = suspect/stall), `.err` red bang for errors.
- Duration helper `dur(s)` renders s/m/h; `dcl(s)` maps duration to a color
  class ladder (`d-fast` muted -> `d-ok` green -> `d-warn` orange -> `d-slow` red).
- All user-derived text goes through `esc()` (escapes `& < >`) before innerHTML.
- Timestamps shown as `hh:mm:ss` via slice(11,19) of the ISO string.

### 1.3 State sourcing (extract)

- Read-only aggregation over files another process writes. `routes_loop_status`
  derives `state` from MULTIPLE files ("never trusted from a single field"):
  STOP file presence -> stopped; cycle.txt presence -> running; else idle.
- Every read is individually fail-soft (`_read_text` / `_read_json` -> None).
- Log preview = tail of an append log, fixed line cap (`LOG_TAIL_LINES = 12`).
- Big-file safety: transcript JSONL is read through `deque(fh, maxlen=8000)` so
  a multi-hour tens-of-MB file never blows memory.
- Subprocess discipline: `CREATE_NO_WINDOW (0x08000000)` on every `subprocess.run`
  because the server runs under `pythonw.exe` and the page polls every 4 s - an
  unsuppressed console window would steal desktop focus on every poll. LW
  inherits this as a hard rule.
- The builder is a pure function (`build_loop_timeline(session_path=..., now_ts=...)`)
  with injectable IO - that is what makes the RC test file possible.

### 1.4 Styling conventions (extract)

Dark hextech palette via CSS custom properties (fits the LW corpus - League
splash-art wallpapers - so we keep it):

```
--bg:#0a1428  --panel:#0f1c2e  --line:#1e2d44
--gold:#c8aa6e  --teal:#0ac8b9  --tx:#cdd2e0  --mut:#7c869c
--red:#c8455a  --grn:#3fb950  --org:#d29922
```

RC uses 14 px body / 12 px meta - fine for a phone at arm's length, TOO SMALL
for the LW use case (operator watches from across the room). LW bumps the whole
type ramp (section 6.2). Other conventions kept: `Segoe UI/system-ui` body,
`ui-monospace/Consolas` for paths and ids, `.card` panels with 1 px `--line`
border + 8 px radius, uppercase letter-spaced `h2` section labels in teal,
pill badges with translucent tinted backgrounds.

### 1.5 Test pattern (extract)

`test_loop_monitor_route.py` tests three seams and LW mirrors all three:
1. The pure builder against tmp_path fixture files (pairing, aggregation,
   inflight, error counting, ordering, fail-soft on missing/garbage input).
2. Route surface: GET-only, matcher hit/miss.
3. `_serve_*` against a `FakeHandler` capturing `(status, body, ctype)`.

---

## 2. LW Monitor - architecture overview

No dashboard server exists in LW and none is planned yet, so the monitor is a
single standalone stdlib-only script plus one static page:

```
tools/lw_monitor.py        the server (stdlib http.server, no dependencies
                           required; Pillow OPTIONAL for real thumbnails)
web/monitor.html           the page (single file: HTML + CSS + JS inline,
                           read from disk per request so edits are live)
ops/runtime/pipeline_state.json   INPUT - written atomically by lw_pipeline.py
                                  (owned by the state-machine agent)
ops/runtime/PIPELINE_LOG.txt      INPUT - append-only log tail source
logs/lw_monitor.log        server's own log (pythonw has no console)
```

- Bind: `127.0.0.1:8901` ONLY (hard-coded host; port via `--port` for tests).
- Launch: `pythonw.exe tools/lw_monitor.py --open` (Desktop shortcut, section 8).
- `ThreadingHTTPServer` with `daemon_threads = True`.
- `BaseHTTPRequestHandler.log_message` overridden to write to the logging
  module (file handler at `logs/lw_monitor.log`), never stdout.
- Every subprocess (none needed in v1, but the seam stays for a future
  git/HEAD widget) MUST pass `creationflags=CREATE_NO_WINDOW` - RC idiom,
  LW hard rule under pythonw.
- Single-instance guard: attempt the bind FIRST; on `OSError` (port in use)
  treat the running instance as authoritative - if `--open` was passed, just
  open the browser and exit 0. Bind-first is race-free, unlike probe-then-bind.
- Cheap DNS-rebinding defense even on loopback: reject requests whose `Host`
  header is not `127.0.0.1[:port]` or `localhost[:port]` with 403. Costless
  and closes the "malicious web page polls localhost" hole for /api/thumb.

### 2.1 Routes

| Route | Method | Serves |
|---|---|---|
| `/` and `/monitor` | GET | `web/monitor.html` from disk, `text/html`, `Cache-Control: no-store` |
| `/api/pipeline` | GET | normalized pipeline view (section 4) - JSON |
| `/api/log?n=60` | GET | tail of PIPELINE_LOG (section 5.2) - JSON |
| `/api/thumb?path=...` | GET | downscaled preview, path-validated (section 5.1) |
| `/api/health` | GET | `{ok, pid, started_iso, port, state_present}` |
| `/api/shutdown` | POST | clean stop (loopback-only by construction); returns `{ok:true}` then `server.shutdown()` from a helper thread |

Everything else: 404 JSON `{ok:false, error:"not found"}`. All GET handlers
follow the RC guard idiom: build inside try/except, log + fail-soft error
response, never a raw traceback to the client.

---

## 3. pipeline_state.json - the contract LW Monitor reads

COORDINATION NOTE: the state-machine agent defines and WRITES this file
(atomically: `tmp.write_text(...); tmp.replace(target)` per CLAUDE.md).
As of 2026-07-03 no `pipeline_state.json` producer exists in the repo (grep
confirms only unrelated hits in `ops/loop/loop_controller.py`), so the shape
below is the monitor's OPENING BID, and section 3.2 defines the tolerance
rules that hold no matter what the final shape becomes. If the state-machine
agent's contract differs, the reader adapts - the tolerance rules are the
real contract.

### 3.1 Proposed shape

```json
{
  "schema": 1,
  "run_id": "2026-07-03T18-22-01Z",
  "updated_at": "2026-07-03T18:25:40Z",
  "stage_names": {
    "0": "intake",
    "1": "source-recovery",
    "2": "upscale",
    "3": "downscale-sharpen",
    "4": "watermark-mask",
    "5": "inpaint",
    "6": "artifact-repair",
    "7": "audit",
    "8": "approve",
    "9": "deliver"
  },
  "images": [
    {
      "id": "aatrox_fanart_001",
      "file": "data/corpus/aatrox_fanart_001.png",
      "stage": 4,
      "phase": "_working",
      "ts": "2026-07-03T18:25:12Z",
      "actor": "lw_pipeline",
      "note": "inpaint mask pass 2 of 2",
      "error": null,
      "needauth": null,
      "thumb": "ops/runtime/thumbs/aatrox_fanart_001.jpg"
    }
  ]
}
```

Field semantics as the monitor consumes them:

- `stage`: int 0-9 (grouping key). The stage_names map above matches the LW
  product steps (recover -> upscale once -> Lanczos down -> unsharp ->
  masked inpaint -> audit -> deliver) but the monitor takes stage names FROM
  THE FILE when present and falls back to `Stage N` otherwise - the
  state-machine agent owns the naming.
- `phase`: one of `_initial | _working | _needauth | _done` (RC-inherited
  4-phase convention). `_needauth` + non-null `error` are what feed the
  needs-attention lane.
- `ts` + `actor`: the last transition - shown per row ("18:25:12 by
  lw_pipeline"). If absent, the monitor substitutes the state file's mtime.
- `needauth`: human reason string when `phase == "_needauth"` ("operator must
  approve mask"). Shown verbatim in the attention lane.
- `thumb`: optional pre-rendered thumbnail path; when present the page uses it
  via `/api/thumb?path=...` (still validated); when absent it falls back to
  `/api/thumb?path=<file>` and the server downscales on the fly.

### 3.2 Tolerance rules (BINDING on the monitor, whatever the producer does)

1. `images` accepted as a LIST of objects or a DICT keyed by id (id then comes
   from the key). Any other type -> treated as empty, `state_present` stays true.
2. Unknown keys - top-level or per-item - are IGNORED, never fatal. The
   state-machine agent may add fields freely.
3. Missing `stage` or non-int -> bucket `"?"` (rendered as its own "unknown
   stage" group at the bottom). Missing `phase` -> `_initial`. Missing `id` ->
   derived from `file` basename, else `item-<index>`.
4. Phase strings outside the known four render verbatim with a neutral badge -
   never dropped, never crash.
5. File absent or unparsable JSON -> `/api/pipeline` still returns 200 with
   `state_present: false`; the page shows a "waiting for pipeline state"
   banner instead of an error.
6. Mid-write safety belt: the producer writes atomically, but the monitor
   ADDITIONALLY keeps the last successfully parsed payload in memory and
   serves it (flagged `stale: true`, with `stale_since`) if a read ever
   catches a JSONDecodeError. Two independent defenses, RC's
   "never trusted from a single mechanism" spirit.
7. Timestamps parsed with the RC `_parse_ts` idiom (`fromisoformat` after
   `Z -> +00:00`); junk timestamps -> None, row still renders.

---

## 4. GET /api/pipeline - normalized response

The server (not the page) does the grouping, exactly as RC's
`build_loop_timeline` does the aggregation server-side. Pure function
`build_pipeline_view(state_path, log_path=None, now_ts=None) -> dict`:

```json
{
  "ok": true,
  "state_present": true,
  "stale": false,
  "run_id": "...",
  "state_updated_at": "...",
  "state_mtime_iso": "...",
  "counts": {"0": 12, "1": 3, "9": 280, "?": 0},
  "phase_counts": {"_initial": 5, "_working": 2, "_needauth": 1, "_done": 287},
  "attention": [
    {"id": "...", "file": "...", "stage": 4, "phase": "_needauth",
     "reason": "operator must approve mask", "ts": "...", "actor": "...",
     "kind": "needauth"}
  ],
  "stages": [
    {"stage": 0, "name": "intake", "count": 12,
     "items": [
       {"id": "...", "file": "...", "phase": "_working", "ts": "...",
        "actor": "...", "note": "...", "error": null, "thumb": "...",
        "age_s": 312.4, "stuck": false}
     ]}
  ],
  "updated_at": "2026-07-03T18:25:44Z"
}
```

- `attention` = every item with `phase == "_needauth"` (kind `needauth`) OR
  non-null `error` (kind `error`) OR `_working` with `age_s` over the stuck
  threshold (kind `stuck`, default 900 s - the LW analog of RC's inflight
  "stuck on X for Nm" signal). Sorted needauth first, then errors, then stuck,
  newest first within kind.
- `age_s` = now - last transition ts (server-computed so the page needs no
  clock math); `now_ts` injectable for tests, RC idiom.
- Stage groups sorted ascending 0-9 then `"?"`; items within a group sorted
  active-first (`_working`, `_needauth`, `_initial`, `_done`) then newest ts.
- `_done` items are counted always but LISTED only up to the newest 5 per
  stage (`done_cap=5`) - with ~302 images the page must not become a 300-row
  wall; the counts strip carries the totals.

## 5. Side endpoints

### 5.1 GET /api/thumb?path=...

- Query `path` may be absolute or repo-relative; repo-relative resolves
  against `C:\LegionWallpaper`.
- VALIDATION (all must pass, else 403 `{ok:false}`; no path echo in errors):
  1. `resolved = Path(p).resolve()` (resolves `..` and symlinks).
  2. `resolved.is_relative_to(root)` for at least one configured root.
     Default roots: `C:\LegionWallpaper\data` and
     `C:\LegionWallpaper\ops\runtime\thumbs`. Overridable via
     `--images-root` (repeatable). NOTE: the corpus location is not final -
     when the state-machine agent fixes the intake/output folders, add them
     here. Windows is case-insensitive: compare case-folded, which
     `is_relative_to` on WindowsPath already does.
  3. Suffix allowlist: `.png .jpg .jpeg .webp`.
  4. File exists and is a regular file.
- Downscale: if Pillow imports, `Image.thumbnail((256, 256))`, convert RGBA
  to RGB on white for JPEG, emit JPEG q=80. In-memory cache keyed by
  `(resolved, mtime)` with a small LRU cap (128 entries) and a lock -
  ThreadingHTTPServer means concurrent handlers.
- Fallback WITHOUT Pillow: serve the raw file bytes only if size <= 2 MB
  (typical DeviantArt jpg previews pass; 2560x1440 pipeline PNGs of ~4-8 MB
  do NOT - respond 503 `{ok:false, error:"thumb unavailable - install Pillow"}`).
  This keeps the no-dependency promise honest while pushing toward the 1-line
  Pillow install.
- Response headers: `Cache-Control: max-age=300` (thumbs are cheap to cache;
  the mtime key busts server-side on file change; 5 min browser staleness on
  a preview is acceptable).
- Pillow on Python 3.14: recent Pillow releases ship cp314 wheels
  (UNVERIFIED exact minimum version - verify with
  `python -m pip install Pillow` on this box; if 3.14 wheels are missing,
  this is the first concrete pressure point for the side-install of 3.11/3.12
  already flagged in the toolchain research).

### 5.2 GET /api/log?n=60

- Tail of `ops/runtime/PIPELINE_LOG.txt` (path overridable `--log-file`;
  COORDINATION: the state-machine agent should confirm this path or the
  monitor points at whatever it names - reader-tolerant, again).
- Read with `deque(fh, maxlen=min(n, 200))` - RC big-file idiom - newest last
  in the array; the page renders newest first.
- Absent file -> `{ok:true, lines:[], present:false}`.

---

## 6. web/monitor.html - structure skeleton

Single file, no external assets (works file-served and offline). Layout top
to bottom: header, counts strip, ATTENTION lane, stage groups, log tail.

### 6.1 Skeleton

```html
<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>LW Monitor</title>
<style>
:root{--bg:#0a1428;--panel:#0f1c2e;--line:#1e2d44;--gold:#c8aa6e;--teal:#0ac8b9;
--tx:#cdd2e0;--mut:#7c869c;--red:#c8455a;--grn:#3fb950;--org:#d29922}
*{box-sizing:border-box}
body{margin:0 auto;max-width:1400px;background:var(--bg);color:var(--tx);
padding:16px;font:16px/1.5 'Segoe UI',system-ui,sans-serif}   /* 16px >= 15px floor */
header h1{font-size:22px;color:var(--gold)}
.card{background:var(--panel);border:1px solid var(--line);border-radius:8px;
padding:12px 14px;margin-bottom:12px}
h2{font-size:15px;text-transform:uppercase;letter-spacing:.6px;color:var(--teal)}
/* counts strip: one chip per stage, count number 24px bold */
.chip{display:inline-block;padding:6px 14px;border:1px solid var(--line);
border-radius:8px;margin:0 6px 6px 0}
.chip .n{font-size:24px;font-weight:700}
.chip .lbl{font-size:13px;color:var(--mut);text-transform:uppercase}
/* phase badges: bigger than RC pills - readable across the room */
.badge{padding:4px 14px;border-radius:12px;font-size:16px;font-weight:700}
.b-initial{background:rgba(124,134,156,.18);color:var(--mut)}
.b-working{background:rgba(10,200,185,.15);color:var(--teal)}
.b-needauth{background:rgba(210,153,34,.22);color:var(--org)}
.b-done{background:rgba(63,185,80,.15);color:var(--grn)}
.b-err{background:rgba(200,69,90,.2);color:var(--red)}
.b-unknown{background:rgba(124,134,156,.12);color:var(--tx)}
/* attention lane: red border, larger rows */
#attention{border-color:var(--red)}
#attention .row{font-size:18px;padding:8px 0}
/* stage rows */
.irow{display:flex;align-items:center;gap:12px;padding:6px 0;
border-bottom:1px solid rgba(30,45,68,.5)}
.irow img{width:72px;height:40px;object-fit:cover;border-radius:4px;
background:#000}
.iid{font-family:ui-monospace,Consolas,monospace;font-size:15px;flex:1;
overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.meta{color:var(--mut);font-size:14px;white-space:nowrap}
.stuck{outline:1px solid var(--org)}
#logpanel pre{font:14px/1.45 ui-monospace,Consolas,monospace;color:var(--mut);
white-space:pre-wrap;max-height:320px;overflow-y:auto;margin:0}
.stale{background:rgba(210,153,34,.25);color:var(--org);padding:6px 12px;
border-radius:8px;font-weight:700;display:none}
</style></head><body>
<header>
  <h1>LW MONITOR</h1>
  <span id="runid" class="meta"></span>
  <span id="stalebanner" class="stale">STALE - last good data shown</span>
  <span id="updated" class="meta"></span>
</header>
<div class="card" id="counts"></div>
<div class="card" id="attention"></div>
<div id="stages"></div>          <!-- one .card per nonempty stage -->
<div class="card" id="logpanel"></div>
<script>
var $=function(i){return document.getElementById(i)};
function esc(t){return (t==null?'':String(t)).replace(/[&<>"]/g,function(c){
  return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
function tm(s){return esc((s||'').slice(11,19))}
function age(s){if(s==null)return'';if(s<90)return Math.round(s)+'s';
  if(s<5400)return Math.round(s/60)+'m';return (s/3600).toFixed(1)+'h'}
function badge(p,err){ /* phase string -> badge span; err wins */ }
async function jget(u){try{var r=await fetch(u,{cache:'no-store'});
  return r.ok?await r.json():null}catch(e){return null}}
var lastGood=null;
async function load(){
  var a=await Promise.all([jget('/api/pipeline'),jget('/api/log?n=40')]);
  var p=a[0],l=a[1];
  if(p){lastGood=p;$('stalebanner').style.display='none'}
  else if(lastGood){p=lastGood;$('stalebanner').style.display='inline-block'}
  if(!p){$('counts').innerHTML='<div class="meta">monitor endpoint down</div>';return}
  rHeader(p);rCounts(p);rAttention(p);rStages(p);rLog(l);
}
function rHeader(p){/* run_id, updated ts, waiting-banner when !state_present */}
function rCounts(p){/* chips: per-stage count + phase totals chip row */}
function rAttention(p){/* p.attention rows: badge + id + reason + ts/actor;
  empty -> 'nothing needs attention' in green */}
function rStages(p){/* one card per stage in p.stages: header
  'STAGE 4 - WATERMARK-MASK (12)', rows: thumb img (src=/api/thumb?path=...,
  loading="lazy", onerror hides), id, badge, note, 'hh:mm:ss by actor',
  age; .stuck outline when item.stuck */}
function rLog(l){/* newest-first joined lines into #logpanel pre */}
load();setInterval(load,3000);   /* 3s - inside the 2-5s spec window */
</script></body></html>
```

### 6.2 Distance-legibility rules (the delta from RC)

- Body 16 px (floor 15 px), image ids 15 px mono, meta 14 px minimum.
- Phase badges 16 px bold with generous padding - the badge column is the
  thing the operator reads from across the room.
- Counts strip numbers 24 px bold - stage progress readable at a glance.
- Attention lane rows 18 px inside a red-bordered card pinned above all
  stage groups; when empty it collapses to one green line, so ANY red border
  content is itself the signal.
- `_working` badge may pulse (CSS `@keyframes` opacity) - motion reads at
  distance; keep it subtle (1.6 s cycle) to avoid distraction.
- Thumbnails 72x40 (16:9 crop via `object-fit:cover`) - identification aid
  up close, not load-bearing at distance.

---

## 7. tools/lw_monitor.py - internal structure

```
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
ROOT = Path(__file__).resolve().parent.parent
STATE_PATH   = ROOT / "ops" / "runtime" / "pipeline_state.json"
LOG_PATH     = ROOT / "ops" / "runtime" / "PIPELINE_LOG.txt"
PAGE_PATH    = ROOT / "web" / "monitor.html"
IMAGE_ROOTS  = [ROOT / "data", ROOT / "ops" / "runtime" / "thumbs"]
STUCK_S      = 900.0
DONE_CAP     = 5

_read_json / _read_text / _parse_ts / _now_iso      # RC fail-soft idioms, verbatim
build_pipeline_view(state_path=..., now_ts=...)     # pure, injectable (sec 4)
tail_log(log_path, n)                                # deque tail (sec 5.2)
make_thumb(resolved: Path) -> tuple[bytes, str] | None   # Pillow or fallback
_validate_thumb_path(raw: str) -> Path | None       # sec 5.1 checks
class Handler(BaseHTTPRequestHandler):
    do_GET / do_POST dispatch on parsed path         # equals-match, RC style
    _send(status, body, ctype)                       # single write seam
    log_message -> logging, never stdout
main(argv): parse --open --port --images-root --log-file;
    bind-first single-instance guard; if bind fails and --open: webbrowser.open; exit 0
    if --open: webbrowser.open after successful bind, then serve_forever()
```

Notes:
- `webbrowser.open` on Windows routes through `os.startfile` - no console
  window, correct default browser. No subprocess needed for `--open`.
- Logging: `logging.basicConfig` to `logs/lw_monitor.log` (the server runs
  under pythonw; unhandled prints vanish, so everything goes through logging).
- `py_compile` before any restart - CLAUDE.md hard rule applies here doubly:
  a syntax error under pythonw crashes with zero visible signal.

## 8. Desktop shortcut - "LW Monitor"

Requirement: click -> server starts if not running -> browser opens. ZERO
console flash. Analysis of the launcher options:

- `.cmd` file: cmd.exe ALWAYS creates a console window - disqualified.
- `powershell -WindowStyle Hidden`: the console is created first and then
  hidden - a visible flash on every click - disqualified as primary.
- `pythonw.exe` directly: never allocates a console at all. WINNER - and it
  removes the middleman entirely: `lw_monitor.py --open` already implements
  "start if not running, then open browser" (bind-first guard, section 7),
  so the shortcut needs no wrapper script.

Shortcut spec:

- Target: `C:\Users\Administrator\AppData\Local\Programs\Python\Python314\pythonw.exe "C:\LegionWallpaper\tools\lw_monitor.py" --open`
- Start in: `C:\LegionWallpaper`
- Icon: `imageres.dll,109` (monitor glyph) - cosmetic, optional.

Exact one-time creation commands (PowerShell 5.1 safe, ASCII only):

```powershell
$ws  = New-Object -ComObject WScript.Shell
$lnk = $ws.CreateShortcut("$env:USERPROFILE\Desktop\LW Monitor.lnk")
$lnk.TargetPath       = "C:\Users\Administrator\AppData\Local\Programs\Python\Python314\pythonw.exe"
$lnk.Arguments        = '"C:\LegionWallpaper\tools\lw_monitor.py" --open'
$lnk.WorkingDirectory = "C:\LegionWallpaper"
$lnk.IconLocation     = "C:\Windows\System32\imageres.dll,109"
$lnk.Description      = "Legion Wallpaper pipeline monitor (127.0.0.1:8901)"
$lnk.Save()
```

Stop path (documented, not on the shortcut): `POST /api/shutdown` via
`Invoke-RestMethod -Method Post http://127.0.0.1:8901/api/shutdown`, or
`taskkill /F /PID <pid>` (pid from `/api/health`) - never `Stop-Process`
(CLAUDE.md hard rule: it hangs the MCP pipe).

## 9. Test plan (mirrors C:\Riot Commander\tests\test_loop_monitor_route.py)

`tests/test_lw_monitor.py`, pure-builder-first:

1. build_pipeline_view: list-form images grouped by stage; counts correct.
2. dict-form images accepted (tolerance rule 1); id from key.
3. Unknown per-item and top-level fields ignored (tolerance rule 2).
4. Missing stage -> "?" bucket; missing phase -> _initial (rule 3).
5. Unknown phase string preserved verbatim (rule 4).
6. Missing state file -> ok:true, state_present:false (rule 5).
7. Garbage JSON after a good read -> stale:true with last-good payload (rule 6).
8. attention ordering: needauth before error before stuck; stuck fires at
   age_s > 900 for _working items (now_ts injected).
9. done_cap: 300 _done items -> count 300, items listed 5.
10. tail_log: absent file -> present:false; n cap respected.
11. _validate_thumb_path: rejects `..\..\windows\win.ini`, absolute path
    outside roots, disallowed suffix, nonexistent file; accepts a real file
    under a tmp root passed via --images-root.
12. Route surface: FakeHandler `_send` capture - /api/pipeline returns 200
    application/json with ok:true; bad Host header -> 403; unknown path -> 404.
13. Single-instance: second bind on an occupied test port exits 0 (subprocess
    or refactored main seam).

## 10. Coordination points, risks, UNVERIFIED

- COORDINATE (state-machine agent): final `pipeline_state.json` shape and the
  PIPELINE_LOG path/name. The monitor's tolerance rules (3.2) mean drift is
  non-fatal, but stage_names and the four phase strings should be agreed once.
  Producer MUST keep atomic writes (tmp + replace) - the monitor polls at 3 s.
- COORDINATE (toolchain agent): confirm Pillow installs cleanly on Python
  3.14 on this box (cp314 wheel availability UNVERIFIED). Fallback behavior
  is specified (5.1) so the monitor works either way, minus thumbnails for
  large PNGs.
- RISK: images root defaults (`data\`, `ops\runtime\thumbs\`) are guesses
  until the pipeline fixes its folder layout; the `--images-root` flag and
  the 403-on-miss behavior contain the blast radius.
- RISK: 302-image corpus renders fine with done_cap, but if the pipeline
  later fans out per-stage artifacts (masks, intermediates) as separate
  items, the page needs pagination - out of scope v1, noted for the audit.
- UNVERIFIED: `imageres.dll,109` icon index (cosmetic only).
- Port 8901 assumed free on this box (RC dashboard uses 8888; no LW service
  exists yet) - `/api/health` disambiguates if anything else ever squats it.
