r"""LW Run Dashboard - read-only server for RUNS (spec: docs/RUNDASH_SPEC_2026-08-01.md).

Serves web/rundash.html plus the JSON APIs on 127.0.0.1, on the shared
tools/lw_httpd.py scaffold. This module owns routes and composition only: the
transport, the Host guard, the fail-soft 500 wrapper and the bind-first
single-instance guard are lw_httpd's, and every reader is
tools/lw_rundash_state.py's. What is left here is the join - which readers make
up which panel, and which facts a panel is allowed to state.

Panels shipped: P1 Run Ledger and P3 Resume Decision, plus the P2 evidence chip
in its only reachable state. P4 and P5 are out of scope.

IMAGE STATE IS NOT HERE. tools/lw_monitor.py owns the pipeline board and runs on
its own port; these two share a scaffold and nothing else.

THREE THINGS THIS FILE REFUSES TO DO.

LIVENESS OFF A LOCK. run_liveness corroborates a lock against pid liveness, lock
age and the newest write on disk. Measured 2026-08-01: RUNNING.lock named a pid
Windows had reissued to an unrelated conhost, and the loop sat wedged for five
days. A dashboard that trusts the lock file reproduces that as a display bug.

A BLANK EVIDENCE CELL. The P2 chip renders amber NOT OBSERVED on every row until
the instrumentation in the spec's backlog lands. Blank reads as "fine"; a panel
that says what it cannot see is the argument for fixing it.

DOLLARS. LEDGER 40 settles that Claude cost accounting is notional on a Max
plan, so the fleet reports output tokens and nothing else.

Launch: pythonw.exe tools/lw_rundash.py --open
Runs under pythonw - no console, so nothing here may print; output goes to
logs/lw_rundash.log. Stop: taskkill /F /PID <pid> (pid from /api/health).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent

if str(ROOT) not in sys.path:  # launched as a script, not as tools.lw_rundash
    sys.path.insert(0, str(ROOT))

from tools import lw_rundash_state as rundash_state  # noqa: E402
from tools.lw_httpd import (  # noqa: E402
    BaseLWHandler,
    LWServer,
    serve_or_defer,
    setup_logging,
)

# Named as a module constant because tests/test_no_console_flash.py AST-resolves
# the creationflags argument to a VALUE - a typo'd attribute name returns 0,
# spawns fine, and flashes a console on the operator's desktop anyway.
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

HOST = "127.0.0.1"
DEFAULT_PORT = 8900

CONTROL_DIR = ROOT / "ops" / "loop" / "control"
MANIFEST_PATH = ROOT / "ops" / "runtime" / "slice_manifest.json"
CONFIG_PATH = ROOT / "ops" / "loop" / "config.json"
PAGE_PATH = ROOT / "web" / "rundash.html"
RUNDASH_LOG = ROOT / "logs" / "lw_rundash.log"

# Where Claude Code keeps this project's sessions, and with them the only record
# of which agent owned which worktree. AVAILABLE, NOT DURABLE - no
# cleanupPeriodDays is set, so absent is a normal answer here.
TRANSCRIPT_DIR = Path.home() / ".claude" / "projects" / "C--LegionWallpaper"

# A slice sitting in one status this long, or an agent silent this long while
# the run is still LIVE, is the thing the operator came to the page to find.
STUCK_S = 900.0

# Never two. Only the third is reachable until the spec's instrumentation
# backlog lands, and the vocabulary ships now so the upgrade is a value change
# rather than a rewrite of the panel.
EVIDENCE_STATES = ("VERIFIED", "REFUTED", "NOT OBSERVED")
NOT_OBSERVED = "NOT OBSERVED"
NOT_OBSERVED_WHY = ("no persisted verifier verdict or suite observation exists "
                    "for this slice - claims here are unbacked")

# What the operator sees when git fails. The raw stderr goes to the log: a git
# error can carry a remote URL or a username and never belongs on a page.
GIT_UNAVAILABLE = "git state unavailable - see logs/lw_rundash.log"

log = logging.getLogger("lw_rundash")


# ----------------------------------------------------------------- git facts


def _git_runner(argv, timeout=20.0):
    try:
        proc = subprocess.run(
            argv, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout, creationflags=NO_WINDOW)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return 1, "", str(exc)
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def head_summary(repo_root, *, runner=None, git="git", timeout=20.0):
    """HEAD sha, branch and ahead/behind for the P1 header, in ONE subprocess.

    `status --porcelain=v2 --branch` carries branch.oid and branch.ab together,
    so this costs one spawn per poll instead of two - and every spawn on this
    box is a chance to flash a console.

    `error` is for the log only; build_run_view never copies it into a payload.
    """
    run = runner if callable(runner) else (lambda argv: _git_runner(argv, timeout))
    out = {"ok": False, "head": None, "head_short": None, "branch": None,
           "ahead": None, "behind": None, "upstream": None, "error": None}
    try:
        rc, stdout, stderr = run([git, "-C", str(repo_root), "status", "--porcelain=v2", "--branch"])
    except (OSError, ValueError, TypeError, subprocess.SubprocessError) as exc:
        rc, stdout, stderr = 1, "", str(exc)
    if rc != 0:
        out["error"] = (stderr or "git status failed").strip()[:200]
        return out
    out["ok"] = True
    for line in (stdout or "").splitlines():
        parts = line.split()
        if len(parts) < 3 or parts[0] != "#":
            continue
        if parts[1] == "branch.oid":
            out["head"] = parts[2][:12]
            out["head_short"] = parts[2][:7]
        elif parts[1] == "branch.head":
            out["branch"] = None if parts[2] == "(detached)" else parts[2]
        elif parts[1] == "branch.upstream":
            out["upstream"] = parts[2]
        elif parts[1] == "branch.ab" and len(parts) >= 4:
            out["ahead"] = _int(parts[2].lstrip("+"))
            out["behind"] = _int(parts[3].lstrip("-"))
    return out


def _int(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------ small readers


def read_cycle_cap(config_path):
    """max_cycles from ops/loop/config.json, or None.

    Absent and unparsable are the same answer on purpose: the cap is a display
    denominator, and a run whose config is unreadable still has a cycle number
    worth showing without one.
    """
    try:
        data = json.loads(Path(config_path).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    return _int(data.get("max_cycles"))


def newest_session_dir(transcript_dir):
    """The most recently touched session dir that actually holds subagents.

    Claude Code keeps one dir per session and only some carry a fleet; picking
    by name would be picking by uuid, so this picks by the mtime of the
    subagents dir itself - the thing that moves when an agent writes.
    """
    try:
        entries = [p for p in Path(transcript_dir).iterdir() if (p / "subagents").is_dir()]
    except (OSError, ValueError, TypeError):
        return None
    if not entries:
        return None
    def key(p):
        try:
            return (p / "subagents").stat().st_mtime
        except OSError:
            return 0.0
    return max(entries, key=key)


# ------------------------------------------------------ P2: the evidence chip


def evidence_for_slice(_slice_row):
    """The P2 chip. Amber NOT OBSERVED, with the reason it cannot say more.

    The argument is in the spec: blank is a lie, and three states must exist even
    when one is reachable, so that a VERIFIED chip later means something. The
    row is taken as an argument rather than ignored because the moment a
    persisted verdict exists this function reads it and nothing else changes.
    """
    return {"state": NOT_OBSERVED, "label": NOT_OBSERVED, "class": "amber",
            "why": NOT_OBSERVED_WHY}


# --------------------------------------------------------- P1: attribution


def _mentions(text, token):
    """Whole-token match, so slice B1 does not claim agent branch ...-B10."""
    if not text or not token:
        return False
    return re.search(r"(?<![0-9a-z])" + re.escape(str(token).lower()) + r"(?![0-9a-z])",
                     str(text).lower()) is not None


def _attribute(slice_id, agents):
    """The agent whose branch, worktree path or description names this slice.

    A HINT, and labelled as one on the page. The manifest carries no worktree
    field, so ownership is reconstructed from a naming convention that nothing
    enforces; presenting an inference as a record is how a dashboard starts
    lying. Worktree agents win ties - they are the ones that hold work.
    """
    if not slice_id:
        return None
    hits = [a for a in agents
            if _mentions(a.get("worktree_branch"), slice_id)
            or _mentions(a.get("worktree_path"), slice_id)
            or _mentions(a.get("description"), slice_id)]
    if not hits:
        return None
    hits.sort(key=lambda a: (not a.get("is_worktree_agent"),))
    a = hits[0]
    return {"id": a["id"], "type": a["type"], "branch": a.get("worktree_branch"),
            "worktree_path": a.get("worktree_path"), "running": a.get("running"),
            "idle_human": a.get("idle_human"), "elapsed_human": a.get("elapsed_human"),
            "output_tokens": a.get("output_tokens"), "hint": True}


# ------------------------------------------------------------ P1: the view


def build_run_view(*, control_dir, manifest_path, config_path=None, session_dir=None,
                   repo_root=None, now_ts=None, cache=None, runner=None, pid_alive=None,
                   stuck_after_s=STUCK_S, git="git"):
    """The /api/run payload - P1 plus the P2 chip.

    Pure and injectable in the same sense as lw_monitor.build_pipeline_view:
    every path, the clock, the JSON cache, the git runner and the pid probe come
    from the caller, which is what lets the suite drive a recycled-pid lock and a
    whole agent fleet out of tmp_path with nothing running.
    """
    now_ts = time.time() if now_ts is None else now_ts
    cache = {} if cache is None else cache
    repo_root = ROOT if repo_root is None else Path(repo_root)

    manifest = rundash_state.read_slice_manifest(manifest_path, now_ts, cache=cache)
    liveness = rundash_state.run_liveness(
        control_dir, now_ts, manifest_path=manifest_path, pid_alive=pid_alive,
        repo_root=repo_root)
    fleet = (rundash_state.read_agent_fleet(session_dir, now_ts) if session_dir
             else {"ok": True, "present": False, "agents": [],
                   "counts": {"total": 0, "running": 0, "worktree": 0, "other": 0},
                   "output_tokens": 0})
    head = head_summary(repo_root, runner=runner, git=git)
    if not head["ok"] and head["error"]:
        log.info("head_summary failed: %s", head["error"])

    agents = fleet.get("agents") or []
    alerts = []
    slices = []
    stuck_count = 0
    for row in manifest["slices"]:
        stuck = bool(row["status"] == "in_progress"
                     and row["status_age_s"] is not None
                     and row["status_age_s"] > stuck_after_s)
        out_row = dict(row)
        out_row["stuck"] = stuck
        out_row["evidence"] = evidence_for_slice(row)
        out_row["agent"] = _attribute(row["id"], agents)
        slices.append(out_row)
        if stuck:
            stuck_count += 1
            alerts.append({
                "kind": "stuck_slice", "id": row["id"],
                "text": f"slice {row['id']} has been in_progress for {row['status_age_human']}"})

    # An agent going quiet is only news while the run is supposed to be running.
    # After a run ends every transcript is idle, and flagging all of them would
    # bury the one case this signal exists for.
    if liveness["state"] == "LIVE":
        for a in agents:
            if not a.get("is_worktree_agent") or a.get("running"):
                continue
            if a.get("idle_s") is None or a["idle_s"] <= stuck_after_s:
                continue
            alerts.append({
                "kind": "stalled_agent", "id": a["id"],
                "text": (f"worktree agent {a['id'][:8]} on {a.get('worktree_branch') or 'an unnamed branch'}"
                         f" has been silent for {a.get('idle_human')}")})

    disjoint = rundash_state.disjointness_warnings(manifest)
    for warn in disjoint:
        alerts.append({
            "kind": "disjointness", "id": warn["file"],
            "text": f"{warn['file']} is claimed by {', '.join(str(s) for s in warn['slices'])}"})

    manifest_head = manifest["head"]
    head_now = head["head"]
    head_moved = None
    if manifest_head and head_now:
        width = min(len(manifest_head), len(head_now))
        head_moved = manifest_head[:width].lower() != head_now[:width].lower()

    run = {
        "run_id": manifest["run_id"],
        "controller_run_id": liveness["run_id"],
        "state": liveness["state"],
        "reason": liveness["reason"],
        "pid": liveness["pid"],
        "pid_alive": liveness["pid_alive"],
        "corroborated": liveness["corroborated"],
        "lock_present": liveness["lock_present"],
        "lock_age_human": rundash_state.human_age(liveness["lock_age_s"]),
        "newest_write_age_human": rundash_state.human_age(liveness["newest_write_age_s"]),
        "newest_write_path": (liveness["newest_write"] or {}).get("path"),
        "writes_fresh": liveness["writes_fresh"],
        "stop_present": liveness["stop_present"],
        "stop_reason": liveness["stop_reason"],
        "cycle": liveness["cycle"],
        "cycle_cap": read_cycle_cap(config_path) if config_path else None,
        "manifest_head": manifest_head,
        "head_now": head["head_short"],
        "head_moved": head_moved,
        "branch": head["branch"],
        "ahead": head["ahead"],
        "behind": head["behind"],
        "git_ok": head["ok"],
        "git_message": None if head["ok"] else GIT_UNAVAILABLE,
    }
    return {
        "ok": True,
        "generated_at": rundash_state.iso_from_epoch(now_ts),
        "run": run,
        "manifest": {
            "present": manifest["present"], "stale": manifest["stale"],
            "stale_since": manifest["stale_since"], "updated": manifest["updated"],
            "updated_age_human": rundash_state.human_age(manifest["updated_age_s"]),
        },
        "slices": slices,
        "counts": manifest["counts"],
        "open_count": manifest["open_count"],
        "disjointness": disjoint,
        "fleet": fleet,
        "alerts": alerts,
        "stuck_count": stuck_count,
    }


# ------------------------------------------------------ P3: resume decision


def build_resume_view(*, control_dir, manifest_path, repo_root, now_ts=None, cache=None,
                      runner=None, pid_alive=None, git="git", tail_n=5):
    """The /api/resume payload - resume or restart, and is any work stranded.

    The controller.log tail is pinned ONLY when the run is DEAD. On a live run it
    is noise that scrolls; on a dead one it is the last thing that happened, and
    that is the whole reason the panel exists.
    """
    now_ts = time.time() if now_ts is None else now_ts
    cache = {} if cache is None else cache
    manifest = rundash_state.read_slice_manifest(manifest_path, now_ts, cache=cache)
    liveness = rundash_state.run_liveness(
        control_dir, now_ts, manifest_path=manifest_path, pid_alive=pid_alive,
        repo_root=repo_root)
    inventory = rundash_state.worktree_inventory(repo_root, runner=runner, git=git)
    if not inventory["ok"] and inventory.get("error"):
        # Raw git stderr can name a remote or a username. Log it, show a line.
        log.info("worktree inventory failed: %s", inventory["error"])
    verdict = rundash_state.resume_verdict(manifest, inventory, liveness, now_ts=now_ts)

    verdict["log_tail"] = (rundash_state.tail_lines(Path(control_dir) / "controller.log", tail_n)
                           if liveness["state"] == "DEAD" else [])
    verdict["run_reason"] = liveness["reason"]
    verdict["git_message"] = None if inventory["ok"] else GIT_UNAVAILABLE
    verdict["worktrees"] = [{
        "path": w["path"], "branch": w["branch"], "primary": w["primary"],
        "detached": w["detached"], "dirty_count": w["dirty_count"],
        "ahead": w["ahead"], "behind": w["behind"], "status_ok": w["status_ok"],
    } for w in inventory["worktrees"]]
    return verdict


# -------------------------------------------------------------------- server


class RunDashServer(LWServer):
    def __init__(self, addr, handler, *, control_dir=CONTROL_DIR, manifest_path=MANIFEST_PATH,
                 config_path=CONFIG_PATH, page_path=PAGE_PATH, repo_root=ROOT,
                 session_dir=None, runner=None, pid_alive=None, cache=None):
        super().__init__(addr, handler)
        self.control_dir = Path(control_dir)
        self.manifest_path = Path(manifest_path)
        self.config_path = Path(config_path)
        self.page_path = Path(page_path)
        self.repo_root = Path(repo_root)
        self.session_dir = Path(session_dir) if session_dir else None
        self.runner = runner
        self.pid_alive = pid_alive
        self.view_cache = {} if cache is None else cache

    def resolve_session_dir(self):
        """Re-resolved per request: a run dispatched after launch lands in a new
        session dir, and a board that pinned one at startup would go blind."""
        if self.session_dir is not None:
            return self.session_dir
        return newest_session_dir(TRANSCRIPT_DIR)


class Handler(BaseLWHandler):
    server_version = "LWRunDash/1.0"
    logger_name = "lw_rundash"

    def _route(self, method):
        path = urlparse(self.path).path
        srv = self.server
        if method == "GET":
            if path in ("/", "/rundash"):
                try:
                    body = srv.page_path.read_bytes()
                except OSError:
                    self._send_json(404, {"ok": False, "error": "dashboard page missing"})
                    return
                self._send(200, body, "text/html; charset=utf-8", {"Cache-Control": "no-store"})
                return
            if path == "/api/run":
                view = build_run_view(
                    control_dir=srv.control_dir, manifest_path=srv.manifest_path,
                    config_path=srv.config_path, session_dir=srv.resolve_session_dir(),
                    repo_root=srv.repo_root, cache=srv.view_cache,
                    runner=srv.runner, pid_alive=srv.pid_alive)
                self._send_json(200, view, {"Cache-Control": "no-store"})
                return
            if path == "/api/resume":
                view = build_resume_view(
                    control_dir=srv.control_dir, manifest_path=srv.manifest_path,
                    repo_root=srv.repo_root, cache=srv.view_cache,
                    runner=srv.runner, pid_alive=srv.pid_alive)
                self._send_json(200, view, {"Cache-Control": "no-store"})
                return
            if path == "/api/health":
                self._send_json(200, {
                    "ok": True,
                    "pid": os.getpid(),
                    "started_iso": srv.started_iso,
                    "port": srv.server_address[1],
                    "manifest_present": srv.manifest_path.is_file(),
                    "control_present": srv.control_dir.is_dir(),
                })
                return
        if method == "POST" and path == "/api/shutdown":
            self._send_json(200, {"ok": True})
            threading.Thread(target=srv.shutdown, daemon=True).start()
            return
        self._send_json(404, {"ok": False, "error": "not found"})


# ---------------------------------------------------------------------- main


def main(argv=None):
    ap = argparse.ArgumentParser(description="LW run dashboard server (127.0.0.1 only)")
    ap.add_argument("--open", action="store_true", dest="open_browser",
                    help="open the dashboard in the default browser")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--control-dir", default=None, help="ops/loop/control override")
    ap.add_argument("--manifest", default=None, help="slice_manifest.json override")
    ap.add_argument("--session-dir", default=None, help="agent transcript session dir override")
    ap.add_argument("--log-file", default=None, help="server log path override")
    args = ap.parse_args(argv)
    setup_logging(Path(args.log_file) if args.log_file else RUNDASH_LOG)
    url = f"http://{HOST}:{args.port}/"

    def factory():
        return RunDashServer(
            (HOST, args.port), Handler,
            control_dir=Path(args.control_dir) if args.control_dir else CONTROL_DIR,
            manifest_path=Path(args.manifest) if args.manifest else MANIFEST_PATH,
            session_dir=Path(args.session_dir) if args.session_dir else None)

    # webbrowser.open routes through os.startfile - no console flash
    return serve_or_defer(factory, url, name="lw_rundash", log=log,
                          open_url=webbrowser.open if args.open_browser else None)


if __name__ == "__main__":
    raise SystemExit(main())
