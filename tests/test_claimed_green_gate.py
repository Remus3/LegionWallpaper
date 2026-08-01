"""Characterization tests for the Stop-hook claimed-green gate (P1).

The gate answers one question at the moment Claude says it is done: was a
"tests pass" claim backed by a run that actually happened in this session?

Contract under test, from the official hook docs (docs/MCP_LIFT_DIVE_2026-08-01
section 3, Item B):
  - input arrives as JSON on stdin with `stop_hook_active`,
    `last_assistant_message` and `transcript_path`
  - a block is exit 0 with top-level {"decision": "block", "reason": ...}
  - `stop_hook_active` is COOPERATIVE - the harness does not cap the loop, so an
    always-block hook wedges the session forever. This is the single most
    important test in the file.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

GATE = Path(__file__).resolve().parents[1] / "tools" / "claimed_green_gate.py"


def _line(**kw) -> str:
    return json.dumps(kw)


def _assistant_bash(command: str, stdout: str = "", code: int = 0) -> str:
    """One assistant turn issuing a Bash tool call, as Claude Code records it."""
    return _line(
        type="assistant",
        message={
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "name": "Bash",
                    "input": {"command": command},
                }
            ],
        },
        toolUseResult={"stdout": stdout, "code": code},
    )


def _paired_bash(
    command: str,
    stdout: str = "",
    tool_id: str = "toolu_01",
    interrupted: str = "False",
) -> list:
    """The REAL Claude Code shape, measured against a live 1.4 MB transcript.

    The result does NOT sit on the assistant entry - it arrives on a LATER user
    entry, joined by `tool_use_id`, with the payload at entry-level
    `toolUseResult`. Bash results carry NO `code` field at all: just stdout,
    stderr and `interrupted`, and `interrupted` is the STRING "False", not a
    bool. Synthetic same-entry fixtures hid all three of these.
    """
    return [
        _line(
            type="assistant",
            message={
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": tool_id,
                        "name": "Bash",
                        "input": {"command": command},
                    }
                ],
            },
        ),
        _line(
            type="user",
            message={
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": tool_id}],
            },
            toolUseResult={
                "stdout": stdout,
                "stderr": "",
                "interrupted": interrupted,
                "isImage": False,
            },
        ),
    ]


def _user_text(text: str) -> str:
    return _line(type="user", message={"role": "user", "content": text})


def _transcript(tmp_path: Path, *lines: str) -> Path:
    path = tmp_path / "transcript.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def run_gate(payload: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(GATE)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
    )


def decision_of(proc: subprocess.CompletedProcess) -> dict:
    if not proc.stdout.strip():
        return {}
    return json.loads(proc.stdout)


PASSING = "1537 passed, 16 skipped in 42.10s"
FAILING = "1 failed, 1536 passed in 41.88s"


# --- the loop guard: this is the one that must never regress ----------------


def test_stop_hook_active_always_allows(tmp_path):
    """An always-block Stop hook loops forever. stop_hook_active breaks it."""
    transcript = _transcript(tmp_path, _user_text("go"))
    proc = run_gate(
        {
            "hook_event_name": "Stop",
            "stop_hook_active": True,
            "last_assistant_message": "All tests pass, suite is green.",
            "transcript_path": str(transcript),
        }
    )
    assert proc.returncode == 0
    assert decision_of(proc) == {}


# --- claim detection --------------------------------------------------------


def test_no_claim_allows(tmp_path):
    transcript = _transcript(tmp_path, _user_text("go"))
    proc = run_gate(
        {
            "stop_hook_active": False,
            "last_assistant_message": "Wrote the docs. Nothing else to report.",
            "transcript_path": str(transcript),
        }
    )
    assert proc.returncode == 0
    assert decision_of(proc) == {}


@pytest.mark.parametrize(
    "claim",
    [
        "All tests pass.",
        "Suite is green.",
        "1537 passed, 16 skipped.",
        "CI is green on that commit.",
        "The full suite passes now.",
    ],
)
def test_green_claims_are_recognized(tmp_path, claim):
    transcript = _transcript(tmp_path, _user_text("go"))
    proc = run_gate(
        {
            "stop_hook_active": False,
            "last_assistant_message": claim,
            "transcript_path": str(transcript),
        }
    )
    assert decision_of(proc).get("decision") == "block", claim


# --- detector: claim-no-run -------------------------------------------------


def test_claim_with_no_run_blocks(tmp_path):
    transcript = _transcript(
        tmp_path,
        _user_text("fix it"),
        _assistant_bash("git status --short"),
    )
    proc = run_gate(
        {
            "stop_hook_active": False,
            "last_assistant_message": "Done - all tests pass.",
            "transcript_path": str(transcript),
        }
    )
    assert proc.returncode == 0
    decision = decision_of(proc)
    assert decision["decision"] == "block"
    assert "claim-no-run" in decision["reason"]


def test_claim_with_passing_run_allows(tmp_path):
    transcript = _transcript(
        tmp_path,
        _user_text("fix it"),
        _assistant_bash("python -m pytest -q", stdout=PASSING, code=0),
    )
    proc = run_gate(
        {
            "stop_hook_active": False,
            "last_assistant_message": "Done - 1537 passed, 16 skipped.",
            "transcript_path": str(transcript),
        }
    )
    assert decision_of(proc) == {}


def test_run_in_a_subagent_counts(tmp_path):
    """A suite run by a subagent is still a run - do not accuse on sidechains."""
    transcript = _transcript(
        tmp_path,
        _line(
            type="assistant",
            isSidechain=True,
            message={
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Bash",
                        "input": {"command": "pytest tests/ -q"},
                    }
                ],
            },
            toolUseResult={"stdout": PASSING, "code": 0},
        ),
    )
    proc = run_gate(
        {
            "stop_hook_active": False,
            "last_assistant_message": "Suite is green.",
            "transcript_path": str(transcript),
        }
    )
    assert decision_of(proc) == {}


# --- detector: claim-vs-fail ------------------------------------------------


def test_claim_after_failing_run_blocks(tmp_path):
    transcript = _transcript(
        tmp_path,
        _assistant_bash("python -m pytest -q", stdout=FAILING, code=1),
    )
    proc = run_gate(
        {
            "stop_hook_active": False,
            "last_assistant_message": "All tests pass now.",
            "transcript_path": str(transcript),
        }
    )
    decision = decision_of(proc)
    assert decision["decision"] == "block"
    assert "claim-vs-fail" in decision["reason"]


def test_failing_then_passing_run_allows(tmp_path):
    """The LAST run is what the claim is about - a red-then-green fix is normal."""
    transcript = _transcript(
        tmp_path,
        _assistant_bash("python -m pytest -q", stdout=FAILING, code=1),
        _assistant_bash("python -m pytest -q", stdout=PASSING, code=0),
    )
    proc = run_gate(
        {
            "stop_hook_active": False,
            "last_assistant_message": "All tests pass now.",
            "transcript_path": str(transcript),
        }
    )
    assert decision_of(proc) == {}


def test_interrupted_run_is_not_a_failure(tmp_path):
    """Exit 124/137/143 is an interrupted run, not a red suite - do not accuse."""
    transcript = _transcript(
        tmp_path,
        _assistant_bash("python -m pytest -q", stdout="", code=143),
        _assistant_bash("python -m pytest -q", stdout=PASSING, code=0),
    )
    proc = run_gate(
        {
            "stop_hook_active": False,
            "last_assistant_message": "Suite green.",
            "transcript_path": str(transcript),
        }
    )
    assert decision_of(proc) == {}


# --- detector: no-verify ----------------------------------------------------


def test_commit_after_hook_rejection_blocks(tmp_path):
    transcript = _transcript(
        tmp_path,
        _assistant_bash(
            "git commit -m x",
            stdout="precommit_gate BLOCKED commit - net-new violations",
            code=1,
        ),
        _assistant_bash("git commit --no-verify -m x", stdout="[main abc123]", code=0),
    )
    proc = run_gate(
        {
            "stop_hook_active": False,
            "last_assistant_message": "Committed and pushed.",
            "transcript_path": str(transcript),
        }
    )
    decision = decision_of(proc)
    assert decision["decision"] == "block"
    assert "no-verify" in decision["reason"]


def test_no_verify_without_a_prior_rejection_is_not_blocked(tmp_path):
    """No hook rejection before it - suspicious at most, and not this gate's call."""
    transcript = _transcript(
        tmp_path,
        _assistant_bash("git commit --no-verify -m x", stdout="[main abc123]", code=0),
    )
    proc = run_gate(
        {
            "stop_hook_active": False,
            "last_assistant_message": "Committed.",
            "transcript_path": str(transcript),
        }
    )
    assert decision_of(proc) == {}


def test_git_push_dash_n_is_not_a_commit_bypass(tmp_path):
    """`git push -n` is a dry run. Segment the command, do not substring-match."""
    transcript = _transcript(
        tmp_path,
        _assistant_bash("git commit -m x", stdout="pre-commit hook failed", code=1),
        _assistant_bash("git push -n origin main", stdout="", code=0),
    )
    proc = run_gate(
        {
            "stop_hook_active": False,
            "last_assistant_message": "Pushed.",
            "transcript_path": str(transcript),
        }
    )
    assert decision_of(proc) == {}


# --- never wedge the session ------------------------------------------------


@pytest.mark.parametrize("payload", [{}, {"transcript_path": "nope.jsonl"}])
def test_unreadable_input_allows(payload):
    proc = run_gate(payload)
    assert proc.returncode == 0
    assert decision_of(proc) == {}


def test_corrupt_transcript_lines_are_skipped(tmp_path):
    path = tmp_path / "transcript.jsonl"
    path.write_text(
        "not json at all\n"
        + _assistant_bash("python -m pytest -q", stdout=PASSING, code=0)
        + "\n{\n",
        encoding="utf-8",
    )
    proc = run_gate(
        {
            "stop_hook_active": False,
            "last_assistant_message": "Tests pass.",
            "transcript_path": str(path),
        }
    )
    assert proc.returncode == 0
    assert decision_of(proc) == {}


def test_operator_waiver_allows(tmp_path):
    """If the operator said not to run them, a green claim is not an accusation."""
    transcript = _transcript(tmp_path, _user_text("skip the tests, just commit it"))
    proc = run_gate(
        {
            "stop_hook_active": False,
            "last_assistant_message": "Committed. Tests pass as of the last run.",
            "transcript_path": str(transcript),
        }
    )
    assert decision_of(proc) == {}


# --- the REAL transcript shape ---------------------------------------------
# These are the regression tests for the bug the synthetic fixtures above hid:
# a live probe found 46 commands and 2 pytest runs, and classified BOTH as
# "unknown" because the result never joined back to the call.


def test_real_shape_passing_run_allows(tmp_path):
    transcript = _transcript(
        tmp_path, *_paired_bash("python -m pytest -q", stdout=PASSING)
    )
    proc = run_gate(
        {
            "stop_hook_active": False,
            "last_assistant_message": "Done - 1537 passed, 16 skipped.",
            "transcript_path": str(transcript),
        }
    )
    assert decision_of(proc) == {}, "the run is right there in the transcript"


def test_real_shape_failing_run_blocks(tmp_path):
    transcript = _transcript(
        tmp_path, *_paired_bash("python -m pytest -q", stdout=FAILING)
    )
    proc = run_gate(
        {
            "stop_hook_active": False,
            "last_assistant_message": "All tests pass.",
            "transcript_path": str(transcript),
        }
    )
    assert decision_of(proc)["decision"] == "block"
    assert "claim-vs-fail" in decision_of(proc)["reason"]


def test_real_shape_interrupted_string_is_not_a_failure(tmp_path):
    """`interrupted` arrives as the STRING "True" - truthiness alone is a trap."""
    lines = _paired_bash("python -m pytest -q", stdout="", tool_id="a", interrupted="True")
    lines += _paired_bash("python -m pytest -q", stdout=PASSING, tool_id="b")
    transcript = _transcript(tmp_path, *lines)
    proc = run_gate(
        {
            "stop_hook_active": False,
            "last_assistant_message": "Suite green.",
            "transcript_path": str(transcript),
        }
    )
    assert decision_of(proc) == {}


def test_real_shape_no_code_field_and_no_output_is_unknown_not_pass(tmp_path):
    """No code, no counts - that is not evidence of green, so the claim is bare."""
    transcript = _transcript(
        tmp_path, *_paired_bash("python -m pytest -q", stdout="")
    )
    proc = run_gate(
        {
            "stop_hook_active": False,
            "last_assistant_message": "All tests pass.",
            "transcript_path": str(transcript),
        }
    )
    decision = decision_of(proc)
    assert decision.get("decision") == "block"
    assert "no-counts" in decision["reason"]


def test_real_shape_no_verify_after_rejection_blocks(tmp_path):
    lines = _paired_bash(
        "git commit -m x",
        stdout="precommit_gate BLOCKED commit - net-new violations",
        tool_id="a",
    )
    lines += _paired_bash("git commit --no-verify -m x", stdout="[main abc]", tool_id="b")
    transcript = _transcript(tmp_path, *lines)
    proc = run_gate(
        {
            "stop_hook_active": False,
            "last_assistant_message": "Committed.",
            "transcript_path": str(transcript),
        }
    )
    assert "no-verify" in decision_of(proc)["reason"]


def test_block_reason_is_ascii_and_actionable(tmp_path):
    transcript = _transcript(tmp_path, _user_text("go"))
    proc = run_gate(
        {
            "stop_hook_active": False,
            "last_assistant_message": "All tests pass.",
            "transcript_path": str(transcript),
        }
    )
    reason = decision_of(proc)["reason"]
    reason.encode("ascii")
    assert "pytest" in reason
