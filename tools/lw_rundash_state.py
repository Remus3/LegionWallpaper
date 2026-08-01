#!/usr/bin/env python
r"""Pure run-state readers for the LW run dashboard (spec docs/RUNDASH_SPEC_2026-08-01.md).

Panels P1 (Run Ledger) and P3 (Resume Decision) only - the two the spec found
need zero new instrumentation. No HTTP, no server, no page: a sibling slice owns
`tools/lw_rundash.py` and `web/rundash.html` and imports from here.

THREE PROPERTIES, EACH FOR A MEASURED REASON.

PURE + INJECTABLE. Every path, the clock and every cache arrive as arguments and
nothing is read at import. That is what lets the suite exercise a whole fleet, a
recycled-pid lock and a torn ledger out of `tmp_path` with no server running and
no access to the real tree - the same posture `tests/test_lw_monitor.py` uses on
`build_pipeline_view`.

NEVER RAISES. Every function returns a normalized dict on an absent, corrupt,
torn or wrong-typed source. A dashboard exists to be read when things are
already broken; one half-written log line must not be able to blank the panel
that would explain the breakage.

READ-ONLY. Nothing here writes. `slice_orchestrator.py`, `truth_gate.py` and
`loop_controller.py` own their files, and a reader that repairs what it reads
would be racing its own writer.

Cost is deliberately absent: LEDGER 40 settles that Claude dollar accounting is
notional on a Max plan and the old meter billed the wrong session. Token counts
only.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# 0 off Windows so the module still imports and tests under CI. Named as a
# module constant because tests/test_no_console_flash.py AST-resolves the
# creationflags argument to a value - a typo'd attribute silently returns 0,
# spawns fine, and flashes a console on the operator's desktop anyway.
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# The ladder as slice_orchestrator writes it. Kept for ordering and for counting
# statuses that never appeared in a given manifest - a zero is information.
SLICE_STATUSES = ("pending", "in_progress", "verified", "committed", "failed")

# Statuses whose work is durable in git. Anything else is only in a worktree.
COMMITTED_STATUSES = ("committed",)

# A STOP whose reason matches one of these is a run that ENDED, not one that was
# killed. Both write the same file, and telling the operator "STOPPED" about a
# clean 12-of-12 completion is a false alarm. Substrings of the reasons written
# by loop_controller.stop().
FINISH_MARKERS = ("max_cycles", "NO_WORK")

# Only used when ops/loop/slots.py cannot be loaded at all. slots is the
# authority (byte-identical-by-contract with the sibling repo, never edited from
# here); this exists so a reader on a broken tree still returns a verdict rather
# than an exception. test_default_stale_after_tracks_slots pins the two together
# so this copy cannot drift unnoticed.
FALLBACK_STALE_AFTER = 3.0 * 5400.0

# An agent transcript that has not been appended to in this long is finished
# rather than running. Measured 2026-08-01: live lanes sat at 4.6s / 14.9s /
# 58.2s of mtime age against ~176,000s for the 2026-07-30 fleet, so the gap the
# threshold has to split is four orders of magnitude wide.
AGENT_RUNNING_WITHIN_S = 300.0

_SLOTS_CACHE = {}


# ---------------------------------------------------------------- primitives


def _load_slots(root=None):
    """Import ops/loop/slots.py by path, lazily and at most once per root.

    Lazily because this module promises to read nothing at import. By path
    because ops/ and ops/loop/ carry no __init__.py, which is also how
    tests/test_loop_concurrency.py loads it.
    """
    root = Path(root) if root is not None else Path(__file__).resolve().parent.parent
    key = str(root)
    if key in _SLOTS_CACHE:
        return _SLOTS_CACHE[key]
    mod = None
    try:
        spec = importlib.util.spec_from_file_location(
            "lw_rundash_slots", root / "ops" / "loop" / "slots.py")
        if spec is not None and spec.loader is not None:
            mod = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = mod
            spec.loader.exec_module(mod)
    except (OSError, ImportError, SyntaxError, ValueError, AttributeError):
        mod = None
    _SLOTS_CACHE[key] = mod
    return mod


def default_stale_after(root=None):
    """The stale window, from slots if it loads, from the fallback if not."""
    mod = _load_slots(root)
    value = getattr(mod, "DEFAULT_STALE_AFTER", None)
    try:
        return float(value)
    except (TypeError, ValueError):
        return FALLBACK_STALE_AFTER


def default_pid_alive(root=None):
    """slots.pid_alive, or a never-alive stub if slots is unavailable.

    Fail-CLOSED here, unlike slots' own fail-open reaping: an unverifiable pid
    that the dashboard reports as LIVE would recreate exactly the false green
    the corroboration rule exists to kill.
    """
    fn = getattr(_load_slots(root), "pid_alive", None)
    return fn if callable(fn) else (lambda pid: False)


def iso_from_epoch(epoch):
    """UTC ISO-8601 with a Z suffix, or None when the input is not a number."""
    try:
        return datetime.fromtimestamp(float(epoch), tz=timezone.utc).isoformat().replace("+00:00", "Z")
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def parse_iso(text):
    """ISO-8601 -> epoch seconds, or None.

    A stamp with no offset is read as LOCAL time, because the producer wrote it
    that way: loop_controller.record_directive_outcome uses
    time.strftime("%Y-%m-%dT%H:%M:%S"). Reading those as UTC would shift every
    cycle age by the machine's offset and silently corrupt the ordering this
    module uses to separate colliding cycle numbers.
    """
    if not isinstance(text, str) or not text.strip():
        return None
    s = text.strip()
    if s.endswith(("Z", "z")):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    try:
        return dt.timestamp()
    except (ValueError, OSError, OverflowError):
        return None


def _age(now_ts, epoch):
    """Non-negative seconds from epoch to now, or None. Clamped at 0: a future
    stamp is a clock skew, and a negative age renders as nonsense."""
    if epoch is None:
        return None
    try:
        return max(0.0, float(now_ts) - float(epoch))
    except (TypeError, ValueError):
        return None


def human_age(seconds):
    """Compact age for a chip. Returns "-" for an unknown age rather than an
    empty cell, so a missing timestamp cannot be misread as "just now"."""
    if seconds is None:
        return "-"
    try:
        s = max(0.0, float(seconds))
    except (TypeError, ValueError):
        return "-"
    if s < 90:
        return f"{int(s)}s"
    if s < 5400:
        return f"{int(s // 60)}m"
    if s < 172800:
        return f"{int(s // 3600)}h"
    return f"{int(s // 86400)}d"


def _mtime(path):
    try:
        return Path(path).stat().st_mtime
    except (OSError, TypeError, ValueError):
        return None


def _read_text(path):
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except (OSError, TypeError, ValueError):
        return None


def _read_json(path):
    """(obj, mtime) with obj None on absent-or-unparsable. Never raises."""
    raw = _read_text(path)
    if raw is None:
        return None, None
    try:
        return json.loads(raw), _mtime(path)
    except ValueError:
        return None, _mtime(path)


def _str_or_none(value):
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _int_or_none(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------ P1: manifest


def _normalize_verdict(raw, now_ts):
    """One append-only verdict record from the manifest, or None if it is junk.

    `state` is carried through as written and NOT coerced to a known value: the
    consumer maps CONFIRM / REFUTE and treats everything else as unobserved, so
    a drifted or hand-edited record degrades to "nobody checked" rather than to
    a green chip.

    Counts stay None when the writer recorded none. Defaulting them to zero
    would turn "no suite was run" into "0 failed", which reads as a pass.
    """
    if not isinstance(raw, dict):
        return None
    counts = raw.get("counts")
    if isinstance(counts, dict):
        counts = {k: _int_or_none(counts.get(k)) for k in ("passed", "skipped", "failed")}
        if all(v is None for v in counts.values()):
            counts = None
    else:
        counts = None
    counts_human = None
    if counts is not None:
        counts_human = "{} passed / {} skipped / {} failed".format(
            *("?" if counts[k] is None else counts[k]
              for k in ("passed", "skipped", "failed")))
    lines = raw.get("discrepancies")
    lines = [d for d in lines if isinstance(d, str) and d.strip()] if isinstance(lines, list) else []
    at = _str_or_none(raw.get("at"))
    age = _age(now_ts, parse_iso(at))
    state = _str_or_none(raw.get("state"))
    return {
        "state": state.upper() if state else None,
        "observer": _str_or_none(raw.get("observer")),
        "at": at,
        "at_age_s": age,
        "at_age_human": human_age(age),
        "agent_id": _str_or_none(raw.get("agent_id")),
        "counts": counts,
        "counts_human": counts_human,
        "discrepancies": lines,
        "note": _str_or_none(raw.get("note")) or "",
        "backfilled": bool(raw.get("backfilled")),
    }


def read_verdicts(raw_slice, now_ts):
    """The verdict history of one raw manifest slice, oldest first.

    ABSENT IS NOT OBSERVED. The field is optional by contract
    (slice_orchestrator.VERDICT_FIELD), so every manifest written before it
    existed lands here as an empty history - which is the honest answer, not a
    degraded one. A non-list field is the same empty answer rather than a crash.

    Order is FILE order and is left alone. The list is append-only, so file
    order is the order the observations actually happened; re-sorting by a
    timestamp that can be absent would let a REFUTE jump ahead of the CONFIRM
    that fixed it.
    """
    if not isinstance(raw_slice, dict):
        return []
    history = raw_slice.get("verdicts")
    if not isinstance(history, list):
        return []
    out = [_normalize_verdict(r, now_ts) for r in history]
    return [r for r in out if r is not None]


def read_slice_manifest(path, now_ts=None, *, cache=None):
    """Normalize ops/runtime/slice_manifest.json for the P1 board.

    The manifest is atomically written and safe to poll, but "safe to poll" is
    not "never observed mid-swap on a busy box", so an unparsable read serves
    the last good payload flagged stale rather than blanking the board.

    Adds `status_age_s` per slice - time in the CURRENT status. The manifest
    carries only `updated`, and a slice sitting at in_progress for four hours is
    the single most actionable fact on the panel; without the subtraction the
    operator has to do date math off a UTC string to see it.

    Carries the optional `verdicts` history through as `verdicts` /
    `verdict_count` - normalized, never interpreted. Which of VERIFIED /
    REFUTED / NOT OBSERVED that history means is the caller's ruling, not this
    reader's, and an absent field stays an empty list all the way to the chip.
    """
    now_ts = time.time() if now_ts is None else now_ts
    cache = {} if cache is None else cache
    p = Path(path)
    out = {
        "ok": True,
        "present": False,
        "stale": False,
        "stale_since": None,
        "path": str(p),
        "run_id": None,
        "head": None,
        "created": None,
        "updated": None,
        "updated_age_s": None,
        "mtime_iso": None,
        "slices": [],
        "counts": {s: 0 for s in SLICE_STATUSES},
        "open_count": 0,
        "checked_at": iso_from_epoch(now_ts),
    }
    data, mtime = _read_json(p)
    if data is None and _read_text(p) is not None:
        entry = cache.get(str(p))
        if entry:
            data = entry.get("data")
            mtime = entry.get("mtime")
            out["stale"] = True
            out["stale_since"] = entry.get("good_iso")
    if data is None:
        return out
    if not isinstance(data, dict):
        # A producer that wrote a list or a bare string is drift, not a crash.
        data = {}
    out["present"] = True
    if not out["stale"]:
        cache[str(p)] = {"data": data, "mtime": mtime, "good_iso": iso_from_epoch(now_ts)}
    out["mtime_iso"] = iso_from_epoch(mtime)
    out["run_id"] = _str_or_none(data.get("run_id"))
    out["head"] = _str_or_none(data.get("head"))
    out["created"] = _str_or_none(data.get("created"))
    out["updated"] = _str_or_none(data.get("updated"))
    out["updated_age_s"] = _age(now_ts, parse_iso(out["updated"]))

    raw_slices = data.get("slices")
    if not isinstance(raw_slices, list):
        raw_slices = []
    for i, raw in enumerate(raw_slices):
        if not isinstance(raw, dict):
            continue
        files = raw.get("files")
        files = [f for f in files if isinstance(f, str)] if isinstance(files, list) else []
        status = _str_or_none(raw.get("status")) or "pending"
        updated = _str_or_none(raw.get("updated"))
        age = _age(now_ts, parse_iso(updated))
        verdicts = read_verdicts(raw, now_ts)
        out["slices"].append({
            "id": _str_or_none(raw.get("id")) or f"slice-{i + 1}",
            "title": _str_or_none(raw.get("title")) or "",
            "files": files,
            "status": status,
            "commit": _str_or_none(raw.get("commit")),
            "note": _str_or_none(raw.get("note")) or "",
            "updated": updated,
            "status_age_s": age,
            "status_age_human": human_age(age),
            "committed": status in COMMITTED_STATUSES,
            "verdicts": verdicts,
            "verdict_count": len(verdicts),
        })
        out["counts"][status] = out["counts"].get(status, 0) + 1
    out["open_count"] = sum(1 for s in out["slices"] if not s["committed"])
    return out


def disjointness_warnings(manifest):
    """Paths claimed by two or more non-committed slices.

    The orchestrator's whole safety story is that parallel agents touch disjoint
    file sets; an overlap is a merge conflict scheduled for later. Committed
    slices are excluded - their files are already in git, so a later slice
    naming the same path is sequential work, not a collision.
    """
    owners = {}
    slices = manifest.get("slices") if isinstance(manifest, dict) else None
    for s in slices if isinstance(slices, list) else []:
        if not isinstance(s, dict) or s.get("committed"):
            continue
        for f in s.get("files") or []:
            owners.setdefault(f, []).append(s.get("id"))
    return [{"file": f, "slices": ids} for f, ids in sorted(owners.items()) if len(ids) > 1]


# ------------------------------------------------------------ P1: liveness


def run_liveness(control_dir, now_ts=None, *, manifest_path=None, extra_paths=(),
                 stale_after=None, pid_alive=None, repo_root=None):
    r"""Corroborated LIVE / DEAD / STOPPED / FINISHED for the header chip.

    THE LOCK IS NOT EVIDENCE. Measured 2026-08-01: control/RUNNING.lock named pid
    8532 from a run that ended cleanly five days earlier with STOP written, and
    Windows had since reissued 8532 to an unrelated conhost.exe. Bare
    slots.pid_alive said "alive" and the loop refused to start for five days
    (fixed for the controller in e63a50d).

    So this applies e63a50d's rule verbatim - a holder owns the repo for at most
    a cycle, therefore a lock older than slots.DEFAULT_STALE_AFTER is not a live
    run whatever the pid table says - and then corroborates it against the disk:
    a genuinely live run moves controller.log, cycle.txt or slice_manifest.json.
    Nothing moving is the tell that no bare pid check can give you.

    Deliberately NOT the controller's rule in one respect: e63a50d excludes its
    OWN pid from the aliveness test because it is about to take the lock. A
    reader takes nothing, so an own-pid match here would be a genuine live
    holder and is treated as one.

    STOP outranks LIVE. The controller exits on STOP, so a run with a STOP file
    is winding down at best; calling it LIVE would tell the operator to wait for
    output that is never coming.
    """
    now_ts = time.time() if now_ts is None else now_ts
    ctl = Path(control_dir)
    stale_after = default_stale_after(repo_root) if stale_after is None else float(stale_after)
    alive_fn = default_pid_alive(repo_root) if pid_alive is None else pid_alive

    lock_path = ctl / "RUNNING.lock"
    stop_path = ctl / "STOP"
    out = {
        "ok": True,
        "state": "DEAD",
        "reason": "",
        "run_present": False,
        "control_dir": str(ctl),
        "lock_present": False,
        "pid": None,
        "run_id": None,
        "pid_alive": None,
        "lock_ts": None,
        "lock_age_s": None,
        "lock_fresh": False,
        "lock_holder_ok": False,
        "stale_after_s": stale_after,
        "stop_present": False,
        "stop_reason": None,
        "newest_write": None,
        "newest_write_age_s": None,
        "writes_fresh": False,
        "corroborated": False,
        "cycle": None,
        "checked_at": iso_from_epoch(now_ts),
    }

    lock, _ = _read_json(lock_path)
    lock_exists = lock_path.exists()
    out["lock_present"] = bool(lock_exists)
    if isinstance(lock, dict):
        out["pid"] = _int_or_none(lock.get("pid"))
        out["run_id"] = _str_or_none(lock.get("run_id"))
        try:
            out["lock_ts"] = float(lock.get("ts"))
        except (TypeError, ValueError):
            out["lock_ts"] = None
    elif lock_exists:
        # Present but unreadable: fall back to mtime, the same belt slots.is_stale
        # uses, so a corrupt lock cannot masquerade as a fresh one.
        out["lock_ts"] = _mtime(lock_path)
    out["lock_age_s"] = _age(now_ts, out["lock_ts"])
    if out["lock_present"]:
        pid = out["pid"] or 0
        try:
            out["pid_alive"] = bool(alive_fn(pid)) if pid > 0 else False
        except (OSError, ValueError, TypeError, AttributeError):
            out["pid_alive"] = False
        out["lock_fresh"] = out["lock_age_s"] is not None and out["lock_age_s"] < stale_after
        out["lock_holder_ok"] = bool(out["pid_alive"] and out["lock_fresh"])

    stop_raw = _read_text(stop_path)
    if stop_path.exists():
        out["stop_present"] = True
        reason = (stop_raw or "").strip().splitlines()
        out["stop_reason"] = reason[0][:200] if reason else ""

    watch = [ctl / "controller.log", ctl / "cycle.txt"]
    if manifest_path:
        watch.append(Path(manifest_path))
    watch.extend(Path(p) for p in (extra_paths or ()))
    newest, newest_path = None, None
    for p in watch:
        m = _mtime(p)
        if m is not None and (newest is None or m > newest):
            newest, newest_path = m, p
    if newest is not None:
        age = _age(now_ts, newest)
        out["newest_write"] = {"path": str(newest_path), "iso": iso_from_epoch(newest), "age_s": age}
        out["newest_write_age_s"] = age
        out["writes_fresh"] = age is not None and age < stale_after

    cycle_raw = _read_text(ctl / "cycle.txt")
    if cycle_raw is not None:
        out["cycle"] = _int_or_none(cycle_raw)
    out["run_present"] = bool(out["lock_present"] or out["stop_present"] or newest is not None)
    out["corroborated"] = bool(out["lock_holder_ok"] and out["writes_fresh"])

    if out["lock_holder_ok"] and out["writes_fresh"] and not out["stop_present"]:
        out["state"] = "LIVE"
        moved = human_age(out["newest_write_age_s"])
        out["reason"] = f"lock held by live pid {out['pid']}, fresh, and disk moved {moved} ago"
    elif out["stop_present"]:
        text = out["stop_reason"] or ""
        finished = any(m in text for m in FINISH_MARKERS)
        out["state"] = "FINISHED" if finished else "STOPPED"
        out["reason"] = text or "STOP present with no reason"
    elif not out["run_present"]:
        out["state"] = "DEAD"
        out["reason"] = "no run state on disk"
    elif out["lock_present"] and out["pid_alive"] and not out["lock_fresh"]:
        # The measured defect, named explicitly so the operator does not go
        # hunting a pid that belongs to something else entirely.
        out["state"] = "DEAD"
        old = human_age(out["lock_age_s"])
        out["reason"] = (f"lock pid {out['pid']} is alive but the lock is {old} old "
                         f"- recycled pid, not a live run")
    elif out["lock_present"] and not out["pid_alive"]:
        out["state"] = "DEAD"
        out["reason"] = f"lock pid {out['pid']} is not alive"
    elif out["lock_holder_ok"] and not out["writes_fresh"]:
        out["state"] = "DEAD"
        quiet = human_age(out["newest_write_age_s"])
        out["reason"] = f"lock looks held but nothing has been written for {quiet}"
    else:
        out["state"] = "DEAD"
        out["reason"] = "no lock held"
    return out


# ------------------------------------------------------- P2 spine: history


def read_cycle_history(path, now_ts=None, *, limit=None):
    """Parse ops/loop/control/directive_history.jsonl.

    Append-only and NOT atomic (loop_controller writes it with a plain open+write),
    so a poll can catch a half-written last line. Parsed per line with a failing
    TAIL line discarded as torn; a failing line in the MIDDLE is real corruption
    and is counted separately, because the two mean different things and folding
    them together would hide a producer bug behind an expected race.

    Cycle numbers COLLIDE across runs - the file carries no run id and two
    `cycle 1` records exist today. Records are therefore keyed by ts, and a
    cycle number that does not advance starts a new `run_index` segment.
    """
    now_ts = time.time() if now_ts is None else now_ts
    p = Path(path)
    out = {
        "ok": True,
        "present": False,
        "path": str(p),
        "records": [],
        "line_count": 0,
        "parsed": 0,
        "torn_tail": False,
        "corrupt_lines": 0,
        "run_count": 0,
        "checked_at": iso_from_epoch(now_ts),
    }
    raw = _read_text(p)
    if raw is None:
        return out
    out["present"] = True
    lines = [ln for ln in raw.splitlines() if ln.strip()]
    out["line_count"] = len(lines)
    recs = []
    for i, line in enumerate(lines):
        try:
            obj = json.loads(line)
        except ValueError:
            if i == len(lines) - 1:
                out["torn_tail"] = True
            else:
                out["corrupt_lines"] += 1
            continue
        if not isinstance(obj, dict):
            out["corrupt_lines"] += 1
            continue
        ts = _str_or_none(obj.get("ts"))
        epoch = parse_iso(ts)
        recs.append({
            "cycle": _int_or_none(obj.get("cycle")),
            "ts": ts,
            "ts_epoch": epoch,
            "age_s": _age(now_ts, epoch),
            "title": _str_or_none(obj.get("title")) or "",
            "sha_before": _str_or_none(obj.get("sha_before")),
            "sha_after": _str_or_none(obj.get("sha_after")),
            "tests": _int_or_none(obj.get("tests")),
            "tests_raw": obj.get("tests"),
            "regress": bool(obj.get("regress")),
            "verdict": _str_or_none(obj.get("verdict")) or "",
            "line_no": i + 1,
        })
    out["parsed"] = len(recs)

    # File order is append order, which is chronological; ts is the tiebreaker
    # and the only cross-run-safe identity, so key on it rather than on cycle.
    run_index, prev_cycle = 0, None
    for r in recs:
        c = r["cycle"]
        if prev_cycle is None or (c is not None and c <= prev_cycle):
            run_index += 1
        if c is not None:
            prev_cycle = c
        r["run_index"] = run_index
        r["key"] = f"{r['ts'] or 'no-ts'}#{c if c is not None else '?'}"
    out["run_count"] = run_index
    out["records"] = recs[-limit:] if isinstance(limit, int) and limit > 0 else recs
    return out


# --------------------------------------------------------- P3: worktrees


def _git_runner(argv, timeout=20.0):
    """(rc, stdout, stderr). CREATE_NO_WINDOW: under a pythonw parent a console
    child allocates its own window and flashes on the operator's desktop."""
    try:
        proc = subprocess.run(
            argv, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout, creationflags=NO_WINDOW)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return 1, "", str(exc)
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def _parse_worktree_list(text):
    """`git worktree list --porcelain` -> one dict per blank-line-separated block."""
    trees, cur = [], {}
    for line in (text or "").splitlines():
        line = line.rstrip()
        if not line:
            if cur:
                trees.append(cur)
                cur = {}
            continue
        key, _, value = line.partition(" ")
        if key == "worktree":
            if cur:
                trees.append(cur)
            cur = {"path": value.strip()}
        elif key == "HEAD":
            cur["head"] = value.strip()
        elif key == "branch":
            cur["branch"] = value.strip().replace("refs/heads/", "", 1)
        elif key == "detached":
            cur["detached"] = True
        elif key == "bare":
            cur["bare"] = True
    if cur:
        trees.append(cur)
    return [t for t in trees if t.get("path")]


def _parse_status_v2(text):
    """`git status --porcelain=v2 --branch` -> (dirty entries, ahead, behind, upstream).

    porcelain=v2 with --branch rather than plain --porcelain: it carries the
    ahead/behind counts in the same call, so a fleet of eight worktrees costs
    eight subprocesses instead of sixteen, and every one of those is a chance to
    flash a console.
    """
    dirty, ahead, behind, upstream = [], None, None, None
    for line in (text or "").splitlines():
        if not line.strip():
            continue
        try:
            if line.startswith("# branch.ab "):
                parts = line.split()
                ahead = _int_or_none(parts[2].lstrip("+"))
                behind = _int_or_none(parts[3].lstrip("-"))
            elif line.startswith("# branch.upstream "):
                upstream = line.split(None, 2)[2].strip()
            elif line.startswith("1 "):
                fields = line.split(" ", 8)
                dirty.append({"code": fields[1], "path": fields[8].split("\t")[0]})
            elif line.startswith("2 "):
                # A rename record carries one extra score field, then "new\torig".
                # The new path is the one that exists on disk to be salvaged.
                fields = line.split(" ", 9)
                dirty.append({"code": fields[1], "path": fields[9].split("\t")[0]})
            elif line.startswith("u "):
                fields = line.split(" ", 10)
                dirty.append({"code": "UU", "path": fields[10]})
            elif line.startswith("? "):
                dirty.append({"code": "??", "path": line[2:]})
        except (IndexError, ValueError):
            continue  # one unparsable status line must not lose the other seven
    return dirty, ahead, behind, upstream


def worktree_inventory(repo_root, *, runner=None, git="git", timeout=20.0):
    """`git worktree list` plus a per-worktree status, for the P3 salvage check.

    `runner(argv) -> (rc, stdout, stderr)` is injectable so the tests can drive
    every branch - dirty tree, unpushed commits, detached head, git absent -
    without a real repo and without spawning anything.
    """
    run = runner if callable(runner) else (lambda argv: _git_runner(argv, timeout))
    root = str(repo_root)
    out = {
        "ok": True,
        "error": None,
        "repo_root": root,
        "worktrees": [],
        "dirty_count": 0,
        "unpushed_count": 0,
    }
    try:
        rc, stdout, stderr = run([git, "-C", root, "worktree", "list", "--porcelain"])
    except (OSError, ValueError, TypeError, subprocess.SubprocessError) as exc:
        rc, stdout, stderr = 1, "", str(exc)
    if rc != 0:
        out["ok"] = False
        # Truncated, and the caller renders a friendly line: a raw git error is
        # never surfaced in the UI.
        out["error"] = (stderr or "git worktree list failed").strip()[:200]
        return out

    for i, tree in enumerate(_parse_worktree_list(stdout)):
        entry = {
            "path": tree.get("path"),
            "branch": tree.get("branch"),
            "head": tree.get("head"),
            "detached": bool(tree.get("detached")),
            "bare": bool(tree.get("bare")),
            "primary": i == 0,
            "dirty": [],
            "dirty_count": 0,
            "ahead": None,
            "behind": None,
            "upstream": None,
            "status_ok": False,
            "status_error": None,
        }
        try:
            src, sout, serr = run([git, "-C", entry["path"], "status", "--porcelain=v2", "--branch"])
        except (OSError, ValueError, TypeError, subprocess.SubprocessError) as exc:
            src, sout, serr = 1, "", str(exc)
        if src == 0:
            dirty, ahead, behind, upstream = _parse_status_v2(sout)
            entry.update({"dirty": dirty, "dirty_count": len(dirty), "ahead": ahead,
                          "behind": behind, "upstream": upstream, "status_ok": True})
        else:
            # A worktree whose directory was deleted still lists; say so rather
            # than reporting a clean tree we never actually looked at.
            entry["status_error"] = (serr or "git status failed").strip()[:200]
        out["worktrees"].append(entry)
        out["dirty_count"] += entry["dirty_count"]
        if (entry["ahead"] or 0) > 0:
            out["unpushed_count"] += 1
    return out


# ----------------------------------------------------- P3: resume verdict


def resume_verdict(manifest, worktrees, liveness=None, *, now_ts=None, include_primary=False):
    """RESUME SAFE vs SALVAGE FIRST.

    2026-07-29: a session limit killed five agents at once. One agent's
    uncommitted files were salvaged out of its worktree; another slice's work was
    lost. The only difference was somebody knowing to look. This is that
    knowledge as a computed verdict.

    SALVAGE FIRST when work exists ONLY in a worktree - uncommitted files, or
    commits that are ahead of the upstream. Both die with `git worktree prune`
    and neither is reproducible by re-running the slice, because the agent that
    would reproduce it is already gone.

    The primary worktree is excluded by default: the operator's own working tree
    is routinely dirty and that is not a stranding.
    """
    now_ts = time.time() if now_ts is None else now_ts
    manifest = manifest if isinstance(manifest, dict) else {}
    worktrees = worktrees if isinstance(worktrees, dict) else {}
    slices = manifest.get("slices")
    slices = slices if isinstance(slices, list) else []
    trees = worktrees.get("worktrees")
    trees = [t for t in trees if isinstance(t, dict)] if isinstance(trees, list) else []

    open_slices = [{
        "id": s.get("id"), "title": s.get("title"), "status": s.get("status"),
        "files": s.get("files") or [], "status_age_s": s.get("status_age_s"),
        "status_age_human": s.get("status_age_human", "-"),
    } for s in slices if isinstance(s, dict) and not s.get("committed")]

    # Slice ids appear in agent branch names (worktree-agent-<id>); the manifest
    # itself carries no worktree field yet, so claim-matching is by branch/path
    # substring and is reported as a hint, never as proof of ownership.
    claimed = {}
    for s in slices:
        if not isinstance(s, dict):
            continue
        sid = s.get("id")
        for t in trees:
            b = f"{t.get('branch') or ''} {t.get('path') or ''}"
            if sid and isinstance(sid, str) and sid.lower() in b.lower():
                claimed.setdefault(t.get("path"), []).append(sid)

    stranded, unpushed, orphans = [], [], []
    for t in trees:
        if t.get("primary") and not include_primary:
            continue
        path = t.get("path")
        row = {
            "path": path, "branch": t.get("branch"),
            "dirty_count": t.get("dirty_count", 0),
            "files": [d.get("path") for d in (t.get("dirty") or [])],
            "ahead": t.get("ahead"), "behind": t.get("behind"),
            "slices": claimed.get(path) or [],
            "status_ok": bool(t.get("status_ok")),
        }
        if row["dirty_count"] > 0:
            stranded.append(row)
        if (row["ahead"] or 0) > 0:
            unpushed.append(row)
        if not row["slices"]:
            orphans.append(row)

    reasons = []
    if stranded:
        held = sum(r["dirty_count"] for r in stranded)
        reasons.append(f"{len(stranded)} worktree(s) hold {held} uncommitted file(s)")
    if unpushed:
        reasons.append(f"{len(unpushed)} worktree(s) have unpushed commits")
    verdict = "SALVAGE FIRST" if reasons else "RESUME SAFE"
    if not reasons:
        reasons.append("no uncommitted or unpushed work outside the primary worktree")

    live = liveness if isinstance(liveness, dict) else {}
    return {
        "ok": True,
        "verdict": verdict,
        "salvage": verdict == "SALVAGE FIRST",
        "reasons": reasons,
        "open_slices": open_slices,
        "open_count": len(open_slices),
        "stranded": stranded,
        "unpushed": unpushed,
        "orphan_worktrees": orphans,
        "disjointness": disjointness_warnings(manifest),
        "run_state": live.get("state"),
        "stop_reason": live.get("stop_reason"),
        "inventory_ok": bool(worktrees.get("ok", False)),
        "checked_at": iso_from_epoch(now_ts),
    }


def tail_lines(path, n=5):
    """Last n non-empty lines of a text file, for the DEAD-only controller.log
    pin in P3. Read whole: controller.log is a few MB and a seek-based tail buys
    nothing at that size while adding a decode-boundary bug to maintain."""
    raw = _read_text(path)
    if raw is None:
        return []
    lines = [ln.rstrip() for ln in raw.splitlines() if ln.strip()]
    try:
        n = max(0, int(n))
    except (TypeError, ValueError):
        n = 5
    return lines[-n:] if n else []


# ----------------------------------------------------------- P1: the fleet


def _agent_jsonl_stats(path):
    """Walk one agent transcript for first/last event and output tokens.

    Non-atomic append, so a torn FINAL line is expected and discarded; a torn
    line anywhere else is counted. Streamed line by line rather than read into a
    list because these files reach tens of MB and the dashboard polls.
    """
    stats = {"events": 0, "torn_lines": 0, "output_tokens": 0,
             "start_epoch": None, "last_epoch": None}
    raw = _read_text(path)
    if raw is None:
        return stats
    lines = [ln for ln in raw.splitlines() if ln.strip()]
    for i, line in enumerate(lines):
        try:
            obj = json.loads(line)
        except ValueError:
            if i != len(lines) - 1:
                stats["torn_lines"] += 1
            continue
        if not isinstance(obj, dict):
            continue
        stats["events"] += 1
        epoch = parse_iso(obj.get("timestamp"))
        if epoch is not None:
            if stats["start_epoch"] is None or epoch < stats["start_epoch"]:
                stats["start_epoch"] = epoch
            if stats["last_epoch"] is None or epoch > stats["last_epoch"]:
                stats["last_epoch"] = epoch
        msg = obj.get("message")
        usage = msg.get("usage") if isinstance(msg, dict) else None
        if isinstance(usage, dict):
            tokens = _int_or_none(usage.get("output_tokens"))
            if tokens:
                stats["output_tokens"] += tokens
    return stats


def read_agent_fleet(session_dir, now_ts=None, *, running_within_s=AGENT_RUNNING_WITHIN_S):
    r"""The agent fleet from ~/.claude/projects/C--LegionWallpaper/<session>/subagents/.

    Accepts either the session dir or the subagents dir - the caller's notion of
    "session" varies and guessing wrong would silently return an empty fleet.

    agent-<id>.meta.json carries agentType / worktreePath / worktreeBranch /
    description. Presence of `worktreePath` IS the worktree-agent-vs-verifier
    discriminator; there is no type name that reliably separates them, since
    build agents run as general-purpose too.

    An agent with a meta file but no transcript yet is still reported: a lane
    that was dispatched and has produced nothing is exactly what an operator
    needs to see. Elapsed comes from the transcript's own first and last
    timestamps; mtime age is what separates running from finished, because a
    finished agent's file simply stops growing.

    AVAILABLE, NOT DURABLE. ~/.claude/settings.json sets no cleanupPeriodDays, so
    Claude Code's default reaping can delete all of this without warning. Absent
    is therefore a normal answer here, not an error.
    """
    now_ts = time.time() if now_ts is None else now_ts
    base = Path(session_dir)
    if base.name != "subagents" and (base / "subagents").is_dir():
        base = base / "subagents"
    out = {
        "ok": True,
        "present": False,
        "path": str(base),
        "agents": [],
        "counts": {"total": 0, "running": 0, "worktree": 0, "other": 0},
        "output_tokens": 0,
        "checked_at": iso_from_epoch(now_ts),
    }
    try:
        metas = sorted(base.glob("agent-*.meta.json"))
    except (OSError, ValueError):
        return out
    if not base.is_dir():
        return out
    out["present"] = True

    for meta_path in metas:
        data, _ = _read_json(meta_path)
        if not isinstance(data, dict):
            data = {}
        agent_id = meta_path.name[len("agent-"):-len(".meta.json")]
        jsonl = base / f"agent-{agent_id}.jsonl"
        stats = _agent_jsonl_stats(jsonl)
        mtime = _mtime(jsonl)
        mtime_age = _age(now_ts, mtime)
        start = stats["start_epoch"]
        last = stats["last_epoch"]
        elapsed = None
        if start is not None and last is not None:
            elapsed = max(0.0, last - start)
        worktree_path = _str_or_none(data.get("worktreePath"))
        running = mtime_age is not None and mtime_age <= running_within_s
        agent = {
            "id": agent_id,
            "type": _str_or_none(data.get("agentType")) or "unknown",
            "description": _str_or_none(data.get("description")) or "",
            "worktree_path": worktree_path,
            "worktree_branch": _str_or_none(data.get("worktreeBranch")),
            "is_worktree_agent": worktree_path is not None,
            "spawn_depth": _int_or_none(data.get("spawnDepth")),
            "transcript_present": mtime is not None,
            "start": iso_from_epoch(start),
            "start_epoch": start,
            "last_event": iso_from_epoch(last),
            "last_event_epoch": last,
            "elapsed_s": elapsed,
            "elapsed_human": human_age(elapsed),
            "idle_s": mtime_age,
            "idle_human": human_age(mtime_age),
            "running": bool(running),
            "events": stats["events"],
            "torn_lines": stats["torn_lines"],
            "output_tokens": stats["output_tokens"],
        }
        out["agents"].append(agent)
        out["counts"]["total"] += 1
        out["counts"]["running"] += 1 if running else 0
        if agent["is_worktree_agent"]:
            out["counts"]["worktree"] += 1
        else:
            out["counts"]["other"] += 1
        out["output_tokens"] += agent["output_tokens"]

    # Newest first: the lane that moved last is the one being watched. Agents
    # with no transcript sort last rather than being dropped.
    out["agents"].sort(key=lambda a: (a["last_event_epoch"] is None, -(a["last_event_epoch"] or 0)))
    return out
