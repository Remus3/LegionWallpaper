"""P6 Fleet History - what the mirror knows that the disk no longer does.

Item 6 made the fleet durable: 136 agents across 35 sessions, back to
2026-07-03, survive Claude Code's reaping. Nothing read them. This panel does.

It answers two questions the live fleet view cannot:

  WHERE DID THE TOKENS GO. Per-session output-token spend, newest first, so an
  expensive run is visible as a run rather than as 20 agent rows.

  WHAT HAS ALREADY BEEN LOST. Every session is labelled by whether its source
  transcripts still exist. `mirror only` means reaping has been there and this
  file is now the ONLY copy - which is the fact that decides whether the mirror
  is doing its job or quietly failing to run.

The rule inherited from P5: never present a derived number as an observation.
A session whose agents carry no timestamps has an unknown span, and that renders
as unknown, not as zero.
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import lw_agent_mirror as mirror  # noqa: E402
import lw_rundash_state as st  # noqa: E402


def iso(epoch):
    return st.iso_from_epoch(epoch)


WORKER = {"agentType": "general-purpose", "description": "slice B4",
          "worktreePath": "C:/LW/worktrees/b4", "worktreeBranch": "slice/b4",
          "spawnDepth": 1}
VERIFIER = {"agentType": "verifier", "description": "verify B4", "spawnDepth": 1}


def event(ts, out_tokens=0):
    return {"timestamp": ts, "message": {"usage": {"output_tokens": out_tokens}}}


def session(tmp_path, name, agents):
    base = tmp_path / "transcripts" / name / "subagents"
    base.mkdir(parents=True, exist_ok=True)
    for agent_id, meta, events in agents:
        (base / f"agent-{agent_id}.meta.json").write_text(json.dumps(meta),
                                                          encoding="utf-8")
        (base / f"agent-{agent_id}.jsonl").write_text(
            "".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
    return tmp_path / "transcripts" / name


def reap(session_dir):
    """What Claude Code's cleanup does: the transcripts go, the mirror stays."""
    for leftover in (session_dir / "subagents").glob("*"):
        leftover.unlink()
    (session_dir / "subagents").rmdir()
    session_dir.rmdir()


def built(tmp_path, sessions, **kw):
    target = tmp_path / "mirror.json"
    mirror.mirror_fleet(sessions, target, now_ts=kw.pop("mirror_at", 1000.0))
    return target


# ------------------------------------------------------------ the grouping


def test_a_session_is_one_row_carrying_its_fleet_and_its_spend(tmp_path):
    s = session(tmp_path, "sess-a", [
        ("a1", WORKER, [event("2026-07-30T12:00:00Z", 100),
                        event("2026-07-30T12:10:00Z", 300)]),
        ("a2", VERIFIER, [event("2026-07-30T12:05:00Z", 50)]),
    ])
    hist = st.read_fleet_history(built(tmp_path, [s]), now_ts=time.time())

    row, = hist["sessions"]
    assert row["session_id"] == "sess-a"
    assert row["agent_count"] == 2
    assert row["worktree_count"] == 1
    assert row["output_tokens"] == 450
    assert row["first_start"] == "2026-07-30T12:00:00Z"
    assert row["last_event"] == "2026-07-30T12:10:00Z"
    assert row["span_human"] == "10m"


def test_sessions_come_back_newest_first(tmp_path):
    old = session(tmp_path, "old", [("a1", WORKER, [event("2026-07-03T12:00:00Z")])])
    new = session(tmp_path, "new", [("b1", WORKER, [event("2026-07-30T12:00:00Z")])])
    hist = st.read_fleet_history(built(tmp_path, [old, new]), now_ts=time.time())

    assert [r["session_id"] for r in hist["sessions"]] == ["new", "old"]


def test_a_session_whose_agents_carry_no_stamps_has_an_unknown_span(tmp_path):
    # P5's rule, applied here: a derived number is never presented as an
    # observation. Zero would read as "ran instantly".
    s = session(tmp_path, "sess-a", [("a1", WORKER, [{"no": "timestamp"}])])
    hist = st.read_fleet_history(built(tmp_path, [s]), now_ts=time.time())

    row, = hist["sessions"]
    assert row["span_s"] is None
    assert row["span_human"] == "-"


# ------------------------------------------------- what has already been lost


def test_a_session_still_on_disk_is_labelled_live_backed(tmp_path):
    s = session(tmp_path, "sess-a", [("a1", WORKER, [event("2026-07-30T12:00:00Z")])])
    hist = st.read_fleet_history(built(tmp_path, [s]), now_ts=time.time())

    row, = hist["sessions"]
    assert row["source_present"] is True
    assert row["mirror_only"] is False
    assert row["agents_on_disk"] == 1


def test_a_reaped_session_is_mirror_only_and_that_is_the_headline(tmp_path):
    s = session(tmp_path, "sess-a", [("a1", WORKER, [event("2026-07-30T12:00:00Z", 7)])])
    target = built(tmp_path, [s])
    reap(s)
    hist = st.read_fleet_history(target, now_ts=time.time())

    row, = hist["sessions"]
    assert row["mirror_only"] is True
    assert row["agents_on_disk"] == 0
    assert row["output_tokens"] == 7
    assert hist["totals"]["mirror_only_sessions"] == 1
    assert hist["totals"]["mirror_only_agents"] == 1


def test_a_half_reaped_session_reports_both_numbers(tmp_path):
    # Reaping is per-file, not per-session. "2 of 3 still on disk" is the state
    # that says the mirror is earning its keep RIGHT NOW.
    s = session(tmp_path, "sess-a", [
        ("a1", WORKER, [event("2026-07-30T12:00:00Z")]),
        ("a2", WORKER, [event("2026-07-30T12:01:00Z")]),
        ("a3", WORKER, [event("2026-07-30T12:02:00Z")]),
    ])
    target = built(tmp_path, [s])
    for leftover in (s / "subagents").glob("agent-a3.*"):
        leftover.unlink()
    hist = st.read_fleet_history(target, now_ts=time.time())

    row, = hist["sessions"]
    assert row["agent_count"] == 3
    assert row["agents_on_disk"] == 2
    assert row["mirror_only"] is False


# ----------------------------------------------------------------- totals


def test_the_totals_bound_the_whole_record(tmp_path):
    a = session(tmp_path, "a", [("a1", WORKER, [event("2026-07-03T12:00:00Z", 10)])])
    b = session(tmp_path, "b", [("b1", VERIFIER, [event("2026-07-30T12:00:00Z", 20)]),
                                ("b2", WORKER, [event("2026-07-30T13:00:00Z", 30)])])
    hist = st.read_fleet_history(built(tmp_path, [a, b]), now_ts=time.time())
    t = hist["totals"]

    assert t["sessions"] == 2
    assert t["agents"] == 3
    assert t["worktree_agents"] == 2
    assert t["output_tokens"] == 60
    assert t["oldest"] == "2026-07-03T12:00:00Z"
    assert t["newest"] == "2026-07-30T13:00:00Z"


def test_an_absent_mirror_is_an_empty_history_not_a_crash(tmp_path):
    hist = st.read_fleet_history(tmp_path / "gone.json", now_ts=time.time())
    assert hist["present"] is False
    assert hist["sessions"] == []
    assert hist["totals"]["agents"] == 0


def test_a_corrupt_mirror_degrades_to_empty_rather_than_raising(tmp_path):
    p = tmp_path / "mirror.json"
    p.write_text("{not json", encoding="utf-8")
    hist = st.read_fleet_history(p, now_ts=time.time())
    assert hist["present"] is False
    assert hist["sessions"] == []


# ------------------------------------------------------------- the top agents


def test_each_session_names_its_biggest_spenders_not_all_of_them(tmp_path):
    # 136 agents will not fit on a panel and were never the unit of the
    # question. The top few per session are what makes a spend actionable.
    s = session(tmp_path, "sess-a", [
        (f"a{i}", WORKER, [event("2026-07-30T12:00:00Z", i * 100)])
        for i in range(1, 6)])
    hist = st.read_fleet_history(built(tmp_path, [s]), now_ts=time.time(),
                                 top_agents=2)

    row, = hist["sessions"]
    assert [a["output_tokens"] for a in row["top_agents"]] == [500, 400]
    assert row["top_agents_shown"] == 2
    assert row["agent_count"] == 5


# --------------------------------------------------------------- the join


def test_a_session_the_cycle_chain_knows_is_labelled_with_its_run(tmp_path):
    s = session(tmp_path, "sess-a", [("a1", WORKER, [event("2026-07-30T12:00:00Z")])])
    join = {"runs": [{"run_id": "7dd1dc02", "session_ids": ["sess-a"],
                      "manifest_run_ids": ["2026-07-30-01"], "cycle_count": 3}],
            "by_session_id": {"sess-a": ["7dd1dc02"]}, "by_manifest_run_id": {},
            "unjoined_cycles": 0}
    hist = st.read_fleet_history(built(tmp_path, [s]), now_ts=time.time(), join=join)

    row, = hist["sessions"]
    assert row["run_id"] == "7dd1dc02"
    assert row["manifest_run_id"] == "2026-07-30-01"


def test_a_session_nothing_pairs_is_left_unlabelled_never_guessed(tmp_path):
    # Same rule as the header join: adjacency is not evidence. Today NO cycle
    # record on this machine carries a session_id, so every row is unlabelled -
    # which is the truth, and it makes the missing instrumentation visible.
    s = session(tmp_path, "sess-a", [("a1", WORKER, [event("2026-07-30T12:00:00Z")])])
    join = {"runs": [{"run_id": "7dd1dc02", "session_ids": [],
                      "manifest_run_ids": ["2026-07-30-01"], "cycle_count": 3}],
            "by_session_id": {}, "by_manifest_run_id": {}, "unjoined_cycles": 0}
    hist = st.read_fleet_history(built(tmp_path, [s]), now_ts=time.time(), join=join)

    row, = hist["sessions"]
    assert row["run_id"] is None
    assert row["manifest_run_id"] is None
