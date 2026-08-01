"""Shared HTTP scaffold for LW's localhost-only dashboard servers.

Every LW board needs the same four things and none of them should own a
private copy: a threading server whose bind failure is load-bearing, a request
handler that refuses foreign Host headers and can never leak a traceback, file
logging that cannot take the server down, and a tolerant reader for JSON that
a producer rewrites underneath us.

A service supplies only its routes - subclass BaseLWHandler and implement
_route(method). tools/lw_monitor.py is the reference consumer.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# ------------------------------------------------------------------- time


def iso_from_epoch(epoch):
    try:
        return datetime.fromtimestamp(float(epoch), tz=timezone.utc).isoformat().replace("+00:00", "Z")
    except (OSError, OverflowError, ValueError, TypeError):
        return None


def parse_ts(value):
    """ISO-8601 string -> epoch float; junk -> None.

    Anything a producer writes into a timestamp field is untrusted input: a
    dashboard that raises on a malformed date is a dashboard that goes dark
    exactly when the run it watches went wrong.
    """
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


def age_text(age_s):
    if age_s is None:
        return ""
    if age_s < 90:
        return f"{round(age_s)}s"
    if age_s < 5400:
        return f"{round(age_s / 60)}m"
    return f"{age_s / 3600:.1f}h"


# -------------------------------------------------------- tolerant reading


def read_json_tolerant(path, cache, *, now_ts=None):
    """Read a JSON file that a producer may be mid-rewrite of.

    Absent or unreadable -> absent. Unparsable -> the last good payload this
    cache saw, flagged stale with the time it was good; the reader polls far
    faster than the producer writes, so a torn read is expected traffic and
    must not blank the board. Returns a dict with keys present / data / mtime
    / stale / stale_since; `cache` is caller-owned and keyed by path.

    A bare `null` counts as absent, NOT as a payload - see the guard below.
    """
    if now_ts is None:
        now_ts = time.time()
    path = Path(path)
    key = str(path)
    out = {"present": False, "data": None, "mtime": None, "stale": False, "stale_since": None}
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return out
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = None
    try:
        data = json.loads(raw)
    except ValueError:
        entry = cache.get(key)
        if entry is None:
            return out
        return {"present": True, "data": entry["data"], "mtime": entry["mtime"],
                "stale": True, "stale_since": entry["good_iso"]}
    if data is None:
        # `null` parses cleanly, so without this it would be stored as the new
        # last-good and throw the real payload away - and the NEXT torn read
        # would then have nothing to fall back on and blank the board. None is
        # this function's absent sentinel, so it cannot also mean "a payload".
        # Every other falsy JSON (0, "", [], false, {}) IS content and does
        # replace last-good; only null is nothing.
        return out
    cache[key] = {"data": data, "mtime": mtime, "good_iso": iso_from_epoch(now_ts)}
    out.update(present=True, data=data, mtime=mtime)
    return out


# -------------------------------------------------------------- the server


class LWServer(ThreadingHTTPServer):
    daemon_threads = True
    # Windows SO_REUSEADDR would let a second server steal the port; a hard
    # bind failure is what makes the bind-first single-instance guard work.
    allow_reuse_address = False

    def __init__(self, addr, handler):
        super().__init__(addr, handler)
        self.started_iso = iso_from_epoch(time.time())


class BaseLWHandler(BaseHTTPRequestHandler):
    """Transport, guards and fail-soft posture. Subclasses add only _route."""

    server_version = "LWHttpd/1.0"
    protocol_version = "HTTP/1.1"
    logger_name = "lw_httpd"

    def log_message(self, fmt, *args):  # never stdout - pythonw has no console
        logging.getLogger(self.logger_name + ".http").info("%s %s", self.address_string(), fmt % args)

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
        # The Host guard lives here, not in _route: a DNS-rebinding defense a
        # new service can forget to call is not a defense.
        try:
            if not self._host_ok():
                self._send_json(403, {"ok": False, "error": "forbidden"})
                return
            self._route(method)
        except Exception:  # noqa: BLE001 - top-level request guard, fail-soft
            logging.getLogger(self.logger_name + ".http").exception(
                "unhandled error on %s %s", method, self.path)
            self._send_json(500, {"ok": False, "error": "internal error"})

    def _route(self, method):
        """Dispatch one request. Implemented by the service, never here."""
        raise NotImplementedError


# ---------------------------------------------------------------- lifecycle


def setup_logging(log_path):
    try:
        log_path = Path(log_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        root = logging.getLogger()
        if not root.handlers:
            root.addHandler(handler)
            root.setLevel(logging.INFO)
    except OSError:
        pass  # logging must never take the server down


def serve_or_defer(factory, url, *, name, log, open_url=None):
    """Bind first, then decide - a failed bind IS the single-instance guard.

    The instance already holding the port is authoritative, so a second launch
    points the operator at it and exits clean rather than dying with a stack
    trace behind a double-clicked shortcut. `open_url` is the browser seam and
    is None when the caller was not asked to open one.
    """
    try:
        server = factory()
    except OSError as exc:
        log.info("bind failed on %s (%s) - assuming %s already runs; deferring", url, exc, name)
        if open_url is not None:
            open_url(url)
        return 0
    log.info("%s serving %s pid=%d", name, url, os.getpid())
    if open_url is not None:
        open_url(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        log.info("%s stopped pid=%d", name, os.getpid())
    return 0
