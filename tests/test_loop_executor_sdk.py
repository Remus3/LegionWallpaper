"""SdkExecutor (F1 P2) against a fake `claude` shim. NO live API spend.

The shim is a python script injected via cfg["claude_cmd"] as an argv list, so
nothing touches PATH and no .cmd/.ps1 resolution is involved. Each test makes it
emit exactly the result shape being exercised.

The failure cases matter more than the happy path here: this channel runs
unattended with bypassPermissions, so every way a run can end WITHOUT a usable
result has to degrade into a recorded failed cycle rather than a fabricated
success. A made-up sha would defeat the controller's same-sha no-progress guard,
which is the loop's runaway backstop.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "lw_loop_executor_sdk_under_test", ROOT / "ops" / "loop" / "executor.py")
executor = importlib.util.module_from_spec(_spec)
sys.modules["lw_loop_executor_sdk_under_test"] = executor
_spec.loader.exec_module(executor)

OK_STRUCT = {"sha": "abc1234def", "tests_pass": "612", "regressions": False,
             "summary": "did the thing"}


def _shim(tmp_path: Path, *, stdout: str = "", exit_code: int = 0,
          sleep: float = 0.0, echo_argv: bool = True) -> list:
    """A fake `claude` that prints canned stdout and exits with a chosen code."""
    script = tmp_path / "fake_claude.py"
    script.write_text(
        "import sys, time, json, pathlib\n"
        f"time.sleep({sleep})\n"
        + ("pathlib.Path(r'" + str(tmp_path / "argv.json") +
           "').write_text(json.dumps(sys.argv[1:]), encoding='utf-8')\n"
           if echo_argv else "")
        + "sys.stdin.read()\n"
        f"sys.stdout.write({stdout!r})\n"
        f"sys.exit({exit_code})\n",
        encoding="utf-8")
    return [sys.executable, str(script)]


def _cfg(tmp_path: Path, argv: list, **over) -> dict:
    # No cycle_budget_usd by default - see test_no_budget_flag_when_uncapped.
    cfg = {"channel": "sdk", "claude_cmd": argv, "repo_root": str(tmp_path),
           "cycle_deadline_sec": 30, "executor_model": "claude-opus-5"}
    cfg.update(over)
    return cfg


def _build(cfg, tmp_path, logs=None):
    return executor.build(cfg, tmp_path, log=(logs.append if logs is not None
                                              else (lambda *a: None)),
                          stop=lambda m: None, awrite=lambda *a: None,
                          wait_for=lambda *a: True, wait_gone=lambda *a: True,
                          rjson=lambda *a, **k: {}, stall_action=lambda n: "stop",
                          stall_recovery_directive=lambda c: "")


# ---- happy path -----------------------------------------------------------

def test_success_returns_cost_session_and_structured_fields(tmp_path: Path):
    out = json.dumps({"is_error": False, "total_cost_usd": 0.42,
                      "session_id": "sess-1", "structured_output": OK_STRUCT})
    ex = _build(_cfg(tmp_path, _shim(tmp_path, stdout=out)), tmp_path)
    rec = ex.run(1, "body", "fixed")
    assert rec.error is None
    assert rec.sha == "abc1234def"
    assert rec.tests_pass == "612"
    assert rec.regressions is False
    # THE point of this channel: a receipt the AHK path could never return.
    assert rec.cost_usd == 0.42
    assert rec.session_id == "sess-1"


def test_argv_carries_the_flags_the_contract_depends_on(tmp_path: Path):
    out = json.dumps({"structured_output": OK_STRUCT})
    cfg = _cfg(tmp_path, _shim(tmp_path, stdout=out))
    _build(cfg, tmp_path).run(1, "b", "fixed")
    argv = json.loads((tmp_path / "argv.json").read_text(encoding="utf-8"))
    for flag in ("-p", "--output-format", "--json-schema", "--permission-mode",
                 "--add-dir", "--model"):
        assert flag in argv, f"{flag} missing from argv"
    assert argv[argv.index("--output-format") + 1] == "json"
    assert argv[argv.index("--permission-mode") + 1] == "bypassPermissions"
    schema = json.loads(argv[argv.index("--json-schema") + 1])
    assert set(schema["required"]) == {"sha", "tests_pass", "regressions", "summary"}


def test_fresh_session_per_cycle_when_clear_each_cycle(tmp_path: Path):
    """clear_each_cycle True reproduces the AHK channel's /clear semantics."""
    out = json.dumps({"session_id": "s1", "structured_output": OK_STRUCT})
    ex = _build(_cfg(tmp_path, _shim(tmp_path, stdout=out), clear_each_cycle=True),
                tmp_path)
    ex.run(1, "b", "fixed")
    argv = json.loads((tmp_path / "argv.json").read_text(encoding="utf-8"))
    assert "--session-id" in argv and "--resume" not in argv
    ex.run(2, "b", "fixed")
    argv2 = json.loads((tmp_path / "argv.json").read_text(encoding="utf-8"))
    assert "--resume" not in argv2, "a fresh session per cycle, never resumed"


def test_resumes_the_prior_session_when_continuity_is_on(tmp_path: Path):
    out = json.dumps({"session_id": "sess-keep", "structured_output": OK_STRUCT})
    ex = _build(_cfg(tmp_path, _shim(tmp_path, stdout=out), clear_each_cycle=False),
                tmp_path)
    ex.run(1, "b", "fixed")          # first cycle has nothing to resume
    ex.run(2, "b", "fixed")
    argv = json.loads((tmp_path / "argv.json").read_text(encoding="utf-8"))
    assert argv[argv.index("--resume") + 1] == "sess-keep"


def test_prompt_has_no_clear_or_cycle_header(tmp_path: Path):
    """Both are AHK typing artifacts; a -p call is already a fresh process."""
    p = executor.sdk_prompt(4, "the body", "fixed")
    assert "/clear" not in p
    assert not p.startswith("CYCLE=")
    assert "the body" in p
    assert "done_sentinel" in p and "do NOT run" in p


# ---- every way a cycle can fail -------------------------------------------

def test_is_error_true_is_a_failed_cycle_not_a_success(tmp_path: Path):
    out = json.dumps({"is_error": True, "result": "rate limited",
                      "total_cost_usd": 0.1, "session_id": "s"})
    ex = _build(_cfg(tmp_path, _shim(tmp_path, stdout=out)), tmp_path)
    rec = ex.run(1, "b", "fixed")
    assert rec.error and "rate limited" in rec.error
    assert rec.sha == "", "a failed cycle must not carry a sha"
    assert rec.cost_usd == 0.1, "cost is still real and must be accounted"


def test_nonzero_exit_is_a_failed_cycle(tmp_path: Path):
    out = json.dumps({"structured_output": OK_STRUCT})
    ex = _build(_cfg(tmp_path, _shim(tmp_path, stdout=out, exit_code=1)), tmp_path)
    rec = ex.run(1, "b", "fixed")
    assert rec.error, "exit 1 must not read as success even with a valid payload"
    assert rec.sha == ""


def test_malformed_stdout_is_a_failed_cycle(tmp_path: Path):
    ex = _build(_cfg(tmp_path, _shim(tmp_path, stdout="not json at all")), tmp_path)
    rec = ex.run(1, "b", "fixed")
    assert rec.error and "unparseable" in rec.error
    assert rec.sha == ""


def test_missing_structured_output_does_not_fabricate_a_sha(tmp_path: Path):
    """The runaway backstop is the controller's same-sha guard. Inventing a sha
    here would silently disable it."""
    out = json.dumps({"is_error": False, "total_cost_usd": 1.0, "result": "text only"})
    ex = _build(_cfg(tmp_path, _shim(tmp_path, stdout=out)), tmp_path)
    rec = ex.run(1, "b", "fixed")
    assert rec.error and "structured_output" in rec.error
    assert rec.sha == "" and rec.tests_pass == "?"


def test_incomplete_structured_output_is_rejected(tmp_path: Path):
    out = json.dumps({"structured_output": {"sha": "x", "tests_pass": "1"}})
    ex = _build(_cfg(tmp_path, _shim(tmp_path, stdout=out)), tmp_path)
    assert ex.run(1, "b", "fixed").error


def test_no_budget_flag_when_uncapped(tmp_path: Path):
    """Operator 2026-07-26: the cap is OFF by default.

    On a Claude Code Max subscription total_cost_usd is NOTIONAL API-equivalent
    pricing, not what the plan is billed, so --max-budget-usd would truncate real
    work against a number unrelated to spend. RC's gate cycle ran to $22.01 of a
    $25 cap - the next slightly larger scope would have been cut off by an
    accounting artifact.
    """
    out = json.dumps({"structured_output": OK_STRUCT})
    _build(_cfg(tmp_path, _shim(tmp_path, stdout=out)), tmp_path).run(1, "b", "fixed")
    argv = json.loads((tmp_path / "argv.json").read_text(encoding="utf-8"))
    assert "--max-budget-usd" not in argv


def test_budget_flag_is_passed_when_explicitly_set(tmp_path: Path):
    """The capability stays for a METERED api key, where the figure is real."""
    out = json.dumps({"structured_output": OK_STRUCT})
    cfg = _cfg(tmp_path, _shim(tmp_path, stdout=out), cycle_budget_usd=5.0)
    _build(cfg, tmp_path).run(1, "b", "fixed")
    argv = json.loads((tmp_path / "argv.json").read_text(encoding="utf-8"))
    assert argv[argv.index("--max-budget-usd") + 1] == "5.0"


def test_budget_exhaustion_surfaces_as_a_failed_cycle(tmp_path: Path):
    """--max-budget-usd tripping is reported by the CLI as an error result.
    Only reachable when a cap is explicitly set (metered key)."""
    out = json.dumps({"is_error": True, "result": "budget exceeded: max-budget-usd",
                      "total_cost_usd": 25.0})
    ex = _build(_cfg(tmp_path, _shim(tmp_path, stdout=out)), tmp_path)
    rec = ex.run(1, "b", "fixed")
    assert rec.error and "budget" in rec.error
    assert rec.cost_usd == 25.0


def test_timeout_kills_the_tree_and_reports(tmp_path: Path):
    logs: list = []
    out = json.dumps({"structured_output": OK_STRUCT})
    cfg = _cfg(tmp_path, _shim(tmp_path, stdout=out, sleep=10), cycle_deadline_sec=1)
    rec = _build(cfg, tmp_path, logs).run(1, "b", "fixed")
    assert rec.error and "timeout" in rec.error
    assert any("taskkill" in m for m in logs), "must taskkill, never Stop-Process"


# ---- channel selection ----------------------------------------------------

def test_build_returns_the_sdk_channel(tmp_path: Path):
    ex = _build(_cfg(tmp_path, ["x"], channel="sdk"), tmp_path)
    assert ex.name == "sdk"


def test_sdk_channel_holds_no_window_title(tmp_path: Path):
    """The AHK channel keyed on a machine-wide window title - that singleton is
    the whole reason two loops could not run at once."""
    cfg = _cfg(tmp_path, _shim(tmp_path, stdout=json.dumps(
        {"structured_output": OK_STRUCT})), channel="sdk",
        claude_window_title="Image")
    _build(cfg, tmp_path).run(1, "b", "fixed")
    argv = json.loads((tmp_path / "argv.json").read_text(encoding="utf-8"))
    assert not any("Image" in str(a) for a in argv)
