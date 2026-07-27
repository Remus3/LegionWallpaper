"""Per-session drift guard for Legion Wallpaper. Cheap invariant checks at /done.

Exit 0 = clean, 1 = at least one breach. Adapted from the machine-wide ritual doc
(DONE_RITUAL_OPTIMIZED.md, 2026-07-26). Every check exists because the drift it
catches actually happened on a project on this box and later cost a dedicated
cleanup session.

LW-specific deviations from the reference implementation, each measured:
- MIRROR_PAIRS (tools/*.md <-> .claude/commands/*.md) is a NO-OP here: the two
  dirs share zero basenames. Replaced by LW's real duplicated-invariant risk -
  every .claude/commands/*.md must carry the SUBAGENT-FIRST block (CLAUDE.md).
- Untracked-authored is still checked but points at .claude/commands, which LW
  tracks in git (unlike RC, where it was gitignored and silently unversioned).
- Version-anchor stays wired but dormant: LW has no shipped version string yet.
"""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

# CREATE_NO_WINDOW: 0 on non-Windows so the module still imports/tests in CI.
# Under a pythonw.exe parent (every hook + scheduled task here) a console child
# allocates its OWN window and flashes over the desktop.
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# ---- CONFIG - the only per-project section -------------------------------
# CLAUDE.md budget is real and CI-enforced (CLAUDE.md: "CI size-budgeted < 60KB").
# ROADMAP.md is advisory here - LW states no hard budget for it.
DOC_BUDGETS = {"CLAUDE.md": 61440}
DOC_BUDGETS_ADVISORY = {"ROADMAP.md": 81920}
COMMANDS_DIR = ".claude/commands"
COMMANDS_MARKER = "SUBAGENT-FIRST"
MEMORY_DIR = pathlib.Path(
    r"C:\Users\Administrator\.claude\projects\C--LegionWallpaper\memory"
)
MEMORY_INDEX = "MEMORY.md"
MEMORY_UNINDEXED_OK = ()
DOC_GLOBS = ["docs/**/*.md", "*.md"]
DOC_EXCLUDE = ("_archive", "node_modules", ".git", "worktrees", ".venv")
# --------------------------------------------------------------------------

problems: list[str] = []
notes: list[str] = []


def warn(msg: str) -> None:
    problems.append(msg)


def _authored_docs() -> list[pathlib.Path]:
    out: list[pathlib.Path] = []
    for g in DOC_GLOBS:
        for p in ROOT.glob(g):
            if p.is_file() and not any(x in p.as_posix() for x in DOC_EXCLUDE):
                out.append(p)
    return out


def check_doc_budgets() -> None:
    for name, budget in DOC_BUDGETS.items():
        p = ROOT / name
        if not p.exists():
            warn(f"DOC BUDGET: {name} missing")
            continue
        n = p.stat().st_size
        pct = 100 * n / budget
        if n > budget:
            warn(f"DOC BUDGET: {name} is {n} bytes, OVER its {budget} budget")
        elif pct >= 90:
            warn(f"DOC BUDGET: {name} at {pct:.0f}% of budget - relocate soon")
        else:
            notes.append(f"{name} {pct:.0f}% of {budget} budget")
    for name, budget in DOC_BUDGETS_ADVISORY.items():
        p = ROOT / name
        if p.exists():
            notes.append(f"{name} {100 * p.stat().st_size / budget:.0f}% (advisory)")


def check_command_marker() -> None:
    """LW invariant: every command doc carries the SUBAGENT-FIRST block."""
    d = ROOT / COMMANDS_DIR
    if not d.is_dir():
        notes.append(f"{COMMANDS_DIR} absent - marker check skipped")
        return
    files = sorted(d.glob("*.md"))
    missing = [f.name for f in files
               if COMMANDS_MARKER.lower() not in
               f.read_text(encoding="utf-8", errors="replace").lower()]
    if missing:
        warn(f"COMMAND MARKER: {len(missing)} missing {COMMANDS_MARKER}: {missing[:6]}")
    else:
        notes.append(f"{len(files)} command docs carry {COMMANDS_MARKER}")


def check_memory_index() -> None:
    if not MEMORY_DIR.is_dir():
        warn(f"MEMORY: {MEMORY_DIR} not found")
        return
    idx = MEMORY_DIR / MEMORY_INDEX
    if not idx.exists():
        warn(f"MEMORY: no {MEMORY_INDEX}")
        return
    text = idx.read_text(encoding="utf-8", errors="replace")
    files = {p.stem for p in MEMORY_DIR.glob("*.md") if p.name != MEMORY_INDEX}
    linked = set(re.findall(r"\]\(([A-Za-z0-9_.\-]+)\.md\)", text))
    dead = sorted(linked - files)
    if dead:
        warn(f"MEMORY: {len(dead)} dead index link(s): {dead[:5]}")
    unindexed = sorted(
        f for f in (files - linked)
        if not (MEMORY_UNINDEXED_OK and f.startswith(MEMORY_UNINDEXED_OK))
    )
    if unindexed:
        warn(f"MEMORY: {len(unindexed)} unindexed: {unindexed[:6]}")
    if not dead and not unindexed:
        notes.append(f"memory index clean ({len(files)} files)")


def check_version_anchors(old_version: str | None) -> None:
    """After a version bump, no authored doc may still name the OLD version."""
    if not old_version:
        return
    hits = []
    for p in list(_authored_docs()) + list(ROOT.glob("docs/**/*.html")):
        try:
            if old_version in p.read_text(encoding="utf-8", errors="replace"):
                hits.append(p.relative_to(ROOT).as_posix())
        except OSError:
            continue
    hits = [h for h in hits
            if not re.search(r"CHANGELOG|HISTORY|LEDGER|_archive|WAKEUP", h, re.I)]
    if hits:
        warn(f"VERSION ANCHOR: {old_version} still present in {hits}")


def check_counted_claims() -> None:
    """A doc saying 'the N most recent' above a list of a different length."""
    words = {"three": 3, "five": 5, "ten": 10, "twelve": 12,
             "fifteen": 15, "twenty": 20}
    for p in _authored_docs():
        text = p.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"[Tt]he (\w+) most recent", text)
        if not m:
            continue
        claimed = words.get(m.group(1).lower())
        if claimed is None:
            continue
        actual = len(re.findall(r"^- \d+\.\d+\.\d+ ->", text[m.end():], re.M))
        if actual and actual != claimed:
            warn(f"COUNT CLAIM: {p.relative_to(ROOT).as_posix()} says "
                 f"'{m.group(1)} most recent' but lists {actual}")


def check_untracked_authored() -> None:
    """Authored command docs git is not tracking - LW tracks .claude/ on purpose."""
    d = ROOT / COMMANDS_DIR
    if not d.is_dir():
        return
    bad = []
    for f in sorted(d.glob("*.md")):
        rel = f.relative_to(ROOT).as_posix()
        r = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "--error-unmatch", rel],
            capture_output=True, text=True, creationflags=NO_WINDOW,
        )
        if r.returncode != 0:
            bad.append(rel)
    if bad:
        warn(f"UNTRACKED: {len(bad)} authored command doc(s) not in git: {bad[:5]}")


def check_cited_shas() -> None:
    """SHAs cited in staged docs must resolve (worktree-slice SHAs often do not)."""
    r = subprocess.run(
        ["git", "-C", str(ROOT), "diff", "--cached", "-U0"],
        capture_output=True, text=True, creationflags=NO_WINDOW,
    )
    added = [ln for ln in r.stdout.splitlines() if ln.startswith("+")]
    shas = set(re.findall(r"\b([0-9a-f]{7,8})\b", "\n".join(added)))
    for sha in sorted(shas)[:40]:
        ok = subprocess.run(
            ["git", "-C", str(ROOT), "cat-file", "-e", f"{sha}^{{commit}}"],
            capture_output=True, creationflags=NO_WINDOW,
        )
        if ok.returncode != 0:
            notes.append(f"cited SHA {sha} does not resolve (worktree slice?)")


def main() -> int:
    old_version = sys.argv[1] if len(sys.argv) > 1 else None
    check_doc_budgets()
    check_command_marker()
    check_memory_index()
    check_version_anchors(old_version)
    check_counted_claims()
    check_untracked_authored()
    check_cited_shas()

    for n in notes:
        print(f"  note   : {n}")
    for p in problems:
        print(f"  BREACH : {p}")
    print(f"drift_guard: {len(problems)} breach(es), {len(notes)} note(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
