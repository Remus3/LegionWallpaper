"""The glyph/ruff gate must survive a channel that does not load Claude hooks.

RC measured (2026-07-26) that a nested `claude -p --permission-mode
bypassPermissions` commits WITHOUT the PreToolUse gate firing, while
`.git/hooks/*` ran normally. The gate therefore has to live in git itself or
the F1 sdk executor ships with no backstop at all
(docs/specs/2026-07-26-f1-sdk-executor-channel.md section 7, P0).

Two hooks, not one: `pre-commit` cannot see the commit message (verified - at
pre-commit time .git/COMMIT_EDITMSG does not exist yet), so the message-glyph
check that the PreToolUse gate does on the `-m` text has to run as `commit-msg`.

Every banned glyph here is built with chr() so this file stays 7-bit ASCII and
does not trip the very gate it tests.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
GATE = ROOT / "tools" / "precommit_gate.py"
INSTALLER = ROOT / "tools" / "install_git_hooks.py"
EMDASH = chr(0x2014)
SMART_Q = chr(0x201C)


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True, errors="replace")


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "r"
    r.mkdir()
    _git(r, "init", "-q", ".")
    _git(r, "config", "user.email", "t@example.com")
    _git(r, "config", "user.name", "t")
    return r


def _run_gate(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(GATE), *args], cwd=str(repo),
                          capture_output=True, text=True, errors="replace")


# ---- --git-hook mode (staged content) ----------------------------------

def test_git_hook_mode_blocks_staged_glyph(repo: Path):
    (repo / "doc.md").write_text(f"a line with an {EMDASH} in it\n", encoding="utf-8")
    _git(repo, "add", "doc.md")
    r = _run_gate(repo, "--git-hook")
    assert r.returncode != 0, "staged em-dash must block the commit"
    assert "em-dash" in r.stderr


def test_git_hook_mode_passes_clean_staged_content(repo: Path):
    (repo / "doc.md").write_text("a clean ASCII line - no glyphs\n", encoding="utf-8")
    _git(repo, "add", "doc.md")
    r = _run_gate(repo, "--git-hook")
    assert r.returncode == 0, r.stderr


def test_git_hook_mode_blocks_staged_syntax_error(repo: Path):
    (repo / "bad.py").write_text("def broken(:\n    pass\n", encoding="utf-8")
    _git(repo, "add", "bad.py")
    r = _run_gate(repo, "--git-hook")
    assert r.returncode != 0
    assert "py_compile" in r.stderr


def test_git_hook_mode_ignores_unstaged_glyph(repo: Path):
    """Only staged content gates - an unstaged glyph is the operator's business."""
    (repo / "clean.md").write_text("fine\n", encoding="utf-8")
    _git(repo, "add", "clean.md")
    (repo / "dirty.md").write_text(f"unstaged {EMDASH}\n", encoding="utf-8")
    r = _run_gate(repo, "--git-hook")
    assert r.returncode == 0, r.stderr


# ---- --message-file mode (commit message) ------------------------------

def test_message_file_blocks_glyph(repo: Path, tmp_path: Path):
    msg = tmp_path / "COMMIT_EDITMSG"
    msg.write_text(f"feat: something {EMDASH} else\n", encoding="utf-8")
    r = _run_gate(repo, "--message-file", str(msg))
    assert r.returncode != 0
    assert "em-dash" in r.stderr


def test_message_file_blocks_smart_quote(repo: Path, tmp_path: Path):
    msg = tmp_path / "COMMIT_EDITMSG"
    msg.write_text(f"fix: the {SMART_Q}thing\n", encoding="utf-8")
    r = _run_gate(repo, "--message-file", str(msg))
    assert r.returncode != 0


def test_message_file_ignores_comment_lines(repo: Path, tmp_path: Path):
    """git strips '#' lines from the message, so a glyph there is not shipped."""
    msg = tmp_path / "COMMIT_EDITMSG"
    msg.write_text(f"clean subject\n\n# a comment with {EMDASH} that git drops\n",
                   encoding="utf-8")
    r = _run_gate(repo, "--message-file", str(msg))
    assert r.returncode == 0, r.stderr


def test_message_file_passes_clean(repo: Path, tmp_path: Path):
    msg = tmp_path / "COMMIT_EDITMSG"
    msg.write_text("feat: plain ASCII subject - fine\n", encoding="utf-8")
    r = _run_gate(repo, "--message-file", str(msg))
    assert r.returncode == 0, r.stderr


# ---- co-author trailer (operator policy 2026-06-03) --------------------
# "never emit the Claude co-author trailer". Measured 2026-07-26: 84 of the
# last 200 LW commits carry it, so the policy was never actually enforced.
# commit-msg STRIPS rather than blocks - a trailer the tool appends is not the
# operator's mistake to fix, and blocking would wedge an unattended run.

def test_message_file_strips_claude_coauthor_trailer(repo: Path, tmp_path: Path):
    msg = tmp_path / "COMMIT_EDITMSG"
    msg.write_text(
        "feat: a thing\n\nbody line\n\n"
        "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>\n",
        encoding="utf-8")
    r = _run_gate(repo, "--message-file", str(msg))
    assert r.returncode == 0, r.stderr
    out = msg.read_text(encoding="utf-8")
    assert "Co-Authored-By" not in out
    assert "anthropic" not in out.lower()
    assert "feat: a thing" in out and "body line" in out


def test_message_file_strips_lowercase_variant(repo: Path, tmp_path: Path):
    msg = tmp_path / "COMMIT_EDITMSG"
    msg.write_text("fix: x\n\nCo-authored-by: Claude <noreply@anthropic.com>\n",
                   encoding="utf-8")
    _run_gate(repo, "--message-file", str(msg))
    assert "claude" not in msg.read_text(encoding="utf-8").lower()


def test_message_file_keeps_a_human_coauthor(repo: Path, tmp_path: Path):
    """Only the Claude/Anthropic trailer is policy - a real co-author stays."""
    msg = tmp_path / "COMMIT_EDITMSG"
    msg.write_text("feat: y\n\nCo-Authored-By: Some Person <p@example.com>\n",
                   encoding="utf-8")
    r = _run_gate(repo, "--message-file", str(msg))
    assert r.returncode == 0
    assert "Some Person" in msg.read_text(encoding="utf-8")


def test_message_file_untouched_when_no_trailer(repo: Path, tmp_path: Path):
    msg = tmp_path / "COMMIT_EDITMSG"
    before = "feat: z\n\nplain body\n"
    msg.write_text(before, encoding="utf-8")
    _run_gate(repo, "--message-file", str(msg))
    assert msg.read_text(encoding="utf-8") == before


def test_real_commit_drops_the_trailer(repo: Path):
    _install(repo)
    (repo / "doc.md").write_text("clean body\n", encoding="utf-8")
    _git(repo, "add", "doc.md")
    r = _git(repo, "commit", "-m",
             "feat: real one\n\nCo-Authored-By: Claude Opus 5 <noreply@anthropic.com>")
    assert r.returncode == 0, r.stdout + r.stderr
    body = _git(repo, "log", "-1", "--format=%B").stdout
    assert "Co-Authored-By" not in body, "the trailer must not reach history"
    assert "feat: real one" in body


# ---- installer ---------------------------------------------------------

def _install(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(INSTALLER), "--repo", str(repo), *args],
                          capture_output=True, text=True, errors="replace")


def test_installer_writes_both_hooks(repo: Path):
    r = _install(repo)
    assert r.returncode == 0, r.stderr
    for name in ("pre-commit", "commit-msg"):
        h = repo / ".git" / "hooks" / name
        assert h.is_file(), f"{name} not installed"
        assert "precommit_gate.py" in h.read_text(encoding="utf-8")


def test_installer_check_passes_after_install(repo: Path):
    _install(repo)
    r = _install(repo, "--check")
    assert r.returncode == 0, r.stdout + r.stderr


def test_installer_check_detects_missing_hook(repo: Path):
    _install(repo)
    (repo / ".git" / "hooks" / "commit-msg").unlink()
    r = _install(repo, "--check")
    assert r.returncode != 0, "a removed hook must be reported as drift"


def test_installer_check_detects_modified_hook(repo: Path):
    _install(repo)
    h = repo / ".git" / "hooks" / "pre-commit"
    h.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    r = _install(repo, "--check")
    assert r.returncode != 0, "a neutered hook must be reported as drift"


def test_installer_refuses_to_clobber_a_foreign_hook(repo: Path):
    """RC's .git/hooks/pre-commit carries its Share sync - never silently eat it."""
    h = repo / ".git" / "hooks" / "pre-commit"
    h.write_text("#!/bin/sh\necho someone elses hook\n", encoding="utf-8")
    r = _install(repo)
    assert r.returncode != 0
    assert "--force" in (r.stdout + r.stderr)
    assert "someone elses hook" in h.read_text(encoding="utf-8"), "must not overwrite"


# ---- end to end: a real commit --------------------------------------------

def test_real_commit_is_blocked_by_installed_hooks(repo: Path):
    _install(repo)
    (repo / "doc.md").write_text(f"body glyph {EMDASH}\n", encoding="utf-8")
    _git(repo, "add", "doc.md")
    r = _git(repo, "commit", "-m", "clean ASCII subject")
    assert r.returncode != 0, "the installed pre-commit hook must block this"
    log = _git(repo, "log", "--oneline")
    assert log.stdout.strip() == "", "nothing may land"


def test_real_commit_message_glyph_is_blocked(repo: Path):
    _install(repo)
    (repo / "doc.md").write_text("clean body\n", encoding="utf-8")
    _git(repo, "add", "doc.md")
    r = _git(repo, "commit", "-m", f"subject with {EMDASH} glyph")
    assert r.returncode != 0, "the installed commit-msg hook must block this"
    assert _git(repo, "log", "--oneline").stdout.strip() == ""


def test_real_clean_commit_succeeds(repo: Path):
    _install(repo)
    (repo / "doc.md").write_text("clean body - ascii only\n", encoding="utf-8")
    _git(repo, "add", "doc.md")
    r = _git(repo, "commit", "-m", "feat: clean subject")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "feat: clean subject" in _git(repo, "log", "--oneline").stdout
