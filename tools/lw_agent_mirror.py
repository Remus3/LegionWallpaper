#!/usr/bin/env python
r"""Mirror the at-risk agent fleet metadata into ops/runtime/ before it is reaped.

Spec docs/RUNDASH_SPEC_2026-08-01.md, instrumentation backlog item 6.

Every fleet fact the dashboard shows - which agent owned which worktree, when it
started, what it spent - is reconstructed live from
`~/.claude/projects/C--LegionWallpaper/<session>/subagents/`. The spec's census
lane proved that works by rebuilding the whole 2026-07-30 fleet from it. The
same lane found the catch: `~/.claude/settings.json` sets no `cleanupPeriodDays`,
so Claude Code's default reaping can delete all of it without warning, and the
dir was already 596 MB. AVAILABLE, NOT DURABLE.

This is the durability half, and it is a separate tool rather than a hook inside
the dashboard on purpose: the dashboard is read-only over run state and is not
always running, and the window this has to cover is exactly the window in which
nobody is watching.

Two rules, each because the naive version is wrong:

  NEVER REGRESS A COUNT. A poll that catches a truncated or half-reaped
  transcript reads FEWER events and FEWER tokens. That is a loss of information,
  not news, so counts move one way only.

  NEVER MIRROR A VOLATILE VERDICT. `running` and `idle_s` are true only at the
  instant they were measured. A stored `running: true` from four days ago paints
  a live agent on the board that does not exist. Only raw timestamps are stored;
  the verdict is re-derived at read time, where a mirrored agent is running by
  definition never - nothing is appending to a transcript that is gone.

Usage:
  C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe tools/lw_agent_mirror.py [--session DIR]... [--target PATH] [--quiet]
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lw_rundash_state as rundash_state  # noqa: E402  (sibling tool, not a package)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TARGET = ROOT / "ops" / "runtime" / "agent_fleet_mirror.json"
PROJECT_SESSIONS = (Path.home() / ".claude" / "projects" / "C--LegionWallpaper")

SCHEMA = 1

# Carried verbatim from the live fleet record. Deliberately NOT `running` or
# `idle_s` - see the module docstring - and deliberately NOT `transcript_present`,
# which describes the source dir rather than the agent.
STATIC_FIELDS = ("type", "description", "worktree_path", "worktree_branch",
                 "is_worktree_agent", "spawn_depth")

# Counts that may only ever grow.
MONOTONE_FIELDS = ("events", "output_tokens", "torn_lines")


def discover_sessions(base=PROJECT_SESSIONS):
    """Every session dir under the project transcript root. Never raises."""
    try:
        return sorted(p for p in Path(base).iterdir()
                      if p.is_dir() and (p / "subagents").is_dir())
    except (OSError, ValueError):
        return []


def load_mirror(path):
    """(mirror dict, rebuilt) - an unusable file is REBUILT, not raised on.

    Losing a corrupt mirror costs the reaped history it held. Refusing to write
    because of it costs the history not yet captured, which is strictly worse:
    the first failure is bounded and the second compounds every poll.
    """
    data, _ = rundash_state._read_json(path)
    if isinstance(data, dict) and isinstance(data.get("agents"), dict):
        return data, False
    rebuilt = Path(path).exists()
    return {"schema": SCHEMA, "agents": {}}, rebuilt


def merge_agent(old, new, now_iso):
    """One mirrored record from a previous one (may be None) and a live read."""
    rec = dict(old or {})
    rec["id"] = new["id"]
    for field in STATIC_FIELDS:
        rec[field] = new[field]
    for field in MONOTONE_FIELDS:
        rec[field] = max(new.get(field) or 0, rec.get(field) or 0)
    # Widen the observed window from both ends: the earliest start and the
    # latest event ever seen. A later read that lost the head of the transcript
    # must not be able to move the start forward.
    for field, better in (("start_epoch", min), ("last_event_epoch", max)):
        vals = [v for v in (rec.get(field), new.get(field)) if v is not None]
        rec[field] = better(vals) if vals else None
    rec["start"] = rundash_state.iso_from_epoch(rec["start_epoch"])
    rec["last_event"] = rundash_state.iso_from_epoch(rec["last_event_epoch"])
    if rec["start_epoch"] is not None and rec["last_event_epoch"] is not None:
        rec["elapsed_s"] = max(0.0, rec["last_event_epoch"] - rec["start_epoch"])
    else:
        rec["elapsed_s"] = None
    rec["session"] = new.get("session") or rec.get("session")
    rec.setdefault("first_mirrored", now_iso)
    rec["last_mirrored"] = now_iso
    return rec


def write_mirror_atomic(mirror, path):
    """tmp sibling then replace (CLAUDE.md atomic-write hard rule)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(mirror, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def mirror_fleet(session_dirs, target, now_ts=None):
    """Fold every session's live fleet into the mirror at `target`.

    Absent sessions and absent agents are NORMAL - reaping is the expected case,
    and an agent the source no longer holds is exactly what the mirror is for,
    so nothing is ever removed here.
    """
    now_ts = time.time() if now_ts is None else now_ts
    now_iso = rundash_state.iso_from_epoch(now_ts)
    out = {"ok": True, "target": str(target), "mirrored": 0, "sessions": 0,
           "rebuilt": False, "total": 0, "checked_at": now_iso}
    mirror, out["rebuilt"] = load_mirror(target)
    agents = mirror["agents"]

    for session_dir in session_dirs or []:
        fleet = rundash_state.read_agent_fleet(session_dir, now_ts)
        if not fleet["present"]:
            continue
        out["sessions"] += 1
        for agent in fleet["agents"]:
            live = dict(agent, session=str(session_dir))
            agents[agent["id"]] = merge_agent(agents.get(agent["id"]), live, now_iso)
            out["mirrored"] += 1

    mirror["schema"] = SCHEMA
    mirror["updated"] = now_iso
    try:
        write_mirror_atomic(mirror, target)
    except OSError as exc:
        out["ok"] = False
        out["error"] = type(exc).__name__
    out["total"] = len(agents)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--session", action="append", default=None,
                    help="a session dir to mirror; repeatable. Default: every "
                         "session under the project transcript root")
    ap.add_argument("--target", default=str(DEFAULT_TARGET))
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    sessions = [Path(s) for s in args.session] if args.session else discover_sessions()
    out = mirror_fleet(sessions, args.target)
    if not args.quiet:
        print(json.dumps({k: out[k] for k in
                          ("ok", "sessions", "mirrored", "total", "rebuilt")}))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
