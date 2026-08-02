"""LW-CIWatchdog: the red-main auto-fixer's decision logic.

The task fires at startup and every 2 minutes, unattended, with permission to
push and merge. That authority is why almost all of the logic here is PURE and
tested in isolation: the parts that decide WHETHER to act must be readable and
provable without a GitHub API, a worktree, or a model call.

Three rails the tests exist to hold:

  1. HALT is checked first and answers everything. A kill switch that only works
     when the tool is otherwise healthy is not a kill switch.
  2. Ambiguity NEVER means act. `queued`, `pending`, `unavailable` and
     `not-evaluated` all wait. Only a settled `failure` triggers a fix - the same
     distinction f1 item 12 had to build into `check_ci`, for the same reason.
  3. The merge self-gates on the FIX BRANCH'S OWN green CI at its own head sha.
     Merging a ci-fix on anything else - the base's status, a stale run, a
     pending one - is how an auto-fixer turns one red main into two.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load():
    spec = importlib.util.spec_from_file_location(
        "lw_ci_watchdog_under_test", ROOT / "tools" / "ci_watchdog.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


cw = _load()

RED = {"status": "failure", "sha": "a" * 40, "runs": [{"name": "ci"}]}
GREEN = {"status": "success", "sha": "a" * 40}


# ---- 1. the kill switch ----------------------------------------------------

def test_halt_file_stops_everything(tmp_path: Path):
    (tmp_path / "HALT").write_text("operator", encoding="utf-8")
    assert cw.halted(tmp_path) == "operator"


def test_an_empty_halt_file_still_halts(tmp_path: Path):
    """`type nul > HALT` is the likeliest way an operator creates it under
    stress. An empty file must not read as 'no halt'."""
    (tmp_path / "HALT").write_text("", encoding="utf-8")
    assert cw.halted(tmp_path) == "HALT file present"


def test_no_halt_file_means_no_halt(tmp_path: Path):
    assert cw.halted(tmp_path) is None


def test_halt_beats_a_red_main(tmp_path: Path):
    (tmp_path / "HALT").write_text("stop", encoding="utf-8")
    assert cw.decide(RED, {}, halt=cw.halted(tmp_path))["action"] == "halt"


# ---- 2. ambiguity never means act -----------------------------------------

def test_a_settled_failure_is_the_only_trigger():
    assert cw.decide(RED, {})["action"] == "fix"


def test_green_is_idle():
    assert cw.decide(GREEN, {})["action"] == "idle"


def test_not_evaluated_is_idle_not_a_fix():
    """paths-ignore covered every changed file, so no run was ever coming.
    Nothing is broken and nothing is owed."""
    d = cw.decide({"status": "not-evaluated", "sha": "b" * 40}, {})
    assert d["action"] == "idle"


def test_every_unsettled_status_waits():
    for status in ("queued", "pending", "unavailable"):
        d = cw.decide({"status": status, "sha": "b" * 40}, {})
        assert d["action"] == "wait", status


def test_an_unknown_status_waits_rather_than_acting():
    """Fail closed on a status string nobody anticipated."""
    assert cw.decide({"status": "banana", "sha": "b" * 40}, {})["action"] == "wait"


# ---- 3. attempt budget -----------------------------------------------------

def test_a_second_attempt_on_the_same_sha_is_allowed():
    state = {"sha": "a" * 40, "attempts": 1}
    assert cw.decide(RED, state, max_attempts=2)["action"] == "fix"


def test_the_budget_is_exhausted_and_it_gives_up_loudly():
    state = {"sha": "a" * 40, "attempts": 2}
    d = cw.decide(RED, state, max_attempts=2)
    assert d["action"] == "give-up"
    assert "2" in d["reason"]


def test_a_new_red_sha_resets_the_budget():
    """The budget is per-sha. A different failure deserves its own attempts, or
    one exhausted sha would wedge the watchdog forever."""
    state = {"sha": "a" * 40, "attempts": 9}
    assert cw.decide({"status": "failure", "sha": "c" * 40}, state,
                     max_attempts=2)["action"] == "fix"


def test_bump_attempt_counts_within_a_sha_and_resets_across_them():
    s = cw.bump_attempt({}, "a" * 40)
    assert s == {"sha": "a" * 40, "attempts": 1}
    s = cw.bump_attempt(s, "a" * 40)
    assert s["attempts"] == 2
    s = cw.bump_attempt(s, "d" * 40)
    assert s["attempts"] == 1


def test_bump_attempt_does_not_mutate_its_input():
    src = {"sha": "a" * 40, "attempts": 1}
    cw.bump_attempt(src, "a" * 40)
    assert src["attempts"] == 1


# ---- 4. the merge self-gate ------------------------------------------------

def test_merge_needs_the_fix_branchs_own_green_ci():
    assert cw.merge_allowed({"status": "success", "sha": "f" * 40},
                            "f" * 40) is True


def test_merge_is_refused_when_the_green_is_for_another_sha():
    """A stale success from an earlier push on the same branch is the trap. The
    status must belong to the head being merged."""
    assert cw.merge_allowed({"status": "success", "sha": "0" * 40},
                            "f" * 40) is False


def test_merge_is_refused_on_anything_but_success():
    for status in ("failure", "pending", "queued", "unavailable",
                   "not-evaluated"):
        assert cw.merge_allowed({"status": status, "sha": "f" * 40},
                                "f" * 40) is False, status


def test_merge_is_refused_on_a_missing_status():
    assert cw.merge_allowed(None, "f" * 40) is False
    assert cw.merge_allowed({}, "f" * 40) is False


# ---- 5. naming + transient classification ----------------------------------

def test_branch_name_is_unique_per_sha_and_attempt():
    a = cw.branch_name("abcdef1234567890" + "0" * 24, 1)
    b = cw.branch_name("abcdef1234567890" + "0" * 24, 2)
    assert a != b
    assert a.startswith("ci-fix/")
    assert "abcdef12" in a


def test_branch_name_never_contains_a_path_separator_or_space():
    n = cw.branch_name("a" * 40, 1)
    assert " " not in n and "\\" not in n
    assert n.count("/") == 1


def test_a_transient_api_condition_is_not_a_repo_fault():
    """Same class the weekly-hygiene wrapper already handles: a credit or rate
    limit must not burn an attempt, or one bad afternoon exhausts the budget on
    a repo that was never broken."""
    for txt in ["credit balance is too low", "429 Too Many Requests",
                "API Error: overloaded", "rate_limit_error"]:
        assert cw.is_transient(txt) is True, txt


def test_an_ordinary_failure_is_not_transient():
    assert cw.is_transient("AssertionError: 3 tests failed") is False
    assert cw.is_transient("") is False


# ---- 6. single instance ----------------------------------------------------

def test_a_fresh_lock_blocks_a_second_run(tmp_path: Path):
    """The task fires every 2 minutes and a fix pass takes longer than that, so
    overlapping runs are the DEFAULT, not an edge case."""
    assert cw.acquire(tmp_path, pid=111, now=1000.0) is True
    assert cw.acquire(tmp_path, pid=222, now=1030.0) is False


def test_a_stale_lock_is_reclaimed(tmp_path: Path):
    assert cw.acquire(tmp_path, pid=111, now=1000.0) is True
    assert cw.acquire(tmp_path, pid=222, now=1000.0 + cw.LOCK_STALE_S + 1) is True


def test_release_lets_the_next_run_in(tmp_path: Path):
    assert cw.acquire(tmp_path, pid=111, now=1000.0) is True
    cw.release(tmp_path)
    assert cw.acquire(tmp_path, pid=222, now=1001.0) is True


def test_a_corrupt_lock_file_does_not_wedge_the_watchdog(tmp_path: Path):
    (tmp_path / "lock.json").write_text("{not json", encoding="utf-8")
    assert cw.acquire(tmp_path, pid=111, now=1000.0) is True
