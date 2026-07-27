"""The director prompt's stdin cap must not silently eat its de-dup evidence.

RC hit this live on 2026-07-27: its assembled director prompt ran 62,823 chars
against a 60,000 ceiling, the blind middle cut fired, and the bytes it discarded
were exactly the ALREADY-COMPLETED DIGEST header and the RECENT COMMITS block -
the de-dup evidence. The director then re-emitted the same drained directive
three cycles running. That presents as a model ignoring instructions, not as a
truncation bug, which is why it survived three cycles.

LW is NOT currently affected - the live prompt measured 38,336 of 60,000 with
every section intact. But LW carries the identical cap_stdin, and LW's
ALREADY-COMPLETED DIGEST sits in the MIDDLE of the prompt, which is precisely
the region cap_stdin sacrifices. So the exposure is latent, not absent, and it
grows every time LEDGER or the suffix grows. These tests make it loud before it
bites rather than after.
"""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CONTROLLER = ROOT / "ops" / "loop" / "loop_controller.py"
LIVE_PROMPT = ROOT / "ops" / "loop" / "control" / "_gemini_in.txt"
DEDUP_MARKERS = ("ALREADY-COMPLETED DIGEST", "ROADMAP.md")


def _cap_stdin():
    """Load just the function under test - importing the module runs a controller."""
    src = CONTROLLER.read_text(encoding="utf-8")
    start = src.index("def cap_stdin(")
    end = src.index("\ndef ", start + 1)
    ns = {"GEMINI_STDIN_CAP": 60_000}
    exec(compile(src[start:end], "cap_stdin", "exec"), ns)  # noqa: S102 - own source
    return ns["cap_stdin"]


cap_stdin = _cap_stdin()


def test_cap_stdin_is_a_no_op_below_the_limit():
    body = "x" * 100
    assert cap_stdin(body, limit=1000) == body


def test_cap_stdin_preserves_head_and_tail():
    body = "HEAD" + ("x" * 5000) + "TAIL"
    out = cap_stdin(body, limit=500)
    assert out.startswith("HEAD")
    assert out.endswith("TAIL")
    assert len(out) <= 500


def test_the_middle_is_what_gets_sacrificed():
    """Characterization, and the reason the next test exists. A section in the
    middle is NOT protected - this is the RC failure verbatim."""
    body = "HEAD" + ("x" * 3000) + "ALREADY-COMPLETED DIGEST" + ("y" * 3000) + "TAIL"
    out = cap_stdin(body, limit=1000)
    assert "ALREADY-COMPLETED DIGEST" not in out, (
        "if this passes, cap_stdin gained middle protection and the headroom "
        "guard below can be relaxed - check before relaxing it")
    assert "STDIN CAP" in out, "a cut must announce itself"


def test_directive_suffix_is_emitted_under_its_own_section_header():
    """Unlabelled static prose glued to a live section gets read as part of it.
    RC's director quoted a months-old suffix back as the current work order."""
    src = CONTROLLER.read_text(encoding="utf-8")
    i = src.index('CFG.get("directive_suffix"')
    window = src[max(0, i - 600):i + 400]
    assert "OPERATOR STANDING ORDERS" in window, (
        "the suffix must carry its own === header identifying it as STATIC")
    assert "outranks" in window, (
        "the header must say the live sections outrank the static text")


@pytest.mark.skipif(not LIVE_PROMPT.is_file(),
                    reason="no director prompt artifact on this machine (CI)")
def test_live_director_prompt_keeps_headroom_under_the_cap():
    """Fails at 90 percent, not at 100. At 100 the damage is already done and
    silent; the whole point is to be told while there is still room to act."""
    size = LIVE_PROMPT.stat().st_size
    assert size < 54_000, (
        f"director prompt is {size} bytes of the 60,000 cap. Past the cap the "
        f"blind middle cut fires and takes the ALREADY-COMPLETED DIGEST with "
        f"it, so the director re-issues drained work and looks like it is "
        f"ignoring instructions. Trim a component cap before that happens.")


@pytest.mark.skipif(not LIVE_PROMPT.is_file(),
                    reason="no director prompt artifact on this machine (CI)")
@pytest.mark.parametrize("marker", DEDUP_MARKERS)
def test_live_director_prompt_still_carries_its_dedup_evidence(marker):
    text = LIVE_PROMPT.read_text(encoding="utf-8", errors="replace")
    assert "STDIN CAP" not in text, "the cut already fired on the last real prompt"
    assert marker in text, f"{marker} missing from the assembled director prompt"
