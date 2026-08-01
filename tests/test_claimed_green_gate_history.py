"""The RETROSPECTIVE half of L2: how often was a green claim in this repo unbacked?

P1 shipped the LIVE gate - a Stop hook that reads one payload and answers for the
turn it is stopping. The question the triage actually posed is the other
direction and was left untouched: run the same detectors over the history and
COUNT. A gate that starts today says nothing about the 81 transcripts already on
disk, and "this is LW's most documented failure class" was itself a claim backed
by anecdote.

The retrospective is NOT the live gate pointed at an old file, and this file
pins the difference:

  1. PREFIX SEMANTICS. Live, the transcript ends at the claim, so every action in
     it happened BEFORE the claim. Retrospectively a transcript keeps going, so a
     run that happened AFTER a claim must not back it - that is exactly the
     "reported first, verified later" pattern the gate exists to catch, and
     evaluating over the whole file would launder it into a pass.
  2. EVERY claim is assessed, not just the last one. A session that claimed green
     three times gets three verdicts.
  3. It REPORTS, it does not block. Exit stays 0 whatever it finds; a
     non-zero exit would make a historical audit fail a CI run.

The hook path must keep working with NO argv and a stdin payload - adding a CLI
is the most likely way to break the live gate, so that regression is tested here
rather than assumed.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "tools" / "claimed_green_gate.py"

sys.path.insert(0, str(ROOT / "tools"))

import claimed_green_gate as gate  # noqa: E402


# --------------------------------------------------------------- fixture shapes
def _line(**kw) -> str:
    return json.dumps(kw)


def _claim(text: str) -> str:
    """An assistant turn that is prose, not a tool call."""
    return _line(type="assistant",
                 message={"role": "assistant", "content": [{"type": "text", "text": text}]})


def _run(command: str, stdout: str = "", tool_id: str = "toolu_01") -> list:
    """The REAL two-entry shape: the call, then the result on a LATER user entry."""
    call = _line(type="assistant",
                 message={"role": "assistant",
                          "content": [{"type": "tool_use", "id": tool_id,
                                       "name": "Bash", "input": {"command": command}}]})
    result = _line(type="user",
                   message={"role": "user",
                            "content": [{"type": "tool_result", "tool_use_id": tool_id}]},
                   toolUseResult={"stdout": stdout, "stderr": "", "interrupted": "False"})
    return [call, result]


def _subagent_run(command: str, output: str = "", tool_id: str = "toolu_s1",
                  is_error: bool = False) -> list:
    """The SUBAGENT shape, measured on a live sidechain transcript.

    A subagent file carries NO entry-level `toolUseResult` at all - the output
    sits on the tool_result PART as `content` (str or block list) with
    `is_error`. Reading only the main-thread shape joins ZERO results here, which
    scores every subagent suite run as "no evidence" and manufactures a
    no-counts finding out of a perfectly good green run.
    """
    call = _line(type="assistant", isSidechain=True,
                 message={"role": "assistant",
                          "content": [{"type": "tool_use", "id": tool_id,
                                       "name": "Bash", "input": {"command": command}}]})
    result = _line(type="user", isSidechain=True,
                   message={"role": "user",
                            "content": [{"type": "tool_result", "tool_use_id": tool_id,
                                         "content": output, "is_error": is_error}]})
    return [call, result]


def _transcript(tmp_path, *chunks, name="session.jsonl") -> Path:
    lines = []
    for chunk in chunks:
        lines.extend(chunk if isinstance(chunk, list) else [chunk])
    target = tmp_path / name
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


PASS = "1640 passed, 16 skipped in 70.55s"
FAIL = "1 failed, 1639 passed in 71.02s"
PYTEST = "python -m pytest tests/ -q"


# --------------------------------------------------------------- prefix semantics
def test_a_run_after_the_claim_does_not_back_it(tmp_path):
    # THE retrospective-only rule. Claiming first and verifying afterwards is the
    # failure mode; evaluating the whole file would score it as backed.
    t = _transcript(tmp_path, _claim("all tests pass"), _run(PYTEST, PASS))
    findings = gate.audit_transcript(t)
    assert [f["detector"] for f in findings] == ["claim-no-run"]


def test_a_run_before_the_claim_backs_it(tmp_path):
    t = _transcript(tmp_path, _run(PYTEST, PASS), _claim("suite is green, 1640 passed"))
    assert gate.audit_transcript(t) == []


def test_each_claim_is_assessed_separately(tmp_path):
    # First claim unbacked, then a real run, then a second claim that IS backed.
    t = _transcript(tmp_path,
                    _claim("tests pass"),
                    _run(PYTEST, PASS, tool_id="toolu_02"),
                    _claim("confirmed: 1640 passed"))
    findings = gate.audit_transcript(t)
    assert [f["detector"] for f in findings] == ["claim-no-run"]


def test_the_last_run_before_a_claim_is_the_one_that_counts(tmp_path):
    t = _transcript(tmp_path,
                    _run(PYTEST, PASS, tool_id="toolu_01"),
                    _run(PYTEST, FAIL, tool_id="toolu_02"),
                    _claim("suite is green"))
    findings = gate.audit_transcript(t)
    assert [f["detector"] for f in findings] == ["claim-vs-fail"]


def test_a_red_run_followed_by_a_green_rerun_then_a_claim_is_clean(tmp_path):
    t = _transcript(tmp_path,
                    _run(PYTEST, FAIL, tool_id="toolu_01"),
                    _run(PYTEST, PASS, tool_id="toolu_02"),
                    _claim("1640 passed"))
    assert gate.audit_transcript(t) == []


def test_a_pytest_run_with_no_counts_is_not_evidence(tmp_path):
    t = _transcript(tmp_path, _run(PYTEST, ""), _claim("tests pass"))
    findings = gate.audit_transcript(t)
    assert [f["detector"] for f in findings] == ["no-counts"]


# --------------------------------------------------------------- shared rules
def test_a_waiver_anywhere_in_the_session_suppresses_the_finding(tmp_path):
    user = _line(type="user", message={"role": "user",
                                       "content": "ship it, no need to run the tests"})
    t = _transcript(tmp_path, user, _claim("tests pass"))
    assert gate.audit_transcript(t) == []


def test_a_non_claim_turn_is_never_assessed(tmp_path):
    t = _transcript(tmp_path, _claim("edited the file and pushed"))
    assert gate.audit_transcript(t) == []


def test_the_finding_carries_where_and_what_so_it_can_be_hand_checked(tmp_path):
    # A count nobody can audit is the same species of unbacked claim this tool
    # exists to catch, so every finding names its file and quotes its claim.
    t = _transcript(tmp_path, _claim("all tests pass now"))
    finding = gate.audit_transcript(t)[0]
    assert finding["transcript"] == str(t)
    assert "all tests pass now" in finding["claim"]
    assert finding["detector"] == "claim-no-run"


def test_a_subagent_run_still_backs_a_claim(tmp_path):
    # Same rule the live gate holds: a suite run by a subagent is still a run.
    t = _transcript(tmp_path,
                    _run("python -m pytest tests/test_x.py -q", "12 passed"),
                    _claim("tests pass"))
    assert gate.audit_transcript(t) == []


# ------------------------------------------------- reporting red is not claiming green
def test_a_tdd_red_report_is_not_a_green_claim(tmp_path):
    """The first sweep flagged THIS repo's own TDD reports as false claims.

    "12 failed / 4 passed" matches the green pattern on `\\d+ passed`, and the
    last run really was red, so claim-vs-fail fired on a turn doing exactly what
    the TDD rule demands - reporting a deliberate failure. A gate that blocks the
    RED half of red-green gets disabled within a day.
    """
    t = _transcript(tmp_path, _run(PYTEST, FAIL), _claim("Failing-first confirmed (12 failed / 4 passed). Now the gate."))
    assert gate.audit_transcript(t) == []


def test_an_honest_report_of_pre_existing_failures_is_not_a_green_claim(tmp_path):
    t = _transcript(tmp_path, _run(PYTEST, FAIL),
                    _claim("Fresh suite: the same 7 pre-existing failures, 7 failed, 529 passed."))
    assert gate.audit_transcript(t) == []


def test_reporting_failures_in_words_counts_as_reporting_red(tmp_path):
    # "7 failures" and "a single pre-existing failure" are the same disclosure as
    # "7 failed", and the sweep flagged both wordings as false green claims.
    t = _transcript(tmp_path, _run(PYTEST, FAIL),
                    _claim("Confirmed pre-existing: identical 7 failures at HEAD, 529 passed here"))
    assert gate.audit_transcript(t) == []


def test_relaying_a_subagent_count_while_declining_to_trust_it_is_not_a_claim(tmp_path):
    # LW's Verification Discipline REQUIRES this turn shape - quote the agent's
    # number, refuse to carry it forward, go verify. Blocking it would punish the
    # exact behaviour the rule mandates.
    t = _transcript(tmp_path,
                    _claim("Build agent claims 27 passed, ruff clean. Per Verification "
                           "Discipline I don't trust a subagent's counts - verifying now."))
    assert gate.audit_transcript(t) == []


def test_asserting_a_subagent_count_as_fact_is_still_caught(tmp_path):
    # The exemption is for DECLINING to trust. Carrying the number forward as
    # your own, with no run, is the failure the discipline names.
    t = _transcript(tmp_path, _claim("Green: 27 passed, ruff clean. Merging."))
    assert [f["detector"] for f in gate.audit_transcript(t)] == ["claim-no-run"]


def test_a_plain_green_claim_after_a_red_run_is_still_caught(tmp_path):
    # The exemption must not swallow the detector it lives in.
    t = _transcript(tmp_path, _run(PYTEST, FAIL), _claim("suite is green, all tests pass"))
    assert [f["detector"] for f in gate.audit_transcript(t)] == ["claim-vs-fail"]


# ------------------------------------------------- the subagent result shape
def test_a_subagent_run_result_is_joined_from_the_tool_result_part(tmp_path):
    # Measured on C--LegionWallpaper/<session>/subagents/*.jsonl: 16 tool_use,
    # 16 tool_result parts, ZERO entry-level toolUseResult. Before this, the
    # first sweep read 172 no-counts findings that were mostly this bug.
    t = _transcript(tmp_path, _subagent_run(PYTEST, PASS), _claim("1640 passed"))
    assert gate.audit_transcript(t) == []


def test_a_subagent_run_content_can_be_a_block_list(tmp_path):
    call = _line(type="assistant",
                 message={"role": "assistant",
                          "content": [{"type": "tool_use", "id": "toolu_b",
                                       "name": "Bash", "input": {"command": PYTEST}}]})
    result = _line(type="user",
                   message={"role": "user",
                            "content": [{"type": "tool_result", "tool_use_id": "toolu_b",
                                         "content": [{"type": "text", "text": PASS}]}]})
    t = _transcript(tmp_path, [call, result], _claim("suite is green"))
    assert gate.audit_transcript(t) == []


def test_a_subagent_run_that_errored_is_not_read_as_green(tmp_path):
    t = _transcript(tmp_path,
                    _subagent_run(PYTEST, "collection error", is_error=True),
                    _claim("tests pass"))
    assert [f["detector"] for f in gate.audit_transcript(t)] == ["claim-vs-fail"]


def test_the_entry_level_payload_still_wins_where_it_exists(tmp_path):
    # The main-thread shape must not regress: it carries the real stdout, while
    # a same-id part may carry a truncated view.
    t = _transcript(tmp_path, _run(PYTEST, PASS), _claim("1640 passed"))
    assert gate.audit_transcript(t) == []


def test_a_hook_bypass_is_reported_even_with_no_green_claim(tmp_path):
    # The third detector is not claim-tied: bypassing a rejection is its own
    # finding, and a historical sweep that only counted claims would miss it.
    t = _transcript(tmp_path,
                    _run("git commit -m x", "precommit_gate BLOCKED: banned glyph",
                         tool_id="toolu_01"),
                    _run("git commit --no-verify -m x", "", tool_id="toolu_02"))
    assert [f["detector"] for f in gate.audit_transcript(t)] == ["no-verify"]


# --------------------------------------------------------------- the sweep
def test_audit_tree_walks_nested_session_directories(tmp_path):
    # Subagent transcripts live one level down under <session>/subagents/, and
    # skipping them would undercount the corpus AND miss the runs that back
    # main-thread claims.
    nested = tmp_path / "153bbbb2" / "subagents"
    nested.mkdir(parents=True)
    _transcript(tmp_path, _claim("tests pass"), name="top.jsonl")
    _transcript(nested, _claim("suite is green"), name="sub.jsonl")
    findings = gate.audit_tree(tmp_path)
    assert len(findings) == 2
    assert {Path(f["transcript"]).name for f in findings} == {"top.jsonl", "sub.jsonl"}


def test_audit_tree_survives_an_unreadable_or_malformed_transcript(tmp_path):
    # 81 real files; one bad line must not abort the sweep and silently report a
    # smaller, cleaner-looking number.
    (tmp_path / "broken.jsonl").write_text("{not json\n\x00\n", encoding="utf-8")
    _transcript(tmp_path, _claim("tests pass"), name="ok.jsonl")
    findings = gate.audit_tree(tmp_path)
    assert [Path(f["transcript"]).name for f in findings] == ["ok.jsonl"]


def test_summarize_counts_claims_and_findings_not_just_findings(tmp_path):
    # "How often" is a RATE. Findings alone cannot answer it - the denominator is
    # the number of green claims made, and reporting only the numerator is the
    # same missing-evidence problem one level up.
    t1 = _transcript(tmp_path, _run(PYTEST, PASS), _claim("1640 passed"), name="a.jsonl")
    t2 = _transcript(tmp_path, _claim("tests pass"), name="b.jsonl")
    summary = gate.summarize([t1, t2])
    assert summary["transcripts"] == 2
    assert summary["claims"] == 2
    assert summary["findings"] == 1
    assert summary["by_detector"]["claim-no-run"] == 1


# --------------------------------------------------------------- the CLI
def _cli(*args, stdin=""):
    return subprocess.run([sys.executable, str(GATE), *args], input=stdin,
                          capture_output=True, text=True)


def test_the_hook_path_still_works_with_no_argv_and_a_stdin_payload(tmp_path):
    # The regression that adding a CLI invites: argparse eating the hook mode.
    t = _transcript(tmp_path, _claim("tests pass"))
    payload = json.dumps({"last_assistant_message": "all tests pass",
                          "transcript_path": str(t)})
    done = _cli(stdin=payload)
    assert done.returncode == 0
    assert json.loads(done.stdout)["decision"] == "block"


def test_audit_mode_reports_and_never_fails_the_caller(tmp_path):
    t = _transcript(tmp_path, _claim("tests pass"), name="c.jsonl")
    done = _cli("--audit", str(t))
    assert done.returncode == 0                      # a report, not a gate
    assert "claim-no-run" in done.stdout


def test_audit_mode_emits_machine_readable_json_on_request(tmp_path):
    t = _transcript(tmp_path, _claim("tests pass"), name="d.jsonl")
    done = _cli("--audit", str(t), "--json")
    assert done.returncode == 0
    payload = json.loads(done.stdout)
    assert payload["summary"]["claims"] == 1
    assert payload["findings"][0]["detector"] == "claim-no-run"
