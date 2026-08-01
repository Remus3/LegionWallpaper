"""The start gate: a slice cannot enter `in_progress` unless its files are held.

The claim table (BACKLOG mcp-lift-phases P4) made disjointness CHECKABLE. Nothing
called it, so it stayed advisory - exactly the gap f1-phase6 queue item 7 names:
nothing refuses to start an agent without a granted claim. This file pins the
enforcement half, lifted from task-orchestrator's one unique property (BACKLOG
P7): a precondition that is not met makes the CALL fail, versus a prompt-based
framework where the same rule is only what an agent "should follow". An agent
that can ignore the gate does not have a gate.

The gate rides on the `pending -> in_progress` transition in `set`, and NOT on a
separate `start` subcommand, deliberately: a second door that skipped the check
would be the bypass, and a dispatcher writing `set --status in_progress` is what
the skill already documents.

Three refusals carry the weight:

  1. UNCLAIMED. The slice declares files nobody holds - the agent is starting on
     ground no one reserved, which is the state that loses a run's work when a
     second agent is handed the same file.
  2. HELD BY ANOTHER. Worse than unclaimed and must not read the same: the
     refusal names the holder, because the operator's next action is to go look
     at what that agent is doing.
  3. NO FILES AT ALL. A slice with an empty file list cannot prove disjointness
     about anything, so it is the trivial bypass of every other rule here. It is
     refused rather than waved through.

A refused start must leave the manifest byte-identical. A gate that half-wrote
the status it refused to grant would be worse than no gate.

Every test routes writes through an explicit --manifest under tmp_path; nothing
here may touch the live ops/runtime/slice_manifest.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import slice_orchestrator as so  # noqa: E402


def _target(tmp_path):
    return tmp_path / "ops" / "runtime" / "slice_manifest.json"


def _run(manifest, *argv):
    return so.main([*argv, "--manifest", str(manifest)])


def _load(manifest):
    return json.loads(Path(manifest).read_text(encoding="utf-8"))


def _init(manifest, run_id="2026-08-01-02", head="deadbee"):
    return _run(manifest, "init", "--run-id", run_id, "--head", head)


def _slice(manifest, slice_id="S1", files="tools/a.py,tools/b.py"):
    return _run(manifest, "add", "--id", slice_id, "--title", "t", "--files", files)


def _status(manifest, slice_id="S1"):
    return next(s["status"] for s in _load(manifest)["slices"] if s["id"] == slice_id)


# ---------------------------------------------------------------- the refusals
def test_start_is_refused_when_no_one_holds_the_files(tmp_path):
    target = _target(tmp_path)
    _init(target)
    _slice(target)
    assert _run(target, "set", "--id", "S1", "--status", "in_progress",
                "--agent", "A1") != 0
    assert _status(target) == "pending"


def test_start_is_refused_when_only_some_of_the_files_are_claimed(tmp_path):
    # All-or-nothing, same discipline as the claim itself: an agent that starts
    # on the half it got still edits a file another agent may be handed.
    target = _target(tmp_path)
    _init(target)
    _slice(target)
    _run(target, "claim", "--agent", "A1", "--files", "tools/a.py")
    assert _run(target, "set", "--id", "S1", "--status", "in_progress",
                "--agent", "A1") != 0
    assert _status(target) == "pending"


def test_start_is_refused_when_another_agent_holds_a_file(tmp_path, capsys):
    target = _target(tmp_path)
    _init(target)
    _slice(target)
    _run(target, "claim", "--agent", "A1", "--files", "tools/a.py,tools/b.py")
    capsys.readouterr()
    assert _run(target, "set", "--id", "S1", "--status", "in_progress",
                "--agent", "A2") != 0
    err = capsys.readouterr().err
    assert "tools/a.py" in err and "A1" in err     # names the file AND the holder
    assert _status(target) == "pending"


def test_start_is_refused_without_an_agent_id(tmp_path):
    # The old call shape. It cannot keep working, or the gate is opt-in.
    target = _target(tmp_path)
    _init(target)
    _slice(target)
    _run(target, "claim", "--agent", "A1", "--files", "tools/a.py,tools/b.py")
    assert _run(target, "set", "--id", "S1", "--status", "in_progress") != 0
    assert _status(target) == "pending"


def test_start_is_refused_for_a_slice_that_declares_no_files(tmp_path):
    # The trivial bypass: declare nothing, claim nothing, pass every other check.
    target = _target(tmp_path)
    _init(target)
    _run(target, "add", "--id", "S1", "--title", "unbounded")
    assert _run(target, "set", "--id", "S1", "--status", "in_progress",
                "--agent", "A1") != 0
    assert _status(target) == "pending"


def test_a_refused_start_leaves_the_manifest_byte_identical(tmp_path):
    target = _target(tmp_path)
    _init(target)
    _slice(target)
    before = Path(target).read_bytes()
    assert _run(target, "set", "--id", "S1", "--status", "in_progress",
                "--agent", "A1", "--note", "dispatched") != 0
    assert Path(target).read_bytes() == before


# ---------------------------------------------------------------- what passes
def test_start_is_granted_when_the_agent_holds_every_file(tmp_path):
    target = _target(tmp_path)
    _init(target)
    _slice(target)
    _run(target, "claim", "--agent", "A1", "--files", "tools/a.py,tools/b.py")
    assert _run(target, "set", "--id", "S1", "--status", "in_progress",
                "--agent", "A1", "--note", "dispatched") == 0
    entry = next(s for s in _load(target)["slices"] if s["id"] == "S1")
    assert entry["status"] == "in_progress"
    assert entry["note"] == "dispatched"


def test_a_directory_claim_covers_the_files_under_it(tmp_path):
    # `_contains` is already segment-wise for conflicts; the grant side has to
    # agree, or an agent that reserved a whole subtree is refused its own work.
    target = _target(tmp_path)
    _init(target)
    _slice(target, files="tools/sub/a.py,tools/sub/b.py")
    _run(target, "claim", "--agent", "A1", "--files", "tools/sub")
    assert _run(target, "set", "--id", "S1", "--status", "in_progress",
                "--agent", "A1") == 0
    assert _status(target) == "in_progress"


def test_the_slice_file_list_is_normalized_the_same_way_a_claim_is(tmp_path):
    # A slice added with backslashes and a claim written with forward slashes are
    # the same file. Comparing raw strings here would refuse a granted claim.
    target = _target(tmp_path)
    _init(target)
    _slice(target, files="tools\\Sub\\A.py")
    _run(target, "claim", "--agent", "A1", "--files", "./tools/sub/a.py")
    assert _run(target, "set", "--id", "S1", "--status", "in_progress",
                "--agent", "A1") == 0
    assert _status(target) == "in_progress"


@pytest.mark.parametrize("status", [s for s in so.STATUSES if s != "in_progress"])
def test_no_other_status_is_gated(tmp_path, status):
    # The gate is about BEGINNING work. `verified` and `committed` are observations
    # about work already done, and a crashed agent's claims may already be gone -
    # gating those would strand a finished slice with no way to record it.
    target = _target(tmp_path)
    _init(target)
    _slice(target)
    assert _run(target, "set", "--id", "S1", "--status", status) == 0
    assert _status(target) == status


def test_a_released_claim_makes_a_restart_refuse_again(tmp_path):
    # The gate reads live state, not a once-granted permission: an agent that
    # released its files on the way out cannot be re-dispatched onto them.
    target = _target(tmp_path)
    _init(target)
    _slice(target)
    _run(target, "claim", "--agent", "A1", "--files", "tools/a.py,tools/b.py")
    _run(target, "set", "--id", "S1", "--status", "in_progress", "--agent", "A1")
    _run(target, "set", "--id", "S1", "--status", "pending")
    _run(target, "release", "--agent", "A1")
    assert _run(target, "set", "--id", "S1", "--status", "in_progress",
                "--agent", "A1") != 0
    assert _status(target) == "pending"


# ---------------------------------------------------------------- the predicate
def test_start_gate_reports_every_unmet_precondition_not_just_the_first(tmp_path):
    # The operator fixes what the refusal lists. Reporting one problem per run
    # turns one broken dispatch into three round-trips.
    manifest = {"schema": so.SCHEMA, "slices": [
        {"id": "S1", "files": ["tools/a.py", "tools/b.py", "tools/c.py"],
         "status": "pending"}]}
    so.claim_files(manifest, "A2", ["tools/b.py"])
    ok, problems = so.start_gate(manifest, "S1", "A1")
    assert ok is False
    joined = " | ".join(problems)
    assert "tools/a.py" in joined and "tools/c.py" in joined
    assert "tools/b.py" in joined and "A2" in joined


def test_start_gate_refuses_an_unknown_slice_id(tmp_path):
    manifest = {"schema": so.SCHEMA, "slices": []}
    ok, problems = so.start_gate(manifest, "S9", "A1")
    assert ok is False
    assert any("S9" in p for p in problems)
