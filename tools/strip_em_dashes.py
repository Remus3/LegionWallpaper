"""One-shot + reusable maintenance: purge Unicode dashes + smart quotes.

Hard rule (CLAUDE.md, carried over from Riot Commander 2026-05-18): no
em-dashes, en-dashes, or smart quotes in any authored text - keep
authored content 7-bit ASCII. This replaces every em-dash (U+2014) and
en-dash (U+2013) with a plain ASCII hyphen-minus '-', and every smart
quote (U+2018 U+2019 U+201C U+201D) with the plain ASCII apostrophe or
double quote. A flat 1:1 char swap (not context-aware) is deliberate:
' X ' (spaced dash) naturally becomes ' - ' which reads fine in prose.
Arrows / math symbols are NOT in scope (the hard rule names dashes +
smart quotes; anything further is a separate operator-gated decision).

This script keeps itself 7-bit ASCII (codepoints via chr(), not the
literal glyphs) so it does not need to be its own exclusion for that
reason - it is still skipped to avoid self-mutation mid-walk.

EXCLUSIONS (immutable history / non-text / not project content, per the
standing don't-rewrite-history rule + CLAUDE.md carve-out):
  - .git/ , __pycache__/ , any path component '_archive'
  - Claude/ at repo root (Claude Desktop app data, NOT project content)
  - logs/ and any *.log / *.log.N (append-only operational history)
  - *.jsonl (append-only operational ledgers)
  - binary / generated: .pyc .pyd .db .db-shm .db-wal .png .jpg .jpeg
    .gif .ico .zip .exe .dll .lnk .woff .woff2 .ttf .bin .so .o
  - this script itself (it documents the chars via chr() codepoints)

File enumeration: git ls-files when the repo has git history (tracked
files only - everything gitignored is excluded automatically); falls
back to a filesystem walk with the same exclusions while the repo is
young / unborn.

Usage:
  C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe tools/strip_em_dashes.py            # dry-run (default): report only
  C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe tools/strip_em_dashes.py --apply    # rewrite in place (atomic)
  C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe tools/strip_em_dashes.py --check    # drift gate: exit 1 if any offender found
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

EM = chr(0x2014)    # em-dash
EN = chr(0x2013)    # en-dash
LSQ = chr(0x2018)   # left single smart quote
RSQ = chr(0x2019)   # right single smart quote
LDQ = chr(0x201C)   # left double smart quote
RDQ = chr(0x201D)   # right double smart quote
REPL = {EM: "-", EN: "-", LSQ: "'", RSQ: "'", LDQ: '"', RDQ: '"'}
# All six offenders are U+2013..U+201D: UTF-8 prefix b"\xe2\x80" is a cheap
# byte-level prefilter before the (costlier) decode + per-char count.
_PREFILTER = b"\xe2\x80"
ROOT = Path(__file__).resolve().parent.parent

# CREATE_NO_WINDOW: 0 on non-Windows so the module still imports/tests in CI.
# Under a pythonw.exe parent a console child allocates its OWN window.
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# git-tracked enumeration already excludes everything gitignored
# (.pyc, ops/runtime state, .venv, ...). These are the additional
# tracked-but-immutable / non-project carve-outs; the walk fallback
# relies on them entirely.
_SKIP_DIR_PARTS = {".git", "__pycache__", "_archive", "logs"}
_SKIP_ROOT_DIRS = {"Claude"}  # Claude Desktop app data at repo root
_SKIP_EXT = {
    ".pyc", ".pyd", ".db", ".png", ".jpg", ".jpeg", ".gif", ".ico",
    ".zip", ".exe", ".dll", ".lnk", ".woff", ".woff2", ".ttf", ".bin",
    ".so", ".o",
    # append-only operational ledgers: logs in JSON form, potentially
    # concurrently written by a running daemon.
    ".jsonl",
}
# any *.log, *.log.1, *.log.3, supervisor.log.3, ...
_LOG_RE = re.compile(r"\.log(\.\d+)?$", re.IGNORECASE)
_SELF = Path(__file__).resolve()


def _skip(path: Path) -> bool:
    if path.resolve() == _SELF:
        return True
    try:
        rel = path.resolve().relative_to(ROOT)
    except ValueError:
        rel = path
    if rel.parts and rel.parts[0] in _SKIP_ROOT_DIRS:
        return True
    if set(rel.parts) & _SKIP_DIR_PARTS:
        return True
    name = path.name.lower()
    if _LOG_RE.search(name):
        return True
    if name.endswith((".db-shm", ".db-wal")):
        return True
    if path.suffix.lower() in _SKIP_EXT:
        return True
    return False


def _tracked_files() -> list[Path]:
    """git ls-files if usable; else a filesystem walk (same exclusions)."""
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z"], cwd=ROOT,
            capture_output=True, check=True, creationflags=NO_WINDOW,
        ).stdout
        files = [ROOT / p for p in out.decode("utf-8").split("\0") if p]
        if files:
            return files
    except (OSError, subprocess.CalledProcessError):
        pass
    return [p for p in ROOT.rglob("*") if p.is_file()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="rewrite files in place (default: dry-run)")
    ap.add_argument("--check", action="store_true",
                    help="drift gate: dry-run + exit 1 if any offender found")
    ap.add_argument("--top", type=int, default=15,
                    help="show N highest-count files")
    args = ap.parse_args()

    by_ext: Counter[str] = Counter()
    per_file: list[tuple[int, str]] = []
    total_occ = 0
    files_changed = 0
    skipped_binary = 0

    for p in _tracked_files():
        if _skip(p):
            continue
        try:
            raw = p.read_bytes()
        except OSError:
            continue
        if _PREFILTER not in raw:
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            skipped_binary += 1
            continue
        n = sum(text.count(d) for d in REPL)
        if not n:
            continue
        total_occ += n
        files_changed += 1
        by_ext[p.suffix.lower() or "<none>"] += n
        per_file.append((n, str(p.relative_to(ROOT))))
        if args.apply:
            new = text
            for d, r in REPL.items():
                new = new.replace(d, r)
            tmp = p.with_suffix(p.suffix + ".emtmp")
            tmp.write_text(new, encoding="utf-8", newline="")
            os.replace(tmp, p)

    mode = ("APPLIED" if args.apply else
            "CHECK (drift gate)" if args.check else "DRY-RUN (no writes)")
    print(f"=== strip_em_dashes (em+en+smart-quotes) {mode} ===")
    print(f"files with offenders : {files_changed}")
    print(f"total occurrences    : {total_occ}")
    print(f"skipped (binary utf8): {skipped_binary}")
    print("by extension:")
    for ext, c in by_ext.most_common():
        print(f"  {ext:<8} {c}")
    print(f"top {args.top} files by count:")
    for n, rel in sorted(per_file, reverse=True)[:args.top]:
        print(f"  {n:>6}  {rel}")
    if args.check and total_occ > 0:
        print("DRIFT: offenders present - run with --apply to purge")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
