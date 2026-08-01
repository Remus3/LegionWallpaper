"""The fleet record has to outlive the transcript dir it is read from.

Spec item 6. Every fleet fact the dashboard shows - which agent owned which
worktree, when it started, what it spent - is reconstructed live from
`~/.claude/projects/C--LegionWallpaper/<session>/subagents/`. That directory is
AVAILABLE, NOT DURABLE: `~/.claude/settings.json` sets no `cleanupPeriodDays`,
so Claude Code's default reaping can delete the whole 2026-07-30 fleet without
warning, and the dir was already 596 MB when the spec was written.

This mirror is the durability half. Two rules it exists to enforce:

  NEVER REGRESS A COUNT. A later read that catches a truncated or half-reaped
  transcript must not overwrite a bigger earlier observation with a smaller one.

  NEVER MIRROR A VOLATILE VERDICT. `running` and `idle_s` are true only at the
  instant they were measured. A stored `running: true` from four days ago is a
  live agent on the board that does not exist, so only the raw timestamps are
  mirrored and the verdict is re-derived at read time.
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import lw_agent_mirror as mirror  # noqa: E402
import lw_rundash_state as st  # noqa: E402


def session(tmp_path, agents, name="session"):
    """agents: list of (id, meta dict, list of jsonl event dicts or None)."""
    base = tmp_path / name / "subagents"
    base.mkdir(parents=True, exist_ok=True)
    for agent_id, meta, events in agents:
        (base / f"agent-{agent_id}.meta.json").write_text(
            json.dumps(meta), encoding="utf-8")
        if events is not None:
            (base / f"agent-{agent_id}.jsonl").write_text(
                "".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
    return tmp_path / name


def event(ts, out_tokens=0):
    return {"timestamp": ts, "message": {"usage": {"output_tokens": out_tokens}}}


WORKER = {"agentType": "general-purpose", "description": "slice B4",
          "worktreePath": "C:/LegionWallpaper/worktrees/b4",
          "worktreeBranch": "slice/b4", "spawnDepth": 1}


# ------------------------------------------------------------- the mirroring


def test_it_captures_the_fields_that_die_with_the_transcript_dir(tmp_path):
    sess = session(tmp_path, [("a1", WORKER, [event("2026-07-30T12:00:00Z", 100),
                                              event("2026-07-30T12:05:00Z", 50)])])
    target = tmp_path / "mirror.json"
    out = mirror.mirror_fleet([sess], target, now_ts=time.time())

    assert out["mirrored"] == 1
    rec = json.loads(target.read_text(encoding="utf-8"))["agents"]["a1"]
    assert rec["type"] == "general-purpose"
    assert rec["worktree_branch"] == "slice/b4"
    assert rec["is_worktree_agent"] is True
    assert rec["output_tokens"] == 150
    assert rec["events"] == 2
    assert rec["description"] == "slice B4"


def test_a_volatile_verdict_is_never_stored_only_the_stamps_it_came_from(tmp_path):
    sess = session(tmp_path, [("a1", WORKER, [event("2026-07-30T12:00:00Z")])])
    target = tmp_path / "mirror.json"
    mirror.mirror_fleet([sess], target, now_ts=time.time())
    rec = json.loads(target.read_text(encoding="utf-8"))["agents"]["a1"]

    assert "running" not in rec
    assert "idle_s" not in rec
    assert rec["last_event_epoch"] is not None


def test_a_later_thinner_read_never_shrinks_what_was_already_seen(tmp_path):
    sess = session(tmp_path, [("a1", WORKER, [event("2026-07-30T12:00:00Z", 100),
                                              event("2026-07-30T12:05:00Z", 400)])])
    target = tmp_path / "mirror.json"
    mirror.mirror_fleet([sess], target, now_ts=time.time())

    # The transcript is half-reaped between polls: fewer events, fewer tokens,
    # a later start. Every one of those is a LOSS of information, not news.
    session(tmp_path, [("a1", WORKER, [event("2026-07-30T12:05:00Z", 10)])])
    mirror.mirror_fleet([sess], target, now_ts=time.time())
    rec = json.loads(target.read_text(encoding="utf-8"))["agents"]["a1"]

    assert rec["output_tokens"] == 500
    assert rec["events"] == 2
    assert rec["start"] == "2026-07-30T12:00:00Z"


def test_a_still_growing_agent_does_update_the_record(tmp_path):
    sess = session(tmp_path, [("a1", WORKER, [event("2026-07-30T12:00:00Z", 100)])])
    target = tmp_path / "mirror.json"
    mirror.mirror_fleet([sess], target, now_ts=time.time())
    session(tmp_path, [("a1", WORKER, [event("2026-07-30T12:00:00Z", 100),
                                       event("2026-07-30T12:09:00Z", 100)])])
    mirror.mirror_fleet([sess], target, now_ts=time.time())
    rec = json.loads(target.read_text(encoding="utf-8"))["agents"]["a1"]

    assert rec["output_tokens"] == 200
    assert rec["last_event"] == "2026-07-30T12:09:00Z"
    assert rec["elapsed_s"] == 540.0


def test_an_agent_the_dir_no_longer_holds_stays_in_the_mirror(tmp_path):
    # The whole point. Reaping must not propagate into the mirror.
    sess = session(tmp_path, [("a1", WORKER, [event("2026-07-30T12:00:00Z")])])
    target = tmp_path / "mirror.json"
    mirror.mirror_fleet([sess], target, now_ts=time.time())
    for leftover in (sess / "subagents").glob("agent-a1.*"):
        leftover.unlink()
    out = mirror.mirror_fleet([sess], target, now_ts=time.time())

    assert out["mirrored"] == 0
    assert "a1" in json.loads(target.read_text(encoding="utf-8"))["agents"]


def test_first_and_last_mirrored_stamps_bound_when_it_was_observable(tmp_path):
    sess = session(tmp_path, [("a1", WORKER, [event("2026-07-30T12:00:00Z")])])
    target = tmp_path / "mirror.json"
    mirror.mirror_fleet([sess], target, now_ts=1000.0)
    mirror.mirror_fleet([sess], target, now_ts=9000.0)
    rec = json.loads(target.read_text(encoding="utf-8"))["agents"]["a1"]

    assert rec["first_mirrored"] == st.iso_from_epoch(1000.0)
    assert rec["last_mirrored"] == st.iso_from_epoch(9000.0)


def test_two_sessions_mirror_side_by_side_and_each_keeps_its_own(tmp_path):
    s1 = session(tmp_path, [("a1", WORKER, [event("2026-07-30T12:00:00Z")])], "s1")
    s2 = session(tmp_path, [("b2", WORKER, [event("2026-07-31T12:00:00Z")])], "s2")
    target = tmp_path / "mirror.json"
    mirror.mirror_fleet([s1, s2], target, now_ts=time.time())
    agents = json.loads(target.read_text(encoding="utf-8"))["agents"]

    assert set(agents) == {"a1", "b2"}
    assert agents["a1"]["session"].endswith("s1")


# --------------------------------------------------------------- fail-soft


def test_a_missing_session_dir_mirrors_nothing_and_raises_nothing(tmp_path):
    out = mirror.mirror_fleet([tmp_path / "gone"], tmp_path / "mirror.json",
                              now_ts=time.time())
    assert out["mirrored"] == 0
    assert out["ok"] is True


def test_a_corrupt_mirror_is_rebuilt_rather_than_crashing_the_writer(tmp_path):
    target = tmp_path / "mirror.json"
    target.write_text("{not json", encoding="utf-8")
    sess = session(tmp_path, [("a1", WORKER, [event("2026-07-30T12:00:00Z")])])
    out = mirror.mirror_fleet([sess], target, now_ts=time.time())

    assert out["mirrored"] == 1
    assert out["rebuilt"] is True
    assert "a1" in json.loads(target.read_text(encoding="utf-8"))["agents"]


def test_the_write_is_atomic_and_leaves_no_tmp_behind(tmp_path):
    sess = session(tmp_path, [("a1", WORKER, [event("2026-07-30T12:00:00Z")])])
    mirror.mirror_fleet([sess], tmp_path / "mirror.json", now_ts=time.time())
    assert not list(tmp_path.glob("*.tmp"))


# ----------------------------------------------------------- the read side


def test_the_reader_unions_live_agents_with_mirrored_ones(tmp_path):
    target = tmp_path / "mirror.json"
    sess = session(tmp_path, [("gone", WORKER, [event("2026-07-30T12:00:00Z", 90)])])
    mirror.mirror_fleet([sess], target, now_ts=time.time())
    for leftover in (sess / "subagents").glob("agent-gone.*"):
        leftover.unlink()
    now = time.time()
    session(tmp_path, [("live", WORKER, [event(st.iso_from_epoch(now))])])

    fleet = st.read_agent_fleet(sess, now, mirror_path=target)
    by_id = {a["id"]: a for a in fleet["agents"]}

    assert by_id["live"]["source"] == "live"
    assert by_id["gone"]["source"] == "mirror"
    assert by_id["gone"]["output_tokens"] == 90
    assert fleet["counts"]["mirrored"] == 1


def test_a_mirrored_agent_is_never_reported_running(tmp_path):
    # It cannot be: nothing is appending to a transcript that no longer exists.
    target = tmp_path / "mirror.json"
    now = time.time()
    sess = session(tmp_path, [("gone", WORKER, [event(st.iso_from_epoch(now))])])
    mirror.mirror_fleet([sess], target, now_ts=now)
    for leftover in (sess / "subagents").glob("agent-gone.*"):
        leftover.unlink()

    fleet = st.read_agent_fleet(sess, now, mirror_path=target)
    gone, = [a for a in fleet["agents"] if a["id"] == "gone"]

    assert gone["running"] is False
    assert fleet["counts"]["running"] == 0


def test_a_live_agent_wins_over_its_own_mirrored_copy(tmp_path):
    target = tmp_path / "mirror.json"
    now = time.time()
    sess = session(tmp_path, [("a1", WORKER, [event("2026-07-30T12:00:00Z", 5)])])
    mirror.mirror_fleet([sess], target, now_ts=now)
    session(tmp_path, [("a1", WORKER, [event("2026-07-30T12:00:00Z", 5),
                                       event(st.iso_from_epoch(now), 7)])])

    fleet = st.read_agent_fleet(sess, now, mirror_path=target)
    a1, = fleet["agents"]

    assert a1["source"] == "live"
    assert a1["output_tokens"] == 12
    assert fleet["counts"]["total"] == 1


def test_the_board_stays_scoped_to_this_session_and_says_how_many_it_holds(tmp_path):
    # The mirror holds every session ever observed - 136 agents across 36
    # sessions the first time it ran on this machine. Unioning all of them into
    # the run board would bury the live fleet under a month of history, so the
    # panel is scoped and the total is REPORTED rather than silently dropped.
    target = tmp_path / "mirror.json"
    now = time.time()
    s1 = session(tmp_path, [("a1", WORKER, [event("2026-07-30T12:00:00Z")])], "s1")
    s2 = session(tmp_path, [("b2", WORKER, [event("2026-07-31T12:00:00Z")])], "s2")
    mirror.mirror_fleet([s1, s2], target, now_ts=now)

    fleet = st.read_agent_fleet(s1, now, mirror_path=target)

    assert [a["id"] for a in fleet["agents"]] == ["a1"]
    assert fleet["mirror_total"] == 2


def test_no_mirror_path_is_the_old_behaviour_exactly(tmp_path):
    now = time.time()
    sess = session(tmp_path, [("a1", WORKER, [event("2026-07-30T12:00:00Z")])])
    assert st.read_agent_fleet(sess, now)["counts"]["mirrored"] == 0
