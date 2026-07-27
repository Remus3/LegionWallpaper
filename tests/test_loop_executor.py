"""Executor seam (F1 P1). The AHK channel is a verbatim lift - prove it.

P1 is a refactor only, so these tests pin the things a refactor is most likely
to break silently: the byte-exact typed payload, the stall-recovery sequence,
and the channel selection. Behavior parity at the artifact level was proven
separately by a hermetic 2-cycle dry run diffed before/after
(docs/specs/2026-07-26-f1-sdk-executor-channel.md, P1 acceptance).
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "lw_loop_executor_under_test", ROOT / "ops" / "loop" / "executor.py")
executor = importlib.util.module_from_spec(_spec)
sys.modules["lw_loop_executor_under_test"] = executor
_spec.loader.exec_module(executor)


# ---- directive_payload: byte-exact, because AHK types it ------------------

def test_payload_director_branch_is_byte_exact():
    got = executor.directive_payload(7, "ignored body", "director")
    assert got == (
        "CYCLE=7\n/clear\n"
        "/gemini-headless-upgrade and Read the file ops/loop/control/directive.md "
        "and fully execute it now. No questions; auto-pick the recommended option "
        "and proceed."
    )


def test_payload_fixed_branch_types_the_body_verbatim():
    got = executor.directive_payload(3, "do the thing", "fixed")
    assert got == "CYCLE=3\n/clear\ndo the thing"


def test_payload_cycle_command_branch_matches_fixed():
    assert (executor.directive_payload(1, "/x", "cycle_command")
            == executor.directive_payload(1, "/x", "fixed"))


def test_payload_omits_clear_when_disabled():
    got = executor.directive_payload(2, "body", "fixed", clear_each_cycle=False)
    assert got == "CYCLE=2\nbody"
    assert "/clear" not in got


def test_payload_first_line_is_always_the_cycle_header():
    """Line 1 is the header the AHK bridge SKIPS. If a payload ever loses it,
    the bridge types the real first line into the void."""
    for src in ("director", "fixed", "cycle_command"):
        assert executor.directive_payload(9, "b", src).splitlines()[0] == "CYCLE=9"


# ---- FINAL STEP must match the channel -----------------------------------
# The directive told Claude to end by running done_sentinel.py while the sdk
# prompt appended "do NOT run done_sentinel.py, return JSON". FINAL_STEP is
# appended last so it probably won, but "probably" is not a contract, and with
# sdk now the DEFAULT the next director-authored cycle is the first to exercise
# it. One source of truth, selected by channel.

def test_final_step_for_ahk_is_the_sentinel():
    s = executor.final_step_instruction("ahk")
    assert "done_sentinel.py" in s
    assert "--tests" in s and "--regressions" in s
    assert "do NOT" not in s


def test_final_step_for_sdk_is_the_json_return():
    s = executor.final_step_instruction("sdk")
    assert "do NOT" in s and "done_sentinel" in s
    assert "JSON" in s
    # the ahk sentinel COMMAND must not appear - that is the contradiction
    assert "--tests" not in s


def test_final_step_defaults_to_ahk_when_unset():
    assert executor.final_step_instruction(None) == executor.final_step_instruction("ahk")
    assert executor.final_step_instruction("") == executor.final_step_instruction("ahk")


def test_final_step_rejects_an_unknown_channel():
    with pytest.raises(ValueError):
        executor.final_step_instruction("sdkk")


def test_sdk_prompt_uses_the_same_source_of_truth():
    """If these ever drift, the directive body and the appended instruction
    disagree again - which is the whole defect."""
    assert executor.final_step_instruction("sdk") in executor.sdk_prompt(1, "b", "fixed")


def test_ahk_final_step_names_this_repo_only():
    """The sentinel line is per-repo (interpreter path, exact spacing). RC pins
    the mirror of this. Copying the other repo's string verbatim would break the
    ahk rollback path in a way only a live dry cycle would catch."""
    s = executor.final_step_instruction("ahk")
    assert "Riot Commander" not in s
    assert "ops/loop/done_sentinel.py" in s


def test_sdk_never_consumes_the_stall_recovery_directive():
    """stall_recovery_directive names done_sentinel.py, which is CHANNEL-CORRECT
    rather than a missed spot: it is reachable only from AhkExecutor's
    deadline-breach branch. SdkExecutor has no stall-recovery path at all - it
    times out and taskkills the tree. Flagged by RC; pinned behaviorally here so
    nobody later wires it into the sdk channel and re-introduces the
    contradiction through the back door."""
    def boom(_cycle):
        raise AssertionError("sdk must never inject a stall-recovery directive")

    ex = executor.build({"channel": "sdk", "claude_cmd": ["nonexistent-binary-xyz"]},
                        Path("."), **_deps(stall_recovery_directive=boom))
    assert not hasattr(ex, "stall_recovery_directive"), (
        "SdkExecutor must not even bind the ahk-only dependency")


def test_director_prompt_has_no_hardcoded_final_step():
    """The template must carry the placeholder, not a channel-specific command."""
    tmpl = (ROOT / "ops" / "loop" / "director_prompt.md").read_text(encoding="utf-8")
    assert "{{FINAL_STEP}}" in tmpl, "director_prompt must defer to the executor"
    assert "done_sentinel.py --tests" not in tmpl, (
        "a hardcoded sentinel command contradicts the sdk channel")


def test_directive_suffix_names_no_channel_specific_step():
    """config.json's directive_suffix was LW's SECOND source of the
    contradiction - it also ended every cycle with the sentinel."""
    import json as _json
    cfg = _json.loads((ROOT / "ops" / "loop" / "config.json").read_text(encoding="utf-8"))
    assert "done_sentinel" not in cfg.get("directive_suffix", "")


# ---- build(): channel selection ------------------------------------------

def _deps(**over):
    d = dict(log=lambda *a: None, stop=lambda *a: None, awrite=lambda *a: None,
             wait_for=lambda *a: True, wait_gone=lambda *a: True,
             rjson=lambda *a, **k: {}, stall_action=lambda n: "stop",
             stall_recovery_directive=lambda c: "recover")
    d.update(over)
    return d


def test_build_defaults_to_ahk(tmp_path: Path):
    ex = executor.build({"cycle_deadline_sec": 1}, tmp_path, **_deps())
    assert ex.name == "ahk"


def test_build_rejects_unknown_channel_loudly(tmp_path: Path):
    """A typo must NOT silently fall back to the machine-wide singleton channel
    during a concurrent run - that is the exact failure this seam prevents."""
    with pytest.raises(ValueError, match="unknown executor channel"):
        executor.build({"channel": "sdkk"}, tmp_path, **_deps())


def test_build_returns_sdk_channel_since_p2(tmp_path: Path):
    """Was 'rejects sdk until P2'. P2 shipped it - see test_loop_executor_sdk.py."""
    assert executor.build({"channel": "sdk"}, tmp_path, **_deps()).name == "sdk"


# ---- gate preflight: the fresh-clone gap ----------------------------------
# core.hooksPath is LOCAL config and is NOT cloned, so a tracked .githooks dir
# buys nothing on a fresh clone until someone sets it. Verified empirically:
# a clone of this repo reports core.hooksPath unset and the gate INERT.

def test_gate_reason_is_none_in_this_repo():
    """LW itself has the gate active - the loop must not refuse to start here."""
    assert executor.gate_inactive_reason(ROOT) is None


def test_gate_reason_reports_a_repo_with_no_hookspath(tmp_path: Path):
    import subprocess
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", str(ROOT), str(clone)],
                   capture_output=True, text=True)
    if not (clone / ".git").exists():
        pytest.skip("clone unavailable in this environment")
    reason = executor.gate_inactive_reason(clone)
    assert reason, "a fresh clone has no hooks and must be reported, not assumed fine"
    assert "hooksPath" in reason


def test_gate_reason_stays_silent_when_the_repo_has_no_installer(tmp_path: Path):
    """Do not invent a blocker for a tree that never had this tooling."""
    assert executor.gate_inactive_reason(tmp_path) is None


# ---- AhkExecutor.run ------------------------------------------------------

class _Ctl:
    """Records the handshake without touching disk."""

    def __init__(self):
        self.writes: list[tuple[str, str]] = []
        self.logs: list[str] = []
        self.stops: list[str] = []


def _wire(ctl_rec, tmp_path, *, wait_for_results, done_payload, stall="stop"):
    calls = {"wait_for": 0}

    def wait_for(_path, _deadline):
        i = calls["wait_for"]
        calls["wait_for"] += 1
        return wait_for_results[min(i, len(wait_for_results) - 1)]

    return executor.build(
        {"cycle_deadline_sec": 5}, tmp_path,
        **_deps(
            log=ctl_rec.logs.append,
            stop=lambda m: (ctl_rec.stops.append(m), (_ for _ in ()).throw(SystemExit(1))),
            awrite=lambda p, t: ctl_rec.writes.append((Path(p).name, t)),
            wait_for=wait_for,
            rjson=lambda *a, **k: done_payload,
            stall_action=lambda n: stall,
        )), calls


def test_run_happy_path_returns_a_done_record(tmp_path: Path):
    rec_ctl = _Ctl()
    (tmp_path / "claude.done").write_text("{}", encoding="utf-8")
    ex, _ = _wire(rec_ctl, tmp_path, wait_for_results=[True],
                  done_payload={"sha": "abc1234", "tests_pass": "42",
                                "regressions": False})
    out = ex.run(5, "body", "fixed")
    assert out.sha == "abc1234"
    assert out.tests_pass == "42"
    assert out.regressions is False
    assert out.raw == {"sha": "abc1234", "tests_pass": "42", "regressions": False}
    # AHK returns no receipt - that is why the controller still scrapes cost.
    assert out.cost_usd == 0.0 and out.session_id is None


def test_run_writes_the_payload_to_gemini_ready(tmp_path: Path):
    rec_ctl = _Ctl()
    (tmp_path / "claude.done").write_text("{}", encoding="utf-8")
    ex, _ = _wire(rec_ctl, tmp_path, wait_for_results=[True], done_payload={})
    ex.run(4, "the body", "fixed")
    assert rec_ctl.writes[0][0] == "gemini.ready"
    assert rec_ctl.writes[0][1] == "CYCLE=4\n/clear\nthe body"


def test_run_carries_raw_payload_through_untouched(tmp_path: Path):
    """The director prompt is built from this dict; reshaping it would change
    directive text and make the refactor a behavior change."""
    rec_ctl = _Ctl()
    (tmp_path / "claude.done").write_text("{}", encoding="utf-8")
    payload = {"sha": "d", "tests_pass": "1", "regressions": True, "extra": [1, 2]}
    ex, _ = _wire(rec_ctl, tmp_path, wait_for_results=[True], done_payload=payload)
    assert ex.run(1, "b", "fixed").raw is payload


def test_run_injects_stall_recovery_on_first_breach(tmp_path: Path):
    """First deadline breach earns ONE recovery, not a hard stop."""
    rec_ctl = _Ctl()
    (tmp_path / "claude.done").write_text("{}", encoding="utf-8")
    ex, calls = _wire(rec_ctl, tmp_path, wait_for_results=[False, True],
                      done_payload={"sha": "z"}, stall="recover")
    out = ex.run(2, "b", "fixed")
    assert out.sha == "z"
    assert [w[0] for w in rec_ctl.writes] == ["gemini.ready", "gemini.ready"]
    assert rec_ctl.writes[1][1] == "recover"
    assert not rec_ctl.stops
    assert any("deadline breach 1" in m for m in rec_ctl.logs)


def test_run_hard_stops_when_stall_action_says_stop(tmp_path: Path):
    rec_ctl = _Ctl()
    ex, _ = _wire(rec_ctl, tmp_path, wait_for_results=[False], done_payload={},
                  stall="stop")
    with pytest.raises(SystemExit):
        ex.run(3, "b", "fixed")
    assert "hard hang" in rec_ctl.stops[0]


def test_run_stops_when_the_bridge_never_types(tmp_path: Path):
    rec_ctl = _Ctl()
    ex = executor.build(
        {"cycle_deadline_sec": 5}, tmp_path,
        **_deps(log=rec_ctl.logs.append,
                stop=lambda m: (rec_ctl.stops.append(m),
                                (_ for _ in ()).throw(SystemExit(1))),
                awrite=lambda p, t: None,
                wait_gone=lambda *a: False))
    with pytest.raises(SystemExit):
        ex.run(1, "b", "fixed")
    assert "never typed" in rec_ctl.stops[0]
