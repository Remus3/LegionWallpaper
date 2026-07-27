"""wakeup_prune must actually see this repo's session blocks.

SESSION_RE was `^# ` only - carried from the ancestor repo, where session
headings were `# sNN wrap`. Every LW block is an H2 (`## 2026-07-27 - topic`),
so the pattern matched nothing, prune fell back to counting `---` separators,
and a 42.5KB WAKEUP_NOTES.md holding 20 session blocks reported

    wakeup_prune: 3 session(s) <= keep=3; nothing to do

and exited 0 on every /done since the tool was adopted. The ritual ran, the tool
ran, and the file grew unbounded - and headless spawn cost scales with it,
because `claude --print` cold-loads the file on every cycle.

The bug is not the regex. It is that the tool's silence was indistinguishable
from success, which is the sixth instance of that shape found in this repo on
2026-07-27.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load():
    spec = importlib.util.spec_from_file_location(
        "lw_wakeup_prune_under_test", ROOT / "scripts" / "wakeup_prune.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


wp = _load()

H2 = "## 2026-07-27 - a session block\n\nbody\n"
H1 = "# 2026-07-26 - an older-style block\n\nbody\n"
WRAP = "# s41 wrap\n\nbody\n"


def test_an_h2_dated_heading_is_recognised_as_a_session():
    """The live format. This is what was silently invisible."""
    assert wp.SESSION_RE.search(H2) is not None


def test_the_ancestor_h1_formats_still_match():
    """Widening must not drop what already worked - the archive holds both."""
    assert wp.SESSION_RE.search(H1) is not None
    assert wp.SESSION_RE.search(WRAP) is not None


def test_a_plain_h2_that_is_not_a_session_is_not_matched():
    """Section headings inside a session block must not split it."""
    assert wp.SESSION_RE.search("## STANDING REFERENCE - machine state\n") is None
    assert wp.SESSION_RE.search("### 2026-07-27 sub-heading\n") is None


def test_the_parser_sees_every_heading_in_the_real_file():
    """Ground truth, not a fixture - but asserting the INVARIANT, not the count.

    The first cut asserted the live file holds >= 4 sessions, and then went red
    the moment prune did its job and left 3. A test coupled to a mutable state
    the tool exists to CHANGE reports success as a failure. The invariant is
    that the parser sees whatever headings are actually there, at any count.
    """
    text = (ROOT / "WAKEUP_NOTES.md").read_text(encoding="utf-8")
    _, sessions = wp.split_sessions(text)
    heads = sum(1 for ln in text.splitlines() if wp.SESSION_RE.match(ln + "\n"))
    assert heads > 0, "no session heading matched the live file at all"
    assert len(sessions) == heads, (
        f"split_sessions found {len(sessions)} blocks for {heads} headings - "
        f"the parser is not seeing this file's real structure, which is exactly "
        f"the silent no-op this guard exists for")
