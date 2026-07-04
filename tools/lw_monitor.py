"""LW Monitor - read-only pipeline dashboard server (spec: docs/research/LW_MONITOR_SPEC.md).

Serves web/monitor.html plus JSON APIs over 127.0.0.1:8901 (stdlib http.server,
zero required dependencies; Pillow optional for real thumbnails). Reads
ops/runtime/pipeline_state.json written atomically by lw_pipeline.py and the
append-only PIPELINE_LOG.md at the project root. The reader is tolerant per
the 7 binding rules in spec section 3.2 - drift in the producer's shape is
never fatal.

Launch: pythonw.exe tools/lw_monitor.py --open  (Desktop shortcut "LW Monitor").
Runs under pythonw - no console, all output goes to logs/lw_monitor.log.
Stop: POST /api/shutdown, or taskkill /F /PID <pid> (pid from /api/health).
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import os
import re
import threading
import time
import webbrowser
from collections import OrderedDict, deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# Legion focus-steal rule: every subprocess authored in this repo must pass
# creationflags=CREATE_NO_WINDOW. No subprocess is spawned in v1, but the
# constant stays as the seam for any future widget (git/HEAD etc).
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = ROOT / "ops" / "runtime" / "pipeline_state.json"
LOG_PATH = ROOT / "PIPELINE_LOG.md"  # project-root append-only log (build-wave contract)
PAGE_PATH = ROOT / "web" / "monitor.html"
DEFAULT_IMAGE_ROOTS = [ROOT / "images"]
MONITOR_LOG = ROOT / "logs" / "lw_monitor.log"

HOST = "127.0.0.1"
DEFAULT_PORT = 8901
STUCK_S = 900.0
DONE_CAP = 5
LOG_TAIL_MAX = 200
THUMB_MAX_RAW_BYTES = 2 * 1024 * 1024
THUMB_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
THUMB_CACHE_CAP = 128

log = logging.getLogger("lw_monitor")

# Stage names fall back to the agreed images/ folder contract when the state
# file does not carry its own stage_names map.
DEFAULT_STAGE_NAMES = {
    "0": "Originals",
    "1": "First Pass Scratch",
    "2": "First Pass Done",
    "3": "Cleaning Scratch",
    "4": "Cleaning Done",
    "5": "Final Scratch",
    "6": "Final Done",
    "7": "Last Scratch",
    "8": "End Review",
    "9": "Image Backup",
    "?": "Unknown Stage",
}

# PIPELINE_STATE_MACHINE.md section 2.3 state names -> stage folder number.
STATE_TO_STAGE = {
    "PENDING_INTAKE": 0,
    "FIRST_SCRATCH": 1,
    "FIRST_DONE": 2,
    "CLEAN_SCRATCH": 3,
    "CLEAN_DONE": 4,
    "FINAL_SCRATCH": 5,
    "FINAL_DONE": 6,
    "LAST_SCRATCH": 7,
    "END_REVIEW": 8,
    "PASSED": 9,
}

CANONICAL_PHASES = ("_initial", "_working", "_needauth", "_done")

# Accepts both the generic four (_working) and the producer's stage-prefixed
# tokens (_firstworking_02, _cleanneedauth, _lastdone, ...).
_PHASE_RE = re.compile(r"^_(?:first|clean|final|last)?(initial|needauth|done|working)(?:_[0-9]+)?$")

_MODULE_VIEW_CACHE: dict = {}  # last-good pipeline_state payloads, keyed by path


# ------------------------------------------------------------------ helpers


def _iso_from_epoch(epoch):
    try:
        return datetime.fromtimestamp(float(epoch), tz=timezone.utc).isoformat().replace("+00:00", "Z")
    except (OSError, OverflowError, ValueError, TypeError):
        return None


def _parse_ts(value):
    """ISO-8601 string -> epoch float; junk -> None (tolerance rule 7)."""
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    if raw.endswith(("Z", "z")):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    try:
        return dt.timestamp()
    except (OSError, OverflowError, ValueError):
        return None


def classify_phase(phase):
    """Phase string -> one of the four canonical classes, or None for unknown."""
    if not isinstance(phase, str):
        return None
    m = _PHASE_RE.match(phase.strip())
    if not m:
        return None
    return "_" + m.group(1)


def _derive_stage(item):
    """Stage bucket key as str, or '?' (tolerance rule 3)."""
    s = item.get("stage")
    if isinstance(s, bool):
        return "?"
    if isinstance(s, int):
        return str(s)
    if isinstance(s, str) and s.strip().isdigit():
        return str(int(s.strip()))
    # producer shape: derive from the section 2.3 state name
    st = item.get("state")
    if isinstance(st, str) and st.strip().upper() in STATE_TO_STAGE:
        return str(STATE_TO_STAGE[st.strip().upper()])
    return "?"


def _derive_phase(item):
    """Verbatim phase string; producer state/substate mapped; default _initial."""
    phase = item.get("phase")
    if isinstance(phase, str) and phase.strip():
        return phase.strip()
    sub = item.get("substate")
    if isinstance(sub, str):
        u = sub.strip().upper()
        if u == "NEEDAUTH":
            return "_needauth"
        if u == "APPROVED_PENDING_MOVE":
            return "_done"
        if u == "EDITING":
            wm = item.get("working_max")
            if isinstance(wm, int) and not isinstance(wm, bool) and wm >= 1:
                return "_working"
            return "_initial"
    st = item.get("state")
    if isinstance(st, str):
        u = st.strip().upper()
        if u in ("FIRST_DONE", "CLEAN_DONE", "FINAL_DONE", "END_REVIEW", "PASSED"):
            return "_done"
        if u.endswith("_SCRATCH"):
            return "_working"
    return "_initial"


def _derive_id(item, key_id, index):
    if key_id:
        return str(key_id)
    v = item.get("id")
    if isinstance(v, str) and v.strip():
        return v.strip()
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return str(v)
    f = item.get("file")
    if isinstance(f, str) and f.strip():
        stem = Path(f.replace("\\", "/")).stem
        if stem:
            return stem
    return f"item-{index}"


def _norm_item(item, key_id, index, fallback_ts, now_ts, stuck_s):
    phase = _derive_phase(item)
    phase_class = classify_phase(phase)
    ts_raw = item.get("ts")
    if not isinstance(ts_raw, str):
        ts_raw = item.get("last_op_ts")
    ts_epoch = _parse_ts(ts_raw)
    ts_iso = ts_raw if isinstance(ts_raw, str) and ts_epoch is not None else None
    if ts_epoch is None and fallback_ts is not None:
        ts_epoch = fallback_ts
        ts_iso = _iso_from_epoch(fallback_ts)
    age_s = None
    if ts_epoch is not None:
        age_s = max(0.0, round(now_ts - ts_epoch, 1))
    error = item.get("error")
    error = str(error) if error not in (None, "") else None
    needauth = item.get("needauth")
    needauth = str(needauth) if needauth not in (None, "") else None
    note = item.get("note")
    note = str(note) if note not in (None, "") else None
    actor = item.get("actor")
    actor = str(actor) if actor not in (None, "") else None
    file_field = item.get("file")
    file_field = str(file_field) if isinstance(file_field, str) and file_field.strip() else None
    thumb = item.get("thumb")
    thumb = str(thumb) if isinstance(thumb, str) and thumb.strip() else None
    stuck = bool(phase_class == "_working" and age_s is not None and age_s > stuck_s)
    return {
        "id": _derive_id(item, key_id, index),
        "file": file_field,
        "stage": _derive_stage(item),
        "phase": phase,
        "phase_class": phase_class,
        "ts": ts_iso,
        "ts_epoch": ts_epoch,
        "actor": actor,
        "note": note,
        "error": error,
        "needauth": needauth,
        "thumb": thumb,
        "age_s": age_s,
        "stuck": stuck,
    }


def _age_text(age_s):
    if age_s is None:
        return ""
    if age_s < 90:
        return f"{round(age_s)}s"
    if age_s < 5400:
        return f"{round(age_s / 60)}m"
    return f"{age_s / 3600:.1f}h"


# ------------------------------------------------------------- pure builder


def build_pipeline_view(state_path, now_ts=None, *, done_cap=DONE_CAP, stuck_s=STUCK_S, cache=None):
    """Normalize pipeline_state.json into the /api/pipeline payload.

    Pure and injectable: state_path + now_ts + cache come from the caller.
    Implements every tolerance rule in spec section 3.2; never raises on
    producer drift, garbage JSON, or a missing file.
    """
    if now_ts is None:
        now_ts = time.time()
    if cache is None:
        cache = _MODULE_VIEW_CACHE
    state_path = Path(state_path)
    key = str(state_path)
    out = {
        "ok": True,
        "state_present": False,
        "stale": False,
        "run_id": None,
        "state_updated_at": None,
        "state_mtime_iso": None,
        "counts": {"?": 0},
        "phase_counts": {p: 0 for p in CANONICAL_PHASES},
        "attention": [],
        "stages": [],
        "updated_at": _iso_from_epoch(now_ts),
    }
    try:
        raw = state_path.read_text(encoding="utf-8")
    except OSError:
        raw = None
    state = None
    mtime = None
    if raw is not None:
        try:
            mtime = state_path.stat().st_mtime
        except OSError:
            mtime = None
        try:
            state = json.loads(raw)
        except ValueError:
            # rule 6: mid-write safety belt - serve the last good payload
            entry = cache.get(key)
            if entry:
                state = entry["state"]
                mtime = entry["mtime"]
                out["stale"] = True
                out["stale_since"] = entry["good_iso"]
    if state is None:
        return out  # rule 5: absent or unparsable with no last-good
    if not isinstance(state, dict):
        state = {}
    out["state_present"] = True
    if not out["stale"]:
        cache[key] = {"state": state, "mtime": mtime, "good_iso": _iso_from_epoch(now_ts)}
    out["state_mtime_iso"] = _iso_from_epoch(mtime) if mtime is not None else None

    run_id = state.get("run_id")
    out["run_id"] = str(run_id) if run_id not in (None, "") else None
    updated = state.get("updated_at")
    if not isinstance(updated, str):
        updated = state.get("generated_ts")
    out["state_updated_at"] = updated if isinstance(updated, str) else None

    stage_names = {}
    raw_names = state.get("stage_names")
    if isinstance(raw_names, dict):
        for k, v in raw_names.items():
            if isinstance(v, str) and v.strip():
                stage_names[str(k)] = v.strip()

    # rule 1: images as list or dict-keyed-by-id; anything else -> empty
    imgs_raw = state.get("images")
    items = []
    if isinstance(imgs_raw, list):
        for i, it in enumerate(imgs_raw):
            items.append(_norm_item(it if isinstance(it, dict) else {}, None, i, mtime, now_ts, stuck_s))
    elif isinstance(imgs_raw, dict):
        for i, (k, it) in enumerate(imgs_raw.items()):
            items.append(_norm_item(it if isinstance(it, dict) else {}, str(k), i, mtime, now_ts, stuck_s))

    # counts + phase_counts
    counts = {"?": 0}
    phase_counts = {p: 0 for p in CANONICAL_PHASES}
    buckets = {}
    for item in items:
        bucket = item["stage"]
        counts[bucket] = counts.get(bucket, 0) + 1
        pkey = item["phase_class"] or item["phase"]
        phase_counts[pkey] = phase_counts.get(pkey, 0) + 1
        buckets.setdefault(bucket, []).append(item)
    # producer-counts top-up (tolerance spirit, spec 3.2): lw_pipeline's
    # scan_tree tracks pre-intake originals ONLY as counts.pending_intake -
    # no per-image entries exist before intake - so count-only stages must
    # still surface their pressure. Never double counts tracked images.
    extra_counts = {}
    raw_counts = state.get("counts")
    if isinstance(raw_counts, dict):
        for k, v in raw_counts.items():
            if isinstance(v, bool) or not isinstance(v, int) or v <= 0:
                continue
            u = str(k).strip().upper()
            if u not in STATE_TO_STAGE:
                continue  # e.g. 'anomalies' - not a stage bucket
            bucket = str(STATE_TO_STAGE[u])
            extra = v - len(buckets.get(bucket, ()))
            if extra <= 0:
                continue
            extra_counts[bucket] = extra_counts.get(bucket, 0) + extra
            counts[bucket] = counts.get(bucket, 0) + extra
            if u == "PENDING_INTAKE":
                cls = "_initial"
            elif u.endswith("_SCRATCH"):
                cls = "_working"
            else:
                cls = "_done"
            phase_counts[cls] = phase_counts.get(cls, 0) + extra
    out["counts"] = counts
    out["phase_counts"] = phase_counts

    # attention lane: needauth > error > stuck, newest first within kind
    kind_rank = {"needauth": 0, "error": 1, "stuck": 2}
    attention = []
    for item in items:
        if item["phase_class"] == "_needauth":
            kind = "needauth"
            reason = item["needauth"] or item["note"] or "needs authorization"
        elif item["error"]:
            kind = "error"
            reason = item["error"]
        elif item["stuck"]:
            kind = "stuck"
            reason = f"working for {_age_text(item['age_s'])}"
        else:
            continue
        attention.append({
            "id": item["id"], "file": item["file"], "stage": item["stage"],
            "phase": item["phase"], "reason": reason, "ts": item["ts"],
            "ts_epoch": item["ts_epoch"], "actor": item["actor"],
            "age_s": item["age_s"], "kind": kind,
        })
    anomalies = state.get("anomalies")
    if isinstance(anomalies, list):
        for i, a in enumerate(anomalies):
            if not isinstance(a, dict):
                a = {}
            aid = a.get("slug") or a.get("id") or f"anomaly-{i}"
            klass = a.get("class")
            detail = a.get("detail")
            parts = [str(x) for x in (klass, detail) if x not in (None, "")]
            attention.append({
                "id": str(aid), "file": None, "stage": "?", "phase": None,
                "reason": ": ".join(parts) or "anomaly", "ts": None,
                "ts_epoch": None, "actor": None, "age_s": None, "kind": "error",
            })
    attention.sort(key=lambda a: (kind_rank[a["kind"]], -(a["ts_epoch"] or 0.0)))
    for a in attention:
        a.pop("ts_epoch", None)
    out["attention"] = attention

    # stage groups: 0-9 ascending then "?", active-first then newest inside
    phase_rank = {"_working": 0, "_needauth": 1, "_initial": 2, None: 3, "_done": 4}
    def bucket_sort(b):
        return (1, 0) if b == "?" else (0, int(b))
    stages = []
    for bucket in sorted(set(buckets) | set(extra_counts), key=bucket_sort):
        group = buckets.get(bucket, [])
        group.sort(key=lambda it: (phase_rank.get(it["phase_class"], 3),
                                   -(it["ts_epoch"] or 0.0)))
        listed = []
        done_listed = 0
        for it in group:
            if it["phase_class"] == "_done":
                if done_listed >= done_cap:
                    continue
                done_listed += 1
            listed.append(it)
        for it in listed:
            it.pop("ts_epoch", None)
        name = stage_names.get(bucket) or DEFAULT_STAGE_NAMES.get(bucket) or f"Stage {bucket}"
        stages.append({
            "stage": bucket if bucket == "?" else int(bucket),
            "name": name,
            "count": len(group) + extra_counts.get(bucket, 0),
            "items": listed,
        })
    out["stages"] = stages
    return out


# ------------------------------------------------------------------ log tail


def tail_log(log_path, n=60):
    """Tail of PIPELINE_LOG - deque big-file idiom, absent file fail-soft."""
    try:
        n = int(n)
    except (TypeError, ValueError):
        n = 60
    n = max(1, min(n, LOG_TAIL_MAX))
    try:
        with Path(log_path).open("r", encoding="utf-8", errors="replace") as fh:
            lines = list(deque(fh, maxlen=n))
    except OSError:
        return {"ok": True, "present": False, "lines": []}
    return {"ok": True, "present": True, "lines": [ln.rstrip("\r\n") for ln in lines]}


# -------------------------------------------------------------------- thumbs


_THUMB_CACHE: "OrderedDict[tuple, tuple]" = OrderedDict()
_THUMB_LOCK = threading.Lock()
_RAW_CTYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}


def _validate_thumb_path(raw, roots):
    """Spec 5.1: resolve + is_relative_to root(s) + suffix allowlist + is_file."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        p = Path(raw.strip())
        if not p.is_absolute():
            p = ROOT / p
        resolved = p.resolve()
    except (OSError, ValueError):
        return None
    if resolved.suffix.lower() not in THUMB_SUFFIXES:
        return None
    inside = False
    for root in roots:
        try:
            if resolved.is_relative_to(Path(root).resolve()):
                inside = True
                break
        except (OSError, ValueError):
            continue
    if not inside:
        return None
    try:
        if not resolved.is_file():
            return None
    except OSError:
        return None
    return resolved


def make_thumb(resolved):
    """(bytes, content_type) or None. Pillow downscale; raw-bytes fallback <= 2 MB."""
    try:
        mtime = resolved.stat().st_mtime
    except OSError:
        return None
    key = (str(resolved), mtime)
    with _THUMB_LOCK:
        cached = _THUMB_CACHE.get(key)
        if cached is not None:
            _THUMB_CACHE.move_to_end(key)
            return cached
    try:
        from PIL import Image
    except ImportError:
        Image = None
    if Image is None:
        try:
            if resolved.stat().st_size > THUMB_MAX_RAW_BYTES:
                return None
            data = resolved.read_bytes()
        except OSError:
            return None
        result = (data, _RAW_CTYPES.get(resolved.suffix.lower(), "application/octet-stream"))
    else:
        try:
            with Image.open(resolved) as im:
                im.thumbnail((256, 256))
                if im.mode in ("RGBA", "LA", "P"):
                    rgba = im.convert("RGBA")
                    bg = Image.new("RGB", rgba.size, (255, 255, 255))
                    bg.paste(rgba, mask=rgba.split()[-1])
                    im = bg
                elif im.mode != "RGB":
                    im = im.convert("RGB")
                buf = io.BytesIO()
                im.save(buf, "JPEG", quality=80)
            result = (buf.getvalue(), "image/jpeg")
        except (OSError, ValueError):
            return None
    with _THUMB_LOCK:
        _THUMB_CACHE[key] = result
        while len(_THUMB_CACHE) > THUMB_CACHE_CAP:
            _THUMB_CACHE.popitem(last=False)
    return result


# -------------------------------------------------------------------- server


class MonitorServer(ThreadingHTTPServer):
    daemon_threads = True
    # Windows SO_REUSEADDR would let a second server steal the port; a hard
    # bind failure is what makes the bind-first single-instance guard work.
    allow_reuse_address = False

    def __init__(self, addr, handler, *, state_path=STATE_PATH, log_path=LOG_PATH,
                 page_path=PAGE_PATH, image_roots=None, cache=None):
        super().__init__(addr, handler)
        self.state_path = Path(state_path)
        self.log_path = Path(log_path)
        self.page_path = Path(page_path)
        self.image_roots = [Path(r) for r in (image_roots or DEFAULT_IMAGE_ROOTS)]
        self.view_cache = {} if cache is None else cache
        self.started_iso = _iso_from_epoch(time.time())


class Handler(BaseHTTPRequestHandler):
    server_version = "LWMonitor/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # never stdout - pythonw has no console
        logging.getLogger("lw_monitor.http").info("%s %s", self.address_string(), fmt % args)

    def _send(self, status, body, ctype="application/json; charset=utf-8", extra=None):
        try:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            if extra:
                for k, v in extra.items():
                    self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)
        except OSError:
            pass  # client went away mid-response

    def _send_json(self, status, obj, extra=None):
        self._send(status, json.dumps(obj).encode("utf-8"), extra=extra)

    def _host_ok(self):
        host = (self.headers.get("Host") or "").strip().lower()
        name = host.rsplit(":", 1)[0] if ":" in host else host
        return name in ("127.0.0.1", "localhost")

    def do_GET(self):
        self._guarded("GET")

    def do_POST(self):
        self._guarded("POST")

    def _guarded(self, method):
        try:
            self._route(method)
        except Exception:  # noqa: BLE001 - top-level request guard, fail-soft per spec
            logging.getLogger("lw_monitor.http").exception("unhandled error on %s %s", method, self.path)
            self._send_json(500, {"ok": False, "error": "internal error"})

    def _route(self, method):
        if not self._host_ok():
            self._send_json(403, {"ok": False, "error": "forbidden"})
            return
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        srv = self.server
        if method == "GET":
            if path in ("/", "/monitor"):
                try:
                    body = srv.page_path.read_bytes()
                except OSError:
                    self._send_json(404, {"ok": False, "error": "monitor page missing"})
                    return
                self._send(200, body, "text/html; charset=utf-8", {"Cache-Control": "no-store"})
                return
            if path == "/api/pipeline":
                view = build_pipeline_view(srv.state_path, cache=srv.view_cache)
                self._send_json(200, view, {"Cache-Control": "no-store"})
                return
            if path == "/api/log":
                n = (query.get("n") or ["60"])[0]
                self._send_json(200, tail_log(srv.log_path, n), {"Cache-Control": "no-store"})
                return
            if path == "/api/thumb":
                raw = (query.get("path") or [""])[0]
                resolved = _validate_thumb_path(raw, srv.image_roots)
                if resolved is None:
                    self._send_json(403, {"ok": False})  # no path echo
                    return
                result = make_thumb(resolved)
                if result is None:
                    self._send_json(503, {"ok": False, "error": "thumb unavailable - install Pillow"})
                    return
                data, ctype = result
                self._send(200, data, ctype, {"Cache-Control": "max-age=300"})
                return
            if path == "/api/health":
                self._send_json(200, {
                    "ok": True,
                    "pid": os.getpid(),
                    "started_iso": srv.started_iso,
                    "port": srv.server_address[1],
                    "state_present": srv.state_path.is_file(),
                })
                return
        if method == "POST" and path == "/api/shutdown":
            self._send_json(200, {"ok": True})
            threading.Thread(target=srv.shutdown, daemon=True).start()
            return
        self._send_json(404, {"ok": False, "error": "not found"})


# ---------------------------------------------------------------------- main


def _setup_logging():
    try:
        MONITOR_LOG.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(MONITOR_LOG, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        root = logging.getLogger()
        if not root.handlers:
            root.addHandler(handler)
            root.setLevel(logging.INFO)
    except OSError:
        pass  # logging must never take the server down


def main(argv=None):
    ap = argparse.ArgumentParser(description="LW pipeline monitor server (127.0.0.1 only)")
    ap.add_argument("--open", action="store_true", dest="open_browser",
                    help="open the monitor page in the default browser")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--images-root", action="append", default=None,
                    help="allowed thumbnail root (repeatable); default C:\\LegionWallpaper\\images")
    ap.add_argument("--log-file", default=None, help="PIPELINE_LOG path override")
    ap.add_argument("--state-file", default=None, help="pipeline_state.json path override")
    args = ap.parse_args(argv)
    _setup_logging()
    image_roots = [Path(r) for r in args.images_root] if args.images_root else list(DEFAULT_IMAGE_ROOTS)
    url = f"http://{HOST}:{args.port}/"
    try:
        server = MonitorServer(
            (HOST, args.port), Handler,
            state_path=Path(args.state_file) if args.state_file else STATE_PATH,
            log_path=Path(args.log_file) if args.log_file else LOG_PATH,
            image_roots=image_roots,
        )
    except OSError as exc:
        # bind-first single-instance guard: the running instance is authoritative
        log.info("bind failed on %s (%s) - assuming LW Monitor already runs; deferring", url, exc)
        if args.open_browser:
            webbrowser.open(url)  # routes through os.startfile - no console
        return 0
    log.info("lw_monitor serving %s pid=%d state=%s", url, os.getpid(), server.state_path)
    if args.open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        log.info("lw_monitor stopped pid=%d", os.getpid())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
