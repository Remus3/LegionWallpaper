"""Tests for tools/lw_rundash_state.py - the pure run-state readers (slice B2).

Every case injects its paths, its clock and its cache, so nothing here starts a
server, spawns git, or reads the real images/ tree, the real
ops/loop/control/, or the operator's transcript dir. Same posture as the
build_pipeline_view half of tests/test_lw_monitor.py.

Two things get disproportionate coverage on purpose:

  LIVENESS - the recycled-pid case (live pid, five-day-old lock) is the defect
  that wedged the loop for five days and that a bare pid check cannot see.

  TORN INPUT - directive_history.jsonl and every agent .jsonl are non-atomic
  appends. A dashboard that raises on a half-written line is useless precisely
  when it is needed.
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import lw_rundash_state as rd  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

T = 1800000000.0  # fixed injected "now" so every age is exact, not approximate
STALE = rd.FALLBACK_STALE_AFTER  # 16200.0


def iso(epoch):
    return rd.iso_from_epoch(epoch)


def _load_slots():
    spec = importlib.util.spec_from_file_location(
        "lw_slots_for_rundash_test", ROOT / "ops" / "loop" / "slots.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


# ------------------------------------------------------------- primitives


def test_default_stale_after_tracks_slots():
    """The fallback constant must equal the authority it stands in for.

    slots.py is byte-identical-by-contract with the sibling repo and is never
    edited from here, so this is the only thing stopping a silent drift between
    the controller's stale window and the dashboard's.
    """
    assert rd.default_stale_after(ROOT) == _load_slots().DEFAULT_STALE_AFTER
    assert rd.FALLBACK_STALE_AFTER == _load_slots().DEFAULT_STALE_AFTER


def test_default_stale_after_falls_back_when_slots_missing(tmp_path):
    assert rd.default_stale_after(tmp_path) == rd.FALLBACK_STALE_AFTER


def test_default_pid_alive_fails_closed_without_slots(tmp_path):
    # An unverifiable pid reported as alive would recreate the false green.
    assert rd.default_pid_alive(tmp_path)(4242) is False


def test_parse_iso_handles_z_naive_and_garbage():
    assert rd.parse_iso("1970-01-01T00:00:00Z") == 0.0
    assert rd.parse_iso("1970-01-01T00:00:01.500Z") == pytest.approx(1.5)
    assert rd.parse_iso("not a date") is None
    assert rd.parse_iso(None) is None
    assert rd.parse_iso("") is None
    # A naive stamp is local time, so it must parse to SOMETHING (the producer
    # writes time.strftime with no offset) - just not to the UTC reading.
    assert rd.parse_iso("2026-07-27T00:02:19") is not None


def test_human_age_never_blank_for_unknown():
    assert rd.human_age(None) == "-"
    assert rd.human_age("x") == "-"
    assert rd.human_age(30) == "30s"
    assert rd.human_age(600) == "10m"
    assert rd.human_age(7200) == "2h"
    assert rd.human_age(400000) == "4d"


# ------------------------------------------------------- read_slice_manifest


def write_manifest(tmp_path, payload):
    p = tmp_path / "slice_manifest.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def sample_manifest():
    return {
        "schema": 1,
        "run_id": "2026-08-01-01",
        "head": "55b9e95",
        "created": iso(T - 7200),
        "updated": iso(T - 60),
        "slices": [
            {"id": "B1", "title": "extract scaffold", "files": ["tools/lw_httpd.py"],
             "status": "committed", "commit": "abc1234", "note": "", "updated": iso(T - 3600)},
            {"id": "B2", "title": "pure readers", "files": ["tools/lw_rundash_state.py"],
             "status": "in_progress", "commit": None, "note": "", "updated": iso(T - 900)},
        ],
    }


def test_manifest_normalizes_slices_and_status_age(tmp_path):
    m = rd.read_slice_manifest(write_manifest(tmp_path, sample_manifest()), now_ts=T, cache={})
    assert m["ok"] is True and m["present"] is True and m["stale"] is False
    assert m["run_id"] == "2026-08-01-01" and m["head"] == "55b9e95"
    ids = [s["id"] for s in m["slices"]]
    assert ids == ["B1", "B2"]
    b1, b2 = m["slices"]
    assert b1["committed"] is True and b1["commit"] == "abc1234"
    assert b2["committed"] is False
    assert b2["status_age_s"] == pytest.approx(900.0)
    assert b2["status_age_human"] == "15m"
    assert m["counts"]["committed"] == 1 and m["counts"]["in_progress"] == 1
    assert m["counts"]["failed"] == 0  # a status nobody used still reports zero
    assert m["open_count"] == 1


def test_manifest_absent_returns_normalized_empty(tmp_path):
    m = rd.read_slice_manifest(tmp_path / "nope.json", now_ts=T, cache={})
    assert m["ok"] is True and m["present"] is False
    assert m["slices"] == [] and m["open_count"] == 0
    assert m["counts"] == {s: 0 for s in rd.SLICE_STATUSES}


def test_manifest_corrupt_with_no_last_good_is_empty_not_raising(tmp_path):
    p = tmp_path / "slice_manifest.json"
    p.write_text('{"slices": [', encoding="utf-8")
    m = rd.read_slice_manifest(p, now_ts=T, cache={})
    assert m["present"] is False and m["stale"] is False and m["slices"] == []


def test_manifest_mid_write_serves_last_good_flagged_stale(tmp_path):
    cache = {}
    p = write_manifest(tmp_path, sample_manifest())
    rd.read_slice_manifest(p, now_ts=T, cache=cache)
    p.write_text('{"slices": [{"id": "B1"', encoding="utf-8")  # caught mid-swap
    m = rd.read_slice_manifest(p, now_ts=T + 5, cache=cache)
    assert m["present"] is True and m["stale"] is True
    assert m["stale_since"] == iso(T)
    assert [s["id"] for s in m["slices"]] == ["B1", "B2"]


def test_manifest_wrong_types_do_not_raise(tmp_path):
    p = write_manifest(tmp_path, {"run_id": 17, "slices": "not-a-list"})
    m = rd.read_slice_manifest(p, now_ts=T, cache={})
    assert m["present"] is True and m["slices"] == []
    p2 = write_manifest(tmp_path, ["a", "list", "at", "top", "level"])
    assert rd.read_slice_manifest(p2, now_ts=T, cache={})["slices"] == []
    p3 = write_manifest(tmp_path, {"slices": [None, 5, {"id": None, "files": "x", "status": None}]})
    m3 = rd.read_slice_manifest(p3, now_ts=T, cache={})
    assert len(m3["slices"]) == 1
    assert m3["slices"][0]["id"] == "slice-3" and m3["slices"][0]["files"] == []
    assert m3["slices"][0]["status"] == "pending"


def test_manifest_unparsable_updated_gives_unknown_age(tmp_path):
    p = write_manifest(tmp_path, {"slices": [
        {"id": "X", "status": "pending", "updated": "yesterday-ish"}]})
    s = rd.read_slice_manifest(p, now_ts=T, cache={})["slices"][0]
    assert s["status_age_s"] is None and s["status_age_human"] == "-"


def test_disjointness_flags_only_non_committed_overlap(tmp_path):
    p = write_manifest(tmp_path, {"slices": [
        {"id": "A", "status": "in_progress", "files": ["tools/x.py", "tools/y.py"]},
        {"id": "B", "status": "pending", "files": ["tools/x.py"]},
        {"id": "C", "status": "committed", "files": ["tools/y.py"]},
    ]})
    warn = rd.disjointness_warnings(rd.read_slice_manifest(p, now_ts=T, cache={}))
    assert warn == [{"file": "tools/x.py", "slices": ["A", "B"]}]
    assert rd.disjointness_warnings(None) == []


# --------------------------------------------------- verdict history (P2)


def test_a_slice_with_no_verdict_field_reads_as_an_empty_history(tmp_path):
    # Absence is the NOT OBSERVED state. Every manifest written before the
    # verdict subcommand existed lands here, and none of them may read as
    # verified by omission.
    m = rd.read_slice_manifest(write_manifest(tmp_path, sample_manifest()), now_ts=T, cache={})
    assert m["slices"][0]["verdicts"] == []
    assert m["slices"][0]["verdict_count"] == 0


def test_the_verdict_history_is_carried_through_in_recorded_order(tmp_path):
    p = write_manifest(tmp_path, {"slices": [{
        "id": "B1", "status": "committed", "updated": iso(T - 60), "verdicts": [
            {"state": "REFUTE", "observer": "verifier", "at": iso(T - 3600),
             "agent_id": "a1", "counts": None,
             "discrepancies": ["null payload evicts the last-good cache entry"],
             "note": "", "backfilled": False},
            {"state": "CONFIRM", "observer": "merger", "at": iso(T - 1800),
             "agent_id": None,
             "counts": {"passed": 1306, "skipped": 16, "failed": 0},
             "note": "5-sequence differential probe", "backfilled": True},
        ]}]})
    s = rd.read_slice_manifest(p, now_ts=T, cache={})["slices"][0]
    assert [r["state"] for r in s["verdicts"]] == ["REFUTE", "CONFIRM"]
    assert s["verdict_count"] == 2
    first, second = s["verdicts"]
    assert first["observer"] == "verifier" and first["agent_id"] == "a1"
    assert first["counts"] is None and first["counts_human"] is None
    assert first["discrepancies"] == ["null payload evicts the last-good cache entry"]
    assert first["at_age_s"] == pytest.approx(3600.0)
    assert second["counts"] == {"passed": 1306, "skipped": 16, "failed": 0}
    assert second["counts_human"] == "1306 passed / 16 skipped / 0 failed"
    assert second["backfilled"] is True


def test_a_garbage_verdict_record_never_raises_and_never_reads_as_confirmed(tmp_path):
    p = write_manifest(tmp_path, {"slices": [{
        "id": "X", "status": "pending", "verdicts": [
            None, 7, "CONFIRM",
            {"state": None, "counts": "1306 passed", "discrepancies": "one line"},
        ]}]})
    s = rd.read_slice_manifest(p, now_ts=T, cache={})["slices"][0]
    assert s["verdict_count"] == 1  # the three non-dict records are dropped
    rec = s["verdicts"][0]
    assert rec["state"] is None and rec["counts"] is None
    assert rec["discrepancies"] == [] and rec["observer"] is None


def test_a_non_list_verdict_field_is_an_empty_history_not_a_crash(tmp_path):
    p = write_manifest(tmp_path, {"slices": [
        {"id": "X", "status": "pending", "verdicts": "CONFIRM"}]})
    assert rd.read_slice_manifest(p, now_ts=T, cache={})["slices"][0]["verdicts"] == []


def test_a_naive_verdict_stamp_gives_an_unknown_age_rather_than_a_wrong_one(tmp_path):
    # parse_iso here reads naive as LOCAL and lw_httpd.parse_ts reads it as UTC.
    # slice_orchestrator refuses to write a naive stamp for exactly that reason;
    # a hand-edited one must degrade to "-", never to a confidently wrong age.
    p = write_manifest(tmp_path, {"slices": [{"id": "X", "status": "pending", "verdicts": [
        {"state": "CONFIRM", "observer": "verifier", "at": "whenever"}]}]})
    rec = rd.read_slice_manifest(p, now_ts=T, cache={})["slices"][0]["verdicts"][0]
    assert rec["at_age_s"] is None and rec["at_age_human"] == "-"


# ------------------------------------------------------------- run_liveness


def make_control(tmp_path, *, lock=None, stop=None, log_mtime=None, cycle=None):
    ctl = tmp_path / "control"
    ctl.mkdir(exist_ok=True)
    if lock is not None:
        (ctl / "RUNNING.lock").write_text(
            lock if isinstance(lock, str) else json.dumps(lock), encoding="utf-8")
    if stop is not None:
        (ctl / "STOP").write_text(stop, encoding="utf-8")
    if cycle is not None:
        (ctl / "cycle.txt").write_text(str(cycle), encoding="utf-8")
    if log_mtime is not None:
        p = ctl / "controller.log"
        p.write_text("cycle 3 start\ncycle 3 done\nrun ended\n", encoding="utf-8")
        import os
        os.utime(p, (log_mtime, log_mtime))
    return ctl


ALIVE = (lambda pid: True)
DEAD = (lambda pid: False)


def test_liveness_live_needs_lock_freshness_and_a_moving_disk(tmp_path):
    ctl = make_control(tmp_path, lock={"pid": 4321, "run_id": "abc", "ts": T - 30},
                       log_mtime=T - 10, cycle=3)
    v = rd.run_liveness(ctl, now_ts=T, pid_alive=ALIVE, stale_after=STALE)
    assert v["state"] == "LIVE"
    assert v["corroborated"] is True and v["pid"] == 4321 and v["run_id"] == "abc"
    assert v["cycle"] == 3
    assert v["newest_write_age_s"] == pytest.approx(10.0)


def test_liveness_recycled_pid_is_dead_not_live(tmp_path):
    """The measured 2026-08-01 defect: live pid, ancient lock, unrelated process.

    RUNNING.lock named pid 8532 from a run that ended five days earlier and
    Windows had reissued 8532 to a conhost. pid_alive says True and is useless;
    the lock's AGE is what settles it. Matches claim_single_controller after
    e63a50d - refusal needs alive AND fresh - so the two cannot disagree.
    """
    ctl = make_control(tmp_path, lock={"pid": 8532, "run_id": "7dd1dc02", "ts": T - 423000},
                       log_mtime=T - 423000)
    v = rd.run_liveness(ctl, now_ts=T, pid_alive=ALIVE, stale_after=STALE)
    assert v["state"] == "DEAD"
    assert v["pid_alive"] is True and v["lock_fresh"] is False
    assert v["lock_holder_ok"] is False and v["corroborated"] is False
    assert "recycled pid" in v["reason"] and "8532" in v["reason"]


def test_liveness_live_holder_inside_the_window_is_still_live(tmp_path):
    """Age must not become a way to declare a running loop dead."""
    ctl = make_control(tmp_path, lock={"pid": 8532, "ts": T - (STALE - 60)}, log_mtime=T - 30)
    assert rd.run_liveness(ctl, now_ts=T, pid_alive=ALIVE, stale_after=STALE)["state"] == "LIVE"


def test_liveness_dead_pid_is_dead_even_with_a_fresh_lock(tmp_path):
    ctl = make_control(tmp_path, lock={"pid": 999, "ts": T - 10}, log_mtime=T - 5)
    v = rd.run_liveness(ctl, now_ts=T, pid_alive=DEAD, stale_after=STALE)
    assert v["state"] == "DEAD" and "not alive" in v["reason"]


def test_liveness_fresh_lock_but_frozen_disk_is_dead(tmp_path):
    """The corroboration the lock alone cannot provide - nothing has moved."""
    ctl = make_control(tmp_path, lock={"pid": 4321, "ts": T - 60}, log_mtime=T - (STALE + 600))
    v = rd.run_liveness(ctl, now_ts=T, pid_alive=ALIVE, stale_after=STALE)
    assert v["state"] == "DEAD" and v["writes_fresh"] is False
    assert "nothing has been written" in v["reason"]


def test_liveness_stop_outranks_a_live_lock(tmp_path):
    ctl = make_control(tmp_path, lock={"pid": 4321, "ts": T - 10}, stop="gemini budget ceiling hit",
                       log_mtime=T - 5)
    v = rd.run_liveness(ctl, now_ts=T, pid_alive=ALIVE, stale_after=STALE)
    assert v["state"] == "STOPPED" and v["stop_reason"] == "gemini budget ceiling hit"


def test_liveness_max_cycles_stop_reads_as_finished(tmp_path):
    ctl = make_control(tmp_path, lock={"pid": 8532, "ts": T - 423000},
                       stop="max_cycles 12 reached", log_mtime=T - 423000)
    v = rd.run_liveness(ctl, now_ts=T, pid_alive=ALIVE, stale_after=STALE)
    assert v["state"] == "FINISHED" and v["stop_present"] is True


def test_liveness_no_work_stop_reads_as_finished(tmp_path):
    ctl = make_control(tmp_path, stop="director returned NO_WORK")
    assert rd.run_liveness(ctl, now_ts=T, pid_alive=DEAD, stale_after=STALE)["state"] == "FINISHED"


def test_liveness_empty_control_dir_is_dead_with_no_run_present(tmp_path):
    ctl = tmp_path / "control"
    ctl.mkdir()
    v = rd.run_liveness(ctl, now_ts=T, pid_alive=ALIVE, stale_after=STALE)
    assert v["state"] == "DEAD" and v["run_present"] is False
    assert v["reason"] == "no run state on disk"


def test_liveness_missing_control_dir_does_not_raise(tmp_path):
    v = rd.run_liveness(tmp_path / "gone", now_ts=T, pid_alive=ALIVE, stale_after=STALE)
    assert v["ok"] is True and v["state"] == "DEAD"


def test_liveness_corrupt_lock_falls_back_to_mtime(tmp_path):
    ctl = make_control(tmp_path, lock="{not json", log_mtime=T - 5)
    v = rd.run_liveness(ctl, now_ts=T, pid_alive=ALIVE, stale_after=STALE)
    assert v["lock_present"] is True and v["pid"] is None
    assert v["lock_age_s"] is not None  # mtime belt, so it cannot look fresh forever
    assert v["state"] == "DEAD"


def test_liveness_pid_alive_probe_that_explodes_is_contained(tmp_path):
    def boom(pid):
        raise OSError("access denied")

    ctl = make_control(tmp_path, lock={"pid": 5, "ts": T - 10}, log_mtime=T - 5)
    v = rd.run_liveness(ctl, now_ts=T, pid_alive=boom, stale_after=STALE)
    assert v["ok"] is True and v["pid_alive"] is False and v["state"] == "DEAD"


def test_liveness_manifest_counts_as_a_corroborating_write(tmp_path):
    import os
    ctl = make_control(tmp_path, lock={"pid": 4321, "ts": T - 60}, log_mtime=T - (STALE + 600))
    mp = write_manifest(tmp_path, sample_manifest())
    os.utime(mp, (T - 30, T - 30))  # the orchestrator moved even though the log did not
    v = rd.run_liveness(ctl, now_ts=T, manifest_path=mp, pid_alive=ALIVE, stale_after=STALE)
    assert v["state"] == "LIVE" and v["newest_write"]["path"] == str(mp)


def test_liveness_garbage_cycle_txt_is_none_not_a_crash(tmp_path):
    ctl = make_control(tmp_path, lock={"pid": 4321, "ts": T - 10}, log_mtime=T - 5, cycle="n/a")
    assert rd.run_liveness(ctl, now_ts=T, pid_alive=ALIVE, stale_after=STALE)["cycle"] is None


# --------------------------------------------------------- read_cycle_history


def hist_line(cycle, ts, **kw):
    rec = {"cycle": cycle, "ts": ts, "title": kw.get("title", "t"),
           "sha_before": kw.get("sha_before", "aaaaaaaa"),
           "sha_after": kw.get("sha_after", "bbbbbbbb"),
           "tests": kw.get("tests", "808"), "regress": kw.get("regress", False),
           "verdict": kw.get("verdict", "VERDICT: CLEAN")}
    return json.dumps(rec)


def write_hist(tmp_path, lines):
    p = tmp_path / "directive_history.jsonl"
    p.write_text("".join(ln + "\n" for ln in lines), encoding="utf-8")
    return p


def test_history_parses_records_and_coerces_counts(tmp_path):
    p = write_hist(tmp_path, [hist_line(1, "2026-07-27T00:02:19", tests="693"),
                              hist_line(2, "2026-07-27T00:18:03", tests="718")])
    h = rd.read_cycle_history(p, now_ts=T)
    assert h["present"] is True and h["parsed"] == 2 and h["line_count"] == 2
    assert [r["tests"] for r in h["records"]] == [693, 718]
    assert h["records"][0]["ts_epoch"] is not None
    assert h["records"][0]["verdict"] == "VERDICT: CLEAN"
    assert h["torn_tail"] is False and h["corrupt_lines"] == 0


def test_history_discards_a_torn_tail_line(tmp_path):
    p = tmp_path / "directive_history.jsonl"
    p.write_text(hist_line(1, "2026-07-27T00:02:19") + "\n" + '{"cycle": 2, "ts": "2026-',
                 encoding="utf-8")
    h = rd.read_cycle_history(p, now_ts=T)
    assert h["parsed"] == 1 and h["torn_tail"] is True and h["corrupt_lines"] == 0


def test_history_counts_a_corrupt_middle_line_separately(tmp_path):
    """A torn tail is a race; a broken line in the middle is a producer bug.

    Folding them together would hide the second behind the first.
    """
    p = tmp_path / "directive_history.jsonl"
    p.write_text(hist_line(1, "2026-07-27T00:02:19") + "\n{bad\n"
                 + hist_line(2, "2026-07-27T00:18:03") + "\n", encoding="utf-8")
    h = rd.read_cycle_history(p, now_ts=T)
    assert h["parsed"] == 2 and h["corrupt_lines"] == 1 and h["torn_tail"] is False


def test_history_colliding_cycle_numbers_split_into_runs(tmp_path):
    """Two `cycle 1` records exist today and the file carries no run id.

    Identity is the ts; a cycle number that does not advance opens a new run.
    """
    p = write_hist(tmp_path, [
        hist_line(1, "2026-07-27T00:02:19"), hist_line(2, "2026-07-27T00:18:03"),
        hist_line(1, "2026-07-30T09:00:00"), hist_line(2, "2026-07-30T09:30:00")])
    h = rd.read_cycle_history(p, now_ts=T)
    assert h["run_count"] == 2
    assert [r["run_index"] for r in h["records"]] == [1, 1, 2, 2]
    keys = [r["key"] for r in h["records"]]
    assert len(set(keys)) == 4  # cycle numbers collide, keys must not
    assert keys[0] == "2026-07-27T00:02:19#1"


def test_history_absent_and_empty_and_non_dict_lines(tmp_path):
    assert rd.read_cycle_history(tmp_path / "none.jsonl", now_ts=T)["present"] is False
    p = tmp_path / "directive_history.jsonl"
    p.write_text("\n\n", encoding="utf-8")
    assert rd.read_cycle_history(p, now_ts=T)["parsed"] == 0
    p.write_text('"just a string"\n[1,2]\n', encoding="utf-8")
    h = rd.read_cycle_history(p, now_ts=T)
    assert h["parsed"] == 0 and h["corrupt_lines"] == 2


def test_history_missing_and_wrong_typed_fields_do_not_raise(tmp_path):
    p = tmp_path / "directive_history.jsonl"
    p.write_text(json.dumps({"cycle": "seven", "tests": None, "ts": 12345}) + "\n",
                 encoding="utf-8")
    r = rd.read_cycle_history(p, now_ts=T)["records"][0]
    assert r["cycle"] is None and r["tests"] is None and r["ts"] is None
    assert r["ts_epoch"] is None and r["age_s"] is None


def test_history_limit_keeps_the_newest(tmp_path):
    p = write_hist(tmp_path, [hist_line(i, f"2026-07-27T0{i}:00:00") for i in range(1, 6)])
    h = rd.read_cycle_history(p, now_ts=T, limit=2)
    assert [r["cycle"] for r in h["records"]] == [4, 5] and h["parsed"] == 5


# ------------------------------------------------------- worktree_inventory


WT_LIST = (
    "worktree C:/LegionWallpaper\n"
    "HEAD 55b9e9500000000000000000000000000000aaaa\n"
    "branch refs/heads/main\n"
    "\n"
    "worktree C:/LegionWallpaper/.claude/worktrees/agent-B2\n"
    "HEAD 1111111111111111111111111111111111111111\n"
    "branch refs/heads/worktree-agent-B2\n"
    "\n"
    "worktree C:/LegionWallpaper/.claude/worktrees/agent-lost\n"
    "HEAD 2222222222222222222222222222222222222222\n"
    "detached\n"
)

CLEAN_STATUS = "# branch.oid 5555\n# branch.head main\n# branch.ab +0 -0\n"
DIRTY_STATUS = (
    "# branch.oid 1111\n# branch.head worktree-agent-B2\n"
    "# branch.upstream origin/worktree-agent-B2\n# branch.ab +2 -1\n"
    "1 .M N... 100644 100644 100644 aaa bbb tools/lw_rundash_state.py\n"
    "2 R. N... 100644 100644 100644 aaa bbb R100 tests/new.py\ttests/old.py\n"
    "u UU N... 100644 100644 100644 100644 a b c tools/conflict.py\n"
    "? scratch/notes.txt\n"
)


def fake_runner(responses):
    """argv-prefix -> (rc, stdout, stderr), so every branch is drivable without git."""
    calls = []

    def run(argv):
        calls.append(argv)
        for needle, resp in responses:
            if needle in " ".join(argv):
                return resp
        return (1, "", "unexpected argv")

    run.calls = calls
    return run


def test_worktree_inventory_parses_list_and_status():
    run = fake_runner([
        ("worktree list", (0, WT_LIST, "")),
        ("agent-B2 status", (0, DIRTY_STATUS, "")),
        ("agent-lost status", (0, CLEAN_STATUS, "")),
        ("status", (0, CLEAN_STATUS, "")),
    ])
    inv = rd.worktree_inventory("C:/LegionWallpaper", runner=run)
    assert inv["ok"] is True and len(inv["worktrees"]) == 3
    primary, agent, lost = inv["worktrees"]
    assert primary["primary"] is True and primary["branch"] == "main"
    assert agent["branch"] == "worktree-agent-B2" and agent["primary"] is False
    assert agent["dirty_count"] == 4
    assert [d["path"] for d in agent["dirty"]] == [
        "tools/lw_rundash_state.py", "tests/new.py", "tools/conflict.py", "scratch/notes.txt"]
    assert agent["ahead"] == 2 and agent["behind"] == 1
    assert agent["upstream"] == "origin/worktree-agent-B2"
    assert lost["detached"] is True and lost["branch"] is None
    assert inv["dirty_count"] == 4 and inv["unpushed_count"] == 1


def test_worktree_inventory_git_failure_is_a_flag_not_an_exception():
    run = fake_runner([("worktree list", (128, "", "fatal: not a git repository"))])
    inv = rd.worktree_inventory("C:/nowhere", runner=run)
    assert inv["ok"] is False and inv["worktrees"] == []
    assert "not a git repository" in inv["error"]


def test_worktree_inventory_status_failure_is_per_worktree():
    run = fake_runner([
        ("worktree list", (0, WT_LIST, "")),
        ("agent-lost status", (1, "", "fatal: cannot chdir")),
        ("status", (0, CLEAN_STATUS, "")),
    ])
    inv = rd.worktree_inventory("C:/LegionWallpaper", runner=run)
    assert inv["ok"] is True
    lost = inv["worktrees"][2]
    assert lost["status_ok"] is False and "cannot chdir" in lost["status_error"]
    assert inv["worktrees"][0]["status_ok"] is True  # one failure loses nothing else


def test_worktree_inventory_runner_that_raises_is_contained():
    def boom(argv):
        raise OSError("git not found")

    inv = rd.worktree_inventory("C:/LegionWallpaper", runner=boom)
    assert inv["ok"] is False and "git not found" in inv["error"]


def test_worktree_inventory_garbage_status_lines_are_skipped():
    run = fake_runner([
        ("worktree list", (0, "worktree C:/x\nHEAD abc\nbranch refs/heads/main\n", "")),
        ("status", (0, "# branch.ab bogus\n1 truncated\n? ok/path.txt\n", "")),
    ])
    inv = rd.worktree_inventory("C:/x", runner=run)
    wt = inv["worktrees"][0]
    assert [d["path"] for d in wt["dirty"]] == ["ok/path.txt"]
    assert wt["ahead"] is None


def test_worktree_inventory_empty_list_output():
    run = fake_runner([("worktree list", (0, "", ""))])
    inv = rd.worktree_inventory("C:/x", runner=run)
    assert inv["ok"] is True and inv["worktrees"] == []


def test_worktree_inventory_passes_create_no_window():
    """Guard the constant itself. tests/test_no_console_flash.py AST-checks the
    call site; this asserts the value it resolves to is the real flag."""
    assert rd.NO_WINDOW == (0x08000000 if sys.platform == "win32" else 0)


# ------------------------------------------------------------ resume_verdict


def inventory_from(run):
    return rd.worktree_inventory("C:/LegionWallpaper", runner=run)


def test_resume_safe_when_nothing_is_stranded(tmp_path):
    run = fake_runner([("worktree list", (0, WT_LIST, "")), ("status", (0, CLEAN_STATUS, ""))])
    m = rd.read_slice_manifest(write_manifest(tmp_path, sample_manifest()), now_ts=T, cache={})
    v = rd.resume_verdict(m, inventory_from(run), {"state": "DEAD"}, now_ts=T)
    assert v["verdict"] == "RESUME SAFE" and v["salvage"] is False
    assert v["open_count"] == 1 and v["open_slices"][0]["id"] == "B2"
    assert v["stranded"] == [] and v["run_state"] == "DEAD"


def test_salvage_first_when_a_worktree_holds_uncommitted_files(tmp_path):
    """2026-07-29: five agents killed at once, one worktree salvaged, one slice
    lost. The difference was somebody knowing to look - this is that look."""
    run = fake_runner([
        ("worktree list", (0, WT_LIST, "")),
        ("agent-B2 status", (0, DIRTY_STATUS, "")),
        ("status", (0, CLEAN_STATUS, "")),
    ])
    m = rd.read_slice_manifest(write_manifest(tmp_path, sample_manifest()), now_ts=T, cache={})
    v = rd.resume_verdict(m, inventory_from(run), {"state": "DEAD", "stop_reason": "killed"}, now_ts=T)
    assert v["verdict"] == "SALVAGE FIRST" and v["salvage"] is True
    assert len(v["stranded"]) == 1
    row = v["stranded"][0]
    assert row["branch"] == "worktree-agent-B2" and row["dirty_count"] == 4
    assert "tools/lw_rundash_state.py" in row["files"]
    assert row["slices"] == ["B2"]  # branch name carries the slice id
    assert v["unpushed"] and v["stop_reason"] == "killed"
    assert any("uncommitted" in r for r in v["reasons"])


def test_salvage_on_unpushed_commits_with_a_clean_tree():
    ahead_only = "# branch.oid 1111\n# branch.head worktree-agent-B2\n# branch.ab +3 -0\n"
    run = fake_runner([
        ("worktree list", (0, WT_LIST, "")),
        ("agent-B2 status", (0, ahead_only, "")),
        ("status", (0, CLEAN_STATUS, "")),
    ])
    v = rd.resume_verdict({}, inventory_from(run), None)
    assert v["verdict"] == "SALVAGE FIRST"
    assert v["stranded"] == [] and len(v["unpushed"]) == 1


def test_resume_ignores_a_dirty_primary_worktree_by_default():
    run = fake_runner([("worktree list", (0, WT_LIST, "")),
                       ("LegionWallpaper status", (0, DIRTY_STATUS, "")),
                       ("status", (0, CLEAN_STATUS, ""))])
    inv = inventory_from(run)
    assert rd.resume_verdict({}, inv, None)["verdict"] == "RESUME SAFE"
    assert rd.resume_verdict({}, inv, None, include_primary=True)["verdict"] == "SALVAGE FIRST"


def test_resume_reports_orphan_worktrees_no_slice_claims(tmp_path):
    run = fake_runner([("worktree list", (0, WT_LIST, "")), ("status", (0, CLEAN_STATUS, ""))])
    m = rd.read_slice_manifest(write_manifest(tmp_path, sample_manifest()), now_ts=T, cache={})
    v = rd.resume_verdict(m, inventory_from(run), None, now_ts=T)
    orphans = [o["path"] for o in v["orphan_worktrees"]]
    assert orphans == ["C:/LegionWallpaper/.claude/worktrees/agent-lost"]


def test_resume_verdict_survives_junk_inputs():
    v = rd.resume_verdict(None, None, None)
    assert v["ok"] is True and v["verdict"] == "RESUME SAFE"
    assert v["inventory_ok"] is False and v["open_slices"] == []
    v2 = rd.resume_verdict("nonsense", {"worktrees": "nope", "ok": True}, "nope")
    assert v2["ok"] is True and v2["stranded"] == []


# ---------------------------------------------------------------- tail_lines


def test_tail_lines_and_absent_file(tmp_path):
    p = tmp_path / "controller.log"
    p.write_text("a\n\nb\nc\nd\ne\nf\n", encoding="utf-8")
    assert rd.tail_lines(p, 3) == ["d", "e", "f"]
    assert rd.tail_lines(tmp_path / "nope.log", 5) == []
    assert rd.tail_lines(p, "x") == ["b", "c", "d", "e", "f"]


# ------------------------------------------------------------ agent fleet


def write_agent(subdir, agent_id, meta, events, *, mtime=None, torn=""):
    (subdir / f"agent-{agent_id}.meta.json").write_text(json.dumps(meta), encoding="utf-8")
    body = "".join(json.dumps(e) + "\n" for e in events) + torn
    p = subdir / f"agent-{agent_id}.jsonl"
    p.write_text(body, encoding="utf-8")
    if mtime is not None:
        import os
        os.utime(p, (mtime, mtime))
    return p


def event(ts, out_tokens=None, role="assistant"):
    msg = {"role": role}
    if out_tokens is not None:
        msg["usage"] = {"input_tokens": 2, "output_tokens": out_tokens}
    return {"type": role, "timestamp": ts, "message": msg}


def build_fleet(tmp_path):
    sess = tmp_path / "153bbbb2-438f-41cd-b111-21b5c023f606"
    subs = sess / "subagents"
    subs.mkdir(parents=True)
    write_agent(subs, "a8701dbad981ba8dc", {
        "agentType": "general-purpose",
        "worktreePath": "C:\\LegionWallpaper\\.claude\\worktrees\\agent-a8701dbad981ba8dc",
        "worktreeBranch": "worktree-agent-a8701dbad981ba8dc",
        "description": "R11 charter md-hygiene slice", "spawnDepth": 1,
    }, [event("2026-07-30T10:00:00.000Z"), event("2026-07-30T10:20:00.000Z", 120),
        event("2026-07-30T10:40:00.000Z", 80)], mtime=T - 10)
    write_agent(subs, "add1dc786154ac384", {
        "agentType": "verifier", "description": "Verify cycle 6 claims", "spawnDepth": 1,
    }, [event("2026-07-30T09:00:00.000Z"), event("2026-07-30T09:05:00.000Z", 40)],
        mtime=T - 176000)
    return sess, subs


def test_fleet_reports_type_branch_elapsed_and_tokens(tmp_path):
    sess, _ = build_fleet(tmp_path)
    f = rd.read_agent_fleet(sess, now_ts=T)
    assert f["ok"] is True and f["present"] is True and f["counts"]["total"] == 2
    by_id = {a["id"]: a for a in f["agents"]}
    build = by_id["a8701dbad981ba8dc"]
    assert build["type"] == "general-purpose"
    assert build["description"] == "R11 charter md-hygiene slice"
    assert build["worktree_branch"] == "worktree-agent-a8701dbad981ba8dc"
    assert build["is_worktree_agent"] is True
    assert build["elapsed_s"] == pytest.approx(2400.0) and build["elapsed_human"] == "40m"
    assert build["output_tokens"] == 200 and build["events"] == 3
    assert build["start"] == "2026-07-30T10:00:00Z"
    assert f["output_tokens"] == 240


def test_fleet_worktree_path_is_the_verifier_discriminator(tmp_path):
    sess, _ = build_fleet(tmp_path)
    f = rd.read_agent_fleet(sess, now_ts=T)
    ver = [a for a in f["agents"] if not a["is_worktree_agent"]]
    assert [a["type"] for a in ver] == ["verifier"]
    assert ver[0]["worktree_path"] is None and ver[0]["worktree_branch"] is None
    assert f["counts"]["worktree"] == 1 and f["counts"]["other"] == 1


def test_fleet_mtime_separates_running_from_finished(tmp_path):
    """Measured: live lanes at 4.6s / 14.9s / 58.2s of mtime age against
    ~176,000s for the finished 2026-07-30 fleet."""
    sess, _ = build_fleet(tmp_path)
    f = rd.read_agent_fleet(sess, now_ts=T)
    by_id = {a["id"]: a for a in f["agents"]}
    assert by_id["a8701dbad981ba8dc"]["running"] is True
    assert by_id["add1dc786154ac384"]["running"] is False
    assert by_id["add1dc786154ac384"]["idle_human"] == "2d"
    assert f["counts"]["running"] == 1


def test_fleet_accepts_the_subagents_dir_directly(tmp_path):
    sess, subs = build_fleet(tmp_path)
    assert rd.read_agent_fleet(subs, now_ts=T)["counts"]["total"] == 2


def test_fleet_tolerates_a_torn_final_transcript_line(tmp_path):
    sess = tmp_path / "s"
    subs = sess / "subagents"
    subs.mkdir(parents=True)
    write_agent(subs, "torn1", {"agentType": "verifier", "description": "d"},
                [event("2026-07-30T10:00:00.000Z", 10)],
                mtime=T - 5, torn='{"type": "assis')
    a = rd.read_agent_fleet(sess, now_ts=T)["agents"][0]
    assert a["events"] == 1 and a["torn_lines"] == 0 and a["output_tokens"] == 10


def test_fleet_counts_a_corrupt_middle_transcript_line(tmp_path):
    sess = tmp_path / "s"
    subs = sess / "subagents"
    subs.mkdir(parents=True)
    (subs / "agent-x.meta.json").write_text('{"agentType": "verifier"}', encoding="utf-8")
    (subs / "agent-x.jsonl").write_text(
        "{bad\n" + json.dumps(event("2026-07-30T10:00:00.000Z", 5)) + "\n", encoding="utf-8")
    a = rd.read_agent_fleet(sess, now_ts=T)["agents"][0]
    assert a["torn_lines"] == 1 and a["events"] == 1


def test_fleet_agent_with_meta_but_no_transcript_is_still_listed(tmp_path):
    sess = tmp_path / "s"
    subs = sess / "subagents"
    subs.mkdir(parents=True)
    (subs / "agent-ghost.meta.json").write_text(
        json.dumps({"agentType": "general-purpose", "worktreePath": "C:/wt"}), encoding="utf-8")
    a = rd.read_agent_fleet(sess, now_ts=T)["agents"][0]
    assert a["id"] == "ghost" and a["transcript_present"] is False
    assert a["running"] is False and a["events"] == 0
    assert a["elapsed_s"] is None and a["elapsed_human"] == "-"
    assert a["start"] is None and a["idle_human"] == "-"


def test_fleet_corrupt_meta_does_not_drop_the_agent(tmp_path):
    sess = tmp_path / "s"
    subs = sess / "subagents"
    subs.mkdir(parents=True)
    (subs / "agent-broken.meta.json").write_text("{not json", encoding="utf-8")
    (subs / "agent-broken.jsonl").write_text(
        json.dumps(event("2026-07-30T10:00:00.000Z", 7)) + "\n", encoding="utf-8")
    a = rd.read_agent_fleet(sess, now_ts=T)["agents"][0]
    assert a["id"] == "broken" and a["type"] == "unknown" and a["output_tokens"] == 7


def test_fleet_absent_dir_is_normal_not_an_error(tmp_path):
    # No cleanupPeriodDays is set, so Claude Code may reap this whole tree.
    f = rd.read_agent_fleet(tmp_path / "no-such-session", now_ts=T)
    assert f["ok"] is True and f["present"] is False and f["agents"] == []
    assert f["counts"]["total"] == 0


def test_fleet_empty_subagents_dir(tmp_path):
    subs = tmp_path / "s" / "subagents"
    subs.mkdir(parents=True)
    f = rd.read_agent_fleet(subs, now_ts=T)
    assert f["present"] is True and f["agents"] == []


def test_fleet_orders_newest_activity_first_with_unknowns_last(tmp_path):
    sess = tmp_path / "s"
    subs = sess / "subagents"
    subs.mkdir(parents=True)
    write_agent(subs, "old", {"agentType": "verifier"},
                [event("2026-07-01T00:00:00.000Z", 1)], mtime=T - 900)
    write_agent(subs, "new", {"agentType": "verifier"},
                [event("2026-07-30T00:00:00.000Z", 1)], mtime=T - 5)
    (subs / "agent-none.meta.json").write_text("{}", encoding="utf-8")
    assert [a["id"] for a in rd.read_agent_fleet(sess, now_ts=T)["agents"]] == ["new", "old", "none"]


# ------------------------------------------------------------ module posture


def test_module_writes_nothing_on_a_full_read(tmp_path):
    """Read-only is a contract, not an intention: the orchestrator, truth_gate
    and loop_controller own these files and a reader that touches them races
    its own writer. Snapshot every path before and after a full sweep."""
    ctl = make_control(tmp_path, lock={"pid": 1, "ts": T - 10}, stop="max_cycles 12 reached",
                       log_mtime=T - 5, cycle=4)
    mp = write_manifest(tmp_path, sample_manifest())
    hp = write_hist(tmp_path, [hist_line(1, "2026-07-27T00:02:19")])
    sess, _ = build_fleet(tmp_path)
    before = {str(p): (p.stat().st_mtime, p.stat().st_size)
              for p in sorted(tmp_path.rglob("*")) if p.is_file()}

    rd.read_slice_manifest(mp, now_ts=T, cache={})
    rd.run_liveness(ctl, now_ts=T, manifest_path=mp, pid_alive=ALIVE, stale_after=STALE)
    rd.read_cycle_history(hp, now_ts=T)
    rd.read_agent_fleet(sess, now_ts=T)
    rd.tail_lines(ctl / "controller.log", 5)

    after = {str(p): (p.stat().st_mtime, p.stat().st_size)
             for p in sorted(tmp_path.rglob("*")) if p.is_file()}
    assert after == before


def test_no_module_level_state_is_read_at_import(monkeypatch):
    """Import must touch no path and spawn nothing.

    Any module-level read would make the readers depend on the machine they run
    on, and the whole test file below depends on them not doing that. Enforced
    by booby-trapping the IO primitives across a fresh exec_module.
    """
    def trap(*a, **kw):
        raise AssertionError("lw_rundash_state read state at import time")

    monkeypatch.setattr(Path, "read_text", trap)
    monkeypatch.setattr(Path, "stat", trap)
    monkeypatch.setattr(Path, "glob", trap)
    monkeypatch.setattr(Path, "exists", trap)
    monkeypatch.setattr("subprocess.run", trap)
    spec = importlib.util.spec_from_file_location(
        "lw_rundash_state_reimport", ROOT / "tools" / "lw_rundash_state.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod._SLOTS_CACHE == {}  # slots is loaded lazily, on first use only
