"""The three run-id namespaces get an actual join, or admit they have none.

Spec item 5 (docs/RUNDASH_SPEC_2026-08-01.md). LW names one run three ways:
`slice_manifest.run_id` (`2026-08-01-01`, a human date-ordinal), the controller
`run_id` (`7dd1dc02`, a uuid4 stub) and the Claude `sessionId`. The dashboard
header showed two of them side by side with nothing saying they were the same
run - and nothing on disk said so either.

The join is EVIDENCE, never inference: a pairing exists only because a cycle
record carried both ids at once. Same-looking, same-aged, only-run-that-day -
none of those make a join, and a guessed one is worse than none, because the
whole panel exists to separate what was observed from what was assumed.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "ops" / "loop"))

import lw_rundash_state as st  # noqa: E402
import loop_controller as lc  # noqa: E402


def _write_history(tmp_path, recs):
    p = tmp_path / "directive_history.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in recs), encoding="utf-8")
    return p


def _rec(cycle, ts, **kw):
    base = {"cycle": cycle, "ts": ts, "title": "t", "sha_before": "aaaaaaa",
            "sha_after": "bbbbbbb", "tests": 10, "regress": False,
            "verdict": "VERDICT: CLEAN"}
    base.update(kw)
    return base


# ------------------------------------------------- the writer side (producer)


def test_the_controller_records_the_manifest_run_id_alongside_its_own(tmp_path):
    lc.record_directive_outcome(1, "body", "aaaaaaa1", "bbbbbbb2", {}, "CLEAN",
                                ctl=tmp_path, run_id="7dd1dc02",
                                manifest_run_id="2026-08-01-01")
    rec = json.loads((tmp_path / "directive_history.jsonl").read_text(
        encoding="utf-8").splitlines()[0])

    assert rec["run_id"] == "7dd1dc02"
    assert rec["manifest_run_id"] == "2026-08-01-01"


def test_a_missing_manifest_run_id_degrades_it_never_raises(tmp_path):
    rec = lc.record_directive_outcome(1, "body", "a", "b", {}, "CLEAN",
                                      ctl=tmp_path, run_id="7dd1dc02")
    assert rec["manifest_run_id"] is None


def test_read_manifest_run_id_reads_it_and_survives_every_absence(tmp_path):
    good = tmp_path / "good.json"
    good.write_text(json.dumps({"run_id": "2026-08-01-01"}), encoding="utf-8")
    junk = tmp_path / "junk.json"
    junk.write_text("{not json", encoding="utf-8")
    noid = tmp_path / "noid.json"
    noid.write_text(json.dumps({"slices": []}), encoding="utf-8")

    assert lc.read_manifest_run_id(good) == "2026-08-01-01"
    assert lc.read_manifest_run_id(junk) is None
    assert lc.read_manifest_run_id(noid) is None
    assert lc.read_manifest_run_id(tmp_path / "gone.json") is None


# ------------------------------------------------- the reader side (the join)


def test_one_controller_run_gathers_its_manifest_and_session_ids(tmp_path):
    p = _write_history(tmp_path, [
        _rec(1, "2026-08-01T12:00:00", run_id="7dd1dc02",
             manifest_run_id="2026-08-01-01", session_id="sess-a"),
        _rec(2, "2026-08-01T13:00:00", run_id="7dd1dc02",
             manifest_run_id="2026-08-01-01", session_id="sess-b"),
    ])
    join = st.read_cycle_history(p)["join"]

    run, = join["runs"]
    assert run["run_id"] == "7dd1dc02"
    assert run["manifest_run_ids"] == ["2026-08-01-01"]
    assert run["session_ids"] == ["sess-a", "sess-b"]
    assert run["cycles"] == [1, 2]
    assert run["first_ts"] == "2026-08-01T12:00:00"
    assert run["last_ts"] == "2026-08-01T13:00:00"


def test_a_manifest_reinit_mid_run_shows_as_two_ids_not_as_the_last_one(tmp_path):
    # `init --force` mints a new manifest run id under a controller run that
    # never restarted. Both are true; collapsing to one would silently drop a
    # whole slice ladder off the join.
    p = _write_history(tmp_path, [
        _rec(1, "2026-08-01T12:00:00", run_id="7dd1dc02",
             manifest_run_id="2026-08-01-01"),
        _rec(2, "2026-08-01T13:00:00", run_id="7dd1dc02",
             manifest_run_id="2026-08-01-02"),
    ])
    run, = st.read_cycle_history(p)["join"]["runs"]

    assert run["manifest_run_ids"] == ["2026-08-01-01", "2026-08-01-02"]
    assert run["ambiguous"] is True


def test_records_from_before_the_id_existed_are_counted_not_merged(tmp_path):
    # The records already on disk can never gain an id retroactively. Bucketing
    # them under some neighbouring run would invent the exact pairing this
    # panel exists to refuse to invent.
    p = _write_history(tmp_path, [
        _rec(1, "2026-07-30T12:00:00"),
        _rec(2, "2026-07-30T13:00:00"),
        _rec(1, "2026-08-01T12:00:00", run_id="7dd1dc02",
             manifest_run_id="2026-08-01-01"),
    ])
    join = st.read_cycle_history(p)["join"]

    assert [r["run_id"] for r in join["runs"]] == ["7dd1dc02"]
    assert join["unjoined_cycles"] == 2


def test_the_reverse_lookups_are_built_for_both_foreign_namespaces(tmp_path):
    p = _write_history(tmp_path, [
        _rec(1, "2026-08-01T12:00:00", run_id="7dd1dc02",
             manifest_run_id="2026-08-01-01", session_id="sess-a"),
    ])
    join = st.read_cycle_history(p)["join"]

    assert join["by_manifest_run_id"]["2026-08-01-01"] == ["7dd1dc02"]
    assert join["by_session_id"]["sess-a"] == ["7dd1dc02"]


def test_the_join_is_built_over_every_record_not_just_the_rendered_window(tmp_path):
    # `limit` truncates what the panel renders. A join built after truncation
    # would lose the pairing for any run older than the window and report the
    # live run as unjoinable.
    p = _write_history(tmp_path, [
        _rec(i, f"2026-08-01T1{i}:00:00", run_id="old" if i < 3 else "new",
             manifest_run_id=f"2026-08-01-0{1 if i < 3 else 2}")
        for i in range(5)
    ])
    out = st.read_cycle_history(p, limit=1)

    assert len(out["records"]) == 1
    assert [r["run_id"] for r in out["join"]["runs"]] == ["old", "new"]


# ------------------------------------------------------------- the resolver


def _join(tmp_path, recs):
    return st.read_cycle_history(_write_history(tmp_path, recs))["join"]


def test_resolving_a_manifest_id_finds_its_controller_run(tmp_path):
    join = _join(tmp_path, [_rec(1, "2026-08-01T12:00:00", run_id="7dd1dc02",
                                 manifest_run_id="2026-08-01-01",
                                 session_id="sess-a")])
    ident = st.resolve_run_identity(join, manifest_run_id="2026-08-01-01")

    assert ident["joined"] is True
    assert ident["controller_run_id"] == "7dd1dc02"
    assert ident["session_ids"] == ["sess-a"]
    assert "cycle record" in ident["evidence"]


def test_resolving_a_controller_id_finds_its_manifest(tmp_path):
    join = _join(tmp_path, [_rec(1, "2026-08-01T12:00:00", run_id="7dd1dc02",
                                 manifest_run_id="2026-08-01-01")])
    ident = st.resolve_run_identity(join, controller_run_id="7dd1dc02")

    assert ident["joined"] is True
    assert ident["manifest_run_id"] == "2026-08-01-01"


def test_an_unpaired_id_says_unjoined_rather_than_guessing_the_only_run(tmp_path):
    join = _join(tmp_path, [_rec(1, "2026-08-01T12:00:00", run_id="7dd1dc02",
                                 manifest_run_id="2026-08-01-01")])
    ident = st.resolve_run_identity(join, manifest_run_id="2026-08-01-99")

    assert ident["joined"] is False
    assert ident["controller_run_id"] is None
    assert "no cycle record" in ident["evidence"]


def test_two_ids_that_disagree_are_reported_as_a_conflict_not_reconciled(tmp_path):
    # The lock says one run, the manifest another, and a cycle record pairs the
    # manifest with a THIRD. Picking a winner here would put a confident wrong
    # id on the header of a board whose entire job is corroboration.
    join = _join(tmp_path, [_rec(1, "2026-08-01T12:00:00", run_id="7dd1dc02",
                                 manifest_run_id="2026-08-01-01")])
    ident = st.resolve_run_identity(join, controller_run_id="deadbeef",
                                    manifest_run_id="2026-08-01-01")

    assert ident["conflict"] is True
    assert ident["controller_run_id"] == "deadbeef"
    assert "7dd1dc02" in ident["evidence"]


def test_an_empty_history_resolves_to_unjoined_without_crashing(tmp_path):
    join = _join(tmp_path, [])
    ident = st.resolve_run_identity(join, manifest_run_id="2026-08-01-01")

    assert ident["joined"] is False
    assert ident["conflict"] is False


def test_resolving_nothing_at_all_is_unjoined_not_an_empty_success():
    ident = st.resolve_run_identity({"runs": [], "by_manifest_run_id": {},
                                     "by_session_id": {}, "unjoined_cycles": 0})
    assert ident["joined"] is False
    assert ident["manifest_run_id"] is None
    assert ident["controller_run_id"] is None
