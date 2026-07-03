"""Drift guard: assert no mojibake byte signatures in tracked source files.

Background (inherited from the RC operating system hygiene sweep): two
8-byte mojibake signatures were observed upstream. Both are dash-class
glyphs that survived a cp1252-misdecode then UTF-8 re-encode round
trip:

    Variant A: c3 a2 e2 80 9d e2 82 ac  (orig: U+2500 box draw)
    Variant B: c3 a2 e2 82 ac e2 80 9d  (orig: U+2014 em-dash)

LW starts clean - neither signature exists anywhere in this repo. This
drift guard asserts neither signature EVER appears in any enumerated
authored source file, so a copy-paste from a mis-encoded source (or a
bad editor round-trip) is caught at the /done gate immediately.

If this test fails on a freshly added file, run:
    C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe tools/repair_mojibake.py            # dry-run report (both variants)
    C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe tools/repair_mojibake.py --apply    # rewrite in place
    C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe tools/strip_smart_quotes.py --apply # follow-through to ASCII ' - '
(tools/repair_mojibake.py is ported from RC on demand - LW has no
mojibake today, so the repair tool is not yet vendored; hand-fix or
port it if this guard ever trips.)

FILE ENUMERATION (LW adaptation): `git ls-files --cached --others
--exclude-standard` - tracked files PLUS untracked-but-not-gitignored
files, so the gate covers freshly authored files before the initial
commit lands. Everything gitignored is excluded automatically.

EXCLUSIONS (parallel to the smart-quote guard):
    - .git/, __pycache__/, _archive/ (any depth, incl. docs/_archive/),
      node_modules/
    - Claude/ at repo root (Claude Desktop app data, NOT project content)
    - logs/, ops/runtime/ (append-only / runtime state)
    - *.log / *.log.N, *.jsonl
    - binary: .pyc .pyd .db .png .jpg .jpeg .gif .webp .ico .zip .gz .exe
              .dll .lnk .woff .woff2 .ttf .bin .so .o
    - this test file itself + tools/repair_mojibake.py (both reference the
      signature via \\xNN byte literals so they stay 7-bit ASCII)

EXTERNAL-DATA allowlist: EMPTY. LW starts clean; the _is_external_data
hook is the extension point for future vendored data, same as in
test_smart_quote_hygiene.py.

FROZEN files: per CLAUDE.md the frozen list is "none yet". Upstream, the
mojibake walk excluded frozen files (the repair tool refuses to rewrite
them without an operator grant); the exclusion branch is retained with an
empty set so the behavior activates automatically once files get frozen.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent

# 8-byte mojibake signatures, via \xNN byte literals to keep this file ASCII.
#   Variant A: c3 a2 e2 80 9d e2 82 ac  (orig: U+2500 box draw)
#   Variant B: c3 a2 e2 82 ac e2 80 9d  (orig: U+2014 em-dash)
_MOJIBAKE_SIG = b"\xc3\xa2\xe2\x80\x9d\xe2\x82\xac"
_MOJIBAKE_SIG_B = b"\xc3\xa2\xe2\x82\xac\xe2\x80\x9d"
_MOJIBAKE_SIGS: tuple[bytes, ...] = (_MOJIBAKE_SIG, _MOJIBAKE_SIG_B)

# Exclusions mirrored from tests/test_smart_quote_hygiene.py
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

_TEST_FILE = Path(__file__).resolve().as_posix()


def _is_external_data(rel_posix: str) -> bool:
    # LW starts clean: no vendored external data yet. Allowlist future
    # third-party data path prefixes HERE, mirroring the smart-quote guard.
    _ = rel_posix
    return False


def _should_skip(path: Path, rel_posix: str) -> bool:
    abs_p = path.resolve().as_posix()
    if abs_p == _TEST_FILE:
        return True
    # The repair tool references the signature via \xNN literals.
    if rel_posix == "tools/repair_mojibake.py":
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
# as core stabilizes". The repair tool refuses to rewrite frozen files by
# default; this test also excludes them from the assertion (any stray
# mojibake inside a frozen file is operator-gated to fix separately).
# Add repo-relative POSIX paths here when files get frozen.
_FROZEN: frozenset[str] = frozenset()


def _tracked_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=_REPO_ROOT,
        capture_output=True,
        check=True,
    ).stdout
    return [_REPO_ROOT / p for p in out.decode("utf-8").split("\0") if p]


def test_no_mojibake_signature_in_authored_source() -> None:
    """Walk every enumerated source file and assert no mojibake signature."""
    violations: list[tuple[str, int, int]] = []  # (rel, n_a, n_b)
    for p in _tracked_files():
        rel_posix = p.relative_to(_REPO_ROOT).as_posix()
        if _should_skip(p, rel_posix):
            continue
        if rel_posix in _FROZEN:
            continue
        try:
            raw = p.read_bytes()
        except OSError:
            continue
        n_a = raw.count(_MOJIBAKE_SIG)
        n_b = raw.count(_MOJIBAKE_SIG_B)
        if n_a or n_b:
            violations.append((rel_posix, n_a, n_b))

    if violations:
        lines = [
            f"  {rel}: A={n_a} B={n_b} (A=c3a2 e2809d e282ac, "
            f"B=c3a2 e282ac e2809d)"
            for rel, n_a, n_b in sorted(violations)
        ]
        msg = (
            "Mojibake byte signature drift detected. Hand-fix the mis-encoded "
            "bytes (or port tools/repair_mojibake.py from RC), then run "
            "`C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe tools/strip_smart_quotes.py --apply` to "
            "normalize. Violations:\n" + "\n".join(lines)
        )
        pytest.fail(msg)


def test_repair_mojibake_tool_is_ascii() -> None:
    """The repair tool MUST be 7-bit ASCII (signature via \\xNN) if present.

    LW starts mojibake-free, so tools/repair_mojibake.py is ported from RC
    on demand rather than vendored up front. Skip (visibly) until it exists;
    once ported, this asserts it stays ASCII.
    """
    p = _REPO_ROOT / "tools" / "repair_mojibake.py"
    if not p.is_file():
        pytest.skip("tools/repair_mojibake.py not vendored yet (LW starts "
                    "mojibake-free; port from RC on demand)")
    raw = p.read_bytes()
    non_ascii = [(i, b) for i, b in enumerate(raw) if b > 127]
    assert not non_ascii, (
        f"tools/repair_mojibake.py has {len(non_ascii)} non-ASCII bytes; "
        f"first at offset {non_ascii[0][0]}"
    )


def test_this_drift_guard_is_ascii() -> None:
    """This test file MUST be 7-bit ASCII."""
    raw = Path(__file__).read_bytes()
    non_ascii = [(i, b) for i, b in enumerate(raw) if b > 127]
    assert not non_ascii, (
        f"tests/test_mojibake_hygiene.py has {len(non_ascii)} non-ASCII "
        f"bytes; first at offset {non_ascii[0][0]}"
    )
