"""Drift guard: assert that U+2500 BOX DRAWINGS LIGHT HORIZONTAL does NOT
appear in operator-asserted-clean files.

Background (inherited from the RC operating system hygiene sweeps): U+2500
(UTF-8 bytes e2 94 80) shows up when box-drawing horizontal rules in
docstring section headers (e.g. "# === Section ============") get authored
with the box-drawing glyph instead of plain ASCII '-'. The visual width is
identical (1:1 char replacement) and the semantic intent of a horizontal
rule is preserved by the ASCII form.

SCOPE NOTE (mechanism preserved 1:1 from upstream): U+2500 is NOT a banned
codepoint globally (unlike smart quotes / em-dashes which are CLAUDE.md
hard-rule). Upstream it appeared intentionally in many authored files, so
the guard deliberately asserts ONLY on files the operator has explicitly
swept clean and pinned. LW starts with ZERO U+2500 anywhere, so the
_ASSERTED_CLEAN pin set starts EMPTY - to pin files in the future, the
operator must grant explicit permission, run the sweep tool, and add the
repo-relative POSIX paths to the _ASSERTED_CLEAN frozenset below. The
walk test then covers them automatically.

If this test fails on a re-introduction, normalize the U+2500 glyphs in
the flagged file back to ASCII '-' (1:1 char replacement), or port
tools/strip_u2500.py from RC:
    C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe tools/strip_u2500.py --allow-frozen <path> --dry-run
    C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe tools/strip_u2500.py --allow-frozen <path>
"""
from __future__ import annotations

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent

# UTF-8 byte sequence for U+2500 BOX DRAWINGS LIGHT HORIZONTAL.
# Constructed via \xNN escapes so this test file stays 7-bit ASCII.
_U2500_BYTES = b"\xe2\x94\x80"

# Operator-granted swept-clean files. These specific paths must remain
# U+2500-free. EMPTY at LW start (the repo has zero U+2500 anywhere and
# no operator sweeps have been granted yet). To extend coverage, get
# operator grant + run the sweep tool, then add the path here.
_ASSERTED_CLEAN: frozenset[str] = frozenset()


def _count_u2500(path: Path) -> int:
    try:
        raw = path.read_bytes()
    except OSError:
        return 0
    return raw.count(_U2500_BYTES)


def test_all_asserted_clean_files_are_u2500_free() -> None:
    """Walk the _ASSERTED_CLEAN frozenset and verify every entry is clean.

    Passes trivially while the set is empty (LW start state); any future
    extension to the set is automatically covered.
    """
    violations: list[tuple[str, int]] = []
    for rel_posix in sorted(_ASSERTED_CLEAN):
        p = _REPO_ROOT / rel_posix
        if not p.is_file():
            pytest.fail(f"asserted-clean file missing: {rel_posix}")
        n = _count_u2500(p)
        if n > 0:
            violations.append((rel_posix, n))
    if violations:
        lines = [f"  {rel}: U+2500 x{n}" for rel, n in violations]
        msg = (
            "U+2500 drift detected in operator-asserted-clean files. "
            "Normalize the glyphs back to ASCII '-' (or port "
            "tools/strip_u2500.py from RC and run it with --allow-frozen "
            "<path>). Violations:\n" + "\n".join(lines)
        )
        pytest.fail(msg)


def test_strip_u2500_tool_is_ascii() -> None:
    """The strip tool MUST be 7-bit ASCII (no literal U+2500 glyph) if present.

    LW starts U+2500-free, so tools/strip_u2500.py is ported from RC on
    demand rather than vendored up front. Skip (visibly) until it exists;
    once ported, this asserts it stays ASCII.
    """
    p = _REPO_ROOT / "tools" / "strip_u2500.py"
    if not p.is_file():
        pytest.skip("tools/strip_u2500.py not vendored yet (LW starts "
                    "U+2500-free; port from RC on demand)")
    raw = p.read_bytes()
    non_ascii = [(i, b) for i, b in enumerate(raw) if b > 127]
    assert not non_ascii, (
        f"tools/strip_u2500.py has {len(non_ascii)} non-ASCII bytes; "
        f"first at offset {non_ascii[0][0]}"
    )


def test_this_drift_guard_is_ascii() -> None:
    """This test file MUST be 7-bit ASCII."""
    raw = Path(__file__).read_bytes()
    non_ascii = [(i, b) for i, b in enumerate(raw) if b > 127]
    assert not non_ascii, (
        f"tests/test_u2500_hygiene.py has {len(non_ascii)} non-ASCII "
        f"bytes; first at offset {non_ascii[0][0]}"
    )
