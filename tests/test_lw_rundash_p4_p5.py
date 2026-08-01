"""P4 Operator Queue and P5 Suite Trajectory.

Spec docs/RUNDASH_SPEC_2026-08-01.md.

P4 answers "what is waiting on ME, and for how long". Its ROADMAP half is a
prose grep on `OPERATOR-GATED` - it works today and it will rot, so it is
LABELLED fragile on the panel rather than dressed up as structured data.

P5 answers "where is the suite going". Its one hard rule: a commit with no
observation is a GAP and renders as one. Interpolating between two datapoints
would manufacture exactly the false continuity - unbacked green carried forward
across commits nobody measured - that this whole dashboard exists to expose.
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import lw_rundash_state as st  # noqa: E402


def iso(epoch):
    return st.iso_from_epoch(epoch)


# ------------------------------------------------------ P4: operator queue


def pipeline_state(tmp_path, images):
    p = tmp_path / "pipeline_state.json"
    p.write_text(json.dumps({"schema": 1, "generated_ts": iso(time.time()),
                             "images": images}), encoding="utf-8")
    return p


def test_needauth_slugs_are_the_queue_with_an_age_on_each(tmp_path):
    now = time.time()
    path = pipeline_state(tmp_path, {
        "aatrox-pre": {"state": "CLEAN_SCRATCH", "substate": "NEEDAUTH",
                       "stage_folder": "3.Cleaning Scratch",
                       "last_op_ts": iso(now - 7260), "files": []},
        "ahri": {"state": "FIRST_DONE", "substate": None,
                 "stage_folder": "2.First Pass Done",
                 "last_op_ts": iso(now), "files": []},
    })
    q = st.read_operator_queue(path, now_ts=now)

    assert q["needauth_count"] == 1
    row, = q["needauth"]
    assert row["slug"] == "aatrox-pre"
    assert row["stage"] == "3.Cleaning Scratch"
    assert row["age_human"] == "2h"


def test_the_queue_is_oldest_first_because_age_is_the_whole_point(tmp_path):
    now = time.time()
    path = pipeline_state(tmp_path, {
        "new": {"substate": "NEEDAUTH", "stage_folder": "s", "last_op_ts": iso(now)},
        "old": {"substate": "NEEDAUTH", "stage_folder": "s",
                "last_op_ts": iso(now - 86460)},
    })
    q = st.read_operator_queue(path, now_ts=now)

    assert [r["slug"] for r in q["needauth"]] == ["old", "new"]
    assert q["oldest_age_human"] == "24h"


def test_one_stage_holding_the_whole_queue_reads_structural_not_scattered(tmp_path):
    # The run-relevant residue the spec kept from the rejected gate-flag census:
    # clustered on one reason means look at the pipeline, scattered means look
    # at the images. It is a POINTER, never a target to tune against.
    now = time.time()
    path = pipeline_state(tmp_path, {
        "a": {"substate": "NEEDAUTH", "stage_folder": "3.Cleaning Scratch",
              "last_op_ts": iso(now)},
        "b": {"substate": "NEEDAUTH", "stage_folder": "3.Cleaning Scratch",
              "last_op_ts": iso(now)},
    })
    q = st.read_operator_queue(path, now_ts=now)

    assert q["clustered"] is True
    assert q["cluster_stage"] == "3.Cleaning Scratch"


def test_a_queue_spread_over_stages_is_not_reported_as_clustered(tmp_path):
    now = time.time()
    path = pipeline_state(tmp_path, {
        "a": {"substate": "NEEDAUTH", "stage_folder": "3.Cleaning Scratch",
              "last_op_ts": iso(now)},
        "b": {"substate": "NEEDAUTH", "stage_folder": "1.First Pass Scratch",
              "last_op_ts": iso(now)},
    })
    q = st.read_operator_queue(path, now_ts=now)

    assert q["clustered"] is False
    assert q["cluster_stage"] is None


def test_an_absent_pipeline_state_is_an_empty_queue_not_a_crash(tmp_path):
    q = st.read_operator_queue(tmp_path / "gone.json", now_ts=time.time())
    assert q["present"] is False
    assert q["needauth"] == []


# ------------------------------------------------- P4: the ROADMAP half


ROADMAP = """\
# ROADMAP

- **m1-gate-fund-or-close - decide attempt 4 on the weapon gate - OPERATOR-GATED.**
  Next: operator decides FUND or CLOSE. Three measured negatives landed.
  Evidence: LEDGER 37.

- **something-else - not gated at all.**
  Next: just do it.

- **arm-scheduled-tasks - register the LW-* roster - OPERATOR-GATED.**
  Next: operator approves the task list.
"""


def test_operator_gated_items_come_back_with_their_next_line(tmp_path):
    p = tmp_path / "ROADMAP.md"
    p.write_text(ROADMAP, encoding="utf-8")
    out = st.read_operator_gated(p)

    assert out["count"] == 2
    first = out["items"][0]
    assert first["id"] == "m1-gate-fund-or-close"
    assert first["next"] == "operator decides FUND or CLOSE. Three measured negatives landed."
    assert first["line_no"] == 3


def test_a_marker_on_a_wrapped_line_belongs_to_the_bullet_above_it(tmp_path):
    # Three of the six live items today wrap before the marker. Reading the
    # wrapped line as the item yields the id "OPERATOR-GATED on policy" - a
    # fragment that matches no roadmap item and cannot be looked up.
    p = tmp_path / "ROADMAP.md"
    p.write_text("- **g1-source-adequacy - decide the source floor\n"
                 "  images came from one - OPERATOR-GATED on policy.**\n"
                 "  Next: operator answers two questions.\n", encoding="utf-8")
    item, = st.read_operator_gated(p)["items"]

    assert item["id"] == "g1-source-adequacy"
    assert item["line_no"] == 1
    assert item["next"] == "operator answers two questions."


def test_the_roadmap_grep_declares_itself_fragile(tmp_path):
    # It is a prose grep on a heading convention. Saying so on the panel is the
    # difference between a stale row and a silently missing one.
    p = tmp_path / "ROADMAP.md"
    p.write_text(ROADMAP, encoding="utf-8")
    assert st.read_operator_gated(p)["fragile"] is True


def test_a_gated_item_with_no_next_line_still_appears(tmp_path):
    # Dropping it would hide a decision that is genuinely owed.
    p = tmp_path / "ROADMAP.md"
    p.write_text("- **orphan - OPERATOR-GATED.**\n", encoding="utf-8")
    item, = st.read_operator_gated(p)["items"]

    assert item["id"] == "orphan"
    assert item["next"] == ""


def test_an_absent_roadmap_is_zero_items_not_a_crash(tmp_path):
    out = st.read_operator_gated(tmp_path / "gone.md")
    assert out["present"] is False
    assert out["items"] == []


# ------------------------------------------------- P5: suite trajectory


def test_a_commit_with_an_observation_carries_its_counts_and_source():
    commits = [{"sha": "aaaaaaa", "subject": "one", "date": "2026-08-01T12:00:00Z"}]
    obs = [{"sha": "aaaaaaa", "passed": 1458, "failed": 0, "skipped": 16,
            "source": "truth_gate", "at": "2026-08-01T12:01:00Z"}]
    rows = st.build_suite_trajectory(commits, obs)["rows"]

    assert rows[0]["observed"] is True
    assert rows[0]["passed"] == 1458
    assert rows[0]["source"] == "truth_gate"


def test_a_commit_nobody_measured_is_a_gap_and_says_so():
    commits = [{"sha": "bbbbbbb", "subject": "two", "date": "2026-08-01T13:00:00Z"}]
    rows = st.build_suite_trajectory(commits, [])["rows"]

    assert rows[0]["observed"] is False
    assert rows[0]["passed"] is None
    assert rows[0]["delta"] is None


def test_a_delta_is_never_computed_across_a_gap():
    # THE rule of this panel. 1400 at commit one, nothing at commit two, 1500 at
    # commit three: "+100" would attribute to commit three work that may have
    # landed in commit two. The honest answer is that the chain is broken.
    commits = [{"sha": "c1aaaaa"}, {"sha": "c2bbbbb"}, {"sha": "c3ccccc"}]
    obs = [{"sha": "c1aaaaa", "passed": 1400, "source": "directive_history"},
           {"sha": "c3ccccc", "passed": 1500, "source": "directive_history"}]
    rows = st.build_suite_trajectory(commits, obs)["rows"]
    by_sha = {r["sha"]: r for r in rows}

    assert by_sha["c2bbbbb"]["observed"] is False
    assert by_sha["c3ccccc"]["delta"] is None
    assert by_sha["c3ccccc"]["delta_broken_by_gap"] is True


def test_a_delta_between_two_adjacent_observations_is_computed():
    commits = [{"sha": "c1aaaaa"}, {"sha": "c2bbbbb"}]
    obs = [{"sha": "c1aaaaa", "passed": 1400, "source": "x"},
           {"sha": "c2bbbbb", "passed": 1458, "source": "x"}]
    rows = st.build_suite_trajectory(commits, obs)["rows"]

    assert rows[1]["delta"] == 58
    assert rows[1]["delta_broken_by_gap"] is False


def test_a_count_that_drops_is_flagged_rather_than_shown_as_a_neutral_delta():
    # Deleted tests or a collection error. Either way it is not routine.
    commits = [{"sha": "c1aaaaa"}, {"sha": "c2bbbbb"}]
    obs = [{"sha": "c1aaaaa", "passed": 1458, "source": "x"},
           {"sha": "c2bbbbb", "passed": 1200, "source": "x"}]
    rows = st.build_suite_trajectory(commits, obs)["rows"]

    assert rows[1]["delta"] == -258
    assert rows[1]["regression"] is True


def test_the_coverage_summary_counts_what_was_never_measured():
    commits = [{"sha": "c1aaaaa"}, {"sha": "c2bbbbb"}, {"sha": "c3ccccc"}]
    obs = [{"sha": "c1aaaaa", "passed": 1, "source": "x"}]
    out = st.build_suite_trajectory(commits, obs)

    assert out["observed_count"] == 1
    assert out["gap_count"] == 2


def test_short_and_long_shas_match_each_other():
    # directive_history stores 8 chars, the manifest stores 7, git gives 40.
    commits = [{"sha": "abcdef1234567890"}]
    obs = [{"sha": "abcdef12", "passed": 10, "source": "directive_history"}]
    rows = st.build_suite_trajectory(commits, obs)["rows"]

    assert rows[0]["observed"] is True


def test_the_newest_observation_for_a_sha_wins_over_an_older_one():
    commits = [{"sha": "c1aaaaa"}]
    obs = [{"sha": "c1aaaaa", "passed": 1, "source": "old", "at": "2026-08-01T10:00:00Z"},
           {"sha": "c1aaaaa", "passed": 2, "source": "new", "at": "2026-08-01T11:00:00Z"}]
    rows = st.build_suite_trajectory(commits, obs)["rows"]

    assert rows[0]["passed"] == 2
    assert rows[0]["source"] == "new"
    assert rows[0]["observation_count"] == 2


def test_no_commits_is_an_empty_trajectory_not_a_crash():
    out = st.build_suite_trajectory([], [])
    assert out["rows"] == []
    assert out["gap_count"] == 0


# -------------------------------------------- P5: where the datapoints come from


def test_observations_are_harvested_from_the_cycle_chain_and_the_ladder():
    cycles = {"records": [
        {"sha_after": "aaaaaaa1", "tests": 1400, "ts": "2026-08-01T12:00:00"},
        {"sha_after": None, "tests": 1401, "ts": "2026-08-01T12:30:00"},
    ]}
    manifest = {"slices": [
        {"id": "B1", "commit": "bbbbbbb", "verdicts": [
            {"state": "CONFIRM", "observer": "truth_gate",
             "counts": {"passed": 1458, "skipped": 16, "failed": 0},
             "at": "2026-08-01T13:00:00Z"}]},
        {"id": "B2", "commit": "ccccccc", "verdicts": [
            {"state": "REFUTE", "observer": "verifier", "counts": None,
             "at": "2026-08-01T13:10:00Z"}]},
    ]}
    obs = st.collect_suite_observations(cycles, manifest)
    by_sha = {o["sha"]: o for o in obs}

    assert by_sha["aaaaaaa1"]["source"] == "directive_history"
    assert by_sha["bbbbbbb"]["passed"] == 1458
    assert by_sha["bbbbbbb"]["source"] == "truth_gate"
    # A cycle with no sha and a verdict with no counts are not datapoints. A
    # count that cannot be attached to a commit certifies nothing.
    assert "ccccccc" not in by_sha
    assert len(obs) == 2
