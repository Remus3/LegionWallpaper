"""Drift guard: assert no Unicode smart quotes / en-em dashes / NBSP / ellipsis
in authored source files.

Hard rule (CLAUDE.md, carried over from the RC operating system 2026-05-18):
no em-dashes / en-dashes / smart quotes in any authored text - keep authored
content 7-bit ASCII. This test is the companion drift guard for
tools/strip_smart_quotes.py (same exclusion list) and is a mandatory /done
gate (see .claude/commands/done.md section 0).

If this test fails on a freshly added file, run:
    C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe tools/strip_smart_quotes.py            # dry-run report
    C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe tools/strip_smart_quotes.py --apply    # rewrite in place

Codepoints checked (mirrors strip_smart_quotes.py):
    U+201C  LEFT DOUBLE QUOTATION MARK
    U+201D  RIGHT DOUBLE QUOTATION MARK
    U+2018  LEFT SINGLE QUOTATION MARK
    U+2019  RIGHT SINGLE QUOTATION MARK
    U+2013  EN DASH
    U+2014  EM DASH
    U+2026  HORIZONTAL ELLIPSIS
    U+00A0  NON-BREAKING SPACE

FILE ENUMERATION (LW adaptation): `git ls-files --cached --others
--exclude-standard` - tracked files PLUS untracked-but-not-gitignored
files. The upstream guard walked tracked files only; LW runs this gate
from day one (before the initial commit lands) and wants freshly
authored, not-yet-staged files covered too. Everything gitignored
(Claude/, logs/, ops/runtime/, _archive/, __pycache__/, *.db, ...) is
excluded automatically by --exclude-standard.

EXCLUSIONS (parallel to the strip tool, defense-in-depth on top of
gitignore):
    - .git/, __pycache__/, _archive/ (any depth, incl. docs/_archive/),
      node_modules/
    - Claude/ at repo root (Claude Desktop app data, NOT project content)
    - logs/, ops/runtime/ (append-only / runtime state)
    - *.log / *.log.N, *.jsonl
    - binary: .pyc .pyd .db .png .jpg .jpeg .gif .webp .ico .zip .gz .exe
              .dll .lnk .woff .woff2 .ttf .bin .so .o
    - this test file itself + tools/strip_smart_quotes.py (both contain the
      codepoint constants intentionally, via chr() so they remain 7-bit ASCII)

EXTERNAL-DATA allowlist: EMPTY. LW starts clean - there is no vendored
external data yet. The _is_external_data hook is retained as the
extension point: when LW vendors third-party data files that carry
upstream punctuation, add their repo-relative path prefixes THERE (with
a comment naming the upstream source), never by weakening the walk.

MOJIBAKE allowance: files with U+201D bytes appearing in mojibake byte
context (e2 80 9d adjacent to e2 82 ac for U+20AC EURO sign) are flagged
to the report but allowed - those would be legacy mojibake of em-dash /
box-drawing characters needing separate hand-fix, NOT smart-quote drift.
The tolerance set is EMPTY (LW starts clean); the machinery is retained
for forward use if mojibake-tainted files are ever introduced before a
repair pass.

FROZEN files: per CLAUDE.md the frozen list is "none yet - files get
frozen as core stabilizes". The banned-set walk asserts on EVERY
enumerated authored file, frozen included (upstream policy since the
"frozen INCLUDED" operator greenlight). The _FROZEN set is retained
empty to power the explicit per-file regression lock
test_frozen_files_clean_of_banned_glyphs once files get frozen.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent

# Codepoints we ban. Built via chr() so this test file stays 7-bit ASCII.
_BANNED = {
    0x201C: "LEFT DOUBLE QUOTATION MARK",
    0x201D: "RIGHT DOUBLE QUOTATION MARK",
    0x2018: "LEFT SINGLE QUOTATION MARK",
    0x2019: "RIGHT SINGLE QUOTATION MARK",
    0x2013: "EN DASH",
    0x2014: "EM DASH",
    0x2026: "HORIZONTAL ELLIPSIS",
    0x00A0: "NON-BREAKING SPACE",
}

# UTF-8 byte sequences for each banned codepoint.
_BANNED_BYTES = {
    cp: chr(cp).encode("utf-8") for cp in _BANNED
}

# Mojibake neighbour for U+201D context check.
_MOJI_NEIGHBOUR = b"\xe2\x82\xac"  # U+20AC EURO SIGN bytes
_RDQUO_BYTES = b"\xe2\x80\x9d"

# Exclusions mirrored from tools/strip_smart_quotes.py
_SKIP_DIR_PARTS = {"_archive", "node_modules", "__pycache__", ".git", "logs"}
_SKIP_ROOT_DIRS = {"Claude"}  # Claude Desktop app data at repo root
_SKIP_REL_PREFIXES = ("ops/runtime/",)  # runtime state, never authored source
_SKIP_EXT = {
    ".pyc", ".pyd", ".db", ".png", ".jpg", ".jpeg", ".gif", ".webp",
    ".ico", ".zip", ".gz", ".exe", ".dll", ".lnk", ".woff", ".woff2",
    ".ttf", ".bin", ".so", ".o",
    ".jsonl",
}
_LOG_RE = re.compile(r"\.log(\.\d+)?$", re.IGNORECASE)

# Files that legitimately contain banned codepoints in chr() form (ASCII).
# These are the strip tool + this test itself - they reference the
# codepoints in docstrings as U+201C etc but never as literal glyphs.
# The test asserts on RAW BYTES so chr()-constructed runtime strings
# do not trigger.
_TEST_FILE = Path(__file__).resolve().as_posix()


def _is_external_data(rel_posix: str) -> bool:
    # LW starts clean: no vendored external data yet. When third-party
    # data files (upstream snapshots, vendored HTML, ...) are added and
    # carry upstream punctuation, allowlist their path prefixes HERE with
    # a comment naming the upstream source. Keep this list minimal.
    _ = rel_posix
    return False


def _should_skip(path: Path, rel_posix: str) -> bool:
    abs_p = path.resolve().as_posix()
    if abs_p == _TEST_FILE:
        return True
    if rel_posix == "tools/strip_smart_quotes.py":
        return True
    rel_parts = rel_posix.split("/")
    if rel_parts and rel_parts[0] in _SKIP_ROOT_DIRS:
        return True
    if set(rel_parts) & _SKIP_DIR_PARTS:
        return True
    if rel_posix.startswith(_SKIP_REL_PREFIXES):
        return True
    name = path.name.lower()
    if _LOG_RE.search(name):
        return True
    if name.endswith((".db-shm", ".db-wal")):
        return True
    if path.suffix.lower() in _SKIP_EXT:
        return True
    if _is_external_data(rel_posix):
        return True
    return False


# Frozen files per CLAUDE.md hard-rule list: "none yet - files get frozen
# as core stabilizes". The banned-set walk covers every enumerated file
# regardless (frozen files are NOT skipped - upstream "frozen INCLUDED"
# policy), so a banned glyph cannot hide in a frozen file undetected.
# When files get frozen, add their repo-relative POSIX paths here so the
# explicit per-file regression lock below pins them too.
_FROZEN: frozenset[str] = frozenset()


# Files with pre-existing mojibake (mis-encoded em-dash sequences containing
# U+201D bytes in mojibake context). These are NOT smart-quote drift; they
# need separate mojibake repair. EMPTY - LW starts clean. The tolerance
# machinery is retained for forward use if new mojibake-tainted files are
# introduced before a repair pass.
_MOJIBAKE_TOLERATED: frozenset[str] = frozenset()


def _tracked_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=_REPO_ROOT,
        capture_output=True,
        check=True,
    ).stdout
    return [_REPO_ROOT / p for p in out.decode("utf-8").split("\0") if p]


def _is_pure_mojibake_201d(raw: bytes) -> bool:
    """True if every U+201D byte in raw is in mojibake context."""
    total = raw.count(_RDQUO_BYTES)
    if total == 0:
        return True
    # find every U+201D byte position, check neighbours
    n_moji = 0
    i = 0
    while True:
        idx = raw.find(_RDQUO_BYTES, i)
        if idx < 0:
            break
        nxt = raw[idx + 3:idx + 6]
        prev = raw[max(0, idx - 3):idx]
        if nxt == _MOJI_NEIGHBOUR or prev == _MOJI_NEIGHBOUR:
            n_moji += 1
        i = idx + 3
    return n_moji == total


def test_no_smart_quotes_in_authored_source() -> None:
    """Walk every enumerated source file and assert no banned codepoint bytes."""
    violations: list[tuple[str, int, str, int]] = []
    for p in _tracked_files():
        rel_posix = p.relative_to(_REPO_ROOT).as_posix()
        if _should_skip(p, rel_posix):
            continue
        # Frozen files are NOT skipped (upstream "frozen INCLUDED" policy);
        # the banned-set walk covers them.
        try:
            raw = p.read_bytes()
        except OSError:
            continue
        # Decode-test: skip true binary (e.g. embedded raw bytes in some
        # test fixtures); the strip tool does the same.
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        for cp, name in _BANNED.items():
            byte_seq = _BANNED_BYTES[cp]
            n = raw.count(byte_seq)
            if not n:
                continue
            # Mojibake allowance for U+201D
            if cp == 0x201D and rel_posix in _MOJIBAKE_TOLERATED:
                if _is_pure_mojibake_201d(raw):
                    continue  # all U+201D are mojibake context; tolerated
            violations.append((rel_posix, cp, name, n))

    if violations:
        lines = [
            f"  {rel}: U+{cp:04X} ({name}) x{n}"
            for rel, cp, name, n in sorted(violations)
        ]
        msg = (
            "Smart-quote / em-dash / en-dash / NBSP / ellipsis drift detected. "
            "Run `C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe tools/strip_smart_quotes.py` to inspect, then `--apply` "
            "to rewrite. Violations:\n" + "\n".join(lines)
        )
        pytest.fail(msg)


def test_frozen_files_clean_of_banned_glyphs() -> None:
    """Per-file regression lock: every frozen file is free of the banned set
    (em/en-dash, smart quotes, NBSP, ellipsis). The LW frozen list is empty
    (CLAUDE.md: "none yet"), so this passes trivially today; it activates
    automatically as paths are added to _FROZEN. A miss here also surfaces
    in test_no_smart_quotes_in_authored_source (frozen files are walked)."""
    violations: list[tuple[str, int, str, int]] = []
    for rel_posix in sorted(_FROZEN):
        p = _REPO_ROOT / rel_posix
        if not p.is_file():
            continue
        raw = p.read_bytes()
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        for cp, name in _BANNED.items():
            n = raw.count(_BANNED_BYTES[cp])
            if n:
                violations.append((rel_posix, cp, name, n))
    assert not violations, (
        "Banned glyph(s) in frozen file(s) (operator-gated to fix):\n"
        + "\n".join(f"  {rel}: U+{cp:04X} ({name}) x{n}"
                    for rel, cp, name, n in violations)
    )


def test_strip_smart_quotes_tool_is_ascii() -> None:
    """The strip tool itself MUST be 7-bit ASCII (codepoints via chr())."""
    p = _REPO_ROOT / "tools" / "strip_smart_quotes.py"
    assert p.is_file(), f"strip tool missing at {p}"
    raw = p.read_bytes()
    non_ascii = [(i, b) for i, b in enumerate(raw) if b > 127]
    assert not non_ascii, (
        f"tools/strip_smart_quotes.py has {len(non_ascii)} non-ASCII bytes; "
        f"first at offset {non_ascii[0][0]}"
    )


def test_this_drift_guard_is_ascii() -> None:
    """This test file MUST be 7-bit ASCII."""
    raw = Path(__file__).read_bytes()
    non_ascii = [(i, b) for i, b in enumerate(raw) if b > 127]
    assert not non_ascii, (
        f"tests/test_smart_quote_hygiene.py has {len(non_ascii)} non-ASCII "
        f"bytes; first at offset {non_ascii[0][0]}"
    )
