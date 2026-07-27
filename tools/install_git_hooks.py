#!/usr/bin/env python3
r"""Install the glyph/ruff gate into .git/hooks so it survives EVERY channel.

WHY THIS EXISTS (docs/specs/2026-07-26-f1-sdk-executor-channel.md section 7, P0).
RC measured on 2026-07-26 that a nested
`claude -p --permission-mode bypassPermissions` lands a commit carrying a banned
em-dash: `.git/hooks/pre-commit` ran, the Claude PreToolUse gate did NOT. LW is
worse off than RC was - `.git/hooks/` here held only `.sample` files, so under
the F1 sdk executor channel the gate would have been absent entirely, unattended,
with no window and no operator watching.

A git hook is the only placement that survives every channel: AHK, SDK, a human
at a terminal, or CI. The PreToolUse copy stays as the fast in-session signal;
THIS is the authoritative one.

TWO hooks, not one, and that is not a style choice: at pre-commit time
`.git/COMMIT_EDITMSG` does not exist yet (verified 2026-07-26), so a lone
pre-commit hook would silently lose the commit-message glyph check.
  pre-commit -> precommit_gate.py --git-hook       (staged content)
  commit-msg -> precommit_gate.py --message-file $1 (the message)

`.git/hooks/` is NOT tracked by git, so this installer is the committed source of
truth and `--check` is wired into tools/drift_guard.py. Without that pairing the
gate silently un-installs itself on every fresh clone - which is exactly the
failure mode this whole item exists to prevent.

Usage:
  python tools/install_git_hooks.py            # install into this repo
  python tools/install_git_hooks.py --check    # verify; exit 1 on drift
  python tools/install_git_hooks.py --force    # overwrite a foreign hook
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

# Marker identifying a hook this installer owns. A hook WITHOUT it belongs to
# someone else (RC's pre-commit carries its Share mirror sync) and is never
# overwritten without --force.
MARKER = "# managed-by: tools/install_git_hooks.py"

# The project interpreter (CLAUDE.md Paths). Falls back to whatever is running
# this installer when that exact build is absent, so a clone on another box
# still gets a working hook rather than a silently dead one.
_PINNED = Path(r"C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe")
PYTHON = str(_PINNED if _PINNED.exists() else Path(sys.executable))

HOOKS = {
    "pre-commit": "--git-hook",
    "commit-msg": '--message-file "$1"',
}


def _body(name: str, gate: Path) -> str:
    """Hook script text. Git for Windows runs hooks through sh, so /bin/sh it is.

    Paths are forward-slashed: a backslash inside a double-quoted sh string is an
    escape, so C:\\LegionWallpaper would reach python as C:LegionWallpaper.
    """
    args = HOOKS[name]
    return (
        "#!/bin/sh\n"
        f"{MARKER}\n"
        "# Authoritative glyph/ruff gate - survives bypassPermissions, which the\n"
        "# Claude PreToolUse hook does not. Reinstall: python tools/install_git_hooks.py\n"
        f'exec "{PYTHON}" "{gate.as_posix()}" {args}\n'
    )


def _hooks_dir(repo: Path) -> Path:
    """Resolve .git/hooks, honoring worktrees (.git is a FILE there)."""
    out = subprocess.run(["git", "-C", str(repo), "rev-parse", "--git-common-dir"],
                         capture_output=True, text=True, errors="replace",
                         creationflags=NO_WINDOW).stdout.strip()
    if not out:
        return repo / ".git" / "hooks"
    d = Path(out)
    if not d.is_absolute():
        d = repo / d
    return d / "hooks"


def _expected(repo: Path) -> dict[Path, str]:
    gate = ROOT / "tools" / "precommit_gate.py"
    hd = _hooks_dir(repo)
    return {hd / name: _body(name, gate) for name in HOOKS}


def check(repo: Path) -> list[str]:
    """Return a list of drift descriptions; empty means installed and intact."""
    problems = []
    for path, want in _expected(repo).items():
        if not path.is_file():
            problems.append(f"MISSING {path.name}")
            continue
        try:
            got = path.read_text(encoding="utf-8")
        except OSError as e:
            problems.append(f"UNREADABLE {path.name}: {e}")
            continue
        if got != want:
            kind = "MODIFIED" if MARKER in got else "FOREIGN"
            problems.append(f"{kind} {path.name}")
    return problems


def install(repo: Path, force: bool) -> int:
    hd = _hooks_dir(repo)
    hd.mkdir(parents=True, exist_ok=True)
    for path, want in _expected(repo).items():
        if path.is_file():
            existing = path.read_text(encoding="utf-8", errors="replace")
            if MARKER not in existing and not force:
                sys.stderr.write(
                    f"REFUSING to overwrite {path}: it is not managed by this\n"
                    f"installer (no marker). Chain it manually or re-run with --force.\n"
                    f"RC's pre-commit carries its Share mirror sync - do not eat it.\n"
                )
                return 1
        tmp = path.with_suffix(".tmp")
        tmp.write_text(want, encoding="utf-8", newline="\n")
        os.replace(tmp, path)
        try:
            os.chmod(path, 0o755)
        except OSError:
            pass  # no-op on Windows; git for windows does not need the bit
        print(f"installed {path.name}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=str(ROOT))
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    repo = Path(a.repo).resolve()

    if a.check:
        problems = check(repo)
        if problems:
            sys.stderr.write("git-hook gate DRIFT: " + "; ".join(problems) +
                             "\nreinstall: python tools/install_git_hooks.py\n")
            return 1
        print("git-hook gate installed and intact")
        return 0
    return install(repo, a.force)


if __name__ == "__main__":
    sys.exit(main())
