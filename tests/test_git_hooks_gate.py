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


# ---- installer ---------------------------------------------------------

def _install(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(INSTALLER), "--repo", str(repo), *args],
                          capture_output=True, text=True, errors="replace")


@pytest.fixture()
def wired(repo: Path) -> Path:
    """A repo shaped like LW: TRACKED .githooks + the tools the hooks call.

    Hook bodies are tracked source that arrives with a clone; the only per-clone
    step is core.hooksPath. That is the contract the installer verifies.
    """
    (repo / ".githooks").mkdir()
    (repo / "tools").mkdir()
    for name in ("pre-commit", "commit-msg"):
        (repo / ".githooks" / name).write_text(
            (ROOT / ".githooks" / name).read_text(encoding="utf-8"),
            encoding="utf-8", newline="\n")
    for tool in ("precommit_gate.py", "precommit_msg_check.py"):
        src = ROOT / "tools" / tool
        if src.is_file():
            (repo / "tools" / tool).write_text(src.read_text(encoding="utf-8"),
                                               encoding="utf-8")
    return repo


def test_check_fails_when_hookspath_is_unset(wired: Path):
    """The trap that made a first cut of this tool report false green: correct
    hooks in .git/hooks are DEAD when core.hooksPath points elsewhere."""
    r = _install(wired, "--check")
    assert r.returncode != 0
    assert "core.hooksPath" in r.stderr


def test_install_sets_hookspath_then_passes(wired: Path):
    assert _install(wired).returncode == 0
    assert _git(wired, "config", "--get", "core.hooksPath").stdout.strip() == ".githooks"
    assert _install(wired, "--check").returncode == 0


def test_check_detects_missing_hook_file(wired: Path):
    _install(wired)
    (wired / ".githooks" / "commit-msg").unlink()
    r = _install(wired, "--check")
    assert r.returncode != 0
    assert "MISSING" in r.stderr


def test_check_detects_a_present_but_noop_invocation(wired: Path):
    """THE regression test for the real 2026-07-26 defect: the hook existed, was
    tracked, was executable, ran on every commit - and gated NOTHING, because it
    called the gate with no args and the gate self-gates to a no-op."""
    _install(wired)
    h = wired / ".githooks" / "pre-commit"
    h.write_text(h.read_text(encoding="utf-8").replace(
        'precommit_gate.py" --git-hook', 'precommit_gate.py"'),
        encoding="utf-8", newline="\n")
    r = _install(wired, "--check")
    assert r.returncode != 0, "a present-but-no-op hook must NOT read as installed"
    assert "no-op" in r.stderr


def test_check_reports_inert_shadowed_hooks(wired: Path):
    """With core.hooksPath set, anything in .git/hooks is dead. Silent, and
    exactly how a working hook (RC's Share mirror sync) gets disabled."""
    _install(wired)
    legacy = wired / ".git" / "hooks"
    legacy.mkdir(parents=True, exist_ok=True)
    (legacy / "pre-commit").write_text("#!/bin/sh\necho share sync\n",
                                       encoding="utf-8", newline="\n")
    r = _install(wired, "--check")
    assert r.returncode != 0
    assert "INERT" in r.stderr


# ---- end to end: a real commit through the real hooks ----------------------

def test_real_commit_is_blocked_by_staged_glyph(wired: Path):
    _install(wired)
    (wired / "doc.md").write_text(f"body glyph {EMDASH}\n", encoding="utf-8")
    _git(wired, "add", "-A")
    r = _git(wired, "commit", "-m", "docs: clean ascii subject")
    assert r.returncode != 0, "the pre-commit hook must block this"
    assert _git(wired, "log", "--oneline").stdout.strip() == "", "nothing may land"


def test_real_commit_message_glyph_is_blocked(wired: Path):
    _install(wired)
    (wired / "doc.md").write_text("clean body\n", encoding="utf-8")
    _git(wired, "add", "-A")
    r = _git(wired, "commit", "-m", f"docs: subject with {EMDASH} glyph")
    assert r.returncode != 0, "the commit-msg hook must block this"
    assert _git(wired, "log", "--oneline").stdout.strip() == ""


def test_real_commit_drops_the_trailer(wired: Path):
    _install(wired)
    (wired / "doc.md").write_text("clean body\n", encoding="utf-8")
    _git(wired, "add", "-A")
    r = _git(wired, "commit", "-m",
             "docs: real one\n\nCo-Authored-By: Claude Opus 5 <noreply@anthropic.com>")
    assert r.returncode == 0, r.stdout + r.stderr
    body = _git(wired, "log", "-1", "--format=%B").stdout
    assert "Co-Authored-By" not in body, "the trailer must not reach history"


def test_real_clean_commit_succeeds(wired: Path):
    _install(wired)
    (wired / "doc.md").write_text("clean body - ascii only\n", encoding="utf-8")
    _git(wired, "add", "-A")
    r = _git(wired, "commit", "-m", "feat: clean subject")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "feat: clean subject" in _git(wired, "log", "--oneline").stdout
