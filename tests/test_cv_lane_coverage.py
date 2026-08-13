"""Guard: the cv-lane is the ONLY lane that can run tools/test_lw_clean_dekel.py.

That file imports cv2 + skimage at module scope and sits in tools/ beside the
module it exercises (it imports `lw_clean_dekel` directly). pytest.ini pins
testpaths=tests, so no default collection reaches it, and before 2026-08-12 no
CI lane named it either - 8 tests of pure-math coverage on the Dekel solver ran
literally nowhere, while a bare `pytest` at the repo root only ever reached the
file to die on the missing import.

The floor assertion below is the half that matters: the lane's own false-green
guard demands a minimum executed-test count, and if that floor is not raised
when a file is added, the file can silently stop being collected and the lane
stays green on the other suite alone.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
TOOLS_SUITE = "tools/test_lw_clean_dekel.py"


def _workflow() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_the_cv_lane_runs_the_tools_dekel_suite():
    ci = _workflow()
    assert TOOLS_SUITE in ci, (
        f"{TOOLS_SUITE} is named by no CI lane. It is outside testpaths and "
        "needs the CV stack, so the cv-lane is the only place it can run - "
        "without that line it is dead coverage.")


def test_the_tools_dekel_suite_is_run_by_pytest_not_merely_mentioned():
    """A path inside a comment is not a test run."""
    for line in _workflow().splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if TOOLS_SUITE in stripped and "pytest" in stripped:
            return
    raise AssertionError(
        f"{TOOLS_SUITE} appears in ci.yml but not on a pytest invocation line")


def test_the_false_green_floor_covers_both_dekel_suites():
    """tests/test_lw_clean_dekel_align.py = 10 tests, tools/ file = 8, so a
    floor below 18 lets one of them vanish from collection unnoticed."""
    m = re.search(r"if total - skipped < (\d+):", _workflow())
    assert m, "the cv-lane false-green floor is gone - that guard is the lane"
    assert int(m.group(1)) >= 18, (
        f"floor is {m.group(1)}, but the two dekel suites contribute 18 tests. "
        "A floor below the real count means a suite can stop being collected "
        "while the lane stays green.")
