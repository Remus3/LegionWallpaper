#!/usr/bin/env python3
r"""Verify the glyph/ruff gate is ACTIVE, not merely present.

WHY THIS EXISTS (docs/specs/2026-07-26-f1-sdk-executor-channel.md section 7, P0).
RC measured on 2026-07-26 that a nested
`claude -p --permission-mode bypassPermissions` lands a commit carrying a banned
em-dash: git hooks ran, the Claude PreToolUse gate did not. A git hook is the
only placement that survives every channel (AHK, SDK, human, CI).

TWO FALSE-GREEN TRAPS THIS TOOL EXISTS TO CATCH, both measured on LW the same day:

  1. WRONG DIRECTORY. `core.hooksPath` was already set to a TRACKED `.githooks`
     here, which makes git ignore `.git/hooks` ENTIRELY. A first cut of this
     installer wrote correct hooks into `.git/hooks` and reported "installed and
     intact" while they were dead. Checking the directory you wrote to proves
     nothing - resolve the EFFECTIVE hooks path from git config and check THAT.

  2. RIGHT FILE, WRONG INVOCATION. `.githooks/pre-commit` called
     `precommit_gate.py` with NO ARGUMENTS from 2026-07-03 to 2026-07-26. Given
     no args the gate reads the Claude PreToolUse payload from stdin, finds no
     `git commit` command, and self-gates to a SILENT no-op. The hook existed,
     was executable, was tracked, ran on every commit, and gated nothing.
     Measured consequence: 84 of the last 200 LW commits carry the banned
     co-author trailer. So presence is not the check - the required ARGUMENT is.

Hook bodies live in the tracked `.githooks/` and arrive with any clone. The only
per-clone step is `core.hooksPath`, which is local config and cannot be tracked.

That config is REPO-level, so it is shared with every linked worktree and holds
the MAIN checkout's absolute `.githooks`. Resolving the tracked gate against the
current working tree alone therefore reported a FALSE NEGATIVE in every worktree
(2026-07-29) - see `tracked_hooks_dirs`.

Usage:
  python tools/install_git_hooks.py            # set core.hooksPath, then verify
  python tools/install_git_hooks.py --check    # verify only; exit 1 on any gap
  python tools/install_git_hooks.py --repo PATH [...]
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

HOOKS_DIRNAME = ".githooks"

# hook file -> the exact invocation that must appear in it. Presence of the file
# is NOT sufficient (trap 2 above); the argument is what makes the gate fire.
REQUIRED = {
    "pre-commit": "precommit_gate.py\" --git-hook",
    "commit-msg": "precommit_gate.py\" --message-file",
}


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                          text=True, errors="replace", creationflags=NO_WINDOW)


def _resolve(p: Path) -> Path:
    try:
        return p.resolve()
    except OSError:
        return p


def common_git_dir(repo: Path) -> Path:
    """The shared .git that owns every worktree - worktree-invariant."""
    common = _git(repo, "rev-parse", "--git-common-dir").stdout.strip()
    base = Path(common) if common else repo / ".git"
    if not base.is_absolute():
        base = repo / base
    return base


def effective_hooks_dir(repo: Path) -> Path:
    """What git ACTUALLY uses: core.hooksPath if set, else .git/hooks."""
    cfg = _git(repo, "config", "--get", "core.hooksPath").stdout.strip()
    if cfg:
        p = Path(cfg)
        # A relative core.hooksPath is resolved by git against the top level of
        # the working tree the hook runs in, so `repo` is the right base here.
        return p if p.is_absolute() else repo / p
    return common_git_dir(repo) / "hooks"


def tracked_hooks_dirs(repo: Path) -> list[Path]:
    """Every directory whose `.githooks` IS this repo's tracked gate.

    Two of them, because `core.hooksPath` is REPO-level config shared with every
    linked worktree. A worktree therefore inherits the MAIN checkout's absolute
    `.githooks` while also checking out its own copy of the same tracked files -
    both are the real gate and hooks fire either way. Comparing only against the
    working tree reported every worktree INERT (measured 2026-07-29), and a
    safety check that cries wolf in a repo full of parallel worktree agents
    teaches them to dismiss a red gate, which is worse than no check at all.
    """
    out: list[Path] = []
    for base in (repo, _resolve(common_git_dir(repo)).parent):
        d = _resolve(base / HOOKS_DIRNAME)
        if d not in out:
            out.append(d)
    return out


def check(repo: Path) -> list[str]:
    """Return drift descriptions; empty means the gate is genuinely active."""
    problems: list[str] = []
    candidates = tracked_hooks_dirs(repo)
    active = effective_hooks_dir(repo)
    active_res = _resolve(active)
    armed = active_res in candidates

    if not armed:
        problems.append(
            f"core.hooksPath points at {active} - the tracked gate in "
            f"{HOOKS_DIRNAME} is INERT (git ignores it)")

    # Inspect the directory git will actually run when it is a tracked one; only
    # fall back to this tree's copy when the active dir is not the gate at all.
    gate_dir = active_res if armed else candidates[0]

    for name, needle in REQUIRED.items():
        f = gate_dir / name
        if not f.is_file():
            problems.append(f"MISSING {HOOKS_DIRNAME}/{name}")
            continue
        # git SILENTLY skips a hook without the exec bit, so a 0644 hook is a
        # dead gate that reads as installed. No exec bit exists on Windows.
        if os.name != "nt" and not os.access(f, os.X_OK):
            problems.append(
                f"{HOOKS_DIRNAME}/{name} is not executable - git skips it "
                f"silently, so the gate is dead")
        body = f.read_text(encoding="utf-8", errors="replace")
        if needle not in body:
            problems.append(
                f"{HOOKS_DIRNAME}/{name} does not invoke the gate correctly "
                f"(expected {needle!r}) - present but a SILENT no-op")

    # Shadowed leftovers: with core.hooksPath set, anything in .git/hooks is dead.
    # Silent, and exactly how a working hook gets disabled without a diff. RC's
    # .git/hooks carries a Share mirror sync, so this is a live risk there.
    if armed:
        legacy = common_git_dir(repo) / "hooks"
        if legacy.is_dir():
            stray = [p.name for p in legacy.iterdir()
                     if p.is_file() and not p.name.endswith(".sample")]
            if stray:
                problems.append(
                    f"INERT hooks shadowed in {legacy}: {', '.join(sorted(stray))} "
                    f"- core.hooksPath={HOOKS_DIRNAME} means these never run")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=str(ROOT))
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    repo = Path(a.repo).resolve()

    if not a.check:
        # Same defect class as check(): comparing against this working tree only
        # made the installer rewrite core.hooksPath from inside a worktree, and
        # that config is SHARED - it would mutate the main checkout's setting.
        if _resolve(effective_hooks_dir(repo)) not in tracked_hooks_dirs(repo):
            _git(repo, "config", "core.hooksPath", HOOKS_DIRNAME)
            print(f"set core.hooksPath = {HOOKS_DIRNAME}")

    problems = check(repo)
    if problems:
        sys.stderr.write("git-hook gate NOT ACTIVE:\n  " + "\n  ".join(problems) +
                         "\n")
        return 1
    print("git-hook gate active and correctly invoked")
    return 0


if __name__ == "__main__":
    sys.exit(main())
