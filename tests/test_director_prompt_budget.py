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


def _live_director_text():
    """The live prompt artifact, but ONLY when it is a DIRECTOR prompt.

    `_gemini_in.txt` is reused by BOTH gemini calls - director and auditor - so
    whichever ran last owns it. These tests assumed director unconditionally and
    passed for hours purely because the loop happened to be stopped after a
    director call; the moment a run ended on an audit they went red with nothing
    wrong. Same class as everything else this session: a check reading an
    artifact it had never been exercised against.
    """
    if not LIVE_PROMPT.is_file():
        pytest.skip("no gemini prompt artifact on this machine (CI)")
    text = LIVE_PROMPT.read_text(encoding="utf-8", errors="replace")
    if "You are the AUDITOR" in text or "=== ROADMAP.md" not in text:
        pytest.skip("last gemini call was the AUDITOR - not a director prompt")
    return text


def test_live_director_prompt_keeps_headroom_under_the_cap():
    """Fails at 90 percent, not at 100. At 100 the damage is already done and
    silent; the whole point is to be told while there is still room to act."""
    _live_director_text()
    size = LIVE_PROMPT.stat().st_size
    assert size < 54_000, (
        f"director prompt is {size} bytes of the 60,000 cap. Past the cap the "
        f"blind middle cut fires and takes the ALREADY-COMPLETED DIGEST with "
        f"it, so the director re-issues drained work and looks like it is "
        f"ignoring instructions. Trim a component cap before that happens.")


@pytest.mark.parametrize("marker", DEDUP_MARKERS)
def test_live_director_prompt_still_carries_its_dedup_evidence(marker):
    text = _live_director_text()
    assert "STDIN CAP" not in text, "the cut already fired on the last real prompt"
    assert marker in text, f"{marker} missing from the assembled director prompt"


# ---- the config the controller loads when nobody passes one -----------------

def test_the_no_argv_config_fallback_is_module_relative():
    r"""A hardcoded C:\LegionWallpaper path resolves on exactly one machine.

    Everywhere else the read throws and the module runs with CFG = {}, so every
    import-time consumer of CFG tests a configuration that never runs in
    production - silently, and only in the environment nobody watches. The old
    comment justified that branch with "a clean checkout has no config.json",
    which is false: all four ops/loop/config*.json are tracked. RC hit the same
    thing at 261aeb30 and its CI had been running configless.
    """
    src = CONTROLLER.read_text(encoding="utf-8")
    i = src.index("_CFG_ARG = (")
    window = src[i:i + 400]
    assert "Path(__file__).resolve().parent" in window, (
        "the no-argv config fallback must resolve module-relative")
    assert r"C:\LegionWallpaper" not in window, (
        "a machine-specific absolute path here means CI loads no config at all")


def test_the_tracked_config_is_where_that_fallback_points():
    """The fallback is only useful if it names a file the repo actually ships."""
    assert (ROOT / "ops" / "loop" / "config.json").is_file()


# ---- the hardcoded-path CLASS, not the one line ----------------------------
#
# f1 item 10: enumerate every instance of a defect class IN THE FILE before
# committing the fix, then across the codebase. The no-argv config fallback was
# fixed one commit before this guard existed, and a second site in the SAME file
# (the recovery directive's interpreter path) was visible in the same grep
# output and went unfixed. RC hit the identical thing at f0f3fd32 - "the
# hardcoded repo root was a class, not the one line just fixed". This test is
# what stops the third round.

# Absolutes that are DELIBERATE. Each needs a reason, or it is drift in costume.
ALLOWED_ABSOLUTES = {
    # The machine-wide slot root is the cross-repo contract itself: LW and RC
    # coordinate through ONE path, so it cannot be repo-relative. slots.py is
    # also byte-identical-by-contract and must never be edited unilaterally.
    ("ops/loop/slots.py", "ProgramData"),
    ("ops/loop/p5_probe.py", "ProgramData"),
    # Prose, not a path the code opens: usage text and the directive's FINAL
    # STEP instruction, both consumed on Legion by a human or an executor.
    # FUTURE: executor.py's copy pins an interpreter and would be wrong in a
    # venv - worth deriving, but it is instruction text, not a resolved path.
    ("ops/loop/done_sentinel.py", "docstring"),
    ("ops/loop/loop_controller.py", "docstring"),
    ("ops/loop/executor.py", "FINAL STEP"),
}
_BANNED_PREFIXES = (r"C:\LegionWallpaper", r"C:\Users" + "\\")


def _hardcoded_path_sites():
    import ast as _ast
    hits = []
    for py in sorted((ROOT / "ops").rglob("*.py")):
        if "__pycache__" in py.parts:
            continue
        rel = py.relative_to(ROOT).as_posix()
        try:
            tree = _ast.parse(py.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        # Identify docstrings by NODE identity, not by id() of the string value.
        # id() on equal str objects is not a reliable identity test - Python may
        # intern or not - and the first version of this guard used it, which
        # made it report a docstring as code the moment one was added. A guard
        # whose own classifier is unsound produces exactly the false red that
        # gets it deleted.
        docstrings = set()
        for n in _ast.walk(tree):
            if not isinstance(n, (_ast.Module, _ast.FunctionDef,
                                  _ast.AsyncFunctionDef, _ast.ClassDef)):
                continue
            body = getattr(n, "body", None)
            if (body and isinstance(body[0], _ast.Expr)
                    and isinstance(body[0].value, _ast.Constant)
                    and isinstance(body[0].value.value, str)):
                docstrings.add(id(body[0].value))
        for node in _ast.walk(tree):
            if not (isinstance(node, _ast.Constant) and isinstance(node.value, str)):
                continue
            if not any(p in node.value for p in _BANNED_PREFIXES):
                continue
            kind = "docstring" if id(node) in docstrings else "code"
            if kind == "docstring" and (rel, "docstring") in ALLOWED_ABSOLUTES:
                continue
            if any(rel == f and tag in ("FINAL STEP",) and tag.lower().replace(" ", "") in
                   node.value.lower().replace(" ", "")
                   for f, tag in ALLOWED_ABSOLUTES):
                continue
            hits.append(f"{rel}:{node.lineno}")
    return hits


def test_no_module_resolves_a_path_only_this_machine_has():
    """A hardcoded root is not one line - it is every line that shares the
    assumption, and the ones that stay behind fail only off Legion."""
    hits = _hardcoded_path_sites()
    assert hits == [], (
        f"hardcoded machine paths in ops/: {hits}. Derive from "
        f"Path(__file__) or sys.executable, or add an entry to "
        f"ALLOWED_ABSOLUTES with the reason it must be absolute.")
