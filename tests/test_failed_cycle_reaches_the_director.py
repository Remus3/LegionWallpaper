"""A failed cycle must tell the next director call that it failed.

`loop_controller` does `done = rec.raw` and feeds exactly that forward as
`=== LAST claude.done ===`. All four sdk failure paths left `raw` at its default
{}, so a cycle that timed out, errored, or produced no structured output handed
the director the literal string `{}` - while the executor's own error string
stayed in the module. The cycle a director most needs to know about is the one
that failed, and that was the single branch it could not see.

Found by RC hitting the identical hole in its own reporting seam on 2026-07-27
and flagging it across; LW's version is independent of RC's `_REPORT_IT` ask,
which LW does not carry at all (LW has no disjointness/grounding guards - item 7
was RC-owned).

The failure payload is deliberately NOT success-shaped. Inventing a sha would
defeat the controller's same-sha no-progress guard; inventing tests_pass would
report a result nobody measured.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load():
    spec = importlib.util.spec_from_file_location(
        "lw_executor_failraw_under_test", ROOT / "ops" / "loop" / "executor.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


ex = _load()


def test_a_failure_payload_is_not_empty():
    raw = ex.failure_raw(7, "timeout after 5400s", "sid-abc")
    assert raw, "an empty dict tells the director nothing"
    assert raw["cycle"] == 7
    assert "timeout" in raw["error"]
    assert raw["session_id"] == "sid-abc"


def test_a_failure_payload_carries_no_fabricated_result():
    """A sha here would be read as progress by the controller's same-sha guard."""
    raw = ex.failure_raw(1, "exit 1", None)
    for forbidden in ("sha", "tests_pass", "regressions"):
        assert forbidden not in raw, (
            f"{forbidden!r} in a failure payload invents a result nobody measured")


def test_a_missing_session_id_is_omitted_not_nulled():
    raw = ex.failure_raw(1, "exit 1", None)
    assert "session_id" not in raw


@pytest.mark.parametrize("site", [
    'raw=failure_raw(cycle, err, self.session_in_play))',
    'raw=failure_raw(cycle, err, sid))',
])
def test_the_failure_paths_actually_use_it(site):
    """Item 10: the fix is only real if EVERY instance carries it. Four sdk
    failure paths exist - timeout, unparseable stdout, is_error/returncode, and
    missing structured_output."""
    src = (ROOT / "ops" / "loop" / "executor.py").read_text(encoding="utf-8")
    assert site in src


def test_every_sdk_failure_return_carries_a_raw():
    """Counts rather than spot-checks, so a fifth failure path added later
    cannot quietly ship without one."""
    src = (ROOT / "ops" / "loop" / "executor.py").read_text(encoding="utf-8")
    sdk = src[src.index("class SdkExecutor"):]
    error_returns = sdk.count("error=err")
    with_raw = sdk.count("raw=failure_raw(")
    assert error_returns == with_raw == 4, (
        f"{error_returns} error returns but {with_raw} carry a raw payload - "
        f"a failure path without one is invisible to the director")


def test_the_clean_payload_shape_is_unchanged():
    """The seam must not gain a key on SUCCESS. RC's version of this fix wrote
    the stamp back unconditionally and added `"summary": ""` to every clean
    cycle - a shape change to the director's context rather than a record of
    anything. The success path still returns the structured_output as-is.
    """
    src = (ROOT / "ops" / "loop" / "executor.py").read_text(encoding="utf-8")
    sdk = src[src.index("class SdkExecutor"):]
    tail = sdk[sdk.rindex("return DoneRecord("):]
    assert "raw=dict(so)" in tail, (
        "the success path must hand through structured_output untouched - it "
        "copies rather than aliases, which is the shape verified on disk rather "
        "than the one I first assumed")
    assert "failure_raw" not in tail, "a clean cycle must not carry a failure payload"
