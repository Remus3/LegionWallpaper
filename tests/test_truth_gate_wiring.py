"""Wiring truth_gate.py into the run flow.

Instrumentation backlog item 7 of `docs/RUNDASH_SPEC_2026-08-01.md`: "truth_gate
is never invoked by the run flow - its report has never been written on this
machine. The atomic writer already exists; only the call is missing."

Verified before writing any of this: `tools/truth_gate.py` has a `main`, an
atomic `write_report_atomic`, and a `reconcile` that returns PROCEED/REFUSE -
and NOTHING under `ops/` referenced it. `slice_orchestrator.OBSERVERS` already
listed `truth_gate` as a legal observer, so the verdict slot was reserved for a
caller that never existed.

Two design points worth stating because they are not obvious:

  1. The suite-count claim is attached to a SYNTHETIC cycle-level slice, not
     smeared across every real slice. `DoneRecord.tests_pass` is a run-level
     claim; hanging it on each slice would quarantine all of them for one wrong
     number and bury which claim actually failed.
  2. The gate is ADVISORY by default. It always runs and always writes its
     report; whether a REFUSE stops the loop is `truth_gate_blocking` in
     ops/loop/config.json, default False. Landing a new control-flow branch as
     blocking on a loop that is not currently running would be shipping an
     unmeasured change to the one thing that must not wedge.

Loading note: importing loop_controller RUNS a controller, so the functions are
extracted from source the same way tests/test_director_prompt_budget.py does it.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTROLLER = ROOT / "ops" / "loop" / "loop_controller.py"
sys.path.insert(0, str(ROOT / "tools"))


def _load():
    """Extract the truth-gate bridge with a stub namespace."""
    import re as _re
    import subprocess as _sp

    src = CONTROLLER.read_text(encoding="utf-8")
    start = src.index("def parse_claimed_count(")
    end = src.index("\ndef record_directive_outcome(", start)
    ns = {"json": json, "Path": Path, "subprocess": _sp, "ROOT": ROOT,
          "re": _re, "sys": sys, "NO_WINDOW": 0, "log": lambda *a, **k: None}
    exec(compile(src[start:end], "tg", "exec"), ns)  # noqa: S102 - own source
    return ns


NS = _load()


# ---------------------------------------------------------------------------
# claimed-count parsing - tests_pass is free text from the executor
# ---------------------------------------------------------------------------
def test_a_plain_count_parses():
    assert NS["parse_claimed_count"]("1441") == 1441


def test_a_count_inside_a_summary_line_parses():
    assert NS["parse_claimed_count"]("1441 passed, 16 skipped") == 1441


def test_the_unknown_marker_is_not_a_claim():
    """'?' is the DoneRecord default. Turning it into 0 would invent a claim
    the executor never made, and then quarantine the cycle for failing it."""
    for junk in ("?", "", None, "unknown", []):
        assert NS["parse_claimed_count"](junk) is None


# ---------------------------------------------------------------------------
# claims construction
# ---------------------------------------------------------------------------
def _manifest():
    return {"run_id": "2026-08-01-01", "slices": [
        {"id": "S1", "title": "a slice", "files": ["tools/a.py", "tests/test_a.py"]},
        {"id": "S2", "title": "another", "files": ["tools/b.py"]},
    ]}


def test_every_manifest_slice_becomes_a_file_claim():
    c = NS["build_truth_gate_claims"]("run7", 3, {"tests_pass": "1441"}, _manifest())
    by_id = {s["id"]: s for s in c["slices"]}
    assert [f["path"] for f in by_id["S1"]["files"]] == ["tools/a.py", "tests/test_a.py"]
    assert [f["path"] for f in by_id["S2"]["files"]] == ["tools/b.py"]


def test_the_count_claim_is_isolated_on_a_synthetic_cycle_slice():
    """Point 1 in the module docstring - do not smear one number over N slices."""
    c = NS["build_truth_gate_claims"]("run7", 3, {"tests_pass": "1441"}, _manifest())
    by_id = {s["id"]: s for s in c["slices"]}
    assert by_id["cycle-3"]["claimed_passed"] == 1441
    for sid in ("S1", "S2"):
        assert "claimed_passed" not in by_id[sid]


def test_no_count_claim_when_the_executor_claimed_nothing():
    c = NS["build_truth_gate_claims"]("run7", 3, {"tests_pass": "?"}, _manifest())
    assert not [s for s in c["slices"] if s["id"] == "cycle-3"]


def test_a_missing_manifest_still_yields_a_usable_claims_doc():
    """The gate must run on a cycle that dispatched no slices at all."""
    c = NS["build_truth_gate_claims"]("run7", 1, {"tests_pass": "1441"}, None)
    assert c["run_id"] == "run7"
    assert [s["id"] for s in c["slices"]] == ["cycle-1"]


def test_files_are_never_asserted_to_contain_anything():
    """must_contain would need the diff. Claiming content we cannot source is
    how a gate starts REFUSING on its own invention."""
    c = NS["build_truth_gate_claims"]("run7", 3, {"tests_pass": "1"}, _manifest())
    for sl in c["slices"]:
        for f in sl.get("files", []):
            assert f.get("must_contain", []) == []


# ---------------------------------------------------------------------------
# invocation - injectable runner, never a real 70s suite in the suite
# ---------------------------------------------------------------------------
def _runner(rc, payload=None):
    calls = []

    def run(argv, **kw):
        calls.append((argv, kw))

        class R:
            returncode = rc
            stdout = json.dumps(payload or {"verdict": "PROCEED"})
            stderr = ""
        return R()

    run.calls = calls
    return run


def test_a_proceed_verdict_is_reported_and_the_report_path_is_passed(tmp_path):
    rep = tmp_path / "truth_gate_report.json"
    rep.write_text(json.dumps({"verdict": "PROCEED", "quarantined": []}),
                   encoding="utf-8")
    run = _runner(0)
    verdict, report = NS["run_truth_gate"](
        {"run_id": "r", "slices": []}, claims_path=tmp_path / "claims.json",
        report_path=rep, runner=run)
    assert verdict == "PROCEED"
    assert report["verdict"] == "PROCEED"
    argv = run.calls[0][0]
    assert "--report" in argv and str(rep) in argv
    assert (tmp_path / "claims.json").exists(), "claims were never written"


def test_a_refuse_verdict_survives_the_nonzero_exit(tmp_path):
    """truth_gate exits 2 on REFUSE. A subprocess wrapper that treats nonzero as
    'the tool broke' would silently downgrade a real refusal."""
    rep = tmp_path / "r.json"
    rep.write_text(json.dumps({"verdict": "REFUSE", "quarantined": ["S1"]}),
                   encoding="utf-8")
    verdict, report = NS["run_truth_gate"](
        {"run_id": "r", "slices": []}, claims_path=tmp_path / "c.json",
        report_path=rep, runner=_runner(2))
    assert verdict == "REFUSE"
    assert report["quarantined"] == ["S1"]


def test_the_gate_crashing_is_ERROR_and_never_a_silent_proceed(tmp_path):
    """Fail-CLOSED on the verdict, fail-OPEN on the loop: an unreadable report
    must not read as permission, but it must not wedge the run either."""
    verdict, report = NS["run_truth_gate"](
        {"run_id": "r", "slices": []}, claims_path=tmp_path / "c.json",
        report_path=tmp_path / "never_written.json", runner=_runner(1))
    assert verdict == "ERROR"
    assert report.get("verdict") == "ERROR"


def test_skip_suite_is_passed_through_when_asked(tmp_path):
    rep = tmp_path / "r.json"
    rep.write_text(json.dumps({"verdict": "PROCEED"}), encoding="utf-8")
    run = _runner(0)
    NS["run_truth_gate"]({"run_id": "r", "slices": []},
                         claims_path=tmp_path / "c.json", report_path=rep,
                         runner=run, skip_suite=True)
    assert "--skip-suite" in run.calls[0][0]


def test_the_subprocess_never_flashes_a_console(tmp_path):
    """Legion focus-steal rule - the controller runs under pythonw."""
    rep = tmp_path / "r.json"
    rep.write_text(json.dumps({"verdict": "PROCEED"}), encoding="utf-8")
    run = _runner(0)
    NS["run_truth_gate"]({"run_id": "r", "slices": []},
                         claims_path=tmp_path / "c.json", report_path=rep,
                         runner=run)
    assert "creationflags" in run.calls[0][1]


# ---------------------------------------------------------------------------
# the controller actually calls it, and blocking is opt-in
# ---------------------------------------------------------------------------
def test_the_run_flow_invokes_the_gate():
    """The whole point of item 7. A bridge nothing calls is the previous bug."""
    src = CONTROLLER.read_text(encoding="utf-8")
    body = src[src.index("with slots.hold("):]
    assert "run_truth_gate(" in body, "the gate is defined but never called"


def test_blocking_is_opt_in_and_defaults_to_advisory():
    src = CONTROLLER.read_text(encoding="utf-8")
    assert 'CFG.get("truth_gate_blocking", False)' in src
    cfg = json.loads((ROOT / "ops" / "loop" / "config.json").read_text(encoding="utf-8-sig"))
    assert cfg.get("truth_gate_blocking", False) is False


# ---------------------------------------------------------------------------
# the gate's own suite command - found by RUNNING it, which nothing ever had
# ---------------------------------------------------------------------------
def test_the_gate_runs_the_same_suite_ci_runs():
    """First real invocation returned 0 passed / 2 errors on a green tree.

    DEFAULT_SUITE_CMD was a bare `-m pytest -q` with no path, so pytest
    collected from the repo root and swept in files the project suite never
    runs: tools/test_lw_clean_dekel.py (needs skimage, which lives only in the
    lw-clean venv) and a vendored MCP extension's conftest under Claude/.
    Collection died, counts came back zeroed, and EVERY count claim quarantined.
    A gate that manufactures a REFUSE is worse than no gate at all.
    CI runs `pytest tests/ -q`; so must this.
    """
    import truth_gate

    assert " tests/" in truth_gate.DEFAULT_SUITE_CMD, (
        f"suite cmd sweeps the whole tree: {truth_gate.DEFAULT_SUITE_CMD}")
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "pytest tests/ -q" in ci, "CI moved - re-pin the gate to match it"


def test_the_documented_example_suite_cmd_matches_the_default():
    """The docstring is the copy-paste source for a hand-written claims file."""
    import truth_gate

    assert "-m pytest tests/ -q" in truth_gate.__doc__
