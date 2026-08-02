"""Workflow-parity guard: every CI job that runs the suite must arm the gate.

The nightly `nightly-full-suite` job went RED two nights running (runs
30351782593 + 30444928280, both event=schedule) on
test_loop_executor.py::test_gate_reason_is_none_in_this_repo. The test was
right and CI was wrong: core.hooksPath is LOCAL git config and is never
cloned, so a fresh checkout has the tracked .githooks gate INERT until
tools/install_git_hooks.py runs. The `check` job already armed it; the
nightly was never given the same step.

Arming one job by hand does not stop a THIRD job from being added without it,
which is why the fix ships as this parity guard rather than as two hand-edited
jobs. Any future job that gains `pytest tests/` fails here until it also arms.

Parsed with the stdlib only, on purpose: requirements.txt is pytest / ruff /
numpy / Pillow, and PyYAML is not a dependency. Adding one to CI just to read
CI would be a bigger surface than the indentation walk below.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"

# The suite invocation and the arming command, matched on the substrings that
# actually carry the meaning - not on whole lines, which carry flags that are
# free to change (-q, --tb=short vs --tb=line) without changing the contract.
SUITE = "pytest tests/"
ARMER = "tools/install_git_hooks.py"

_JOB = re.compile(r"^  ([A-Za-z0-9_-]+):\s*$")


def _jobs() -> dict[str, list[str]]:
    """job name -> its body lines, by indentation walk.

    Top-level keys sit at column 0, job names at 2 spaces under `jobs:`, so a
    job body runs until the next 2-space key or the next column-0 key.
    """
    lines = WORKFLOW.read_text(encoding="utf-8").splitlines()
    out: dict[str, list[str]] = {}
    current: str | None = None
    in_jobs = False
    for line in lines:
        if line.startswith("jobs:"):
            in_jobs = True
            continue
        if not in_jobs:
            continue
        if line and not line.startswith(" "):  # dedent to a new top-level key
            break
        m = _JOB.match(line)
        if m:
            current = m.group(1)
            out[current] = []
            continue
        if current is not None:
            out[current].append(line)
    return out


def test_the_workflow_parses_into_the_jobs_we_know_about():
    """Guard the guard: an indentation walk that silently found zero jobs would
    make every assertion below vacuously true."""
    jobs = _jobs()
    assert set(jobs) == {"nightly-full-suite", "check", "cv-lane"}, (
        f"unexpected job set {sorted(jobs)} - if a job was added or renamed, "
        "confirm the arming assertions below still cover it")
    assert all(body for body in jobs.values()), "a job parsed with an empty body"


def test_every_job_running_the_suite_arms_the_git_hook_gate():
    """The regression itself. A job that runs the suite without arming the gate
    fails test_gate_reason_is_none_in_this_repo on a fresh CI checkout."""
    offenders = []
    for name, body in _jobs().items():
        text = "\n".join(body)
        if SUITE in text and ARMER not in text:
            offenders.append(name)
    assert not offenders, (
        f"CI job(s) {offenders} run `{SUITE}` without running `{ARMER}` first. "
        "core.hooksPath is local config and is never cloned, so the tracked "
        ".githooks gate is INERT on a fresh checkout and the gate-active test "
        "correctly fails. Add the arming step to the job.")


def test_the_arming_step_runs_before_the_suite_in_every_such_job():
    """Order matters: arming AFTER pytest leaves the failing test failing."""
    for name, body in _jobs().items():
        text = "\n".join(body)
        if SUITE not in text:
            continue
        assert text.index(ARMER) < text.index(SUITE), (
            f"job {name} runs `{ARMER}` after `{SUITE}` - the gate must be "
            "armed before the suite observes it")
    # All three jobs are expected to have a suite step (cv-lane runs a single
    # file, which still matches the SUITE substring - deliberately, so a
    # narrow-scope job cannot dodge the arming contract). If that ever stops
    # being true the loop above would silently assert nothing.
    assert sum(SUITE in "\n".join(b) for b in _jobs().values()) == 3


def test_the_arming_step_also_verifies_with_check():
    """Installing without --check is how the 2026-07-26 false green happened -
    a hook present but not firing. --check is the authoritative probe."""
    for name, body in _jobs().items():
        text = "\n".join(body)
        if SUITE not in text:
            continue
        assert f"{ARMER} --check" in text, (
            f"job {name} installs the hooks but never runs "
            f"`{ARMER} --check` to prove they fire")
